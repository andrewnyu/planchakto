import base64,io
import pytest
from fastapi.testclient import TestClient
from backend.store import LocalStore
from backend.example import example
from backend.engine import compute
from backend import quickcheck as q
from backend.rules import STRUCTURAL
import backend.main as main

TRUTH=q.StructuralSheet.model_validate_json((q.SAMPLE_DIR/'structure-sample.sheet.json').read_text())

@pytest.fixture
def store(tmp_path):return LocalStore(str(tmp_path/'test.sqlite3'))
@pytest.fixture
def client(store,monkeypatch):
    monkeypatch.setattr(main,'_store',store)
    for v in ['GEMINI_API_KEY','OPENROUTER_API_KEY','BUILDGRAPH_AI_PROVIDER','GOOGLE_CLOUD_PROJECT']:monkeypatch.delenv(v,raising=False)
    return TestClient(main.app)

def sheet(**changes):return TRUTH.model_copy(update=changes)
def inputs(**changes):i,_,_=q.map_structural(TRUTH);return q.StructuralInputs(**(i|changes))
def pdf(pages=2):
    from reportlab.pdfgen import canvas
    buf=io.BytesIO();c=canvas.Canvas(buf)
    for n in range(pages):c.drawString(100,700,f'Sheet {n+1}');c.showPage()
    c.save();return buf.getvalue()

def test_unscoped_compute_still_covers_every_discipline():
    r=compute(example(),'r')
    assert 'coverage' not in r and 'scope' not in r
    assert {'LAYOUT','FITOUT','ROUTE','DRAIN','ELECTRICAL','SLS','BEARING'}<={c['rule_id'] for c in r['checks']}

def test_scoped_compute_reports_only_structure_and_lists_the_rest():
    b=q.building_from_inputs(inputs(),'sample');r=compute(b,'qc',scope='structure')
    rules={c['rule_id'] for c in r['checks']}
    assert rules<=STRUCTURAL|{'PH-CODE'} and {'SLS','ELASTIC','BEARING','SEISMIC-V'}<=rules
    assert not rules&{'LAYOUT','FITOUT','ROUTE','DRAIN','ELECTRICAL'}
    assert r['scope']=='structure' and {x['item'] for x in r['coverage']['not_checked']}>={'Plumbing and electrical routes','Fire protection'}
    assert not any('Plumbing hydraulic' in c['evidence'] for c in r['checks'])
    with pytest.raises(ValueError):compute(b,'qc',scope='plumbing')

def test_the_recorded_sample_maps_to_the_drawn_frame():
    i,t,notes=q.map_structural(TRUTH)
    assert i['grid_x']==[0,5,10,15] and i['grid_y']==[0,4,8] and len(i['columns'])==12
    assert (i['section'],i['column_section'],i['dead'],i['live'],i['soil'],i['height'])==('RHS150','SHS150',.65,.75,96,3.5)
    assert t['residual']<1 and abs(t['sx']*15+t['ox']-711.1)<1
    assert i['r_factor'] is None and 'zone' in i['assumed']

def test_the_sample_finds_the_undersized_interior_beams():
    b=q.building_from_inputs(inputs(),'sample');r=compute(b,'qc','structure')
    failing={x['y'] for x in r['structure']['beams'] if x['status']=='fail'}
    assert failing=={4.0}  # row 2 carries twice the tributary width of the edge rows
    assert all(c['status']=='missing_input' for c in r['checks'] if c['rule_id'] in ('SEISMIC-V','DRIFT'))

def test_values_missing_from_the_sheet_stay_missing():
    s=sheet(loads=[],height_m=None,sections=[])
    i,_,notes=q.map_structural(s)
    assert i['dead'] is None and i['live'] is None and i['soil'] is None and i['height'] is None
    assert {'section','column_section'}<=set(i['assumed'])
    assert {n.field for n in notes if n.level=='missing'}>={'dead','live','soil','height'}
    b=q.building_from_inputs(q.StructuralInputs(**(i|{'height':3})),'x');r=compute(b,'qc','structure')
    assert r['structure']['status']=='missing_input' and b.engineering.soil.value is None
    assert {c['status'] for c in r['checks'] if c['rule_id'] in ('SLS','ELASTIC')}=={'missing_input'}
    with pytest.raises(ValueError,match='storey height'):q.building_from_inputs(q.StructuralInputs(**i),'x')

def test_sources_say_where_each_value_came_from():
    b=q.building_from_inputs(inputs(r_factor=4.5,entered=['r_factor'],assumed=['soil']),'x');e=b.engineering
    assert e.dead.source==q.ON_SHEET and e.soil.source==q.ASSUMED and e.lateral.r_factor.source==q.ENTERED and e.lateral.na.source=='Not on the drawing'

def test_section_and_grid_reference_parsing():
    from backend.structure import CATALOG,COLUMNS
    assert q.parse_section('RHS 150x100x5',CATALOG)==('RHS150',True)
    assert q.parse_section('RHS200',CATALOG)==('RHS200',True)
    assert q.parse_section('RHS 250 X 150 X 8.0',CATALOG)==('RHS250',True)
    assert q.parse_section('W8x18',CATALOG)[1] is False
    assert q.parse_section('SHS 200x200x8',COLUMNS)==('SHS200',True)
    assert q.parse_section('C1 COLUMN SHS 150x150x6',COLUMNS)==('SHS150',True)
    assert q.parse_section('RB ROOF BEAM RHS 150x100x5',CATALOG)==('RHS150',True)
    assert q.parse_section('RHS 200',CATALOG)==('RHS200',True)
    assert q.parse_section('2-RHS 175x100x6',CATALOG)==('RHS150',False)
    for ref in ['B-2','b2','2-B','B/2']:assert q.parse_grid_ref(ref,['A','B','C'],['1','2'])==(1,1)
    assert q.parse_grid_ref('E-9',['A','B'],['1','2']) is None

def test_unsupported_and_conflicting_reads_are_flagged_not_forced():
    _,_,notes=q.map_structural(sheet(storeys=2,outside_supported=[q.Flag(reason='Cantilevered canopy on grid D')]))
    assert sum(n.level=='unsupported' for n in notes)==2
    _,_,notes=q.map_structural(sheet(sheet_kind='floor_plan'))
    assert any(n.level=='unsupported' and 'framing' in n.message for n in notes)
    _,_,notes=q.map_structural(sheet(columns=[q.SheetColumn(grid='Z-9')]))
    assert any(n.level=='conflict' and 'Z-9' in n.message for n in notes)
    i,t,notes=q.map_structural(sheet(grid_x=[q.GridLine(label='A',position=0),q.GridLine(label='B',position=None)]))
    assert t is None and any(n.field=='grid_x' and n.level=='missing' for n in notes)

def test_grid_dimensioned_from_the_far_end_is_normalised():
    flipped=[q.GridLine(label=g.label,position=15000-g.position,page=g.page) for g in TRUTH.grid_x]
    i,t,_=q.map_structural(sheet(grid_x=flipped))
    assert i['grid_x']==[0,5,10,15] and t['residual']<1

def test_rasterize_pdf_pages_and_images():
    png,w,h,pages=q.rasterize(pdf(2),'application/pdf',1)
    assert png[:4]==b'\x89PNG' and pages==2 and max(w,h)<=q.MAX_SIDE
    with pytest.raises(ValueError,match='2 page'):q.rasterize(pdf(2),'application/pdf',5)
    with pytest.raises(ValueError):q.rasterize(b'not an image','image/png')

def test_sample_flow_never_touches_the_project(client,store):
    head=store.state()['head'];revisions=len(store.list())
    r=client.post('/api/quick-checks/sample',json={'discipline':'structure'});assert r.status_code==200,r.text
    record=r.json();assert record['status']=='confirm' and record['mode']=='recorded' and record['results'] is None
    img=client.get(f'/api/quick-checks/{record["id"]}/image');assert img.status_code==200 and img.content[:4]==b'\x89PNG'
    run=client.post(f'/api/quick-checks/{record["id"]}/run',json=record['inputs']);assert run.status_code==200,run.text
    done=run.json();assert done['status']=='checked' and done['results']['summary']['fail']==6
    assert client.get(f'/api/quick-checks/{record["id"]}').json()['status']=='checked'
    assert store.state()['head']==head and len(store.list())==revisions

def test_upload_without_a_provider_is_explained_and_saves_nothing(client):
    data=base64.b64encode((q.SAMPLE_DIR/'structure-sample.png').read_bytes()).decode()
    r=client.post('/api/quick-checks',json={'attachment':{'name':'s.png','mime_type':'image/png','data':data}})
    assert r.status_code==503 and r.json()['mode']=='unavailable'

def test_upload_reads_through_the_injected_reader(client,store,monkeypatch):
    monkeypatch.setattr(q,'extract_structural',lambda png:TRUTH)
    data=base64.b64encode(pdf(1)).decode()
    r=client.post('/api/quick-checks',json={'attachment':{'name':'plan.pdf','mime_type':'application/pdf','data':data}})
    assert r.status_code==200,r.text
    assert r.json()['mode']=='live' and r.json()['source']['pages']==1 and 'sheet_png' not in r.json()

def test_bad_requests(client):
    assert client.get('/api/quick-checks/../../etc').status_code==404
    assert client.get('/api/quick-checks/qc-000000000000').status_code==404
    record=client.post('/api/quick-checks/sample',json={}).json()
    assert client.post(f'/api/quick-checks/{record["id"]}/run',json=record['inputs']|{'height':None}).status_code==422
    assert client.post(f'/api/quick-checks/{record["id"]}/run',json=record['inputs']|{'grid_x':[0,5,5,15]}).status_code==422

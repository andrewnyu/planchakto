import pytest
from fastapi.testclient import TestClient
from backend.store import LocalStore
from backend.engine import compute
from backend import quickcheck as q
from backend.rules import FIRE,STRUCTURAL
import backend.main as main

TRUTH=q.FireSheet.model_validate_json((q.SAMPLE_DIR/'fire-sample.sheet.json').read_text())

@pytest.fixture
def store(tmp_path):return LocalStore(str(tmp_path/'test.sqlite3'))
@pytest.fixture
def client(store,monkeypatch):
    monkeypatch.setattr(main,'_store',store)
    for v in ['GEMINI_API_KEY','OPENROUTER_API_KEY','BUILDGRAPH_AI_PROVIDER','GOOGLE_CLOUD_PROJECT']:monkeypatch.delenv(v,raising=False)
    return TestClient(main.app)

def sheet(**changes):return TRUTH.model_copy(update=changes)
def inputs(sheet=TRUTH,**changes):i,_,_=q.map_fire(sheet);return q.FireInputs(**(i|{'occupancy':'business','hazard':'low'}|changes))
def run(i):b,doors=q.building_from_fire(i,'sample');return compute(b,'qc','fire',doors=doors)

def test_fire_scope_reports_only_fire_rules_and_lists_the_rest():
    r=run(inputs());rules={c['rule_id'] for c in r['checks']}
    assert rules<=FIRE|{'PH-CODE'} and {'FIRE-OCCLOAD','FIRE-EXITS','FIRE-TRAVEL','FIRE-EXT'}<=rules
    assert not rules&(STRUCTURAL|{'LAYOUT','FITOUT','ROUTE','DRAIN','ELECTRICAL'})
    assert not any(k in c['evidence'] for c in r['checks'] for k in ('Foundation','seismic','Plumbing hydraulic'))
    assert r['scope']=='fire' and {x['item'] for x in r['coverage']['not_checked']}>={'Structure and seismic','Plumbing and electrical routes'}
    assert r['structure']['beams']==[] and r['lateral']=={'enabled':False}

def test_the_recorded_sample_maps_to_the_drawn_plan():
    i,t,notes=q.map_fire(TRUTH)
    assert (i['width'],i['depth'])==(20,12) and t['residual']==0
    rooms={r['name']:(r['x'],r['y'],r['w'],r['h']) for r in i['rooms']}
    assert rooms['CONFERENCE']==(12,0,8,5) and rooms['CORRIDOR']==(0,5,20,2) and sum(w*h for *_,w,h in rooms.values())==240
    assert len(i['doors'])==7 and all('room-corridor' in d['rooms'] for d in i['doors'])
    assert [(e['side'],e['offset'],e['width']) for e in i['exits']]==[('bottom',2.1,1.8),('left',5.55,.9),('right',5.55,.9)]
    assert i['extinguishers']==[{'id':'ext-1','x':2.4,'y':5.35,'rating':'2-A'}] and i['exit_signs'] and 'exit_signs' not in i['assumed']

def test_occupancy_is_never_assumed_and_missing_occupancy_blocks_the_run(client):
    i,_,notes=q.map_fire(TRUTH)
    assert i['occupancy'] is None and i['hazard'] is None  # rooms named OFFICE do not make it a business occupancy
    assert {n.field for n in notes if n.level=='missing'}>={'occupancy','hazard'}
    with pytest.raises(ValueError,match='occupancy'):q.building_from_fire(q.FireInputs(**(i|{'hazard':'low'})),'x')
    with pytest.raises(ValueError,match='hazard'):q.building_from_fire(q.FireInputs(**(i|{'occupancy':'business'})),'x')
    record=client.post('/api/quick-checks/sample',json={'discipline':'fire'}).json()
    r=client.post(f'/api/quick-checks/{record["id"]}/run',json=record['inputs']|{'hazard':'low'})
    assert r.status_code==422 and 'occupancy' in r.json()['detail']
    assert client.get(f'/api/quick-checks/{record["id"]}').json()['status']=='confirm'

def test_printed_occupancy_is_read_and_unsupported_ones_are_flagged():
    i,_,notes=q.map_fire(sheet(occupancy_text='OCCUPANCY: MERCANTILE (DIVISION C)'))
    assert i['occupancy']=='mercantile' and any(n.level=='read' and n.field=='occupancy' for n in notes)
    i,_,notes=q.map_fire(sheet(occupancy_text='RESIDENTIAL R-1'))
    assert i['occupancy'] is None and any(n.level=='unsupported' and n.field=='occupancy' for n in notes)

def test_the_sample_finds_the_extinguisher_and_alarm_gaps():
    r=run(inputs());status={c['rule_id']:c['status'] for c in r['checks'] if c['rule_id']!='FIRE-SCOPE'}
    assert {k for k,v in status.items() if v=='fail'}=={'FIRE-EXT','FIRE-ALARM'}
    assert status['FIRE-TRAVEL']=='pass' and status['FIRE-SIGNS']=='pass' and r['fire']['travel']['critical_path']
    assert len(r['fire']['exits'])==3 and len(r['fire']['doors'])==7
    assert r['fire']['extinguishers']['max_travel_m']>15

def test_travel_only_passes_through_doors_read_from_the_sheet():
    i=inputs();r=run(i.model_copy(update={'doors':[d for d in i.doors if 'room-conference' not in d.rooms]}))
    travel=next(c for c in r['checks'] if c['rule_id']=='FIRE-TRAVEL')
    assert travel['status']=='fail' and 'room-conference' in travel['evidence']

def test_a_drawn_plan_gets_no_implied_entrance():
    # The planning model adds a west entrance to its corridor; a drawing has only the exits it shows.
    r=run(inputs(exits=[]));exits=next(c for c in r['checks'] if c['rule_id']=='FIRE-EXITS')
    assert exits['status']=='fail' and exits['inputs']['provided']==0 and r['fire']['exits']==[]

def test_provisions_not_shown_are_treated_as_not_provided():
    i,_,notes=q.map_fire(sheet(provisions=[]))
    assert (i['sprinklered'],i['alarm'],i['exit_signs'],i['emergency_lighting'])==(False,'none',False,False)
    assert {'sprinklered','alarm','exit_signs','emergency_lighting'}<=set(i['assumed'])
    i,_,_=q.map_fire(sheet(provisions=[q.Provision(kind='alarm_manual'),q.Provision(kind='sprinklers',provided=False)]))
    assert i['alarm']=='manual' and i['sprinklered'] is False and 'sprinklered' not in i['assumed']

def test_extinguisher_ratings():
    assert q.parse_rating('2-A:10-B:C')==('2-A','') and q.parse_rating('3A 40BC')[0]=='3-A'
    assert q.parse_rating('6-A:80-B:C')[0]=='4-A' and q.parse_rating('1-A:10-B:C')[0] is None and q.parse_rating(None)[0] is None
    i,_,notes=q.map_fire(sheet(extinguishers=[q.SheetExtinguisher(point=[500,400]),q.SheetExtinguisher(point=[500,500],rating='1-A')]))
    assert len(i['extinguishers'])==1 and 'ext-1:rating' in i['assumed'] and any(n.level=='conflict' and '1-A' in n.message for n in notes)

def test_unreadable_geometry_is_missing_not_guessed():
    i,t,notes=q.map_fire(sheet(footprint=q.Footprint(box=TRUTH.footprint.box)))
    assert i['width'] is None and t is None and i['rooms']==[] and {'width','depth','rooms'}<={n.field for n in notes if n.level=='missing'}
    _,_,notes=q.map_fire(sheet(sheet_kind='framing_plan'))
    assert any(n.level=='unsupported' for n in notes)
    _,_,notes=q.map_fire(sheet(doors=[q.SheetDoor(between=['OFFICE A','STORAGE'],point=[100,100])]))
    assert any(n.level=='conflict' and n.field=='doors' for n in notes)

def test_bad_plans_are_refused():
    i=inputs();rooms=i.rooms
    with pytest.raises(ValueError,match='overlaps'):q.building_from_fire(i.model_copy(update={'rooms':rooms+[rooms[0].model_copy(update={'id':'dup','x':1})]}),'x')
    with pytest.raises(ValueError,match='90%'):q.building_from_fire(i.model_copy(update={'rooms':rooms[:4],'doors':[d for d in i.doors if d.rooms[1] in {r.id for r in rooms[:4]}]}),'x')
    with pytest.raises(ValueError,match='share a wall'):q.building_from_fire(i.model_copy(update={'doors':[q.FireDoor(id='d',rooms=['room-office-a','room-storage'])]}),'x')
    with pytest.raises(ValueError,match='beyond its wall'):q.building_from_fire(i.model_copy(update={'exits':[q.FireExit(id='e',side='left',offset=11.5,width=.9)]}),'x')

def test_fire_sample_flow_never_touches_the_project(client,store):
    head=store.state()['head'];revisions=len(store.list())
    record=client.post('/api/quick-checks/sample',json={'discipline':'fire'}).json()
    assert record['discipline']=='fire' and record['mode']=='recorded' and record['inputs']['occupancy'] is None
    r=client.post(f'/api/quick-checks/{record["id"]}/run',json=record['inputs']|{'occupancy':'business','hazard':'low'});assert r.status_code==200,r.text
    done=r.json();assert done['status']=='checked' and done['results']['summary']['fail']==2 and done['inputs']['occupancy']=='business'
    assert store.state()['head']==head and len(store.list())==revisions
    assert client.post(f'/api/quick-checks/{record["id"]}/run',json={'grid_x':[0,5]}).status_code==422  # structural inputs on a fire check

def test_fire_upload_reads_through_the_injected_reader(client,monkeypatch):
    import base64
    monkeypatch.setattr(q,'extract_fire',lambda png:TRUTH)
    data=base64.b64encode((q.SAMPLE_DIR/'fire-sample.png').read_bytes()).decode()
    r=client.post('/api/quick-checks',json={'discipline':'fire','attachment':{'name':'plan.png','mime_type':'image/png','data':data}})
    assert r.status_code==200,r.text
    assert r.json()['mode']=='live' and r.json()['discipline']=='fire' and len(r.json()['inputs']['rooms'])==8

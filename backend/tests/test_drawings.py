import io,re,pytest,ezdxf
from fastapi.testclient import TestClient
from backend.example import example
from backend.domain import apply_commands,SetFire,FireProtection,ExitDoor,SetSolar,Solar
from backend.engine import compute
from backend.drawings import sheet_set,render_pdf,render_dxf,PermitRequest,LAYERS
from backend.store import LocalStore
import backend.main as main

def full():
    b,_=apply_commands(example(),[SetSolar(type='set_solar',solar=Solar(enabled=True)),SetFire(type='set_fire',fire=FireProtection(enabled=True,exits=[ExitDoor(id='exit-east',wall='east',offset=4.2,width=1)]))]);return b,compute(b,'rev-x')

def test_sheet_set_per_discipline_and_optional_fire_sheet():
    b=example();r=compute(b,'a')
    assert [s['number'] for s in sheet_set(b,r,PermitRequest())]==['A-1','A-2','S-1','E-1','P-1']   # FP needs the fire screen
    b,r=full()
    sheets=sheet_set(b,r,PermitRequest())
    assert [s['number'] for s in sheets]==['A-1','A-2','S-1','E-1','P-1','FP-1']
    assert 'PV SINGLE-LINE' in sheets[3]['title'] and any(p[0]=='oneline' for p in sheets[3]['panels'])
    assert [s['number'] for s in sheet_set(b,r,PermitRequest(disciplines=['S','FP']))]==['S-1','FP-1']

def test_schedules_come_from_the_analysis():
    b,r=full();s1=next(s for s in sheet_set(b,r,PermitRequest()) if s['number']=='S-1')
    beams=dict((p[1],p[2]) for p in s1['panels'] if p[0]=='table')['BEAM SCHEDULE'][1]
    assert len(beams)==len(r['structure']['beams']) and beams[0][2]==b.engineering.section

@pytest.mark.parametrize('size,mm',[('20x30',(762,508)),('A3',(420,297))])
def test_pdf_one_page_per_sheet_at_the_requested_size(size,mm):
    b,r=full();pdf=render_pdf(b,r,PermitRequest(sheet=size),'rev-x')
    assert pdf.startswith(b'%PDF') and len(re.findall(rb'/Type /Page\b',pdf))==6
    boxes={tuple(float(v) for v in m.split()[2:]) for m in re.findall(rb'/MediaBox \[([^\]]*)\]',pdf)}
    assert len(boxes)==1 and all(abs(w-mm[0]*72/25.4)<.01 and abs(h-mm[1]*72/25.4)<.01 for w,h in boxes)

def test_dxf_layers_units_and_flipped_y():
    b,r=full();doc=ezdxf.read(io.StringIO(render_dxf(b,r,PermitRequest(),'rev-x').decode()))
    assert doc.header['$INSUNITS']==6 and set(LAYERS)<=set(l.dxf.name for l in doc.layers)
    used={e.dxf.layer for e in doc.modelspace()}
    assert {'A-WALL','S-BEAM','S-FNDN','E-POWR','E-PV','P-SANR','FP-EGRS'}<=used
    beams=[e for e in doc.modelspace() if e.dxf.layer=='S-BEAM']
    assert len(beams)==len(r['structure']['beams'])+len(r['structure']['girders']) and all(e.dxf.start.y<=0 for e in beams)   # roof beams + grid girders; plan y-down → CAD y-up

def test_permit_endpoints(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'_store',LocalStore(str(tmp_path/'t.sqlite3')));client=TestClient(main.app)
    head=client.get('/api/project').json()['state']['head']
    r=client.post(f'/api/export/{head}/permit.pdf',json={'sheet':'A3','owner':'Sample Owner','professionals':{'A':{'name':'Sample Architect','prc_no':'0000000'}}})
    assert r.status_code==200 and r.headers['content-type']=='application/pdf' and r.content.startswith(b'%PDF')
    d=client.post(f'/api/export/{head}/permit.dxf',json={})
    assert d.status_code==200 and b'SECTION' in d.content[:200]
    assert client.post(f'/api/export/{head}/permit.pdf',json={'sheet':'A0'}).status_code==422

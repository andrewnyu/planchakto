"""Live eval of the Quick check drawing readings against sheets whose answer is known.

Cases:
  sample        the bundled framing plan; truth is its recorded reading
  demo-S1       the demo project's own S-1 permit sheet rendered by drawings.py; truth is the demo model
  demo-A1       the demo's architectural sheet; a structural reading must flag it as not a framing plan
  fire-sample   the bundled floor plan; truth is its recorded reading, and the unprinted occupancy must stay unread
  demo-FP1      the fire demo's FP-1 sheet; its printed occupancy and provisions must be read, and with no overall
                dimension strings the footprint must be read correctly or left missing
  fire-on-S     the framing plan read as a floor plan must be flagged as not a floor plan

Needs a configured provider (Gemini in the deployed build). Run from the repo root:
    .venv/bin/python scripts/eval_quick_check.py                                   # provider from .env
    .venv/bin/python scripts/eval_quick_check.py --vertex planchakto --gcloud-user  # Vertex AI with your gcloud login
    .venv/bin/python scripts/eval_quick_check.py --vertex planchakto --gcloud-user --only fire
"""
import argparse,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend import quickcheck as q
from backend.example import example
from backend.engine import compute
from backend.drawings import render_pdf,PermitRequest
from backend.domain import FireProtection

def demo_sheet(discipline,b=None):
    b=b or example();return render_pdf(b,compute(b,'eval'),PermitRequest(disciplines=[discipline],sheet='A3'),'eval')

def fire_demo():
    b=example();b.fire=FireProtection(enabled=True,occupancy='business');return b

def expect_inputs(got,want,keys):return [f'{k}: read {got[k]!r}, expected {want[k]!r}' for k in keys if got[k]!=want[k]]

def near(a,b,tol):return abs(a-b)<=tol

def expect_fire(i,truth,tol=.35):
    """Rooms, doors, exits and extinguishers match the drawn plan within `tol` metres; occupancy is never inferred."""
    out=expect_inputs(i,truth,['width','depth','occupancy','hazard','exit_signs'])
    want={r['name'].upper():r for r in truth['rooms']};got={r['name'].upper():r for r in i['rooms']}
    if set(got)!=set(want):out.append(f'rooms {sorted(got)}, expected {sorted(want)}')
    out+=[f'{n} at {[g[k] for k in "xywh"]}, expected {[want[n][k] for k in "xywh"]}' for n,g in got.items() if n in want and not all(near(g[k],want[n][k],tol) for k in 'xywh')]
    pairs=lambda x:sorted(sorted(next(r['name'].upper() for r in x['rooms'] if r['id']==id) for id in d['rooms']) for d in x['doors'])
    if pairs(i)!=pairs(truth):out.append(f'doors {pairs(i)}, expected {pairs(truth)}')
    key=lambda e:(e['side'],e['offset'])
    for g,w in zip(sorted(i['exits'],key=key),sorted(truth['exits'],key=key)):
        if g['side']!=w['side'] or not near(g['offset'],w['offset'],tol) or not near(g['width'],w['width'],.05):out.append(f'exit {g}, expected {w}')
    if len(i['exits'])!=len(truth['exits']):out.append(f'{len(i["exits"])} exits, expected {len(truth["exits"])}')
    if [(e['rating'],near(e['x'],w['x'],.6) and near(e['y'],w['y'],.6)) for e,w in zip(i['extinguishers'],truth['extinguishers'])]!=[(w['rating'],True) for w in truth['extinguishers']] or len(i['extinguishers'])!=len(truth['extinguishers']):
        out.append(f'extinguishers {i["extinguishers"]}, expected {truth["extinguishers"]}')
    return out

def expect_fp1(i,t,n):
    b=fire_demo();out=[]
    if i['occupancy']!='business':out.append(f'occupancy {i["occupancy"]!r}, expected the printed business occupancy')
    for field,value in [('sprinklered',False),('alarm','none'),('exit_signs',False),('emergency_lighting',False)]:
        if i[field]!=value or field in i['assumed']:out.append(f'{field}: {i[field]!r}{" (assumed)" if field in i["assumed"] else ""}, expected {value!r} read from the provisions table')
    # FP-1 has a scale bar but no overall dimension strings: the footprint is either read right or left missing.
    for field,value in [('width',b.width),('depth',b.depth)]:
        if i[field] is not None and not near(i[field],value,.3):out.append(f'{field} {i[field]} m, expected {value} m or missing')
    if i['width'] and i['depth']:
        names={r['name'].upper() for r in i['rooms']};want={r.name.upper() for r in b.rooms}
        if names!=want:out.append(f'rooms {sorted(names)}, expected {sorted(want)}')
        if [e['side'] for e in i['exits']]!=['left']:out.append(f'exits {i["exits"]}, expected one on the left wall')
    return out

def cases(only=None):
    truth,_,_=q.map_structural(q.StructuralSheet.model_validate_json((q.SAMPLE_DIR/'structure-sample.sheet.json').read_text()))
    keys=['grid_x','grid_y','section','column_section','dead','live','soil','height','footing_width','footing_thickness']
    if only in (None,'structure'):
        yield 'sample','structure',(q.SAMPLE_DIR/'structure-sample.png').read_bytes(),'image/png',lambda i,t,n:expect_inputs(i,truth,keys)+([] if len(i['columns'])==12 else [f'{len(i["columns"])} columns, expected 12'])
        b=example();e=b.engineering
        demo={'grid_x':b.grid_x,'grid_y':b.grid_y,'section':e.section,'column_section':e.column_section,'dead':e.dead.value,'live':e.live.value,'soil':e.soil.value}
        yield 'demo-S1','structure',demo_sheet('S'),'application/pdf',lambda i,t,n:expect_inputs(i,demo,list(demo))+([] if t and t['residual']<15 else ['grid not located on the page'])
        yield 'demo-A1','structure',demo_sheet('A'),'application/pdf',lambda i,t,n:[] if any(x.level=='unsupported' for x in n) else ['an architectural sheet was not flagged as outside the structural screen']
    if only in (None,'fire'):
        fire,_,_=q.map_fire(q.FireSheet.model_validate_json((q.SAMPLE_DIR/'fire-sample.sheet.json').read_text()))
        yield 'fire-sample','fire',(q.SAMPLE_DIR/'fire-sample.png').read_bytes(),'image/png',lambda i,t,n:expect_fire(i,fire)+([] if t else ['outline not located on the page'])
        yield 'demo-FP1','fire',demo_sheet('FP',fire_demo()),'application/pdf',expect_fp1
        yield 'fire-on-S','fire',(q.SAMPLE_DIR/'structure-sample.png').read_bytes(),'image/png',lambda i,t,n:[] if any(x.level=='unsupported' for x in n) else ['a framing plan was not flagged as outside the fire screen']

def run(readers=None,only=None):
    readers=readers or {'structure':q.extract_structural,'fire':q.extract_fire};maps={'structure':q.map_structural,'fire':q.map_fire}
    report=[]
    for name,discipline,raw,mime,check in cases(only):
        t=time.monotonic()
        try:
            png,*_=q.rasterize(raw,mime);inputs,transform,notes=maps[discipline](readers[discipline](png));problems=check(inputs,transform,notes)
        except Exception as e:problems=[f'{type(e).__name__}: {str(e)[:200]}']
        report.append({'case':name,'passed':not problems,'problems':problems,'seconds':round(time.monotonic()-t,1)})
        print(('PASS ' if not problems else 'FAIL ')+name,f"{report[-1]['seconds']}s",*problems,sep='\n  ' if problems else ' ')
    print(f"{sum(r['passed'] for r in report)}/{len(report)} passed")
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--vertex',metavar='PROJECT',help='use Vertex AI in this GCP project')
    ap.add_argument('--model',help='override GEMINI_MODEL')
    ap.add_argument('--gcloud-user',action='store_true',help='authenticate Vertex with `gcloud auth print-access-token` instead of ADC')
    ap.add_argument('--only',choices=['structure','fire'],help='run only this discipline\'s cases')
    args=ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent/'.env')
    if args.vertex:os.environ.update(BUILDGRAPH_AI_PROVIDER='vertex',GOOGLE_CLOUD_PROJECT=args.vertex);os.environ.setdefault('GEMINI_MODEL','gemini-3.8-flash')
    if args.model:os.environ['GEMINI_MODEL']=args.model
    if args.gcloud_user:
        import google.auth
        from google.oauth2.credentials import Credentials
        token=subprocess.run(['gcloud','auth','print-access-token'],capture_output=True,text=True,check=True).stdout.strip()
        creds=Credentials(token,quota_project_id=os.environ['GOOGLE_CLOUD_PROJECT'])
        google.auth.default=lambda *a,**k:(creds,os.environ['GOOGLE_CLOUD_PROJECT'])
    if not q.ai.configured():sys.exit('No AI provider is configured; set one in .env or pass --vertex PROJECT.')
    print('Provider',q.ai.status())
    sys.exit(0 if all(r['passed'] for r in run(only=args.only)) else 1)

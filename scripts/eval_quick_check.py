"""Live eval of the Quick check structural reading against sheets whose answer is known.

Cases:
  sample    the bundled framing plan; truth is its recorded reading
  demo-S1   the demo project's own S-1 permit sheet rendered by drawings.py; truth is the demo model
  demo-A1   the demo's architectural sheet; a structural reading must flag it as not a framing plan

Needs a configured provider (Gemini in the deployed build). Run from the repo root:
    .venv/bin/python scripts/eval_quick_check.py                                   # provider from .env
    .venv/bin/python scripts/eval_quick_check.py --vertex planchakto --gcloud-user  # Vertex AI with your gcloud login
"""
import argparse,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend import quickcheck as q
from backend.example import example
from backend.engine import compute
from backend.drawings import render_pdf,PermitRequest

def demo_sheet(discipline):
    b=example();return render_pdf(b,compute(b,'eval'),PermitRequest(disciplines=[discipline],sheet='A3'),'eval')

def expect_inputs(got,want,keys):return [f'{k}: read {got[k]!r}, expected {want[k]!r}' for k in keys if got[k]!=want[k]]

def cases():
    truth,_,_=q.map_structural(q.StructuralSheet.model_validate_json((q.SAMPLE_DIR/'structure-sample.sheet.json').read_text()))
    keys=['grid_x','grid_y','section','column_section','dead','live','soil','height','footing_width','footing_thickness']
    yield 'sample',(q.SAMPLE_DIR/'structure-sample.png').read_bytes(),'image/png',lambda i,t,n:expect_inputs(i,truth,keys)+([] if len(i['columns'])==12 else [f'{len(i["columns"])} columns, expected 12'])
    b=example();e=b.engineering
    demo={'grid_x':b.grid_x,'grid_y':b.grid_y,'section':e.section,'column_section':e.column_section,'dead':e.dead.value,'live':e.live.value,'soil':e.soil.value}
    yield 'demo-S1',demo_sheet('S'),'application/pdf',lambda i,t,n:expect_inputs(i,demo,list(demo))+([] if t and t['residual']<15 else ['grid not located on the page'])
    yield 'demo-A1',demo_sheet('A'),'application/pdf',lambda i,t,n:[] if any(x.level=='unsupported' for x in n) else ['an architectural sheet was not flagged as outside the structural screen']

def run(reader=q.extract_structural):
    report=[]
    for name,raw,mime,check in cases():
        t=time.monotonic()
        try:
            png,*_=q.rasterize(raw,mime);inputs,transform,notes=q.map_structural(reader(png));problems=check(inputs,transform,notes)
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
    sys.exit(0 if all(r['passed'] for r in run()) else 1)

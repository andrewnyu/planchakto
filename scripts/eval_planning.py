"""Live staged-design eval, isolated in a private database. Approval is a test actor, not user acceptance.
Usage: .venv/bin/python scripts/eval_planning.py --gcloud-user --brief file.txt [--site site.json]
Each gate and failure is recorded; no silent fallback to canned model output.
"""
import argparse,os,json,time,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--brief',type=Path,required=True);ap.add_argument('--site',type=Path);ap.add_argument('--programme',type=Path);ap.add_argument('--reference',type=Path);ap.add_argument('--vertex',default='planchakto');ap.add_argument('--model',default='gemini-3.8-flash');ap.add_argument('--gcloud-user',action='store_true');ap.add_argument('--output',type=Path,default=ROOT/'.data/evals/planning-live');ap.add_argument('--stop-after',choices=['programme','strategy','layout','details','outputs'],default='outputs');ap.add_argument('--resume',action='store_true');ap.add_argument('--regenerate-stage',choices=['programme','strategy','layout','details']);args=ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env');os.environ.update(BUILDGRAPH_AI_PROVIDER='vertex',GOOGLE_CLOUD_PROJECT=args.vertex,GEMINI_MODEL=args.model)
    if args.gcloud_user:
        import google.auth
        from google.oauth2.credentials import Credentials
        def credentials(*a,**kw):
            token=subprocess.run(['gcloud','auth','print-access-token'],capture_output=True,text=True,check=True).stdout.strip();return Credentials(token,quota_project_id=args.vertex),args.vertex
        google.auth.default=credentials
    from backend.store import LocalStore
    from backend import planning_workflow as w,planning_outputs as outputs,ai
    from backend.planning_details import quantities
    from backend.planning_models import EngineeringInputs
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'report.json').exists():(args.output/f'report-prior-{time.time_ns()}.json').write_bytes((args.output/'report.json').read_bytes())
    store=LocalStore(str(args.output/'preview.sqlite3'));report={'started_at':time.time(),'provider':ai.status(),'gates':[],'acceptance_actor':'Automated evaluation only; never user acceptance','attempts':[]}
    previous=store.latest_compose_session(('planning_active',)) if args.resume else None
    s=w.view(store,previous) if previous else w.create(store,'commercial',args.brief.read_text())
    if args.site and not s['site']:
        value=json.loads(args.site.read_text());s=w.set_site(store,s['id'],s['version'],value.get('site',value))
    attachment=None
    if args.reference:
        import base64,mimetypes
        attachment=ai.Attachment(name=args.reference.name,mime_type=mimetypes.guess_type(args.reference)[0] or 'application/pdf',data=base64.b64encode(args.reference.read_bytes()).decode())
    try:
        for stage in w.DESIGN_STAGES:
            if stage in s['refs'] and stage!=args.regenerate_stage:continue
            started=time.monotonic();prior_ids={p['id'] for p in s['proposals']};value=json.loads(args.programme.read_text()) if stage=='programme' and args.programme else None
            messages={'programme':args.brief.read_text(),'strategy':'Develop two access strategies for the confirmed programme. A simple initial approach is enough; vehicle turning remains unresolved.','layout':'Produce two complete schemes. Bind ALL operating spaces to their exact requirement IDs, including every bedroom or support room. Preserve confirmed capacities and make parking envelopes large enough for actual bays and aisles. Plan support groups so rooms can actually fit.','details':'Resolve the confirmed operating programme fully. Place all requested parking and cashiers, room functions, equipment and pedestrian/vehicle routes. Check actual array extents and keep clear of doors. Include support fixtures. Preserve requirements; report inability honestly.'}
            s=w.propose(store,s['id'],s['version'],stage,messages[stage],value=value,attachment=attachment if stage=='programme' else None,trace=lambda row:report['attempts'].append({'stage':stage,**row}))
            proposal=next(p for p in reversed(s['proposals']) if p['stage']==stage);s=w.accept(store,s['id'],s['version'],proposal['id']);report['gates'].append({'stage':stage,'seconds':round(time.monotonic()-started,2),'alternatives':len([p for p in s['proposals'] if p['stage']==stage and p['id'] not in prior_ids]),'artifact':s['refs'][stage]});print(stage,report['gates'][-1],flush=True)
            (args.output/'report.json').write_text(json.dumps(report,indent=2));(args.output/'session.json').write_text(json.dumps(s,indent=2))
            if args.stop_after==stage:return
        review=w.approval_review(store,w.load(store,s['id']));(args.output/'approval-review.json').write_text(json.dumps(review,indent=2))
        s=w.approve(store,s['id'],s['version'],True,actor='automated_evaluation');s=w.propose(store,s['id'],s['version'],'inputs',value={});s=w.accept(store,s['id'],s['version'],s['proposals'][-1]['id']);s=w.checks(store,s['id'],s['version']);v=outputs.bundle(store,w.load(store,s['id']));(args.output/'review.pdf').write_bytes(outputs.render_pdf(v));(args.output/'review.zip').write_bytes(outputs.render_zip(v));report['findings']=s['analysis']['summary'];report['result_hash']=s['analysis']['result_hash'];report['completed_at']=time.time();(args.output/'session.json').write_text(json.dumps(s,indent=2));print('Completed:',report['findings'],flush=True)
    except Exception as exc:
        report['error']=str(exc);raise
    finally:(args.output/'report.json').write_text(json.dumps(report,indent=2))

if __name__=='__main__':main()

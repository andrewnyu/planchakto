"""Live advisory-role evaluation against an existing private staged-planning session.

Reviews share one frozen design and deterministic analysis. Only advisory artifacts are
saved; accepted design stages and engineering inputs are never changed. No canned replies.

Example:
  .venv/bin/python scripts/eval_specialists.py --db .data/evals/planning-live/preview.sqlite3 \
    --session latest --roles structure,fire_accessibility --vertex planchakto \
    --model gemini-3.8-flash --gcloud-user --output .data/evals/specialists-live
"""
from __future__ import annotations
import argparse,datetime,json,os,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def parser():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db',type=Path,required=True,help='Existing private planning SQLite database; never creates a session')
    ap.add_argument('--session',default='latest',help='Planning session ID, or latest (default)')
    ap.add_argument('--roles',default='structure,fire_accessibility',help='Comma-separated advisory roles; run sequentially against one frozen analysis')
    ap.add_argument('--vertex',default='planchakto',help='Google Cloud project; overrides .env provider settings')
    ap.add_argument('--model',default='gemini-3.8-flash',help='Gemini model; overrides .env model settings')
    ap.add_argument('--gcloud-user',action='store_true',help='Obtain fresh credentials from the local gcloud user without printing tokens')
    ap.add_argument('--output',type=Path,default=ROOT/'.data/evals'/('specialists-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')),help='New private output directory; use .data/ inside this repo')
    ap.add_argument('--max-seconds',type=float,default=330,help='Shared evaluation budget in seconds (default 330); each role remains capped at 165')
    return ap


def write_json(path,value):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    temporary.replace(path)


def configure(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    os.environ.update(BUILDGRAPH_AI_PROVIDER='vertex',GOOGLE_CLOUD_PROJECT=args.vertex,GEMINI_MODEL=args.model)
    if args.gcloud_user:
        import google.auth
        from google.oauth2.credentials import Credentials
        def credentials(*unused_args,**unused_kwargs):
            result=subprocess.run(['gcloud','auth','print-access-token'],capture_output=True,text=True,check=False,timeout=30)
            if result.returncode or not result.stdout.strip():
                raise RuntimeError('Could not obtain a fresh gcloud user access token. Check the local gcloud login.')
            return Credentials(result.stdout.strip(),quota_project_id=args.vertex),args.vertex
        google.auth.default=credentials


def snapshot_key(bundle):
    analysis=bundle.get('analysis') or {}
    return (analysis.get('design_hash'),analysis.get('inputs_hash'),analysis.get('result_hash'),bundle.get('analysis_id'))


def main():
    ap=parser();args=ap.parse_args()
    if not args.db.expanduser().is_file():ap.error('--db must name an existing SQLite database')
    if not 75<=args.max_seconds<=3600:ap.error('--max-seconds must be between 75 and 3600')
    args.db=args.db.expanduser().resolve();args.output=args.output.expanduser().resolve()
    try:relative=args.output.relative_to(ROOT)
    except ValueError:relative=None
    if relative is not None and (not relative.parts or relative.parts[0] not in ('.data','artifacts')):
        ap.error('Private reports inside this repository must be under .data/ or artifacts/')
    if (args.output/'report.json').exists():ap.error('--output already contains report.json; choose a new private directory')
    from backend import planning_agents as agents
    roles=[role.strip() for role in args.roles.split(',') if role.strip()]
    if not roles or len(roles)!=len(set(roles)) or any(role not in agents.ROLES for role in roles):
        ap.error('--roles must contain distinct roles from: '+','.join(agents.ROLES))
    args.output.mkdir(parents=True,exist_ok=True)
    report={'started_at':time.time(),'database':str(args.db),'requested_session':args.session,'roles':roles,
        'max_seconds':args.max_seconds,'execution':'Sequential live role calls; one frozen design; no model fallback',
        'advisory_only':True,'role_runs':[],'status':'running'}
    exit_code=0
    try:
        configure(args)
        from backend import planning_workflow as w,ai
        from backend.store import LocalStore,Conflict
        store=LocalStore(str(args.db))
        raw=store.latest_compose_session(('planning_active',)) if args.session=='latest' else store.get_compose_session(args.session)
        if raw is None:raise ValueError('No staged-planning session was found in this database')
        raw=w.load(store,raw['id'],raw['version']);frozen=w.view(store,raw)
        if not frozen['analysis_current']:raise ValueError('Run deterministic checks for the current accepted design and inputs first')
        # Validate all roles and hash bindings before making any billable request.
        for role in roles:agents.role_context(frozen,role)
        key=snapshot_key(frozen);expected_version=raw['version'];deadline=time.monotonic()+args.max_seconds
        report.update(session_id=raw['id'],initial_version=expected_version,provider=ai.status(),
            snapshot={'design_hash':key[0],'inputs_hash':key[1],'analysis_result_hash':key[2],'analysis_id':key[3]})
        write_json(args.output/'report.json',report)
        for role in roles:
            started=time.monotonic();run={'role':role,'started_at':time.time(),'status':'running','stored':False}
            report['role_runs'].append(run)
            try:
                current=w.load(store,raw['id'],expected_version);current_view=w.view(store,current)
                if not current_view['analysis_current'] or snapshot_key(current_view)!=key:
                    raise Conflict('The accepted design or deterministic analysis changed; this frozen evaluation cannot continue')
                if time.monotonic()+75>deadline:raise RuntimeError('The shared evaluation budget cannot fit another bounded model call')
                review=agents.review_role(frozen,role,
                    'Review your discipline against this frozen accepted design. Quote only cited supplied or deterministic evidence; preserve all missing and unsupported screens.',
                    deadline=min(deadline,time.monotonic()+165))
                review['analysis_result_hash']=key[2]
                # Preserve the real validated reply even if concurrent edits later prevent CAS storage.
                write_json(args.output/(role+'.json'),review)
                run.update(response_file=role+'.json',provider=review['provider'],mode=review['mode'])
                artifact=store.save_design_artifact('agent_review',review)
                current.setdefault('agent_review_ids',{})[role]=artifact
                saved=w.save(store,current,expected_version);expected_version=saved['version']
                run.update(status='success',stored=True,artifact=artifact,session_version=expected_version)
                print(role+': live review validated and stored',flush=True)
            except Exception as exc:
                run.update(status='failed',error_type=type(exc).__name__,error=str(exc))
                exit_code=1
                print(role+': failed ('+type(exc).__name__+'): '+str(exc),file=sys.stderr,flush=True)
                if isinstance(exc,Conflict):break
            finally:
                run['seconds']=round(time.monotonic()-started,3)
                write_json(args.output/'report.json',report)
        report['status']='success' if not exit_code else 'failed'
        report['final_version']=expected_version
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__,error=str(exc));exit_code=1
        print('Evaluation failed ('+type(exc).__name__+'): '+str(exc),file=sys.stderr,flush=True)
    finally:
        report['completed_at']=time.time()
        write_json(args.output/'report.json',report)
    print('Report: '+str(args.output/'report.json'),flush=True)
    return exit_code


if __name__=='__main__':raise SystemExit(main())

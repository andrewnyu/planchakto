"""Live spatial-design experiment, isolated from project revisions.

Supply a brief and optional confirmed site JSON. Writes real provider responses,
validated plans and measured geometry to a gitignored report. Can record the
legacy composer's response to the same brief for comparison.
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--brief', type=Path, help='UTF-8 brief text file')
    ap.add_argument('--site', type=Path, help='Reviewed SitePlan JSON, in local metres')
    ap.add_argument('--read-site', type=Path, help='Read one PDF/image instead of generating concepts')
    ap.add_argument('--compare-legacy', action='store_true')
    ap.add_argument('--template', choices=['house','commercial','warehouse'], default='commercial')
    ap.add_argument('--vertex', default='planchakto')
    ap.add_argument('--model', default='gemini-3.8-flash')
    ap.add_argument('--gcloud-user', action='store_true')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    os.environ.update(BUILDGRAPH_AI_PROVIDER='vertex', GOOGLE_CLOUD_PROJECT=args.vertex, GEMINI_MODEL=args.model)
    if args.gcloud_user:
        import google.auth
        from google.oauth2.credentials import Credentials
        token = subprocess.run(['gcloud','auth','print-access-token'], capture_output=True, text=True, check=True).stdout.strip()
        creds = Credentials(token, quota_project_id=args.vertex)
        google.auth.default = lambda *a, **k: (creds, args.vertex)
    from backend import concepts, ai
    out = args.output or ROOT/'.data/evals'/f'concepts-{time.strftime("%Y%m%d-%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {'provider':ai.status(),'started_at':time.time()}
    if args.read_site:
        import base64, mimetypes
        attachment = ai.Attachment(name=args.read_site.name,mime_type=mimetypes.guess_type(args.read_site)[0] or 'application/pdf',data=base64.b64encode(args.read_site.read_bytes()).decode())
        report['reading'] = concepts.read_site(attachment).model_dump(mode='json')
    else:
        if not args.brief: ap.error('--brief is required when not reading a site')
        message = args.brief.read_text()
        site = concepts.SitePlan.model_validate_json(args.site.read_text()) if args.site else None
        report.update(brief=message,site=site.model_dump(mode='json') if site else None)
        if args.compare_legacy:
            from backend.compose import template_spec
            started = time.monotonic()
            legacy = ai.compose_turn(args.template,template_spec(args.template),[],message)
            report['legacy'] = {k:legacy[k] for k in ['reply','outcome','plan','tools']}
            report['legacy']['spec'] = legacy['spec'].model_dump(mode='json')
            report['legacy']['seconds'] = round(time.monotonic()-started,1)
            out.write_text(json.dumps(report,indent=2))
            print('Legacy:',legacy['outcome'],legacy['reply'],flush=True)
        started = time.monotonic()
        report['attempts']=[]
        try:
            reply, metrics = concepts.propose(message,site,trace=report['attempts'].append)
            report['spatial'] = {'reply':reply.model_dump(mode='json'),'metrics':metrics,'seconds':round(time.monotonic()-started,1)}
            print('Spatial:',len(reply.proposals),'validated proposals in',report['spatial']['seconds'],'seconds',flush=True)
        except Exception as exc:
            report['spatial'] = {'error':str(exc),'seconds':round(time.monotonic()-started,1)}
            out.write_text(json.dumps(report,indent=2))
            raise
    report['finished_at'] = time.time()
    out.write_text(json.dumps(report,indent=2))
    print('Report:',out)


if __name__=='__main__': main()

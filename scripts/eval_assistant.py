"""Live evaluation of the new-project design assistant against the configured AI provider.

    .venv/bin/python scripts/eval_assistant.py                  # every case, provider from .env
    .venv/bin/python scripts/eval_assistant.py --case clinic-brief --case basement
    .venv/bin/python scripts/eval_assistant.py --vertex planchakto --gcloud-user   # Vertex AI with your gcloud login

Writes a JSON report to .data/evals/ and exits 1 if any release invariant fails (invalid output, a corrupted or
unbuildable project, an edit on a clarification or unsupported turn, or an invented budget or site value).
Expectation misses are reported as the quality score; they do not fail the run.
"""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', action='append', help='run only these case ids')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--vertex', metavar='PROJECT', help='use Vertex AI in this GCP project')
    ap.add_argument('--model', help='override GEMINI_MODEL / OPENROUTER_MODEL')
    ap.add_argument('--gcloud-user', action='store_true', help='authenticate Vertex with `gcloud auth print-access-token` instead of ADC')
    args = ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    if args.vertex:
        os.environ.update({'BUILDGRAPH_AI_PROVIDER': 'vertex', 'GOOGLE_CLOUD_PROJECT': args.vertex})
        os.environ.setdefault('GEMINI_MODEL', 'gemini-3.8-flash')
    if args.model: os.environ['OPENROUTER_MODEL' if os.getenv('BUILDGRAPH_AI_PROVIDER') == 'openrouter' else 'GEMINI_MODEL'] = args.model
    if args.gcloud_user:
        import google.auth
        from google.oauth2.credentials import Credentials
        token = subprocess.run(['gcloud', 'auth', 'print-access-token'], capture_output=True, text=True, check=True).stdout.strip()
        creds = Credentials(token, quota_project_id=os.environ['GOOGLE_CLOUD_PROJECT'])
        google.auth.default = lambda *a, **k: (creds, os.environ['GOOGLE_CLOUD_PROJECT'])
    from backend.ai import status
    from backend.evals.cases import CASES
    from backend.evals.runner import run_case
    info = status()
    if not info['ai_provider']: raise SystemExit('No AI provider is configured; set one in .env or pass --vertex PROJECT.')
    cases = [c for c in CASES if not args.case or c.id in args.case]
    print(f'{len(cases)} case(s) on {info["ai_provider"]} / {info["ai_model"]}\n')
    with ThreadPoolExecutor(args.workers) as pool: results = list(pool.map(run_case, cases))
    for r in results:
        hits = sum(e['ok'] for e in r['expect'])
        print(f'{"PASS" if r["passed"] else "FAIL"}  {r["id"]:<26} {r["category"]:<12} {hits}/{len(r["expect"])} expectations  {r["seconds"]:>5.1f}s  '
              + ' → '.join(t['outcome'] for t in r['turns']))
        for p in r['problems']: print(f'      INVARIANT  {p}')
        for e in r['expect']:
            if not e['ok']: print(f'      missed     {e["label"]}')
    broken = [r for r in results if r['problems']]; expect = [e for r in results for e in r['expect']]
    print(f'\n{sum(r["passed"] for r in results)}/{len(results)} cases fully passed · {sum(e["ok"] for e in expect)}/{len(expect)} expectations met · '
          f'{len(broken)} invariant failure(s)')
    out = ROOT / '.data' / 'evals' / f'assistant-{time.strftime("%Y%m%d-%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'provider': info, 'results': results}, indent=2, ensure_ascii=False))
    print(f'Report: {out.relative_to(ROOT)}')
    sys.exit(1 if broken else 0)


if __name__ == '__main__':
    main()

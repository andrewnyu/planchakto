# Planchakto (BuildGraph)

An all-in-one **build plan and checker for Philippine building projects**. Every design edit flows through the same pipeline before anyone accepts it: geometry, structural and service calculations, checks, and a priced quantity takeoff.

> *Plan + tsakto* ("exactly right"). The app shows itself as **BuildGraph**.

Built for small PH architecture and engineering teams iterating on a modest single-storey building. It is a hackathon prototype: preliminary planning only, and **professional review is still required for construction**.

## What it does

- **Start a new project from a template.** Pick a house, a commercial building or a warehouse and describe it in plain language. Gemini turns the description into a typed project spec (name, location, use and room programme). It then asks only about what is still undecided, offering two to four suggested answers per question that you select, as in a guided interview. Picking a suggestion applies a validated value instantly; free text goes to the design agent (`backend/agent.py`). It runs a bounded tool loop: Gemini calls typed tools (update the brief, add, resize or remove rooms, run checks, look up a rule), and after every edit the loop re-plans the building and runs every check. The results (footprint, failures, estimated cost against the budget) go back to Gemini before it may answer, so the reply quotes real numbers and offers a fix. Each tool step and the reply stream live to the chat. Budget and site values are refused unless the user supplied them, and clarification or out-of-scope turns leave the project unchanged. The conversation is saved server-side, survives a refresh, and moves with the project into the project assistant after Build. A deterministic generator (`backend/compose.py`) builds the model from the spec:
  - it lays out two room strips around the corridor
  - it places columns in shared walls clear of every corridor door
  - it chooses the coarsest grid and the lightest beam, column and pad sizes that pass the checks
  - it adds fixtures, lighting, power and air conditioning
  - it places fire provisions and extinguishers until the Table 7 screen passes
  - it sets seismic inputs only from your answers

  Unanswered site values (fault distance, R, friction) stay `missing_input`. The result lands as a candidate revision, so the accepted design is kept until you apply it. Only single-storey footprints up to 30 × 30 m are supported, and the assistant says so when asked for more.

- **See the full process.** The Planning graph is the default workspace. It connects site and brief inputs to layout, coordinated disciplines, quantities, and review/export. Progress comes from the current revision's inputs and computed screens; it never presents model preparation as professional approval.
- **Quick check a drawing.** Upload one structural framing plan (PDF or image) and screen it on its own, in a separate workspace that never touches your projects or the demo. Gemini reads the sheet into a typed reading: grid lines with their positions on the page, columns, member sizes and loads. Deterministic code then maps that reading to inputs you confirm on top of the drawing. Values not on the sheet stay missing; anything defaulted is labelled "assumed". The engine runs scoped to structure: beams, footings and seismic. Every finding is pinned back onto the uploaded sheet, and checks that need other drawings are listed as not checked. A bundled sample sheet (`examples/quick-check/`) works with or without an AI provider. Fire, plumbing and electrical drawing readers are next. See [docs/QUICK_CHECK_PLAN.md](docs/QUICK_CHECK_PLAN.md).
- **Review one system.** Inside a project, go straight to plumbing, fire protection, electrical, structural or solar findings. The built-in plumbing and fire samples load as candidates on the demo project, giving a reliable finding → fix → cost-impact loop.
- **Edit the plan.** Move or swap rooms, move fixtures, furniture and equipment, change loads, remove columns, or edit the brief, grid and site. Edits work in a 2D scaled plan and a synchronized 3D model.
- **See the impact before accepting.** Each edit creates a *candidate* revision. The accepted revision is never overwritten. You compare the two, then apply or discard.
- **Run deterministic checks.** All of these are code, not AI:
  - **Structure:** Euler–Bernoulli beam finite elements for independent simply supported roof beams, checked for serviceability (deflection) and elastic stress, plus a centred-footing bearing screen. Results are verified against closed-form solutions.
  - **Seismic:** the NSCP 2015 §208 static force procedure gives the design base shear (zone, soil profile, near-source factors, R, I, period). A rigid roof diaphragm shares it between moment frames on every grid line: roof beams in X, grid girders in Y. A direct-stiffness 2D frame solver then checks storey drift (ΔM = 0.7RΔS), the redundancy factor ρ, steel columns (AISC 360-10 §E3 buckling and §H1-1 interaction, which NSCP Ch. 5 is based on) and frame members under the LRFD seismic combinations. Footings are checked for eccentric bearing, overturning and sliding under the ASD combinations. Coefficient tables were transcribed from secondary sources, so only values those sources agree on are built in. Any other value, and every site-specific one (Na, Nv, R, friction), stays `missing_input` until entered, and each check carries a verify flag. Wind, torsion, P-Δ and connections are reported as unsupported.
  - **Services:** orthogonal electrical and plumbing routes checked against the geometry, circuit totals, cold water, and gravity drain slopes.
  - **Layout:** a CP-SAT solver (OR-Tools) generates room arrangements around a fixed corridor, honouring locks, adjacency and door access, with transparent scores.
  - **Fit-out and PH code:** checks with explicit source references. Each check reports `pass`, `fail`, `missing_input` or `unsupported`, and missing inputs can never pass.
- **Price it.** The quantity takeoff is derived from geometry and priced with editable rates (₱). You get a cost delta between the accepted design and each candidate.
- **Solar PV (optional).** Packs modules on the roof inside an edge setback and adds their dead load (module + racking) to the roof beams under the array, so the existing deflection, stress and bearing checks re-run with PV included. It sizes the inverter output breaker (125% rule) and screens the busbar 120% rule, transformer loading and worst-case reverse flow, DU hosting capacity, and the net-metering cap. Regulatory values carry their source and a verify flag. Values only the distribution utility can supply (transformer kVA, hosting capacity) stay `missing_input` until entered. Wind uplift is reported as unsupported.
- **Fire protection (optional).** Screens a business, concentrated-use business (e.g. BPO) or mercantile occupancy against the 2019 RIRR of RA 9514 (Fire Code). It covers occupant load, number of exits with single-exit allowances, travel distance, dead-end corridors, common path, exit capacity, corridor width, and the sprinkler, alarm, emergency lighting, exit sign and portable extinguisher (Table 7) requirements. Each result cites its clause (e.g. `10.2.16.2 ¶6.2`). Travel is measured on a 0.25 m grid that only passes between rooms through modeled doors, and the plan draws the critical egress route, the exits and the extinguishers. The one value not located in the RIRR text (mercantile unsprinklered travel distance) stays `missing_input` until entered.
- **Site.** Import a survey CSV and a boundary, triangulate the terrain, and validate the site.
- **Sketch to layout (multimodal).** Attach a hand sketch, photo or existing floor plan (PNG, JPEG, WebP or PDF) in the assistant. Gemini maps its spaces onto the model's rooms and proposes `move_room`/`swap_rooms` edits. It lists anything it cannot map, such as a room the model doesn't have, instead of inventing it. Every edit gets a dry run through the domain layer and the layout checks, and if it breaks something, Gemini gets the specific problems back for one bounded correction pass.
- **AI assistant (optional).** Plain-language requests ("move the bathroom next to the kitchen", "raise the roof live load to 1.5 kPa") become **typed commands**. They go through exactly the same validation pipeline as manual edits and always land as a candidate for review. The assistant cannot change locks, site, grid, brief or rates.
- **Permit drawing set.** Export → *Permit drawing set* produces discipline sheets from the revision:
  - A-1 site development plan, general notes and sheet index
  - A-2 floor plan and room schedule
  - S-1 foundation and roof framing plans with beam and footing schedules
  - E-1 electrical layout, schedule of loads and PV single-line diagram
  - P-1 plumbing and sanitary layout with fixture schedule
  - FP-1 fire protection and egress plan

  Output is a vector **PDF** (20″ × 30″ or A3), each sheet with a PH permit title block: project, location, owner, sheet contents and number, a blank seal box, and the professional's PRC No. and validity, IAPOA/APO No., PTR No. (date and place) and TIN, per NBC IRR Figure III.2. The other format is a layered **DXF** in metres (AIA-style layers: `A-WALL`, `S-BEAM`, `E-PV`, `P-SANR`, `FP-EGRS`, …) for finishing in CAD. Every sheet is stamped *Preliminary — not for construction* until it is signed and sealed. Elevations, sections, details and the vicinity map are not generated.
- **Revisions.** Undo and redo, branchable revision history, and import/export of a project as JSON. Quantities export as CSV, and there is a printable HTML report.

The demo project, *San Isidro Studio*, is a synthetic 12 × 9 m building with a central accessible corridor, six rooms and a regular steel roof grid. All its dimensions, loads and rates are synthetic.

## Quick start

Requires Python 3.13 and Node 22.

```bash
cp .env.example .env   # then add an AI key (optional, see below)
./scripts/dev.sh
```

`dev.sh` creates `.venv`, installs dependencies on first run, builds the frontend, and serves everything at **http://127.0.0.1:8011** (override with `BUILDGRAPH_PORT`).

For frontend work with hot reload, run the API and Vite side by side. Vite proxies `/api` to port 8011:

```bash
.venv/bin/python -m uvicorn backend.main:app --port 8011 --reload --env-file .env
```

```bash
npm run dev --prefix frontend   # http://127.0.0.1:5173
```

To reset to the demo project, use the reset button in the app or `POST /api/reset`. Local state lives in `.data/buildgraph.sqlite3`.

The shortest demo starts on the landing page: on the **Check a plan** card choose **Plumbing on the demo** → **Preview clear routes**. The candidate should change from two plumbing findings to none and show the modeled quantity-cost change before it is applied. See [docs/HACKATHON_DEMO.md](docs/HACKATHON_DEMO.md) for the full three-minute script and honest scope language.

## AI providers

The assistant is server-side only; keys never reach the browser. Configure one or both providers in `.env`:

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Google Gemini via an AI Studio key, using native structured JSON output. Run `scripts/check_gemini.py` to verify the key and list models. |
| `GOOGLE_CLOUD_PROJECT`, `GEMINI_MODEL`, `GOOGLE_CLOUD_LOCATION` | Gemini on **Vertex AI** with Application Default Credentials. This is the deployed configuration. The location defaults to `global`, and `GEMINI_THINKING` defaults to `LOW`. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Any [OpenRouter](https://openrouter.ai/models) model, e.g. `anthropic/claude-sonnet-5.5`. |
| `BUILDGRAPH_AI_PROVIDER` | `gemini`, `vertex` or `openrouter` forces one. If unset, the order is Gemini key, then Vertex AI, then OpenRouter. |

Every provider returns the same `AIPlan`, and every reply is validated identically. Gemini runs in plain JSON mode, with a compact schema of only the commands the assistant may issue in its system prompt. Vertex constrained decoding (`response_json_schema`) was not usable for this: it rejected the full command union, and once the union was accepted it corrupted numbers (a 3.0 m width came back as `3e-128`). Model-supplied numbers are rounded to millimetres before the edit is applied. The validation rejects stale revisions, edits with no commands, read-only answers that carry commands, and restricted operations, so a malformed reply never reaches the store. OpenRouter gets the JSON Schema in the prompt rather than through `response_format`. That's because upstream constrained decoding rejects the large command union, so the Pydantic validation is the real gate.

With no provider configured, the assistant says so explicitly. Every manual tool and calculation still works. There are no recorded or simulated AI responses.

`GET /api/health` reports the active `ai_provider` and `ai_model`.

## Tests and benchmarks

```bash
.venv/bin/python -m pytest -q backend/tests
```

```bash
npm run build --prefix frontend   # tsc type-check + Vite build
```

```bash
npm test --prefix frontend        # workflow status and discipline filtering
```

```bash
.venv/bin/python scripts/benchmark.py   # writes docs/BENCHMARKS.json
```

```bash
.venv/bin/python scripts/eval_assistant.py --vertex planchakto --gcloud-user --model gemini-3.8-flash   # live assistant evals
```

```bash
.venv/bin/python scripts/eval_quick_check.py --vertex planchakto --gcloud-user   # live drawing-reading evals
```

`backend/evals/cases.py` holds 32 scripted conversations: houses, offices and warehouses, multi-turn corrections, ambiguous, unsupported and conflicting requests, questions and budget feedback. The runner fails if any case breaks a release invariant: invalid output, an unbuildable or corrupted project, an edit on a clarification or unsupported turn, or an invented budget or site value. Missed expectations are reported as the quality score. Reports go to `.data/evals/`. The Quick check eval reads three sheets with known answers: the bundled sample, the demo's own S-1 permit sheet (round trip through `drawings.py`), and an architectural sheet that must be flagged as not a framing plan. On 2026-10-17, gemini-3.8-flash passed 3/3 in about 10 s per sheet. On 2026-10-17, gemini-3.8-flash passed 32/32 cases and 59/59 expectations, with a median single-turn time of 7.9 s.

The tests cover edit propagation, the engineering calculations against closed-form results, revision immutability, idempotency, undo/redo, import/export, AI plan validation and provider selection. AI calls are mocked, and no live requests are made. `scripts/fixtures.py` regenerates the files in `examples/`.

## Docker and deployment

**Live demo:** https://buildgraph-428497355584.asia-southeast1.run.app (Cloud Run, `asia-southeast1`, project `planchakto`)

The deployed service uses:
- **Gemini on Vertex AI**, authenticated by the runtime service account, so there is no API key. Text and drawings both use `gemini-3.8-flash` with low thinking. Set `GEMINI_VISION_MODEL` to route drawings to another model, such as `gemini-3.1-pro-preview`; if that model returns 429/503/504, the request falls back to the text model. Each call is bounded at 75 s, inside Cloud Run's 180 s request timeout.
- **Firestore** for the revision index and **Cloud Storage** for snapshots (`BUILDGRAPH_STORAGE=google`).
- Public access, scaling 0–2 instances. Visitors share one resettable demo workspace.

Redeploy from a clean checkout:

```bash
./scripts/deploy.sh
```

The script builds the image on Cloud Build, then deploys to Cloud Run and checks `/api/health`. Source upload honours `.gitignore`, so `.env` and local data are never uploaded. Override `PROJECT`, `REGION`, `GEMINI_MODEL` or `BUCKET` with environment variables. `cloudbuild.yaml` runs the same build and deploy as a Cloud Build pipeline.

One-time project setup:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com storage.googleapis.com aiplatform.googleapis.com --project=planchakto
```

```bash
gcloud firestore databases create --project=planchakto --location=asia-southeast1 --type=firestore-native
```

```bash
gcloud storage buckets create gs://planchakto-artifacts --project=planchakto --location=asia-southeast1 --uniform-bucket-level-access --public-access-prevention
```

```bash
gcloud artifacts repositories create buildgraph --project=planchakto --location=asia-southeast1 --repository-format=docker
```

```bash
gcloud iam service-accounts create buildgraph-runtime --project=planchakto
```

Then grant the runtime account `roles/datastore.user` and `roles/aiplatform.user` on the project, and `roles/storage.objectAdmin` on the bucket.

To run the container locally:

```bash
docker build -t buildgraph .
```

```bash
docker run --rm -p 8080:8080 --env-file .env buildgraph
```

## Project layout

```
backend/
  main.py         FastAPI routes; also serves frontend/dist
  domain.py       typed SI model, commands, immutable revisions
  engine.py       recomputes everything for a revision
  geometry.py     layout checks, survey parsing, site validation
  structure.py    beam FEM + bearing screen, section catalogue
  routing.py      electrical / plumbing routing and slopes
  layout.py       CP-SAT room layout alternatives
  quantities.py   takeoff, pricing, revision comparison
  solar.py        PV array fit, roof load, service & grid screens
  fire.py         RA 9514 egress grid and fire-protection screen
  drawings.py     permit sheet set → PDF (reportlab) and DXF (ezdxf)
  rules.py        rule catalogue with sources
  ai.py           Gemini / OpenRouter interpreter + plan validation
  agent.py        design agent: bounded tool loop, check feedback, streamed events
  quickcheck.py   Quick check: rasterize, Gemini sheet reading, mapping, scoped run
  evals/          assistant evaluation cases and runner
  store.py        SQLite revision store (cloud_store.py for GCP)
frontend/src/
  App.tsx         workspace, tabs, inspector, assistant
  Workflow.tsx    interactive planning-process graph
  planning.ts     derived progress and discipline check filters
  DisciplineReview.tsx focused review, plan context and quick fixes
  QuickCheck.tsx  single-drawing check: upload, confirm on the sheet, findings overlay
  Plan.tsx        2D SVG plan
  Model3D.tsx     Three.js model (lazy-loaded)
  Solar.tsx       solar PV results and inputs (Engineering tab)
  Fire.tsx        fire protection results and inputs (Engineering tab)
  PermitExport.tsx permit drawing export (Export dialog)
examples/         demo project, survey, boundary, coordinated variant
scripts/          dev server, benchmark, fixtures, Gemini check
docs/             implementation plan, benchmark results
```

## Scope and limits

**Supported:** one regular orthogonal single-storey building family; independent simply supported roof beams; a centred bearing screen; geometric service routing.

**Explicitly out of scope:** standpipes, fire-resistance ratings and compartmentation, interior finish, and BFP plan evaluation (FSEC); whole-frame stability, connections, column buckling, lateral/seismic/wind design, hydraulic and vent sizing, electrical protection and sizing, and PH code certification. Unsupported checks are shown as `unsupported`, never as passing.

Production authentication is not implemented; this is a local single-user prototype.

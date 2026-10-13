# Planchakto (BuildGraph)

An all-in-one **build plan and checker for Philippine building projects**. Every design edit flows through the same pipeline before anyone accepts it: geometry, structural and service calculations, checks, and a priced quantity takeoff.

> *Plan + tsakto* ("exactly right"). The app shows itself as **BuildGraph**.

Built for small PH architecture and engineering teams iterating on a modest single-storey building. It is a hackathon prototype: preliminary planning only, and **professional review is still required for construction**.

## What it does

- **Edit the plan.** Move or swap rooms, move fixtures, furniture and equipment, change loads, remove columns, or edit the brief, grid and site. Edits work in a 2D scaled plan and a synchronized 3D model.
- **See the impact before accepting.** Each edit creates a *candidate* revision. The accepted revision is never overwritten. You compare the two, then apply or discard.
- **Run deterministic checks.** All of these are code, not AI:
  - **Structure:** Euler–Bernoulli beam finite elements for independent simply supported roof beams, checked for serviceability (deflection) and elastic stress, plus a centred-footing bearing screen. Results are verified against closed-form solutions.
  - **Services:** orthogonal electrical and plumbing routes checked against the geometry, circuit totals, cold water, and gravity drain slopes.
  - **Layout:** a CP-SAT solver (OR-Tools) generates room arrangements around a fixed corridor, honouring locks, adjacency and door access, with transparent scores.
  - **Fit-out and PH code:** checks with explicit source references. Each check reports `pass`, `fail`, `missing_input` or `unsupported`, and missing inputs can never pass.
- **Price it.** The quantity takeoff is derived from geometry and priced with editable rates (₱). You get a cost delta between the accepted design and each candidate.
- **Solar PV (optional).** Packs modules on the roof inside an edge setback and adds their dead load (module + racking) to the roof beams under the array, so the existing deflection, stress and bearing checks re-run with PV included. It sizes the inverter output breaker (125% rule) and screens the busbar 120% rule, transformer loading and worst-case reverse flow, DU hosting capacity, and the net-metering cap. Regulatory values carry their source and a verify flag. Values only the distribution utility can supply (transformer kVA, hosting capacity) stay `missing_input` until entered. Wind uplift is reported as unsupported.
- **Fire protection (optional).** Screens a business, concentrated-use business (e.g. BPO) or mercantile occupancy against the 2019 RIRR of RA 9514 (Fire Code). It covers occupant load, number of exits with single-exit allowances, travel distance, dead-end corridors, common path, exit capacity, corridor width, and the sprinkler, alarm, emergency lighting, exit sign and portable extinguisher (Table 7) requirements. Each result cites its clause (e.g. `10.2.16.2 ¶6.2`). Travel is measured on a 0.25 m grid that only passes between rooms through modeled doors, and the plan draws the critical egress route, the exits and the extinguishers. The one value not located in the RIRR text (mercantile unsprinklered travel distance) stays `missing_input` until entered.
- **Site.** Import a survey CSV and a boundary, triangulate the terrain, and validate the site.
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

## AI providers

The assistant is server-side only; keys never reach the browser. Configure one or both providers in `.env`:

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Google Gemini, using native structured JSON output. Run `scripts/check_gemini.py` to verify the key and list models. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Any [OpenRouter](https://openrouter.ai/models) model, e.g. `anthropic/claude-sonnet-5.5`. |
| `BUILDGRAPH_AI_PROVIDER` | `gemini` or `openrouter` forces one. If unset, the first configured provider is used, and Gemini is preferred. |

Both providers return the same `AIPlan` and are validated identically. The validation rejects stale revisions, edits with no commands, read-only answers that carry commands, and restricted operations, so a malformed reply never reaches the store. OpenRouter gets the JSON Schema in the prompt rather than through `response_format`. That's because upstream constrained decoding rejects the large command union, so the Pydantic validation is the real gate.

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
.venv/bin/python scripts/benchmark.py   # writes docs/BENCHMARKS.json
```

The tests cover edit propagation, the engineering calculations against closed-form results, revision immutability, idempotency, undo/redo, import/export, AI plan validation and provider selection. AI calls are mocked, and no live requests are made. `scripts/fixtures.py` regenerates the files in `examples/`.

## Docker and deployment

```bash
docker build -t buildgraph .
```

```bash
docker run --rm -p 8080:8080 --env-file .env buildgraph
```

`cloudbuild.yaml` builds, pushes and deploys to Cloud Run (`asia-southeast1`) with Firestore and Cloud Storage persistence (`BUILDGRAPH_STORAGE=google`). Before using it, you need to:

- set `_BUCKET` to a private bucket
- create the `buildgraph-runtime` service account
- know that it deploys with `--no-allow-unauthenticated`, so a public demo needs that flag changed or a proxy in front

AI keys should go in Secret Manager, not `--set-env-vars`.

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
  store.py        SQLite revision store (cloud_store.py for GCP)
frontend/src/
  App.tsx         workspace, tabs, inspector, assistant
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

# AGENTS.md

Shared context for every coding agent on this repo: Codex, Claude Code, and anything else. Read this first, then the doc for the area you are touching. Keep it current: if you change scope, an invariant, a workflow or ownership, update this file in the same change.

## What this is

**Planchakto** ("plan + tsakto", exactly right) is a building planning tool and checker for small Philippine architecture and engineering teams. In code and in the UI it is called **BuildGraph**. It is our entry for the **Google Cloud AI Builder Cup 2026**: a hackathon prototype for preliminary planning, not a certification tool.

Hackathon constraints that shape technical choices:
- **Gemini must be the AI in the submission.** OpenRouter exists for local development only; nothing in the deployed path may depend on it. Judging gives 40% to technical merit and meaningful Gen AI use, so visible, grounded Gemini use matters.
- The app is deployed on **Cloud Run** (project `planchakto`, region `asia-southeast1`) and must stay publicly reachable.
- The repo becomes public. Never commit secrets, `.env`, `.data/` or `artifacts/`. `artifacts/` holds the deck, video and submission form; it is gitignored and owned by the user.

## Context sources and precedence

- This root `AGENTS.md` is the canonical cross-agent context. `CLAUDE.md` is a thin adapter that imports it; do not duplicate these instructions there.
- The non-negotiables below are product promises and take precedence over an implementation that accidentally violates them.
- A nearer nested `AGENTS.md` may add subtree-specific rules but may not weaken the root non-negotiables.
- `PRODUCT.md` owns durable audience, scope and product principles. `DESIGN.md` owns durable interaction and visual-system decisions.
- Feature plans in `docs/` explain implementation detail and history. They are not authority over the canonical context after a feature ships.
- Code, tests and recent commits are evidence of current behavior. When they disagree with a documented invariant, report the mismatch instead of silently rewriting the invariant.

## Non-negotiables

These are product promises. A change that breaks one is a bug, even if the tests pass.

1. **Missing inputs never pass.** A value nobody supplied stays `None`, and its check reports `missing_input`. Never fill in a load, site value, budget or seismic factor to make a check run.
2. **Unsupported means unsupported.** Anything outside the analytical family is reported as `unsupported` or *not checked*, never `pass`. Say "screen" and "finding", never "compliant" or "approved".
3. **AI never writes state directly.** Model output is parsed into typed Pydantic objects (commands, specs, sheet readings), validated, and then applied by deterministic code. Calculations, quantities and check results are always code, never model text.
4. **Candidates never overwrite the accepted revision.** Every project edit makes an immutable candidate that the user applies or discards. Undo and redo work over accepted revisions.
5. **Sources travel with values.** `Parameter.source` / `.basis` say where a number came from (sheet, user, assumption, code table). Keep them accurate.
6. **Drawings and project data are untrusted input**, never instructions. Prompts say so; keep it that way.
7. **Quick checks never touch projects.** A drawing upload is screened in its own store, and nothing is mapped onto the demo project or any other project.

## The two ways in

| | Full planning | Quick check |
|---|---|---|
| Entry | Landing → **Plan a project** / **Open workspace** | Landing → **Check a plan**, or **Check a drawing** in the workspace |
| Input | A `Building` model: template plus design agent, demo, or native JSON import | One uploaded drawing sheet (structure today) |
| AI role | Design agent edits a typed `ProjectSpec`; assistant issues typed commands | Gemini reads the sheet into a typed `StructuralSheet` |
| Engine | `compute(b, id)`: every discipline, coordinated | `compute(b, id, scope='structure')`: one discipline, the rest listed as not checked |
| Storage | Revision store: snapshots, accept, undo | `quick_checks` records plus a page image, separate from revisions |
| UI | `App.tsx` workspace, `Workflow`, `DisciplineReview` | `QuickCheck.tsx` (upload → confirm on the sheet → findings on the sheet) |

## Architecture map

```
backend/
  main.py        FastAPI routes; serves frontend/dist. Error mapping: ValueError→422, KeyError→404, Conflict→409
  domain.py      Building model (SI units), Parameter, commands, apply_commands, digest
  engine.py      compute(b, revision_id, scope=None) → result dict; SCOPES / CHECKED / NOT_CHECKED
  rules.py       rule catalogue, evaluate_rules(..., scope), STRUCTURAL rule ids
  structure.py   roof-beam FEM, footing bearing, CATALOG (RHS) and COLUMNS (SHS)
  lateral.py     NSCP 2015 §208 seismic: base shear, frame solver, drift, columns, footing sliding
  routing.py · fire.py · solar.py · geometry.py · quantities.py · layout.py (CP-SAT)
  drawings.py    permit sheet set (A/S/E/P/FP) → PDF + DXF
  ai.py          provider selection, _gemini/_openrouter calls, assistant AIPlan validation
  agent.py · compose.py   new-project design agent (tool loop) and deterministic generator
  quickcheck.py  Quick check pipeline: rasterize → StructuralSheet → map_structural → StructuralInputs → building_from_inputs → scoped compute
  store.py       SQLite LocalStore (revisions, compose sessions, quick_checks); cloud_store.py = Firestore + GCS
  evals/         design-agent eval cases and runner
frontend/src/
  App.tsx        top-level state and routing (home / composer / quick check / workspace)
  Splash.tsx     landing page with the two ways in
  QuickCheck.tsx + quickcheck.css   Quick check screen and SheetView overlay
  Workflow.tsx · DisciplineReview.tsx · Plan.tsx · Model3D.tsx · NewProject.tsx · AgentPanel.tsx
examples/        demo fixtures; examples/quick-check/ = sample framing plan PNG + recorded reading (ground truth)
scripts/         dev.sh, deploy.sh, eval_assistant.py, eval_quick_check.py, make_quick_check_sample.py, fixtures.py, benchmark.py
docs/            QUICK_CHECK_PLAN.md (design + as-built), HACKATHON_DEMO.md (demo script), IMPLEMENTATION_PLAN.md
```

## Engine contract

- `compute(b, id)` with no scope is the full project analysis. Its output must not change unless you mean it to: the unscoped `result_hash` for `example()` is the regression signal.
- `compute(b, id, scope)` runs only that discipline's analyzers. Skipped sections get stub results of the same shape, so the frontend types hold. Checks are filtered by `rules.in_scope`. The result gains `scope` and `coverage: {checked, not_checked}`.
- **To add a scope**, for example `fire`:
  1. Add its analyzers to the `SCOPES` branch in `engine.py`.
  2. Add its rule ids to an `in_scope` set in `rules.py`.
  3. Write its `CHECKED` and `NOT_CHECKED` lists.
  4. Add tests showing that out-of-scope rules never appear and that coordination checks are listed as not checked.

## Quick check

- **Flow:** upload → `rasterize` (PDF pages through pypdfium2; at most 2000 px; always PNG) → `extract_structural` (Gemini, plain JSON mode, schema in the system prompt, one repair retry) → `map_structural` (deterministic; produces `StructuralInputs`, a page transform and notes) → the user confirms → `run` → `building_from_inputs` (a blank `Building` with no rooms, services or rates) → `compute(scope='structure')`.
- **Coordinates:** Gemini returns page positions on a 0–1000 scale (`point` is [y, x], `box` is [ymin, xmin, ymax, xmax]). The transform is per-axis `page = s·metres + o`, fitted from the grid lines. The overlay draws in the image's pixel space.
- **Notes levels:** `read`, `assumed`, `missing`, `conflict`, `unsupported`. Height, loads and soil have no defaults. Section, footing size and seismic zone default with an *assumed* label.
- **Samples:** the sample sheet is read live when a provider is connected and asked for; otherwise the recorded reading is used, and the UI says "No AI call was made". Regenerate both with `scripts/make_quick_check_sample.py`.
- **Next (phase 6):**
  - floor-plan readers for fire, plumbing and electrical (each a new sheet schema plus scope);
  - multi-sheet checks that share a grid, which turn coordination checks on;
  - promote to project (blocked: a blank model has no rooms or survey);
  - a retention TTL.
- Full design and as-built notes: [docs/QUICK_CHECK_PLAN.md](docs/QUICK_CHECK_PLAN.md).

## AI usage rules (learned the hard way)

- **No constrained decoding on Vertex** (`response_json_schema`). It rejected the command union and corrupted numbers (3.0 → 3e-128). Use plain JSON mode with the schema in the system prompt, then validate with Pydantic.
- Round model-supplied numbers before exact geometry checks (`ai.tidy`).
- Calls are bounded: 75 s per call inside Cloud Run's 180 s request timeout. Retry only 429/503/504. Low thinking keeps text calls around 5–10 s.
- With no provider configured, say so explicitly (HTTP 503 with `mode: 'unavailable'`). Never fake a model response. The one exception is a recorded sample reading, and it must be labelled as recorded.
- Deployed config: Vertex AI, `gemini-3.8-flash` for text and drawings (`GEMINI_VISION_MODEL` is optional). Locally, `.env` may point at OpenRouter, and the local `GEMINI_API_KEY` has been invalid. For Gemini locally, use `--vertex planchakto --gcloud-user` on the eval scripts.

## Working on the repo

```bash
./scripts/dev.sh                                   # builds frontend, serves app + API on :8011
```

```bash
.venv/bin/python -m pytest -q backend/tests        # must pass before any commit
```

```bash
npm run build --prefix frontend                    # tsc type-check + Vite build
```

```bash
npm test --prefix frontend
```

```bash
.venv/bin/python scripts/eval_quick_check.py --vertex planchakto --gcloud-user   # live drawing-reading eval (3 sheets)
```

```bash
.venv/bin/python scripts/eval_assistant.py --vertex planchakto --gcloud-user     # live design-agent eval (32 cases)
```

- `dev.sh` runs uvicorn without `--reload`, so restart it after backend changes. Frontend changes need `npm run build` (or use Vite on :5173 for hot reload).
- Deploy with `./scripts/deploy.sh` (Cloud Build, then Cloud Run). It needs the user's local gcloud login, so cloud agents cannot deploy. Deploy only when the user asks.
- New Python dependencies go in both `backend/requirements.in` and the pinned `backend/requirements.lock.txt` (the Dockerfile installs the lock file).
- AI calls in tests are always mocked or injected. Live calls happen only in `scripts/eval_*.py`.

## Conventions

- **Match the surrounding style.** The backend and `App.tsx` are deliberately dense: one-liners and `;`-joined statements. Newer components (`DisciplineReview.tsx`, `QuickCheck.tsx`) are formatted normally. Comments explain *why* (a constraint or a lesson), not *what*.
- Units are SI everywhere in the model: metres, kPa, kN, MPa. Convert at the edge.
- User-facing copy is plain and honest about scope, with no compliance claims. Every structural screen ends with the reminder that licensed professional review is required.
- **Commits and PRs carry no AI attribution** (no `Co-Authored-By: Claude`, no "Generated with" lines), by the user's standing instruction. Commit or push only when the user asks.

## Ownership and coordination

- Historically Codex built the core backend and engine, and Claude took the frontend and review. Since 2026-10-17 either agent may work across the stack when the user asks.
- One writer per file set at a time. Register active work in the table below before editing shared or cross-cutting files. Remove or close the row when the work is committed, abandoned or handed off.
- Leave the demo fixture (`example()`) and its results unchanged unless the task is about the demo. The hackathon video and the deck depend on its numbers.

### Active work

| Owner | Scope | Files | State |
|---|---|---|---|
| Codex | Shared agent context | `AGENTS.md`, `CLAUDE.md`, `DESIGN.md` | Context update complete locally; uncommitted |

## Status (2026-10-17)

- On `origin/main` through `e82b194`:
  - full planning workspace (planning graph, discipline reviews, candidates, undo);
  - design agent with live evals (32/32);
  - structure, seismic, routing, fire, solar and quantities;
  - permit PDF/DXF export;
  - Cloud Run deploy.
- Committed on local `main` at `5434133`, not yet on `origin/main`:
  - **Quick Check for structural framing plans**. Its committed docs report a 3/3 live evaluation on `gemini-3.8-flash`; this context pass did not rerun it.
- Next after the local commit is pushed: Quick Check phase 6 (see above), then deck and video updates for the Quick Check moment ([docs/HACKATHON_DEMO.md](docs/HACKATHON_DEMO.md) has the script).

# Quick check workspace — implementation plan

Status: **phases 1–5 built 2026-10-17** (structure); **phase 6 fire, plumbing and electrical built 2026-10-17**. Plumbing and electrical are intentionally limited one-sheet screens. Multi-sheet checks and project promotion remain open.

### As built (differences from the plan below)
- `backend/quickcheck.py` holds the whole pipeline: rasterize, `StructuralSheet` reading, `map_structural`, `building_from_inputs`, `create`/`create_sample`/`run`. Endpoints: `POST /api/quick-checks`, `POST /api/quick-checks/sample`, `GET /api/quick-checks/{id}`, `GET …/{id}/image`, `POST …/{id}/run` (body: the full `StructuralInputs`).
- Cloud storage keeps the record JSON and the page PNG in GCS (`<workspace>/quick-checks/`), not in a Firestore collection. Records can exceed Firestore's document limit once results are attached.
- The page transform is axis-aligned scale + offset per axis (`page = s·m + o`, in 0–1000 page units), fitted from the grid lines. Rotated sheets are not supported.
- Storey height, loads and soil bearing have no defaults: they stay missing until read or entered. Run is blocked until height is given; missing loads become `missing_input` checks. Section, footing size and seismic zone fall back to defaults that are labelled *assumed*.
- `StructuralInputs.assumed` / `.entered` record where each value came from. `Parameter.source` carries that into the results ("Read from the uploaded drawing", "Entered in quick check", "Assumed — not on the drawing; confirm").
- The model view is the Quick check's own SVG (grid, beams, footings), not `<Plan readOnly>`, because the blank model has no rooms, survey or routes.
- **Promote to project is deferred**: a blank framing model has no rooms or survey, so the project pipeline's terrain and layout checks cannot run on it.
- `ReviewUpload.tsx` and the "map this drawing onto the current model" path are removed. Every "check a drawing" entry point opens Quick check. The older fire candidate sample remains available separately on the demo project.
- Sample sheet and ground truth come from `scripts/make_quick_check_sample.py`; the live eval is `scripts/eval_quick_check.py`.

### As built — phase 6, fire (2026-10-17)
- **Reading (`FireSheet`):** sheet kind, units, storeys; the footprint's overall width and depth from the dimension strings plus the box of its outer wall faces; rooms as named boxes; interior doors as the two printed room names plus a point; exterior exits by the page side of their wall (top/bottom/left/right), with printed clear width, mark and box; extinguishers with a point and verbatim rating; `occupancy_text` only when printed; provisions (sprinklers, manual/automatic alarm, emergency lighting, exit signs) only where a legend, symbol or note shows them. Prompt `FIRE_SYSTEM` follows `EXTRACT_SYSTEM`: untrusted image, report only what is printed, 0–1000 page coordinates, flag what does not fit.
- **Mapping (`map_fire`, deterministic):** the transform comes from the footprint box and overall dimensions (exact per axis, so no residual). Rooms are scaled from their boxes and their edges snapped within 0.35 m, closing the wall-thickness gaps so neighbours share walls. Each door goes on the shared wall of the two named rooms nearest its point; one on no shared wall is a *conflict* and left out. Room kinds come from names (corridor, toilet, pantry…); only `corridor` matters to the engine (dead ends, corridor width).
- **Never assumed:** occupancy (a printed classification is mapped by keyword, an unsupported one such as residential is flagged *unsupported*, and room names are never used) and contents hazard. `building_from_fire` refuses to run without them. Provisions not shown are *assumed* not provided, so they can fail but never pass on a guess. Unprinted exit widths are scaled from the drawing (*assumed*).
- **Engine:** `compute(b, id, 'fire', doors=…)` runs `analyze_fire` only. `fire.Grid` accepts drawn door segments on walls of either orientation (matched to the 0.25 m grid within one step) and `exit_segments(b, drawn=True)` drops the planning model's implied west entrance, so a drawing without exits fails `FIRE-EXITS` instead of passing on an invented door. Unreachable floor is reported in `travel.unreachable` and fails `FIRE-TRAVEL`; the common path is measured over reachable floor (previously an unreachable cell made it infinite, which the planning model never hit). The unscoped `example()` result hash is unchanged.
- **Rules:** `rules.FIRE` lists the FIRE-* ids and `in_scope` admits them under the fire scope. Structural `PH-CODE` gaps are not emitted under fire; `FIRE-SCOPE` lists the fire items not evaluated.
- **UI:** `QuickFire.tsx`. The discipline picker enables Fire protection (also from the landing card and from the fire review's **Check a drawing**). The confirm panel puts occupancy and hazard first as required choices, then provisions, outline, editable rooms, doors (add by picking two rooms), exits and extinguishers. The overlay draws rooms, doors, exits and extinguishers on the sheet; results add the worst travel path to an exit, the farthest point from an extinguisher, and rooms with no way out in red.
- **Sample and eval:** `examples/quick-check/fire-sample.png` is a 20 × 12 m office with a full-width corridor, eight rooms, seven doors, three exits and one 2-A extinguisher, and no printed occupancy. With business / low hazard it fails `FIRE-EXT` (one extinguisher for 240 m², 20.4 m away at worst) and `FIRE-ALARM` (not shown). Live eval cases: `fire-sample` (geometry within 0.35 m, doors by room pair, exits, extinguisher, occupancy left unread), `demo-FP1` (the fire demo's FP-1 sheet: printed occupancy and provisions read; no overall dimension strings, so the footprint is read right or left missing) and `fire-on-S` (the framing plan read as a floor plan must be flagged). gemini-3.8-flash passed 3/3 at about 10 s per sheet.

### As built — phase 6, plumbing and electrical (2026-10-17)
- **Typed reading:** `ServiceSheet` is tied to the requested discipline. It reads the footprint, named room boxes and page-positioned service points. Plumbing points are fixtures plus water and sanitary connections; electrical points are equipment/load points plus the panel. Printed drain fall/slope and circuit values are copied only when shown.
- **Deterministic mapping:** `map_service` scales rooms and points from the footprint transform, resolves every item to a named/containing room, and leaves conflicts out. `ServiceInputs` is confirmed before `building_from_service` creates a blank one-discipline model.
- **Plumbing scope:** fixture-to-water and fixture-to-drain plan routes plus gravity fall using user-confirmed available fall and minimum slope. Pipe sizes, pressure/flow, hydraulic adequacy, vents, traps, cleanouts, risers, quantities and structural clashes are listed as not checked.
- **Electrical scope:** equipment-to-panel plan routes plus connected load and single-phase current arithmetic from confirmed watts, voltage, power factor and demand factor. Missing watts remain `missing_input`. Conductors, breakers, voltage drop, fault current, grounding, code coverage, risers, quantities and structural clashes are listed as not checked.
- **Samples:** `plumbing-sample` and `electrical-sample` are synthetic 20 × 12 m plans with recorded readings. The electrical sample deliberately omits one load rating to demonstrate that missing input does not pass.

### Answers to the open questions
- **Bounding-box accuracy:** on the sample and on the demo's CAD-style S-1 sheet, gemini-3.8-flash placed grid lines within about 1/1000 of the page (fit residual < 0.5 units) and read every value exactly. Dense real-world sheets are still unproven. The overlay degrades to the model view when no transform can be fitted.
- **Retention:** no TTL yet. Records persist until the store is reset.
- **Seismic inputs:** asked as optional fields in the confirm step. Left blank, the seismic checks report `missing_input`.

## Why

Today a Quick check upload goes into the demo project:

- A native JSON import calls `store().import_model()`, which makes a candidate whose parent is the demo's head (`backend/store.py:98`). The uploaded plan then shows up in the San Isidro revision history and its diff.
- A PDF or image goes to the assistant with the prompt "Map only rooms that match the current model" (`frontend/src/App.tsx:72`). The drawing is read against the demo building, not on its own terms.

Users cannot tell which findings belong to their drawing and which belong to the demo.

## Is a single-discipline review technically sound?

Yes. The disciplines are separate inside `compute()` (`backend/engine.py`). Each analyzer reads only part of `Building`:

| Discipline | Minimum inputs | Depends on |
|---|---|---|
| Structure (gravity) | width, depth, height, `grid_x`/`grid_y`, active columns, roof section, dead/live load, soil, footing size | — (PV load if solar is in scope) |
| Seismic | the above + `engineering.lateral` | structure output |
| Fire | footprint, rooms, exits, extinguishers, occupancy | — |
| Plumbing | rooms, fixtures, water/drain points | columns as obstacles (clash check) |
| Electrical | rooms, equipment, circuits, panel | columns as obstacles |

A structural framing plan by itself is enough for the gravity, seismic and footing screens. It needs no rooms or fixtures. The one real limit is **coordination**. A check that needs another discipline's data, such as a pipe clashing with a column, cannot run on one sheet. It must be reported as **not checked** (`missing_input` / `not_applicable` with a reason), never as a pass.

## Target experience

1. Landing → **Quick check** → choose Structure → upload a framing plan (PDF/PNG/JPEG).
2. Gemini reads the sheet. The user sees **the uploaded drawing with what was read overlaid on it**: grid lines, columns and section callouts, each with a confidence level. A side table lists the extracted values and the missing ones (e.g. "Dead load not on sheet").
3. The user corrects or fills values, then presses **Run check**. This step is the honesty gate: nothing is computed from unconfirmed geometry.
4. The results screen shows findings **pinned on the drawing** (failing beam highlighted along its span, overloaded footing circled), alongside a reconstructed model view. Every finding opens the same evidence and calculation inputs as `DisciplineReview`.
5. A coverage panel lists what was *not* checked and why (other disciplines, wind, connections and so on).
6. Optional: **Start a project from this check** promotes the model into a real project. This is the only path into the project store.

The demo project is never touched.

---

## Phase 1 — Engine scoping (backend)

**`backend/engine.py`**
- `compute(b, revision_id, scope: set[str] | None = None)`. `None` keeps today's behaviour exactly, so all existing tests and the demo stay unchanged.
- `SCOPES = {'structure': {'structure','lateral'}, 'fire': {'fire'}, 'plumbing': {'routing:water','routing:drain'}, 'electrical': {'routing:conduit','electrical:load'}}`. Solar remains a full-project screen, not a single-drawing Quick check.
- Skip analyzers outside the scope and return `{'skipped': True, 'reason': 'Outside this check'}` for them. Quantities run only on in-scope items.
- Add `result['coverage'] = {'checked': [...], 'not_checked': [{'item', 'reason'}]}`.

**`backend/rules.py`**
- Pass `scope` into `evaluate_rules`. Emit only in-scope rules and only the in-scope `PH-CODE` gaps. Under a structure scope, plumbing clashes and the like become one `not_applicable` line each: "Requires plumbing drawing".

**`backend/domain.py`**
- Add a `blank_building(width, depth, height, grid_x, grid_y)` factory with empty rooms, fixtures, equipment, circuits, furniture and rates, a boundary equal to the footprint, and fire/solar disabled. Check that `layout_checks`, `fitout_checks`, `takeoff` and `terrain` accept empty lists (add tests). Most are skipped by scope anyway.
- The `Building` validator already enforces a grid from 0 to the extent, which is what we want.

**Tests**
- `compute(example(), id)` is byte-identical before and after (result hash).
- `compute(blank_with_columns, id, {'structure'})` produces beam/footing/seismic checks and no LAYOUT, ROUTE or FITOUT checks, with coverage listing them.

## Phase 2 — Separate Quick check store (backend)

Use a new table/collection, not the project revision store. A quick check needs no accept, undo/redo or branching.

- `LocalStore`: `CREATE TABLE quick_checks(id TEXT PRIMARY KEY, updated_at REAL, data TEXT)`. `GoogleStore`: a `quick_checks` collection. Store page images in GCS, not inline.
- Record shape:
  ```
  {id, discipline, status: 'extracting'|'confirm'|'checked',
   source: {name, mime_type, page, image_url, width_px, height_px},
   extraction: {...raw Gemini output...},
   transform: {model_to_image affine 2x3, residual_px},
   model: Building, results: compute(..., scope), created_at, updated_at}
  ```
- Endpoints in `backend/main.py`:
  - `POST /api/quick-checks` `{discipline, attachment, page?}` → rasterize, extract, map → record in `confirm` state
  - `GET  /api/quick-checks/{id}`
  - `PATCH /api/quick-checks/{id}` `{model_patch}` → re-validate, recompute, status `checked`
  - `GET  /api/quick-checks/{id}/image` → the rasterized page
  - `POST /api/quick-checks/{id}/promote` → `store().import_model(model, label=f'From quick check {name}')` (later phase)
- PDF rasterization: add `pypdfium2` to `requirements.in`. Render the selected page at ~150 dpi to PNG. All bounding boxes refer to that PNG. For multi-page PDFs, return a page count and let the user pick a page (v1 defaults to page 1).

## Phase 3 — Structural extraction with Gemini (backend)

New module `backend/extract.py`, separate from the assistant's `AIPlan` path in `ai.py`, reusing `_gemini` with its own system prompt and schema.

**Schema `StructuralSheet`:**
```
units: 'm'|'mm'|'ft'
overall: {width, depth, height?}           # with source text
grid_x / grid_y: [{label, position, bbox}] # "A","B"... / "1","2"... ; position in sheet units
columns: [{grid_ref: "B-2" | null, x?, y?, bbox, mark?}]
sections: [{applies_to: 'roof_beam'|'girder'|'column', callout: "RHS 200x100x6", bbox}]
loads: [{kind: 'dead'|'live'|'soil', value, unit, source_text, bbox}]
notes: [{text, bbox}]
outside_supported: [{reason, bbox?}]      # multi-storey, cantilever, RC frame, sloped grid…
confidence per item: 'read'|'inferred'
```
Bounding boxes use Gemini's native `[ymin, xmin, ymax, xmax]` normalized 0–1000 against the rasterized page.

**Prompt rules:** read only what is printed. Never invent loads or sections; leave them null. Flag anything outside the supported family (`outside_supported`) instead of forcing it to fit.

**Deterministic mapping (`map_structural(sheet) -> (Building, transform, issues)`), in Python, not the LLM:**
- Convert units. Build `grid_x`/`grid_y` from positions, offset to start at 0, and check that the last line equals the overall extent (otherwise raise an issue).
- Place columns at their grid refs. Column lines with a missing end support are already reported by `analyze_structure` as unsupported cantilevers.
- Section callouts → nearest catalog entry (`RHS150/200/250`, `SHS150/200/250`). An exact match counts as read. Anything else is flagged "Section X not in catalog — assumed RHS200, confirm".
- Loads that are not on the sheet become `Parameter(value=None)`, so they surface as `missing_input`. Never fall back silently to the demo's 0.65/0.75 kPa.
- Transform: least-squares affine from (grid position in m) → (grid bbox centre in px), using both axes. Store the residual. If the residual is large, flag "Drawing may not be to scale".

**Offline / demo fallback:** ship `examples/quick-check/structure-sample.png` plus a recorded `structure-sample.extraction.json`. The sample path then works without a provider, and the evals have a fixed input.

## Phase 4 — Frontend Quick check screen (Claude)

New `frontend/src/QuickCheck.tsx`, rendered as its own top-level view (not a project tab):

- **Upload step:** discipline picker (Structure enabled; others show "coming next"), file drop, page picker for PDFs, sample button.
- **Confirm step:** a `<DrawingOverlay>` component with the page image plus an SVG layer in image pixel space. It draws grid lines, column markers and callout boxes from the extraction bboxes, coloured by confidence. A side form shows extents, grid spacings, sections and loads, with missing items highlighted. Edits go through PATCH, and Run check sends the final PATCH.
- **Results step:** the same overlay, with findings projected through `transform` (beam → line between its two column points, footing → circle at its column, global checks → banner). The list reuses the `DisciplineReview` finding card (pull `evidence()` out into a shared component). A toggle switches to the model view using `<Plan readOnly>` with the structure layer. A coverage panel shows `results.coverage.not_checked`.
- **Wiring:** `Splash` → `onCheck` opens QuickCheck, not `uploadReview` in the demo. Inside a project, `DisciplineReview` keeps reviewing the project model. Its "Upload another plan" button opens QuickCheck in a new view instead of importing into the project. Remove `drawingForReview`'s "match the current model" path.

## Phase 5 — Evals and proof

- **Round-trip eval:** render the demo's S sheet with `drawings.render_pdf` → rasterize → extract → map, then compare grid, columns and section to `example()`. This gives a known ground truth for free. Add it to `backend/evals` and `scripts/eval_assistant.py`.
- A perturbed variant (one column removed, a wrong section noted) must produce the expected failing checks on the overlay.
- A negative case: a two-storey or RC framing plan must come back as `outside_supported`, not a fabricated check.

## Phase 6 — Next disciplines

Same pipeline, a new schema per discipline:
- **Fire (built):** floor plan → rooms, interior doors, exit doors (wall and offset), extinguishers, occupancy (asked, not inferred). See *As built — phase 6* above.
- **Plumbing / electrical (built, intentionally limited):** fixtures/equipment and utility points. Clashes with structure are reported as "not checked" unless a future framing sheet is added.
- **Multi-sheet check:** let a quick check hold several sheets sharing one grid. Coordination checks then switch on, which is the natural bridge to a full project.

## Ownership and order

| # | Work | Owner |
|---|---|---|
| 1 | Engine scope + coverage + tests | Codex |
| 2 | quick_checks store + endpoints + rasterize | Codex |
| 3 | Structural extraction + mapping + sample fixture | Codex |
| 4 | QuickCheck screen, DrawingOverlay, Splash rewiring | Claude |
| 5 | Round-trip and negative evals | Codex, checked by Claude |
| 6 | Fire, plumbing and electrical built 2026-10-17; multi-sheet coordination next | Claude (fire), Codex (services) |

Phases 1–2 can start in parallel. Phase 4 can begin against the recorded sample fixture before Phase 3 lands.

## Open questions

- **Bounding-box accuracy:** check how precise Gemini's boxes are on dense CAD-exported PDFs before committing to the overlay. Fallback: overlay the grid only and place columns from the transform.
- **Retention:** should quick checks expire (e.g. 7 days) or persist per browser? Unauthenticated uploads on Cloud Run suggest a TTL.
- **Seismic inputs** (R, Na, Nv) are almost never on a framing plan. Should the confirm step ask for them, or report seismic as `missing_input` by default?

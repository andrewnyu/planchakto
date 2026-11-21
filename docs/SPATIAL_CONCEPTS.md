# Spatial concept planning

This documents the retained concept-only workspace. The primary **Start planning** flow is now [the complete staged workflow](PLANNING_WORKFLOW.md).

The coordinated generator is intentionally constrained to a 30 × 30 m orthogonal building with a full-width corridor. That contract is unchanged. A separate concept stage gives Gemini control of the actual footprint, polygon zones, adjacencies, openings and circulation without manufacturing engineering results for unsupported layouts.

## User workflow

Choose **Plan a project → Open earlier concept drafts** for this concept-only workspace. The initial brief is carried into its conversation. **Start planning** and **Open staged planning** enter the complete staged workflow instead. Add a site PDF/image or reviewed site JSON, inspect its outline/source/coordinates, then choose **Use this site** before designing with it. Reading alone writes no site or project state.

Ask for alternatives or edit the selected proposal. The model normally returns two schemes; a clarification or explanation may return none. Select a numbered space or its inspector button to see its measured area and purpose. Applying a proposal accepts a concept snapshot only. New proposals do not overwrite it. Undo/redo move across accepted snapshots; candidates may be discarded unless they belong to the accepted timeline. Export saves the full typed candidate, context, sources and checking scope as JSON. There is no automatic promotion into the coordinated workspace.

## Model and geometry contract

`ProgramReply → LayoutProgram → DesignPlan → Zone / Opening` are strict Pydantic objects. Gemini chooses a footprint and arbitrary ordered spatial cuts, labels each resulting region, and specifies the room connection graph and opening widths. `concept_program.py` derives exact partition polygons and shared-wall segments. There is no imposed corridor or cut sequence. Direct polygon proposals remain readable for compatibility. Coordinates are finite SI metres in a consistent local frame. Plans are one floor, at most 500 m across, up to 48 zones. Polygons may be non-rectangular. Interior zones partition the footprint. Outdoor zones remain outside it and, when supplied, inside the site. Optional clipping is explicit in the authored program and records its area-changing effect as an assumption; it is never disguised as a supplied site dimension.

Code checks simple positive polygons, containment, overlaps, allocation (0.05 m² numerical tolerance), valid opening relationships and reachability from at least one proposed exterior entrance. Areas come from Shapely. A preferred opening may be projected onto its intended straight shared wall while retaining its proposed width. This never moves rooms or invents an adjacency. Exact openings are not moved. Adjustments are recorded in measured results. These are geometric operations, not door-swing, clearance or accessibility checks.

The model gets measured horizontal site sections to help place its proposals in irregular lots. Rejected layouts return actual validation errors, including outside vertices. One repair call is allowed within the request budget. Provider failures and invalid outputs do not persist a partial proposal.

Concept design defaults to the bounded `LOW` thinking level (`GEMINI_CONCEPT_THINKING` overrides it). An experimental `MEDIUM` call timed out; the compact spatial program removes repetitive polygon arithmetic rather than relying on a longer inference. This call-specific setting does not change the existing assistant or quick-check defaults. Generation remains in plain JSON mode with schema validation; no Vertex constrained decoding is introduced.

Geometry results use `status: geometry_checked`. Structural, seismic, fire, traffic, services, terrain, daylight and cost work is explicitly not checked. Missing site, north, setbacks, budget, rates and engineering inputs remain missing; cost is `null`. A required setback is evaluated only when supplied, and has no implicit default.

## Site reading

An upload is rasterized with the existing quick-check rasterizer, then read into a typed `SiteSheet`. Drawings and their text are untrusted input. Printed scale and area are kept separately from inferred coordinates.

For native PDFs, code can recover a unique simple straight-edged polygon whose area agrees within 1% with the independently read printed area at the printed scale. It does **not** rescale a polygon merely to match an area. Curved paths, ambiguous matches, nested transforms and absent scale/area metadata do not use this fallback. A page-space road hint can map to a nearby actual boundary edge. The origin, scale, area agreement and drawing-derived basis travel with the reading. This is not a georeferenced or cadastral survey.

Without a unique vector recovery, a vision boundary whose area differs from a printed area by more than 5% is refused. The UI shows the missing information and keeps the site unchanged. JSON imports are validated by the server before the preview renders them.

## Persistence and APIs

Concept sessions reuse the session-store adapter with status `concept_active`, so coordinated session lookup does not return them. Candidates contain immutable plan and site snapshots, a content hash, code-derived measurements and creation metadata. A separate timeline/cursor represents accepted concepts. Acceptance checks the expected accepted ID and revalidates the stored geometry. Long-running generation refuses to save over a changed conversation. Session size stays below 800 KB for Firestore's document ceiling, and the UI asks for a new conversation when it fills.

- `POST /api/concepts/sessions`, `GET /api/concepts/sessions/latest`, `GET /api/concepts/sessions/{id}`
- `POST /api/concepts/read-site` (read-only), `POST /api/concepts/validate-site` (read-only), `POST /api/concepts/sessions/{id}/site` (explicit confirmation)
- `POST /api/concepts/sessions/{id}/propose`, with optional `base_candidate_id`
- `POST /api/concepts/sessions/{id}/accept|discard`, with `candidate_id` and `expected_accepted_id`
- `POST /api/concepts/sessions/{id}/undo|redo`

No concept endpoint imports or accepts an engineering revision. Quick-check records remain isolated as before.

## Validation

`backend/tests/test_concepts.py` exercises irregular/large layouts, invalid geometry, disconnected rooms, opening placement, native PDF scale/area recovery, unavailable AI, explicit site confirmation, candidate isolation, stale-context rejection and concept undo/redo. Tests inject or mock every AI call.

Live calls belong in `scripts/eval_concepts.py`. It accepts a UTF-8 brief file and optional reviewed `SitePlan` JSON, records real raw provider replies and validation feedback, and can record the legacy composer's response to the same brief. Reports default to `.data/evals/`. Source drawings, client-specific proposals and comparison artifacts stay in gitignored storage.

```bash
.venv/bin/python scripts/eval_concepts.py --brief .data/brief.txt --site .data/site.json --compare-legacy --gcloud-user
.venv/bin/python scripts/eval_concepts.py --read-site /absolute/path/lot.pdf --gcloud-user
```

The live Tacloban experiment exposed vision scale errors, an outside parking zone, a stale door after a zone move and an intermittent authentication failure. Those are recorded separately from successful geometry results. A valid polygon layout is not a validated retail operation; vehicle access, actual racks, customer capacity and professional engineering remain later design work.

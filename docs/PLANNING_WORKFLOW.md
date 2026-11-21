# Staged planning workflow

The primary new-project path is **Start planning**. It uses real polygon concepts and detailed objects all the way through a preliminary review package. It does not convert a large or irregular concept into the older 30 × 30 m coordinated Building model. The coordinated template workspace and drawing Quick checks remain separate entry paths.

## Stage gates

| Stage | Candidate | Confirmation / effect |
|---|---|---|
| Programme | Typed operating spaces, target/minimum/maximum/exact areas, included-area hierarchy, capacities and sources | User confirms programme. No coordinates or engineering defaults are invented. One floor is supported. |
| Site and access | Confirmed site reading plus alternative typed gates, route waypoints and operating strategies | User confirms the site reading separately, then chooses a strategy. A site-free study explicitly omits gates and site routes. |
| Spatial layout | Model-selected footprint, cuts, spaces, programme bindings and access intents | Code compiles exact polygons and real shared-wall openings, checks containment/allocation/connectivity and hard area requirements. User chooses a candidate. |
| Detailed layout | Model-selected array dimensions/origins, support rooms, fixtures and circulation routes | Code places actual objects; skipped placements remain warnings and counts are calculated from placed objects. User confirms a detail candidate. |
| Accept design | Exact frozen programme/site/strategy/layout/details hash, programme findings and unresolved items | Explicit acknowledgement required. Missing functions or confirmed capacities block acceptance. Target-area deviations and unknown engineering are recorded, never silently removed. This is planning acceptance, not professional approval. |
| Engineering inputs | Typed values, source and basis; explicit component-model selection, criteria, circuits, vehicles, connections and rates | User validates and confirms an input candidate. Unknowns remain null. A proposal-source engineering value is not treated as confirmed. Incomplete input sets may be screened so missing inputs are visible. |
| Screens | Deterministic analysis tied to design and input hashes | Runs only after design acceptance and input confirmation. No LLM text supplies findings or calculations. |
| Review package | PDF, layered metre-unit DXF, takeoff CSV, native JSON and ZIP | Export requires current hash-bound analysis. Missing/unsupported coverage and exclusions travel with the artifacts. No permit certification is claimed. |

Every upstream confirmation invalidates downstream references and current analysis. Earlier immutable artifacts remain available through undo/redo. CAS session versions reject stale tabs and late model responses. Alternatives remain selectable when their upstream dependencies match. Discard never deletes a confirmed stage. Undo/redo restore confirmed snapshots; screens must be rerun afterward.

## Spatial tools instead of a fixed arrangement

`concept_program.py` allows arbitrary simple footprints, explicitly requested lot clipping and any sequence of x/y region cuts followed by explicit merges of adjacent regions. `fit_area_m2` solves the actual area inside a supplied site (when present), and `low_area_m2` solves a requested cut area; neither operation invents a statutory setback. Optional `clip_clearance_m` is a clearly labelled proposed edge allowance. Intermediate regions may be disconnected; final spaces must be connected simple polygons. Zero-area line remnants from cuts along a notch are removed without changing areas. A cut child may retain its parent identifier; it cannot replace another live region.

The model chooses actual spatial design decisions. Door endpoints are computed from real shared walls. Explicit `allow_public_path` may derive intermediate doors through unenclosed circulation/living/retail zones. `auto_access` is a stronger intent tool: for each room the model supplies acceptable neighbouring space kinds, opening width and kind; code selects an actual adjacent space already connected to an exterior entrance. Private spaces are not silently used as shortcuts. Both derivations are recorded in assumptions. There is no required corridor, strip, rectangular building or furniture layout.

Array recipes include proposed item dimensions, clear access side, row/column spacing, rotation and optional origin. Packing refuses boundary, room, door-approach, reserved-route, object and object-access clashes. Accessible parking has its own object kind; accessible counts are included in total parking. Bay and cashier numbering are derived from actual placement. Only explicit `cashier` objects count as checkouts; ordinary kitchen/service `counter` objects do not. `packing=fill` searches a bounded fine grid, preserving proposed spacing/access envelopes and explicit target counts. Vehicle routes use explicit customer_vehicle/service_vehicle kinds; pedestrian/interior/egress are walking routes. Support-room groups place rooms, drawn doors and fixtures; unplaced rooms or fixtures stay visible.

`auto_route=true` explicitly asks code to derive a width-aware visibility path inside the inset boundary, avoiding the building for outdoor vehicle routes. Original waypoints are retained as `requested_points`; resolved coordinates and derivation basis travel with the route. A waypoint may be projected inward by at most route width plus 1 m. This is geometric path planning, not swept-path analysis, gate approach design or turning certification.

## Analytical coverage

- Programme: actual polygon areas, bound operating spaces and placed parking/cashier counts. Hard area modes and capacities block design acceptance; soft targets remain explicit warnings. Included-area relationships avoid adding support-room allowances twice.
- Circulation: route envelopes against placed objects/building/site; nominal object access/array spacing against supplied criteria; crossing warnings. No vehicle kinematics or statutory accessibility claims.
- Fire: bounded eight-direction grid exit reachability around drawn objects/walls through drawn doors, supplied-limit route-distance comparison, supplied occupant-factor/exit-width arithmetic and drawn door-width comparison. Grid resolution is reported and narrow paths may be missed. Loading openings do not count as pedestrian exits. Mixed-occupancy strategy, exit independence/discharge, hardware, suppression, smoke and statutory determination remain unsupported.
- Structure: only an explicitly selected representative simply-supported steel roof bay using supplied span, tributary width, loads, elastic modulus, yield strength, factors, deflection criterion, RHS section and explicit self-weight inclusion/addition mode; elastic FEM bending/deflection comparison. Independent gross square-footing bearing uses a separately supplied load, width and soil bearing. Global frame/load paths, member stability, connections, seismic/wind, reinforced-concrete design and settlement are unsupported. This never establishes whole-building structural suitability.
- Electrical: per-circuit connected/demand watts and current from supplied voltage, power/demand factors and phases. Indicative zone-to-panel lines only where panel points exist. No cable sizing, protection, supply capacity or constructible routing.
- Plumbing: direct drawn-fixture-to-supplied-drain connections and longest direct-line fall arithmetic when slope/fall are supplied. No hydraulic sizing, water demand, invert/fitting coordination or buildable routing.
- Quantities: footprint, supplied-thickness slab volume, unique enclosed-wall allowance at supplied height, placed-object counts and route lengths. Every line carries formula/object references. Missing dimensions or rates remain missing/unpriced; partial subtotal is separate from a nullable complete modelled-scope total. Excluded structural/civil/MEP/labour/tax/fee scope is printed.

Criteria are supplied with provenance; the staged engine does not silently invent Philippine statutory values. A passing finding covers only its named arithmetic or geometry screen. Each report requires licensed professional review.

## Persistence and APIs

`planning_models.py` owns strict Pydantic contracts; `planning_workflow.py` owns gates, dependencies and immutable checkpoints. `planning_details.py` compiles fit-out and geometric takeoff; `planning_routes.py` derives explicitly requested paths; `planning_checks.py` computes findings; `planning_outputs.py` builds exports; `planning_api.py` exposes `/api/planning`.

Session metadata reuses the compose-session index with `status=planning_active`, CAS `version` and small content-addressed references. Artifact bodies are immutable `design-<sha256>` records in SQLite's `design_artifacts` table locally and GCS `workspace/planning/` in cloud storage. Firestore holds only session metadata, not thousands of detailed objects. GCS uses generation-zero writes. Failed or stale requests may leave unreferenced immutable artifacts, but never change confirmed state. This prototype does not yet garbage-collect orphan artifacts.

Routes: create/latest/get sessions; propose; accept/discard; site confirmation; approval-review/approve; input confirmation through propose/accept; checks; travel; versioned export. Input/proposal mutations require `expected_version`. Spatial design has at most three validated attempts and starts no new full call after 80 seconds elapsed; other AI requests have one validation repair. All provider calls remain bounded; errors leave confirmed state intact. Live calls remain in eval scripts; automated tests inject/mock AI.

Native `planning-1` and `planning-draft-1` imports restore a new draft. Programme, site and typed geometry are validated; each design stage is revalidated and confirmed in sequence. Prior approval, calculations and outputs are never restored as current. Browser form edits have a local recovery draft, while validated candidates are durably saved on the server.

## Validation

Run backend tests, frontend tests and the TypeScript/Vite build. `scripts/eval_planning.py` runs a real Gemini programme → strategy → layout → details → test-actor acceptance → blank-input screens → review export, in a private database. `--stop-after`, `--resume`, `--programme`, `--reference` and `--site` support focused runs. Reports label automated acceptance explicitly; it is never user acceptance. Private architect plans and live benchmark outputs stay in `.data/`, never public fixtures. Preserve the demo's existing unscoped result hash.

## Specialist coordination

The architectural agent owns programme, spatial design and fit-out proposals. A coordinator enforces stage gates and immutable state. After design acceptance and current deterministic analysis, architecture, structural, fire/accessibility, electrical, plumbing, site/traffic and quantities specialists review the same snapshot. Advice cites role-filtered finding IDs or exact RFC6901 input paths. Numeric prose can quote its own cited evidence; it cannot infer missing values, introduce arithmetic or convert/round supplied values into new calculated claims. Role, hashes and evidence are validated, with one repair. Advice remains separate from findings and never makes edits or certifications. Explicit batches are bounded to at most three parallel calls; single-role UI reviews are on demand.

Current advice additionally binds to the deterministic result hash. Upstream/input changes and reruns using changed results hide stale advice. Review packages include only current advice. There is no fake offline specialist response: deterministic roster status says when no AI review was made. Live evaluation: `scripts/eval_specialists.py --db PRIVATE.sqlite3 --roles structure,fire_accessibility --gcloud-user --output .data/evals/specialists-live`.

## Interaction and recovery

Saved projects have a selector and a direct `?planning=<session>&stage=<stage>` link; the server still enforces each gate. Browser-only edits can be recovered separately from saved candidates. Engineering vehicle dimensions and connection coordinates start blank; clearing coordinates retains missing values, while explicitly entered zero is preserved. Incomplete required rows cannot validate as measurements. Finding evidence links focus the actual deterministic finding; geometry links can reveal the drawing. Empty filters state that there are no matches and do not hide the global coverage summary.

# BuildGraph hackathon demo

## The story

BuildGraph turns one building model into a visible planning process. A user can start with an existing plan, focus on one discipline, preview a fix, and see the downstream quantity and cost change before accepting anything.

The progress indicator means “prepared in this model.” It does not mean code-approved, permit-ready, or professionally reviewed.

## New project path (recommended for the video)

1. On the landing page choose **Start a new project**, then **Commercial building**.
2. Describe it, for example: *A dental clinic in Cebu City called Ngiti Dental, with 3 treatment rooms, a waiting area for 12, a sterilisation room, an office, two toilets and a pantry.* Gemini rewrites the room programme and asks only about undecided fields; the plan preview on the right updates with every answer.
3. Answer the suggested questions (budget, eave height, occupancy, rear exit, fire provisions, solar, fault distance, soil, frame, footing friction). Point out that the fault distance is asked, never assumed, and that unanswered values stay missing inputs.
4. Type a change, e.g. *make the waiting area 30 m² and add a second office*, then choose **Build project**. The new building arrives as a candidate on the planning graph with structure, seismic, services, fire, solar and cost already screened.

## Three-minute path

0. Start on the landing page. Point out the two ways in: **Plan a project** (the full planning graph) and **Check a plan** (a deliberately limited one-system screen for an existing drawing).
1. Under **Check a plan**, choose **Plumbing sample**, then **Try the sample plumbing plan**. Without a provider, the recorded reading opens and says that no AI call was made.
2. On **Confirm what was read**, show the fixture markers, water and sanitary connection points, available drain fall and minimum slope. Values remain editable before anything is calculated.
3. Choose **Run limited plumbing check**. The water and drain paths appear on the sheet, with plan connectivity and gravity fall as the only checked items.
4. Scroll to **Not checked**: pipe sizing, pressure and flow, vents/traps/cleanouts, structural clashes, other disciplines, quantities and cost. Emphasize that one sheet cannot establish those items, so BuildGraph does not pass them.
5. Choose **Check another sheet** → **Electrical** → **Try the sample electrical plan**. Run it and show that one circuit remains `missing_input` because the pantry load has no printed wattage; the other circuit shows connected-load/current arithmetic.
6. Finish on the landing page or open the full planning workspace to contrast a narrow drawing screen with a coordinated project model.

## Optional second moment: fire protection

Landing-page route: choose **Home** in the left rail, then **Fire on the demo** on the **Check a plan** card. This imports a single-storey office with no fire provisions as a candidate and opens the fire review with four findings. Finish by choosing **Planning graph** to show that a quick check continues into the full plan.

Full-plan route:

1. Return to **Planning** and open **Fire protection**.
2. Explain that the current residential brief is not silently treated as a supported occupancy. Choose a supported business or mercantile occupancy explicitly, then start the screen.
3. Show the findings-first view, the passing screens, and the separate unassessed count. Open **Edit occupancy, exits & provisions**, add one provision such as exit signs, and preview the recalculation.

The fire screen is limited to the implemented single-storey business and mercantile family. It does not claim residential fire-code review, FSEC approval, or full building compliance.

## Gemini moment: Quick check a framing plan

This is the clearest visible use of Gemini, and it takes about 40 seconds.

1. On the landing page choose **Structure** on the **Check a plan** card, then **Try the sample framing plan**. With Gemini connected, the sample sheet is read live in about 10 s; without a provider, a recorded reading is used and the page says so.
2. **Confirm what was read.** The grid, columns and the read notes are drawn over the uploaded sheet. Point out the chips: values *from the sheet*, *assumed* (seismic zone) and *missing* (R, Na, Nv: never on a framing plan, so the seismic checks stay missing input rather than guessed).
3. **Run structural check.** The interior row of roof beams (RB-4 to RB-6) turns red at about 150% utilization: it carries twice the tributary width of the edge rows on the same RHS 150 section. Select a beam or footing on the drawing to open its finding and calculation inputs.
4. **Edit inputs and re-run** with RHS 200 × 100 × 6: every beam passes at about 64%. Point out **Not checked**: plumbing clashes, fire and layout need other drawings, so they are listed, never passed.

Say "screen" and "finding"; the page itself states that a licensed engineer must review the design.

Optional follow-on (about 30 seconds): **Check another sheet** → **Fire protection** → **Try the sample floor plan**. The rooms, doors and exits are drawn over the sheet. Point out that the run is blocked until you choose the occupancy, because it is not printed. Choose **Business** and **Low**, run, and show the 20.4 m path from the far corner to the only extinguisher and the alarm finding marked as assumed (not shown on the sheet). Removing the Conference door and re-running turns that room red: travel only passes doors read from the drawing.

## Upload behavior

| Input | What happens | Review boundary |
|---|---|---|
| Structural framing plan (PDF, PNG, JPEG, WebP) | **Quick check**, in its own workspace. Gemini reads grid, columns, sections and loads with page positions, the user confirms them on the sheet, and the structure-scoped engine runs | Values not on the sheet stay missing or are labelled assumed. Other disciplines are listed as not checked. Projects and the demo are never changed |
| Single-storey floor plan (fire) | **Quick check → Fire protection**. Gemini reads the outline, rooms, doors, exits and extinguishers; the user chooses the occupancy and hazard, and the fire-scoped engine runs with the worst travel path drawn on the sheet | Occupancy is never inferred. Provisions not shown are screened as not provided. Projects and the demo are never changed |
| Plumbing plan | **Quick check → Plumbing.** Gemini reads named rooms, fixtures, water/drain points and printed fall/slope; the user confirms them before routing | Plan connectivity and gravity fall only. Sizing, hydraulics, vents/traps/cleanouts, risers and structural coordination are not checked |
| Electrical plan | **Quick check → Electrical.** Gemini reads named rooms, loads, circuit marks, circuit values and the panel; the user confirms them before routing/load arithmetic | No conductor, breaker, voltage-drop, fault-current, grounding, riser or structural-coordination design |
| Native BuildGraph JSON | Import from the Site inspector's **Import** dialog: schema validation, recomputation, candidate revision | The model's supplied inputs are reviewed within the implemented analytical scope |
| Fire sample | Imports a bundled office (business occupancy, no provisions) as a candidate on the demo | A reliable local demo with no AI or network dependency |

## Presentation choices

- Open on the landing page, then go straight to the graph. The two cards answer “what can I do here?”, and the graph answers “where am I?” before the audience sees the detailed editor.
- Use one scope-honesty loop. The plumbing and electrical samples make the checked/not-checked boundary visible on the drawing and in the findings panel.
- Keep advanced editing behind the graph cards and focused review actions. The audience sees the outcome before the implementation detail.
- Say “screen,” “finding,” and “prepared.” Avoid “compliant,” “approved,” and “complete.”
- End on the candidate bar and cost comparison. This makes the engineering principle concrete: changes are calculated and reviewed before acceptance.

## Local verification

```bash
./scripts/dev.sh
```

Open `http://127.0.0.1:8011`. All four Quick check samples and their deterministic calculations work without an AI provider. Reading your own drawings requires a configured provider and should be demonstrated only with a non-sensitive drawing the presenter is authorized to send to that provider.

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

0. Start on the landing page. Point out the two ways in: **Plan a project** (the full planning graph, which this demo follows) and **Check a plan** (a one-system check for existing drawings). Choose **Open the planning graph**.
1. Open the **Planning** graph. Point out that every card is an entry point and that the status comes from the active revision: available inputs, calculated screens, findings, missing inputs, or an optional/not-screened state.
2. Choose **Check a drawing**, then the **plumbing sample** link under the upload card (or **Plumbing on the demo** on the landing page). This creates a candidate on the demo project and preserves its accepted design.
3. Show the two real route findings on the focused review screen. The plan highlights the plumbing and structure layers; each finding can locate its source element.
4. Choose **Preview clear routes**. The routing engine recomputes water, drainage, and conduit paths. The plumbing count changes from two findings to zero.
5. Show **Change since uploaded plan** and **Compare quantities**. In the bundled sample, the clear routes add approximately ₱600 in modeled material cost because the paths are longer. Rates are synthetic demonstration inputs.
6. Choose **Apply revision** only if you want to show the acceptance step. Until then, the saved design remains unchanged. Undo and revision history remain available after acceptance.

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

## Upload behavior

| Input | What happens | Review boundary |
|---|---|---|
| Structural framing plan (PDF, PNG, JPEG, WebP) | **Quick check**, in its own workspace. Gemini reads grid, columns, sections and loads with page positions, the user confirms them on the sheet, and the structure-scoped engine runs | Values not on the sheet stay missing or are labelled assumed. Other disciplines are listed as not checked. Projects and the demo are never changed |
| Fire, plumbing or electrical drawing | Not read yet; the Quick check page says so and offers the samples on the demo project | Floor-plan readers are the next Quick check disciplines |
| Native BuildGraph JSON | Import from the Site inspector's **Import** dialog: schema validation, recomputation, candidate revision | The model's supplied inputs are reviewed within the implemented analytical scope |
| Plumbing sample | Imports a bundled model with direct routes as a candidate on the demo | A reliable local demo with no AI or network dependency |
| Fire sample | Imports a bundled office (business occupancy, no provisions) as a candidate on the demo | A reliable local demo with no AI or network dependency |

## Presentation choices

- Open on the landing page, then go straight to the graph. The two cards answer “what can I do here?”, and the graph answers “where am I?” before the audience sees the detailed editor.
- Use one finding-to-fix loop. The plumbing sample is the clearest because the effect is visible on the plan and in quantities.
- Keep advanced editing behind the graph cards and focused review actions. The audience sees the outcome before the implementation detail.
- Say “screen,” “finding,” and “prepared.” Avoid “compliant,” “approved,” and “complete.”
- End on the candidate bar and cost comparison. This makes the engineering principle concrete: changes are calculated and reviewed before acceptance.

## Local verification

```bash
./scripts/dev.sh
```

Open `http://127.0.0.1:8011`. The plumbing sample, deterministic calculations, revision comparison, quantities, and exports work without an AI provider. Reading your own drawings requires a configured provider and should be demonstrated only with a non-sensitive drawing the presenter is authorized to send to that provider.

# BuildGraph hackathon demo

## The story

BuildGraph turns one building model into a visible planning process. A user can start with an existing plan, focus on one discipline, preview a fix, and see the downstream quantity and cost change before accepting anything.

The progress indicator means “prepared in this model.” It does not mean code-approved, permit-ready, or professionally reviewed.

## Three-minute path

0. Start on the landing page. Point out the two ways in: **Plan a project** (the full planning graph, which this demo follows) and **Check a plan** (a one-system check for existing drawings). Choose **Open the planning graph**.
1. Open the **Planning** graph. Point out that every card is an entry point and that the status comes from the active revision: available inputs, calculated screens, findings, missing inputs, or an optional/not-screened state.
2. Choose **Review an existing plan**, leave **Plumbing** selected, then choose **Try a plumbing sample**. This creates a candidate and preserves the accepted project.
3. Show the two real route findings on the focused review screen. The plan highlights the plumbing and structure layers; each finding can locate its source element.
4. Choose **Preview clear routes**. The routing engine recomputes water, drainage, and conduit paths. The plumbing count changes from two findings to zero.
5. Show **Change since uploaded plan** and **Compare quantities**. In the bundled sample, the clear routes add approximately ₱600 in modeled material cost because the paths are longer. Rates are synthetic demonstration inputs.
6. Choose **Apply revision** only if you want to show the acceptance step. Until then, the saved design remains unchanged. Undo and revision history remain available after acceptance.

## Optional second moment: fire protection

Quick-check route: choose **Home** in the left rail, then **Fire sample** on the **Check a plan** card. This imports a single-storey office with no fire provisions as a candidate and opens the fire review with four findings. Finish by choosing **Planning graph** to show that a quick check continues into the full plan.

Full-plan route:

1. Return to **Planning** and open **Fire protection**.
2. Explain that the current residential brief is not silently treated as a supported occupancy. Choose a supported business or mercantile occupancy explicitly, then start the screen.
3. Show the findings-first view, the passing screens, and the separate unassessed count. Open **Edit occupancy, exits & provisions**, add one provision such as exit signs, and preview the recalculation.

The fire screen is limited to the implemented single-storey business and mercantile family. It does not claim residential fire-code review, FSEC approval, or full building compliance.

## Upload behavior

| Input | What happens | Review boundary |
|---|---|---|
| Native BuildGraph JSON | Schema validation, deterministic recomputation, candidate revision, focused discipline findings | The model's supplied inputs are reviewed within the implemented analytical scope |
| PDF, PNG, JPEG, WebP | The configured AI provider maps recognizable rooms to the current model and proposes geometry changes | The file is a layout reference. Services, devices, loads, dimensions, and compliance are not inferred |
| Current model | Opens the chosen discipline immediately | Useful when the plan is already in BuildGraph |
| Plumbing sample | Imports a bundled model with direct routes as a candidate | A reliable local demo with no AI or network dependency |
| Fire sample | Imports a bundled office (business occupancy, no provisions) as a candidate | A reliable local demo with no AI or network dependency |

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

Open `http://127.0.0.1:8011`. The plumbing sample, deterministic calculations, revision comparison, quantities, and exports work without an AI provider. PDF/image interpretation requires a configured provider and should be demonstrated only with a non-sensitive reference drawing the presenter is authorized to send to that provider.

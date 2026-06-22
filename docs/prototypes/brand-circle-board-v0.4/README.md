# Brand Circle Board v0.4 Prototype

## Scope

This prototype supports the PRD direction in `docs/prd-brand-circle-board-redesign-2026-06-17.md`.

Core premise:

- Brand Space is organized as `Graph / Boards / Assets / Reports`.
- Board is an executable canvas, not a report page.
- The only board-level deliverable is `Graph Update`.
- Assets keep intermediate outputs such as raw answers, parsed answers, and graph patches.
- Reports interpret a graph state change and must pass report guardrails.

## Views

- `index.html?view=board`: default runtime canvas with parallel platform fetch nodes, inspector, run status, and simulated graph patch stream.
- `index.html?view=graph`: brand graph home with circle status, risk entities, competitor candidates, and graph update queue.
- `index.html?view=report`: graph-update report view with graph diff, report guardrails, and trace chain.

The file can be opened directly in a browser. No dev server is required.

## Interactions

- Click a node to update the Node Inspector overview metrics.
- Switch `Overview / Events / Output / Config` in the inspector.
- Click `View run log` to open the run log modal.
- Click `Pause`, `Stop`, or the canvas play button to change the simulated board runtime state.
- Click the platform rack `Run all` control to simulate one grouped four-platform dispatch.
- Click runtime controls for events and output to move the inspector to the related tab.
- Click Graph Update Queue review actions to mark a patch as accepted or rejected.
- Click the pending review entity in Graph Home, then accept it into a candidate circle or keep it in the review layer.
- Click `Share` to simulate a report guardrail event entering the graph patch stream.

## PRD Mapping

- Parallel fetch group maps to the four-platform AI capture model: ChatGPT, DeepSeek, Kimi, Doubao.
- Node colors map to PRD node roles: input, prepare, fetch, extract, review, graph update.
- The inspector separates live status, event stream, output artifacts, and guardrail config.
- The graph preview stays secondary in the board view; the primary board deliverable remains graph patch application.
- Risk and competitor changes are visible as review candidates rather than silently promoted into the brand circle.
- Graph Update Queue now reflects the PRD state machine with `auto_applied` and `needs_review` groups.
- Report Guardrails show `PASS / WARN / BLOCK`; BLOCK keeps the report in draft rather than treating validation as decorative metadata.
- Trace Chain is represented as conclusion -> evidence -> platform/question -> graph patch.

## Motion Layer

The prototype uses motion to make the system feel actively orchestrated:

- Board runtime: scanning canvas pass, faster pipe flow, active node sweeps, progress shimmer, and run-state heartbeat.
- Platform rack: rack-level scan and overall progress pulse to show four platforms running as one grouped unit.
- Graph home: orbit marker, pending-review layer pulse, and review-entity motion to make graph state changes visible.
- Review actions: accept/reject and run events trigger short burst feedback.
- Report view: guardrail and trace content wake in as generated validation output.

The motion layer includes `prefers-reduced-motion` handling. Production implementation should keep this as a state-driven animation system tied to actual run events, not decorative CSS loops disconnected from runtime state.

## Review v0.4 Response

The review file `docs/prototype-review-v0.4-2026-06-17.md` raised 3 mismatches, 4 gaps, and 2 design conflicts. This revision addresses the implementation-facing items:

- Parallel Platform Rack: the four fetch nodes are visually grouped and have a group-level run control plus overall progress.
- Graph Update Queue: auto-applied and needs-review patches are separated, with diff summaries and accept/reject actions.
- Pending Review Layer: the graph shows a dedicated review zone and supports accept/keep-review interactions.
- Node Inspector Output: output now shows node-specific artifacts and production-relevant counts.
- Report Guardrails: the report view now includes a blocking validation state.
- Trace Chain: report claims point back to evidence, platform, question, and patch ids.
- Runtime Controls: Pause and Stop copy now clarifies Orchestrator behavior.
- Visual Language: the prototype keeps the selected clean white runner look but removes decorative blue gradients and reinforces Specta teal as the action/evidence color.

Remaining production caveat: `index.html` is still a single-file prototype with layered CSS from iteration history. Production implementation should not copy this CSS directly; it should extract tokens and components into the frontend design system.

## Implementation Notes

The production build should split this prototype into:

- `BrandSpaceShell`: sidebar, topbar, route-level layout.
- `BoardRuntimeView`: canvas, viewport controls, run footer, canvas toolbar.
- `BoardNode`: role-colored node with progress and runtime state.
- `NodeInspector`: overview, events, output, config tabs.
- `GraphHomeView`: graph lenses, update queue, selected entity details.
- `ReportReviewView`: report content, graph diff, guardrail results, trace chain.
- `GraphUpdateQueue`: patch grouping, diff preview, state-machine actions.
- `ReviewLayerControls`: accept / reject / keep-review interactions for pending entities.
- `TraceChain`: claim-to-evidence-to-answer-to-platform source trace.
- `ReportGuardrailStatus`: PASS / WARN / BLOCK validation result renderer.

Runtime integration should keep the board as a visual control surface over orchestrated workflow execution. The frontend should not own scoring, graph patch resolution, report validation, or evidence rules.

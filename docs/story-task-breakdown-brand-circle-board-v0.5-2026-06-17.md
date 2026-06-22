# Story / Task Breakdown: Brand Circle Board v0.5

> Date: 2026-06-17  
> Status: Planning draft  
> PRD: `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md`  
> Handoff: `docs/implementation-handoff-brand-circle-board-v0.5-2026-06-17.md`
> Phase 0 closeout: `docs/milestone-0-closeout-brand-circle-board-v0.5-2026-06-17.md`
> First engineering ticket: `docs/first-engineering-ticket-brand-space-v0.5-2026-06-17.md`
> Specs:
> - `docs/spec-circle-allocation-v0.1-2026-06-17.md`
> - `docs/spec-entity-extraction-v0.1-2026-06-17.md`
> - `docs/spec-report-generation-v0.1-2026-06-17.md`
> - `docs/spec-backend-models-api-v0.1-2026-06-17.md`

Estimate scale:

- `S`: 0.5-1 engineering day.
- `M`: 2-3 engineering days.
- `L`: 4-6 engineering days.
- `XL`: needs technical spike or split before sprint commitment.

## Milestone 0: Product And Technical Freeze

Goal: Freeze the implementation boundary before frontend/backend work starts.

### Story 0.1: Approve PRD v0.5

Estimate: `S`

Tasks:

- Review PRD v0.5 with product/design.
- Confirm Board's only core deliverable is Graph Update.
- Confirm Reports interpret Graph Update only.
- Confirm Chat remains contextual command/explanation layer.
- Confirm Graph / Boards / Assets / Reports IA.
- Confirm Brand Space ships as a parallel feature area beside the current Dashboard.

Acceptance:

- No unresolved P0 product decision remains.
- Open questions are either assigned or explicitly deferred.
- Current Dashboard replacement is explicitly out of Phase 1.

### Story 0.2: Approve Runtime Boundary

Estimate: `S`

Tasks:

- Review Board / Orchestrator / Node Runtime ownership.
- Confirm frontend does not own scoring, patch truth, or report validation truth.
- Confirm Pause / Stop / Resume semantics.
- Confirm auto-apply boundary.

Acceptance:

- Engineering agrees on the state machines before implementation.

### Story 0.3: Map Existing Data Models

Estimate: `L`

Tasks:

- Map current session / task / output concepts to BoardRun, NodeRun, Artifact, GraphUpdate.
- Map `BrandIntelligenceRun` to BoardRun source or parent run.
- Map `AnalysisTask` / `TaskRun` to runtime attempt and execution recovery.
- Map A3 question outputs to `question_set` artifacts.
- Map A4 fetch outputs to `raw_answers` and `parsed_answers` artifacts.
- Map A5 report outputs to legacy report artifacts and future `CircleReport`.
- Decide whether BoardRun owns graph truth directly or references existing task runtime truth.
- Identify missing database tables.
- Identify which current A3/A4/A5 outputs can be mapped to Assets.
- Identify migration risks for existing report artifacts.

Acceptance:

- Data mapping doc or table exists.
- Missing persistence work is listed as backend tasks.
- Legacy reports without Graph Update are explicitly marked `pre_graph_update`.

### Story 0.4: Approve Phase 0 Implementation Specs

Estimate: `M`

Tasks:

- Review and freeze circle allocation formula.
- Review and freeze entity extraction workflow.
- Review and freeze report generation strategy.
- Review and freeze Python model/API contracts.
- Confirm v1 platform list: `doubao`, `yuanbao`, `kimi`, `deepseek`.
- Record deferred adapter slots such as `zhipu` or `chatgpt`.

Acceptance:

- No P0 algorithm or API gap remains.
- Engineering can start Milestone 1 without guessing scoring, extraction, reporting, or persistence contracts.

## Milestone 1: Brand Space Shell

Goal: Create the stable product frame without real graph mutation.

### Story 1.1: Add Brand Space Route Shell

Estimate: `M`

Tasks:

- Add `/brand-space` route shell for Brand Space.
- Optionally add `/dashboard-v2` QA alias.
- Add `NEXT_PUBLIC_BRAND_SPACE_ENABLED` gate if needed.
- Add left navigation.
- Add brand context header.
- Add top run status slot.
- Add route placeholders for Graph, Boards, Assets, Reports.

Acceptance:

- User can navigate between four primary areas.
- Shell follows Specta global visual system.
- No generic AI palette or decorative light effects.
- Existing `/dashboard` behavior is unchanged.

### Story 1.2: Static Graph Home

Estimate: `M`

Tasks:

- Build Graph Home layout.
- Render static circle graph with risk, competitor, and pending-review zones.
- Render Graph Update Queue with mock auto-applied and needs-review groups.
- Render Selected Entity panel.

Acceptance:

- Risk entities are visible by default.
- Pending review layer is visible.
- Graph Update Queue shows diff summaries.

### Story 1.3: Static Report Review

Estimate: `M`

Tasks:

- Build report reader layout.
- Render Graph Diff.
- Render Report Guardrail Status.
- Render Trace Chain.
- Render BLOCK state.

Acceptance:

- BLOCK state visually prevents publish.
- Trace Chain shows claim -> evidence -> answer -> platform/question -> patch.

## Milestone 2: Board Runtime UI With Mock State

Goal: Prove the visual runtime architecture before connecting real backend execution.

### Story 2.1: Board Canvas And Nodes

Estimate: `L`

Tasks:

- Build Board Runtime route.
- Build BoardCanvas.
- Build BoardNode.
- Build PipelineEdge.
- Build role color system for input, prepare, fetch, extract, review, graph update.

Acceptance:

- Canvas matches clean white runner direction.
- Nodes are compact enough for workflow readability.
- Edges show data flow state.

### Story 2.2: Parallel Platform Rack

Estimate: `M`

Tasks:

- Build PlatformRackNode.
- Render Doubao / Yuanbao / Kimi / DeepSeek nodes inside a grouped rack.
- Add group-level progress.
- Add per-platform status.
- Add group-level Run all action.

Acceptance:

- User understands this is one grouped parallel runtime unit.
- One platform failure does not visually imply whole rack failure.

### Story 2.3: Node Inspector

Estimate: `M`

Tasks:

- Build NodeInspector tabs.
- Implement Overview tab.
- Implement Events tab.
- Implement Output tab.
- Implement Config tab.
- Connect selected node state.

Acceptance:

- Selecting a node updates all Inspector tabs.
- Output tab shows artifact references, not placeholder copy.

### Story 2.4: Runtime Controls

Estimate: `M`

Tasks:

- Add Start / Pause / Resume / Stop controls.
- Add run footer.
- Add run log modal.
- Implement local reducer for mock run state.

Acceptance:

- Pause removes running state from active nodes.
- Resume restores running state.
- Stop preserves visible artifacts and pending patches.

### Story 2.5: Motion Layer

Estimate: `M`

Tasks:

- Add run heartbeat.
- Add edge data flow.
- Add node scan/progress shimmer.
- Add platform rack scan.
- Add review pulse.
- Add interaction burst.
- Add reduced-motion support.

Acceptance:

- Motion communicates running system state.
- Reduced motion disables continuous loops.
- Motion is driven by run state or events.

## Milestone 3: Backend Runtime And Artifact Foundation

Goal: Persist runs, node states, artifacts, and events.

### Story 3.1: Board Run Persistence

Estimate: `L`

Tasks:

- Add BoardRun model/table.
- Add NodeRun model/table.
- Add run status transitions.
- Add started/ended timestamps.
- Add summary fields.

Acceptance:

- A Board Run can be created, read, paused, resumed, stopped.
- Refreshing frontend can recover run state.

### Story 3.2: Artifact Registry

Estimate: `L`

Tasks:

- Add ArtifactRef model/table or service.
- Define artifact path convention.
- Persist raw answers, parsed answers, graph patch sets, reports, run logs.
- Expose asset listing endpoint.

Acceptance:

- Node outputs point to persisted artifacts.
- Assets view can list artifacts by run and type.

### Story 3.3: Runtime Events

Estimate: `M`

Tasks:

- Add RuntimeEvent envelope.
- Emit run events.
- Emit node events.
- Emit artifact events.
- Emit graph patch events.
- Expose polling or websocket event stream.

Acceptance:

- Frontend can update Board UI from events.
- Event payloads are enough to drive motion states.

## Milestone 4: Minimal Real Graph Update

Goal: Produce a real graph update from a minimal workflow.

### Story 4.1: Graph Patch Set Generation

Estimate: `XL`, split after Story 0.4 if implementation risk remains

Tasks:

- Generate GraphPatchSet from extracted entity relations.
- Include before/after diff.
- Include confidence, sentiment, risk class.
- Include evidence refs.
- Implement `connection_strength` and zone proposal using the circle allocation spec.
- Implement entity relation extraction using the extraction spec, or connect to an existing extractor that satisfies it.

Acceptance:

- Each patch can be displayed in Graph Update Queue.
- Each patch has traceable evidence.

### Story 4.2: Auto-apply Boundary

Estimate: `M`

Tasks:

- Implement low-risk auto-apply rules.
- Implement high-impact needs-review routing.
- Block risk/competitor/circle migration from auto-apply.
- Add backend tests for boundary cases.

Acceptance:

- New risk relation cannot auto-apply.
- New competitor relation cannot auto-apply.
- Small mention/strength updates can auto-apply.

### Story 4.3: Graph Version Write

Estimate: `L`

Tasks:

- Add graph version before/after.
- Apply auto-applied patches.
- Keep needs-review patches pending.
- Handle optimistic lock or serial apply.

Acceptance:

- Completed Board Run can create a Graph Update.
- Graph state changes are versioned.

## Milestone 5: Review Loop

Goal: Let users resolve high-impact graph changes.

### Story 5.1: Graph Update Queue Actions

Estimate: `M`

Tasks:

- Wire accept / reject / keep-review endpoints.
- Persist reviewer decision.
- Update patch state in UI.
- Disable repeated action after decision.

Acceptance:

- Patch decision changes state.
- Decision is auditable.

### Story 5.2: Pending Review Layer

Estimate: `M`

Tasks:

- Render pending-review entities from backend state.
- Link entity to patch.
- Add accept into candidate circle.
- Add keep-review.
- Add reject.

Acceptance:

- Pending entity action writes Graph Update decision.
- Entity does not silently enter official circle.

### Story 5.3: Review Inbox

Estimate: `L`

Tasks:

- Add brand-level Review Inbox view or panel.
- Aggregate needs-review items across Board Runs.
- Filter by risk, competitor, new entity, conflict.

Acceptance:

- User can review pending items outside the originating Board.

## Milestone 6: Report Guardrails And Trace Chain

Goal: Make reports trustworthy and enforceable.

### Story 6.1: Report Skeleton From Graph Update

Estimate: `M`

Tasks:

- Generate report skeleton from Graph Update.
- Include core entity changes.
- Include risk and competitor changes.
- Include evidence excerpts.
- Apply evidence selection and strategic segmentation from the report generation spec.

Acceptance:

- Report cannot cite entities absent from Graph Update.

### Story 6.2: Guardrail Validation

Estimate: `M`

Tasks:

- Implement similarity check for strategic conclusions.
- Implement competitor evidence check.
- Implement risk evidence check.
- Implement evidence concentration check.
- Implement action specificity check.
- Implement circle-label consistency check.

Acceptance:

- BLOCK result prevents publish.
- WARN result is visible.
- PASS result allows publish.

### Story 6.3: Trace Chain Viewer

Estimate: `M`

Tasks:

- Assemble report claim trace.
- Link claim to Graph Patch.
- Link patch to Entity Relation.
- Link relation to Answer and Question.
- Render evidence span.

Acceptance:

- User can trace each key claim to platform and question.

## Milestone 7: Assets View

Goal: Make intermediate outputs inspectable without turning them into primary UI.

### Story 7.1: Asset Listing

Estimate: `M`

Tasks:

- Build Assets view.
- Filter by artifact type.
- Filter by Board Run.
- Link to Graph Update and Report.

Acceptance:

- Raw answers and parsed outputs are discoverable.

### Story 7.2: Artifact Detail

Estimate: `M`

Tasks:

- Render artifact metadata.
- Render preview for JSONL / table-like parsed output when safe.
- Provide copy/open/download affordance if allowed.

Acceptance:

- User can inspect intermediate output without leaving Brand Space.

## Milestone 8: Hardening And Migration

Goal: Prepare for replacing old report-first flows.

### Story 8.1: Legacy Mapping

Estimate: `M`

Tasks:

- Map existing reports to Reports area.
- Map old fetched answers to Assets where possible.
- Mark legacy reports as pre-Graph Update when no trace exists.

Acceptance:

- Old data remains accessible.
- Legacy reports are not falsely treated as traceable Graph Update reports.

### Story 8.2: Performance And Accessibility

Estimate: `M`

Tasks:

- Verify Board rendering with at least 50 nodes.
- Verify reduced motion.
- Verify keyboard access for inspector tabs and review actions.
- Verify text overflow in compact nodes.

Acceptance:

- Board stays usable under expected workflow size.
- Accessibility checks pass for core controls.

## Cross-cutting Validation

Run for every milestone that touches UI:

- Scan for old AI palette / effect terms.
- Scan for question-mark corruption.
- Run `python scripts/validate_change.py`.
- Capture Board / Graph / Report screenshots when visible UI changes.
- Verify interaction paths relevant to the milestone.

Run for every milestone that touches backend truth:

- Unit tests for state transitions.
- Unit tests for guardrail boundaries.
- Persistence test for refresh/reload.
- API contract tests for required fields.

## Suggested Sprint Order

Sprint 0:

- Story 0.1
- Story 0.2
- Story 0.3
- Story 0.4

Sprint 1:

- Story 1.1
- Story 1.2
- Story 1.3

Sprint 2:

- Story 2.1
- Story 2.2
- Story 2.3
- Story 2.4
- Story 2.5

Sprint 3:

- Story 3.1
- Story 3.2
- Story 3.3
- Story 4.1 spike / split

Sprint 4:

- Story 4.1 implementation remainder
- Story 4.2
- Story 4.3
- Story 5.1
- Story 5.2

Sprint 5:

- Story 6.1
- Story 6.2
- Story 6.3
- Story 7.1

Sprint 6:

- Story 7.2
- Story 8.1
- Story 8.2
- production integration hardening

## First Engineering Ticket Recommendation

After Sprint 0 closes, start with:

`FE-001: Parallel Brand Space Shell With Mock Board Runtime`

Ticket doc:

`docs/first-engineering-ticket-brand-space-v0.5-2026-06-17.md`

Reason:

- It proves the new Brand Space frame and Board architecture without waiting for backend graph mutation.
- It avoids prematurely coupling UI to unfinished scoring and graph persistence.
- It lets design and product validate the runtime surface in the real app shell.
- It keeps the current Dashboard stable while the new interaction model is validated.

## Fallback Strategy

If real Graph Update work slips after Milestone 3, do not block the product shell.

Fallback path:

1. Keep Phase 1-2 UI behind the isolated Brand Space route with typed mock data.
2. Ship Assets and Report shells as read-only views over mock or legacy artifacts.
3. Mark all legacy reports as `pre_graph_update`; do not claim Trace Chain completeness.
4. Keep Graph Update Queue in `mock_runtime` mode until GraphPatchSet generation passes tests.
5. Allow users to review the interaction model, but disable publish/apply actions that would imply real graph truth.
6. Continue supporting the old report flow until at least one real Board template can produce a validated Graph Update.

Fallback exit criteria:

- `GraphPatchSet` can be generated from real extracted relations.
- `GraphUpdate` persists with before/after graph version.
- Report generation can block publish on guardrail failure.

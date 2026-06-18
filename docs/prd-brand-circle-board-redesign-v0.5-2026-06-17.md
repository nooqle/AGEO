# PRD v0.5: Specta Brand Circle Board Redesign

> Date: 2026-06-17  
> Status: Implementation-ready draft  
> Scope: Brand Space / Graph / Board Runtime / Assets / Reports  
> Source docs:  
> - `docs/prd-brand-circle-board-redesign-2026-06-17.md`  
> - `docs/prototype-review-v0.4-2026-06-17.md`  
> - `docs/prototypes/brand-circle-board-v0.4/README.md`
> Phase 0 closeout:
> - `docs/milestone-0-closeout-brand-circle-board-v0.5-2026-06-17.md`
> First engineering ticket:
> - `docs/first-engineering-ticket-brand-space-v0.5-2026-06-17.md`
> Implementation spec set:
> - `docs/spec-circle-allocation-v0.1-2026-06-17.md`
> - `docs/spec-entity-extraction-v0.1-2026-06-17.md`
> - `docs/spec-report-generation-v0.1-2026-06-17.md`
> - `docs/spec-backend-models-api-v0.1-2026-06-17.md`

If this PRD summary conflicts with an implementation spec, the spec is the source of truth for Phase 0 engineering freeze.

## 1. Product Decision

Specta should be re-centered around a brand-owned entity relationship graph.

The product surface is no longer primarily a chat flow or a report flow. It becomes a Brand Space with four durable areas:

- `Graph`: the brand's current circle state and entity relationship library.
- `Boards`: executable workflow canvases that update the graph.
- `Assets`: intermediate artifacts such as questions, answers, parsed entities, patches, and raw run outputs.
- `Reports`: interpretations of a specific Graph Update.

The Board's only core deliverable is `Graph Update`.

Reports do not create truth. Reports explain a graph state change that has already been produced by a Board run and validated by graph/report guardrails.

### 1.1 Rollout Decision

Brand Space should ship as a new parallel feature area beside the current Dashboard.

User-facing name:

- `Brand Space`

Internal engineering labels:

- `brand-space`
- `dashboard-v2` can be used as an internal alias or feature flag name.

The current Dashboard remains active for existing brand management, report-first flows, and Chat handoff paths. Brand Space does not replace it until real Graph Update, review loop, and report guardrails are proven in production-like validation.

## 2. Problems This Version Must Prevent

The redesign must prevent the real failures seen in the Amway report review:

- Mention frequency must not be treated as positive recognition.
- Risk entities must not disappear from the graph.
- Competitor entities must be detected through evidence, not only declared in prose.
- Report evidence must not collapse into one repeated question source.
- Strategic conclusions must differ by score, evidence, sentiment, platform, and scenario.
- Graph changes must be reviewable before high-impact changes are applied.
- Users must understand what the Board is doing while it is running.

## 3. Final IA

### 3.1 Brand Space

Default brand workspace.

Required top-level navigation:

- Overview
- Graph
- Boards
- Assets
- Reports
- Templates
- Connections
- Settings

`Graph` should be the primary analytical home for the brand once the first graph exists.

### 3.2 Graph

Graph shows:

- Current brand circle graph.
- Inner / middle / outer / risk / competitor / pending-review zones.
- Entity inspector.
- Graph Update Queue.
- Graph Update Timeline.
- Lens controls: circle state, this update, risk cognition, competitor pressure, time.

### 3.3 Boards

Boards are executable canvases.

Board templates:

- AI Visibility Monitor / 全景抓取
- User Persona / 用户画像
- Manual Question Source / 手动问题
- Document Modeling / 文档建模
- Periodic Monitor / 周期监控

Users can start from a template, then replace bounded nodes such as question source, platform fetch group, extraction strategy, or report guardrail profile.

### 3.4 Assets

Assets store intermediate and final run artifacts.

Minimum asset groups:

- Brand seeds
- Entity lexicons
- Questions
- Raw answers
- Parsed answers
- Entity relation sets
- Graph patch sets
- Graph updates
- Reports
- Run logs

### 3.5 Reports

Reports are readers for graph change interpretation.

A report must point back to:

- Graph Update id
- Board Run id
- GraphPatchSet id
- EntityRelationSet id
- AnswerSet id
- Supporting questions and platform answers

## 4. Core Concepts

### 4.1 Brand Entity Lexicon

The brand lexicon is the seed entity relationship library for a brand.

It contains:

- Brand entities
- Product entities
- Category entities
- Scene entities
- Audience entities
- Risk entities
- Competitor entities
- Alias and synonym rules
- Initial relationship hints

The lexicon is not the graph. It is a controlled input that helps extraction and matching.

### 4.2 Brand Circle Graph

The graph is the current state of the brand's entity relationships and circle zones.

Primary zones:

- Inner circle: positive, stable, brand-owned associations.
- Middle circle: relevant but not yet stable or fully positive.
- Outer circle: weak, emerging, or exploratory associations.
- Risk layer: negative, questioning, compliance, reputation, or trust-risk entities.
- Competitor layer: direct or indirect substitute entities.
- Pending review layer: entities or relationships that cannot be safely promoted.

### 4.3 Graph Update

Graph Update is the only Board-level deliverable.

It contains:

- Run metadata
- Graph patch set
- Auto-applied patches
- Needs-review patches
- Rejected / accepted review decisions
- Graph version before and after
- Report generation status

### 4.4 Graph Patch

A patch is an atomic proposed graph change.

Patch examples:

- Add entity
- Add relation
- Update relation strength
- Move entity from one zone to another
- Merge alias
- Add risk relation
- Add competitor relation

## 5. Board Runtime Requirements

### 5.1 Board Is A Visual Control Surface

The Board owns:

- Visible workflow layout
- Node status display
- Runtime controls
- Node Inspector
- Graph Patch Stream
- Output artifact pointers

The Board does not own:

- Scoring
- Entity extraction rules
- Graph patch resolution
- Report validation logic
- Persistence truth

### 5.2 Orchestrator Relationship

Orchestrator owns:

- Intent routing inside allowed Board template boundaries
- Node scheduling
- Retry / fallback / pause / stop behavior
- User confirmation strategy
- Runtime recovery

Node Runtime owns:

- Deterministic node execution
- Input contract validation
- Output contract validation
- Artifact writes
- Run event emission

### 5.3 Pause / Stop Semantics

`Pause`:

- Allows currently in-flight external requests to finish when reasonable.
- Stops dispatching new questions or downstream tasks.
- Preserves already written assets and graph patches.
- Keeps unapplied patches in the run queue.

`Stop`:

- Cancels not-yet-started work.
- Preserves assets already written.
- Does not apply unapplied graph patches.
- Marks the Board Run as stopped and reviewable.

`Resume`:

- Continues from persisted run state.
- Must not duplicate already finalized node outputs.

## 6. Parallel Platform Rack

The default AI capture template must show four platform nodes as a grouped rack:

- Doubao Fetch
- Yuanbao Fetch
- Kimi Fetch
- DeepSeek Fetch

These four match the current backend fetch schema. ChatGPT is a future adapter slot only and must not appear in the v1 implementation rack unless a real backend adapter is added.

The rack must support:

- Group-level run state.
- Per-platform progress.
- Per-platform retry / failed / completed status.
- Group-level overall progress.
- Independent platform output artifacts.
- Partial continuation if one platform fails.

The rack is not a decorative group. It represents a real parallel runtime boundary.

## 7. Node Inspector

Inspector tabs:

- Overview
- Events
- Output
- Config

### 7.1 Overview

Shows:

- Node name
- Status
- Progress
- Output count
- Latency
- Started / elapsed / ETA

### 7.2 Events

Shows:

- Runtime event stream
- Graph patch stream
- Retry events
- Guardrail events
- Review-required events

### 7.3 Output

Output must not be an empty placeholder.

Fetch node output should show at minimum:

- Platform
- Answer count
- Failure / retry count
- Extracted entity count if available
- Raw answer artifact path
- Parsed output artifact path

Extract node output should show:

- Entity count
- Relation count
- Risk signal count
- Competitor candidate count
- GraphPatchSet artifact path

Graph Apply output should show:

- Auto-applied count
- Needs-review count
- Rejected / accepted count
- Graph version after run

### 7.4 Config

Shows:

- Node contract version
- Inputs
- Runtime policy
- Guardrail rules
- Whether config can still be changed during run

Running nodes can only change future dispatch parameters, not official outputs already written.

## 8. Graph Update Queue

Graph Update Queue is required in Graph view and Board Inspector.

Queue groups:

- `auto_applied`
- `needs_review`
- `accepted`
- `rejected`
- `blocked`

Each queue item must show:

- Entity / relationship affected
- Patch type
- Before / after diff
- Score or confidence
- Evidence span presence
- Risk / competitor / sentiment status
- Action: accept, reject, keep pending, open evidence

### 8.1 Auto-applied Boundary

Auto-apply is allowed only for low-risk updates:

- `last_seen_at`
- `source_count`
- `mention_count`
- Small `connection_strength` update below 10 percent relative change
- Non-semantic evidence count changes

Auto-apply is not allowed for:

- New entity
- Circle migration
- New risk relation
- New competitor relation
- Alias merge
- Negative sentiment majority
- Low-confidence relation
- Any patch affecting a report conclusion already published

## 9. Pending Review Layer

Pending review layer is a graph zone outside official brand circles.

It is used for:

- New entities
- Low-confidence entities
- Competitor candidates
- Risk candidates
- Grey-zone sentiment entities
- Conflicting circle assignments

Required interactions:

- Accept into candidate circle.
- Keep in review layer.
- Reject from graph update.
- Open evidence.
- Open originating Board Run.

Accepting a pending item must write a review decision into the Graph Update.

## 10. Circle Allocation Rules

The implementation must preserve the v0.4 guardrails:

- `sentiment_or_risk_score < 3/10`: cannot enter inner or middle circle.
- `sentiment_or_risk_score >= 3/10 and < 5/10`: cannot enter inner circle.
- `< 5/10` with negative or questioning evidence majority: must enter risk layer or pending review.
- Inner circle requires `sentiment_or_risk_score >= 6/10` and positive evidence majority.
- Grey-zone movement into inner circle requires two consecutive positive Graph Updates.
- Regulatory, pyramid-scheme, scam, exaggerated-efficacy, pricing-dispute, and trust-risk entities cannot be promoted by connection strength alone.

The rule order is:

1. Detect risk / competitor / sentiment class.
2. Apply one-vote veto and review gates.
3. Calculate connection strength.
4. Decide zone.
5. Write patch and evidence.

## 11. Competitor Detection

`competes_with` cannot be inferred from same-category co-mention alone.

Required evidence:

- Explicit substitute / recommendation / comparison context.
- Evidence span.
- Confidence score.
- Platform and question reference.

Rules:

- `confidence < 0.7`: pending review only.
- `confidence >= 0.7`: competitor candidate patch, still review-required before graph promotion.
- EntityLexicon competitor flag can seed candidates but cannot replace evidence.

## 12. Risk Detection

Risk detection sources:

- EntityLexicon risk flag.
- Risk keyword set.
- Negative or questioning evidence.
- Risk relation extraction.
- High-frequency negative co-occurrence.

Risk rendering requirements:

- Risk entities are visible by default.
- Risk layer is not hidden by normal graph filters.
- Risk evidence must be traceable to question and platform.

## 13. Report Requirements

### 13.1 Report Positioning

Report explains one Graph Update.

It must not:

- Invent graph facts not present in the Graph Update.
- Claim competitor findings without competitor evidence.
- Claim risk findings without risk evidence.
- Reuse generic strategic conclusions across unrelated entities.

### 13.2 Report Structure

Minimum structure:

- Summary of graph change
- Core entity changes
- Risk changes
- Competitor changes
- Strategic word segmentation
- Evidence excerpts
- Recommended next Board
- Guardrail result
- Trace Chain

### 13.3 Report Guardrails

Report validation states:

- `PASS`: can publish.
- `WARN`: can publish only with visible warning or user confirmation.
- `BLOCK`: cannot publish; save as draft.

Minimum post-generation checks:

- Strategic conclusions similarity over 0.8 -> needs review.
- Competitor claim without evidence span -> BLOCK.
- Risk claim without evidence span -> BLOCK.
- More than 80 percent evidence from one question -> WARN or BLOCK depending severity.
- Action recommendation missing platform and scenario -> BLOCK.
- Circle label contradicts sentiment / evidence rule -> BLOCK.

## 14. Trace Chain

Every report claim must trace back to:

`Report claim -> Graph Update -> Graph Patch -> Entity Relation -> Answer -> Question -> Platform`

Reader interaction:

- Click claim.
- See evidence span.
- See originating platform answer.
- See question text.
- See patch diff.
- Open Board Run.

## 15. Motion Requirements

Motion is a product requirement, not decoration.

Motion must communicate:

- Board is actively executing.
- Parallel platform nodes are running as a group.
- Data is flowing through the graph patch pipeline.
- Review items are waiting for a decision.
- Guardrails can block output.

Required motion states:

- Run-state heartbeat.
- Data flow on active pipeline edges.
- Active node scan / progress shimmer.
- Platform rack scan and progress pulse.
- Graph review layer pulse.
- Review decision burst.
- Report guardrail wake-in.

Accessibility:

- Must support `prefers-reduced-motion`.
- Reduced motion keeps state indicators but disables continuous loops.

## 16. Implementation Phases

### Phase 0: Spec Freeze

Deliver:

- PRD v0.5
- Implementation handoff
- Story / task breakdown
- Prototype v0.4 as visual reference
- Circle allocation spec
- Entity extraction spec
- Report generation spec
- Backend model and API spec

Exit criteria:

- Product direction approved.
- Core state machines approved.
- API contracts are implementable.
- `connection_strength`, entity extraction, report generation, and backend model/API specs are approved.
- Team agrees prototype CSS is reference-only, not production source.

### Phase 1: Read-only Brand Space Shell

Deliver:

- Parallel Brand Space feature area, behind feature flag if needed
- `/brand-space` route shell
- Optional `/dashboard-v2` QA alias
- Graph / Boards / Assets / Reports navigation
- Static Graph view
- Static Report view
- No real run execution

### Phase 2: Board Runtime Prototype In App

Deliver:

- Board canvas runtime view
- Platform rack component
- Node Inspector
- Mock event stream
- Motion layer connected to mock run state

### Phase 3: Minimal Real Graph Update

Deliver:

- Board Run persistence
- Node run persistence
- Artifact references
- GraphPatchSet creation
- Graph Update Queue
- Auto-applied low-risk patch handling

### Phase 4: Review Loop

Deliver:

- Pending review layer
- Accept / reject / keep-review actions
- Review decision persistence
- Graph version update after approved patches

### Phase 5: Report Guardrails And Trace Chain

Deliver:

- Report generation skeleton
- Guardrail validation
- PASS / WARN / BLOCK states
- Trace Chain viewer
- Report draft / publish boundary

## 17. Acceptance Criteria

### Product

- User can understand that Board output is Graph Update.
- User can see intermediate artifacts in Assets.
- User can see and act on pending graph changes.
- User can understand why a report is blocked or publishable.
- User can trace a report claim back to a question and platform answer.

### Interaction

- Platform rack communicates parallel execution.
- Pause / Stop behavior is visible and explainable.
- Output tab shows useful node artifacts.
- Graph Update Queue shows diff and state.
- Pending review layer has accept / reject / keep-review actions.

### Visual / Motion

- Uses Specta Evidence Teal as primary action and evidence color.
- Does not use old AI-gradient language.
- Motion communicates execution and review state.
- Reduced-motion mode remains usable.

### Technical

- Graph patches are versioned.
- Report claims are traceable.
- Auto-apply boundary is enforced server-side.
- Frontend does not own scoring or validation truth.
- Board state can be recovered after refresh.
- Circle allocation follows `spec-circle-allocation-v0.1-2026-06-17.md`.
- Entity extraction follows `spec-entity-extraction-v0.1-2026-06-17.md`.
- Report generation follows `spec-report-generation-v0.1-2026-06-17.md`.
- Backend models and APIs follow `spec-backend-models-api-v0.1-2026-06-17.md`.

## 18. Non-goals

- This is not a general low-code workflow builder.
- Users do not freely script arbitrary nodes in v1.
- Chat is not removed; it becomes a contextual command/explanation layer.
- Reports are not a replacement for graph state.
- Prototype CSS is not production-ready design system code.

## 19. Open Questions

These remain open after v0.5 and should be resolved before Phase 3:

1. Should every Graph Update generate a report automatically, or only when a user requests one?
2. How much historical graph state should be visible in the first Graph Timeline implementation?
3. What exact storage path convention should Assets use for raw answers and parsed outputs?
4. Should Review Inbox be brand-global only, or also Board-run scoped in the UI?

Resolved in this review pass:

- Phase 3 v1 platform rack uses `doubao`, `yuanbao`, `kimi`, and `deepseek`. `chatgpt` is not part of v1 implementation unless a backend adapter exists.

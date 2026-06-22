# Implementation Handoff: Brand Circle Board v0.5

> Date: 2026-06-17  
> Status: Engineering handoff draft  
> Product reference: `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md`  
> Prototype reference: `docs/prototypes/brand-circle-board-v0.4/index.html`
> Phase 0 closeout: `docs/milestone-0-closeout-brand-circle-board-v0.5-2026-06-17.md`
> First engineering ticket: `docs/first-engineering-ticket-brand-space-v0.5-2026-06-17.md`
> Spec references:
> - `docs/spec-circle-allocation-v0.1-2026-06-17.md`
> - `docs/spec-entity-extraction-v0.1-2026-06-17.md`
> - `docs/spec-report-generation-v0.1-2026-06-17.md`
> - `docs/spec-backend-models-api-v0.1-2026-06-17.md`

This handoff defines integration boundaries. Algorithm truth, extraction rules, report generation rules, and Python model/API details live in the spec references above.

## 1. Implementation Principle

Do not copy the prototype as production code.

The prototype is a visual and interaction reference. Production should rebuild the feature using the Specta frontend architecture, shared tokens, typed API contracts, persisted run state, and real artifact references.

Frontend owns the visual control surface.

Backend / runtime owns:

- Node execution
- Entity extraction
- Scoring
- Patch lifecycle
- Report validation
- Persistence truth

Implementation must use the current v1 fetch platform list unless new adapters are added:

- `doubao`
- `yuanbao`
- `kimi`
- `deepseek`

`chatgpt` is not a v1 platform rack item without a backend adapter.

## 2. Target Route Shape

Phase 1 should create a new parallel feature area, not replace the current Dashboard.

Recommended Phase 1 route:

```text
/brand-space
```

Optional QA alias:

```text
/dashboard-v2
```

The UI label remains `Brand Space`; `dashboard-v2` is only an internal engineering alias if used.

Future durable routes:

```text
/brand-space/[brandId]/graph
/brand-space/[brandId]/boards
/brand-space/[brandId]/boards/[boardId]
/brand-space/[brandId]/assets
/brand-space/[brandId]/reports
/brand-space/[brandId]/reports/[reportId]
```

Feature flag:

```text
NEXT_PUBLIC_BRAND_SPACE_ENABLED
```

Existing `/dashboard` behavior must remain unchanged in Phase 1.

## 3. Frontend Component Map

### 3.1 Shell

`BrandSpaceShell`

Responsibilities:

- Brand context header
- Left navigation
- Top run status region
- View-level routing outlet

Inputs:

- `brandId`
- `brandName`
- `activeSection`
- `currentGraphVersion`
- `activeRunSummary`

### 3.2 Graph Home

`GraphHomeView`

Responsibilities:

- Render current Brand Circle Graph
- Show graph lenses
- Show Graph Update Queue
- Show selected entity inspector
- Show pending review layer

Subcomponents:

- `BrandCircleGraph`
- `GraphLensTabs`
- `GraphUpdateQueue`
- `SelectedEntityPanel`
- `PendingReviewLayer`

### 3.3 Board Runtime

`BoardRuntimeView`

Responsibilities:

- Render executable canvas
- Render runtime toolbar
- Render run footer
- Render node graph
- Render right Node Inspector
- Connect to run events

Subcomponents:

- `BoardCanvas`
- `BoardNode`
- `PlatformRackNode`
- `PipelineEdge`
- `CanvasRuntimeControls`
- `RunFooter`
- `NodeInspector`
- `RunLogModal`

### 3.4 Node Inspector

`NodeInspector`

Tabs:

- `Overview`
- `Events`
- `Output`
- `Config`

Data sources:

- `NodeRun`
- `NodeEvent[]`
- `NodeOutputArtifact[]`
- `NodeConfigSchema`

### 3.5 Reports

`ReportReviewView`

Responsibilities:

- Render report content
- Render Graph Diff
- Render Report Guardrail Status
- Render Trace Chain
- Expose navigation back to Graph Update and Board Run

Subcomponents:

- `GraphUpdateReport`
- `GraphDiffPreview`
- `ReportGuardrailStatus`
- `TraceChain`

### 3.6 Assets

`AssetsView`

Responsibilities:

- List run artifacts
- Filter by artifact type
- Open raw / parsed outputs
- Link artifacts to Board Run and Graph Update

## 4. Core Types

### 4.1 Board Run

```ts
type BoardRunStatus =
  | "queued"
  | "running"
  | "paused"
  | "stopping"
  | "stopped"
  | "completed"
  | "failed";

type BoardRun = {
  id: string;
  brandId: string;
  boardId: string;
  templateId: string;
  status: BoardRunStatus;
  startedAt?: string;
  endedAt?: string;
  graphUpdateId?: string;
  activeNodeIds: string[];
  nodeRuns: NodeRun[];
  summary: {
    nodesTotal: number;
    nodesCompleted: number;
    answersFetched: number;
    entitiesExtracted: number;
    patchesProposed: number;
    patchesAutoApplied: number;
    patchesNeedsReview: number;
  };
};
```

### 4.2 Node Run

```ts
type NodeRunStatus =
  | "idle"
  | "queued"
  | "running"
  | "retrying"
  | "completed"
  | "needs_review"
  | "failed"
  | "skipped";

type NodeRun = {
  id: string;
  boardRunId: string;
  nodeId: string;
  nodeType: string;
  title: string;
  status: NodeRunStatus;
  progress: number;
  startedAt?: string;
  endedAt?: string;
  latencyP95Ms?: number;
  inputArtifactRefs: ArtifactRef[];
  outputArtifactRefs: ArtifactRef[];
  metrics: Record<string, string | number | boolean>;
};
```

### 4.3 Artifact

```ts
type ArtifactType =
  | "brand_seed"
  | "entity_lexicon"
  | "question_set"
  | "raw_answers"
  | "parsed_answers"
  | "entity_relation_set"
  | "graph_patch_set"
  | "graph_update"
  | "report"
  | "run_log";

type ArtifactRef = {
  id: string;
  type: ArtifactType;
  path: string;
  mimeType?: string;
  rowCount?: number;
  createdAt: string;
};
```

### 4.4 Graph Patch

```ts
type GraphPatchStatus =
  | "proposed"
  | "auto_applied"
  | "needs_review"
  | "accepted"
  | "rejected"
  | "blocked"
  | "applied";

type GraphPatch = {
  id: string;
  graphUpdateId: string;
  patchType:
    | "add_entity"
    | "add_relation"
    | "update_strength"
    | "move_zone"
    | "merge_alias"
    | "add_risk_relation"
    | "add_competitor_relation";
  status: GraphPatchStatus;
  entityId?: string;
  relationId?: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  confidence?: number;
  sentimentScore?: number;
  evidenceRefs: EvidenceRef[];
  requiresReviewReason?: string;
};
```

### 4.5 Evidence

```ts
type EvidenceRef = {
  id: string;
  questionId: string;
  platform: "doubao" | "yuanbao" | "kimi" | "deepseek" | "zhipu" | string;
  answerArtifactId: string;
  spanStart?: number;
  spanEnd?: number;
  polarity: "positive" | "neutral" | "questioning" | "negative";
  excerpt: string;
};
```

### 4.6 Report Guardrail

```ts
type GuardrailSeverity = "pass" | "warn" | "block";

type ReportGuardrailResult = {
  id: string;
  reportId: string;
  severity: GuardrailSeverity;
  ruleId: string;
  title: string;
  message: string;
  evidenceRefs?: EvidenceRef[];
};
```

## 5. API Contract Draft

Detailed request/response, auth, pagination, and error contracts are defined in `docs/spec-backend-models-api-v0.1-2026-06-17.md`. This section keeps the frontend integration surface visible.

All routes must be scoped by authenticated user, brand access, and tenant/org policy. The frontend does not send `reviewerId`; review identity is derived server-side.

### 5.1 Brand Space

```http
GET /api/v1/brands/{brandId}/space
```

Returns:

- Brand metadata
- Current graph version
- Active / latest Board Run summary
- Navigation counts

### 5.2 Graph

```http
GET /api/v1/brands/{brandId}/graph
GET /api/v1/brands/{brandId}/graph/updates
GET /api/v1/brands/{brandId}/graph/updates/{graphUpdateId}
```

### 5.3 Board Runtime

```http
GET  /api/v1/boards/{boardId}
POST /api/v1/boards/{boardId}/runs
GET  /api/v1/board-runs/{runId}
POST /api/v1/board-runs/{runId}/pause
POST /api/v1/board-runs/{runId}/resume
POST /api/v1/board-runs/{runId}/stop
GET  /api/v1/board-runs/{runId}/events
```

### 5.4 Graph Patch Review

```http
POST /api/v1/graph-patches/{patchId}/accept
POST /api/v1/graph-patches/{patchId}/reject
POST /api/v1/graph-patches/{patchId}/keep-review
```

Required body:

```json
{
  "decisionNote": "string",
  "targetZone": "inner | middle | outer | risk | competitor | pending_review | null",
  "expectedGraphVersion": 12
}
```

Required responses and errors:

- `200`: updated patch and graph update state.
- `403 brand_access_denied`
- `404 graph_patch_not_found`
- `409 graph_version_conflict`
- `409 patch_already_decided`
- `423 patch_blocked_by_guardrail`

### 5.5 Assets

```http
GET /api/v1/brands/{brandId}/assets
GET /api/v1/artifacts/{artifactId}
```

### 5.6 Reports

```http
GET  /api/v1/reports/{reportId}
POST /api/v1/graph-updates/{graphUpdateId}/reports
POST /api/v1/reports/{reportId}/validate
POST /api/v1/reports/{reportId}/publish
```

Publishing must fail when any guardrail returns `block`.

Required responses and errors:

- `201`: report draft generated from graph update.
- `200`: report validation or publish response.
- `404 graph_update_not_found`
- `409 report_version_conflict`
- `423 blocked_by_guardrail`
- `422 report_schema_invalid`

## 6. Realtime Event Contract

Recommended event envelope:

```ts
type RuntimeEvent = {
  id: string;
  runId: string;
  graphUpdateId?: string;
  nodeRunId?: string;
  type:
    | "run_started"
    | "run_paused"
    | "run_resumed"
    | "run_stopped"
    | "node_started"
    | "node_progress"
    | "node_completed"
    | "node_retrying"
    | "artifact_written"
    | "graph_patch_proposed"
    | "graph_patch_auto_applied"
    | "graph_patch_needs_review"
    | "report_guardrail_pass"
    | "report_guardrail_warn"
    | "report_guardrail_block";
  severity?: "info" | "success" | "warning" | "risk";
  timestamp: string;
  payload: Record<string, unknown>;
};
```

Frontend motion should be driven by these events, not by arbitrary timers alone.

## 7. Motion Binding

### 7.1 Runtime Motion

| Event | UI response |
|-------|-------------|
| `run_started` | Top run heartbeat starts, canvas sweep starts |
| `node_started` | Node scan starts, connected edge flow starts |
| `node_progress` | Progress bar updates and shimmers |
| `artifact_written` | Output tab row wakes in |
| `graph_patch_proposed` | Graph Patch Stream row wakes in |
| `graph_patch_needs_review` | Review node and pending layer pulse |
| `report_guardrail_block` | Guardrail BLOCK panel wakes in and publish action disables |

### 7.2 Reduced Motion

When `prefers-reduced-motion: reduce`:

- Keep state dots.
- Keep progress changes.
- Disable continuous canvas sweep, orbit, shimmer, and scan loops.
- Keep one-step state changes without movement.

## 8. State Machines

### 8.1 Board Run

```text
queued -> running -> paused -> running -> completed
queued -> running -> stopping -> stopped
queued -> running -> failed
```

Rules:

- `paused` preserves artifacts and graph patches.
- `stopped` preserves artifacts but does not apply pending patches.
- `completed` does not mean all patches are applied; needs-review patches may remain.

### 8.2 Graph Patch

```text
proposed -> auto_applied -> applied
proposed -> needs_review -> accepted -> applied
proposed -> needs_review -> rejected
proposed -> blocked
```

Rules:

- High-impact patches always enter `needs_review`.
- Blocked patches cannot be accepted until the blocking rule is resolved.
- Accepted patches must apply against the latest graph version or retry through optimistic lock.

### 8.3 Report

```text
draft -> validating -> blocked
draft -> validating -> ready_to_publish -> published
draft -> validating -> warning -> ready_to_publish -> published
```

Rules:

- `blocked` reports cannot publish.
- `warning` reports require user confirmation or visible warning depending policy.

## 9. Backend Responsibilities

Backend / services must provide:

- Board run persistence.
- Node run persistence.
- Artifact persistence.
- Graph patch generation.
- Graph patch auto-apply decision.
- Review decision persistence.
- Graph version writes.
- Report skeleton generation.
- Report guardrail validation.
- Trace chain assembly.

## 10. Frontend Responsibilities

Frontend must provide:

- Route shell.
- Canvas view.
- Runtime status display.
- Inspector tabs.
- Queue review actions.
- Pending review layer interaction.
- Report guardrail display.
- Trace chain navigation.
- Motion state representation.

Frontend must not:

- Recalculate truth scores.
- Promote patches by itself.
- Publish blocked reports.
- Invent trace links.
- Mutate official node outputs locally.

## 11. Design System Notes

Production UI must use Specta global visual rules:

- Light-first.
- Paper-neutral surfaces.
- Specta Evidence Teal `#1F7A6B` for primary/evidence states.
- Blue-gray only for platform/source status.
- Amber for warning.
- Red for risk/blocking.
- No old AI-gradient styling.
- No decorative light effects or glass surfaces.

The prototype's single-file CSS is reference-only.

## 12. Validation Plan

Minimum before calling a phase done:

- `python scripts/validate_change.py`
- scan edited files for question-mark corruption
- scan visible UI source for old AI palette/effect terms
- browser screenshot of Board / Graph / Report
- interaction check for:
  - Start / Pause / Resume / Stop
  - Select node
  - Inspector tab switch
  - Output artifact display
  - Accept / reject patch
  - Pending review accept / keep-review
  - BLOCK report cannot publish

For implementation phases touching real data:

- backend tests for patch auto-apply boundary
- backend tests for report guardrail blocking
- frontend tests for disabled publish state
- persistence test for refresh and resume

## 13. First Implementation Slice

Recommended first slice:

1. Create parallel `/brand-space` shell, optionally with `/dashboard-v2` QA alias.
2. Implement static Graph / Board / Report views with typed mock data.
3. Implement Board Run state reducer.
4. Implement motion layer driven by reducer events.
5. Implement Node Inspector with mock output artifacts.
6. Implement Graph Update Queue with mock patch actions.

This slice proves the UI architecture before connecting real graph mutation.

## 14. Risks

- Copying prototype CSS directly will preserve iteration debt.
- Implementing the Board as a generic DAG editor will conflict with product intent.
- Letting frontend decide patch truth will create data integrity issues.
- Adding animation without event binding will look impressive but mislead users.
- Building Reports before Graph Update persistence will recreate the old report-first failure.

## 15. Handoff Checklist

Before engineering starts:

- PRD v0.5 approved.
- Circle allocation spec approved.
- Entity extraction spec approved.
- Report generation spec approved.
- Backend model/API spec approved.
- API contract owners assigned.
- Existing AGEO data models mapped to BoardRun / GraphUpdate / Artifact.
- First route strategy chosen.
- Mock data shape agreed.
- Motion intensity accepted by product/design.
- Reduced-motion requirement accepted.

# Spec: Backend Models And API Contracts v0.1

> Date: 2026-06-17  
> Status: Phase 0 freeze candidate  
> Applies to: FastAPI routes, SQLAlchemy models, Pydantic schemas, Alembic planning  
> PRD reference: `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md`

## 1. Purpose

This spec translates the Brand Circle Board handoff into Python/FastAPI/SQLAlchemy implementation contracts.

The existing backend uses SQLAlchemy 2 `Mapped` / `mapped_column`, UUID primary keys, enum value persistence, Pydantic `BaseModel`, and `JSONText` for JSON payload fields. New models should follow that style.

## 2. Platform Contract

Default v1 fetch platforms must match the current fetch schema:

- `doubao`
- `yuanbao`
- `kimi`
- `deepseek`

`hunyuan` should normalize to `yuanbao`.

`zhipu` can remain a frontend display/config candidate only if a backend adapter is added before implementation. `chatgpt` is not in the v1 implementation list.

## 3. SQLAlchemy Models

### 3.1 `BoardRun`

Table: `board_runs`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | UUID | Yes | Primary key |
| `brand_id` | UUID | Yes | FK to brand/entity context |
| `board_id` | UUID/string | Yes | Template or saved board id |
| `template_id` | string(80) | Yes | `ai_visibility_monitor`, `manual_question_source`, etc. |
| `created_by_user_id` | UUID | No | FK user |
| `status` | enum/string(40) | Yes | `queued/running/paused/stopping/stopped/completed/failed` |
| `progress` | float | Yes | 0-1 |
| `graph_update_id` | UUID | No | Filled when update exists |
| `active_node_ids` | JSONText | Yes | List of node ids |
| `summary` | JSONText | Yes | Counts shown in UI |
| `input_scope` | JSONText | No | Brand seed, platform plan, question source |
| `error_code` | string(80) | No | Stable error code |
| `error_message` | text | No | Human-readable detail |
| `started_at` | timestamptz | No | Runtime start |
| `ended_at` | timestamptz | No | Terminal status |
| `created_at` | timestamptz | Yes | Default now |
| `updated_at` | timestamptz | Yes | On update |

Indexes:

- `(brand_id, status)`
- `(brand_id, updated_at)`
- `(graph_update_id)`

### 3.2 `BoardNodeRun`

Table: `board_node_runs`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | UUID | Yes | Primary key |
| `board_run_id` | UUID | Yes | FK `board_runs.id` |
| `node_id` | string(120) | Yes | Canvas node id |
| `node_type` | string(80) | Yes | `platform_fetch`, `entity_extract`, etc. |
| `title` | string(160) | Yes | Display title |
| `status` | enum/string(40) | Yes | `idle/queued/running/retrying/completed/needs_review/failed/skipped` |
| `progress` | float | Yes | 0-1 |
| `input_artifact_refs` | JSONText | Yes | Artifact ref ids |
| `output_artifact_refs` | JSONText | Yes | Artifact ref ids |
| `metrics` | JSONText | Yes | Latency, answer count, entity count |
| `started_at` | timestamptz | No | |
| `ended_at` | timestamptz | No | |
| `created_at` | timestamptz | Yes | |
| `updated_at` | timestamptz | Yes | |

Indexes:

- `(board_run_id, status)`
- `(board_run_id, node_id)`

### 3.3 `BoardArtifact`

Table: `board_artifacts`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | UUID | Yes | Primary key |
| `brand_id` | UUID | Yes | Scope guard |
| `board_run_id` | UUID | No | FK |
| `node_run_id` | UUID | No | FK |
| `artifact_type` | string(60) | Yes | `brand_seed`, `raw_answers`, `graph_patch_set`, etc. |
| `path` | text | Yes | Storage path |
| `mime_type` | string(120) | No | |
| `row_count` | integer | No | |
| `metadata` | JSONText | Yes | Hash, schema version, source refs |
| `created_at` | timestamptz | Yes | |

Indexes:

- `(brand_id, artifact_type, created_at)`
- `(board_run_id, artifact_type)`

### 3.4 `GraphUpdate`

Table: `graph_updates`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | UUID | Yes | Primary key |
| `brand_id` | UUID | Yes | Scope guard |
| `board_run_id` | UUID | Yes | FK |
| `before_graph_version` | integer | Yes | Optimistic lock base |
| `after_graph_version` | integer | No | Filled after apply |
| `status` | string(40) | Yes | `building/ready/partially_applied/applied/blocked/failed` |
| `summary` | JSONText | Yes | Counts |
| `created_at` | timestamptz | Yes | |
| `updated_at` | timestamptz | Yes | |

Indexes:

- `(brand_id, created_at)`
- `(board_run_id)`

### 3.5 `GraphPatch`

Table: `graph_patches`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | UUID | Yes | Primary key |
| `graph_update_id` | UUID | Yes | FK |
| `brand_id` | UUID | Yes | Scope guard |
| `patch_type` | string(60) | Yes | add entity, relation, strength, zone, alias |
| `status` | string(40) | Yes | proposed, auto_applied, needs_review, accepted, rejected, blocked, applied, conflict |
| `entity_id` | UUID/string | No | Existing or candidate id |
| `relation_id` | UUID/string | No | Existing or candidate id |
| `before` | JSONText | Yes | Diff before |
| `after` | JSONText | Yes | Diff after |
| `score_breakdown` | JSONText | Yes | Circle allocation score |
| `confidence` | float | No | 0-1 |
| `sentiment_score` | float | No | 0-10 |
| `evidence_refs` | JSONText | Yes | Evidence ref ids and snapshots |
| `requires_review_reason` | text | No | |
| `reviewed_by_user_id` | UUID | No | |
| `review_decision_note` | text | No | |
| `reviewed_at` | timestamptz | No | |
| `created_at` | timestamptz | Yes | |
| `updated_at` | timestamptz | Yes | |

Indexes:

- `(brand_id, status)`
- `(graph_update_id, status)`
- `(entity_id)`

### 3.6 `BoardRuntimeEvent`

Table: `board_runtime_events`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | UUID | Yes | Primary key |
| `board_run_id` | UUID | Yes | FK |
| `graph_update_id` | UUID | No | |
| `node_run_id` | UUID | No | |
| `event_type` | string(80) | Yes | Runtime event name |
| `severity` | string(20) | No | info, success, warning, risk |
| `payload` | JSONText | Yes | Event body |
| `created_at` | timestamptz | Yes | |

Indexes:

- `(board_run_id, created_at)`
- `(node_run_id, created_at)`

### 3.7 `ReportGuardrailResult`

Table: `report_guardrail_results`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | UUID | Yes | Primary key |
| `report_id` | UUID | Yes | Report artifact or report table id |
| `graph_update_id` | UUID | Yes | Scope for report truth |
| `severity` | string(20) | Yes | `pass/warn/block` |
| `rule_id` | string(120) | Yes | Stable guardrail id |
| `title` | string(160) | Yes | |
| `message` | text | Yes | |
| `evidence_refs` | JSONText | Yes | |
| `created_at` | timestamptz | Yes | |

Indexes:

- `(report_id, severity)`
- `(graph_update_id, severity)`

## 4. Pydantic Schema Contracts

### 4.1 Board Run Create

```py
class BoardRunCreate(BaseModel):
    brand_id: str
    template_id: str = Field(..., max_length=80)
    board_id: str | None = Field(default=None, max_length=120)
    input_scope: dict[str, Any] = Field(default_factory=dict)
    platforms: list[Literal["doubao", "yuanbao", "kimi", "deepseek"]] = Field(
        default_factory=lambda: ["doubao", "yuanbao", "kimi", "deepseek"]
    )
    auto_dispatch: bool = True
```

### 4.2 Board Run Response

```py
class BoardRunResponse(BaseModel):
    id: str
    brand_id: str
    board_id: str
    template_id: str
    status: Literal["queued", "running", "paused", "stopping", "stopped", "completed", "failed"]
    progress: float
    graph_update_id: str | None = None
    active_node_ids: list[str] = Field(default_factory=list)
    node_runs: list[NodeRunResponse] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None
```

### 4.3 Graph Patch Review

```py
class GraphPatchReviewRequest(BaseModel):
    decision_note: str | None = Field(default=None, max_length=1000)
    target_zone: str | None = Field(default=None, max_length=40)
    expected_graph_version: int | None = None

class GraphPatchReviewResponse(BaseModel):
    patch: GraphPatchResponse
    graph_update: GraphUpdateResponse
```

### 4.4 Report Generate / Publish

```py
class ReportGenerateRequest(BaseModel):
    guardrail_profile_id: str | None = None
    force_regenerate: bool = False

class ReportPublishRequest(BaseModel):
    acknowledge_warnings: bool = False
    expected_report_version: int | None = None
```

## 5. API Contracts

All routes are scoped by authenticated user, brand access, and tenant/org policy. The client must not pass `reviewerId`; the backend derives it from auth context.

### 5.1 Create Board Run

```http
POST /api/v1/boards/{boardId}/runs
```

Request: `BoardRunCreate`

Response `201`:

```json
{
  "run": { "id": "uuid", "status": "queued", "progress": 0, "summary": {} }
}
```

Errors:

- `400 invalid_board_template`
- `403 brand_access_denied`
- `409 active_run_conflict`
- `422 schema_invalid`

### 5.2 Read Board Run

```http
GET /api/v1/board-runs/{runId}
```

Response `200`:

```json
{
  "run": {},
  "nodeRuns": [],
  "latestEvents": [],
  "artifacts": [],
  "graphUpdate": null
}
```

Errors:

- `403 brand_access_denied`
- `404 board_run_not_found`

### 5.3 Pause / Resume / Stop

```http
POST /api/v1/board-runs/{runId}/pause
POST /api/v1/board-runs/{runId}/resume
POST /api/v1/board-runs/{runId}/stop
```

Request:

```json
{ "reason": "optional string" }
```

Response: `BoardRunResponse`

Errors:

- `409 invalid_state_transition`
- `404 board_run_not_found`

### 5.4 Runtime Events

```http
GET /api/v1/board-runs/{runId}/events?after=<eventId>&limit=100
```

Response:

```json
{
  "items": [],
  "nextCursor": "string-or-null"
}
```

Pagination:

- `limit` default `100`, max `500`.
- `after` is an event id cursor or timestamp cursor, depending implementation.

### 5.5 Graph Patch Review

```http
POST /api/v1/graph-patches/{patchId}/accept
POST /api/v1/graph-patches/{patchId}/reject
POST /api/v1/graph-patches/{patchId}/keep-review
```

Request: `GraphPatchReviewRequest`

Response: `GraphPatchReviewResponse`

Errors:

- `403 brand_access_denied`
- `404 graph_patch_not_found`
- `409 graph_version_conflict`
- `409 patch_already_decided`
- `423 patch_blocked_by_guardrail`

### 5.6 Assets

```http
GET /api/v1/brands/{brandId}/assets?type=raw_answers&runId=<runId>&cursor=<cursor>&limit=50
GET /api/v1/artifacts/{artifactId}
```

List response:

```json
{
  "items": [],
  "nextCursor": "string-or-null"
}
```

Pagination:

- `limit` default `50`, max `200`.
- Filter by `type`, `runId`, `graphUpdateId` where available.

### 5.7 Reports

```http
POST /api/v1/graph-updates/{graphUpdateId}/reports
POST /api/v1/reports/{reportId}/validate
POST /api/v1/reports/{reportId}/publish
```

Rules:

- Report generation may produce a draft even when guardrails fail.
- Publish fails if any guardrail result is `block`.
- Publish with `warn` requires policy confirmation.

Errors:

- `404 graph_update_not_found`
- `409 report_version_conflict`
- `423 blocked_by_guardrail`
- `422 report_schema_invalid`

## 6. Migration Strategy

Phase 1 does not migrate old reports into graph-traceable reports.

Phase 3 mapping:

| Existing concept | New concept |
| --- | --- |
| `BrandIntelligenceRun` | Candidate parent/source for `BoardRun` |
| `AnalysisTask` / `TaskRun` | Runtime execution attempt under a `BoardRun` |
| A3 question output | `question_set` artifact |
| A4 fetch output | `raw_answers` and `parsed_answers` artifacts |
| A5 metrics/report output | `report` artifact, later `CircleReport` |

Legacy reports without graph update ids must be marked as `pre_graph_update` and cannot claim full trace chain.

## 7. Required Backend Tests

- Board run state transition rejects invalid transitions.
- Pause preserves artifacts and pending patches.
- Stop prevents unapplied patches from applying.
- Graph patch review derives reviewer from auth context.
- Graph version conflict returns `409 graph_version_conflict`.
- Blocked report publish returns `423 blocked_by_guardrail`.
- Asset listing enforces brand scope.
- Platform list rejects unsupported `chatgpt` unless adapter is explicitly enabled.

# GEO Canonical Field Mapping (2026-04-17)

## Goal

This document maps the proposed GEO canonical analysis contract onto the current
AGEO producer outputs and identifies the fields that are:

- directly reusable
- reusable after normalization
- missing and must be derived or added in the adapter layer

The mapping rule for this redesign is:

- do not break A1 / A2 / A3 / A4 output contracts
- adapt current outputs into canonical GEO objects after A4
- do not let report/dashboard/export layers invent business facts on the fly

## Source Systems

Primary upstream sources:

- A1 brand output: `aeo-platform/backend/app/schemas/brand.py`
- A2 persona output: `aeo-platform/backend/app/schemas/persona.py`
- A3 operational question output: `aeo-platform/backend/app/workflow/nodes_a3.py`
- A4 fetch output: `aeo-platform/backend/app/schemas/fetch.py`

Current downstream writebacks that must be replaced or adapted:

- A5 report artifact: `aeo-platform/backend/app/workflow/a5/persistence.py`
- snapshot raw payload: `aeo-platform/backend/app/services/snapshot_service.py`
- dashboard aggregation: `aeo-platform/backend/app/services/analytics_service.py`
- export markdown fallback: `frontend/src/lib/canvasExportShared.ts`

## Canonical Enum Normalization

These enum mismatches must be resolved in the adapter layer before internal
analyzer execution.

| Canonical concept | Current state | Required action |
| --- | --- | --- |
| `report_type` | current code uses `baseline` / `persona` | freeze canonical naming to `panorama` / `scenario`; keep legacy aliases only in adapter boundary |
| `platform` | current code uses `hunyuan`; GEO docs use `yuanbao` | canonical value is `yuanbao`; map `hunyuan -> yuanbao` at all adapter boundaries |
| `intent` | current A3 values are free text / semi-structured | map into GEO canonical enum with explicit fallback bucket |
| `decision_stage` | current A3 values are semi-structured | map into GEO canonical enum with explicit fallback bucket |
| `answer_state` | currently implicit in metrics/report logic | derive deterministically in `AnswerStateClassifier` |
| `source_type` / `ecosystem_tag` | currently absent as canonical enums | derive in `CitationAnalyzer` |

## 1. `ReportMeta`

| Canonical field | Current source | Mapping rule | Status | Notes |
| --- | --- | --- | --- | --- |
| `report_id` | current output/message/artifact ids | create new canonical artifact id at A5 writeback | derived | do not reuse message id as business id |
| `report_type` | `data_analytics.report_type`, `Message.output_type`, snapshot type | map `baseline -> panorama`, `persona -> scenario` | normalize | legacy values remain only at compatibility boundary |
| `transport_type` | `Message.output_type` | canonical target is always `report` | normalize | do not keep `report_baseline` as canonical transport |
| `artifact_kind` | `extra_metadata.artifact_kind` | canonical target `geo_report` | normalize | report family identity |
| `report_kind` | `extra_metadata.report_kind` | canonical target `panorama` or `scenario` | normalize | subtype lives in metadata, not transport type |
| `brand_name` | `A1.brand_profile.brand_name` | direct map | direct | source of truth should remain A1 |
| `industry` | `A1.brand_profile.industry` | direct map | direct |  |
| `platforms` | A4 fetch request / A4 fetch results | derive distinct platforms included in this run | derived | sort by canonical platform order |
| `scenario_theme` | current code has no stable field | add explicit field in adapter or report invocation context | missing | required for scenario reports |
| `baseline_report_id` | current code has no explicit binding | add explicit relation in scenario runs | missing | must not infer from latest snapshot |
| `generated_at` | task completion / artifact writeback time | direct from writeback timestamp | derived |  |
| `entity_id` | task/session/entity linkage | map from task/session context | derived | needed for history/follow-up |
| `session_id` | current workflow state | direct map | direct |  |
| `task_id` | `AnalysisTask.id` | direct map | direct |  |

## 2. `BrandMaster`

### 2.1 Monitor brand

| Canonical field | Current source | Mapping rule | Status | Notes |
| --- | --- | --- | --- | --- |
| `monitor_brand` | `A1.brand_profile.brand_name` | direct map | direct |  |
| `monitor_brand_en` | `A1.brand_profile.brand_name_en` | direct map | direct |  |
| `monitor_brand_aliases` | `brand_name`, `brand_name_en`, `brand_keywords`, `Entity.aliases` when present | merge and dedupe | normalize | deterministic alias normalization required |
| `official_domains` | `A1.brand_profile.official_website`, `Entity.domain` | normalize to root domain set | normalize | must follow GEO domain normalization rules |
| `industry` | `A1.brand_profile.industry` | direct map | direct |  |
| `core_products` | `A1.brand_profile.core_products` | direct map | direct |  |
| `brand_positioning` | `A1.brand_profile.brand_positioning` | direct map | direct |  |

### 2.2 Competitors

| Canonical field | Current source | Mapping rule | Status | Notes |
| --- | --- | --- | --- | --- |
| `competitor_brands[].name` | `A1.competitors[].name` | direct map | direct |  |
| `competitor_brands[].name_en` | `A1.competitors[].name_en` | direct map | direct |  |
| `competitor_brands[].website` | `A1.competitors[].website` | direct map | direct |  |
| `competitor_brands[].official_domains` | competitor website | normalize root domain | normalize |  |
| `competitor_brands[].competition_type` | `A1.competitors[].competition_type` | direct map | direct |  |
| `competitor_brands[].relevance_score` | `A1.competitors[].relevance_score` | direct map | direct |  |

### 2.3 Alias dictionaries

| Canonical field | Current source | Mapping rule | Status | Notes |
| --- | --- | --- | --- | --- |
| `brand_alias_dict` | no stable current object | build in adapter from monitor + competitors + domains | missing | required by `BrandEntityResolver` |
| `official_domain_dict` | no stable current object | build in adapter | missing | required by `CitationAnalyzer` |

## 3. `QuestionRecord`

Current A3 operational artifacts are written in `nodes_a3.py` and are narrower
than the richer `SimulatedQuestion` schema.

### 3.1 Directly available operational fields

| Canonical field | Current source | Mapping rule | Status | Notes |
| --- | --- | --- | --- | --- |
| `question_id` | `nodes_a3.py` emitted `question_id` | direct map | direct |  |
| `question_text` | `core_question` / `text` | use `core_question` as canonical question text | normalize | avoid using duplicated presentation fields |
| `category` | emitted `category` | direct map into raw question metadata | direct | not yet canonical GEO scene taxonomy |
| `intent` | emitted `user_intent` / `intent` | map into GEO canonical enum | normalize | free-text today |
| `decision_stage` | emitted `decision_stage` / `stage` | map into GEO canonical enum | normalize | free-text today |
| `persona` | persona mode emits `source_persona` | direct when present | partial | panorama reports may remain null |

### 3.2 Fields available only in the richer schema, not guaranteed in operational outputs

| Canonical field | Current source | Mapping rule | Status | Notes |
| --- | --- | --- | --- | --- |
| `scene` | `SimulatedQuestion.linked_scenario`, `category` | prefer linked scenario, fallback to normalized category | partial | operational A3 output usually lacks linked scenario |
| `pain_point` | `SimulatedQuestion.linked_pain_point`, A2 pain points | prefer linked pain point, fallback to persona-level inferred mapping | partial | needs explicit adapter rule |
| `tags` | `keywords`, `seo_keywords`, category tokens | merge if available, else derive lightweight tags | partial | should not require LLM |
| `user_inner_context` | `SimulatedQuestion.user_inner_context` | pass through if present | partial | likely unavailable in current operational artifact |
| `involves_brands` | `SimulatedQuestion.involves_brands` | pass through if present, else derive from A1 brand + competitors | partial |  |

### 3.3 Canonical recommendation

`InputBundleAdapter` should create a normalized `QuestionRecord` per question by:

1. reading the actual A3 operational artifact first
2. enriching from richer A3 schema fields only when available
3. enriching from A2 persona/scenario/pain-point context when deterministic

## 4. `AnswerRecord`

| Canonical field | Current source | Mapping rule | Status | Notes |
| --- | --- | --- | --- | --- |
| `question_id` | `FetchResult.question_id` | direct map | direct |  |
| `question_text` | `FetchResult.question_text` | direct map | direct |  |
| `platform` | `FetchResult.platform` | normalize `hunyuan -> yuanbao` | normalize | canonical artifact only writes `yuanbao` |
| `fetch_method` | `FetchResult.fetch_method` | direct map | direct |  |
| `status` | `FetchResult.status` | map to canonical data status and answer availability | normalize |  |
| `answer_text` | `FetchResult.answer_text` | direct map | direct |  |
| `citation_urls` | `FetchResult.search_references[].url` | extract ordered list | direct | keep original order after URL dedupe |
| `citation_refs` | `FetchResult.search_references[]` | map into `CitationFetchRecord` list | direct |  |
| `raw_response` | `FetchResult.raw_response` | attach as optional raw payload ref or debug payload | partial | should not become report-facing business field |
| `error_message` | `FetchResult.error_message` | direct map | direct | used for missing/failed state |
| `answer_time` | `FetchResult.fetched_at` | direct map | direct | canonical timestamp |
| `fetch_duration` | `FetchResult.fetch_duration` | direct map | direct | optional diagnostic only |
| `raw_snapshot_id` | no stable public field | write new canonical answer payload ref if needed | missing | optional but useful for auditability |

## 5. `CitationFetchRecord`

| Canonical field | Current source | Mapping rule | Status | Notes |
| --- | --- | --- | --- | --- |
| `url` | `SearchReference.url` | direct map | direct | subject to URL normalization + dedupe |
| `title` | `SearchReference.title` | direct map | direct |  |
| `snippet` | `SearchReference.snippet` | direct map | direct |  |
| `site_name` | `SearchReference.site_name` | direct map | direct |  |
| `is_official_raw` | `SearchReference.is_official` | preserve as raw hint only | direct | canonical official judgement should be domain-based |
| `domain` | not guaranteed in schema | derive by canonical domain extraction | derived | must follow GEO rules |
| `source_type` | not available | derive in `CitationAnalyzer` | missing | canonical business classification |
| `ecosystem_tag` | not available | derive in `CitationAnalyzer` | missing |  |
| `is_platform_ecosystem` | not available | derive in `CitationAnalyzer` | missing |  |
| `is_brand_related` | not available | derive in `CitationAnalyzer` | missing |  |
| `official_conversion_flag` | not available | derive in `CitationAnalyzer` aggregate | missing |  |

## 6. `DomainTaxonomy`

There is no current unified domain taxonomy object in the codebase.

This must be introduced as a canonical static/configured resource that supports:

- domain normalization
- `source_type`
- `ecosystem_tag`
- official-domain matching
- platform ecosystem matching

Recommended storage shape:

- code-defined seed taxonomy
- optional override/config extension for operations

## 7. Current Persistence Surfaces That Must Be Adapted

These are not upstream producer fields, but they are part of the mapping and
migration boundary because follow-up, dashboard, and export currently depend on
them.

### 7.1 Current A5 report artifact

Current writeback shape in `a5/persistence.py` contains:

- `metrics`
- `content`
- `executive_summary`
- `report_markdown`
- `fetch_results_summary`
- `metrics_raw`
- `report_data`
- `summary_metrics`
- `scenario_matrix`
- `source_overview`
- `mention_sentiment_analysis`
- `report_v2`

Canonical replacement should write:

- `meta`
- `input_bundle`
- `skill_outputs` or renamed equivalent if the GEO example package is revised
- `metric_bundle`
- `comparison_bundle`
- `insight_candidates`
- `sections`
- `full_markdown`
- `dashboard_projection`

Canonical writeback metadata target:

- `output_type = report`
- `artifact_kind = geo_report`
- `report_kind = panorama | scenario`

### 7.2 Snapshot raw payload

Current snapshot raw payload stores:

- `metrics`
- `report_data`
- `competitor_metrics`
- `fetch_results_summary`

Canonical replacement should store a compact report payload ref or selected
canonical bundles, not only legacy metrics/report blobs.

### 7.3 Knowledge workspace

Current knowledge ingestion already preserves:

- A1 brand profile facts
- A1 competitor facts
- A4 answer facts
- A4 citation facts

This is good and should be preserved conceptually.
The redesign should extend history consumption around canonical reports, not
replace the A1/A4 fact store.

### 7.4 Monitoring baseline

Current schedule baseline stores old A1 + A3 fragments in
`MonitoringSchedule.baseline_data`.

Canonical recommendation:

- keep the idea of baseline reuse
- redefine payload shape to store deterministic canonical rerun inputs

## 8. Missing Fields and Required Adapter Derivations

The following fields are not reliably available today and must be derived or
added after A4.

| Missing field | Required by | Suggested source | Complexity |
| --- | --- | --- | --- |
| `scenario_theme` | report meta | task/report invocation context | low |
| `baseline_report_id` | scenario comparison | explicit orchestrator/runtime binding | medium |
| canonical `brand_alias_dict` | brand resolution | A1 + entity aliases + domains | medium |
| canonical `domain_taxonomy` | citation analysis | new static/config resource | medium |
| `answer_state` | visibility diagnostics | deterministic rule on answer text + brand entities + competitors | low |
| `source_type` / `ecosystem_tag` | citation visibility | taxonomy-driven classification | medium-high |
| `scene` | question diagnostics | A3 + A2 deterministic mapping | medium |
| `pain_point` | question diagnostics | A3/A2 deterministic mapping | medium |
| `negative_source_type` | sentiment risk | deterministic attribution rule | medium-high |
| `logic_archetype` | platform profiling | deterministic profiling rule | medium-high |
| `comparison_bundle` | scenario reports | current scenario report + explicit panorama baseline | medium |

## 9. Upstream Preservation Rules

These rules should remain fixed during implementation.

1. Do not change A1 output names to satisfy the new report contract.
2. Do not rewrite A2 persona/scenario/pain-point schema just to satisfy A5.
3. Do not rewrite A3 producer protocol before the adapter proves it is needed.
4. Do not rewrite A4 fetch schema for canonical report convenience.
5. Put all canonical GEO normalization in the post-A4 adapter/analysis layer.

## 10. Terminology Rule

To stay aligned with the existing AGEO agent-first layering:

- `Public Skill` means orchestrator-visible capability such as
  `analysis_report_skill`
- `Internal Analyzer` means deterministic module inside A5 canonical analysis
- `Artifact` means persisted bundle for downstream report/dashboard/follow-up

If the payload key `skill_outputs` is kept to match the current GEO example
package, it should be interpreted as “internal analyzer outputs”, not as a list
of orchestrator-visible public skills.

## 11. Frozen Decisions That Affect Mapping

1. Canonical platform value is `yuanbao`.
2. Launch cleanup can remove brand shells and schedules, so long-lived legacy
   brand-level compatibility is not required.
3. Mapping may still use `Entity` metadata when present during the transition,
   but the canonical report design must not depend on preserving old entities
   after launch cleanup.
4. Canonical report transport type is `report`; `report_baseline` becomes a
   migration-only legacy alias.

## 12. Immediate Implementation Implications

1. Build `InputBundleAdapter` before any new GEO skill implementation.
2. Implement `hunyuan -> yuanbao` normalization at the adapter boundary before
   writing dashboard/report logic.
3. Keep the adapter deterministic and testable with fixture packs from the GEO
   docs.
4. Treat current report/dashboard/export code as consumers to be replaced, not
   as sources of truth.

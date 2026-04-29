# A5 Brand Decision Diagnosis System Design (2026-04-28)

> Status: Draft
> Scope: A5 report generation architecture, report artifact contract, diagnosis modules, validation rules
> Owner: AGEO / Specta AI

## 中文验收索引

本设计文档覆盖本次重构的核心目标：把 A5 从自动报告生成器升级为 AI 答案中的品牌决策诊断系统。

1. 一个 Artifact：每次 A5 仍只生成一个 `geo_report`，不引入两份 artifact 或用户可见版本概念。
2. 无信号兜底：`brand_presence_count == 0` 时进入 `NO_SIGNAL`，输出未进入诊断，不输出情感、官网承接、平台偏好和品牌口碑判断。
3. 场景地图：把旧问题类型升级为 `decision_scenario / journey_stage / business_value / brand_status`。
4. 来源证据权：把域名列表升级为品牌官网、官方文档、竞品官网、权威媒体、社区/UGC、百科、学术/医学、政府/监管、低质搬运和未知来源分类。
5. 风险分类：把旧负面信号重映射为价格门槛、交付复杂度、证据充分性、适配边界和竞争替代风险。
6. 性能约束：MVP 诊断模块默认使用确定性代码，不引入多个串行 LLM 调用阻塞 A4 到 A5。
7. 验收标准：每个核心模块都有专项 fixture、pytest 验证、问号乱码扫描、artifact 兼容检查和最终共享验证。

## 1. Core Goal

This optimization is not about making reports look better.

The goal is to upgrade Specta from:

```text
Automatic report generator
```

to:

```text
Brand decision diagnosis system inside AI answers
```

A5 should answer these questions:

1. Did the brand enter AI answers?
2. If it entered, was it the main recommendation, a companion brand, or replaced by competitors?
3. Which decision scenarios trigger brand presence, and which scenarios cause absence?
4. Which sources do AI answers rely on, and does the brand own the evidence chain?
5. Are AI concerns real reputation negatives, purchase barriers, fit boundaries, or competitor substitution risks?
6. What content assets should be built next, and how should the result be retested?

## 2. Non-Goals

This design does not try to:

1. Rebuild A1 / A2 / A3 / A4.
2. Change the existing core metric calculation logic unless a metric is mathematically invalid.
3. Create multiple report artifacts for one A5 run.
4. Add user-facing report versions such as `v1` and `v2`.
5. Make every internal skill an LLM call.
6. Replace future follow-up analysis or history query skills.

## 3. Design Principle

### Principle 1: Audit Data Before Generating Reports

Do not let an LLM write a full report directly from raw A4 answers.

A5 must first run:

```text
Data audit -> report mode routing -> allowed sections / blocked sections
```

Only then can report content be generated.

### Principle 2: No Information Means Diagnosis, Not Insight

When the monitored brand has zero mentions, A5 must not write sentiment analysis, official-site conversion, platform preference, or brand reputation conclusions.

It must switch to:

```text
Brand AI Answer Non-Entry Diagnosis
```

The core questions become:

1. Why did AI not mention the brand?
2. Did the current question set trigger knowledge-style answers rather than brand recommendation answers?
3. Did any competitors appear?
4. What should be sampled next?
5. Which decision scenarios should the brand enter first?

### Principle 3: Every Core Conclusion Uses Fact, Interpretation, Boundary, Action

Every core insight must be represented as:

```json
{
  "fact": "What the data says",
  "interpretation": "What this means",
  "boundary": "What this does not prove",
  "action": "What to validate or optimize next"
}
```

The report generation skill may write prose, but it must consume these structured insights rather than inventing conclusions from raw data.

### Principle 4: Recommendations Must Be Industry-Based, Scenario-Based, and Asset-Based

Do not output generic advice such as:

```text
Build brand definition pages, scenario pages, and comparison pages.
```

Output scenario-specific asset recommendations, for example:

```text
For the "digital transformation consulting selection" scenario, build a methodology page explaining how strategy consulting firms and system implementation vendors divide responsibilities. This asset should improve main recommendation rate and official-site citation conversion in comparison questions.
```

### Principle 5: One Artifact, Two Main Sections

Each A5 run generates one `geo_report` artifact.

The artifact must contain two main report sections:

1. Executive summary
   - One page.
   - For executives.
   - Focused on judgment, priority, and the most important actions.
2. Operations diagnosis
   - Full diagnosis.
   - For strategy, operations, content, and customer success teams.
   - Includes metrics, samples, sources, scenarios, risks, action list, and retest plan.

This is not two artifacts, not two versions, and not a user-facing versioning system.

## 4. Target Architecture

The new A5 should be a multi-skill diagnosis pipeline:

```text
Raw questions and AI answers
        ↓
MetricCalculatorSkill
        ↓
DataAuditSkill
        ↓
ReportRouterSkill
        ↓
ScenarioDiagnosisSkill
        ↓
SourceIntelligenceSkill
        ↓
RiskConcernClassifierSkill
        ↓
ActionRecommendationSkill
        ↓
ReportGenerationSkill
        ↓
ValidatorSkill
        ↓
AutoRepairSkill
        ↓
One geo_report artifact:
  - Executive summary
  - Operations diagnosis
```

Important distinction:

```text
Multi-Skill is the architecture.
Multi-Skill does not mean every step must be a separate LLM call.
```

Some skills should be deterministic code modules. Some can be LLM-assisted. All must have clear input and output contracts.

## 5. Skill Contract Overview

### 5.1 MetricCalculatorSkill

Purpose:

Preserve existing A5 metric calculation as much as possible.

Responsible for:

1. Brand visibility.
2. No-brand rate.
3. Competitor pressure.
4. Monitor-only rate.
5. Monitor-plus-competitor rate.
6. Official citation conversion.
7. Brand-related link penetration.
8. Platform-level answer counts.
9. Source counts.
10. Existing raw sentiment signal, before risk remapping.

This skill should stay fast and deterministic.

### 5.2 DataAuditSkill

Purpose:

Decide what the current data can and cannot support.

Output:

```json
{
  "report_mode": "NO_SIGNAL | WEAK_SIGNAL | BRAND_ENTRY | FULL_LANDSCAPE",
  "confidence": "low | medium | high",
  "allowed_sections": [],
  "blocked_sections": [],
  "not_judged": [],
  "reasons": [],
  "metric_eligibility": {}
}
```

Core rules:

1. If `brand_presence_count == 0`, report mode must be `NO_SIGNAL`.
2. If `brand_presence_count < 5`, report mode should be `WEAK_SIGNAL`.
3. If official citation denominator is 0, official-site conversion must be marked not judgeable.
4. If platform answer count is below the threshold, platform preference must be blocked.
5. If a metric denominator is 0, user-facing report text must explain why the metric cannot be judged.

### 5.3 ReportRouterSkill

Purpose:

Choose the report mode and section structure.

Report modes:

```text
NO_SIGNAL:
  Brand has not entered AI answers.
  Generate non-entry diagnosis.

WEAK_SIGNAL:
  Brand appears, but evidence is thin.
  Generate directional observations only.

BRAND_ENTRY:
  Brand has entered some answers.
  Diagnose entry, competitor co-presence, source ownership, and decision concerns.

FULL_LANDSCAPE:
  Data is sufficient for a complete panorama or scenario diagnosis.
```

### 5.4 ScenarioDiagnosisSkill

Purpose:

Upgrade from question type to customer decision scenario.

Input example:

```json
{
  "question_text": "Digital transformation project: should I hire a strategy consulting firm or Accenture-like implementation vendor?",
  "question_type": "comparison",
  "answer_state": "target_with_competitors"
}
```

Output example:

```json
{
  "question_type": "comparison",
  "decision_scenario": "Digital transformation consulting selection",
  "journey_stage": "supplier_evaluation",
  "business_value": "high",
  "brand_status": "target_with_competitors",
  "diagnosis": "The brand enters the strategy consulting shortlist but is compared against implementation vendors.",
  "content_gap": "Lacks authoritative explanation of strategy consulting vs system implementation responsibility boundaries.",
  "recommended_asset": "How strategy consulting firms and system implementation vendors divide responsibilities in digital transformation"
}
```

### 5.5 SourceIntelligenceSkill

Purpose:

Upgrade source analysis from domain listing to evidence ownership diagnosis.

Each source should be classified into one of:

1. Brand official site.
2. Official document / whitepaper.
3. Competitor official site.
4. Authoritative media.
5. Community / UGC.
6. Encyclopedia / knowledge base.
7. Academic / medical.
8. Government / regulator.
9. Low-quality scraper / content farm.
10. Unknown.

Output example:

```json
{
  "domain": "example.com",
  "source_type": "authoritative_media",
  "authority_score": 72,
  "brand_control_score": 0,
  "ai_citation_frequency": 16,
  "risk_level": "medium",
  "recommended_action": "External content partnership or PR governance"
}
```

Report output should not just say:

```text
douyin.com: 30 citations
jiemian.com: 16 citations
```

It should say:

```text
Current AI answers mainly rely on three source types:
1. Community / UGC: affects answer breadth, but authority is weak.
2. Industry media: affects brand explanation power and can be governed through PR.
3. Low-quality scraper sites: not worth direct investment, but should be monitored for answer pollution.
```

### 5.6 RiskConcernClassifierSkill

Purpose:

Replace shallow negative sentiment with decision-risk classification.

Old-to-new mapping:

| Old Category | New Category | Meaning |
|---|---|---|
| Negative | Risk concern | Affects decision, but may not damage brand reputation |
| Price negative | Price barrier | High cost, budget pressure |
| Usage complexity | Delivery complexity | Project cycle, organizational readiness |
| Information credibility | Evidence sufficiency | Whether cases, data, and methodology support the claim |
| Service inconvenience | Fit boundary | Whether the brand is suitable for a segment or use case |
| Competitor better fit | Competitive substitution risk | Competitor is preferred in a scenario |

Incorrect output:

```text
Brand negative mention rate is 71.4%, but negative information is not high.
```

Correct output:

```text
This round contains many decision concerns, mainly price barriers and project complexity. This does not necessarily mean negative brand reputation. It means AI answers tend to remind users to evaluate budget, organizational readiness, and project fit when recommending the brand.
```

### 5.7 ActionRecommendationSkill

Purpose:

Turn diagnosis into actionable content assets and retest plans.

Each recommendation must include:

```json
{
  "priority": "P0 | P1 | P2",
  "decision_scenario": "string",
  "fact": "string",
  "business_problem": "string",
  "recommended_asset": "string",
  "target_metric": [],
  "validation_plan": "string",
  "observation_cycle": "string"
}
```

Generic recommendations are invalid.

### 5.8 ReportGenerationSkill

Purpose:

Generate the final report prose from structured diagnosis modules.

Constraints:

1. It cannot generate blocked sections.
2. It cannot display `N/A`.
3. It must preserve the report mode chosen by `ReportRouterSkill`.
4. It must write one artifact with two main sections: executive summary and operations diagnosis.
5. It must not invent evidence not present in upstream modules.

### 5.9 ValidatorSkill

Purpose:

Prevent logically invalid reports from being delivered.

Hard rules:

1. User-facing report markdown must not contain `N/A`.
2. If `brand_presence_count == 0`, report must not include sentiment, official-site conversion, platform preference, or brand reputation conclusions.
3. If `negative_rate > 0.5`, report must not say negative information is low.
4. If sample size is too low, report must not use strong claims such as stable, significant, clearly better, or best platform.
5. Every action recommendation must include fact, action, target metric, and validation plan.
6. Report sections must match the selected report mode.

### 5.10 AutoRepairSkill

Purpose:

Apply Validator fixes before artifact writeback.

Auto-repair examples:

1. Replace `official citation conversion N/A` with a business-language explanation.
2. Remove sentiment section from `NO_SIGNAL` reports.
3. Rewrite negative sentiment claims into decision-concern language.
4. Downgrade small-sample platform preference claims into observation or retest suggestions.

## 6. No-Information Fallback Strategy

This section is mandatory and P0.

### 6.1 Never Display N/A Directly

Incorrect:

```text
Official-site citation conversion: N/A.
Brand negative mention rate: N/A.
```

Correct:

```text
This round has no monitored-brand mention samples, so official-site citation conversion cannot be calculated. The priority is not weak official-site conversion; the priority is that the brand has not entered AI answers yet.
```

### 6.2 NO_SIGNAL Report Structure

When `brand_presence_count == 0`, the operations diagnosis must switch to:

```text
# Brand AI Answer Non-Entry Diagnosis

## 1. This Round's Conclusion
- Whether the brand entered AI answers.
- No-brand answer rate.
- Whether any competitors appeared.
- What cannot be judged yet.

## 2. Question Trigger Types
- Which questions triggered knowledge-style answers.
- Which questions may trigger brand recommendation answers.
- Which questions require resampling.

## 3. Occasional Competitor Entry
- Which competitors appeared.
- Whether they were actively recommended or only mentioned in passing.
- Whether this constitutes competitor pressure.

## 4. Content Gap Hypotheses
- Safety / compliance gap.
- Audience-fit gap.
- Price-rationale gap.
- Comparison-explanation gap.
- Purchase-channel gap.

## 5. Next-Round Validation Plan
- Which new questions to add.
- How many questions per scenario.
- Which metrics to observe.
- Which threshold unlocks a fuller report.

## 6. Not Judged
- Sentiment.
- Official-site conversion.
- Platform preference.
- Brand reputation.
```

### 6.3 Allowed and Forbidden NO_SIGNAL Conclusions

Allowed:

```text
The only stable conclusion is that the brand did not enter this round of AI answers.
```

Allowed:

```text
The current question set is more likely to trigger knowledge-style answers than brand recommendation answers.
```

Forbidden:

```text
The brand's negative information ratio is low.
```

Forbidden:

```text
Official-site conversion is weak.
```

Reason:

If there are no brand mentions, official-site conversion and brand sentiment do not have valid denominators.

## 7. Question Scenario Map

### 7.1 Upgrade Question Types Into Decision Scenarios

Current question labels such as comparison, how-to-choose, scenario, and trend are useful but not business-specific enough.

A5 should upgrade each question to:

```json
{
  "question_type": "comparison",
  "decision_scenario": "Digital transformation consulting selection",
  "journey_stage": "supplier_evaluation",
  "business_value": "high",
  "brand_status": "target_with_competitors"
}
```

### 7.2 Management Consulting Scenario Taxonomy

| Decision Scenario | Typical Question | Business Meaning |
|---|---|---|
| Top-tier consulting firm comparison | How to choose McKinsey, BCG, and Bain | Brand shortlist |
| Digital transformation selection | Strategy consulting vs Accenture-style implementation | Business boundary competition |
| Manufacturing cost reduction | How to measure operations optimization ROI | Concrete service opportunity |
| Mid-sized company organization redesign | Which consultant fits limited budget | Segment fit |
| M&A due diligence | What does M&A consulting include | High-value service line |
| PMI integration | What happens if PMI is skipped | High-value service line |
| ESG sustainability | Is ESG consulting practical | Trend-topic mindshare |
| Economic downturn cycle | What consulting services companies still buy | Macro viewpoint influence |

### 7.3 Healthcare Supplement Scenario Taxonomy

| Decision Scenario | Typical Question | Business Meaning |
|---|---|---|
| Elderly nutrition | How to choose protein powder for elders | Family gift / care purchase |
| Child nutrition | Are children's vitamins necessary | Safety and long-term-use concern |
| Ingredient comparison | Natural vitamin C vs synthetic vitamin C | Price rationale |
| Safety and compliance | Blue-hat certification, overseas purchasing safety | Trust barrier |
| Fatigue and late-night work | Liver support, B vitamins, fatigue relief | Scenario demand |
| Direct-selling trust | Direct-selling brands vs pharmacy brands | Channel trust |
| Budget selection | What to buy for parents with 500 RMB | Purchase decision |

### 7.4 Reporting Requirement

Do not only say:

```text
Trend questions did not mention the brand.
```

Say:

```text
The ESG sustainability scenario belongs to trend-topic mindshare. This round mainly triggered viewpoint explanations rather than vendor recommendations, so brand absence here should be treated as a topic-authority gap rather than direct brand weakness.
```

## 8. Source Intelligence and Evidence Ownership

### 8.1 Problem

Current reports can list many `other` sources. This has little action value.

The source module must answer:

1. Which source types are shaping AI answers?
2. Which sources does the brand control?
3. Which sources are competitor-controlled?
4. Which external sources are worth governing?
5. Which low-quality sources may pollute answers?

### 8.2 Source Classification

| Source Type | Rule | Recommended Action |
|---|---|---|
| Brand official site | Main domain belongs to target brand | Optimize structured content |
| Official document / whitepaper | Brand PDF, report, research page | Convert to HTML, summarize, make citation-ready |
| Competitor official site | Domain belongs to competitor | Build differentiated comparison content |
| Authoritative media | Finance, industry, professional media | PR partnership or content distribution |
| Community / UGC | Douyin, Zhihu, Xiaohongshu, forums | Reputation governance |
| Encyclopedia / knowledge base | Baike, MBA knowledge base, industry entries | Entry governance |
| Academic / medical | PubMed, journals, hospital content | Priority for healthcare and supplement categories |
| Government / regulator | Regulators, standard libraries | Compliance proof |
| Low-quality scraper | Document sites, collection sites, content farms | Low priority, monitor pollution |
| Unknown | No rule yet | Wait for taxonomy enrichment |

### 8.3 Source Scoring

Each domain should support:

```json
{
  "domain": "example.com",
  "source_type": "authoritative_media",
  "authority_score": 72,
  "brand_control_score": 0,
  "ai_citation_frequency": 16,
  "risk_level": "medium",
  "recommended_action": "External content partnership or PR governance"
}
```

### 8.4 Report Output Requirement

The report should summarize source meaning, not just domain counts:

```text
Current AI answers mainly rely on three source types:
1. Community / UGC: affects answer breadth, but authority is weak.
2. Industry media: affects brand explanation power and can be governed through PR.
3. Low-quality scraper sites: not worth direct investment, but should be monitored for answer pollution.
```

## 9. Risk and Concern Classification

### 9.1 Problem

The current report can classify price, complexity, and fit boundaries as negative sentiment.

For premium professional-service brands such as BCG, "expensive" is not always negative. It may be part of positioning.

### 9.2 New Classification

| Old Category | New Category | Explanation |
|---|---|---|
| Negative | Risk concern | Affects decision, but not necessarily brand reputation |
| Price negative | Price barrier | High fee, budget pressure |
| Usage complexity | Delivery complexity | Project cycle, internal readiness |
| Information credibility | Evidence sufficiency | Cases, data, methodology support |
| Service inconvenience | Fit boundary | Whether suitable for SMEs or a segment |
| Competitor better fit | Competitive substitution risk | Competitor is more suitable in a scenario |

### 9.3 Output Logic

Incorrect:

```text
Brand negative mention rate is 71.4%, but negative information is not high.
```

Correct:

```text
This round contains many decision concerns, mainly price barriers and project complexity. This does not necessarily mean negative brand reputation. It means AI answers tend to remind users to evaluate budget, organizational readiness, and project fit when recommending the brand.
```

## 10. Artifact Contract

Each A5 run writes one artifact.

Recommended shape:

```json
{
  "artifact_kind": "geo_report",
  "report_kind": "panorama | scenario",
  "report_mode": "NO_SIGNAL | WEAK_SIGNAL | BRAND_ENTRY | FULL_LANDSCAPE",
  "title": "Brand GEO Diagnosis Report",
  "metric_bundle": {},
  "data_audit": {},
  "report_route": {},
  "scenario_diagnostics": {},
  "source_intelligence": {},
  "risk_concern_analysis": {},
  "action_recommendations": [],
  "executive_summary": {
    "section_title": "Executive Summary",
    "one_line_judgment": "",
    "key_findings": [],
    "top_actions": [],
    "not_judged": []
  },
  "operations_diagnosis": {
    "section_title": "Operations Diagnosis",
    "sections": []
  },
  "validator_result": {},
  "report_markdown": ""
}
```

The `report_markdown` should be assembled from structured modules, not treated as the source of truth.

Follow-up analysis, history query, dashboard, and export should consume structured modules first and markdown only as a display/export fallback.

## 11. Performance Design

A4 to A5 must not become slow.

Performance principles:

1. Metric calculation, data audit, report routing, basic source taxonomy, basic risk classification, and Validator should be code-first.
2. Scenario diagnosis and action recommendation may be LLM-assisted only where deterministic rules are insufficient.
3. Any LLM-assisted skill must have timeout and fallback.
4. The synchronous A5 path must not require one LLM call per internal skill.
5. Heavy source scoring or industry taxonomy enrichment can be added later, but the first report must still be usable without it.

In short:

```text
Fast path: deterministic diagnosis and valid report.
Deep path: optional enrichment through the same artifact structure.
```

The user-facing product still remains one artifact, not multiple report versions.

## 12. Compatibility With Follow-Up and History Skills

This design must not conflict with:

1. Post-analysis follow-up skills.
2. Historical query.
3. Historical comparison.
4. Dashboard aggregation.
5. Export.
6. Future deep-dive skills.

Rules:

1. Future skills must read the structured artifact modules, not parse markdown.
2. Future skills may add module-level enrichment, but must not bypass `DataAuditSkill` and `ReportRouterSkill`.
3. History comparison must compare stable fields such as `report_mode`, `metric_bundle`, `scenario_diagnostics`, `source_intelligence`, and `risk_concern_analysis`.
4. Follow-up analysis must respect `not_judged` and must not generate conclusions blocked in the original data audit.
5. Dashboard should show the same diagnosis contract as the report artifact, not reconstruct its own conclusions from raw fields.

## 13. Implementation Mapping

Current relevant files:

1. `aeo-platform/backend/app/workflow/nodes_a5.py`
   - A5 executor orchestration and artifact writeback.
2. `aeo-platform/backend/app/workflow/a5/canonical.py`
   - Current deterministic report contract and section builders.
3. `aeo-platform/backend/app/workflow/a5/metrics.py`
   - Shared metric helpers.
4. `aeo-platform/backend/app/workflow/a5/postprocess.py`
   - Fallback report generation and user-facing safety.
5. `aeo-platform/backend/app/workflow/a5/sanitizer.py`
   - User-facing copy cleanup.
6. `aeo-platform/backend/skill_packages/analysis-report/SKILL.md`
   - Public analysis report skill guidance.

Recommended first implementation slice:

1. Add `DataAuditSkill` and `ReportRouterSkill` as deterministic modules under `app/workflow/a5/`.
2. Add `report_mode`, `data_audit`, and `report_route` to the canonical artifact.
3. Add `NO_SIGNAL` section builder.
4. Add N/A translation and blocked-section enforcement.
5. Add risk/concern remapping structure.
6. Add Validator hard rules before artifact writeback.
7. Update tests for no-signal and high-risk cases.

## 14. MVP Priority

P0:

1. Data audit.
2. Report mode routing.
3. NO_SIGNAL report structure.
4. N/A ban and translation.
5. Blocked sections.
6. Risk concern remapping.
7. Validator hard rules.

P1:

1. Scenario map for management consulting and healthcare supplements.
2. Structured action recommendations.
3. One artifact with executive summary and operations diagnosis.

P2:

1. Source taxonomy expansion.
2. Source scoring.
3. Retest plan generation.
4. Follow-up/history binding to new structured modules.

## 15. Acceptance Criteria

The implementation is acceptable only if:

1. When brand mentions are zero, the report switches to non-entry diagnosis.
2. User-facing markdown does not contain `N/A`.
3. When brand mentions are zero, the report does not include sentiment, official-site conversion, platform preference, or brand reputation conclusions.
4. A high decision-concern rate is not described as "negative information is low".
5. Price and complexity concerns are classified as purchase barrier or delivery complexity where appropriate.
6. Recommendations are scenario-based, asset-based, metric-linked, and retestable.
7. Each A5 run writes one `geo_report` artifact.
8. The artifact contains both executive summary and operations diagnosis.
9. Follow-up/history features can consume structured artifact modules without parsing markdown.
10. The A4-to-A5 main path remains fast because deterministic modules handle the required diagnosis before any optional LLM enrichment.

## 16. Final Decision

A5 should not be patched as a prettier report template.

It should be rebuilt as a multi-skill diagnosis pipeline whose durable output is one report artifact with:

1. Executive summary.
2. Operations diagnosis.
3. Structured diagnosis modules.
4. Validator result.

This is the architecture needed for Specta to become a brand decision diagnosis system inside AI answers.

## 17. Implementation Progress Review

Review date: 2026-04-29.

Implementation branch and worktree:

1. Worktree: `D:\AGEO-worktrees\a5-decision-diagnosis-doc`
2. Branch: `codex/a5-decision-diagnosis-doc`

### 17.1 Status by Design Area

| Design area | Status | Implementation evidence | Validation evidence |
| --- | --- | --- | --- |
| Core goal: upgrade A5 from report generator to brand decision diagnosis system | Completed for A5 artifact generation | `app/workflow/a5/diagnosis.py`, `app/workflow/a5/canonical.py` now audit data, route report mode, build structured diagnosis modules, and assemble a diagnosis report | `test_a5_decision_diagnosis.py` covers no-signal, weak-signal, brand-entry, and full-landscape paths |
| One Artifact contract | Completed | Canonical still writes one `artifact_kind=geo_report`; no public version concept or second artifact was added | Canonical artifact tests assert single `geo_report` contract and structured report fields |
| `executive_summary` structured object | Completed | `executive_summary` is now an object with `section_title`, `one_line_judgment`, `key_findings`, `top_actions`, and `not_judged`; `executive_summary_text` remains for old consumers | Validator checks structured object and compatibility string; frontend `tsc --noEmit` passed |
| Two main report sections inside one Artifact | Completed | Added `report_sections` with `executive_summary` and `operations_diagnosis`; old `sections` remains compatibility data | Tests assert `report_sections` contains exactly the two main section names |
| Data audit and report routing | Completed | `build_data_audit()` and `build_report_route()` implement `NO_SIGNAL`, `WEAK_SIGNAL`, `BRAND_ENTRY`, `FULL_LANDSCAPE` | Tests assert zero brand mentions always route to `NO_SIGNAL` and blocked sections are present |
| No-signal fallback | Completed | `NO_SIGNAL` markdown switches to "品牌 AI 答案未进入诊断报告" with the six fixed operations sections | Tests assert the six headings and absence of raw `N/A`, official-conversion conclusions, and negative-rate copy |
| Non-NO_SIGNAL report generation | Completed for deterministic MVP | `build_structured_report()` now assembles all modes from structured modules instead of appending diagnosis text to old markdown | Tests cover all four modes and `diagnostic_conclusions` four-field completeness |
| Fact / interpretation / boundary / action | Completed for generated core conclusions | `diagnostic_conclusions[]` requires `fact`, `interpretation`, `boundary`, and `action`; markdown renders these fields | Validator and tests enforce the four required fields |
| Risk and concern remapping | Completed for current categories | Negative topics are remapped into price barrier, delivery complexity, evidence sufficiency, fit boundary, competitive substitution risk | High-concern BCG fixture asserts these labels and blocks "negative information is low" style copy |
| Source evidence intelligence | Completed for MVP | `source_taxonomy.json` drives official, white paper, competitor, media, UGC, encyclopedia, academic/medical, regulator, low-quality, and unknown classes | Source tests assert PubMed, Douyin, copied-doc, Baike and fallback classification |
| Decision scenario map | Completed for MVP | `scenario_taxonomy.json` drives management consulting and healthcare supplement scenarios; code keeps fallback rules | Scenario tests assert consulting and supplement scenarios and fallback when config is unavailable |
| Validator to AutoRepair to Validator loop | Completed for deterministic repair scope | Canonical writeback runs validate, deterministic repair, then validate again; unrecoverable missing structure still fails | Repair tests assert copy issues are fixed and missing core structures are not silently invented |
| Downstream history / follow-up compatibility | Completed for current backend contract | Added `extract_geo_report_diagnosis()`, `is_geo_report_topic_judged()`, and `require_geo_report_topic_judged()`; dashboard extraction includes diagnosis modules; orchestrator context reads structured executive text and not-judged policy | Tests assert dashboard projection exposes diagnosis modules and follow-up topics blocked by `not_judged` return a deterministic fallback action |
| Frontend export / dashboard compatibility | Completed for type and export helpers | Canvas data types accept structured executive summary; report view, Markdown export, and PDF template use a helper to extract one-line judgment | Frontend ESLint on touched files and `npx tsc --noEmit` passed |
| Performance constraint | Completed for MVP design | All new diagnosis modules are deterministic JSON/rule processing; no additional synchronous LLM calls were introduced | Existing A5 tests and validate flow run without external LLM dependency |

### 17.2 Priority Completion

P0 completion: complete.

Evidence:

1. Data audit and report mode routing are implemented.
2. `NO_SIGNAL` structure is implemented.
3. Raw `N/A` is blocked and repairable.
4. No-signal blocked sections are enforced in user-facing markdown.
5. Risk concern remapping is implemented.
6. Validator hard rules run before artifact writeback.

P1 completion: complete for current deterministic scope.

Evidence:

1. Management consulting and healthcare supplement scenario taxonomy are configured.
2. Recommendations are structured by scenario, fact, asset, metric, and validation plan.
3. One artifact contains structured executive summary and operations diagnosis.
4. Non-no-signal modes now use structured report generation.

P2 completion: substantially complete for code-level contract.

Evidence:

1. Source taxonomy and scoring defaults are configuration-driven.
2. Retest plan generation is included.
3. Dashboard/export/history helpers can consume structured fields.
4. Follow-up skills now have a deterministic topic policy helper so blocked subjects do not require markdown parsing.
5. Orchestrator context includes the structured `not_judged` policy in report evidence summaries.

Remaining P2 work:

1. Expand taxonomy beyond the current management consulting and healthcare supplement MVP.
2. Add richer source authority scoring rules and externalized governance for taxonomy editing.
3. Add product-level historical comparison screens over `scenario_diagnostics`, `source_intelligence`, and `risk_concern_analysis`.

### 17.3 Final Completion Estimate

Overall design completion: about 93 percent.

Completed:

1. Core A5 diagnosis architecture.
2. Structured artifact contract.
3. All report modes.
4. No-signal fallback.
5. Risk concern remapping.
6. Source evidence intelligence MVP.
7. Scenario taxonomy MVP.
8. Validator and deterministic AutoRepair loop.
9. Frontend/export compatibility for structured executive summary.
10. Downstream diagnosis helper and `not_judged` policy enforcement for backend consumers.

Partially completed:

1. Source and scenario taxonomy are configurable files, not a managed taxonomy product.
2. Dashboard consumes structured diagnosis modules where available, but existing legacy dashboard boards still keep compatibility logic.
3. Historical comparison has stable fields and helpers, but no dedicated product screen was added in this implementation.

Not in this implementation scope:

1. Database-managed taxonomy editing.
2. Deployment.
3. Optional deep LLM enrichment.
4. Full historical trend analysis over multiple A5 artifacts.

### 17.4 Validation Evidence

Commands completed:

1. `python -m pytest aeo-platform/backend/tests/test_a5_decision_diagnosis.py aeo-platform/backend/tests/test_nodes_a5_error_path.py -q`
2. `python -m ruff check` on modified backend files and the A5 test file.
3. `python -m compileall` on modified backend files.
4. `npm run lint -- src/types/canvas.ts src/hooks/websocket/canvas.ts src/components/canvas/contents/ReportContent.tsx src/lib/canvasExportShared.ts src/lib/pdfExportTemplate.tsx`
5. `npx tsc --noEmit --pretty false`

Latest added validation:

1. A5 diagnosis tests now include 17 cases, including dashboard structured-module exposure, follow-up topic policy blocking, and orchestrator not-judged summary.
2. Final shared validation and question-mark corruption scanning were run after this review was added. The shared validator passed with existing frontend lint warnings only, and no question-mark corruption was found in changed files.

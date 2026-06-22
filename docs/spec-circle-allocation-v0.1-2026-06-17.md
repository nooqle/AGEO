# Spec: Brand Circle Allocation v0.1

> Date: 2026-06-17  
> Status: Phase 0 freeze candidate  
> Applies to: Graph Patch generation, Graph Update Queue, Report strategic segmentation  
> PRD reference: `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md`

## 1. Purpose

This spec defines how an extracted entity or relationship becomes a circle placement proposal.

The algorithm must be explainable. It must not use mention count alone as proof of positive association.

## 2. Inputs

Required inputs:

- `EntityRelationSet`: extracted entities, relations, evidence refs, polarity, confidence.
- `BrandCircleGraph`: current graph version and existing zone placement.
- `EntityLexicon`: known brand, product, category, audience, scene, risk, competitor, alias rules.
- `GraphUpdateHistory`: previous graph updates for stability and migration checks.
- `PlatformFetchPlan`: platforms configured for the current run.

Default v1 supported fetch platforms:

- `doubao`
- `yuanbao`
- `kimi`
- `deepseek`

`zhipu` and `chatgpt` are future adapter slots unless backend fetch support is explicitly added.

## 3. Output

```ts
type CircleZone =
  | "center"
  | "inner"
  | "middle"
  | "outer"
  | "risk"
  | "competitor"
  | "pending_review";

type ScoreBreakdown = {
  platformCoverageScore: number;
  mentionFrequencyScore: number;
  explicitAssociationScore: number;
  contextRelevanceScore: number;
  evidenceQualityScore: number;
  sentimentOrRiskScore: number;
  stabilityScore: number;
  connectionStrength: number;
};

type CircleAllocationResult = {
  entityId: string;
  relationId?: string;
  proposedZone: CircleZone;
  previousZone?: CircleZone;
  scoreBreakdown: ScoreBreakdown;
  vetoReasons: string[];
  reviewRequiredReasons: string[];
  evidenceRefIds: string[];
};
```

`CircleAllocationResult` is not a graph write. It becomes one or more `GraphPatch` records.

## 4. Rule Order

Circle allocation must run in this order:

1. Classify risk, competitor, sentiment, and regulatory context.
2. Apply one-vote veto and review gates.
3. Calculate `connection_strength`.
4. Decide proposed zone.
5. Route to `auto_applied`, `needs_review`, `blocked`, or `conflict`.
6. Write score breakdown and evidence refs into the patch.

## 5. Connection Strength Formula

`connection_strength` is a `0-100` score. Each dimension returns a weighted point contribution. The sum is the final score.

| Dimension | Max points | Calculation |
| --- | ---: | --- |
| `platform_coverage_score` | 20 | `min(unique_platforms / target_platform_count, 1) * 20` |
| `mention_frequency_score` | 15 | Bucketed by evidence span count across unique answers |
| `explicit_association_score` | 20 | Direct brand/product/scene relation strength |
| `context_relevance_score` | 15 | Match with lexicon type and intended brand context |
| `evidence_quality_score` | 10 | Quality of evidence source, span clarity, and provenance |
| `sentiment_or_risk_score` | 10 | Polarity and risk safety score |
| `stability_score` | 10 | Repeated appearance across Graph Updates |

### 5.1 Platform Coverage

Use the configured platforms for this Board Run as denominator. If missing, use the v1 default four-platform set.

```text
platform_coverage_score = round(min(unique_platforms / target_platform_count, 1) * 20)
```

Rules:

- Count only successful answers with an evidence span.
- Multiple answers from the same platform count once.
- Platform failure does not reduce the score below the achieved coverage; it is recorded separately as run quality.

### 5.2 Mention Frequency

Count evidence spans across unique `question_id + platform` answers.

| Evidence span count | Points |
| ---: | ---: |
| 0 | 0 |
| 1-2 | 4 |
| 3-5 | 8 |
| 6-10 | 12 |
| 11+ | 15 |

Safeguard:

- One question can contribute at most two spans to this dimension.
- Negative or questioning spans still count for frequency, but sentiment vetoes can prevent positive zone placement.

### 5.3 Explicit Association

| Condition | Points |
| --- | ---: |
| No explicit relation, only co-mention | 0 |
| Same category or loose context | 8 |
| Explicit relation to product, audience, or scenario | 14 |
| Explicit positive relation to brand-owned product, solution, or scenario | 20 |

`competes_with` and `risk_of` do not increase positive association.

### 5.4 Context Relevance

| Condition | Points |
| --- | ---: |
| Entity conflicts with lexicon or run scope | 0 |
| Related category but weak scenario fit | 5 |
| Matches target category or audience | 10 |
| Matches target category, audience, and scenario | 15 |

### 5.5 Evidence Quality

| Condition | Points |
| --- | ---: |
| No usable evidence span | 0 |
| Short span with platform/question only | 3 |
| Clear span with question, platform, and answer asset | 7 |
| Clear span plus source reference or user-uploaded source | 10 |

### 5.6 Sentiment Or Risk

| Evidence profile | Points |
| --- | ---: |
| Negative majority or explicit risk context | 0-2 |
| Questioning majority | 3-4 |
| Mixed or neutral majority | 5 |
| Positive majority with no risk trigger | 6-8 |
| Strong positive majority across platforms | 9-10 |

This dimension is both a score and a veto input.

### 5.7 Stability

| History | Points |
| --- | ---: |
| New in this run | 0 |
| Appeared in previous update but unstable zone | 4 |
| Two consecutive updates with same positive class | 7 |
| Three or more consecutive updates with stable positive class | 10 |

## 6. Veto Rules

These rules run before zone assignment:

1. `sentiment_or_risk_score < 3/10`: entity cannot enter inner or middle circle.
2. `sentiment_or_risk_score >= 3/10 and < 5/10`: entity cannot enter inner circle.
3. `< 5/10` plus negative or questioning evidence majority: entity must enter risk layer or pending review.
4. Inner circle requires `sentiment_or_risk_score >= 6/10` and positive evidence majority.
5. Grey-zone movement into inner circle requires two consecutive positive Graph Updates.
6. Regulatory, pyramid-scheme, scam, exaggerated-efficacy, pricing-dispute, and trust-risk entities cannot be promoted by connection strength alone.
7. Competitor entities cannot enter inner circle.
8. Human review decisions override later automatic upgrades unless a new review decision supersedes them.

## 7. Zone Assignment

Forced zones are evaluated before strength-based zones.

| Zone | Default rule |
| --- | --- |
| `center` | Current brand entity |
| `risk` | `entity_type = risk`, `risk_of`, risk score >= 60, or user marked risk |
| `competitor` | `entity_type = competitor` or `competitor_pressure >= 60` |
| `inner` | `connection_strength >= 75`, platform coverage >= 3, source count >= 8, no veto |
| `middle` | `connection_strength 45-74`, or platform coverage >= 2, no middle veto |
| `outer` | Target entity with `connection_strength < 45`, or low source count |
| `pending_review` | New entity, conflicting entity, low confidence, grey-zone sentiment, alias uncertainty |

## 8. Migration Rules

1. Inner/middle migration requires two consecutive Graph Updates meeting the new zone condition.
2. Risk and competitor zones have priority over inner/middle/outer.
3. User accepted placement can be changed only by a later reviewable patch.
4. Every migration patch must include score breakdown and evidence refs.
5. Risk entities cannot become positive brand assets through platform coverage, frequency, or stability alone.

## 9. Auto-Apply Boundary

Auto-apply is allowed only for low-risk field updates:

| Patch type | Auto-apply | Rule |
| --- | --- | --- |
| `source_count` update | Yes | Count increase only, no zone change |
| `last_seen_at` update | Yes | Timestamp update only |
| `connection_strength` micro update | Yes | Relative change < 10%, no zone change |
| `platform_coverage` update | Yes | No risk or competitor trigger |
| New entity | No | Needs review or pending layer |
| Circle migration | No | Needs review |
| New risk relation | No | Needs review |
| New competitor relation | No | Needs review |
| Alias merge | No | Except exact approved lexicon alias |
| Human-reviewed object reclassification | No | Conflict or superseded |

## 10. Required Tests

Minimum backend tests:

- Positive high-score entity enters inner only when sentiment score and evidence majority pass.
- Entity with `sentiment_or_risk_score = 4` cannot enter inner even with high connection strength.
- Negative/questioning majority with high frequency enters risk or pending review.
- Same-category competitor co-mention does not create competitor zone.
- Explicit substitute evidence creates competitor candidate, review required.
- Regulatory or scam-related entity cannot be promoted by connection strength.
- Micro strength update auto-applies only when no zone migration occurs.
- Two consecutive updates are required for grey-zone inner upgrade.

# Spec: Entity Relation Extraction v0.1

> Date: 2026-06-17  
> Status: Phase 0 freeze candidate  
> Applies to: Entity Extraction node, Graph Patch Set generation, Trace Chain  
> PRD reference: `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md`

## 1. Purpose

This spec defines how raw AI answers become structured entity relations.

The extraction node must not be a black box. Every relation that can affect the graph must preserve question, platform, answer asset, evidence span, confidence, and polarity.

## 2. Inputs

```text
AnswerSet[]
EntityLexicon
BrandSeed
relation_type_taxonomy
PlatformFetchPlan
```

## 3. Outputs

```text
EntityRelationSet
GraphPatchSet
Extraction Asset
```

All node outputs must use the shared envelope:

```ts
type NodeObjectEnvelope<T> = {
  object_type: string;
  schema_version: string;
  brand_id: string;
  board_id: string;
  run_id: string;
  node_run_id: string;
  created_at: string;
  asset_ref?: string;
  provenance_refs: string[];
  payload_hash: string;
  payload: T;
};
```

## 4. EntityRelationSet Schema

```ts
type EntityType =
  | "brand"
  | "product"
  | "category"
  | "audience"
  | "scenario"
  | "strategic_word"
  | "risk"
  | "competitor"
  | "source"
  | "unknown";

type RelationType =
  | "associated_with"
  | "belongs_to"
  | "solution_for"
  | "audience_for"
  | "scenario_for"
  | "competes_with"
  | "risk_of"
  | "evidence_for"
  | "target_gap";

type EvidencePolarity = "positive" | "neutral" | "questioning" | "negative";

type ExtractedEntity = {
  id: string;
  canonicalName: string;
  entityType: EntityType;
  aliases: string[];
  lexiconEntityId?: string;
  confidence: number;
  reviewStatus: "auto_matched" | "new_candidate" | "needs_review" | "rejected";
};

type ExtractedRelation = {
  id: string;
  sourceEntityId: string;
  targetEntityId: string;
  relationType: RelationType;
  confidence: number;
  polarity: EvidencePolarity;
  triggerTerms: string[];
  evidenceRefIds: string[];
  extractionReason: string;
};

type EntityEvidenceRef = {
  id: string;
  questionId: string;
  questionText: string;
  platform: "doubao" | "yuanbao" | "kimi" | "deepseek" | "zhipu" | string;
  answerArtifactId: string;
  spanStart?: number;
  spanEnd?: number;
  excerpt: string;
  polarity: EvidencePolarity;
  sourceReferenceIds: string[];
};

type EntityRelationSet = {
  entities: ExtractedEntity[];
  relations: ExtractedRelation[];
  evidenceRefs: EntityEvidenceRef[];
  targetGaps: Array<{
    lexiconEntityId: string;
    expectedEntityName: string;
    gapReason: string;
  }>;
  extractionStats: {
    answerCount: number;
    entityCount: number;
    relationCount: number;
    riskSignalCount: number;
    competitorCandidateCount: number;
    needsReviewCount: number;
  };
};
```

## 5. Relation Taxonomy

| `relation_type` | Meaning |
| --- | --- |
| `associated_with` | Entity is associated with brand or another entity |
| `belongs_to` | Entity belongs to a brand, product line, or category |
| `solution_for` | Product or brand solves a need, problem, or occasion |
| `audience_for` | Entity maps to an audience group |
| `scenario_for` | Entity maps to a usage or purchase scenario |
| `competes_with` | Entity forms substitute or comparison pressure |
| `risk_of` | Entity points to risk, misunderstanding, controversy, or trust issue |
| `evidence_for` | Source entity supports another relation |
| `target_gap` | Brand target entity was not picked up by AI answers |

## 6. Extraction Workflow

The node runs these steps:

1. Normalize `AnswerSet` by platform, question, language, capture time, and artifact id.
2. Segment each answer into evidence candidate spans.
3. Recall known entities using `EntityLexicon` canonical names and aliases.
4. Extract new candidate entities from spans with an LLM-assisted extractor.
5. Normalize candidates against aliases and known entity ids.
6. Classify relations using the taxonomy above.
7. Classify evidence polarity: positive, neutral, questioning, negative.
8. Detect risk context and competitor comparison context.
9. Disambiguate entities and decide `reviewStatus`.
10. Produce `EntityRelationSet`.
11. Produce `GraphPatchSet` proposals; do not directly write graph state.

## 7. Entity Recognition Rules

Use a hybrid method:

- Lexicon matching is deterministic and runs first.
- LLM extraction can add new candidate entities only with evidence span refs.
- New candidates without span refs are dropped.
- Candidate entities with confidence `< 0.6` enter `needs_review`.
- Strategic target words from the lexicon must be represented even when absent; absence becomes `target_gap`.

## 8. Risk Detection Rules

Risk candidates are generated when any condition is true:

1. `EntityLexicon.entity_type = risk`.
2. Risk keyword set matches the span.
3. Negative polarity plus explicit brand association.
4. Questioning polarity plus high-frequency co-occurrence.
5. Extracted relation is `risk_of`.

Risk keyword examples include regulatory, pyramid-scheme, scam, exaggerated-efficacy, pricing-dispute, and trust-risk language.

Rules:

- Risk entities stay visible by default in graph and report surfaces.
- Risk relation must retain evidence span, question, platform, and answer asset.
- Risk relation cannot be converted into positive brand association by later scoring.

## 9. Competitor Detection Rules

`competes_with` requires explicit decision context. Same-category mention is not enough.

Valid triggers:

- Substitute or alternative recommendation.
- Explicit comparison, superiority, inferiority, pricing, efficacy, audience fit, or buying decision context.
- Answer recommends another brand instead of the current brand for the same scenario.

Invalid trigger:

- Same-category co-mention without substitution or decision signal.

Confidence routing:

- `confidence < 0.7`: pending review only.
- `confidence >= 0.7` plus explicit substitute/recommendation evidence: competitor candidate patch, still review-required.

Each competitor relation must record:

- Competitor name.
- Replaced brand/product/scenario when present.
- Question id and text.
- Platform.
- Answer excerpt.
- Trigger terms.
- Confidence.

## 10. Sentiment And Polarity Rules

1. Every evidence ref must have one polarity.
2. Mention is not recognition.
3. Positive validation requires positive evidence majority.
4. Strategic words can be `mentioned_with_risk` or `questioned`; they cannot all be reported as validated.
5. The extractor must output a short `extractionReason` for polarity and relation classification.

## 11. Disambiguation Rules

1. Exact approved alias match can auto-merge into the lexicon entity.
2. High similarity without exact alias enters `needs_review`.
3. Competitor names, risk terms, and brand-owned sub-assets are not silently merged.
4. Every merge preserves original mention text and source asset.
5. Alias merge patches are never auto-applied unless the alias was already approved in the lexicon.

## 12. Quality Gates

Extraction fails or enters review when:

- Any graph-affecting relation has no evidence span.
- Any risk or competitor relation lacks question or platform.
- More than 20 percent of new entities lack canonical names.
- LLM extraction returns entities not present in evidence spans.
- The same span is reused for unrelated relation types without justification.

## 13. Required Tests

Minimum tests:

- Same-category co-mention does not create `competes_with`.
- Explicit alternative recommendation creates `competes_with` with review required.
- Risk phrase plus brand association creates `risk_of`.
- Negative majority does not become positive `associated_with`.
- New entity without evidence span is dropped.
- Exact alias merges automatically; fuzzy alias enters review.
- Target strategic word absent from all answers becomes `target_gap`.

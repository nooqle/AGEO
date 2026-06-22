# Spec: Graph Update Report Generation v0.1

> Date: 2026-06-17  
> Status: Phase 0 freeze candidate  
> Applies to: Report generation node, Guardrails, Trace Chain, Reports view  
> PRD reference: `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md`

## 1. Purpose

Reports explain a Graph Update. They do not create graph truth.

This spec defines how a report is generated from graph data, how evidence is selected, how strategic conclusions are segmented, and how invalid reports are blocked.

## 2. Inputs

```text
GraphUpdate
GraphPatchSet
EntityRelationSet
AnswerSet refs
QuestionSet refs
EntityLexicon
ReportGuardrailProfile
```

## 3. Outputs

```text
CircleReport
ReportGuardrailResult[]
TraceChain[]
Report Artifact
```

## 4. Generation Strategy

Report generation uses a hybrid pipeline:

1. Deterministic skeleton builder creates the report structure from `GraphUpdate`.
2. Evidence selector attaches evidence refs to each claim candidate.
3. Strategic conclusion segmenter assigns the allowed conclusion direction.
4. Next Board recommender derives follow-up board suggestions from graph state.
5. LLM renderer converts the skeleton into readable prose.
6. Guardrail validator checks the rendered report.
7. Publish gate allows `PASS`, allows `WARN` only with policy confirmation, blocks `BLOCK`.

LLM output is never accepted without post-generation validation.

## 5. Report Skeleton

```ts
type ReportSectionKind =
  | "summary"
  | "core_entity_changes"
  | "risk_changes"
  | "competitor_changes"
  | "strategic_word_segmentation"
  | "evidence_excerpts"
  | "recommended_next_board"
  | "guardrail_result"
  | "trace_chain";

type ReportClaimDraft = {
  id: string;
  sectionKind: ReportSectionKind;
  subjectEntityId?: string;
  patchIds: string[];
  allowedConclusion: string;
  evidenceRefIds: string[];
  requiredPlatformNames: string[];
  requiredScenarioNames: string[];
  missingEvidenceReason?: string;
};

type CircleReportSkeleton = {
  graphUpdateId: string;
  boardRunId: string;
  graphPatchSetId: string;
  entityRelationSetId: string;
  reportShape: "short_summary" | "standard_report" | "full_report_with_review_list";
  claimDrafts: ReportClaimDraft[];
};
```

## 6. Report Shape Rules

| Graph Update shape | Report shape |
| --- | --- |
| 1-3 low-risk changes | Short summary |
| 4-15 changes with limited review | Standard report |
| 15+ changes, risk changes, competitor conflicts, or blocked patches | Full report with review list |

## 7. Evidence Selection Rules

Evidence selection runs before LLM rendering.

1. Each strategic word must reference at least two different questions. If not possible, mark `missingEvidenceReason`.
2. One question cannot be the only evidence source for a strategic word.
3. Selection priority: exact strategic word or alias hit, cross-platform coverage, direct zone change relevance, then longer excerpt.
4. Every selected evidence ref must include question text, platform, answer excerpt, polarity, and asset ref.
5. Risk and competitor evidence must prioritize original excerpts over summaries.
6. If more than 80 percent of selected evidence comes from one question, the report enters `WARN` or `BLOCK` depending on severity.
7. Evidence used for one strategic conclusion should not be reused for unrelated conclusions unless it contains distinct spans.

## 8. Strategic Conclusion Segmentation

Strategic conclusions are selected by rules first. LLM may rewrite wording, but it cannot change the conclusion direction.

| Stability | Evidence volume | Polarity condition | Allowed conclusion direction |
| --- | --- | --- | --- |
| `>= 60` | `>= 30` | Positive evidence majority | Already established; can amplify |
| `50-59` | `15-29` | Positive or neutral majority | Has foundation; needs targeted reinforcement |
| `< 50` | `< 15` | Any | Emerging only; gather more evidence first |
| Any | Any | Negative or questioning majority | Carries risk; clarify specific risk first |

Implementation notes:

- A strategic word with risk majority cannot use the established/amplify conclusion.
- A strategic word with evidence from one question only must be marked as evidence-insufficient.
- Each conclusion must include at least one concrete platform or scenario unless the data is insufficient.

## 9. LLM Rendering Constraints

The renderer receives only the report skeleton and approved evidence snippets.

The prompt must require:

- Use only entity ids, patch ids, evidence refs, platforms, and scenarios provided in the skeleton.
- Do not invent competitors, risks, platform names, or scenario names.
- If evidence is missing, state that evidence is insufficient.
- Distinguish positive validation, neutral mention, negative mention, and questioning mention.
- Write action recommendations with action, audience or scenario, platform, and intended metric change.
- Do not reuse the same strategic conclusion sentence across unrelated strategic words.

The renderer must return structured JSON plus markdown. Guardrails validate the structured fields first.

## 10. Guardrail Validation

| Rule | Condition | Result |
| --- | --- | --- |
| Strategic similarity | Any two strategic conclusions string-similarity > 0.8 | `WARN` or `BLOCK` |
| Competitor evidence | Competitor claim without `competes_with` evidence span | `BLOCK` |
| Risk evidence | Risk claim without `risk_of` or risk evidence span | `BLOCK` |
| Evidence concentration | > 80 percent evidence from one question | `WARN` or `BLOCK` |
| Action specificity | Recommendation missing platform, audience/scenario, or target change | `BLOCK` |
| Circle consistency | Zone label contradicts sentiment or veto rule | `BLOCK` |
| Trace completeness | Key claim lacks trace chain to answer/question/platform | `BLOCK` |

`BLOCK` reports are saved as drafts with guardrail reasons and cannot publish.

## 11. Next Board Recommendation Rules

Recommendations are generated by deterministic state mapping, then rendered by LLM.

| Graph state | Next Board suggestion |
| --- | --- |
| Strategic target stuck in outer circle | User Persona or Manual Question Source |
| Risk entity moved closer to brand | Risk Clarification Board |
| Competitor pressure increased | Competitor Comparison Board |
| Evidence sparse or concentrated | Question Expansion Board |
| Platform coverage weak | Platform Coverage Board |
| Brand lexicon conflict | Document Modeling Board |

## 12. Trace Chain

Every key claim must trace:

```text
Report claim -> Graph Update -> Graph Patch -> Entity Relation -> Evidence span -> Answer -> Question -> Platform
```

```ts
type TraceChain = {
  claimId: string;
  graphUpdateId: string;
  graphPatchId: string;
  entityRelationId: string;
  evidenceRefId: string;
  answerArtifactId: string;
  questionId: string;
  platform: string;
};
```

## 13. Required Tests

Minimum tests:

- Report with competitor claim and no competitor evidence is blocked.
- Report with risk claim and no risk evidence is blocked.
- Strategic conclusions with identical text are flagged.
- Evidence from one question only cannot support established strategic conclusion.
- Action recommendation without platform is blocked.
- Negative majority strategic word cannot be rendered as established.
- Report claim without trace chain cannot publish.

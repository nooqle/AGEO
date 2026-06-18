# Response: PRD v0.5 Docs Review

> Date: 2026-06-17  
> Review source: `docs/review-v0.5-docs-2026-06-17.md`  
> Response scope: PRD v0.5, Implementation Handoff, Story/Task Breakdown, new Phase 0 specs

## Summary

The review is accepted.

v0.5 had a correct product/document split, but it was not ready for engineering because it lacked the executable rules for scoring, extraction, report generation, and backend contracts.

This response adds four independent Phase 0 specs and updates the three v0.5 docs to reference them.

## Review Items And Actions

| Review item | Status | Action |
| --- | --- | --- |
| Missing `connection_strength` formula | Addressed | Added `docs/spec-circle-allocation-v0.1-2026-06-17.md` |
| Missing strategic conclusion segmentation | Addressed | Added to `docs/spec-report-generation-v0.1-2026-06-17.md` |
| Missing evidence selection rules | Addressed | Added to `docs/spec-report-generation-v0.1-2026-06-17.md` |
| Missing entity extraction workflow | Addressed | Added `docs/spec-entity-extraction-v0.1-2026-06-17.md` |
| Report generation still black box | Addressed | Added hybrid generation pipeline, LLM constraints, guardrails, and next-board rules |
| Missing backend Python model/schema contract | Addressed | Added `docs/spec-backend-models-api-v0.1-2026-06-17.md` |
| Handoff carrying too many responsibilities | Addressed | Handoff now points to independent specs as source of truth |
| API contract too shallow | Addressed | Backend/API spec adds request/response, errors, pagination, auth scope |
| Platform mismatch | Addressed | v1 platform rack now uses `doubao`, `yuanbao`, `kimi`, `deepseek`; `chatgpt` is future adapter only |
| Story lacks estimates | Addressed | Story doc now has estimate scale and story-level estimates |
| Story 0.3 too vague | Addressed | Story 0.3 now maps existing AGEO concepts to BoardRun, NodeRun, Artifact, GraphUpdate |
| No fallback if real Graph Update slips | Addressed | Story doc now includes fallback strategy and exit criteria |

## New Phase 0 Spec Set

- `docs/spec-circle-allocation-v0.1-2026-06-17.md`
- `docs/spec-entity-extraction-v0.1-2026-06-17.md`
- `docs/spec-report-generation-v0.1-2026-06-17.md`
- `docs/spec-backend-models-api-v0.1-2026-06-17.md`

## Updated Existing Docs

- `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md`
- `docs/implementation-handoff-brand-circle-board-v0.5-2026-06-17.md`
- `docs/story-task-breakdown-brand-circle-board-v0.5-2026-06-17.md`

## Remaining Decisions

These are no longer blockers for Milestone 1 UI work, but should be closed before real Graph Update rollout:

1. Whether every Graph Update auto-generates a report or only user-requested updates do.
2. First-version Graph Timeline depth.
3. Final asset storage path convention.
4. Review Inbox scope: brand-global only, Board-run scoped, or both.

# Milestone 0 Closeout: Brand Circle Board v0.5

> Date: 2026-06-17  
> Status: Closeout draft  
> Scope: Product freeze, implementation boundary, first engineering entry  
> Related docs:
> - `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md`
> - `docs/implementation-handoff-brand-circle-board-v0.5-2026-06-17.md`
> - `docs/story-task-breakdown-brand-circle-board-v0.5-2026-06-17.md`
> - `docs/spec-circle-allocation-v0.1-2026-06-17.md`
> - `docs/spec-entity-extraction-v0.1-2026-06-17.md`
> - `docs/spec-report-generation-v0.1-2026-06-17.md`
> - `docs/spec-backend-models-api-v0.1-2026-06-17.md`

## 1. Closeout Decision

Milestone 0 can close for Phase 1 frontend implementation once this document is accepted.

The product will be implemented as a new parallel feature area, not as an in-place Dashboard replacement.

Product-facing name:

- `Brand Space`

Internal engineering labels:

- `brand-space`
- `dashboard-v2` can be used as an internal navigation alias or feature flag name, but not as the primary user-facing label.

## 2. Frozen Product Boundary

Locked decisions:

1. Brand Space is centered on a brand-owned entity relationship graph.
2. Board output is only `Graph Update`.
3. Reports interpret a Graph Update; they do not create truth.
4. Assets store intermediate artifacts; they are not the main user surface.
5. Chat remains a contextual command/explanation layer, not the primary workflow surface.
6. The new area runs beside the current Dashboard until real Graph Update, review loop, and report guardrails are proven.

Current Dashboard remains responsible for:

- Existing brand management and report-first flows.
- Existing analysis entrypoints.
- Existing dashboard home APIs and projections.
- Existing Chat handoff paths.

Brand Space v1 becomes responsible for:

- Graph home.
- Board canvas runtime.
- Assets explorer.
- Graph Update reports.
- Review queue and trace chain once backend support exists.

## 3. Route And Entry Strategy

Preferred Phase 1 route:

```text
/brand-space
```

Future durable route shape:

```text
/brand-space/[brandId]/graph
/brand-space/[brandId]/boards
/brand-space/[brandId]/boards/[boardId]
/brand-space/[brandId]/assets
/brand-space/[brandId]/reports
/brand-space/[brandId]/reports/[reportId]
```

Optional internal QA alias:

```text
/dashboard-v2 -> /brand-space
```

Feature flag:

```text
NEXT_PUBLIC_BRAND_SPACE_ENABLED=true
```

Phase 1 should not add Brand Space as a default production navigation item unless the flag is enabled.

## 4. Artifact Status

| Artifact | Status | Closeout judgment |
| --- | --- | --- |
| PRD v0.5 | Ready for Phase 1 | Product direction is stable |
| Implementation Handoff | Ready for Phase 1 | Integration boundaries are clear |
| Story/Task Breakdown | Ready for Sprint 0/1 | Has estimates, fallback, and first ticket direction |
| Circle Allocation Spec | Ready for backend spike | Formula and veto rules are defined |
| Entity Extraction Spec | Ready for backend spike | Extraction workflow and schemas are defined |
| Report Generation Spec | Ready for backend spike | Evidence, segmentation, guardrails are defined |
| Backend Model/API Spec | Ready for backend review | Model/API contracts are detailed enough for spike |
| Prototype v0.4 | Visual reference only | Do not copy production CSS |

## 5. Phase 1 Can Start

Phase 1 frontend can start with typed mock data because:

- Product IA is frozen.
- First route strategy is isolated.
- Component responsibilities are defined.
- Motion can be driven by mock runtime events.
- Backend scoring/extraction/report truth is explicitly out of Phase 1.

Phase 1 must not:

- Replace the current Dashboard.
- Apply real graph patches.
- Publish Graph Update reports as production truth.
- Present mock graph data as real analysis.
- Modify old Dashboard data contracts.

## 6. Remaining Decisions

These do not block Phase 1, but must close before Phase 3 real Graph Update.

| Decision | Needed by | Default until closed |
| --- | --- | --- |
| Auto-generate report for every Graph Update or only user-requested reports | Phase 5 | User-requested generation |
| Graph Timeline first-version depth | Phase 3 | Latest update + previous version only |
| Asset path convention | Phase 3 | `assets/{brand_id}/{board_run_id}/{artifact_type}/{artifact_id}` |
| Review Inbox scope | Phase 5 | Board-run scoped queue first; brand-global inbox later |
| `zhipu` adapter inclusion | Phase 3 | Deferred |
| `chatgpt` adapter inclusion | Phase 3 | Deferred |

## 7. First Implementation Gate

Start with:

```text
FE-001: Parallel Brand Space Shell With Mock Board Runtime
```

Gate exit:

- `/brand-space` renders behind feature flag.
- Existing `/dashboard` behavior is unchanged.
- Graph / Boards / Assets / Reports navigation exists.
- Board runtime mock view renders compact nodes, platform rack, inspector, and motion states.
- Static Graph and Report views render without backend graph truth.
- Validation scans pass.

## 8. Risk Register

| Risk | Control |
| --- | --- |
| New work accidentally mutates current Dashboard | Use isolated route and new component namespace |
| Prototype CSS gets copied into production | Rebuild with Specta tokens and shared primitives |
| Mock data is confused with real truth | Mark Phase 1 as `mock_runtime` in UI and data constants |
| Backend implementation starts before algorithms are frozen | Require the four specs as Story 0.4 acceptance |
| Report-first flow reappears inside Brand Space | Block report publish until Graph Update exists |

## 9. Milestone 0 Exit Checklist

- [x] PRD v0.5 exists.
- [x] Handoff exists.
- [x] Story/Task breakdown exists.
- [x] Circle allocation spec exists.
- [x] Entity extraction spec exists.
- [x] Report generation spec exists.
- [x] Backend model/API spec exists.
- [x] v1 platform list is corrected to `doubao`, `yuanbao`, `kimi`, `deepseek`.
- [x] Parallel feature area decision is recorded.
- [ ] Product/design accepts Brand Space as user-facing name.
- [ ] Engineering accepts `/brand-space` as Phase 1 isolated route.
- [ ] Feature flag naming is accepted.
- [ ] FE-001 is scheduled.

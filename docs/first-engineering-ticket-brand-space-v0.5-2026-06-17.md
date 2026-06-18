# First Engineering Ticket: Parallel Brand Space Shell With Mock Board Runtime

> Date: 2026-06-17  
> Ticket id: `FE-001`  
> Status: Ready for engineering review  
> Depends on: Milestone 0 closeout acceptance  
> User-facing feature name: `Brand Space`  
> Internal label: `dashboard-v2` or `brand-space`

## 1. Goal

Create a new parallel Brand Space feature area beside the existing Dashboard.

This ticket proves the shell, information architecture, board canvas direction, graph/report surfaces, and runtime motion model using typed mock data only.

It must not change current Dashboard behavior.

## 2. Route Scope

Add Phase 1 isolated route:

```text
/brand-space
```

Optional QA alias:

```text
/dashboard-v2
```

If the alias is implemented, it should redirect or render the same Brand Space shell. The product label in the UI remains `Brand Space`.

Feature flag:

```text
NEXT_PUBLIC_BRAND_SPACE_ENABLED
```

Flag behavior:

- If enabled: route renders normally.
- If disabled: route may show a simple unavailable state or redirect to `/dashboard`.
- Existing `/dashboard` must remain unchanged.

## 3. Recommended File Shape

Frontend route:

```text
frontend/src/app/brand-space/page.tsx
frontend/src/app/dashboard-v2/page.tsx        optional alias
```

New component namespace:

```text
frontend/src/components/brand-space/BrandSpaceShell.tsx
frontend/src/components/brand-space/BrandSpaceTopBar.tsx
frontend/src/components/brand-space/BrandSpaceSidebar.tsx
frontend/src/components/brand-space/GraphHomeView.tsx
frontend/src/components/brand-space/BoardRuntimeView.tsx
frontend/src/components/brand-space/AssetsView.tsx
frontend/src/components/brand-space/ReportReviewView.tsx
frontend/src/components/brand-space/BoardCanvas.tsx
frontend/src/components/brand-space/BoardNode.tsx
frontend/src/components/brand-space/PlatformRackNode.tsx
frontend/src/components/brand-space/NodeInspector.tsx
frontend/src/components/brand-space/GraphUpdateQueue.tsx
```

Types and mock data:

```text
frontend/src/types/brandSpace.ts
frontend/src/mocks/brandSpaceMock.ts
```

Do not modify `frontend/src/components/dashboard/*` for this ticket except for an optional flagged entry link.

## 4. Required Views

Brand Space shell:

- Left navigation.
- Top brand/run status area.
- View tabs or internal navigation for Graph / Boards / Assets / Reports.
- Mock brand context, defaulting to `Amway Brand Space`.

Graph view:

- Static Brand Circle Graph.
- Circle zones: center, inner, middle, outer, risk, competitor, pending review.
- Graph Update Queue with `auto_applied` and `needs_review`.
- Selected entity panel.

Board view:

- Board canvas with compact nodes.
- Platform rack with `doubao`, `yuanbao`, `kimi`, `deepseek`.
- Runtime toolbar: start, pause, resume, stop.
- Node Inspector with Overview / Events / Output / Config.
- Mock runtime events drive status and motion.

Assets view:

- Artifact groups: questions, raw answers, parsed answers, entity relation set, graph patch set, reports, run logs.
- Mock artifact rows linked to node outputs.

Reports view:

- Static Graph Update report.
- Guardrail status with PASS / WARN / BLOCK examples.
- Trace chain from claim to platform/question/evidence.
- Publish button disabled for BLOCK state.

## 5. Mock Runtime Requirements

Implement typed mock state for:

- `BoardRun`
- `NodeRun`
- `ArtifactRef`
- `GraphPatch`
- `EvidenceRef`
- `RuntimeEvent`
- `ReportGuardrailResult`

Mock runtime should support:

- Start: active nodes enter running state.
- Pause: running animation stops and status changes.
- Resume: running state returns.
- Stop: run stops but artifacts and pending patches remain visible.
- Select node: Inspector updates.
- Switch Inspector tabs.
- Accept/reject mock patch: queue state changes locally.

No backend persistence is required in this ticket.

## 6. Motion Requirements

Motion must communicate state:

- Run heartbeat when mock run is active.
- Edge data flow for active paths.
- Platform rack progress pulse while platform nodes run.
- Node scan/progress state for active node.
- Review pulse for needs-review items.
- Guardrail wake-in for report block.

Reduced motion:

- Respect `prefers-reduced-motion`.
- Keep state dots and progress changes.
- Disable continuous loops.

## 7. Visual Constraints

Use Specta global visual system:

- Light-first.
- Paper-neutral surfaces.
- Specta Evidence Teal `#1F7A6B` for primary/evidence states.
- Amber for warning.
- Red for risk/blocking.
- Compact nodes.
- No prototype CSS copy.
- No old AI-gradient styling or decorative light effects.

## 8. Acceptance Criteria

Product acceptance:

- User can understand this is a new Brand Space, not the old Dashboard.
- User can switch between Graph / Boards / Assets / Reports.
- User can understand Board output is Graph Update.
- User can see intermediate artifacts without treating them as the primary deliverable.
- User can see report guardrail blocking.

Engineering acceptance:

- `/dashboard` still works unchanged.
- `/brand-space` is isolated behind the feature flag.
- Mock data is typed.
- No backend graph mutation occurs.
- No scoring or report validation truth is implemented on the frontend.
- Components live under the new `brand-space` namespace.

Interaction acceptance:

- Start / Pause / Resume / Stop visible state works.
- Node selection updates Inspector.
- Inspector tab switching works.
- Output tab shows artifact refs.
- Graph Update Queue actions update local mock state.
- BLOCK report cannot publish.

## 9. Validation

Required commands:

```powershell
cd frontend
npm run lint
npm run build
```

Repo validation:

```powershell
python scripts\validate_change.py
```

Required scans:

```powershell
rg -n "\?\?\?" frontend/src/app/brand-space frontend/src/components/brand-space frontend/src/types/brandSpace.ts frontend/src/mocks/brandSpaceMock.ts
```

Also run the standard old AI palette/effect term scan from `AGENTS.md` against changed UI source files.

Browser verification:

- Screenshot `/brand-space` desktop.
- Screenshot `/brand-space` mobile.
- Verify Board / Graph / Reports states.
- Verify reduced-motion mode if practical.

## 10. Out Of Scope

- Real BoardRun persistence.
- Real NodeRun persistence.
- Real GraphPatchSet generation.
- Real Graph Update apply.
- Real report generation.
- Legacy report migration.
- Replacing Dashboard.
- Changing current Chat handoff behavior.

## 11. Implementation Notes

Use existing app patterns:

- Next.js App Router route under `frontend/src/app`.
- Existing auth gating pattern if route should be protected.
- Existing Specta CSS variables and shared UI primitives.
- Existing platform names/colors where useful, but keep Brand Space component state separate from Dashboard state.

If a first implementation needs selected brand context, read from existing dashboard store only as an input. Do not write Brand Space state into the Dashboard store in this ticket.

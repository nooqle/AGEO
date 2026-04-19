# GEO Canonical Rollout Legacy Surface Boundary (2026-04-19)

## Purpose

This note records the rollout boundary after the canonical GEO homepage cutover.
It exists to prevent the controlled rollout from accidentally deleting or
breaking non-homepage analytics surfaces that still rely on legacy contracts.

## Canonical Surfaces In Scope

The following surfaces are now part of the canonical GEO main path and should be
treated as the production truth path:

- `A5 canonical report artifact`
- dashboard homepage latest-report summary
- `打开最新报告` drill-in from dashboard to chat canvas

Homepage data authority:

- backend: `aeo-platform/backend/app/services/analytics_service.py`
- frontend adapter: `frontend/src/adapters/dashboardHome.ts`
- homepage renderer:
  - `frontend/src/components/dashboard/DashboardPage.tsx`
  - `frontend/src/components/dashboard/DashboardHomeBoards.tsx`

Homepage payload should be read as:

- `summary`
- `latest_report`
- `metrics`
- `citation_distribution`
- `related_questions`

## Retained Legacy Surfaces Out Of Scope For This Rollout

These surfaces still exist and may still read older `dashboard v2`-style shapes:

- `frontend/src/adapters/dashboardV2.ts`
- `frontend/src/components/dashboard/AEOTab.tsx`
- `frontend/src/components/dashboard/OptimizationTab.tsx`
- `frontend/src/components/dashboard/PlatformTab.tsx`
- `frontend/src/components/dashboard/SourcesTab.tsx`
- `frontend/src/components/dashboard/VisibilityTab.tsx`
- `frontend/src/components/dashboard/DashboardBoardDialog.tsx`
- `frontend/src/components/dashboard/MentionBoardReport.tsx`
- `frontend/src/components/dashboard/SourceBoardReport.tsx`
- `frontend/src/components/dashboard/RadarBoardReport.tsx`
- `frontend/src/services/api.ts#getAnalyticsAll`
- `frontend/src/stores/dashboardStore.ts#fetchData`

Monitoring is intentionally kept out of the homepage cutover and remains on its
own path:

- `frontend/src/components/dashboard/MonitoringTab.tsx`

## Compatibility Rule

`DashboardHomeData` still carries:

- `mention_board`
- `source_board`
- `radar_board`
- `monitoring_entry`

These are compatibility-only fields retained so legacy dialogs and monitoring-
adjacent views do not break during controlled rollout.

They are no longer the semantic center of the homepage.

## Rollout Rule

Until a dedicated replacement or retirement pass is scheduled:

- do not delete the retained legacy surfaces above as part of the homepage
  rollout
- do not move homepage back to `getAnalyticsAll(...)`
- do not reintroduce mixed homepage cards that combine monitoring trends and
  latest-report facts

## Post-Rollout Cleanup Targets

After the controlled rollout stabilizes, the next cleanup pass should decide
which of the following paths are still product-relevant:

- dialog-style board reports
- old `dashboard v2` tabs
- `getAnalyticsAll(...)` homepage dependency
- legacy `DashboardHomeData` compatibility fields

If they are no longer product-relevant, remove them in a dedicated cleanup pass
with targeted browser validation so monitoring and secondary historical views do
not regress silently.

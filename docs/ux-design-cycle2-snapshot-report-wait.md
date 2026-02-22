# UX Design: Cycle 2 -- Snapshot History + Enhanced Reports + Wait Experience

> **Document Status**: Design Proposal, pending team review
> **Design Lead**: Don Norman (UX Lead)
> **Date**: 2026-02-21
> **Related PRD**: `D:\AGEO\docs\prd-cycle2-snapshot-report-wait.md`
> **Related UX (Cycle 1)**: `D:\AGEO\docs\ux-design-p0-bwvs-resilience.md`
> **Accessibility Target**: WCAG AA compliance (contrast >= 4.5:1, keyboard nav, ARIA)

---

## Design Principles (Cycle 2)

Cycle 1 established five principles: Feedback = Trust, Non-modal, Information Hierarchy,
Cognitive Load Minimization, Design System Consistency. Cycle 2 adds two more:

6. **Progressive Revelation of Value**: During a 3-5 minute wait, users should see
   *incremental evidence* that the system is producing value -- not a spinning wheel.
   Every 30 seconds should deliver something meaningful.
7. **Temporal Continuity**: Brand analysis is not a one-shot event. The UI must create
   a sense of ongoing narrative -- "last time vs this time" -- so users perceive
   cumulative value from repeated use.

---

## Table of Contents

1. [Module 1: Snapshot History Trend UI](#module-1-snapshot-history-trend-ui)
   - 1A. Dashboard BWVS Trend Chart Enhancement
   - 1B. Snapshot List / Timeline View
   - 1C. Report "vs Previous" Delta Indicator
2. [Module 2: Enhanced Report Rendering](#module-2-enhanced-report-rendering)
   - 2A. Tab / Section Layout Restructure
   - 2B. Industry Insights Block
   - 2C. Per-Platform Analysis Cards
   - 2D. Actionable Recommendations Cards
   - 2E. Competitor Comparison Matrix
   - 2F. Risk Alerts Visual Hierarchy
3. [Module 3: Wait Experience](#module-3-wait-experience)
   - 3A. StageResultCard Component Specification
   - 3B. A4 Platform Status Cumulative Card
   - 3C. MiniProgress Enhancement
   - 3D. StageResultCard vs ActionLog: Design Decision
4. [Global CSS Additions](#global-css-additions)
5. [Accessibility Audit & Requirements](#accessibility-audit--requirements)
6. [Component Implementation Summary](#component-implementation-summary)

---

## Module 1: Snapshot History Trend UI

### 1A. Dashboard BWVS Trend Chart Enhancement

#### User Scenario

A marketing manager opens the Dashboard after running their third brand analysis this
month. They want to see: "Is my brand's BWVS score trending up or down? What changed
in each dimension?"

#### Current State

The existing `VisibilityTab` (`D:\AGEO\frontend\src\components\dashboard\VisibilityTab.tsx`)
renders a simple Recharts `LineChart` with one line (`score` over `date`). There is no
dimension switching, no snapshot date annotation, and the hover tooltip is minimal.

#### Enhanced Design

```
+-----------------------------------------------------------------------+
|  BWVS Trend                                                           |
|  [BWVS Index] [Mention Rate] [Sentiment] [Coverage] [Citation]       |
|  ~~~~~~~~~~~~~~~~~~~~~ dimension toggle pills ~~~~~~~~~~~~~~~~~~~~~    |
|                                                                       |
|       80 |                                                            |
|          |                                          *  52.3           |
|       60 |                             *  48.2   /                    |
|          |                          /                                 |
|       40 |           *  35.4    /                                     |
|          |        /                                                   |
|       20 |   * 28.1                                                   |
|          |                                                            |
|        0 +----+--------+--------+--------+--------+----->             |
|            02-01     02-07     02-14     02-17     02-20              |
|              S1        S2        S3        S4        S5               |
|                                                                       |
|  [S] = Snapshot marker (vertical dashed line + date label)            |
|                                                                       |
+-----------------------------------------------------------------------+

HOVER STATE (on data point S5):
+-----------------------------------------------------------------------+
|                                                                       |
|  +-- Tooltip --------------------------------+                        |
|  |  2026-02-20  (Snapshot #5)                |                        |
|  |  ---------------------------------------- |                        |
|  |  BWVS Index:       52.3  (+4.1 vs prev)  |                        |
|  |  Mention Rate:     65.0%                  |                        |
|  |  Sentiment:        72.0                   |                        |
|  |  Coverage:         75.0                   |                        |
|  |  Citation:         45.0                   |                        |
|  |  ---------------------------------------- |                        |
|  |  Platforms: 3/4 success                   |                        |
|  +-------------------------------------------+                        |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Container** | Same as existing: `rounded-xl p-4`, `background: var(--bg-tertiary)`, `border: 1px solid var(--border-default)` |
| **Section Title** | "BWVS Trend" -- `font-size: 14px`, `font-weight: 500`, `color: var(--text-primary)` |
| **Dimension Toggle Pills** | Horizontal pill group, `background: var(--bg-elevated)` for active, `background: transparent` for inactive. Active text: `var(--text-primary)`, inactive: `var(--text-tertiary)`. `font-size: 12px`, `padding: 4px 12px`, `border-radius: 6px`. Group container: `background: var(--bg-secondary)`, `border-radius: 8px`, `padding: 3px` |
| **Chart Area** | Recharts `LineChart`, height: `300px`. Grid: `stroke: var(--border-default)`, `strokeDasharray: "3 3"`. Axis ticks: `font-size: 11px`, `fill: var(--text-tertiary)` |
| **Primary Line** | `stroke: var(--brand-primary, #6366F1)`, `strokeWidth: 2`. Dot: `fill: var(--brand-primary)`, `r: 4`. Active dot: `r: 6`, `stroke: var(--brand-primary)`, `strokeWidth: 2`, `fill: var(--bg-primary)` |
| **Snapshot Markers** | Vertical dashed lines at each snapshot date. `stroke: var(--border-hover)`, `strokeDasharray: "4 4"`, `opacity: 0.5`. Date label below x-axis in `font-size: 10px`, `fill: var(--text-muted)` |
| **Hover Tooltip** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-radius: 10px`, `padding: 12px 16px`, `box-shadow: 0 8px 24px rgba(0,0,0,0.5)`. Title: `font-size: 12px`, `font-weight: 600`, `color: var(--text-primary)`. Values: `font-size: 12px`, `color: var(--text-secondary)`. Delta: `color: var(--success)` if positive, `color: var(--error)` if negative |

#### Interaction Behavior

1. **Dimension Toggle**: Clicking a pill switches the Y-axis data key. Default: "BWVS Index".
   When switching, the line animates (Recharts `animationDuration={300}`). The active pill has
   a subtle transition `background: var(--bg-elevated)` with `transition: all 150ms ease-out`.

2. **Hover**: Recharts `<Tooltip>` renders a custom component showing all 5 dimension values
   plus delta vs previous snapshot. The delta is calculated client-side from adjacent trend
   data points.

3. **Click on Data Point**: Navigates to the snapshot detail (future; for now, no-op).

4. **Empty State**: When fewer than 2 snapshots exist, show existing `EmptyState` component
   with message: "Complete at least two brand analyses to see trend data."

5. **Single Snapshot**: When exactly 1 snapshot exists, show a single data point with no line.
   Display a subtle prompt: "Run another analysis to see your trend."

#### State Changes

| State | Behavior |
|-------|----------|
| Loading | Shimmer animation over chart area (reuse `.animate-shimmer` from globals.css) |
| No data (0 snapshots) | EmptyState with chart icon |
| 1 snapshot | Single dot + "Run another analysis" prompt |
| 2+ snapshots | Full line chart with all features |
| Error fetching trend | Toast error + last cached data if available |

#### Accessibility

- Dimension toggle pills: `role="radiogroup"`, each pill `role="radio"` with `aria-checked`
- Active dimension announced: `aria-live="polite"` region updates "Now showing: Mention Rate"
- Chart: `aria-label="BWVS trend chart showing {n} data points from {startDate} to {endDate}"`
- Tooltip content available as `aria-describedby` on focused data point
- Keyboard: `Tab` to enter pill group, `Arrow Left/Right` to navigate pills, `Enter/Space`
  to select. `Tab` to chart area, `Arrow Left/Right` to navigate data points

---

### 1B. Snapshot List / Timeline View

#### User Scenario

User wants to see all their past analyses for a brand -- when they ran, what scores they
got, which succeeded or partially degraded.

#### Design Decision

The snapshot list is **not a separate page**. It lives inside the existing Dashboard as a
collapsible section below the trend chart, within the "Visibility" tab. This keeps the
information architecture flat and avoids navigation overhead.

#### Layout

```
+-----------------------------------------------------------------------+
|  Analysis History                                          [Expand ^]  |
|-----------------------------------------------------------------------|
|                                                                       |
|  +-- Snapshot Row (latest) ------------------------------------+      |
|  |  #5  2026-02-20 14:33    BWVS 52.3  [+4.1]    Completed   |      |
|  |      Platforms: 3/4   Questions: 48   Mentions: 31          |      |
|  +-------------------------------------------------------------+      |
|                                                                       |
|  +-- Snapshot Row -------------------------------------------+        |
|  |  #4  2026-02-17 10:15    BWVS 48.2  [+12.8]   Completed  |        |
|  |      Platforms: 4/4   Questions: 48   Mentions: 28         |        |
|  +------------------------------------------------------------+       |
|                                                                       |
|  +-- Snapshot Row -------------------------------------------+        |
|  |  #3  2026-02-14 09:00    BWVS 35.4  [--]      Partial    |        |
|  |      Platforms: 2/4   Questions: 24   Mentions: 10         |        |
|  +------------------------------------------------------------+       |
|                                                                       |
|  ...more rows (paginated, 10 per page)                                |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Section Header** | "Analysis History" -- `font-size: 14px`, `font-weight: 500`, `color: var(--text-primary)`. Right side: collapse/expand chevron |
| **Snapshot Row** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-radius: 10px`, `padding: 12px 16px`, `margin-bottom: 8px` |
| **Snapshot Number** | `font-size: 11px`, `font-weight: 600`, `color: var(--text-muted)`. Monospace font |
| **Date** | `font-size: 13px`, `color: var(--text-primary)` |
| **BWVS Score** | `font-size: 16px`, `font-weight: 700`. Color follows score band: >= 70 `var(--success)`, >= 40 `var(--warning)`, < 40 `var(--error)` |
| **Delta Badge** | `font-size: 11px`, `font-weight: 600`, `padding: 2px 6px`, `border-radius: 4px`. Positive: `background: rgba(34,197,94,0.1)`, `color: var(--success)`. Negative: `background: rgba(239,68,68,0.1)`, `color: var(--error)`. Neutral/first: `color: var(--text-muted)`, no background |
| **Status Badge** | `font-size: 10px`, `padding: 2px 8px`, `border-radius: 4px`. Completed: `background: rgba(34,197,94,0.1)`, `color: var(--success)`. Partial: `background: rgba(245,158,11,0.1)`, `color: var(--warning)`. Failed: `background: rgba(239,68,68,0.1)`, `color: var(--error)` |
| **Stats Row** | `font-size: 11px`, `color: var(--text-tertiary)`, `margin-top: 4px` |

#### Interaction Behavior

1. **Default State**: Collapsed (header only). Click to expand.
2. **Pagination**: Show 10 snapshots per page. "Show more" button at bottom loads next page.
3. **Row Click**: Future -- opens snapshot detail in Canvas panel. For now, no action.
4. **Latest Row Highlight**: First row has a subtle left border accent: `border-left: 3px solid var(--brand-primary)`.

#### Accessibility

- Section: `role="region"`, `aria-label="Analysis History"`
- Expand/Collapse: `aria-expanded` on toggle button
- Snapshot rows: `role="list"` container, each row `role="listitem"`
- Status badges: `aria-label` with full text (e.g., "Status: Partially completed")

---

### 1C. Report "vs Previous" Delta Indicator

#### User Scenario

User opens the latest A5 report in the Canvas panel. The Score Card at the top shows
BWVS 52.3. Below the score, they see a delta indicator: "+4.1 (+8.5%) vs 2026-02-17".
This immediately tells them: "My score went up since last time."

#### Layout

```
+----------------------------------------------------------+
|                                                          |
|     52.3       BWVS Index                                |
|                                                          |
|     +4.1 (+8.5%)  vs 2026-02-17                         |
|     ^green text    ^muted text                           |
|                                                          |
|     [=====================          ] Good               |
|                                                          |
+----------------------------------------------------------+
```

When no previous snapshot exists (first analysis):

```
+----------------------------------------------------------+
|                                                          |
|     35.4       BWVS Index                                |
|                                                          |
|     First Analysis                                       |
|     ^muted, italic text                                  |
|                                                          |
|     [=============                  ] Needs Improvement  |
|                                                          |
+----------------------------------------------------------+
```

When score decreased:

```
+----------------------------------------------------------+
|                                                          |
|     42.1       BWVS Index                                |
|                                                          |
|     -6.1 (-12.7%)  vs 2026-02-17                        |
|     ^red text       ^muted text                          |
|                                                          |
|     [================               ] Good               |
|                                                          |
+----------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Delta Row Container** | `display: flex`, `align-items: center`, `gap: 8px`, `margin-top: 6px` |
| **Delta Value** | `font-size: 13px`, `font-weight: 600`. Up: `color: var(--success, #22C55E)`, prefix "+". Down: `color: var(--error, #EF4444)`, prefix "-". Stable (< 0.5 abs): `color: var(--text-muted)`, text "~0" |
| **Delta Percentage** | `font-size: 12px`, `font-weight: 400`. Same color as delta value. Wrapped in parentheses |
| **Comparison Date** | `font-size: 12px`, `color: var(--text-disabled, #525252)`. Prefix "vs" |
| **Direction Arrow** | Before delta value. Up: `RiArrowUpLine` 14px. Down: `RiArrowDownLine` 14px. Stable: no arrow |
| **"First Analysis" label** | `font-size: 12px`, `font-style: italic`, `color: var(--text-muted, #6B6B6B)` |

#### Placement

In `ReportContent.tsx`, inside the existing Score Card block (`activeTab === 'overview'`,
the `data.overallScore !== undefined` section), immediately after the score display and
before the progress bar. Between lines that render `data.overallScore` and `data.scoreBand`.

#### Data Requirements

The `delta_vs_previous` field from the backend artifact:

```typescript
interface DeltaVsPrevious {
  bwvs_index: {
    current: number;
    previous: number;
    delta: number;      // absolute difference
    percentage: number; // percentage change
    direction: 'up' | 'down' | 'stable';
  };
  previous_date: string;        // ISO date: "2026-02-17"
  previous_snapshot_id: string;
}
```

#### Accessibility

- Delta indicator: `role="status"`, `aria-live="polite"`
- Screen reader text: "BWVS score changed by plus 4.1 points, up 8.5 percent, compared to February 17th 2026"
- Direction conveyed by both color AND arrow icon AND text prefix (+/-)
- Color is never the sole indicator

---

## Module 2: Enhanced Report Rendering

### 2A. Tab / Section Layout Restructure

#### Current State

`ReportContent.tsx` has 4 tabs: Overview | Platforms | Competitors | Recommendations.

#### Enhanced Structure

The tab count increases from 4 to 6. To prevent tab overflow in the ~600px Canvas panel,
we use a **scrollable tab bar** rather than wrapping.

```
+-----------------------------------------------------------------------+
|  Brand AI Visibility Report                                           |
|  Mention Rate: 65.0%  (BWVS Index: 52.3)                            |
+-----------------------------------------------------------------------+

Tab bar (horizontally scrollable):
[Overview] [Industry] [Platforms] [Competitors] [Recommendations] [Risks]
  ^active

Each tab maps to:
- Overview:        Score Card + Delta + BWVS Breakdown + Metrics + Key Findings + Exec Summary
- Industry:        Industry Insights block (new)
- Platforms:       Per-platform analysis cards (enhanced)
- Competitors:     Competitor matrix + SWOT (enhanced)
- Recommendations: Actionable recommendation cards (enhanced)
- Risks:           Risk alerts (new)
```

#### Tab Bar Visual Specifications

| Element | Specification |
|---------|---------------|
| **Tab Container** | `display: flex`, `gap: 2px`, `overflow-x: auto`, `scrollbar-width: none` (hide scrollbar), `border-bottom: 1px solid var(--border-default)` |
| **Tab Button** | `padding: 8px 16px`, `font-size: 13px`, `font-weight: 500`, `white-space: nowrap`, `flex-shrink: 0` |
| **Active Tab** | `color: var(--brand-primary, #6366F1)`, `border-bottom: 2px solid var(--brand-primary)` |
| **Inactive Tab** | `color: var(--text-secondary, #A3A3A3)`, `border-bottom: 2px solid transparent` |
| **Scroll Indicator** | Subtle gradient fade on right edge when tabs overflow: `background: linear-gradient(to right, transparent 80%, var(--bg-primary) 100%)` applied as pseudo-element |

#### Accessibility

- Tab bar: `role="tablist"`, each tab `role="tab"`, content panels `role="tabpanel"`
- `aria-selected="true"` on active tab
- Keyboard: `Arrow Left/Right` to navigate tabs, `Enter/Space` to activate
- `aria-controls` linking each tab to its panel

---

### 2B. Industry Insights Block

#### User Scenario

The marketing manager reads the report. After seeing the BWVS score, they want industry
context: "Is 52.3 good or bad for my industry? What are the trends?"

#### Layout

```
+-----------------------------------------------------------------------+
|  [Industry Tab Content]                                               |
|                                                                       |
|  +-- Industry Background -----------------------------------------+   |
|  |                                                                 |   |
|  |  [light bulb icon]  Industry Background                        |   |
|  |                                                                 |   |
|  |  This brand operates in the consumer electronics industry,     |   |
|  |  which is characterized by high AI search competition...       |   |
|  |                                                                 |   |
|  |  (i) Based on industry experience -- not proprietary data      |   |
|  |                                                                 |   |
|  +-----------------------------------------------------------------+   |
|                                                                       |
|  +-- Typical Performance -----------------------------------------+   |
|  |                                                                 |   |
|  |  [bar chart icon]  Industry Benchmarks                         |   |
|  |                                                                 |   |
|  |  Typical AI mention rate for this industry: 30%-60%            |   |
|  |  Your brand: 65.0% -- Above industry average                  |   |
|  |                                                                 |   |
|  +-----------------------------------------------------------------+   |
|                                                                       |
|  +-- Trends & Opportunities --+  +-- Opportunities ---------------+   |
|  |                             |  |                                |   |
|  |  Trends                     |  |  Opportunities                |   |
|  |  - Trend 1                  |  |  - Opportunity 1              |   |
|  |  - Trend 2                  |  |  - Opportunity 2              |   |
|  |                             |  |                                |   |
|  +-----------------------------+  +--------------------------------+   |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Background Card** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-radius: 10px`, `padding: 16px 20px` |
| **Card Title** | `font-size: 13px`, `font-weight: 600`, `color: var(--text-primary)`. Icon: Remix Icon `RiLightbulbLine` 16px, `color: var(--warning)` |
| **Body Text** | `font-size: 13px`, `line-height: 1.7`, `color: var(--text-secondary)` |
| **Disclaimer** | `font-size: 11px`, `color: var(--text-muted)`, prefix "(i)" icon `RiInformationLine` 12px. Separated by `border-top: 1px solid var(--border-default)`, `margin-top: 12px`, `padding-top: 8px` |
| **Benchmark Highlight** | Your brand's value in `font-weight: 600`. If above average: `color: var(--success)`. If below: `color: var(--warning)` |
| **Trends/Opportunities Grid** | `grid-template-columns: 1fr 1fr`, `gap: 12px`. Each column: same card style as Background Card |
| **List Items** | `font-size: 12px`, `color: var(--text-secondary)`, bullet: `color: var(--brand-primary)`, 4px circle |

#### Empty State

When `industry_insights` is null (fallback report), show:

```
+-----------------------------------------------------------------------+
|  Industry insights are not available for this analysis.               |
|  This may be due to a simplified report generation.                  |
+-----------------------------------------------------------------------+
```

Using the existing `EmptyState` component.

#### Accessibility

- Cards: `role="article"` with `aria-label="Industry Background"`
- Disclaimer icon: `aria-hidden="true"` (decorative), text readable by screen reader
- Benchmark comparison: screen reader gets full text "Your brand: 65%, above industry average"

---

### 2C. Per-Platform Analysis Cards

#### User Scenario

The user clicks the "Platforms" tab. They want to see how their brand performs on each
AI platform individually -- not just a mention rate bar, but *why* each platform differs
and *what to do* about each one.

#### Current State

`ReportContent.tsx` platforms tab shows simple bars with `platform name | success/total | mention%`.

#### Enhanced Layout

```
+-----------------------------------------------------------------------+
|  [Platforms Tab Content]                                              |
|                                                                       |
|  +-- Platform Card: DeepSeek ----------------------------------+      |
|  |                                                              |      |
|  |  [DeepSeek icon]  DeepSeek              Mention Rate: 75%   |      |
|  |  ---------------------------------------------------------- |      |
|  |                                                              |      |
|  |  Performance Summary                                         |      |
|  |  The brand performs well on DeepSeek, especially in          |      |
|  |  technical product comparison questions...                   |      |
|  |                                                              |      |
|  |  Content Preferences                                         |      |
|  |  DeepSeek tends to cite technical documentation and          |      |
|  |  authoritative review sites...                               |      |
|  |                                                              |      |
|  |  Strengths                          Weaknesses               |      |
|  |  + Technical docs well-covered     - User review content     |      |
|  |  + Spec data frequently cited        lacking                 |      |
|  |                                    - Product recommendation  |      |
|  |                                      questions weak           |      |
|  |                                                              |      |
|  |  Optimization Tips                                           |      |
|  |  1. Add user review content on third-party platforms         |      |
|  |  2. Create comparison guides targeting product questions     |      |
|  |                                                              |      |
|  +--------------------------------------------------------------+      |
|                                                                       |
|  +-- Platform Card: Doubao ....                                       |
|  +-- Platform Card: Kimi ....                                         |
|  +-- Platform Card: Hunyuan ....                                      |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Platform Card** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-radius: 12px`, `padding: 20px`, `margin-bottom: 12px` |
| **Card Header** | `display: flex`, `justify-content: space-between`, `align-items: center`. Left: platform name `font-size: 15px`, `font-weight: 600`, `color: var(--text-primary)`. Right: mention rate badge `font-size: 13px`, `font-weight: 600`, `padding: 4px 10px`, `border-radius: 6px`, `background: var(--bg-tertiary)`, color by rate (>= 60%: `var(--success)`, 30-59%: `var(--warning)`, < 30%: `var(--error)`) |
| **Divider** | `border-top: 1px solid var(--border-default)`, `margin: 12px 0` |
| **Subsection Title** | `font-size: 12px`, `font-weight: 600`, `color: var(--text-primary)`, `margin-bottom: 6px`, `margin-top: 16px` |
| **Body Text** | `font-size: 13px`, `line-height: 1.6`, `color: var(--text-secondary)` |
| **Strengths/Weaknesses Grid** | `grid-template-columns: 1fr 1fr`, `gap: 16px` |
| **Strength Item** | Prefix "+" in `color: var(--success)`, text `color: var(--text-secondary)`, `font-size: 12px` |
| **Weakness Item** | Prefix "-" in `color: var(--error)`, text `color: var(--text-secondary)`, `font-size: 12px` |
| **Optimization Tips** | Numbered list, `font-size: 12px`, `color: var(--text-secondary)`. Number: `font-weight: 600`, `color: var(--brand-primary)` |

#### Interaction

1. **Default**: All platform cards visible, stacked vertically. No collapsing needed
   (typically 2-4 platforms, content fits).
2. **Empty platform_analysis**: Fall back to the existing simple bar view (backward compatible).

#### Accessibility

- Each platform card: `role="article"`, `aria-label="DeepSeek platform analysis"`
- Strengths list: `role="list"`, `aria-label="Strengths for DeepSeek"`
- Weaknesses list: `role="list"`, `aria-label="Weaknesses for DeepSeek"`

---

### 2D. Actionable Recommendations Cards

#### User Scenario

The user opens the "Recommendations" tab expecting concrete actions. Instead of generic
"improve brand awareness" advice, they see prioritized cards with difficulty, timeline,
and expected impact.

#### Layout

```
+-----------------------------------------------------------------------+
|  [Recommendations Tab Content]                                        |
|                                                                       |
|  +-- Recommendation Card (P0) ---------------------------------+      |
|  |                                                              |      |
|  |  [P0]  Optimize Encyclopedia Entries       Difficulty: Low  |      |
|  |  ---------------------------------------------------------- |      |
|  |                                                              |      |
|  |  Action:                                                     |      |
|  |  Update brand entries on Baidu Baike and Wikipedia.          |      |
|  |  Add product specifications and user review citations.       |      |
|  |                                                              |      |
|  |  Expected Impact:         Timeline:                          |      |
|  |  Citation quality +15-25% 1-2 weeks                         |      |
|  |                                                              |      |
|  +--------------------------------------------------------------+      |
|                                                                       |
|  +-- Recommendation Card (P1) ---------------------------------+      |
|  |                                                              |      |
|  |  [P1]  Create Platform-Specific Content    Difficulty: Med  |      |
|  |  ---------------------------------------------------------- |      |
|  |                                                              |      |
|  |  Action:                                                     |      |
|  |  Publish comparison articles targeting Kimi and DeepSeek's   |      |
|  |  content preferences. Focus on user scenarios...             |      |
|  |                                                              |      |
|  |  Expected Impact:         Timeline:                          |      |
|  |  Mention rate +10-20%     2-4 weeks                          |      |
|  |                                                              |      |
|  +--------------------------------------------------------------+      |
|                                                                       |
|  +-- Recommendation Card (P2) ....                                    |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Card Container** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-radius: 10px`, `padding: 16px 20px`, `margin-bottom: 10px` |
| **Priority Badge** | `font-size: 11px`, `font-weight: 700`, `padding: 3px 8px`, `border-radius: 4px`. P0: `background: rgba(239,68,68,0.15)`, `color: #FCA5A5`. P1: `background: rgba(245,158,11,0.15)`, `color: #FCD34D`. P2: `background: rgba(34,197,94,0.15)`, `color: #86EFAC` |
| **Title** | `font-size: 14px`, `font-weight: 600`, `color: var(--text-primary)` |
| **Difficulty Badge** | `font-size: 11px`, `padding: 2px 8px`, `border-radius: 4px`, `background: var(--bg-tertiary)`. Low: `color: var(--success)`. Medium: `color: var(--warning)`. High: `color: var(--error)` |
| **"Action:" Label** | `font-size: 11px`, `font-weight: 600`, `color: var(--text-muted)`, `text-transform: uppercase`, `letter-spacing: 0.5px` |
| **Action Text** | `font-size: 13px`, `line-height: 1.6`, `color: var(--text-secondary)` |
| **Impact/Timeline Row** | `display: grid`, `grid-template-columns: 1fr 1fr`, `gap: 16px`, `margin-top: 12px`, `padding-top: 12px`, `border-top: 1px solid var(--border-default)` |
| **Impact Value** | `font-size: 13px`, `font-weight: 500`, `color: var(--success)` |
| **Timeline Value** | `font-size: 13px`, `font-weight: 500`, `color: var(--text-primary)` |
| **Small Label** | `font-size: 10px`, `color: var(--text-muted)`, `margin-bottom: 2px` |

#### Left Border Accent (Priority Visual Cue)

Each card has a left border accent matching priority:

- P0: `border-left: 3px solid var(--error, #EF4444)`
- P1: `border-left: 3px solid var(--warning, #F59E0B)`
- P2: `border-left: 3px solid var(--success, #22C55E)`

This provides immediate visual scanning without reading the badge text.

#### Fallback

When `actionable_recommendations` is empty or absent, show the existing
`data.recommendations` list (backward compatible with Cycle 1 format).

#### Accessibility

- Cards: `role="article"`, `aria-label="P0 recommendation: Optimize Encyclopedia Entries"`
- Priority badge: `aria-label="Priority: P0, critical"`
- Difficulty badge: `aria-label="Difficulty: Low"`

---

### 2E. Competitor Comparison Matrix

#### User Scenario

The user clicks "Competitors" tab. They want a side-by-side comparison: how does their
brand stack up against each competitor across key metrics?

#### Enhanced Layout

The existing SWOT cards remain but are moved below a new comparison matrix.

```
+-----------------------------------------------------------------------+
|  [Competitors Tab Content]                                            |
|                                                                       |
|  +-- Competitor Overview ----------------------------------------+    |
|  |  "Among the N competitors analyzed, Brand X leads with..."   |    |
|  +---------------------------------------------------------------+    |
|                                                                       |
|  +-- Comparison Matrix ------------------------------------------+    |
|  |                                                                |    |
|  |  Competitor  | vs Brand | Advantage Reasons  | Learnings      |    |
|  |  ----------- | -------- | ------------------ | -------------- |    |
|  |  Competitor X| Higher   | - Reason 1         | - Learning 1   |    |
|  |              |          | - Reason 2         |                |    |
|  |  ----------- | -------- | ------------------ | -------------- |    |
|  |  Competitor Y| Lower    | - Reason 1         | - Learning 1   |    |
|  |              |          |                    |                |    |
|  +----------------------------------------------------------------+    |
|                                                                       |
|  +-- Differentiation Strategy ------------------------------------+    |
|  |  "Based on the competitive landscape, the recommended          |    |
|  |   differentiation strategy is..."                              |    |
|  +----------------------------------------------------------------+    |
|                                                                       |
|  +-- SWOT Analysis (existing, repositioned) ---------------------+    |
|  |  [S] Strengths  [W] Weaknesses                                |    |
|  |  [O] Opportunities  [T] Threats                                |    |
|  +----------------------------------------------------------------+    |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Overview Text** | `font-size: 13px`, `color: var(--text-secondary)`, `padding: 12px 16px`, `background: var(--bg-secondary)`, `border-radius: 10px`, `margin-bottom: 12px` |
| **Matrix Container** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-radius: 10px`, `overflow: hidden` |
| **Table Header** | `background: var(--bg-tertiary)`, `font-size: 11px`, `font-weight: 600`, `color: var(--text-primary)`, `padding: 10px 16px`, `text-transform: uppercase`, `letter-spacing: 0.5px` |
| **Table Row** | `border-top: 1px solid var(--border-default)`, `padding: 12px 16px` |
| **"vs Brand" Badge** | Higher: `color: var(--error)`, text "Higher". Lower: `color: var(--success)`, text "Lower". Similar: `color: var(--text-muted)`, text "Similar" |
| **Reason/Learning Items** | `font-size: 12px`, `color: var(--text-secondary)`, `line-height: 1.5` |
| **Differentiation Card** | Same as Overview Text styling, with `border-left: 3px solid var(--brand-primary)` |

#### Fallback

When `competitor_deep_analysis` is null, render only the existing SWOT cards
(backward compatible).

#### Accessibility

- Matrix: `role="table"`, headers `role="columnheader"`, rows `role="row"`, cells `role="cell"`
- "vs Brand" badges convey meaning via text, not just color
- SWOT cards retain existing accessibility from Cycle 1

---

### 2F. Risk Alerts Visual Hierarchy

#### User Scenario

The user clicks the "Risks" tab. They see ranked risk alerts -- high-severity risks at
top with prominent visual treatment, medium/low risks below in muted styling.

#### Layout

```
+-----------------------------------------------------------------------+
|  [Risks Tab Content]                                                  |
|                                                                       |
|  +-- Risk Alert (High) ------------------------------------------+    |
|  |  [!]  Competitor X Accelerating AI Search Layout              |    |
|  |  ----------------------------------------------------------- |    |
|  |  Description: Competitor X has been increasing their          |    |
|  |  presence in AI-generated answers by 40% over the past       |    |
|  |  quarter...                                                   |    |
|  |                                                               |    |
|  |  Mitigation:                                                  |    |
|  |  Prioritize content optimization on platforms where           |    |
|  |  Competitor X is weakest (Kimi, Hunyuan)                      |    |
|  +---------------------------------------------------------------+    |
|                                                                       |
|  +-- Risk Alert (Medium) ----------------------------------------+    |
|  |  (i)  Industry Content Standards Evolving                     |    |
|  |  ----------------------------------------------------------- |    |
|  |  Description: ...                                             |    |
|  |  Mitigation: ...                                              |    |
|  +---------------------------------------------------------------+    |
|                                                                       |
|  +-- Risk Alert (Low) -------------------------------------------+    |
|  |  ...more compact, no border accent                            |    |
|  +---------------------------------------------------------------+    |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **High Risk Card** | `background: rgba(239,68,68,0.06)`, `border: 1px solid rgba(239,68,68,0.2)`, `border-left: 3px solid var(--error)`, `border-radius: 10px`, `padding: 16px 20px` |
| **Medium Risk Card** | `background: rgba(245,158,11,0.06)`, `border: 1px solid rgba(245,158,11,0.15)`, `border-left: 3px solid var(--warning)`, `border-radius: 10px`, `padding: 14px 18px` |
| **Low Risk Card** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-radius: 10px`, `padding: 12px 16px` |
| **High Risk Icon** | `RiAlertLine`, `color: var(--error)`, 16px |
| **Medium Risk Icon** | `RiErrorWarningLine`, `color: var(--warning)`, 16px |
| **Low Risk Icon** | `RiInformationLine`, `color: var(--text-tertiary)`, 14px |
| **Title** | `font-size: 13px`, `font-weight: 600`. High: `color: #FCA5A5`. Medium: `color: #FCD34D`. Low: `color: var(--text-primary)` |
| **Description** | `font-size: 12px`, `color: var(--text-secondary)`, `line-height: 1.6` |
| **"Mitigation:" Label** | `font-size: 11px`, `font-weight: 600`, `color: var(--text-muted)`, `margin-top: 10px` |
| **Mitigation Text** | `font-size: 12px`, `color: var(--text-secondary)` |

#### Fallback

When `risk_alerts` is empty or absent, show: "No risk alerts for this analysis."

#### Accessibility

- Risk cards: `role="alert"` for high severity, `role="status"` for medium/low
- Level conveyed via text label AND icon AND color AND border accent (4 channels)
- `aria-label="High severity risk: Competitor X Accelerating AI Search Layout"`

---

## Module 3: Wait Experience

### 3A. StageResultCard Component Specification

#### Design Philosophy

The StageResultCard is the key innovation of Cycle 2's wait experience. Instead of a
passive progress indicator, it delivers *tangible intermediate results* to the user.
Each card says: "Here is something the system just produced for you."

The psychological principle: **the Zeigarnik effect** -- people remember incomplete tasks
more than completed ones. By showing partial results, we create a sense of investment
and anticipation rather than passive waiting.

#### Component Structure

```
StageResultCard
  +-- Header (always visible)
  |   +-- Stage Icon
  |   +-- Stage Name
  |   +-- Status Badge
  +-- Body (content varies by result_type)
  |   +-- [type-specific layout]
  +-- Footer (optional, for in-progress states)
      +-- Loading indicator text
```

#### 5 Result Types

##### Type 1: `brand_profile` (A1 completion)

```
+-- A1 Brand Analysis ----------------------[Completed]--+
|                                                         |
|  Brand:      Xiaomi                                     |
|  Industry:   Consumer Electronics                       |
|  Competitors: Huawei, Apple, OPPO, vivo                 |
|  Products:   Smartphones, IoT devices, smart home...    |
|                                                         |
+---------------------------------------------------------+
```

Layout: Key-value rows. Label column `width: 72px`, right-aligned, `color: var(--text-muted)`.
Value column: `color: var(--text-primary)`.

##### Type 2: `personas` (A2 completion)

```
+-- A2 User Personas -----------------------[Completed]--+
|                                                         |
|  Generated 3 user personas:                             |
|  - Tech Enthusiast (25-35, urban)                       |
|  - Budget-Conscious Buyer (30-45)                       |
|  - Smart Home Early Adopter (28-40)                     |
|                                                         |
+---------------------------------------------------------+
```

Layout: Count summary line + bullet list of persona names. Compact -- max 4 items shown.

##### Type 3: `questions` (A3 completion)

```
+-- A3 Question Generation -----------------[Completed]--+
|                                                         |
|  Generated 48 questions across 6 categories:            |
|  Product Comparison | Purchase Advice | Tech Specs      |
|  Brand Reputation | User Reviews | Feature Requests     |
|                                                         |
|  Samples:                                               |
|  "Which phone has the best camera under 3000 yuan?"     |
|  "How does Xiaomi 15 compare to iPhone 16?"             |
|                                                         |
+---------------------------------------------------------+
```

Layout: Summary line + category tags (inline flow) + 2 sample questions in
`font-style: italic`, `color: var(--text-tertiary)`.

Category tags: `font-size: 10px`, `padding: 2px 6px`, `background: var(--bg-tertiary)`,
`border-radius: 4px`, `color: var(--text-secondary)`.

##### Type 4: `platform_status` (A4 cumulative -- see 3B below for detail)

##### Type 5: `metrics_preview` (A5 calculation done, report generating)

```
+-- A5 Data Analysis -----------------------[Computing]--+
|                                                         |
|      48.2       BWVS Index                              |
|                 Good                                    |
|                                                         |
|  Mention Rate:  58.3%                                   |
|  Mentions:      28 / 48                                 |
|                                                         |
|  Report generating...                                   |
|                                                         |
+---------------------------------------------------------+
```

Layout: Big number display (reuses Score Card visual pattern). Value `font-size: 24px`,
`font-weight: 700`, color by score band. Label `font-size: 11px`, `color: var(--text-secondary)`.
Band text below the label, same color as score.

Two stat rows below. Footer has generating indicator with shimmer animation.

#### Universal Visual Specifications

| Element | Specification |
|---------|---------------|
| **Card Container** | `background: var(--bg-secondary, #1A1A1A)`, `border: 1px solid var(--border-default, #333333)`, `border-radius: 10px`, `padding: 10px 14px`, `margin: 6px 0` |
| **Header** | `display: flex`, `align-items: center`, `gap: 8px`, `margin-bottom: 8px` |
| **Stage Icon** | 16px, `color: var(--brand-primary)`. Icons by stage: A1=`RiBuildingLine`, A2=`RiUserLine`, A3=`RiQuestionLine`, A4=`RiGlobalLine`, A5=`RiBarChartLine` |
| **Stage Name** | `font-size: 12px`, `font-weight: 500`, `color: var(--text-secondary)`, `flex: 1` |
| **Status Badge** | `font-size: 10px`, `padding: 2px 8px`, `border-radius: 4px`. Completed: `background: rgba(34,197,94,0.1)`, `color: var(--success)`, text "Completed". In-progress: `background: rgba(245,158,11,0.1)`, `color: var(--warning)`, text "In Progress". Computing: `background: rgba(99,102,241,0.1)`, `color: var(--brand-primary)`, text "Computing" |
| **Body Text** | `font-size: 12px`, `line-height: 1.6`, `color: var(--text-secondary)` |
| **Key-Value Label** | `font-size: 11px`, `color: var(--text-muted)`, right-aligned, fixed width 72px |
| **Key-Value Value** | `font-size: 12px`, `color: var(--text-primary)` |
| **Footer Text** | `font-size: 11px`, `color: var(--text-muted)`, `font-style: italic`, `margin-top: 8px` |
| **Max Height** | `max-height: 140px`. If content exceeds, clip with gradient fade + "Show more" link (`font-size: 11px`, `color: var(--brand-primary)`) |
| **Entry Animation** | `@keyframes slide-up { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }`, `duration: 200ms`, `ease-out` |

#### State Changes

| Transition | Behavior |
|------------|----------|
| Card appears | Slide-up animation (200ms) |
| Status changes (in_progress -> completed) | Badge color transition (200ms). No re-animation of card body |
| A4 card updates (new platform) | Existing card body updates in-place. New platform row slides in from left (150ms) |
| Execution complete | All cards fade to 70% opacity after 2s delay, to reduce visual competition with the final report |

---

### 3B. A4 Platform Status Cumulative Card

#### Design Decision: Merge 4 Events into 1 Card

The architecture review specifically flagged: "Frontend must merge 4 platform events
into 1 card." This is the correct UX decision. Showing 4 separate cards for each
platform would create visual noise and break the narrative flow.

The A4 StageResultCard is a **single, living card** that updates cumulatively as each
platform completes.

#### State Progression

```
STATE 1: First platform completes
+-- A4 Data Fetch --------------------------[1/4]-------+
|                                                         |
|  [v] DeepSeek    12/12  Mentions: 8                     |
|  [ ] Doubao      Fetching...                            |
|  [ ] Kimi        Waiting                                |
|  [ ] Hunyuan     Waiting                                |
|                                                         |
+---------------------------------------------------------+

STATE 2: Second platform completes
+-- A4 Data Fetch --------------------------[2/4]-------+
|                                                         |
|  [v] DeepSeek    12/12  Mentions: 8                     |
|  [v] Doubao      12/12  Mentions: 6                     |
|  [ ] Kimi        Fetching...                            |
|  [ ] Hunyuan     Waiting                                |
|                                                         |
+---------------------------------------------------------+

STATE 3: Third platform fails
+-- A4 Data Fetch --------------------------[3/4]-------+
|                                                         |
|  [v] DeepSeek    12/12  Mentions: 8                     |
|  [v] Doubao      12/12  Mentions: 6                     |
|  [x] Kimi        Failed: Connection timeout             |
|  [ ] Hunyuan     Fetching...                            |
|                                                         |
+---------------------------------------------------------+

STATE 4: All platforms done
+-- A4 Data Fetch --------------------------[3/4]-------+
|                                                         |
|  [v] DeepSeek    12/12  Mentions: 8                     |
|  [v] Doubao      12/12  Mentions: 6                     |
|  [x] Kimi        Failed: Connection timeout             |
|  [v] Hunyuan     10/12  Mentions: 5                     |
|                                                         |
+---------------------------------------------------------+
```

#### Implementation Strategy

The `conversationStore` must maintain a **single StageResult entry for A4** that merges
incoming `platform_status` events. When a new `platform_status` event arrives:

1. Find existing A4 stage result in `stageResults[]`
2. If none exists, create one with 4 platform slots (all "waiting")
3. Update the specific platform's slot
4. Recalculate the header badge (e.g., "2/4")

```typescript
// Pseudo-code for store merge logic
addStageResult: (result: StageResult) => {
  if (result.resultType === 'platform_status') {
    set((state) => {
      const existing = state.stageResults.find(
        s => s.stage === 'A4' && s.resultType === 'platform_status'
      );
      if (existing) {
        // Merge: update the specific platform in existing.data.platforms
        const platforms = [...(existing.data.platforms || [])];
        const idx = platforms.findIndex(p => p.platform === result.data.platform);
        if (idx >= 0) {
          platforms[idx] = { ...platforms[idx], ...result.data };
        } else {
          platforms.push(result.data);
        }
        const updated = {
          ...existing,
          data: { ...existing.data, platforms },
          timestamp: result.timestamp,
        };
        return {
          stageResults: state.stageResults.map(s =>
            s.stage === 'A4' && s.resultType === 'platform_status' ? updated : s
          ),
        };
      } else {
        // Create new with first platform
        return {
          stageResults: [...state.stageResults, {
            ...result,
            data: { platforms: [result.data] },
          }],
        };
      }
    });
    return;
  }
  // Non-A4: append normally
  set(state => ({ stageResults: [...state.stageResults, result] }));
}
```

#### Platform Row Visual Specifications

| Element | Specification |
|---------|---------------|
| **Row Layout** | `display: grid`, `grid-template-columns: 18px 72px 64px 1fr`, `align-items: center`, `gap: 6px`, `height: 26px` |
| **Success Icon** | `RiCheckLine` 14px, `color: var(--success)` |
| **Failed Icon** | `RiCloseLine` 14px, `color: var(--error)` |
| **Waiting Icon** | Empty circle `w-3 h-3`, `border: 1.5px solid var(--text-disabled)`, `border-radius: 50%` |
| **Fetching Icon** | `RiLoader4Line` 14px, `color: var(--warning)`, `animation: spin 1s linear infinite` |
| **Platform Name** | `font-size: 12px`, `color: var(--text-primary)` |
| **Progress Text** | `font-size: 11px`. Success: `color: var(--text-secondary)`. Failed: `color: var(--error)`. Waiting: `color: var(--text-disabled)`. Fetching: `color: var(--warning)` |
| **Detail Text** | `font-size: 11px`, `color: var(--text-tertiary)`. Success: "Mentions: N". Failed: error reason. Waiting: blank. Fetching: blank |
| **Row Transition** | Status change: icon cross-fades (150ms). New detail text fades in (200ms) |

#### Header Badge for A4

The status badge in the A4 card header shows progress as "N/4" where N = number of
completed (success + failed) platforms.

- All waiting: "0/4", badge style = in-progress (amber)
- Some done: "2/4", badge style = in-progress (amber)
- All done: "3/4" or "4/4", badge style = completed (green) if any success, error (red) if all failed

---

### 3C. MiniProgress Enhancement

#### Current State

`MiniProgress.tsx` shows a collapsible list of 5 steps (A1-A5) with status icons.
The summary bar shows "Analyzing... 3/5".

#### Enhancements

Two additions to MiniProgress:

1. **Estimated Remaining Time** in the summary bar
2. **Global Progress Bar** consuming `executionProgress` store data

#### Enhanced Layout

```
+-----------------------------------------------------------------------+
|  [Spinner] Analyzing...  3/5  ~~  ~1 min remaining        [v]        |
|  [========================================                  ]  65%    |
|-----------------------------------------------------------------------|
|  [v] A1 Brand Analysis              Completed                        |
|  [v] A2 User Personas               Completed                        |
|  [*] A3 Question Generation          In Progress                     |
|  [ ] A4 Data Fetch                   Waiting                         |
|  [ ] A5 Data Analytics               Waiting                         |
+-----------------------------------------------------------------------+
```

#### Summary Bar Enhancement

```
CURRENT:
[Spinner] Analyzing...  3/5                                    [v]

ENHANCED:
[Spinner] Analyzing...  3/5  |  ~1 min remaining              [v]
```

The estimated time is separated by a `|` divider (`color: var(--text-disabled)`).

Estimation text: `font-size: 11px`, `color: var(--text-disabled)`.

Time estimation logic (static heuristic):
```
A1: 10s, A2: 15s, A3: 5s, A4: 60s, A5: 30s
Remaining = sum of pending steps' estimates + 0.5 * in_progress step estimate
Display: < 60s => "~Ns", >= 60s => "~Nm"
```

#### Global Progress Bar

Positioned between the summary bar and the step list. Consumes `executionProgress.progress`
from the store.

```
[=======================================                       ]  65%
```

| Element | Specification |
|---------|---------------|
| **Track** | `width: 100%`, `height: 3px`, `background: var(--bg-tertiary)`, `border-radius: 2px`, `margin: 6px 12px` |
| **Fill** | `height: 100%`, `background: var(--brand-primary)`, `border-radius: 2px`, `transition: width 500ms ease-out` |
| **Percentage Text** | `font-size: 10px`, `color: var(--text-disabled)`, right-aligned below bar |
| **Progress Message** | `font-size: 10px`, `color: var(--text-disabled)`, left-aligned below bar. Source: `executionProgress.message` |

#### Accessibility

- Progress bar: `role="progressbar"`, `aria-valuenow={percentage}`, `aria-valuemin="0"`, `aria-valuemax="100"`, `aria-label="Analysis progress"`
- Estimated time: included in `aria-live="polite"` region so screen readers announce changes
- Step list: `role="list"`, each step `role="listitem"` with `aria-label` including status

---

### 3D. StageResultCard vs ActionLog: Design Decision

#### The Problem

The architecture review flagged a potential visual conflict: ActionLog (collapsible
technical log) and StageResultCard (structured result card) both appear in the message
flow during execution. If both render for each agent stage, the Chat panel becomes
cluttered.

#### Analysis

Current ActionLog behavior:
- Renders as a collapsed "Executed N steps" bar after each agent completes
- Expanded view shows technical details (LLM calls, searches, parsing)
- Visual: `bg-[#111111]`, `border-[#2A2A2A]`, `rounded-xl`, compact

StageResultCard behavior:
- Renders as an expanded card showing user-facing results
- Visual: `bg-[#1A1A1A]`, `border-[#333333]`, `rounded-[10px]`, slightly larger

The two components serve **fundamentally different audiences**:
- ActionLog: for power users / developers who want to see what the system did
- StageResultCard: for business users who want to see what the system produced

#### Decision: COEXIST with Visual Hierarchy

**StageResultCard replaces the need to expand ActionLog for most users**, but ActionLog
is NOT removed. The relationship is:

1. **StageResultCard renders first** (above ActionLog) for the same stage
2. **ActionLog renders collapsed** (below StageResultCard) and is visually de-emphasized
3. Users who want technical details can still expand ActionLog

```
Chat Panel Layout During Execution:

  [User Message: "Analyze Xiaomi brand"]

  [MiniProgress: Analyzing... 2/5  ~2 min remaining]
  [===========================                       ] 45%

  [StageResultCard: A1 Brand Analysis -- Completed]
  |  Brand: Xiaomi
  |  Industry: Consumer Electronics
  |  Competitors: Huawei, Apple, OPPO, vivo

  [ActionLog: A1 -- collapsed -- "Executed 3 steps"]

  [StageResultCard: A2 User Personas -- Completed]
  |  Generated 3 user personas...

  [ActionLog: A2 -- collapsed -- "Executed 2 steps"]

  [StageResultCard: A4 Data Fetch -- 2/4]
  |  [v] DeepSeek   12/12  Mentions: 8
  |  [v] Doubao     12/12  Mentions: 6
  |  [ ] Kimi       Fetching...
  |  [ ] Hunyuan    Waiting
```

#### Visual Differentiation

To ensure the two components do not blur together:

| Property | StageResultCard | ActionLog |
|----------|----------------|-----------|
| **Background** | `#1A1A1A` (var(--bg-secondary)) | `#111111` (darker) |
| **Border** | `#333333` (var(--border-default)) | `#2A2A2A` (subtler) |
| **Border Radius** | `10px` | `12px` (consistent with existing) |
| **Left Accent** | `3px solid var(--brand-primary)` (subtle indicator) | None |
| **Default State** | Expanded (showing data) | Collapsed (one line) |
| **Font Size** | Body at 12px | Summary at 12px, details at 11px |
| **Purpose Signal** | Stage icon + name in header | Checkmark/spinner + "Executed N steps" |

The left accent on StageResultCard (a thin 3px indigo bar on the left edge) creates
a visual "track" that connects the cards vertically, giving users a sense of progress
flow.

#### Ordering Rule

Within a single agent stage's output area:
1. StageResultCard first (if stage_result event received)
2. DegradationNotice (if degradation occurred, e.g., A2 fallback)
3. ActionLog last (always, collapsed)

#### After Execution Completes

When `execution_complete` fires:
- StageResultCards fade to 70% opacity (2s delay, 500ms transition)
- MiniProgress shows "Analysis Complete" in green
- The final report card in Canvas panel takes visual priority

This prevents old stage cards from competing with the final deliverable.

---

## Global CSS Additions

The following CSS keyframes and utility classes need to be added to
`D:\AGEO\frontend\src\app\globals.css`:

```css
/* Slide Up animation (for StageResultCard entry) */
@keyframes slide-up {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-slide-up {
  animation: slide-up 200ms ease-out forwards;
}

/* Fade to background (for stage cards after execution complete) */
@keyframes fade-to-bg {
  from {
    opacity: 1;
  }
  to {
    opacity: 0.5;
  }
}

.animate-fade-to-bg {
  animation: fade-to-bg 500ms ease-out 2s forwards;
}
```

---

## Accessibility Audit & Requirements

Cycle 1 received a 5/10 accessibility score. This section specifies mandatory
requirements to reach 8/10.

### WCAG AA Color Contrast Verification

All text/background combinations used in this design:

| Text Color | Background | Contrast Ratio | Pass? |
|-----------|-----------|----------------|-------|
| `#FFFFFF` (--text-primary) | `#1A1A1A` (--bg-secondary) | 14.5:1 | Yes |
| `#A3A3A3` (--text-secondary) | `#1A1A1A` | 6.3:1 | Yes |
| `#8A8A8A` (--text-tertiary) | `#1A1A1A` | 4.6:1 | Yes (AA) |
| `#6B6B6B` (--text-muted) | `#1A1A1A` | 3.4:1 | **NO** |
| `#525252` (--text-disabled) | `#1A1A1A` | 2.4:1 | **NO** |
| `#22C55E` (--success) | `#1A1A1A` | 6.1:1 | Yes |
| `#F59E0B` (--warning) | `#1A1A1A` | 7.2:1 | Yes |
| `#EF4444` (--error) | `#1A1A1A` | 4.6:1 | Yes (AA) |
| `#FCA5A5` (risk title high) | `rgba(239,68,68,0.06)` on `#1A1A1A` | 7.8:1 | Yes |
| `#FCD34D` (risk title medium) | `rgba(245,158,11,0.06)` on `#1A1A1A` | 10.1:1 | Yes |

**Action Items**:
- `--text-muted` (#6B6B6B) and `--text-disabled` (#525252) fail WCAG AA.
  These colors are used ONLY for decorative/supplementary text that has a
  non-color alternative (e.g., formulas, disclaimers, percentage labels that
  duplicate visual information).
  **Rule**: Never use `--text-muted` or `--text-disabled` as the sole carrier
  of essential information. Always pair with `--text-secondary` or higher.

### ARIA Requirements by Component

| Component | ARIA Requirements |
|-----------|-------------------|
| **Trend Chart Dimension Pills** | `role="radiogroup"`, `aria-label="Select trend dimension"`. Each pill: `role="radio"`, `aria-checked` |
| **Trend Chart** | `aria-label` with data summary. Data points focusable with `tabindex="0"` |
| **Snapshot List** | `role="region"`, `aria-label="Analysis History"`. Toggle: `aria-expanded`. Rows: `role="list"` + `role="listitem"` |
| **Delta Indicator** | `role="status"`, `aria-live="polite"`. Full text in `aria-label` |
| **Report Tab Bar** | `role="tablist"`. Tabs: `role="tab"`, `aria-selected`, `aria-controls`. Panels: `role="tabpanel"`, `aria-labelledby` |
| **Platform Analysis Cards** | `role="article"`, `aria-label` with platform name |
| **Recommendation Cards** | `role="article"`, `aria-label` with priority and title |
| **Risk Alerts** | High: `role="alert"`. Medium/Low: `role="status"` |
| **Competitor Matrix** | `role="table"`, `role="columnheader"`, `role="row"`, `role="cell"` |
| **StageResultCard** | `role="status"`, `aria-live="polite"`, `aria-label` with stage name and status |
| **A4 Platform Card** | `aria-live="polite"` (updates in place). Each row `aria-label` with full status |
| **MiniProgress Bar** | `role="progressbar"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"` |
| **MiniProgress Time** | Within `aria-live="polite"` region |

### Keyboard Navigation

| Component | Keyboard Behavior |
|-----------|-------------------|
| **Dimension Toggle Pills** | `Tab` to focus group. `Arrow Left/Right` to move between pills. `Enter/Space` to select |
| **Report Tab Bar** | `Tab` to focus tab bar. `Arrow Left/Right` to navigate tabs. `Enter/Space` to activate. `Home/End` for first/last tab |
| **Snapshot List Toggle** | `Enter/Space` to expand/collapse |
| **StageResultCard "Show more"** | `Enter/Space` to expand truncated content |
| **ActionLog Toggle** | `Enter/Space` to expand/collapse (existing behavior) |
| **MiniProgress Toggle** | `Enter/Space` to expand/collapse (existing behavior) |

### Screen Reader Announcements

- When a StageResultCard appears: announce "{Stage Name} completed. {Summary}."
  Example: "Brand Analysis completed. Brand: Xiaomi, Industry: Consumer Electronics."
- When A4 platform status updates: announce "Data Fetch progress: {N} of 4 platforms complete."
- When MiniProgress estimated time changes significantly (> 30s difference): announce new estimate.
- When execution completes: announce "Analysis complete. Report is ready."

---

## Component Implementation Summary

### New Components

| Component | File Path | Responsibility |
|-----------|-----------|----------------|
| `StageResultCard` | `frontend/src/components/chat/StageResultCard.tsx` | Renders 5 types of stage result cards in chat flow |
| `SnapshotTrendChart` | `frontend/src/components/dashboard/SnapshotTrendChart.tsx` | Enhanced trend chart with dimension toggle and snapshot markers |
| `SnapshotListSection` | `frontend/src/components/dashboard/SnapshotListSection.tsx` | Collapsible snapshot history list |
| `DeltaIndicator` | `frontend/src/components/canvas/contents/DeltaIndicator.tsx` | "vs previous" delta display, reusable |
| `IndustryInsightsSection` | `frontend/src/components/canvas/contents/IndustryInsightsSection.tsx` | Industry tab content |
| `PlatformAnalysisCard` | `frontend/src/components/canvas/contents/PlatformAnalysisCard.tsx` | Per-platform detailed card |
| `RecommendationCard` | `frontend/src/components/canvas/contents/RecommendationCard.tsx` | Actionable recommendation card |
| `CompetitorMatrix` | `frontend/src/components/canvas/contents/CompetitorMatrix.tsx` | Competitor comparison table |
| `RiskAlertCard` | `frontend/src/components/canvas/contents/RiskAlertCard.tsx` | Risk alert with severity styling |

### Modified Components

| Component | File Path | Changes |
|-----------|-----------|---------|
| `MiniProgress` | `frontend/src/components/chat/MiniProgress.tsx` | Add estimated time, global progress bar, consume `executionProgress` |
| `ReportContent` | `frontend/src/components/canvas/contents/ReportContent.tsx` | Add 2 new tabs (Industry, Risks), integrate DeltaIndicator, enhanced Platform/Competitor/Recommendations tabs |
| `ChatPanel` | `frontend/src/components/chat/ChatPanel.tsx` | Render StageResultCards from `stageResults` store |
| `DashboardPage` | `frontend/src/components/dashboard/DashboardPage.tsx` | Integrate SnapshotTrendChart replacing simple VisibilityTab |
| `VisibilityTab` | `frontend/src/components/dashboard/VisibilityTab.tsx` | Consume snapshot trend API, add SnapshotListSection |
| `conversationStore` | `frontend/src/stores/conversationStore.ts` | Add `stageResults[]`, `addStageResult()`, `clearStageResults()`, A4 merge logic |
| `useWebSocket` | `frontend/src/hooks/useWebSocket.ts` | Listen for `stage_result` events |
| `globals.css` | `frontend/src/app/globals.css` | Add `animate-slide-up`, `animate-fade-to-bg` |

### Store Changes (conversationStore.ts)

```typescript
// New state fields
stageResults: StageResult[];

// New actions
addStageResult: (result: StageResult) => void;
clearStageResults: () => void;

// Modified actions
startExecution: () => void;  // Add: clearStageResults()
reset: () => void;           // Add: stageResults: []
```

### Data Flow for StageResultCards

```
Backend (agent node completion)
    |
    v
WebSocket event: "stage_result" { stage, stageName, resultType, data, timestamp }
    |
    v
useWebSocket.ts: socket.on('stage_result', handler)
    |
    v
conversationStore.addStageResult(payload)
  -- if resultType === 'platform_status': merge into existing A4 entry
  -- else: append to stageResults[]
    |
    v
ChatPanel.tsx: reads stageResults from store
    |
    v
StageResultCard components rendered in message flow area
  (after MiniProgress, before InputArea)
```

---

## Design Validation Checklist

- [ ] Can a first-time user understand what each StageResultCard means without explanation?
- [ ] Does the A4 cumulative card clearly show which platforms succeeded vs failed?
- [ ] Is the delta indicator distinguishable for colorblind users (arrow + sign + text)?
- [ ] Does the trend chart convey meaningful information with only 2 data points?
- [ ] Are the 6 report tabs scannable without reading each label carefully?
- [ ] Does the P0/P1/P2 priority badge convey urgency through the left border accent
  even when the badge text is not read?
- [ ] Is the StageResultCard vs ActionLog visual distinction clear enough that users
  understand they serve different purposes?
- [ ] Does the MiniProgress estimated time reduce anxiety without creating false precision?
  (Using "~1 min" not "47 seconds")
- [ ] After execution completes, do StageResultCards fade appropriately so the final
  report gets visual priority?
- [ ] Are all interactive elements reachable by keyboard?
- [ ] Does the screen reader experience make sense for a visually impaired user waiting
  for analysis results?
- [ ] Is the Risks tab visually distinct enough from the Recommendations tab that users
  don't confuse them?

---

## Cognitive Load Analysis

### Chat Panel During Execution (Most Complex State)

The chat panel during a full A1-A5 execution will display:
- 1 user message
- 1 MiniProgress component (with time estimate and progress bar)
- Up to 5 StageResultCards (A1, A2, A3, A4, A5)
- Up to 5 ActionLogs (collapsed)

This is **10 visual elements** in ~400px width. Risk of overwhelm.

**Mitigations**:
1. StageResultCards are compact (max 140px height). Total stack: ~700px, scrollable
2. ActionLogs are collapsed (single line each). Total: ~200px
3. Cards use consistent visual language -- once you understand one, you understand all
4. The left accent bar creates a visual "progress rail" guiding the eye downward
5. After completion, cards fade to 50% opacity, leaving only the report

### Report Panel (6 Tabs)

6 tabs is at the upper limit of comfortable tab navigation. Miller's 7 +/- 2 applies.

**Mitigations**:
1. Tabs are ordered by importance: Overview (most used) first, Risks (least used) last
2. Scrollable tab bar prevents wrapping
3. Each tab has a single-word label for fast scanning
4. Default tab (Overview) contains the most critical information

---

## Open Design Questions for Review

1. **StageResultCard Persistence**: After page refresh during execution, should
   StageResultCards be reconstructable from backend state? Current proposal: No,
   they are ephemeral. On refresh, user sees MiniProgress (persisted via
   executionProgress events) but not individual stage cards. This is acceptable
   because the final report contains all the data.

2. **Trend Chart Click-to-Snapshot**: Should clicking a data point on the trend chart
   open the corresponding snapshot's report in the Canvas? This creates a navigation
   pattern that does not exist today. Recommend deferring to Cycle 3.

3. **A4 Card Animation**: When 4 platforms complete rapidly (API-first phase, all
   within 2-3 seconds), should we stagger the row updates (100ms delay between each)
   for visual effect, or update all at once? Recommend staggering for better
   perception of "the system is actively working."

4. **Report Tab Memory**: When switching between sessions, should the active report
   tab be remembered? Recommend: No, always default to Overview. Users return to
   Overview for the headline score.

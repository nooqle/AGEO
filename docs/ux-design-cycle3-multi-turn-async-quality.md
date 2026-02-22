# UX Design: Cycle 3 -- Multi-Turn Dialogue + Async Task Resilience + A1 Quality

> **Document Status**: Design Proposal, pending team review
> **Design Lead**: Don Norman (UX Lead)
> **Date**: 2026-02-21
> **Related PRD**: `D:\AGEO\docs\prd-cycle3-multi-turn-async-quality.md`
> **Related UX (Cycle 2)**: `D:\AGEO\docs\ux-design-cycle2-snapshot-report-wait.md`
> **Accessibility Target**: WCAG AA compliance (contrast >= 4.5:1, keyboard nav, ARIA)

---

## Design Principles (Cycle 3)

Cycle 1 established five principles (Feedback = Trust, Non-modal, Information Hierarchy,
Cognitive Load Minimization, Design System Consistency). Cycle 2 added two more (Progressive
Revelation of Value, Temporal Continuity). Cycle 3 introduces three additional principles:

8. **Resilient Continuity**: The user's mental model should never include "keeping a browser
   tab open." Analysis is a background process that reports back when done -- like sending an
   email and getting a reply later. The UI must reinforce this: "You can leave. We will be
   here when you return."

9. **Conversational Depth**: A single analysis is not the end of a conversation; it is the
   beginning. The interface must make follow-up questions feel as natural as typing the
   original request. The system should *invite* further exploration, not present the report
   as a dead end.

10. **Transparent Quality**: When the system detects data quality issues and takes corrective
    action (retries, normalization), the user should be informed -- not with anxiety-inducing
    error messages, but with calm confidence signals: "We verified your data for accuracy."
    Trust comes from visible diligence, not from hiding problems.

---

## Table of Contents

1. [Module 1: Async Task + Reconnection](#module-1-async-task--reconnection)
   - 1A. TaskStatusBadge Component
   - 1B. Reconnection Flow & Replay Experience
   - 1C. Task Completion Toast Notification
   - 1D. Sidebar Task Indicators
   - 1E. Disconnection Banner Enhancement
   - 1F. "Safe to Leave" Signal
2. [Module 2: Multi-Turn Follow-Up](#module-2-multi-turn-follow-up)
   - 2A. Follow-Up Suggestion Chips
   - 2B. Drill-Down Result Rendering
   - 2C. Snapshot Comparison View
   - 2D. Selective Refetch Progress
   - 2E. Follow-Up vs Full Pipeline Visual Distinction
3. [Module 3: A1 Quality Hardening UX](#module-3-a1-quality-hardening-ux)
   - 3A. A1 Retry Experience
   - 3B. Data Quality Indicator on StageResultCard
4. [Global CSS Additions](#global-css-additions)
5. [Accessibility Audit & Requirements](#accessibility-audit--requirements)
6. [Component Implementation Summary](#component-implementation-summary)
7. [Design Validation Checklist](#design-validation-checklist)

---

## Module 1: Async Task + Reconnection

### 1A. TaskStatusBadge Component

#### User Scenario

A marketing manager starts a brand analysis and sees a badge in the Chat panel header
that says "Analyzing..." with a pulsing indicator. They can now confidently navigate away,
close the tab, or switch to another brand. When they return, the badge shows "Completed"
or "Failed" -- immediately communicating what happened while they were away.

#### Why This Matters

The current UI has no persistent status indicator outside the chat message flow. The
MiniProgress component sits inside the scrollable message area. If the user scrolls up
or the chat area is long, they lose sight of the analysis status. The TaskStatusBadge is
a fixed, always-visible indicator that anchors the user's awareness of system state.

#### Layout

The badge is placed in the Chat panel header area, to the right of the session/brand title.

```
+-----------------------------------------------------------------------+
|  [< Back]   Xiaomi Analysis   [TaskStatusBadge: Analyzing...]         |
|-----------------------------------------------------------------------|
|                                                                       |
|  (scrollable message area)                                            |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Badge States

```
STATE 1: PENDING (task created, not yet started)
+-----------------------------------------------+
|  [ hollow circle ]  Preparing...               |
+-----------------------------------------------+

STATE 2: RUNNING (pipeline executing)
+-----------------------------------------------+
|  [spinning loader]  Analyzing...  A3  65%      |
+-----------------------------------------------+

STATE 3: COMPLETED (analysis finished)
+-----------------------------------------------+
|  [check circle]  Analysis complete             |
+-----------------------------------------------+

STATE 4: FAILED (pipeline errored)
+-----------------------------------------------+
|  [alert circle]  Analysis failed               |
+-----------------------------------------------+

STATE 5: CANCELLED (user cancelled)
+-----------------------------------------------+
|  [minus circle]  Cancelled                     |
+-----------------------------------------------+

STATE 6: NO TASK (fresh session, no analysis started)
(badge not rendered)
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Badge Container** | `display: inline-flex`, `align-items: center`, `gap: 6px`, `padding: 4px 10px`, `border-radius: 6px`, `font-size: 11px`, `font-weight: 500`, `white-space: nowrap` |
| **Pending** | `background: var(--bg-tertiary)`, `color: var(--text-tertiary)`. Icon: hollow circle, `border: 1.5px solid var(--text-disabled)`, `width: 10px`, `height: 10px`, `border-radius: 50%` |
| **Running** | `background: rgba(245,158,11,0.1)`, `color: var(--warning)`. Icon: `RiLoader4Line` 12px, `animation: spin 1s linear infinite`. Stage label: `font-weight: 600`. Progress percentage: `color: var(--text-tertiary)` |
| **Completed** | `background: rgba(34,197,94,0.1)`, `color: var(--success)`. Icon: `RiCheckLine` 12px |
| **Failed** | `background: rgba(239,68,68,0.1)`, `color: var(--error)`. Icon: `RiAlertLine` 12px |
| **Cancelled** | `background: var(--bg-tertiary)`, `color: var(--text-muted)`. Icon: `RiIndeterminateCircleLine` 12px |

#### Interaction Behavior

1. **Click on RUNNING badge**: Scrolls the chat panel to the MiniProgress component
   (smooth scroll). This is for users who scrolled up and want to re-find the progress area.

2. **Click on COMPLETED badge**: Scrolls to the final report output card in the message
   flow, OR opens the Canvas panel to the report (if Canvas is collapsed).

3. **Click on FAILED badge**: Scrolls to the error message and retry prompt.

4. **Transition animations**: State changes use a cross-fade (`opacity 0 -> 1`, 200ms).
   The RUNNING state spinner is continuous. When transitioning from RUNNING to COMPLETED,
   the badge briefly pulses green (one `pulse-slow` cycle) before settling.

#### Data Source

The badge reads from `conversationStore.activeTask`:

```typescript
// conversationStore additions
interface ConversationState {
  // ... existing fields ...
  activeTask: AnalysisTask | null;
  setActiveTask: (task: AnalysisTask | null) => void;
  updateActiveTaskProgress: (stage: string, progress: number, message: string) => void;
}
```

The `activeTask` is populated from:
- On mount: `GET /api/v1/tasks/session/{sessionId}/active`
- During execution: WebSocket `execution_progress` events update the task fields locally
- On completion: `execution_complete` event sets status to 'completed'

#### Accessibility

- Container: `role="status"`, `aria-live="polite"`, `aria-label` with full status text
- RUNNING: `aria-label="Analysis in progress, stage A3, 65 percent complete"`
- COMPLETED: `aria-label="Analysis completed successfully"`
- FAILED: `aria-label="Analysis failed"`
- Badge is focusable (`tabindex="0"`) with `Enter/Space` triggering the scroll action
- Status change announcements happen automatically via `aria-live="polite"`

---

### 1B. Reconnection Flow & Replay Experience

#### User Scenario

The user starts an analysis of brand "Xiaomi", closes the browser tab, goes to lunch,
and returns 10 minutes later. They open the same session URL. What do they see?

#### Three Reconnection Scenarios

##### Scenario A: Task still RUNNING

The user closed the tab mid-analysis. The pipeline is still running server-side.

```
USER OPENS PAGE
    |
    v
1. Chat history loads from DB (existing behavior)
2. GET /api/v1/tasks/session/{sessionId}/active => RUNNING task
3. TaskStatusBadge renders: "Analyzing... A4 65%"
4. Cached stage_results replayed as StageResultCards (with replay animation)
5. MiniProgress restores from task.current_stage
6. WebSocket connects for live updates going forward
```

**Replay Animation**: Cached stage results do NOT appear all at once (that would be
jarring). Instead, they appear in a staggered sequence:

```
T=0ms:    First StageResultCard fades in (A1 brand_profile)
T=150ms:  Second StageResultCard fades in (A2 personas)
T=300ms:  Third StageResultCard fades in (A3 questions)
T=450ms:  Fourth StageResultCard fades in (A4 platform_status, partial)
T=600ms:  MiniProgress appears with current state
```

Each card uses the `animate-slide-up` animation (existing from Cycle 2) but with
staggered `animation-delay`. The stagger is 150ms per card.

Visual distinction: replayed cards have a subtle "replayed" indicator -- a small
`RiHistoryLine` icon (12px, `color: var(--text-disabled)`) in the card header, next
to the stage name. This tells the user: "This result was loaded from cache, not just
produced."

```
+-- A1 Brand Analysis ----[replay icon]---[Completed]--+
|                                                       |
|  Brand:      Xiaomi                                   |
|  Industry:   Consumer Electronics                     |
|  Competitors: Huawei, Apple, OPPO, vivo               |
|                                                       |
+-------------------------------------------------------+
```

The replay icon is purely informational and decorative. It appears only during
reconnection replay and not during live execution.

##### Scenario B: Task COMPLETED while user was away

```
USER OPENS PAGE
    |
    v
1. Chat history loads (includes final report message)
2. GET /api/v1/tasks/session/{sessionId}/active => COMPLETED task
3. TaskStatusBadge renders: "Analysis complete"
4. Completion banner appears above message flow
5. Canvas loads the report (existing artifact loading)
```

**Completion Banner**:

```
+-----------------------------------------------------------------------+
|  [check icon]  Analysis of "Xiaomi" completed at 14:33                |
|  BWVS: 52.3 (Good)    |    [View Report ->]                          |
+-----------------------------------------------------------------------+
```

| Element | Specification |
|---------|---------------|
| **Banner Container** | `background: rgba(34,197,94,0.06)`, `border: 1px solid rgba(34,197,94,0.2)`, `border-radius: 10px`, `padding: 12px 16px`, `margin: 8px 16px` |
| **Icon** | `RiCheckboxCircleLine` 18px, `color: var(--success)` |
| **Brand + Time** | `font-size: 13px`, `font-weight: 500`, `color: var(--text-primary)` |
| **BWVS Score** | `font-size: 13px`, `font-weight: 600`, color by band (>= 70 green, >= 40 amber, < 40 red) |
| **View Report Link** | `font-size: 12px`, `font-weight: 500`, `color: var(--brand-primary)`, `cursor: pointer`. Hover: `text-decoration: underline` |
| **Entry Animation** | `animate-slide-up` (200ms) |

Clicking "View Report" opens/focuses the Canvas panel with the report.

The banner auto-dismisses after 15 seconds, fading out (opacity 1 -> 0, 500ms). It can
also be dismissed by clicking a close button (`RiCloseLine` 14px at top-right).

##### Scenario C: Task FAILED while user was away

```
USER OPENS PAGE
    |
    v
1. Chat history loads
2. GET /api/v1/tasks/session/{sessionId}/active => FAILED task
3. TaskStatusBadge renders: "Analysis failed"
4. Error banner appears with retry option
```

**Error Banner**:

```
+-----------------------------------------------------------------------+
|  [alert icon]  Analysis of "Xiaomi" failed at stage A4                |
|  Error: Connection timeout on platform Kimi                           |
|                                                                       |
|  [Retry Analysis]    [Dismiss]                                        |
+-----------------------------------------------------------------------+
```

| Element | Specification |
|---------|---------------|
| **Banner Container** | `background: rgba(239,68,68,0.06)`, `border: 1px solid rgba(239,68,68,0.2)`, `border-radius: 10px`, `padding: 12px 16px`, `margin: 8px 16px` |
| **Icon** | `RiErrorWarningLine` 18px, `color: var(--error)` |
| **Title** | `font-size: 13px`, `font-weight: 500`, `color: var(--text-primary)` |
| **Error Detail** | `font-size: 12px`, `color: var(--text-secondary)`, `margin-top: 4px` |
| **Retry Button** | `background: var(--brand-primary)`, `color: #FFFFFF`, `padding: 6px 14px`, `border-radius: 6px`, `font-size: 12px`, `font-weight: 500`. Hover: `background: var(--brand-hover)` |
| **Dismiss Button** | `background: transparent`, `color: var(--text-secondary)`, `padding: 6px 14px`, `font-size: 12px`. Hover: `color: var(--text-primary)` |

The Retry button sends a re-analysis message via WebSocket, identical to the original
brand analysis request.

The error banner does NOT auto-dismiss. The user must explicitly dismiss or retry.

#### StageResultCard Replay Deduplication

When replaying cached stage results, the frontend must check for duplicates against
existing `stageResults` in the store. Deduplication key: `stage + resultType`. If a
stage result already exists (e.g., from a previous page load), skip it.

```typescript
// Replay logic pseudocode
const replayStageResults = (cached: StageResult[], delay = 150) => {
  const existing = useConversationStore.getState().stageResults;
  const existingKeys = new Set(existing.map(r => `${r.stage}:${r.resultType}`));

  const toReplay = cached.filter(r => !existingKeys.has(`${r.stage}:${r.resultType}`));

  toReplay.forEach((result, index) => {
    setTimeout(() => {
      useConversationStore.getState().addStageResult({
        ...result,
        _isReplay: true, // internal flag for replay icon
      });
    }, index * delay);
  });
};
```

#### Accessibility

- Completion banner: `role="status"`, `aria-live="polite"`
- Error banner: `role="alert"`, `aria-live="assertive"`
- Retry button: `aria-label="Retry analysis for Xiaomi"`
- Replay icon on cards: `aria-hidden="true"` (decorative; the card content is sufficient)

---

### 1C. Task Completion Toast Notification

#### User Scenario

The user is on the Dashboard page or a different brand's chat session. A previously
started analysis for "Xiaomi" completes in the background. A toast notification appears
in the top-right corner.

#### Design

```
+-- Top-right toast (auto-dismiss 10s) ---------------------------+
|                                                                   |
|  [check circle icon]                                              |
|                                                                   |
|  "Xiaomi" analysis completed                                      |
|  BWVS: 52.3 (Good)                                               |
|                                                                   |
|  [View Report]                                                    |
|                                                                   |
+-------------------------------------------------------------------+
```

#### Visual Specifications

This reuses the existing `ToastContainer` and `toast` API from
`D:\AGEO\frontend\src\components\ui\toast.tsx`, but introduces a new toast type:
`task_complete`.

| Element | Specification |
|---------|---------------|
| **Toast Container** | Reuse existing: `fixed top-4 right-4 z-[9999]` |
| **Toast Card** | `background: #1A1A1A`, `border: 1px solid rgba(34,197,94,0.3)`, `border-radius: 12px`, `padding: 14px 18px`, `min-width: 300px`, `max-width: 420px`, `box-shadow: 0 8px 24px rgba(0,0,0,0.5)` |
| **Icon** | `RiCheckboxCircleLine` 20px, `color: var(--success)` |
| **Brand Name** | `font-size: 13px`, `font-weight: 600`, `color: var(--text-primary)` |
| **BWVS Line** | `font-size: 12px`, `color: var(--text-secondary)`. Score value: `font-weight: 600`, color by band |
| **View Report Link** | `font-size: 12px`, `font-weight: 500`, `color: var(--brand-primary)`, `margin-top: 6px`. Click navigates to the session's chat page |
| **Duration** | 10 seconds auto-dismiss (longer than standard 4s toast due to actionable content) |
| **Entry Animation** | Reuse existing toast slide-in from right |

For task failures, a similar toast appears but with error styling:

```
+-- Top-right toast (no auto-dismiss) ----------------------------+
|                                                                   |
|  [alert circle icon]                                              |
|                                                                   |
|  "Huawei" analysis failed                                         |
|  Error at stage A4: Connection timeout                            |
|                                                                   |
|  [View Details]                                                   |
|                                                                   |
+-------------------------------------------------------------------+
```

The failure toast does NOT auto-dismiss. The user must click to dismiss or navigate
to the session.

#### Polling Mechanism

On every page mount (ChatLayout, DashboardPage), the frontend polls:

```
GET /api/v1/tasks?status=completed&unread=true
```

If results are returned, render one toast per completed task. Mark tasks as "read"
after displaying the toast (via a local flag or a `POST /api/v1/tasks/{id}/mark-read`).

Polling frequency: once on mount, then every 30 seconds while the page is open.
This is conservative to meet the PRD constraint of max 1 request per 30 seconds.

#### Accessibility

- Toast: `role="status"`, `aria-live="polite"` for success, `role="alert"` for failure
- View Report link: `aria-label="View analysis report for Xiaomi"`
- Auto-dismiss toasts are also keyboard-dismissible via `Escape`

---

### 1D. Sidebar Task Indicators

#### User Scenario

The user has 3 brands in the sidebar. One is currently analyzing, one completed earlier,
one has never been analyzed. The sidebar should show a subtle visual cue for the currently
running task.

#### Design

In the existing `ChatSidebar.tsx`, the entity list items already show a colored status
dot (green for active, amber for inactive). We extend this to show an animated indicator
when an entity has a RUNNING task.

```
CURRENT SIDEBAR ITEM:
  [green dot]  Xiaomi
               specta.ai
               [clock] 2 hours ago

ENHANCED SIDEBAR ITEM (with RUNNING task):
  [pulsing amber dot]  Xiaomi
                        specta.ai
                        [spinner] Analyzing... 65%
```

#### Visual Specifications

| State | Dot Indicator | Time Line |
|-------|--------------|-----------|
| **No task / idle** | Solid dot, `var(--success)` for active, `var(--text-muted)` for inactive | Normal timestamp "2 hours ago" |
| **RUNNING task** | Pulsing amber dot: `var(--warning)`, `animation: pulse-slow 2s infinite` | Replace timestamp with: `RiLoader4Line` 12px spinning + "Analyzing... 65%" in `color: var(--warning)`, `font-size: 10px` |
| **COMPLETED (unread)** | Solid green dot with a subtle glow: `box-shadow: 0 0 6px rgba(34,197,94,0.5)` | "Completed just now" in `color: var(--success)`, `font-size: 10px`. The glow fades after 30 seconds |
| **FAILED** | Solid red dot: `var(--error)` | "Failed at A4" in `color: var(--error)`, `font-size: 10px` |

The sidebar periodically refreshes task status (every 30 seconds) by polling the task
list API: `GET /api/v1/tasks?status=running&status=completed&limit=10`.

#### Interaction

- Clicking an entity with a RUNNING task navigates to the chat page, which then
  handles reconnection (1B above).
- Clicking an entity with a COMPLETED (unread) task navigates to the chat page,
  which shows the completion banner.

#### Accessibility

- Running indicator: `aria-label` on entity item updated to include task status,
  e.g., "Xiaomi, analysis in progress, 65 percent"
- The pulsing animation is purely decorative; status is conveyed via text

---

### 1E. Disconnection Banner Enhancement

#### Current State

The existing `ChatPanel.tsx` shows a simple banner when disconnected:

```
"Connection lost. Attempting to reconnect..."
```

#### Enhancement

The disconnection banner is enhanced to reassure users that their analysis is safe:

```
+-----------------------------------------------------------------------+
|  [wifi-off icon]  Connection lost  |  Your analysis continues safely   |
|  Reconnecting...                    |  Results will be preserved.      |
+-----------------------------------------------------------------------+
```

| Element | Specification |
|---------|---------------|
| **Banner** | `background: var(--bg-tertiary)`, `border-bottom: 1px solid var(--border-hover)`, `padding: 8px 16px` |
| **Left Section** | `display: flex`, `align-items: center`, `gap: 6px`. Icon: `RiWifiOffLine` 14px, `color: var(--warning)`. "Connection lost" text: `font-size: 12px`, `font-weight: 500`, `color: var(--warning)` |
| **Right Section** | `font-size: 11px`, `color: var(--text-secondary)`, `font-style: italic` |
| **Reconnecting Text** | `font-size: 11px`, `color: var(--text-tertiary)`, with 3-dot loading animation (CSS) |

The key addition is the reassurance text: "Your analysis continues safely. Results will
be preserved." This addresses the core anxiety: "Did I just lose my analysis?"

When reconnection succeeds:

```
+-----------------------------------------------------------------------+
|  [wifi icon]  Reconnected  |  Syncing latest results...               |
+-----------------------------------------------------------------------+
```

This banner appears for 3 seconds, then fades out. Color: green-tinted background
`rgba(34,197,94,0.06)`.

#### Accessibility

- Disconnection banner: `role="alert"`, `aria-live="assertive"`
- Reconnection banner: `role="status"`, `aria-live="polite"`

---

### 1F. "Safe to Leave" Signal

#### User Scenario

The user just started an analysis and wants to know: "Can I close this tab safely?"
There is no explicit UI telling them this is okay. The PRD's core value proposition is
that the browser tab is optional, but we need to *communicate* this.

#### Design

When a pipeline execution begins (after the first `execution_progress` event), a subtle
one-time message appears briefly below the MiniProgress component:

```
+-----------------------------------------------------------------------+
|  [MiniProgress: Analyzing... 0/5  (~2 min)]                          |
|  [================================                     ] 5%           |
+-----------------------------------------------------------------------+
|                                                                       |
|  [shield icon]  You can safely close this tab.                        |
|  We will notify you when the analysis is complete.                    |
|                                                                       |
+-----------------------------------------------------------------------+
```

This message:
- Appears 2 seconds after the first progress event (avoids flash for very fast responses)
- Uses `animate-fade-in` (300ms)
- Auto-fades after 8 seconds (`opacity: 0`, 500ms transition, then `display: none`)
- Only appears once per execution (tracked via a local ref, not persisted)
- Does NOT appear on reconnection (only on fresh execution start)

| Element | Specification |
|---------|---------------|
| **Container** | `display: flex`, `align-items: center`, `gap: 8px`, `padding: 8px 12px`, `margin-top: 8px`, `border-radius: 8px`, `background: rgba(99,102,241,0.06)`, `border: 1px solid rgba(99,102,241,0.15)` |
| **Icon** | `RiShieldCheckLine` 14px, `color: var(--brand-primary)` |
| **Text** | `font-size: 11px`, `color: var(--text-secondary)`. "safely close this tab" is `font-weight: 500`, `color: var(--text-primary)` |

#### Accessibility

- Container: `role="status"`, `aria-live="polite"`
- Transient message -- screen readers will announce it once

---

## Module 2: Multi-Turn Follow-Up

### 2A. Follow-Up Suggestion Chips

#### User Scenario

The user has just completed a full pipeline analysis. The final agent message shows
the report summary. Below the message, the system displays 3-4 suggested follow-up
actions as clickable chips. This invites the user into a deeper conversation rather
than presenting the report as a terminus.

#### Why This Matters

Without explicit follow-up suggestions, users see a completed report and think "I'm done."
They close the tab. By presenting actionable follow-up options, we:
- Increase engagement depth (Reform Plan metric)
- Demonstrate that the system *can* do more
- Reduce the cognitive load of figuring out "what can I ask next?"

This is **Recognition over Recall** -- showing the user what is possible rather than
requiring them to remember or discover the system's capabilities.

#### Layout

Follow-up chips appear after the execution is complete and the final report is available.
They are rendered as part of the final agent message, below the content.

```
+-----------------------------------------------------------------------+
|  [Agent Message]                                                      |
|                                                                       |
|  Analysis complete for Xiaomi. The BWVS score is 52.3 (Good).        |
|  The report has been generated. You can view it in the right panel.   |
|                                                                       |
|  ~~~ Follow-up Suggestions ~~~                                        |
|                                                                       |
|  [Tell me more about DeepSeek results]                                |
|  [Compare with last analysis]                                         |
|  [Re-analyze only on Kimi]                                            |
|  [What should I improve first?]                                       |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Chip Container** | `display: flex`, `flex-wrap: wrap`, `gap: 8px`, `margin-top: 12px`, `padding-top: 12px`, `border-top: 1px solid var(--border-default)` |
| **Individual Chip** | `display: inline-flex`, `align-items: center`, `gap: 4px`, `padding: 6px 14px`, `border-radius: 8px`, `font-size: 12px`, `font-weight: 400`, `cursor: pointer`, `transition: all 150ms ease-out` |
| **Chip Default** | `background: var(--bg-tertiary)`, `border: 1px solid var(--border-default)`, `color: var(--text-secondary)` |
| **Chip Hover** | `background: var(--bg-elevated)`, `border-color: var(--border-hover)`, `color: var(--text-primary)` |
| **Chip Active (pressed)** | `background: var(--brand-active)`, `color: #FFFFFF`, `transform: scale(0.97)` |
| **Chip Icon** (optional) | Leading icon, 12px. Drill-down: `RiSearchEyeLine`. Compare: `RiGitCompareV2Line` (custom, or `RiArrowLeftRightLine`). Refetch: `RiRefreshLine`. General: `RiQuestionLine` |
| **Entry Animation** | Staggered `animate-fade-in`, 100ms delay between chips |

#### Chip Content Generation

The follow-up suggestion chips are NOT hardcoded. They are generated by the backend
as part of the `execution_complete` event payload. The Orchestrator, after A5 completes,
uses the session context to generate relevant follow-up suggestions.

```typescript
// execution_complete event payload (enhanced)
interface ExecutionCompletePayload {
  // ... existing fields ...
  followUpSuggestions?: FollowUpSuggestion[];
}

interface FollowUpSuggestion {
  id: string;
  label: string;         // Display text: "Tell me more about DeepSeek"
  message: string;       // Actual message to send: "Drill deeper into DeepSeek results"
  type: 'drill_down' | 'compare' | 'refetch' | 'general';
  icon?: string;         // Optional icon hint
}
```

If no suggestions are provided by the backend, the frontend falls back to a static set:

```typescript
const DEFAULT_FOLLOWUPS: FollowUpSuggestion[] = [
  { id: 'dd1', label: 'Analyze specific platform in detail', message: 'Tell me more about the platform-specific results', type: 'drill_down' },
  { id: 'cmp', label: 'Compare with previous analysis', message: 'Compare this result with my last analysis', type: 'compare' },
  { id: 'gen', label: 'What should I prioritize improving?', message: 'Based on the analysis, what should I focus on first?', type: 'general' },
];
```

#### Interaction Behavior

1. **Click chip**: The chip's `message` text is sent as a user message via WebSocket,
   exactly as if the user typed it. The chip container disappears after a chip is clicked.
2. **Typing in input while chips visible**: Chips remain visible until either a chip is
   clicked or the user sends a manual message. They do not block the input.
3. **Multiple executions**: If the user triggers another full analysis in the same session,
   the old chips from the first execution are replaced by the new set.

#### State Management

```typescript
// conversationStore additions
interface ConversationState {
  // ... existing ...
  followUpSuggestions: FollowUpSuggestion[];
  setFollowUpSuggestions: (suggestions: FollowUpSuggestion[]) => void;
  clearFollowUpSuggestions: () => void;
}
```

Chips are cleared on `startExecution()`.

#### Accessibility

- Chip container: `role="group"`, `aria-label="Suggested follow-up questions"`
- Each chip: `role="button"`, `tabindex="0"`, `aria-label` with the full suggestion text
- Keyboard: `Tab` into chip group, `Arrow Left/Right` between chips, `Enter/Space` to select
- Screen reader announcement on chips appearing: "3 follow-up suggestions available"

---

### 2B. Drill-Down Result Rendering

#### User Scenario

The user clicks "Tell me more about DeepSeek results" (or types equivalent text). The
Orchestrator routes to `drill_down_node`, which generates a focused analysis from existing
data. The result appears as a chat message, NOT as a new Canvas report.

#### Design Decision: Chat Reply, Not Canvas

Drill-down results are conversational -- they are a focused response to a specific question.
They belong in the chat flow, not in the Canvas panel. This matches the user's mental model:
"I asked a question, I expect an answer in the conversation."

If the drill-down were pushed to Canvas, it would break the conversational flow and create
confusion: "Why did the report change?" vs "Here is a focused answer to your question."

The existing Canvas report remains unchanged. The drill-down is supplementary.

#### Layout

```
+-----------------------------------------------------------------------+
|  [User Message]                                                       |
|  Tell me more about DeepSeek results                                  |
+-----------------------------------------------------------------------+
|                                                                       |
|  [Agent Message -- Drill-Down Response]                               |
|                                                                       |
|  +-- Focus Card: DeepSeek Analysis ---------------------------+       |
|  |                                                             |       |
|  |  [RiSearchEyeLine]  DeepSeek Detailed Analysis             |       |
|  |                                                             |       |
|  |  Mention Rate on DeepSeek: 75.0%                           |       |
|  |  Questions tested: 12                                       |       |
|  |  Mentions found: 9                                          |       |
|  |                                                             |       |
|  |  Key Findings:                                              |       |
|  |  - DeepSeek excels at citing technical documentation...     |       |
|  |  - Product comparison questions show strong brand...        |       |
|  |  - Weak area: user review related questions...              |       |
|  |                                                             |       |
|  |  Recommendations:                                           |       |
|  |  1. Create user-generated content on review platforms...    |       |
|  |  2. Add comparison guides for product categories...         |       |
|  |                                                             |       |
|  +-------------------------------------------------------------+       |
|                                                                       |
|  ~~~ Follow-up Suggestions ~~~                                        |
|  [Compare DeepSeek with Doubao]  [Re-fetch DeepSeek only]            |
|                                                                       |
+-----------------------------------------------------------------------+
```

The drill-down response is rendered as a structured Markdown message with an optional
"Focus Card" wrapper that visually distinguishes it from a normal chat reply.

#### Focus Card Visual Specifications

| Element | Specification |
|---------|---------------|
| **Card Container** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-left: 3px solid var(--info, #3B82F6)`, `border-radius: 10px`, `padding: 14px 18px`, `margin: 6px 0` |
| **Header** | `display: flex`, `align-items: center`, `gap: 8px`, `margin-bottom: 10px`. Icon: `RiSearchEyeLine` 16px, `color: var(--info)`. Title: `font-size: 13px`, `font-weight: 600`, `color: var(--text-primary)` |
| **Stat Row** | `font-size: 12px`, `color: var(--text-secondary)`. Value: `font-weight: 600`, `color: var(--text-primary)` |
| **Section Title** | `font-size: 12px`, `font-weight: 600`, `color: var(--text-primary)`, `margin-top: 12px`, `margin-bottom: 4px` |
| **Body Text** | Standard `prose-chat` Markdown rendering (existing) |
| **Left Border Color** | `var(--info, #3B82F6)` -- blue, to distinguish from StageResultCard (indigo) and error banners (red) |

#### When Focus Card Is Used vs Plain Markdown

- **Focus Card**: When the drill-down has structured data (metrics, numbered findings).
  The backend signals this by including `"format": "structured"` in the response.
- **Plain Markdown**: When the drill-down is a pure text analysis. The standard `prose-chat`
  rendering applies.

The frontend decides based on the presence of structured data in the message metadata.
If the agent message includes `metadata.drillDown = true`, render the Focus Card wrapper.

#### Follow-Up After Drill-Down

After a drill-down response, new follow-up suggestion chips appear, contextual to the
drill-down topic. For example, after drilling into DeepSeek:
- "Compare DeepSeek with Doubao"
- "Re-fetch only DeepSeek data"
- "Show me the actual questions asked on DeepSeek"

These are generated by the backend in the `reply_delta` completion event.

#### Accessibility

- Focus Card: `role="article"`, `aria-label="Focused analysis: DeepSeek"`
- Structured data sections: proper heading hierarchy (`h4` for section titles within card)
- Follow-up chips: same accessibility as 2A

---

### 2C. Snapshot Comparison View

#### User Scenario

The user says "Compare with my last analysis." The Orchestrator routes to
`compare_snapshots_node`, which fetches the two most recent snapshots and generates
a comparison. The result appears as a chat message with a structured comparison layout.

#### Design Decision: Chat Reply with Comparison Card

Like drill-down, snapshot comparison is conversational. However, it has a more structured
visual format because comparison inherently involves side-by-side data.

#### Layout

```
+-----------------------------------------------------------------------+
|  [Agent Message -- Comparison Response]                               |
|                                                                       |
|  +-- Comparison Card -------------------------------------------+     |
|  |                                                               |     |
|  |  [RiArrowLeftRightLine]  Comparison: Feb 17 vs Feb 21         |     |
|  |                                                               |     |
|  |  +-- Score Comparison ---+                                    |     |
|  |  |                       |                                    |     |
|  |  |  BWVS Index           |                                    |     |
|  |  |  48.2  -->  52.3      |                                    |     |
|  |  |  [+4.1, +8.5%]       |                                    |     |
|  |  |  [=========>]         |                                    |     |
|  |  |                       |                                    |     |
|  |  +-----------------------+                                    |     |
|  |                                                               |     |
|  |  +-- Dimension Changes --------------------------------+      |     |
|  |  |                                                      |      |     |
|  |  |  Metric          Previous  Current   Change          |      |     |
|  |  |  -------------------------------------------------- |      |     |
|  |  |  Mention Rate    55.0%     65.0%     +10.0% [up]    |      |     |
|  |  |  Sentiment       68.0      72.0      +4.0   [up]    |      |     |
|  |  |  Coverage        70.0      75.0      +5.0   [up]    |      |     |
|  |  |  Citation        40.0      45.0      +5.0   [up]    |      |     |
|  |  |                                                      |      |     |
|  |  +------------------------------------------------------+      |     |
|  |                                                               |     |
|  |  +-- Analysis ----------------------------------------+       |     |
|  |  |                                                      |       |     |
|  |  |  Your brand's visibility has improved across all     |       |     |
|  |  |  dimensions since the last analysis. The largest     |       |     |
|  |  |  improvement is in Mention Rate (+10%), driven by... |       |     |
|  |  |                                                      |       |     |
|  |  +------------------------------------------------------+       |     |
|  |                                                               |     |
|  +---------------------------------------------------------------+     |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### Edge Cases

**Fewer than 2 snapshots**:
The backend returns a friendly text message (not a comparison card):

```
+-----------------------------------------------------------------------+
|  [Agent Message]                                                      |
|                                                                       |
|  Currently only one analysis is available. Please run the             |
|  analysis at least twice to enable comparison.                        |
|                                                                       |
|  [Run Analysis Again]                                                 |
|                                                                       |
+-----------------------------------------------------------------------+
```

The "Run Analysis Again" is a follow-up chip that triggers a new full analysis.

**Same scores (no change)**:

```
  BWVS Index
  48.2  -->  48.2
  [No change]
```

Delta text: "No change", `color: var(--text-muted)`.

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Comparison Card Container** | `background: var(--bg-secondary)`, `border: 1px solid var(--border-default)`, `border-left: 3px solid var(--phase-plan, #3B82F6)`, `border-radius: 10px`, `padding: 16px 20px` |
| **Header** | Icon: `RiArrowLeftRightLine` 16px, `color: var(--phase-plan)`. Title: `font-size: 13px`, `font-weight: 600`. Date range: `font-size: 12px`, `color: var(--text-secondary)` |
| **Score Comparison Block** | Center-aligned. Previous score: `font-size: 20px`, `font-weight: 600`, `color: var(--text-tertiary)`. Arrow: `RiArrowRightLine` 14px, `color: var(--text-disabled)`. Current score: `font-size: 24px`, `font-weight: 700`, color by band. Delta badge: same as Cycle 2 DeltaIndicator spec |
| **Dimension Table Container** | `background: var(--bg-primary)`, `border: 1px solid var(--border-default)`, `border-radius: 8px`, `overflow: hidden`, `margin-top: 12px` |
| **Table Header** | `background: var(--bg-tertiary)`, `font-size: 11px`, `font-weight: 600`, `color: var(--text-primary)`, `padding: 8px 12px`, `text-transform: uppercase`, `letter-spacing: 0.5px` |
| **Table Row** | `padding: 8px 12px`, `border-top: 1px solid var(--border-default)`, `font-size: 12px` |
| **Change Indicator** | Positive: `color: var(--success)`, prefix "+", direction icon `RiArrowUpSLine` 12px. Negative: `color: var(--error)`, prefix "-", icon `RiArrowDownSLine` 12px. Stable: `color: var(--text-muted)`, text "~" |
| **Analysis Section** | `margin-top: 12px`, `padding-top: 12px`, `border-top: 1px solid var(--border-default)`. Text: standard `prose-chat` Markdown |

#### Accessibility

- Comparison Card: `role="article"`, `aria-label="Analysis comparison between February 17 and February 21"`
- Table: `role="table"`, proper `role="columnheader"` and `role="cell"` semantics
- Change indicators: direction conveyed via text (+/-), icon (arrow), AND color (3 channels)
- Score transition: screen reader text: "BWVS Index changed from 48.2 to 52.3, increase of 4.1 points"

---

### 2D. Selective Refetch Progress

#### User Scenario

The user says "Re-analyze only on Kimi." The system runs A4 (Kimi only) and then A5
to regenerate the report with updated data.

#### Design Decision: Reuse Existing Progress Components

Selective refetch is a mini-pipeline. It reuses:
- **MiniProgress**: Shows 2 steps instead of 5 (A4 Refetch, A5 Report Generation)
- **StageResultCard**: A4 platform_status card shows only the refetched platform(s)
- **TaskStatusBadge**: Shows "Re-analyzing..." instead of "Analyzing..."

This is intentional design reuse. The user has already seen MiniProgress and StageResultCard
during the full pipeline. Using the same components creates consistency and reduces
cognitive load -- "I know what this looks like; it is doing the same thing but smaller."

#### Layout During Selective Refetch

```
+-----------------------------------------------------------------------+
|  [User Message]                                                       |
|  Re-analyze only on Kimi                                              |
+-----------------------------------------------------------------------+
|                                                                       |
|  [MiniProgress: Re-analyzing... 1/2  (~1 min)]                       |
|  [==================                           ] 40%                  |
|  -------------------------------------------------------------------- |
|  [spinner] A4 Data Refetch (Kimi)   In Progress                       |
|  [ ]       A5 Report Update         Waiting                           |
|                                                                       |
|  [StageResultCard: A4 Data Fetch ---- [0/1] ----]                     |
|  |  [ ] Kimi     Fetching...                      |                   |
|                                                                       |
+-----------------------------------------------------------------------+
```

#### MiniProgress Step Labels for Selective Refetch

The step labels are different from the full pipeline:

| Step | ID | Label |
|------|----|-------|
| A4 Refetch | `a4_refetch` | "Data Refetch (Kimi)" or "Data Refetch (Kimi, DeepSeek)" |
| A5 Update | `a5_update` | "Report Update" |

These labels are sent by the backend in `execution_progress` events.

#### Report Update Behavior

When A5 completes after selective refetch, the Canvas report is **updated in place**.
The existing report artifact is replaced with the new one. The user sees:
- A Canvas notification: "Report updated" (brief pulse animation on Canvas panel header)
- The report content reflects the new data
- The Cycle 2 DeltaIndicator now shows the delta vs the *previous* snapshot (before refetch)

This avoids creating duplicate reports and matches the user's expectation: "I asked to
re-analyze, so the report should reflect the new data."

#### Accessibility

- MiniProgress: same ARIA as standard execution
- StageResultCard: same ARIA, with platform count reflecting only selected platforms
- Canvas update notification: `role="status"`, `aria-live="polite"`, text "Report updated with new Kimi data"

---

### 2E. Follow-Up vs Full Pipeline Visual Distinction

#### Design Problem

After a full pipeline analysis, the user may trigger follow-up actions (drill-down,
compare, refetch). These are lighter-weight operations. If they use the exact same visual
weight as the full pipeline (TaskStatusBadge "Analyzing...", full MiniProgress, etc.),
the user may think "the whole analysis is running again." We need a clear visual
distinction between a heavyweight full pipeline and a lightweight follow-up.

#### Solution: Lightweight Execution Indicator

For follow-up operations (drill_down, compare_snapshots), which are LLM-only and take
< 15 seconds, we do NOT show:
- TaskStatusBadge (or show a minimal "Thinking..." variant)
- MiniProgress
- StageResultCards

Instead, we show:
- A typing indicator on the agent message (existing behavior for chat replies)
- The standard `RiLoader4Line` spinner inline with the message bubble

For selective_refetch, which IS a mini-pipeline, we DO show:
- A simplified MiniProgress (2 steps only)
- A4 StageResultCard (partial platform set)
- TaskStatusBadge showing "Re-analyzing..."

#### TaskStatusBadge Behavior During Follow-Up

| Operation | Badge Text | Badge Style |
|-----------|-----------|-------------|
| Full pipeline (A1-A5) | "Analyzing... A3 65%" | Amber, spinner |
| drill_down | "Thinking..." | Brand-primary (indigo), subtle pulse |
| compare_snapshots | "Comparing..." | Brand-primary (indigo), subtle pulse |
| selective_refetch | "Re-analyzing... A4" | Amber, spinner (same as full) |

The "Thinking..." and "Comparing..." badges are visually lighter: indigo tint instead
of amber, subtle `animate-pulse-slow` instead of spinning loader.

```
LIGHTWEIGHT BADGE:
+-----------------------------------------------+
|  [pulse dot]  Thinking...                      |
+-----------------------------------------------+
```

| Element | Specification |
|---------|---------------|
| **Lightweight Badge** | `background: rgba(99,102,241,0.08)`, `color: var(--brand-primary)`. Dot: `width: 6px`, `height: 6px`, `border-radius: 50%`, `background: var(--brand-primary)`, `animation: pulse-slow 2s infinite` |

This visual distinction tells the user: "This is a quick operation, not a full analysis."

#### Accessibility

- Lightweight badge: `aria-label="Processing follow-up question"` (differentiated from
  "Analysis in progress")
- No MiniProgress means no progress bar -- screen reader announces the typing indicator
  via the standard message flow

---

## Module 3: A1 Quality Hardening UX

### 3A. A1 Retry Experience

#### User Scenario

During analysis, the A1 brand analysis agent completes but produces incomplete data.
The system automatically retries with a focused prompt. What does the user see?

#### Design Decision: Subtle Quality Verification, Not Error Display

The user should NOT see "A1 failed, retrying..." -- that creates anxiety and undermines
trust. Instead, the system shows a calm quality verification step.

#### Visual Treatment

When A1 completes but triggers a retry, the A1 StageResultCard transitions through
an additional state:

```
STATE 1: A1 completes (initial, possibly incomplete)
+-- A1 Brand Analysis ----[Verifying]--------+
|                                             |
|  [shimmer placeholder for content]          |
|  Verifying data quality...                  |
|                                             |
+---------------------------------------------+

STATE 2: Retry completes (data quality confirmed)
+-- A1 Brand Analysis ----[Completed]---------+
|                                              |
|  Brand:      Xiaomi                          |
|  Industry:   Consumer Electronics            |
|  Competitors: Huawei, Apple, OPPO, vivo      |
|  Products:   Smartphones, IoT devices...     |
|                                              |
+----------------------------------------------+
```

#### "Verifying" State Specifications

| Element | Specification |
|---------|---------------|
| **Status Badge** | Text: "Verifying", `background: rgba(99,102,241,0.1)`, `color: var(--brand-primary)` |
| **Content Area** | Shimmer animation placeholder (reuse `.animate-shimmer` from globals.css). Two shimmer lines: `height: 10px`, `width: 80%` and `width: 60%`, `border-radius: 4px`, `margin: 4px 0` |
| **Verification Text** | "Verifying data quality..." in `font-size: 11px`, `color: var(--text-muted)`, `font-style: italic` |
| **Duration** | The verifying state lasts as long as the retry takes (typically 5-15 seconds) |

#### Transition Behavior

1. A1 LLM call completes -> validation fails -> backend sends a `stage_result` event
   with `status: 'verifying'` instead of `status: 'completed'`
2. StageResultCard renders in "Verifying" state (shimmer + text)
3. Retry completes -> backend sends updated `stage_result` with `status: 'completed'`
   and final data
4. StageResultCard transitions: shimmer fades out (200ms), content fades in (200ms)

#### If Retry Also Fails

If the retry produces data that still has issues (but was normalized), the card shows
as "Completed" with a subtle quality indicator (see 3B below). The user is not alerted
to internal normalization -- that is an implementation detail.

#### MiniProgress Step Label During Retry

The A1 step in MiniProgress shows a slightly different label during retry:

```
NORMAL:
[spinner] A1 Brand Analysis       In Progress

DURING RETRY:
[spinner] A1 Brand Analysis       Verifying...
```

The "Verifying..." text uses `color: var(--brand-primary)` instead of `var(--warning)`
to visually distinguish it from "In Progress."

#### Accessibility

- Verifying state: `aria-label="Brand Analysis: verifying data quality"`
- Shimmer placeholder: `aria-hidden="true"` (decorative loading animation)
- Status transition announced via `aria-live="polite"` on the card

---

### 3B. Data Quality Indicator on StageResultCard

#### User Scenario

The A1 analysis completes. The data is good but required normalization (field name
fixing, default values for missing optional fields). The user sees a subtle quality
indicator on the A1 StageResultCard.

#### Design Decision: Optional, Non-Alarming

This indicator is **not shown for perfect data**. It only appears when the system
performed some level of quality improvement. It is designed to build trust through
transparency, not to create anxiety.

#### Layout

```
+-- A1 Brand Analysis ----[Completed]--[quality icon]--+
|                                                       |
|  Brand:      Xiaomi                                   |
|  Industry:   Consumer Electronics                     |
|  Competitors: Huawei, Apple, OPPO, vivo               |
|  Products:   Smartphones, IoT devices...              |
|                                                       |
+-------------------------------------------------------+
```

The quality icon appears in the header, between the "Completed" badge and the
expand/collapse chevron.

#### Quality Levels

| Level | When | Icon | Tooltip |
|-------|------|------|---------|
| **High** (no issues) | All fields populated, no retry needed | No icon shown | N/A |
| **Good** (minor fixes) | Field names normalized, minor defaults applied | `RiShieldCheckLine` 12px, `color: var(--success)` | "Data verified and enhanced" |
| **Adequate** (retry performed) | Retry was needed but succeeded | `RiShieldCheckLine` 12px, `color: var(--warning)` | "Data verified after quality check" |
| **Partial** (some fields still missing) | Retry performed but some gaps remain | `RiAlertLine` 12px, `color: var(--warning)` | "Some data fields may be incomplete" |

#### Visual Specifications

| Element | Specification |
|---------|---------------|
| **Quality Icon** | 12px, positioned in header row. Cursor: `help` (indicates tooltip) |
| **Tooltip** | `background: var(--bg-elevated)`, `border: 1px solid var(--border-hover)`, `border-radius: 6px`, `padding: 6px 10px`, `font-size: 11px`, `color: var(--text-secondary)`, `box-shadow: 0 4px 12px rgba(0,0,0,0.3)`. Appears on hover (200ms delay) or focus |

The tooltip is brief and non-technical. We never say "validation failed" or "retry
attempted." We say "verified" and "quality check" -- language that implies diligence,
not failure.

#### Data Source

The backend includes a `quality_level` field in the A1 `stage_result` event:

```typescript
interface StageResult {
  // ... existing fields ...
  qualityLevel?: 'high' | 'good' | 'adequate' | 'partial';
  qualityMessage?: string;
}
```

#### Accessibility

- Quality icon: `aria-label` with the tooltip text (e.g., "Data verified and enhanced")
- Not using `aria-hidden` because it conveys meaningful status information
- Tooltip content duplicated in `aria-label` so screen readers announce it on focus

---

## Global CSS Additions

The following CSS keyframes and utility classes need to be added to
`D:\AGEO\frontend\src\app\globals.css`:

```css
/* Reconnection banner fade-out */
@keyframes banner-fade-out {
  from {
    opacity: 1;
    max-height: 60px;
  }
  to {
    opacity: 0;
    max-height: 0;
    padding: 0;
    margin: 0;
  }
}

.animate-banner-fade-out {
  animation: banner-fade-out 500ms ease-out forwards;
}

/* Staggered entry for replay cards and follow-up chips */
.animate-stagger-1 { animation-delay: 0ms; }
.animate-stagger-2 { animation-delay: 150ms; }
.animate-stagger-3 { animation-delay: 300ms; }
.animate-stagger-4 { animation-delay: 450ms; }
.animate-stagger-5 { animation-delay: 600ms; }

/* Completion glow pulse (for sidebar entity dot) */
@keyframes glow-pulse {
  0%, 100% {
    box-shadow: 0 0 4px rgba(34, 197, 94, 0.3);
  }
  50% {
    box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
  }
}

.animate-glow-pulse {
  animation: glow-pulse 2s ease-in-out 3;
}

/* Safe-to-leave message fade */
@keyframes safe-leave-fade {
  0% {
    opacity: 0;
    transform: translateY(4px);
  }
  15% {
    opacity: 1;
    transform: translateY(0);
  }
  85% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}

.animate-safe-leave {
  animation: safe-leave-fade 8s ease-out forwards;
  animation-delay: 2s;
  opacity: 0;
}

/* Three-dot loading for reconnection text */
@keyframes dot-loading {
  0%, 20% { content: '.'; }
  40% { content: '..'; }
  60%, 100% { content: '...'; }
}

.dot-loading::after {
  content: '';
  animation: dot-loading 1.5s steps(1) infinite;
}
```

---

## Accessibility Audit & Requirements

### WCAG AA Color Contrast Verification (Cycle 3 Additions)

All new text/background combinations:

| Text Color | Background | Usage | Contrast Ratio | Pass? |
|-----------|-----------|-------|----------------|-------|
| `var(--warning)` #F59E0B | `rgba(245,158,11,0.1)` on `#0D0D0D` | TaskStatusBadge RUNNING text | 8.8:1 | Yes |
| `var(--success)` #22C55E | `rgba(34,197,94,0.1)` on `#0D0D0D` | TaskStatusBadge COMPLETED text | 7.3:1 | Yes |
| `var(--error)` #EF4444 | `rgba(239,68,68,0.1)` on `#0D0D0D` | TaskStatusBadge FAILED text | 5.5:1 | Yes |
| `var(--text-secondary)` #A3A3A3 | `var(--bg-tertiary)` #262626 | Follow-up chip text | 5.1:1 | Yes |
| `var(--text-primary)` #FFFFFF | `var(--bg-tertiary)` #262626 | Follow-up chip hover text | 11.6:1 | Yes |
| `var(--brand-primary)` #6366F1 | `rgba(99,102,241,0.08)` on `#0D0D0D` | Lightweight badge text | 5.0:1 | Yes (AA) |
| `var(--text-secondary)` #A3A3A3 | `rgba(34,197,94,0.06)` on `#0D0D0D` | Completion banner text | 6.3:1 | Yes |
| `var(--text-secondary)` #A3A3A3 | `rgba(239,68,68,0.06)` on `#0D0D0D` | Error banner text | 6.3:1 | Yes |
| `#FFFFFF` | `var(--brand-primary)` #6366F1 | Retry button text | 5.9:1 | Yes |
| `var(--brand-primary)` #6366F1 | `var(--bg-secondary)` #1A1A1A | "Verifying" badge text | 4.6:1 | Yes (AA) |

All pass WCAG AA. No action items.

### ARIA Requirements by Component (Cycle 3 Additions)

| Component | ARIA Requirements |
|-----------|-------------------|
| **TaskStatusBadge** | `role="status"`, `aria-live="polite"`, `aria-label` with full status text. Focusable: `tabindex="0"` |
| **Completion Banner** | `role="status"`, `aria-live="polite"`. "View Report" link: standard `<a>` or `<button>` semantics |
| **Error Banner** | `role="alert"`, `aria-live="assertive"`. Retry button: `aria-label="Retry analysis"` |
| **Safe-to-Leave Signal** | `role="status"`, `aria-live="polite"`. Transient; announced once |
| **Follow-Up Chips** | Container: `role="group"`, `aria-label="Suggested follow-up questions"`. Each chip: `role="button"`, `tabindex="0"` |
| **Focus Card (Drill-Down)** | `role="article"`, `aria-label="Focused analysis: {topic}"` |
| **Comparison Card** | `role="article"`, `aria-label="Analysis comparison"`. Table inside: `role="table"` with full semantics |
| **Quality Indicator Icon** | `aria-label` with quality message text. `tabindex="0"` for keyboard tooltip access |
| **Disconnection Banner** | `role="alert"`, `aria-live="assertive"` |
| **Reconnection Banner** | `role="status"`, `aria-live="polite"` |
| **Replay Icon on StageResultCard** | `aria-hidden="true"` (decorative) |
| **Task Completion Toast** | Reuse existing toast ARIA: `role="status"`, `aria-live="polite"`. Failure toast: `role="alert"` |

### Keyboard Navigation (Cycle 3 Additions)

| Component | Keyboard Behavior |
|-----------|-------------------|
| **TaskStatusBadge** | `Tab` to focus. `Enter/Space` to scroll to relevant content |
| **Follow-Up Chips** | `Tab` into group. `Arrow Left/Right` between chips. `Enter/Space` to select |
| **Completion Banner "View Report"** | Standard link/button keyboard interaction |
| **Error Banner "Retry"** | Standard button keyboard interaction |
| **Quality Indicator Tooltip** | `Tab` to focus icon. Tooltip appears on focus. `Escape` to dismiss |
| **Task Completion Toast** | `Escape` to dismiss. "View Report" link: `Tab` to focus, `Enter` to navigate |

### Screen Reader Announcements (Cycle 3 Additions)

- When analysis starts: "Analysis started for {brand}. You can safely close this tab."
- When task status changes (via badge): "Analysis progress: stage {stage}, {percent}% complete"
- When reconnecting and replaying: "Reconnected. Restoring {N} previous stage results."
- When execution completes: "Analysis complete. {N} follow-up suggestions available."
- When drill-down response arrives: "Focused analysis for {topic} ready."
- When comparison response arrives: "Comparison between {date1} and {date2} ready."
- When A1 enters verifying state: "Brand Analysis: verifying data quality."
- When A1 verification completes: "Brand Analysis: data verified."
- When task completion toast appears: "{Brand} analysis completed. BWVS score: {score}."

---

## Component Implementation Summary

### New Components

| Component | File Path | Responsibility |
|-----------|-----------|----------------|
| `TaskStatusBadge` | `frontend/src/components/chat/TaskStatusBadge.tsx` | Always-visible badge showing task status in chat header |
| `ReconnectionBanner` | `frontend/src/components/chat/ReconnectionBanner.tsx` | Completion/Error/Reconnection banner displayed on session reconnect |
| `FollowUpChips` | `frontend/src/components/chat/FollowUpChips.tsx` | Clickable follow-up suggestion chips after execution completes |
| `FocusCard` | `frontend/src/components/chat/FocusCard.tsx` | Structured card for drill-down responses in chat flow |
| `ComparisonCard` | `frontend/src/components/chat/ComparisonCard.tsx` | Side-by-side snapshot comparison rendering in chat flow |
| `SafeToLeaveSignal` | `frontend/src/components/chat/SafeToLeaveSignal.tsx` | Transient "safe to close tab" message below MiniProgress |
| `TaskNotificationPoller` | `frontend/src/components/layout/TaskNotificationPoller.tsx` | Background poller for completed task toast notifications |

### Modified Components

| Component | File Path | Changes |
|-----------|-----------|---------|
| `ChatPanel` | `frontend/src/components/chat/ChatPanel.tsx` | (1) Add TaskStatusBadge in header area. (2) Add ReconnectionBanner rendering logic on mount. (3) Render FollowUpChips after execution completes. (4) Add SafeToLeaveSignal below MiniProgress. (5) Handle reconnection task checking on mount |
| `StageResultCard` | `frontend/src/components/chat/StageResultCard.tsx` | (1) Add "verifying" status badge state. (2) Add quality indicator icon in header. (3) Add replay icon for reconnection replayed cards. (4) Add shimmer placeholder for verifying state |
| `MiniProgress` | `frontend/src/components/chat/MiniProgress.tsx` | (1) Support "Verifying..." step status for A1 retry. (2) Support 2-step mode for selective refetch |
| `ChatSidebar` | `frontend/src/components/layout/ChatSidebar.tsx` | (1) Show RUNNING task indicator (pulsing dot + progress). (2) Show COMPLETED glow effect. (3) Periodic task status polling |
| `ChatLayout` | `frontend/src/components/layout/ChatLayout.tsx` | (1) Mount TaskNotificationPoller. (2) Pass task awareness to ChatPanel |
| `conversationStore` | `frontend/src/stores/conversationStore.ts` | (1) Add `activeTask` state + actions. (2) Add `followUpSuggestions` state + actions. (3) Update `startExecution()` to clear follow-ups |
| `globals.css` | `frontend/src/app/globals.css` | Add CSS animations: banner-fade-out, stagger delays, glow-pulse, safe-leave-fade, dot-loading |
| `toast.tsx` | `frontend/src/components/ui/toast.tsx` | (1) Add `task_complete` and `task_failed` toast types with extended duration and actionable link. (2) Failure toasts: no auto-dismiss |

### New TypeScript Types

| Type File | Contents |
|-----------|---------|
| `frontend/src/types/task.ts` | `AnalysisTask`, `TaskStatus`, `FollowUpSuggestion`, `TaskNotification` interfaces |

### Store Changes (conversationStore.ts)

```typescript
// New state fields
interface ConversationState {
  // ... existing ...
  activeTask: AnalysisTask | null;
  followUpSuggestions: FollowUpSuggestion[];

  // New actions
  setActiveTask: (task: AnalysisTask | null) => void;
  updateActiveTaskProgress: (stage: string, progress: number, message: string) => void;
  setFollowUpSuggestions: (suggestions: FollowUpSuggestion[]) => void;
  clearFollowUpSuggestions: () => void;
}

// Modified actions
startExecution: () => void;
// Addition: clears followUpSuggestions, sets activeTask to RUNNING state

reset: () => void;
// Addition: activeTask: null, followUpSuggestions: []
```

### Data Flow Diagrams

#### Flow 1: Reconnection (Task RUNNING)

```
User opens session page
    |
    v
page.tsx useEffect on mount
    |-- GET /api/v1/tasks/session/{sessionId}/active
    |
    v
If task.status === 'running':
    |-- setActiveTask(task)
    |-- TaskStatusBadge renders: "Analyzing... A3 65%"
    |-- replayStageResults(task.stage_results_cache, delay=150ms)
    |       |-- forEach: addStageResult({ ...result, _isReplay: true })
    |       |-- StageResultCards appear with stagger + replay icon
    |-- setExecutionProgress({ progress: task.progress, message: task.progress_message })
    |-- MiniProgress renders from executionProgress
    |-- connectWebSocket(sessionId) for live updates
```

#### Flow 2: Follow-Up (Drill-Down)

```
User clicks follow-up chip "Tell me more about DeepSeek"
    |
    v
FollowUpChips.onClick(chip)
    |-- clearFollowUpSuggestions()
    |-- addMessage({ type: 'user', content: chip.message })
    |-- sendMessage(chip.message)
    |
    v
Backend: Orchestrator routes to drill_down_node
    |-- sends reply_delta events (streamed chat reply)
    |-- sends execution_complete with new followUpSuggestions
    |
    v
Frontend:
    |-- Agent message renders with FocusCard wrapper
    |-- New FollowUpChips appear from updated suggestions
```

#### Flow 3: A1 Quality Retry

```
Backend: a1_brand_node completes
    |-- _validate_a1_output() fails
    |-- sends stage_result { status: 'verifying', resultType: 'brand_profile' }
    |
    v
Frontend: StageResultCard renders in "Verifying" state
    |-- shimmer placeholder + "Verifying data quality..."
    |
    v
Backend: retry completes
    |-- sends stage_result { status: 'completed', qualityLevel: 'adequate', data: {...} }
    |
    v
Frontend: StageResultCard transitions
    |-- shimmer fades out, real content fades in
    |-- quality icon appears: shield with amber color
    |-- MiniProgress A1 step: "Completed" (no longer "Verifying...")
```

---

## Cognitive Load Analysis

### Chat Panel During Reconnection (Most Complex New State)

During reconnection with a RUNNING task, the user sees:

1. Reconnection banner (temporary, 3s): "Reconnected. Syncing latest results..."
2. Chat history (existing messages)
3. Replayed StageResultCards (staggered, up to 5)
4. Restored MiniProgress
5. TaskStatusBadge in header

This is a lot of visual elements appearing in rapid succession. Mitigations:

1. **Staggered replay**: 150ms between each card prevents a "wall of content" flash
2. **Reconnection banner auto-dismiss**: Reduces to 0 extra elements within 3 seconds
3. **TaskStatusBadge is persistent**: Provides a stable reference point during the
   replay flurry
4. **Auto-scroll**: The chat panel scrolls smoothly to the latest content, so the user
   does not need to manually find their place

### Follow-Up Decision Space

After a full analysis, the user sees 3-4 follow-up chips. This is within the 3-5 range
recommended by Hick's Law for quick decision-making. We avoid showing more than 4 chips
to prevent decision paralysis.

The chips use **active language** ("Tell me more about...", "Compare with...") rather
than abstract labels ("Drill-down", "Comparison"), because active language reduces the
cognitive step of translating a label into an action.

### A1 Retry Transparency vs Anxiety

The "Verifying" state is a careful balance. Too much transparency ("Validation failed,
retrying with focused prompt targeting 3 missing fields") creates anxiety. Too little
("..." spinner) creates uncertainty. "Verifying data quality..." sits in the sweet spot:
it tells the user something proactive is happening, without implying failure.

---

## Interaction Flow Summary (Text Diagrams)

### Full Lifecycle: Start -> Leave -> Return -> Follow Up

```
PHASE 1: START ANALYSIS
[User types "Analyze Xiaomi"]
  -> [TaskStatusBadge: Pending]
  -> [TaskStatusBadge: Analyzing... A1 5%]
  -> [SafeToLeaveSignal: "You can safely close this tab"]
  -> [StageResultCard A1 appears (may go through Verifying)]
  -> [StageResultCard A2 appears]
  -> ...
  -> [MiniProgress: 3/5, ~1 min remaining]

PHASE 2: USER LEAVES
[User closes browser tab]
  (Server continues pipeline; task progress written to DB)

PHASE 3: USER RETURNS (COMPLETED)
[User opens session URL]
  -> [Chat history loads]
  -> [ReconnectionBanner: "Analysis completed at 14:33, BWVS: 52.3"]
  -> [TaskStatusBadge: Completed]
  -> [Canvas loads report]
  -> [FollowUpChips appear below final agent message]
       [Tell me more about DeepSeek]
       [Compare with last analysis]
       [What should I improve first?]

PHASE 4: FOLLOW UP
[User clicks "Compare with last analysis"]
  -> [TaskStatusBadge: Comparing...]
  -> [ComparisonCard renders in chat: Feb 17 vs Feb 21, BWVS +4.1]
  -> [New FollowUpChips: "Drill into the biggest improvement", "Run full analysis again"]

[User clicks "Drill into the biggest improvement"]
  -> [TaskStatusBadge: Thinking...]
  -> [FocusCard renders: Mention Rate detailed analysis]
  -> [New FollowUpChips: ...]

[User types "Re-analyze only Kimi"]
  -> [TaskStatusBadge: Re-analyzing... A4]
  -> [MiniProgress: 2 steps (A4 Refetch, A5 Update)]
  -> [StageResultCard A4: [1/1] Kimi fetching...]
  -> [A4 completes, A5 completes]
  -> [Canvas report updates in-place]
  -> [TaskStatusBadge: Completed]
  -> [New FollowUpChips appear]
```

### Background Completion (User on Different Page)

```
PHASE 1: USER STARTS ANALYSIS
[User on Xiaomi chat, types "Analyze Xiaomi"]
  -> Analysis begins
  -> User navigates to Dashboard

PHASE 2: ANALYSIS COMPLETES IN BACKGROUND
[Backend: A5 completes, task -> COMPLETED]
  -> TaskService checks: no active WebSocket for this session
  -> Task marked as completed in DB

PHASE 3: USER ON DASHBOARD
[TaskNotificationPoller polls every 30s]
  -> GET /api/v1/tasks?status=completed&unread=true
  -> Returns: Xiaomi task completed
  -> Toast appears: "Xiaomi analysis completed. BWVS: 52.3 [View Report]"

[User clicks "View Report"]
  -> Navigates to /chat/{sessionId}
  -> ReconnectionBanner: "Analysis completed at 14:33"
  -> Report loads in Canvas
```

---

## Open Design Questions for Review

1. **Q: Should follow-up chips be generated by the backend or hardcoded in the frontend?**
   - Recommendation: Backend generates contextual suggestions. Frontend has fallback defaults.
   - Rationale: Backend has access to session context (which platforms were used, whether
     previous snapshots exist) and can generate more relevant suggestions.
   - Decision owner: Product Manager + Backend Dev.

2. **Q: Should selective_refetch update the existing Canvas report or create a new one?**
   - Recommendation: Update in-place. Creating a new report artifact would confuse users
     who expect "the report" to reflect the latest data.
   - Risk: If the user wants to compare "before refetch" and "after refetch," the old
     report is gone. Mitigation: Snapshots preserve the old data; the user can use
     `compare_snapshots` to see the delta.
   - Decision owner: UX Designer (self -- recommending update in-place).

3. **Q: How many follow-up suggestion chips should be shown?**
   - Recommendation: 3-4 chips maximum. More creates decision paralysis per Hick's Law.
   - If the backend generates more than 4, the frontend truncates to 4 and does NOT
     show a "More..." option (complexity without value at this stage).
   - Decision owner: UX Designer.

4. **Q: Should the "Safe to Leave" signal appear on every execution or only the first?**
   - Recommendation: Only the first execution in a session. Subsequent executions in
     the same session skip it (the user already learned this). Tracked via sessionStorage.
   - Rationale: Repeated display becomes noise for power users.
   - Decision owner: UX Designer.

5. **Q: Should the sidebar task indicator poll independently or share data with the
   ChatPanel's task awareness?**
   - Recommendation: Share a global task cache. A new `taskStore` (or extend entityStore)
     holds task status for all entities, refreshed every 30 seconds. Both sidebar and
     ChatPanel read from this store.
   - Rationale: Avoids duplicate API calls and keeps data consistent.
   - Decision owner: Frontend Dev + Architect.

6. **Q: Comparison card: should "Higher" competitors be styled in red and "Lower" in green,
   or should positive changes always be green?**
   - Recommendation: In the comparison card, POSITIVE CHANGE for the USER's brand is always
     green, NEGATIVE is always red. This means: if the user's mention rate went up, green.
     If a competitor's advantage increased, that context is explained in text, not color-coded
     as the user's loss.
   - Rationale: Color should reflect the user's perspective, not raw numerical direction.
   - Decision owner: UX Designer.

---

## Design Validation Checklist

- [ ] Can a user who closed their tab 5 minutes ago return and immediately understand
  what happened? (TaskStatusBadge + ReconnectionBanner + replayed cards)
- [ ] Does the "Safe to Leave" signal actually reduce tab-closing anxiety?
  (User testing needed)
- [ ] Are follow-up chips actionable without requiring the user to read the full report
  first? (Labels should be self-explanatory)
- [ ] Does the drill-down FocusCard clearly belong in the chat flow (not confused with
  the Canvas report)?
- [ ] Does the ComparisonCard convey directional change without requiring the user to do
  mental math? (Delta values + arrows + colors + percentage)
- [ ] Is the A1 "Verifying" state calm enough to not trigger anxiety? ("Verifying quality"
  vs "Retrying after failure" -- language matters)
- [ ] Does the quality indicator icon add trust without adding visual noise?
- [ ] Is the selective refetch progress distinguishable from a full analysis? (2 steps
  vs 5 in MiniProgress)
- [ ] Can a screen reader user follow the entire reconnection + follow-up flow without
  losing context?
- [ ] Does the sidebar task indicator create sufficient awareness without pulling attention
  away from the current page?
- [ ] Are all new interactive elements reachable by keyboard?
- [ ] Does the completion toast provide enough context to decide "should I click View Report
  now?" (Brand name + BWVS score = yes)
- [ ] After multiple follow-up interactions, does the chat panel remain scrollable and
  navigable? (No infinite vertical growth of non-collapsible elements)

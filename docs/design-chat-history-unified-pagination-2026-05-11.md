# Chat History Unified Pagination Design

Date: 2026-05-11

## Context

This document records the design decision for fixing Chat history loading in the latest `origin/main` codebase.

The worktree used for this design is:

- Path: `/Users/qiaole/Documents/AGEO-worktrees/chat-history-pagination`
- Branch: `codex/chat-history-pagination`
- Base: `origin/main` at `99d18fd fix(aice): retry site validation failures`

The previous inspected branch, `codex/sync-imspecta-20260423`, is not a safe implementation base for this task. It is ahead of its local base by 4 commits but behind latest `origin/main` by 198 commits, and the relevant Chat / Canvas / message API files have changed on `origin/main`.

## Deterministic Current Behavior

On latest `origin/main`, Chat history loading is not full-history loading.

Current frontend behavior:

1. `ChatPanel` initializes persisted messages with a fixed page size:
   - normal Chat entry: `INITIAL_HISTORY_MESSAGE_LIMIT = 30`
   - artifact route entry: `12`

2. `ChatPanel` records the oldest loaded message id in `oldestLoadedMessageIdRef`.

3. `loadOlderHistoryUntil(targetMessageId)` can fetch older history in batches of `HISTORY_BACKFILL_BATCH_SIZE = 50`.

4. That older-history fetch is only used by the `scroll-to-message` event handler, which is mainly triggered by Canvas "jump to conversation".

5. The message scroll container currently uses `onScroll={updateAutoScrollState}` only. That handler only decides whether auto-scroll-to-bottom is enabled. It does not fetch older messages when the user scrolls to the top.

Current backend behavior:

1. `GET /sessions/{session_id}/messages?limit=N` returns the newest `N` messages.

2. `GET /sessions/{session_id}/messages?limit=N&before=<message_id>` returns messages whose `sequence` is older than the referenced message.

3. The service orders by `sequence desc`, applies `limit`, then reverses the result so the frontend receives chronological order.

Therefore, the missing history is caused by frontend pagination policy, not by missing backend pagination support.

## Product Principle

Use one Chat timeline model:

> Entering a Chat opens the latest point in the conversation. Scrolling upward loads older history page by page until the earliest message. Artifact/report entry should reuse the same timeline and positioning mechanism instead of using a separate initial-history branch.

The Chat window should behave like a normal conversation timeline:

- Initial view starts near the latest message.
- Older messages are loaded by upward scrolling.
- New runtime messages still auto-scroll only when the user is following the bottom.
- Artifact/report entry opens the artifact and then positions the corresponding conversation message through the existing jump-to-conversation capability.

## Target Behavior

### Normal Chat Entry

1. Load the latest message page with one fixed initial size, currently 30.
2. Render those messages in chronological order.
3. Scroll to the latest message after initial load.
4. When the user scrolls near the top, load the next older page using `before=oldestLoadedMessageIdRef.current`.
5. Prepend older messages without visual jump by preserving scroll offset.
6. Repeat until the backend returns fewer than the batch size or no messages.

### Artifact / Report Entry

Artifact entry should not reduce the initial history page size.

1. Load the same latest Chat page as normal entry.
2. Hydrate and focus the requested artifact in Canvas using existing artifact route logic.
3. Resolve the artifact's `linkedMessageId` from hydrated Canvas content.
4. Use the existing `scroll-to-message` flow to locate the linked conversation message.
5. If the linked message is not in the currently loaded page, `loadOlderHistoryUntil(linkedMessageId)` should fetch older pages until it is found or the earliest history is reached.

This keeps artifact entry as "open artifact + locate message" rather than "special Chat history loading mode".

## Implementation Plan

### 1. Unify Initial History Limit

Change initial persisted-message loading in `ChatPanel` so it always uses `INITIAL_HISTORY_MESSAGE_LIMIT`.

Remove the artifact-specific `12` limit from the initial Chat history request.

Expected effect:

- Normal Chat and artifact route entry share the same initial timeline page.
- Artifact routes no longer create a separate short-history behavior.

### 2. Add Top-Scroll Pagination

Replace the current scroll handler with a unified handler that:

1. Calls the existing bottom-follow logic.
2. Checks whether the scroll container is near the top.
3. If near top, calls a new `loadOlderHistoryPage()` helper.

The helper should:

- Guard against concurrent loads.
- Stop when `loadedAllHistoryRef.current` is true.
- Use `oldestLoadedMessageIdRef.current` as the `before` cursor.
- Fetch `HISTORY_BACKFILL_BATCH_SIZE`.
- Prepend via `hydratePersistedMessages(batch, true)`.
- Update `oldestLoadedMessageIdRef.current`.
- Mark `loadedAllHistoryRef.current` when the result is empty or shorter than the batch size.
- Preserve visual scroll position after prepending.

### 3. Keep Targeted Backfill For Jump-To-Message

Keep `loadOlderHistoryUntil(targetMessageId)` as the targeted locator used by Canvas.

It can either:

- Continue using its current loop, or
- Reuse the single-page helper internally until the target appears.

The important contract is that both user top-scroll and artifact jump use the same `before` cursor and the same hydration path.

### 4. Auto-Position Artifact Entry Through Existing Jump Flow

After route artifact hydration resolves content with `linkedMessageId`, dispatch or invoke the same message-positioning path used by Canvas "jump to conversation".

Do not add another artifact-specific message query path.

If the artifact does not have a linked message id, keep the artifact open and do not force Chat scrolling.

## Non-Goals

- Do not change backend message pagination unless validation shows a concrete bug.
- Do not add a separate "load all messages on entry" mode.
- Do not add artifact-specific initial history limits.
- Do not bypass persisted message / artifact identity systems.
- Do not rewrite Canvas hydration as part of this change.

## Risks And Controls

### Risk: scroll jumps when older messages are prepended

Control:

- Before fetch: record `previousScrollHeight` and `previousScrollTop`.
- After prepend render: set `scrollTop` to `newScrollHeight - previousScrollHeight + previousScrollTop`.

### Risk: duplicate messages across pages

Control:

- Existing `hydratePersistedMessages` already deduplicates by message id.
- Keep that path as the only hydration entry.

### Risk: concurrent top-scroll fetches

Control:

- Reuse `historyBackfillPromiseRef` or introduce a separate page-load promise/ref only if targeted locator and top-scroll need independent control.
- Prefer one shared loading lock for older history.

### Risk: artifact route tries to locate before Canvas has a linked message id

Control:

- Run positioning only after the hydrated target content has `linkedMessageId`.
- If the linked message id is absent, no-op.

## Validation Plan

Minimum validation after implementation:

1. Verify worktree and branch:
   - `git branch --show-current`
   - `git status --short --branch`

2. Static checks:
   - From `frontend/`: `npm run lint`
   - If lint is too broad or already noisy, run the narrowest available TypeScript check that covers `ChatPanel`.

3. Targeted manual verification:
   - Open a Chat session with more than 30 messages.
   - Confirm initial view lands at the latest message.
   - Scroll upward and confirm older messages load in pages.
   - Continue until the earliest message and confirm no duplicate messages appear.
   - Open a report/artifact route with `artifact_id` and `output_id`.
   - Confirm the artifact opens in Canvas.
   - Confirm the linked Chat message is located through the same timeline pagination path.

4. Encoding safety:
   - Reopen changed files.
   - Run targeted corruption-marker scan on changed source and docs.

5. Repository validation:
   - Run `python scripts/validate_change.py` from the active worktree if the script is present and dependencies are available.

## Acceptance Criteria

The change is complete only when:

1. There is no artifact-specific initial Chat history page size.
2. Normal Chat entry and artifact route entry share the same initial message loading strategy.
3. Upward scrolling loads older persisted messages until the earliest message.
4. Canvas jump-to-conversation still works when the linked message is not in the initial page.
5. Prepending older messages does not visibly throw the user to a different conversation position.
6. Relevant checks and manual verification results are recorded before marking the task done.

## Implementation Record

Implemented on 2026-05-11 in `frontend/src/components/chat/ChatPanel.tsx`.

Changes made:

1. Removed the artifact-specific initial history limit. Chat now always requests `INITIAL_HISTORY_MESSAGE_LIMIT` for the initial persisted-message page.
2. Added top-scroll pagination on the Chat scroll container. When the user scrolls near the top, the frontend fetches the next older page with `before=oldestLoadedMessageIdRef.current`.
3. Preserved scroll position after prepending older messages by restoring the offset from the previous scroll height.
4. Refactored jump-to-message behavior into one shared `scrollToMessage` helper.
5. Kept Canvas "jump to conversation" on the same helper.
6. Added route artifact positioning: when an artifact route resolves a `linkedMessageId`, Chat uses the same `scrollToMessage` path instead of a separate message-loading path.

Validation run:

1. `git diff --check`: passed.
2. Targeted corruption-marker scan on changed files: passed.
3. `npm run lint` from `frontend/`: passed with 3 pre-existing warnings outside the changed file.
4. `npx tsc --noEmit --pretty false` from `frontend/`: passed.
5. `npm run build` from `frontend/`: passed.
6. `python3 scripts/validate_change.py`: passed.
7. Frontend validation server: `http://127.0.0.1:3000`, `/chat/test-session` returned HTTP 200.

Known validation note:

- This worktree does not have backend `.env.local`, and no backend service is listening on the frontend default API base `http://127.0.0.1:8001/api/v1`. The frontend server is ready for UI verification, but full live Chat data verification requires starting or pointing to a backend runtime.

'use client';

import { useEffect, useMemo, useState } from 'react';

import type { BrowserState } from '@/types/agent';
import { useAioTakeoverStore } from '@/stores/aioTakeoverStore';
import { getPlatformDisplayName } from '@/config/platformLabel';

const TAKEOVER_STATE_LABELS = {
  requested: '待签发',
  issued: '等待打开',
  active: '操作中',
  resolved: '已完成',
  expired: '已失效，可重新打开',
  cancelled: '已跳过',
  resume_failed: '未检测到完成，可重新打开',
} as const;

type SubmitAction = 'open' | 'completed' | 'skip' | null;

interface BrowserActionBannerProps {
  browserState: BrowserState;
  isOpened: boolean;
  openedAtMs?: number;
  onOpenTakeover?: (() => void | Promise<void>) | null;
  onResolve?: (() => void | Promise<void>) | null;
  onSkip?: (() => void | Promise<void>) | null;
}

const OPERATION_WINDOW_MS = 10 * 60 * 1000;

function formatRemainingTime(expiresAtMs?: number | null, nowMs?: number): string | null {
  if (!expiresAtMs) return null;
  const expiry = expiresAtMs;
  if (Number.isNaN(expiry)) return null;
  const remainingMs = Math.max(expiry - (nowMs ?? Date.now()), 0);
  const totalSeconds = Math.floor(remainingMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

export function BrowserActionBanner({
  browserState,
  isOpened,
  openedAtMs,
  onOpenTakeover,
  onResolve,
  onSkip,
}: BrowserActionBannerProps) {
  const [localSubmitting, setLocalSubmitting] = useState<SubmitAction>(null);
  const [nowMs, setNowMs] = useState(Date.now());
  const takeoverId = browserState.takeover?.takeoverId ?? null;
  const takeoverRecord = useAioTakeoverStore((state) =>
    takeoverId ? state.records[takeoverId] ?? null : null,
  );

  useEffect(() => {
    if (!takeoverId) return;
    const timer = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [takeoverId]);

  const platformLabel = getPlatformDisplayName(browserState.platform);
  const hasTakeover = Boolean(takeoverId);
  const takeoverState = takeoverRecord?.takeoverState ?? (hasTakeover ? 'issued' : null);
  const blockingUrl =
    takeoverRecord?.blockingUrl ??
    takeoverRecord?.accessBundle.blockingUrl ??
    browserState.takeover?.blockingUrl ??
    browserState.blockingUrl ??
    null;
  const targetUrl =
    takeoverRecord?.targetUrl ??
    takeoverRecord?.accessBundle.targetUrl ??
    browserState.takeover?.targetUrl ??
    null;
  const sceneUrl = blockingUrl || targetUrl;
  const isTerminalTakeoverState =
    takeoverState === 'resolved' ||
    takeoverState === 'expired' ||
    takeoverState === 'cancelled' ||
    takeoverState === 'resume_failed';
  const operationWindowExpiresAtMs = openedAtMs
    ? openedAtMs + OPERATION_WINDOW_MS
    : null;
  const isClientWindowExpired = Boolean(
    isOpened &&
      operationWindowExpiresAtMs &&
      operationWindowExpiresAtMs <= nowMs &&
      !isTerminalTakeoverState,
  );
  const effectiveTakeoverState =
    isOpened &&
    !isTerminalTakeoverState &&
    (takeoverState === 'issued' || takeoverState === 'requested')
      ? 'active'
      : takeoverState;
  const remainingLabel = isOpened && !isTerminalTakeoverState
    ? formatRemainingTime(operationWindowExpiresAtMs, nowMs)
    : null;
  const title = browserState.actionType === 'verify'
    ? `${platformLabel} 需要验证`
    : browserState.actionType === 'login'
      ? `${platformLabel} 需要登录`
      : browserState.actionType === 'modal'
        ? `${platformLabel} 需要确认`
        : `${platformLabel} 需要处理`;
  const detail = browserState.actionHint || browserState.message;
  const helperText = hasTakeover
    ? takeoverState === 'cancelled'
      ? '该平台已跳过，本轮不会再次请求人工接管。'
      : takeoverState === 'resolved'
        ? '该平台接管已完成，系统会继续后续抓取流程。'
      : takeoverState === 'expired' ||
      takeoverState === 'resume_failed' ||
      isClientWindowExpired
      ? '本次浏览器会话已失效。如果还要继续，请重新打开浏览器；旧会话已经不会继续。'
      : isOpened
        ? '浏览器已打开，系统正在为当前平台保留操作窗口。完成登录或验证后，请回到这里点击“我已完成”。'
        : '点击“打开浏览器”后开始人工接管；只会打开当前平台，不会连带打开其他平台。'
    : '完成当前操作后，请直接点击“我已完成”。';
  const stateLabel =
    isClientWindowExpired
      ? '已失效，可重新打开'
      : effectiveTakeoverState && effectiveTakeoverState in TAKEOVER_STATE_LABELS
      ? TAKEOVER_STATE_LABELS[
          effectiveTakeoverState as keyof typeof TAKEOVER_STATE_LABELS
        ]
      : browserState.requiresAction
        ? '待处理'
        : '已处理';
  const isResolvedState = takeoverState === 'resolved';
  const isCancelledState = takeoverState === 'cancelled';
  const isSettledState = isResolvedState || isCancelledState;

  const containerStyle = isResolvedState
    ? {
        background: 'rgba(15, 23, 42, 0.02)',
        borderColor: 'rgba(15, 23, 42, 0.08)',
      }
    : isCancelledState
      ? {
          background: 'rgba(15, 23, 42, 0.018)',
          borderColor: 'rgba(15, 23, 42, 0.07)',
        }
      : {
          background: 'rgba(245, 158, 11, 0.08)',
          borderColor: 'rgba(245, 158, 11, 0.18)',
        };
  const dotStyle = isResolvedState
    ? { background: 'rgba(34, 197, 94, 0.9)' }
    : isCancelledState
      ? { background: 'rgba(100, 116, 139, 0.8)' }
      : { background: 'var(--warning)' };
  const stateBadgeStyle = isResolvedState
    ? {
        background: 'rgba(34, 197, 94, 0.1)',
        color: 'var(--success)',
      }
    : isCancelledState
      ? {
          background: 'rgba(148, 163, 184, 0.12)',
          color: 'var(--text-secondary)',
        }
      : {
          background: 'var(--bg-secondary)',
          color: 'var(--text-secondary)',
        };
  const detailTextColor = isSettledState ? 'var(--text-primary)' : 'var(--text-secondary)';
  const helperTextColor = isSettledState ? 'var(--text-secondary)' : 'var(--text-tertiary)';
  const sceneTextColor = isSettledState ? 'var(--text-secondary)' : 'var(--text-tertiary)';

  const canResolve =
    Boolean(onResolve) &&
    (!hasTakeover || (isOpened && !isTerminalTakeoverState && !isClientWindowExpired));
  const canSkip =
    Boolean(onSkip) &&
    takeoverState !== 'resolved' &&
    takeoverState !== 'cancelled';
  const canOpenTakeover =
    Boolean(onOpenTakeover) &&
    takeoverState !== 'resolved' &&
    takeoverState !== 'cancelled';

  const countdownLabel = useMemo(() => {
    if (!remainingLabel) return null;
    if (remainingLabel === '00:00') {
      return '已超时';
    }
    return `剩余 ${remainingLabel}`;
  }, [remainingLabel]);

  const openButtonLabel = (() => {
    if (localSubmitting === 'open') return '正在打开...';
    if (takeoverState === 'expired' || takeoverState === 'resume_failed' || isClientWindowExpired) {
      return '重新打开浏览器';
    }
    return isOpened ? '重新打开浏览器' : '打开浏览器';
  })();

  const runAction = async (
    action: Exclude<SubmitAction, null>,
    fn: (() => void | Promise<void>) | null | undefined,
  ) => {
    if (!fn || localSubmitting) return;
    try {
      setLocalSubmitting(action);
      await fn();
    } finally {
      setLocalSubmitting(null);
    }
  };

  return (
    <div
      className="rounded-2xl border px-4 py-4"
      style={containerStyle}
    >
      <div className="flex items-start gap-3">
        <div
          className="mt-1 h-2.5 w-2.5 rounded-full"
          style={dotStyle}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {title}
            </p>
            <span
              className="rounded-full px-2 py-0.5 text-[11px]"
              style={stateBadgeStyle}
            >
              {stateLabel}
            </span>
            {countdownLabel && (
              <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                {countdownLabel}
              </span>
            )}
          </div>

          <p className="mt-1 text-sm leading-6" style={{ color: detailTextColor }}>
            {detail}
          </p>
          <p className="mt-1 text-xs leading-5" style={{ color: helperTextColor }}>
            {helperText}
          </p>
          {sceneUrl && (
            <p className="mt-1 truncate text-xs" style={{ color: sceneTextColor }}>
              {blockingUrl ? '当前阻塞页面：' : '目标页面：'}
              {sceneUrl}
            </p>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {hasTakeover ? (
              <>
                {canOpenTakeover && (
                  <button
                    type="button"
                    onClick={() => runAction('open', onOpenTakeover)}
                    disabled={!canOpenTakeover || localSubmitting !== null}
                    className="rounded-full px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
                    style={{
                      background: 'var(--color-primary)',
                      color: '#fff',
                    }}
                  >
                    {openButtonLabel}
                  </button>
                )}
                {isOpened && !isTerminalTakeoverState && !isClientWindowExpired && (
                  <button
                    type="button"
                    onClick={() => runAction('completed', onResolve)}
                    disabled={!canResolve || localSubmitting !== null}
                    className="rounded-full px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
                    style={{
                      background: 'rgba(34, 197, 94, 0.12)',
                      color: 'var(--success)',
                      border: '1px solid rgba(34, 197, 94, 0.22)',
                    }}
                  >
                    {localSubmitting === 'completed' ? '正在提交完成...' : '我已完成'}
                  </button>
                )}
                {canSkip && (
                  <button
                    type="button"
                    onClick={() => runAction('skip', onSkip)}
                    disabled={!canSkip || localSubmitting !== null}
                    className="rounded-full px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
                    style={{
                      border: '1px solid var(--border-subtle)',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    {localSubmitting === 'skip' ? '正在跳过...' : '跳过此平台'}
                  </button>
                )}
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => runAction('completed', onResolve)}
                  disabled={!canResolve || localSubmitting !== null}
                  className="rounded-full px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
                  style={{
                    background: 'var(--color-primary)',
                    color: '#fff',
                  }}
                >
                  {localSubmitting === 'completed' ? '已提交，正在继续处理...' : '我已完成'}
                </button>
                <button
                  type="button"
                  onClick={() => runAction('skip', onSkip)}
                  disabled={!canSkip || localSubmitting !== null}
                  className="rounded-full px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
                  style={{
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {localSubmitting === 'skip' ? '已提交跳过...' : '跳过此平台'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

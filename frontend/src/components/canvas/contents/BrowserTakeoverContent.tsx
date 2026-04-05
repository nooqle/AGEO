'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  RiAlertLine,
  RiExternalLinkLine,
  RiRefreshLine,
  RiShieldKeyholeLine,
} from '@remixicon/react';

import { useCanvasStore } from '@/stores/canvasStore';
import { api, getApiBaseUrl } from '@/services/api';
import { getStoredAccessToken } from '@/lib/auth-storage';
import type { BrowserCanvasContent } from '@/types/canvas';
import type {
  AioCanvasConfig,
  AioTakeoverRecord,
  AioTakeoverState,
  AioVncUrl,
} from '@/types/aio';

type RenderState =
  | 'hidden'
  | 'opening'
  | 'canvas_ready'
  | 'vnc_ready'
  | 'submitting'
  | 'error';

type BrowserUiController = {
  browser: {
    getTabsSnapshot: () => {
      activeTabId: string | null;
      tabs: Map<
        string,
        {
          url?: string | null;
          title?: string | null;
        }
      >;
    };
    subscribeTabChange: (callback: () => void) => () => void;
    activeTab: (tabId: string) => Promise<boolean>;
    closeTab: (tabId: string) => Promise<boolean>;
  };
  destroy: () => Promise<void>;
};

const PLATFORM_LABELS = {
  doubao: '豆包',
  deepseek: 'DeepSeek',
  kimi: 'Kimi',
  hunyuan: '元宝',
} as const;

const TAKEOVER_STATE_LABELS: Record<AioTakeoverState, string> = {
  requested: '等待',
  issued: '已签发',
  active: '接管中',
  resolved: '已提交',
  expired: '已过期',
  cancelled: '已取消',
  resume_failed: '恢复失败',
};

const DEFAULT_HEARTBEAT_MS = 10000;

function createFrontendId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `fe_${crypto.randomUUID()}`;
  }
  return `fe_${Math.random().toString(36).slice(2, 10)}`;
}

function getFrontendAccessToken(): string | null {
  const token = getStoredAccessToken();
  if (token) return token;
  if (process.env.NODE_ENV === 'development') return 'dev-token';
  return null;
}

function buildCanvasWsEndpoint(path: string): string {
  const apiBase = getApiBaseUrl();
  const url = new URL(path, apiBase);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const token = getFrontendAccessToken();
  if (token) {
    url.searchParams.set('token', token);
  }
  return url.toString();
}

function isInternalBrowserUrl(url?: string | null): boolean {
  if (!url) return true;
  const lowered = url.toLowerCase();
  return (
    lowered.startsWith('chrome://') ||
    lowered.startsWith('chrome-untrusted://') ||
    lowered.startsWith('devtools://')
  );
}

function formatExpiry(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface BrowserTakeoverContentProps {
  content: BrowserCanvasContent;
}

export function BrowserTakeoverContent({ content }: BrowserTakeoverContentProps) {
  const browserState = content.data.browserState;
  const takeover = browserState.takeover ?? null;
  const removeContent = useCanvasStore((state) => state.removeContent);
  const takeoverId = takeover?.takeoverId ?? null;

  const frontendId = useMemo(() => createFrontendId(), []);
  const platformLabel = PLATFORM_LABELS[browserState.platform] || browserState.platform;

  const [takeoverRecord, setTakeoverRecord] = useState<AioTakeoverRecord | null>(null);
  const [canvasConfig, setCanvasConfig] = useState<AioCanvasConfig | null>(null);
  const [vncConfig, setVncConfig] = useState<AioVncUrl | null>(null);
  const [renderState, setRenderState] = useState<RenderState>('hidden');
  const [currentMode, setCurrentMode] = useState<'canvas_cdp' | 'vnc_fallback' | null>(null);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [missedHeartbeats, setMissedHeartbeats] = useState(0);
  const [canvasMounted, setCanvasMounted] = useState(false);

  const canvasRootRef = useRef<HTMLDivElement | null>(null);
  const browserUiRef = useRef<BrowserUiController | null>(null);
  const tabSyncUnsubscribeRef = useRef<(() => void) | null>(null);

  const canvasCdpEndpoint = canvasConfig?.cdpEndpoint ?? null;
  const heartbeatIntervalMs = canvasConfig?.heartbeatIntervalMs || DEFAULT_HEARTBEAT_MS;
  const takeoverState = takeoverRecord?.takeoverState || 'issued';
  const takeoverMode = takeoverRecord?.mode ?? takeover?.mode ?? null;
  const canvasConfigPath =
    takeoverRecord?.accessBundle?.canvasConfigPath ?? takeover?.canvasConfigPath ?? null;
  const vncUrlPath = takeoverRecord?.accessBundle?.vncUrlPath ?? takeover?.vncUrlPath ?? null;
  const heartbeatPath =
    takeoverRecord?.accessBundle?.heartbeatPath ?? takeover?.heartbeatPath ?? null;
  const resolvePath = takeoverRecord?.accessBundle?.resolvePath ?? takeover?.resolvePath ?? null;
  const cancelPath = takeoverRecord?.accessBundle?.cancelPath ?? takeover?.cancelPath ?? null;
  const expiryText = formatExpiry(takeoverRecord?.expiresAt || takeover?.expiresAt);

  const destroyBrowserUi = useCallback(async () => {
    tabSyncUnsubscribeRef.current?.();
    tabSyncUnsubscribeRef.current = null;
    const instance = browserUiRef.current;
    browserUiRef.current = null;
    setCanvasMounted(false);
    if (instance) {
      await instance.destroy().catch(() => undefined);
    }
    if (canvasRootRef.current) {
      canvasRootRef.current.innerHTML = '';
    }
  }, []);

  const ensurePreferredCanvasTab = useCallback(async (): Promise<boolean> => {
    const instance = browserUiRef.current;
    if (!instance) return false;

    const snapshot = instance.browser.getTabsSnapshot();
    const preferredTabEntry = Array.from(snapshot.tabs.entries()).find(
      ([, tab]) => !isInternalBrowserUrl(tab?.url),
    );
    if (!preferredTabEntry) {
      return false;
    }

    if (snapshot.activeTabId !== preferredTabEntry[0]) {
      await instance.browser.activeTab(preferredTabEntry[0]).catch(() => false);
    }

    const afterSwitch = instance.browser.getTabsSnapshot();
    const activeTab = afterSwitch.activeTabId
      ? afterSwitch.tabs.get(afterSwitch.activeTabId)
      : null;

    if (
      activeTab &&
      !isInternalBrowserUrl(activeTab.url) &&
      activeTab.url === preferredTabEntry[1]?.url
    ) {
      return true;
    }

    const staleInternalTabId = afterSwitch.activeTabId;
    if (
      staleInternalTabId &&
      staleInternalTabId !== preferredTabEntry[0] &&
      isInternalBrowserUrl(afterSwitch.tabs.get(staleInternalTabId)?.url)
    ) {
      await instance.browser.closeTab(staleInternalTabId).catch(() => false);
    }

    const latestSnapshot = instance.browser.getTabsSnapshot();
    const latestActiveTab = latestSnapshot.activeTabId
      ? latestSnapshot.tabs.get(latestSnapshot.activeTabId)
      : null;
    return Boolean(
      latestActiveTab &&
        !isInternalBrowserUrl(latestActiveTab.url) &&
        latestActiveTab.url === preferredTabEntry[1]?.url,
    );
  }, []);

  const loadVncFallback = useCallback(async () => {
    if (!vncUrlPath) {
      setRenderState('error');
      setStatusText('VNC 不可用');
      return;
    }

    const vnc = await api.getAioTakeoverVncUrl(vncUrlPath);
    setVncConfig(vnc);
    setCurrentMode('vnc_fallback');
    if (!vnc.upstreamVncAvailable) {
      setRenderState('error');
      setStatusText('VNC 不可用');
      return;
    }
    setRenderState('vnc_ready');
    setStatusText(null);
  }, [vncUrlPath]);

  useEffect(() => {
    if (!takeoverId) {
      setRenderState('hidden');
      return;
    }

    let cancelled = false;

    const loadTakeover = async () => {
      setRenderState('opening');
      setCurrentMode(takeoverMode);
      setStatusText(null);
      setMissedHeartbeats(0);
      setCanvasConfig(null);
      setVncConfig(null);
      await destroyBrowserUi();

      try {
        const record = await api.getAioTakeover(takeoverId);
        if (cancelled) return;
        setTakeoverRecord(record);

        if (takeoverMode === 'canvas_cdp' && canvasConfigPath) {
          const config = await api.getAioTakeoverCanvasConfig(canvasConfigPath);
          if (cancelled) return;
          setCanvasConfig(config);
          setCurrentMode('canvas_cdp');
          setRenderState('opening');
          return;
        }

        await loadVncFallback();
      } catch (error) {
        if (cancelled) return;
        setRenderState('error');
        setStatusText(error instanceof Error ? error.message : '初始化失败');
      }
    };

    void loadTakeover();

    return () => {
      cancelled = true;
    };
  }, [canvasConfigPath, destroyBrowserUi, loadVncFallback, takeoverId, takeoverMode]);

  useEffect(() => {
    if (!takeoverId || currentMode !== 'canvas_cdp' || !canvasCdpEndpoint || !canvasRootRef.current) {
      return;
    }

    let cancelled = false;

    const mountBrowserUi = async () => {
      try {
        await destroyBrowserUi();
        const { BrowserUI } = await import('@agent-infra/browser-ui');
        if (cancelled || !canvasRootRef.current) return;

        const instance = await BrowserUI.create({
          root: canvasRootRef.current,
          browserOptions: {
            connect: {
              browserWSEndpoint: buildCanvasWsEndpoint(canvasCdpEndpoint),
            },
            cast: {
              format: 'jpeg',
              quality: 80,
            },
          },
        });

        if (cancelled) {
          await instance.destroy().catch(() => undefined);
          return;
        }

        const browserUi = instance as BrowserUiController;
        browserUiRef.current = browserUi;
        tabSyncUnsubscribeRef.current = browserUi.browser.subscribeTabChange(() => {
          void ensurePreferredCanvasTab();
        });

        const retryDelaysMs = [0, 150, 500, 1000, 1800];
        for (const delayMs of retryDelaysMs) {
          if (delayMs > 0) {
            await new Promise((resolve) => window.setTimeout(resolve, delayMs));
          }
          if (cancelled) return;
          const ready = await ensurePreferredCanvasTab();
          if (ready) {
            break;
          }
        }

        setCanvasMounted(true);
        setRenderState('canvas_ready');
        setStatusText(null);
      } catch (error) {
        if (cancelled) return;
        await destroyBrowserUi();
        await loadVncFallback().catch(() => undefined);
        if (!vncUrlPath) {
          setRenderState('error');
          setStatusText(error instanceof Error ? error.message : 'Canvas 失败');
        }
      }
    };

    void mountBrowserUi();

    return () => {
      cancelled = true;
      void destroyBrowserUi();
    };
  }, [
    canvasCdpEndpoint,
    currentMode,
    destroyBrowserUi,
    ensurePreferredCanvasTab,
    loadVncFallback,
    takeoverId,
    vncUrlPath,
  ]);

  useEffect(() => {
    const heartbeatReady =
      renderState === 'vnc_ready' || (renderState === 'canvas_ready' && canvasMounted);
    if (!takeoverId || !heartbeatReady || !heartbeatPath) {
      return;
    }

    let cancelled = false;

    const sendHeartbeat = async () => {
      try {
        const next = await api.heartbeatAioTakeover(heartbeatPath, {
          frontendId,
          mode: currentMode || 'vnc_fallback',
        });
        if (cancelled) return;
        setTakeoverRecord(next);
        setMissedHeartbeats(0);
        setStatusText(null);
      } catch {
        if (cancelled) return;
        setMissedHeartbeats((value) => {
          const next = value + 1;
          if (next >= 3) {
            setRenderState('error');
            setStatusText('连接中断');
          }
          return next;
        });
      }
    };

    void sendHeartbeat();
    const timer = window.setInterval(() => {
      void sendHeartbeat();
    }, heartbeatIntervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [canvasMounted, currentMode, frontendId, heartbeatIntervalMs, heartbeatPath, renderState, takeoverId]);

  const closeTakeoverCanvas = useCallback(async () => {
    await destroyBrowserUi();
    removeContent(content.id);
  }, [content.id, destroyBrowserUi, removeContent]);

  useEffect(() => {
    if (takeoverState === 'resolved') {
      void closeTakeoverCanvas();
      return;
    }
    if (takeoverState === 'expired') {
      setRenderState('error');
      setStatusText('已过期');
      return;
    }
    if (takeoverState === 'cancelled') {
      setRenderState('error');
      setStatusText('已取消');
      return;
    }
    if (takeoverState === 'resume_failed') {
      setRenderState('error');
      setStatusText('恢复失败');
    }
  }, [closeTakeoverCanvas, takeoverState]);

  const handleResolve = async () => {
    if (!resolvePath || renderState === 'submitting') {
      return;
    }
    setRenderState('submitting');
    setStatusText('恢复中');
    try {
      const next = await api.resolveAioTakeover(resolvePath, {
        frontendId,
        mode: currentMode || 'vnc_fallback',
        resumeGateResult: 'pass',
        clientObservation: 'user_claimed_done',
      });
      setTakeoverRecord(next);
      if (next.takeoverState === 'resolved') {
        await closeTakeoverCanvas();
        return;
      }
      setRenderState('error');
      setStatusText(
        next.resumeGateResult === 'fail_login_required'
          ? '登录未完成'
          : next.resumeGateResult === 'fail_captcha_required'
            ? '验证未完成'
            : next.resumeGateResult === 'fail_ui_not_ready'
              ? '页面未就绪'
              : next.resumeGateResult === 'fail_state_corrupt'
                ? '状态损坏'
                : '恢复失败',
      );
    } catch (error) {
      setRenderState('error');
      setStatusText(error instanceof Error ? error.message : '恢复失败');
    }
  };

  const handleCancel = async () => {
    if (!cancelPath || renderState === 'submitting') {
      return;
    }
    setRenderState('submitting');
    setStatusText('取消中');
    try {
      const next = await api.cancelAioTakeover(cancelPath, {
        frontendId,
        reason: 'user_cancelled',
      });
      setTakeoverRecord(next);
      await closeTakeoverCanvas();
    } catch (error) {
      setRenderState('error');
      setStatusText(error instanceof Error ? error.message : '取消失败');
    }
  };

  const handleSwitchToVnc = async () => {
    setRenderState('opening');
    setStatusText(null);
    try {
      await destroyBrowserUi();
      await loadVncFallback();
    } catch (error) {
      setRenderState('error');
      setStatusText(error instanceof Error ? error.message : '切换失败');
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <div className="min-w-0">
          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {browserState.actionHint || browserState.message}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
            <span
              className="rounded-full px-2 py-1"
              style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
            >
              {platformLabel}
            </span>
            <span
              className="rounded-full px-2 py-1"
              style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
            >
              {TAKEOVER_STATE_LABELS[takeoverState]}
            </span>
            <span
              className="rounded-full px-2 py-1"
              style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
            >
              {currentMode === 'vnc_fallback' ? 'VNC' : 'Canvas'}
            </span>
            {expiryText && (
              <span style={{ color: 'var(--text-tertiary)' }}>
                {expiryText}
              </span>
            )}
          </div>
        </div>
        <div className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
          {missedHeartbeats > 0 ? `HB ${missedHeartbeats}` : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 bg-black">
        {currentMode === 'canvas_cdp' && renderState !== 'error' && (
          <div className="relative h-full">
            <div ref={canvasRootRef} className="h-full w-full overflow-hidden" />
            {renderState !== 'canvas_ready' && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/70">
                <div
                  className="h-9 w-9 animate-spin rounded-full border-2"
                  style={{
                    borderColor: 'rgba(99, 102, 241, 0.16)',
                    borderTopColor: 'var(--color-primary)',
                  }}
                />
              </div>
            )}
          </div>
        )}

        {renderState === 'opening' && currentMode !== 'canvas_cdp' && (
          <div className="flex h-full items-center justify-center bg-black">
            <div
              className="h-9 w-9 animate-spin rounded-full border-2"
              style={{
                borderColor: 'rgba(99, 102, 241, 0.16)',
                borderTopColor: 'var(--color-primary)',
              }}
            />
          </div>
        )}

        {renderState === 'vnc_ready' && vncConfig?.url && (
          <iframe
            title={`${platformLabel} takeover`}
            src={vncConfig.url}
            className="h-full w-full bg-black"
          />
        )}

        {renderState === 'error' && (
          <div className="flex h-full flex-col items-center justify-center gap-3 bg-black px-6 text-center">
            <RiAlertLine className="h-8 w-8" style={{ color: 'var(--status-danger)' }} />
            <div className="text-sm" style={{ color: '#fff' }}>
              {statusText || '不可用'}
            </div>
          </div>
        )}
      </div>

      <div
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{ borderTop: '1px solid var(--border-subtle)' }}
      >
        <div className="min-w-0 text-xs" style={{ color: 'var(--text-secondary)' }}>
          {statusText || browserState.message}
        </div>
        <div className="flex items-center gap-2">
          {currentMode !== 'vnc_fallback' && vncUrlPath && (
            <button
              type="button"
              onClick={handleSwitchToVnc}
              disabled={renderState === 'submitting'}
              className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
              style={{
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-secondary)',
              }}
            >
              <RiExternalLinkLine className="h-3.5 w-3.5" />
              VNC
            </button>
          )}
          {renderState === 'error' && vncUrlPath && (
            <button
              type="button"
              onClick={handleSwitchToVnc}
              className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition"
              style={{
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-secondary)',
              }}
            >
              <RiRefreshLine className="h-3.5 w-3.5" />
              重试
            </button>
          )}
          <button
            type="button"
            onClick={handleResolve}
            disabled={renderState === 'opening' || renderState === 'submitting'}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
          >
            <RiShieldKeyholeLine className="h-3.5 w-3.5" />
            完成
          </button>
          <button
            type="button"
            onClick={handleCancel}
            disabled={renderState === 'submitting'}
            className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            取消
          </button>
        </div>
      </div>
    </div>
  );
}

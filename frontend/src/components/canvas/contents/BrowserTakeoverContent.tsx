'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  RiAlertLine,
  RiExternalLinkLine,
  RiRefreshLine,
} from '@remixicon/react';

import { api, getApiBaseUrl } from '@/services/api';
import { getStoredAccessToken } from '@/lib/auth-storage';
import { useAioTakeoverStore } from '@/stores/aioTakeoverStore';
import type { BrowserCanvasContent } from '@/types/canvas';
import type {
  AioCanvasConfig,
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
  destroy: () => Promise<void>;
};

const PLATFORM_LABELS = {
  doubao: '豆包',
  deepseek: 'DeepSeek',
  kimi: 'Kimi',
  hunyuan: '元宝',
} as const;

const DEFAULT_RENDER_MODE: 'canvas_cdp' | 'vnc_fallback' = 'vnc_fallback';
const CANVAS_BOOT_TIMEOUT_MS = 12000;
const TAKEOVER_REQUEST_TIMEOUT_MS = 12000;
const CANVAS_BOOT_TIMEOUT_ERROR = '__canvas_boot_timeout__';
const BENIGN_TARGET_CLOSE_PATTERNS = [
  'TargetCloseError',
  'Target closed',
  'Page.screencastFrameAck',
];

function isBenignTargetCloseError(value: unknown): boolean {
  const message =
    value instanceof Error
      ? `${value.name}: ${value.message}`
      : typeof value === 'string'
        ? value
        : value && typeof value === 'object' && 'message' in value
          ? String((value as { message?: unknown }).message ?? '')
          : '';
  return BENIGN_TARGET_CLOSE_PATTERNS.some((pattern) => message.includes(pattern));
}

function normalizeRenderMode(
  mode?: 'canvas_cdp' | 'vnc_fallback' | null,
): 'canvas_cdp' | 'vnc_fallback' {
  return mode === 'canvas_cdp' ? DEFAULT_RENDER_MODE : (mode ?? DEFAULT_RENDER_MODE);
}

const TAKEOVER_STATE_LABELS: Record<AioTakeoverState, string> = {
  requested: '等待',
  issued: '已签发',
  active: '接管中',
  resolved: '已提交',
  expired: '已过期',
  cancelled: '已取消',
  resume_failed: '恢复失败',
};

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

function formatExpiry(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

async function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  timeoutCode: string,
): Promise<T> {
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timeoutHandle = setTimeout(
          () => reject(new Error(timeoutCode)),
          timeoutMs,
        );
      }),
    ]);
  } finally {
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
    }
  }
}

interface BrowserTakeoverContentProps {
  content: BrowserCanvasContent;
}

export function BrowserTakeoverContent({
  content,
}: BrowserTakeoverContentProps) {
  const browserState = content.data.browserState;
  const takeover = browserState.takeover ?? null;
  const takeoverId = takeover?.takeoverId ?? null;
  const takeoverRecord = useAioTakeoverStore((state) =>
    takeoverId ? state.records[takeoverId] ?? null : null,
  );
  const takeoverRegistration = useAioTakeoverStore((state) =>
    takeoverId ? state.registrations[takeoverId] ?? null : null,
  );
  const upsertTakeoverRecord = useAioTakeoverStore(
    (state) => state.upsertRecord,
  );
  const setTakeoverMode = useAioTakeoverStore(
    (state) => state.setTakeoverMode,
  );
  const setHeartbeatInterval = useAioTakeoverStore(
    (state) => state.setHeartbeatInterval,
  );
  const removeRegistration = useAioTakeoverStore(
    (state) => state.removeRegistration,
  );

  const platformLabel =
    PLATFORM_LABELS[browserState.platform] || browserState.platform;

  const [canvasConfig, setCanvasConfig] = useState<AioCanvasConfig | null>(null);
  const [vncConfig, setVncConfig] = useState<AioVncUrl | null>(null);
  const [renderState, setRenderState] = useState<RenderState>('hidden');
  const [currentMode, setCurrentMode] = useState<'canvas_cdp' | 'vnc_fallback'>(
    normalizeRenderMode(takeoverRegistration?.mode),
  );
  const [statusText, setStatusText] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const canvasRootRef = useRef<HTMLDivElement | null>(null);
  const browserUiRef = useRef<BrowserUiController | null>(null);

  const canvasCdpEndpoint = canvasConfig?.cdpEndpoint ?? null;
  const takeoverState = takeoverRecord?.takeoverState || 'issued';
  const canvasConfigPath =
    takeoverRecord?.accessBundle.canvasConfigPath ??
    takeover?.canvasConfigPath ??
    null;
  const vncUrlPath =
    takeoverRecord?.accessBundle.vncUrlPath ?? takeover?.vncUrlPath ?? null;
  const expiryText = formatExpiry(
    takeoverRecord?.expiresAt || takeover?.expiresAt,
  );
  const targetUrl =
    canvasConfig?.targetUrl ??
    takeoverRecord?.targetUrl ??
    takeoverRecord?.accessBundle.targetUrl ??
    takeover?.targetUrl ??
    content.data.targetUrl ??
    null;

  const destroyBrowserUi = useCallback(async () => {
    const instance = browserUiRef.current;
    browserUiRef.current = null;
    if (instance) {
      await instance.destroy().catch(() => undefined);
    }
    if (canvasRootRef.current) {
      canvasRootRef.current.innerHTML = '';
    }
  }, []);

  const loadVncFallback = useCallback(async () => {
    if (!vncUrlPath) {
      setRenderState('error');
      setStatusText('当前云电脑暂时不可用，请重新打开浏览器。');
      return;
    }

    const vnc = await withTimeout(
      api.getAioTakeoverVncUrl(vncUrlPath),
      TAKEOVER_REQUEST_TIMEOUT_MS,
      'vnc_config_timeout',
    );
    setVncConfig(vnc);
    setCurrentMode('vnc_fallback');
    if (takeoverId) {
      setTakeoverMode(takeoverId, 'vnc_fallback');
    }
    if (!vnc.upstreamVncAvailable) {
      setRenderState('error');
      setStatusText('当前云电脑暂时不可用，请重新打开浏览器。');
      return;
    }
    setRenderState('vnc_ready');
    setStatusText(null);
  }, [setTakeoverMode, takeoverId, vncUrlPath]);

  useEffect(() => {
    if (!takeoverId) {
      setRenderState('hidden');
      return;
    }

    let cancelled = false;

    const loadTakeoverRecord = async () => {
      try {
        const record = await withTimeout(
          api.getAioTakeover(takeoverId),
          TAKEOVER_REQUEST_TIMEOUT_MS,
          'takeover_record_timeout',
        );
        if (cancelled) return;
        upsertTakeoverRecord(record);
      } catch {
        if (cancelled) return;
        setRenderState('error');
        setStatusText('云电脑初始化失败，请重新打开浏览器。');
      }
    };

    void loadTakeoverRecord();
    return () => {
      cancelled = true;
    };
  }, [takeoverId, upsertTakeoverRecord]);

  useEffect(() => {
    if (!takeoverId || !takeoverRegistration?.mode) {
      return;
    }
    setCurrentMode(normalizeRenderMode(takeoverRegistration.mode));
  }, [takeoverId, takeoverRegistration?.mode]);

  useEffect(() => {
    if (browserState.state !== 'submitting') {
      return;
    }

    setRenderState('submitting');
    setStatusText('正在确认当前平台操作，马上继续抓取...');
    void destroyBrowserUi();
  }, [browserState.state, destroyBrowserUi]);

  useEffect(() => {
    if (!takeoverId) {
      return;
    }

    let cancelled = false;

    const loadCanvasConfig = async () => {
      if (currentMode !== 'canvas_cdp' || !canvasConfigPath) {
        return;
      }

      setRenderState('opening');
      setStatusText(null);
      setVncConfig(null);
      await destroyBrowserUi();

      try {
        const config = await withTimeout(
          api.getAioTakeoverCanvasConfig(canvasConfigPath),
          TAKEOVER_REQUEST_TIMEOUT_MS,
          'canvas_config_timeout',
        );
        if (cancelled) return;
        setCanvasConfig(config);
        setHeartbeatInterval(takeoverId, config.heartbeatIntervalMs);
        setStatusText(null);
      } catch {
        if (cancelled) return;
        setCanvasConfig(null);
        if (vncUrlPath) {
          setCurrentMode('vnc_fallback');
          setTakeoverMode(takeoverId, 'vnc_fallback');
          try {
            await loadVncFallback();
            return;
          } catch {
            // fall through to friendly error state
          }
        }
        setRenderState('error');
        setStatusText('云电脑连接失败，请重新打开浏览器。');
      }
    };

    const loadVncConfig = async () => {
      if (currentMode !== 'vnc_fallback') {
        return;
      }
      setCanvasConfig(null);
      setRenderState('opening');
      setStatusText(null);
      await destroyBrowserUi();
      try {
        await loadVncFallback();
      } catch {
        if (cancelled) return;
        setRenderState('error');
        setStatusText('云电脑连接失败，请重新打开浏览器。');
      }
    };

    void loadCanvasConfig();
    void loadVncConfig();

    return () => {
      cancelled = true;
    };
  }, [
    canvasConfigPath,
    currentMode,
    destroyBrowserUi,
    loadVncFallback,
    reloadNonce,
    setHeartbeatInterval,
    setTakeoverMode,
    takeoverId,
    vncUrlPath,
  ]);

  useEffect(() => {
    if (
      !takeoverId ||
      currentMode !== 'canvas_cdp' ||
      browserState.state === 'submitting' ||
      !canvasCdpEndpoint ||
      !canvasRootRef.current
    ) {
      return;
    }

    let cancelled = false;

    const mountBrowserUi = async () => {
      let timedOut = false;
      let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
      try {
        await destroyBrowserUi();
        const { BrowserUI } = await import('@agent-infra/browser-ui');
        if (cancelled || !canvasRootRef.current) return;

        const createPromise = BrowserUI.create({
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
        createPromise
          .then(async (instance) => {
            if (timedOut || cancelled) {
              await instance.destroy().catch(() => undefined);
            }
          })
          .catch(() => undefined);
        const timeoutPromise = new Promise<never>((_, reject) => {
          timeoutHandle = setTimeout(() => {
            timedOut = true;
            reject(new Error(CANVAS_BOOT_TIMEOUT_ERROR));
          }, CANVAS_BOOT_TIMEOUT_MS);
        });

        const instance = await Promise.race([createPromise, timeoutPromise]);
        if (timeoutHandle) {
          clearTimeout(timeoutHandle);
        }

        if (cancelled) {
          await instance.destroy().catch(() => undefined);
          return;
        }

        browserUiRef.current = instance as BrowserUiController;
        setRenderState('canvas_ready');
        setStatusText(null);
      } catch (error) {
        if (timeoutHandle) {
          clearTimeout(timeoutHandle);
        }
        if (cancelled) return;
        await destroyBrowserUi();
        if (error instanceof Error && error.message === CANVAS_BOOT_TIMEOUT_ERROR) {
          if (vncUrlPath) {
            setStatusText('云电脑连接较慢，已自动切换到更稳定的兼容模式。');
            setCurrentMode('vnc_fallback');
            setTakeoverMode(takeoverId, 'vnc_fallback');
            try {
              await loadVncFallback();
            } catch {
              setRenderState('error');
              setStatusText('云电脑连接失败，请重新打开浏览器。');
            }
            return;
          }
          setRenderState('error');
          setStatusText('云电脑打开超时，请重试。');
          return;
        }
        setRenderState('error');
        setStatusText('云电脑连接失败，请重新打开浏览器。');
      }
    };

    void mountBrowserUi();

    return () => {
      cancelled = true;
      void destroyBrowserUi();
    };
  }, [
    browserState.state,
    canvasCdpEndpoint,
    currentMode,
    destroyBrowserUi,
    loadVncFallback,
    setTakeoverMode,
    takeoverId,
    vncUrlPath,
  ]);

  useEffect(() => {
    if (!takeoverId) {
      return;
    }
    if (takeoverState === 'resolved') {
      removeRegistration(takeoverId);
      return;
    }
    if (takeoverState === 'expired') {
      removeRegistration(takeoverId);
      setRenderState('error');
      setStatusText('当前浏览器会话已失效，请回到左侧聊天卡片重新打开。');
      return;
    }
    if (takeoverState === 'cancelled') {
      removeRegistration(takeoverId);
      setRenderState('error');
      setStatusText('当前平台已跳过。');
      return;
    }
    if (takeoverState === 'resume_failed') {
      removeRegistration(takeoverId);
      setRenderState('error');
      setStatusText('暂未检测到当前平台操作已完成，请回到左侧聊天卡片重新打开或再次确认。');
    }
  }, [removeRegistration, takeoverId, takeoverState]);

  const handleSwitchToVnc = async () => {
    if (!takeoverId) {
      return;
    }
    setRenderState('opening');
    setStatusText(null);
    setTakeoverMode(takeoverId, 'vnc_fallback');
    try {
      await destroyBrowserUi();
      await loadVncFallback();
    } catch {
      setRenderState('error');
      setStatusText('云电脑连接失败，请重新打开浏览器。');
    }
  };

  const handleRetry = () => {
    setRenderState('opening');
    setStatusText(null);
    setReloadNonce((current) => current + 1);
  };

  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      if (isBenignTargetCloseError(event.reason)) {
        event.preventDefault();
      }
    };

    const handleWindowError = (event: ErrorEvent) => {
      if (isBenignTargetCloseError(event.error ?? event.message)) {
        event.preventDefault();
      }
    };

    const originalConsoleError = window.console.error.bind(window.console);
    window.console.error = (...args: unknown[]) => {
      if (args.some((value) => isBenignTargetCloseError(value))) {
        return;
      }
      originalConsoleError(...args);
    };

    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    window.addEventListener('error', handleWindowError);
    return () => {
      window.console.error = originalConsoleError;
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
      window.removeEventListener('error', handleWindowError);
    };
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col p-4" style={{ background: 'var(--bg-secondary)' }}>
      <div
        className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl"
        style={{
          background: 'var(--bg-primary)',
          border: '1px solid var(--border-subtle)',
          boxShadow: '0 18px 60px rgba(15, 23, 42, 0.12)',
        }}
      >
        <div
          className="flex shrink-0 items-center justify-between gap-3 px-4 py-3"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <div className="min-w-0">
            <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {browserState.actionHint || browserState.message}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
              <span
                className="rounded-full px-2 py-1"
                style={{
                  background: 'rgba(245, 158, 11, 0.14)',
                  color: 'var(--warning)',
                  border: '1px solid rgba(245, 158, 11, 0.2)',
                }}
              >
                {TAKEOVER_STATE_LABELS[takeoverState]}
              </span>
              {expiryText && (
                <span style={{ color: 'var(--text-tertiary)' }}>操作窗口至 {expiryText}</span>
              )}
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 bg-black">
          {currentMode === 'canvas_cdp' && renderState !== 'error' && (
            <div className="relative h-full">
              <div ref={canvasRootRef} className="h-full w-full overflow-hidden" />
              {renderState !== 'canvas_ready' && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/70">
                  <div className="flex flex-col items-center gap-3 text-center">
                    <div
                      className="h-9 w-9 animate-spin rounded-full border-2"
                      style={{
                        borderColor: 'rgba(99, 102, 241, 0.16)',
                        borderTopColor: 'var(--color-primary)',
                      }}
                    />
                    <div className="text-sm text-white/85">
                      正在进入云电脑...
                    </div>
                    {targetUrl && (
                      <div className="max-w-[420px] truncate text-xs text-white/60">
                        {targetUrl}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {renderState === 'opening' && currentMode !== 'canvas_cdp' && (
            <div className="flex h-full items-center justify-center bg-black">
              <div className="flex flex-col items-center gap-3 text-center">
                <div
                  className="h-9 w-9 animate-spin rounded-full border-2"
                  style={{
                    borderColor: 'rgba(99, 102, 241, 0.16)',
                    borderTopColor: 'var(--color-primary)',
                  }}
                />
                <div className="text-sm text-white/85">
                  正在进入云电脑...
                </div>
                {targetUrl && (
                  <div className="max-w-[420px] truncate text-xs text-white/60">
                    {targetUrl}
                  </div>
                )}
              </div>
            </div>
          )}

          {renderState === 'submitting' && (
            <div className="flex h-full items-center justify-center bg-black">
              <div className="flex flex-col items-center gap-3 text-center">
                <div
                  className="h-9 w-9 animate-spin rounded-full border-2"
                  style={{
                    borderColor: 'rgba(99, 102, 241, 0.16)',
                    borderTopColor: 'var(--color-primary)',
                  }}
                />
                <div className="text-sm text-white/85">正在确认当前平台操作...</div>
                {targetUrl && (
                  <div className="max-w-[420px] truncate text-xs text-white/60">
                    {targetUrl}
                  </div>
                )}
              </div>
            </div>
          )}

          {renderState === 'vnc_ready' && vncConfig?.url && (
            <iframe
              title={`${platformLabel} takeover`}
              src={vncConfig.url}
              className="h-full w-full bg-black"
              allow="fullscreen; clipboard-read; clipboard-write"
              allowFullScreen
            />
          )}

          {renderState === 'error' && (
            <div className="flex h-full flex-col items-center justify-center gap-3 bg-black px-6 text-center">
              <RiAlertLine className="h-8 w-8" style={{ color: 'var(--status-danger)' }} />
              <div className="text-sm" style={{ color: '#fff' }}>
                {statusText || '当前云电脑暂时不可用，请重新打开浏览器。'}
              </div>
              {targetUrl && (
                <div className="max-w-[420px] truncate text-xs text-white/60">
                  {targetUrl}
                </div>
              )}
            </div>
          )}
        </div>

        <div
          className="flex shrink-0 items-center justify-between gap-3 px-4 py-3"
          style={{ borderTop: '1px solid var(--border-subtle)' }}
        >
          <div className="min-w-0 text-xs" style={{ color: 'var(--text-secondary)' }}>
            {statusText
              || (targetUrl
                ? `请在当前云电脑中完成操作：${targetUrl}`
                : browserState.message)}
            <div className="mt-1" style={{ color: 'var(--text-tertiary)' }}>
              完成登录或验证后，请回到左侧聊天卡片点击“我已完成”继续。
            </div>
          </div>
          <div className="flex items-center gap-2">
            {currentMode === 'canvas_cdp' && vncUrlPath && (
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
                切换稳定模式
              </button>
            )}
            {renderState === 'error' && (
              <button
                type="button"
                onClick={handleRetry}
                className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition"
                style={{
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-secondary)',
                }}
              >
                <RiRefreshLine className="h-3.5 w-3.5" />
                重新连接
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

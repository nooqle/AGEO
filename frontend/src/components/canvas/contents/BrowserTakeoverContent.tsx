'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  RiAlertLine,
  RiExternalLinkLine,
  RiRefreshLine,
  RiShieldKeyholeLine,
} from '@remixicon/react';

import { api, getApiBaseUrl } from '@/services/api';
import { getStoredAccessToken } from '@/lib/auth-storage';
import { useAioTakeoverStore } from '@/stores/aioTakeoverStore';
import { useCanvasStore } from '@/stores/canvasStore';
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

interface BrowserTakeoverContentProps {
  content: BrowserCanvasContent;
}

export function BrowserTakeoverContent({
  content,
}: BrowserTakeoverContentProps) {
  const browserState = content.data.browserState;
  const takeover = browserState.takeover ?? null;
  const takeoverId = takeover?.takeoverId ?? null;
  const removeContent = useCanvasStore((state) => state.removeContent);
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
    takeoverRegistration?.mode ?? takeover?.mode ?? 'canvas_cdp',
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
  const resolvePath =
    takeoverRecord?.accessBundle.resolvePath ?? takeover?.resolvePath ?? null;
  const cancelPath =
    takeoverRecord?.accessBundle.cancelPath ?? takeover?.cancelPath ?? null;
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

  const closeTakeoverCanvas = useCallback(async () => {
    await destroyBrowserUi();
    removeContent(content.id);
  }, [content.id, destroyBrowserUi, removeContent]);

  const loadVncFallback = useCallback(async () => {
    if (!vncUrlPath) {
      setRenderState('error');
      setStatusText('VNC 不可用');
      return;
    }

    const vnc = await api.getAioTakeoverVncUrl(vncUrlPath);
    setVncConfig(vnc);
    setCurrentMode('vnc_fallback');
    if (takeoverId) {
      setTakeoverMode(takeoverId, 'vnc_fallback');
    }
    if (!vnc.upstreamVncAvailable) {
      setRenderState('error');
      setStatusText('VNC 不可用');
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
        const record = await api.getAioTakeover(takeoverId);
        if (cancelled) return;
        upsertTakeoverRecord(record);
      } catch (error) {
        if (cancelled) return;
        setRenderState('error');
        setStatusText(error instanceof Error ? error.message : '初始化失败');
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
    setCurrentMode(takeoverRegistration.mode);
  }, [takeoverId, takeoverRegistration?.mode]);

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
        const config = await api.getAioTakeoverCanvasConfig(canvasConfigPath);
        if (cancelled) return;
        setCanvasConfig(config);
        setHeartbeatInterval(takeoverId, config.heartbeatIntervalMs);
        setStatusText(null);
      } catch (error) {
        if (cancelled) return;
        setCanvasConfig(null);
        setRenderState('error');
        setStatusText(error instanceof Error ? error.message : 'Canvas 初始化失败');
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
      } catch (error) {
        if (cancelled) return;
        setRenderState('error');
        setStatusText(error instanceof Error ? error.message : 'VNC 初始化失败');
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
    takeoverId,
  ]);

  useEffect(() => {
    if (
      !takeoverId ||
      currentMode !== 'canvas_cdp' ||
      !canvasCdpEndpoint ||
      !canvasRootRef.current
    ) {
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

        browserUiRef.current = instance as BrowserUiController;
        setRenderState('canvas_ready');
        setStatusText(null);
      } catch (error) {
        if (cancelled) return;
        await destroyBrowserUi();
        setRenderState('error');
        setStatusText(error instanceof Error ? error.message : 'Canvas 失败');
      }
    };

    void mountBrowserUi();

    return () => {
      cancelled = true;
      void destroyBrowserUi();
    };
  }, [canvasCdpEndpoint, currentMode, destroyBrowserUi, takeoverId]);

  useEffect(() => {
    if (!takeoverId) {
      return;
    }
    if (takeoverState === 'resolved') {
      removeRegistration(takeoverId);
      void closeTakeoverCanvas();
      return;
    }
    if (takeoverState === 'expired') {
      removeRegistration(takeoverId);
      setRenderState('error');
      setStatusText('已过期');
      return;
    }
    if (takeoverState === 'cancelled') {
      removeRegistration(takeoverId);
      setRenderState('error');
      setStatusText('已取消');
      return;
    }
    if (takeoverState === 'resume_failed') {
      removeRegistration(takeoverId);
      setRenderState('error');
      setStatusText('恢复失败');
    }
  }, [closeTakeoverCanvas, removeRegistration, takeoverId, takeoverState]);

  const handleResolve = async () => {
    if (
      !takeoverId ||
      !takeoverRegistration?.frontendId ||
      !resolvePath ||
      renderState === 'submitting'
    ) {
      return;
    }
    setRenderState('submitting');
    setStatusText('恢复中');
    try {
      const next = await api.resolveAioTakeover(resolvePath, {
        frontendId: takeoverRegistration.frontendId,
        mode: currentMode,
        resumeGateResult: 'pass',
        clientObservation: 'user_claimed_done',
      });
      upsertTakeoverRecord(next);
      if (next.takeoverState === 'resolved') {
        removeRegistration(takeoverId);
        await closeTakeoverCanvas();
        return;
      }
      removeRegistration(takeoverId);
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
    if (
      !takeoverId ||
      !takeoverRegistration?.frontendId ||
      !cancelPath ||
      renderState === 'submitting'
    ) {
      return;
    }
    setRenderState('submitting');
    setStatusText('取消中');
    try {
      const next = await api.cancelAioTakeover(cancelPath, {
        frontendId: takeoverRegistration.frontendId,
        reason: 'user_cancelled',
      });
      upsertTakeoverRecord(next);
      removeRegistration(takeoverId);
      await closeTakeoverCanvas();
    } catch (error) {
      setRenderState('error');
      setStatusText(error instanceof Error ? error.message : '取消失败');
    }
  };

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
    } catch (error) {
      setRenderState('error');
      setStatusText(error instanceof Error ? error.message : '切换失败');
    }
  };

  const handleRetry = () => {
    setRenderState('opening');
    setStatusText(null);
    setReloadNonce((current) => current + 1);
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
              <span style={{ color: 'var(--text-tertiary)' }}>{expiryText}</span>
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
          {statusText ||
            (targetUrl
              ? `请在当前接管页签中完成操作：${targetUrl}`
              : browserState.message)}
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
              重试
            </button>
          )}
          {renderState === 'error' && currentMode !== 'vnc_fallback' && vncUrlPath && (
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
            disabled={
              renderState === 'opening' ||
              renderState === 'submitting' ||
              !takeoverRegistration?.frontendId
            }
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
          >
            <RiShieldKeyholeLine className="h-3.5 w-3.5" />
            完成
          </button>
          <button
            type="button"
            onClick={handleCancel}
            disabled={renderState === 'submitting' || !takeoverRegistration?.frontendId}
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

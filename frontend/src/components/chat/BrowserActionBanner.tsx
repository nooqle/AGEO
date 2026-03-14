'use client';

import { useState } from 'react';

import type { BrowserState } from '@/types/agent';
import { useConversationStore } from '@/stores/conversationStore';

const PLATFORM_LABELS: Record<BrowserState['platform'], string> = {
  doubao: '豆包',
  deepseek: 'DeepSeek',
  kimi: 'Kimi',
  hunyuan: '元宝',
};

interface BrowserActionBannerProps {
  browserState: BrowserState;
}

export function BrowserActionBanner({ browserState }: BrowserActionBannerProps) {
  const sendBrowserActionResolution = useConversationStore((state) => state.wsBrowserActionResolution);
  const [localSubmitting, setLocalSubmitting] = useState<'completed' | 'skip' | null>(null);

  const platformLabel = PLATFORM_LABELS[browserState.platform] || browserState.platform;
  const title = browserState.actionType === 'verify'
    ? `${platformLabel} 遇到了安全验证，需要你协助处理`
    : browserState.actionType === 'login'
    ? `${platformLabel} 需要登录后才能继续抓取`
    : browserState.actionType === 'modal'
    ? `${platformLabel} 页面有弹窗阻碍，需要你协助确认`
    : `${platformLabel} 需要你在浏览器窗口中协助操作`;

  const detail = browserState.actionHint || browserState.message;
  const canConfirm = Boolean(browserState.requestId && sendBrowserActionResolution);

  const handleResolve = (resolution: 'completed' | 'skip') => {
    if (!browserState.requestId || !sendBrowserActionResolution || localSubmitting) {
      return;
    }
    setLocalSubmitting(resolution);
    sendBrowserActionResolution(browserState.requestId, resolution);
  };

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="px-4 py-3 border-b"
      style={{
        background: 'rgba(245, 158, 11, 0.10)',
        borderColor: 'rgba(245, 158, 11, 0.22)',
      }}
    >
      <div className="mx-auto max-w-3xl flex items-start gap-3">
        <div
          className="mt-1 h-2.5 w-2.5 rounded-full animate-pulse"
          style={{ background: 'var(--warning)' }}
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {title}
          </p>
          <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
            {detail}
          </p>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            请先在浏览器窗口中完成操作，再点击下方按钮，我会继续接管当前任务。
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => handleResolve('completed')}
              disabled={!canConfirm || localSubmitting !== null}
              className="rounded-full px-3 py-1.5 text-xs font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'var(--color-primary)',
                color: '#fff',
              }}
            >
              {localSubmitting === 'completed' ? '已提交，正在恢复...' : '我已完成'}
            </button>
            <button
              type="button"
              onClick={() => handleResolve('skip')}
              disabled={!canConfirm || localSubmitting !== null}
              className="rounded-full px-3 py-1.5 text-xs font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-secondary)',
              }}
            >
              {localSubmitting === 'skip' ? '已提交跳过...' : '暂时跳过该平台'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

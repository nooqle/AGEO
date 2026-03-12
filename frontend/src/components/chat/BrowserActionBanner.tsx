'use client';

import type { BrowserState } from '@/types/agent';

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
  const platformLabel = PLATFORM_LABELS[browserState.platform] || browserState.platform;
  const title = browserState.actionType === 'verify'
    ? `${platformLabel} \u89e6\u53d1\u5b89\u5168\u9a8c\u8bc1\uff0c\u7b49\u5f85\u4f60\u5904\u7406`
    : browserState.actionType === 'login'
    ? `${platformLabel} \u9700\u8981\u767b\u5f55`
    : browserState.actionType === 'modal'
    ? `${platformLabel} \u9875\u9762\u51fa\u73b0\u5f39\u6846\uff0c\u7b49\u5f85\u4f60\u786e\u8ba4`
    : `${platformLabel} \u9700\u8981\u4f60\u5728\u6d4f\u89c8\u5668\u7a97\u53e3\u4e2d\u64cd\u4f5c`;
  const detail = browserState.actionHint || browserState.message;

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
            系统已尝试将浏览器切到前台。如果没看到窗口，请检查任务栏中的 Chromium / Patchright 窗口。
          </p>
        </div>
      </div>
    </div>
  );
}

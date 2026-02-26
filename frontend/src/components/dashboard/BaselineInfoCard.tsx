'use client';

import { useCallback, useState } from 'react';
import { RiDatabase2Line, RiRefreshLine, RiQuestionLine } from '@remixicon/react';
import type { BaselineSummary } from '@/types/monitoring';

interface BaselineInfoCardProps {
  hasBaseline: boolean;
  baselineSummary: BaselineSummary | null;
  totalRuns: number;
  onClearBaseline: () => Promise<void>;
}

export function BaselineInfoCard({
  hasBaseline,
  baselineSummary,
  totalRuns,
  onClearBaseline,
}: BaselineInfoCardProps) {
  const [isClearing, setIsClearing] = useState(false);

  const handleClear = useCallback(async () => {
    setIsClearing(true);
    try {
      await onClearBaseline();
    } finally {
      setIsClearing(false);
    }
  }, [onClearBaseline]);

  if (!hasBaseline) {
    // No baseline yet — show pending state
    return (
      <div
        className="rounded-xl p-4 flex items-start gap-3"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div
          className="mt-0.5 p-1.5 rounded-lg"
          style={{ background: 'var(--bg-secondary)' }}
        >
          <RiQuestionLine className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {totalRuns === 0 ? '等待建立监测基线' : '基线待重建'}
          </p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
            {totalRuns === 0
              ? '首次运行将执行完整分析并保存问题基线，后续运行仅重新抓取答案和更新报告。'
              : '基线已重置，下次运行将重新执行完整分析并保存新的问题基线。'}
          </p>
        </div>
      </div>
    );
  }

  // Has baseline — show info
  const savedAt = baselineSummary?.saved_at
    ? new Date(baselineSummary.saved_at).toLocaleDateString('zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null;

  return (
    <div
      className="rounded-xl p-4 flex items-start gap-3"
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <div
        className="mt-0.5 p-1.5 rounded-lg"
        style={{ background: 'color-mix(in srgb, var(--color-primary) 12%, transparent)' }}
      >
        <RiDatabase2Line className="w-4 h-4" style={{ color: 'var(--color-primary)' }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            监测基线已建立
          </p>
          <button
            onClick={handleClear}
            disabled={isClearing}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors"
            style={{
              color: 'var(--text-secondary)',
              background: 'transparent',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--bg-secondary)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
            }}
            title="重置基线后，下次运行将重新执行完整分析"
          >
            <RiRefreshLine className={`w-3.5 h-3.5 ${isClearing ? 'animate-spin' : ''}`} />
            {isClearing ? '重置中...' : '重置基线'}
          </button>
        </div>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {baselineSummary?.question_count ?? 0} 组问题
          </span>
          {savedAt && (
            <>
              <span className="text-xs" style={{ color: 'var(--border-subtle)' }}>|</span>
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                建立于 {savedAt}
              </span>
            </>
          )}
        </div>
        <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
          定时运行使用相同问题重新抓取答案并更新分析报告，确保趋势数据可对比。
        </p>
      </div>
    </div>
  );
}

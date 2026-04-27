import { RiChatQuoteLine } from '@remixicon/react';
import type { DashboardMentionBoard } from '@/types/dashboard';
import { DashboardBoardTrendStrip } from './DashboardBoardTrendStrip';

interface MentionBoardProps {
  data: DashboardMentionBoard;
  onClick: () => void;
}

const sentimentText = {
  positive: '正向',
  neutral: '中性',
  negative: '负向',
} as const;

export function MentionBoard({ data, onClick }: MentionBoardProps) {
  const mentionRate = data.mention_rate != null ? `${(data.mention_rate * 100).toFixed(1)}%` : '--';
  const mentionedQuestionCount = new Set(data.report.brand_mentions.map((item) => item.scenario_id || item.scenario_label).filter(Boolean)).size;

  return (
    <button
      type="button"
      onClick={onClick}
      className="dashboard-board dashboard-board--analysis group relative h-full overflow-hidden rounded-[18px] p-6 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--border-hover)]"
    >
      <div className="relative flex h-full flex-col">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-[14px]" style={{ background: 'color-mix(in srgb, var(--color-primary) 15%, var(--bg-elevated) 85%)' }}>
            <RiChatQuoteLine className="h-5 w-5" style={{ color: 'var(--color-primary)' }} />
          </div>
          <div className="min-w-0">
            <div className="text-[20px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">提及率</div>
            <div className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">看品牌在多少个问题里进入答案，以及提及时的语气倾向。</div>
          </div>
        </div>

        <div className="mt-6 flex items-end gap-3">
          <div className="text-[46px] font-semibold leading-none tracking-[-0.06em] text-[var(--text-primary)]">{mentionRate}</div>
          <div className="pb-1 text-[13px] leading-6 text-[var(--text-secondary)]">涉及问题 {mentionedQuestionCount} 个</div>
        </div>

        <DashboardBoardTrendStrip trend={data.trend} accentColor="var(--color-primary)" />

        <div className="mt-5 grid grid-cols-3 gap-3">
          {(['positive', 'neutral', 'negative'] as const).map((key) => (
            <div
              key={key}
              className="rounded-[18px] border px-3 py-3"
              style={{
                borderColor: 'var(--border-subtle)',
                background:
                  key === 'positive'
                    ? 'color-mix(in srgb, var(--bg-tertiary) 78%, #e9f6ee 22%)'
                    : key === 'neutral'
                      ? 'color-mix(in srgb, var(--bg-tertiary) 84%, #f6f1e8 16%)'
                      : 'color-mix(in srgb, var(--bg-tertiary) 80%, #fbefef 20%)',
              }}
            >
              <div className="text-[11px] tracking-[0.08em] text-[var(--text-tertiary)]">{sentimentText[key]}</div>
              <div className="mt-1 text-[20px] font-semibold text-[var(--text-primary)]">{data.sentiment_summary[key]}</div>
            </div>
          ))}
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-[var(--border-subtle)] pt-4 text-[13px] text-[var(--text-secondary)]">
          <span>查看被提及的问题、平台分布和语气差异</span>
          <span className="font-medium text-[var(--text-primary)]">展开分析</span>
        </div>
      </div>
    </button>
  );
}

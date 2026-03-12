import { cn } from '@/lib/cn';
import type { RiskSectionData } from '@/types/canvas';

interface RiskSectionProps {
  data?: RiskSectionData | null;
}

const severityLabel: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
};

const riskTypeLabel: Record<string, string> = {
  missing_presence: '品牌缺席',
  competitor_substitution: '竞品替代',
  no_official_citation: '官网未被引用',
  weak_presence: '品牌存在感弱',
};

export function RiskSection({ data }: RiskSectionProps) {
  const items = data?.items ?? [];

  return (
    <section className="rounded-[20px] border bg-[var(--bg-tertiary)] p-6" style={{ background: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)' }}>
      <div className="space-y-1.5">
        <h2 className="text-[18px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">
          {data?.title || '缺口与风险'}
        </h2>
        <p className="max-w-3xl text-[13px] leading-7 text-[var(--text-secondary)]">
          {data?.description || '这些缺口正在影响品牌被提及和被引用。'}
        </p>
      </div>

      {data?.summary && (
        <div className="mt-5 rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4 text-[13px] leading-7 text-[var(--text-secondary)]">
          {data.summary}
        </div>
      )}

      {items.length === 0 ? (
        <div className="mt-5 rounded-[18px] border border-dashed border-[var(--border-subtle)] px-5 py-8 text-[13px] text-[var(--text-tertiary)]">
          当前未识别到明确风险，或风险数据尚未返回。
        </div>
      ) : (
        <div className="mt-5 space-y-3.5">
          {items.map((item, index) => (
            <article key={item.risk_id || `${item.scenario_label || 'risk'}-${index}`} className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4">
              <div className="flex flex-wrap items-center gap-2.5">
                {item.severity && (
                  <span
                    className={cn(
                      'rounded-full px-2.5 py-1 text-[11px] font-medium',
                      item.severity === 'high' && 'bg-red-500/10 text-red-400',
                      item.severity === 'medium' && 'bg-amber-500/10 text-amber-400',
                      item.severity === 'low' && 'bg-blue-500/10 text-blue-400'
                    )}
                  >
                    {severityLabel[item.severity] || item.severity}
                  </span>
                )}
                {item.risk_type && (
                  <span className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
                    {riskTypeLabel[item.risk_type] || item.risk_type}
                  </span>
                )}
                {item.scenario_label && <span className="text-[14px] font-medium text-[var(--text-primary)]">{item.scenario_label}</span>}
              </div>

              {item.reason && <p className="mt-4 text-[14px] font-medium leading-7 text-[var(--text-primary)]">{item.reason}</p>}
              {item.impact_summary && <p className="mt-2 text-[13px] leading-7 text-[var(--text-secondary)]">{item.impact_summary}</p>}
              {item.evidence && (
                <div className="mt-4 rounded-[16px] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] leading-7 text-[var(--text-secondary)]">
                  <span className="font-medium text-[var(--text-primary)]">判断依据：</span>
                  {item.evidence}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

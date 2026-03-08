import type { CSSProperties } from 'react';
import type { InsightSectionData, InsightSectionItem } from '@/types/canvas';

interface InsightSectionProps {
  data?: InsightSectionData | null;
}

const SECTION_TONES: Record<'good' | 'bad', { label: string; style: CSSProperties }> = {
  good: {
    label: '现在做得好的是什么',
    style: {
      color: 'color-mix(in srgb, var(--text-primary) 58%, #215846 42%)',
      backgroundColor: 'color-mix(in srgb, var(--bg-elevated) 72%, #d6eadf 28%)',
      borderColor: 'color-mix(in srgb, var(--border-subtle) 32%, #6ea68e 68%)',
      boxShadow: 'inset 0 1px 0 color-mix(in srgb, #ffffff 82%, transparent)',
    },
  },
  bad: {
    label: '现在做得不好的是什么',
    style: {
      color: 'color-mix(in srgb, var(--text-primary) 58%, #84501e 42%)',
      backgroundColor: 'color-mix(in srgb, var(--bg-elevated) 72%, #efdec8 28%)',
      borderColor: 'color-mix(in srgb, var(--border-subtle) 32%, #bd945f 68%)',
      boxShadow: 'inset 0 1px 0 color-mix(in srgb, #ffffff 82%, transparent)',
    },
  },
};

function renderItem(item: InsightSectionItem, index: number, tone: 'good' | 'bad') {
  return (
    <article
      key={`${item.title}-${item.scenario || index}`}
      className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4"
    >
      <h3 className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">{item.title}</h3>
      {item.scenario && (
        <div className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">关联场景：{item.scenario}</div>
      )}
      {item.evidence && (
        <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">{item.evidence}</p>
      )}
      {(item.platforms?.length || item.improvement_hint) && (
        <div className="mt-4 flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
          {item.platforms?.map((platform) => (
            <span
              key={`${item.title}-${platform}`}
              className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 font-medium"
            >
              {platform}
            </span>
          ))}
          {tone === 'bad' && item.improvement_hint && (
            <span className="rounded-full bg-[var(--bg-secondary)] px-2.5 py-1 font-medium">改进提示：{item.improvement_hint}</span>
          )}
        </div>
      )}
    </article>
  );
}

function renderColumnHeader(tone: 'good' | 'bad') {
  const config = SECTION_TONES[tone];
  return (
    <div
      className="inline-flex items-center rounded-full border px-4 py-2 text-[15px] font-semibold tracking-[-0.01em]"
      style={config.style}
    >
      {config.label}
    </div>
  );
}

export function InsightSection({ data }: InsightSectionProps) {
  const strengths = data?.strengths ?? [];
  const weaknesses = data?.weaknesses ?? [];

  return (
    <section className="space-y-5">
      <div className="space-y-1.5">
        <h2 className="text-xl font-semibold tracking-[-0.01em] text-[var(--text-primary)]">
          {data?.title || '洞察'}
        </h2>
        <p className="max-w-4xl text-sm leading-6 text-[var(--text-secondary)]">
          {data?.summary || data?.description || '先看品牌当前做得好的地方，以及还需要补强的地方。'}
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="space-y-4">
          {renderColumnHeader('good')}
          {strengths.length === 0 ? (
            <div className="rounded-[24px] border border-dashed border-[var(--border-subtle)] px-5 py-10 text-sm text-[var(--text-tertiary)]">
              暂未识别出明确优势。
            </div>
          ) : (
            strengths.map((item, index) => renderItem(item, index, 'good'))
          )}
        </div>

        <div className="space-y-4">
          {renderColumnHeader('bad')}
          {weaknesses.length === 0 ? (
            <div className="rounded-[24px] border border-dashed border-[var(--border-subtle)] px-5 py-10 text-sm text-[var(--text-tertiary)]">
              暂未识别出明确短板。
            </div>
          ) : (
            weaknesses.map((item, index) => renderItem(item, index, 'bad'))
          )}
        </div>
      </div>
    </section>
  );
}

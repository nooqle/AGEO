import type { CSSProperties } from 'react';
import type { InsightSectionData, InsightSectionItem } from '@/types/canvas';
import { getSourceLabel } from '@/lib/sourceLabel';
import { getPlatformDisplayName } from '@/lib/platformLabel';

interface InsightSectionProps {
  data?: InsightSectionData | null;
}

const SECTION_TONES: Record<'good' | 'bad', { label: string; style: CSSProperties }> = {
  good: {
    label: '当前优势',
    style: {
      color: '#446d58',
      backgroundColor: 'color-mix(in srgb, #dceadf 24%, var(--bg-elevated) 76%)',
      borderColor: 'color-mix(in srgb, #7cad92 54%, var(--border-subtle) 46%)',
    },
  },
  bad: {
    label: '当前补强',
    style: {
      color: '#7e5c36',
      backgroundColor: 'color-mix(in srgb, #efe1cc 24%, var(--bg-elevated) 76%)',
      borderColor: 'color-mix(in srgb, #c59b67 54%, var(--border-subtle) 46%)',
    },
  },
};

function renderItem(item: InsightSectionItem, index: number) {
  return (
    <article key={`${item.title}-${item.scenario || index}`} className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4">
      <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">{item.title}</h3>
      {item.scenario && <div className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">关联场景：{item.scenario}</div>}
      {item.evidence && <p className="mt-4 text-[13px] leading-7 text-[var(--text-secondary)]">{item.evidence}</p>}

      {(item.platforms?.length || item.sentiment || item.official_citation_present !== undefined) && (
        <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
          {item.platforms?.map((platform) => (
            <span key={`${item.title}-${getPlatformDisplayName(platform)}`} className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 font-medium">
              {getPlatformDisplayName(platform)}
            </span>
          ))}
          {item.sentiment && (
            <span className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 font-medium">
              情绪：{item.sentiment}
            </span>
          )}
          {item.official_citation_present !== undefined && (
            <span className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 font-medium">
              {item.official_citation_present ? '已含官网引用' : '暂无官网引用'}
            </span>
          )}
        </div>
      )}

      {(item.citation_domains?.length ?? 0) > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {item.citation_domains?.slice(0, 4).map((domain) => (
            <span key={`${item.title}-${domain}`} className="rounded-full bg-[var(--bg-secondary)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              {getSourceLabel(domain, false) || domain}
            </span>
          ))}
        </div>
      )}

      {item.improvement_hint && (
        <div className="mt-4 rounded-[16px] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] leading-7 text-[var(--text-secondary)]">
          <span className="font-medium text-[var(--text-primary)]">下一步建议：</span>
          {item.improvement_hint}
        </div>
      )}
    </article>
  );
}

function renderColumnHeader(tone: 'good' | 'bad') {
  const config = SECTION_TONES[tone];
  return (
    <div className="inline-flex items-center rounded-full border px-4 py-2 text-[13px] font-semibold tracking-[-0.01em]" style={config.style}>
      {config.label}
    </div>
  );
}

export function InsightSection({ data }: InsightSectionProps) {
  const strengths = data?.strengths ?? [];
  const weaknesses = data?.weaknesses ?? [];

  return (
    <section className="rounded-[20px] border bg-[var(--bg-tertiary)] p-6" style={{ background: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)' }}>
      <div className="space-y-1.5">
        <h2 className="text-[18px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">
          {data?.title || '当前优势与补强'}
        </h2>
        <p className="max-w-4xl text-[13px] leading-7 text-[var(--text-secondary)]">
          {data?.summary || data?.description || '把品牌已经站住的问题和仍需补强的问题分开看，方便直接转成动作。'}
        </p>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <div className="space-y-3.5">
          {renderColumnHeader('good')}
          {strengths.length === 0 ? (
            <div className="rounded-[18px] border border-dashed border-[var(--border-subtle)] px-5 py-8 text-[13px] text-[var(--text-tertiary)]">
              暂未识别出明确优势。
            </div>
          ) : (
            strengths.map((item, index) => renderItem(item, index))
          )}
        </div>

        <div className="space-y-3.5">
          {renderColumnHeader('bad')}
          {weaknesses.length === 0 ? (
            <div className="rounded-[18px] border border-dashed border-[var(--border-subtle)] px-5 py-8 text-[13px] text-[var(--text-tertiary)]">
              暂未识别出明确补强问题。
            </div>
          ) : (
            weaknesses.map((item, index) => renderItem(item, index))
          )}
        </div>
      </div>
    </section>
  );
}

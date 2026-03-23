import { cn } from '@/lib/cn';
import type { ScenarioCoverageData, ScenarioCoverageItem, ScenarioCoverageLensItem } from '@/types/canvas';
import { ReportSection } from './ReportScaffold';

interface ScenarioCoverageSectionProps {
  data?: ScenarioCoverageData | null;
}

const SECTION_META = {
  effective: {
    title: '已覆盖场景',
    description: '品牌已经进入回答，说明这些问题里已经有基础存在感。',
    tone: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20',
    itemTone: 'bg-emerald-500/10 text-emerald-700',
  },
  missing: {
    title: '待进入场景',
    description: '品牌还没真正进入回答，但竞品或行业内容已经在场的场景。',
    tone: 'bg-amber-500/10 text-amber-700 border-amber-500/20',
    itemTone: 'bg-amber-500/10 text-amber-700',
  },
  risk: {
    title: '高风险场景',
    description: '满足高风险判定条件的场景。',
    tone: 'bg-rose-500/10 text-rose-700 border-rose-500/20',
    itemTone: 'bg-rose-500/10 text-rose-700',
  },
  } as const;

function statusLabel(item: ScenarioCoverageItem) {
  if (item.risk_reason_type === 'competitor_crowding' || item.battle_status === 'competitor_crowding') {
    return '竞品密集正向';
  }
  if (item.risk_reason_type === 'negative_brand' || item.battle_status === 'negative_brand') {
    return '品牌负向提及';
  }
  if (item.battle_status === 'missing') return '待进入';
  if (item.battle_status === 'contested') return '激烈争夺';
  if (item.battle_status === 'defend') return '需要补强';
  return '已进入回答';
}

function lensTone(item: ScenarioCoverageLensItem) {
  if (item.brandCount > item.competitorCount) {
    return {
      card: 'rgba(16,185,129,0.10)',
      border: 'rgba(16,185,129,0.18)',
      text: '#047857',
      subText: '#065f46',
    };
  }
  if (item.competitorCount > item.brandCount) {
    return {
      card: 'rgba(244,63,94,0.10)',
      border: 'rgba(244,63,94,0.18)',
      text: '#be123c',
      subText: '#9f1239',
    };
  }
  return {
    card: 'rgba(148,163,184,0.10)',
    border: 'rgba(148,163,184,0.18)',
    text: '#475569',
    subText: '#64748b',
  };
}

function renderSemanticTags(item: ScenarioCoverageItem) {
  const tags = [
    ...(item.semantic_tags?.audiences ?? []),
    ...(item.semantic_tags?.prices ?? []),
    ...(item.semantic_tags?.features ?? []),
    ...(item.semantic_tags?.usages ?? []),
  ];

  return tags.slice(0, 6);
}

function LensChips({ items }: { items?: ScenarioCoverageLensItem[] }) {
  if (!items?.length) {
    return <div className="text-[13px] text-[var(--text-tertiary)]">当前没有足够明确的共性标签。</div>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-[18px] border px-4 py-3"
          style={{
            background: lensTone(item).card,
            borderColor: lensTone(item).border,
          }}
        >
          <div className="text-[17px] font-semibold" style={{ color: lensTone(item).text }}>{item.label}</div>
          <div className="mt-1 text-[13px]" style={{ color: lensTone(item).subText }}>
            我方 {item.brandCount} · 竞品 {item.competitorCount}
          </div>
        </div>
      ))}
    </div>
  );
}

function ScenarioRow({
  item,
  tone,
}: {
  item: ScenarioCoverageItem;
  tone: string;
}) {
  const tags = renderSemanticTags(item);
  const evidenceText = item.evidence;
  return (
    <article className="rounded-[20px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[16px] font-semibold leading-7 text-[var(--text-primary)]">{item.scenario_label}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className={cn('rounded-full px-2.5 py-1 text-[11px] font-semibold', tone)}>
              {statusLabel(item)}
            </span>
            {(item.competitors_present?.length ?? 0) > 0 ? (
              <span className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
                竞品：{item.competitors_present?.slice(0, 2).join('、')}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      {tags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span key={`${item.scenario_label}-${tag}`} className="rounded-full bg-[var(--bg-secondary)] px-3 py-1.5 text-[14px] font-medium text-[var(--text-secondary)]">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {item.fact_basis && item.fact_basis.length > 0 ? (
        <div className="mt-3 space-y-2">
          <div className="text-[12px] font-semibold tracking-[0.08em] text-[var(--text-tertiary)]">事实依据</div>
          {item.fact_basis.slice(0, 2).map((fact) => (
            <div key={`${item.scenario_label}-${fact}`} className="rounded-[14px] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-6 text-[var(--text-secondary)]">
              {fact}
            </div>
          ))}
        </div>
      ) : null}

      {evidenceText ? (
        <p className="mt-3 text-[13px] leading-7 text-[var(--text-secondary)]">{evidenceText}</p>
      ) : null}
    </article>
  );
}

function SectionBlock({
  title,
  items,
  tone,
}: {
  title: string;
  items: ScenarioCoverageItem[];
  tone: string;
}) {
  return (
    <div className="rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[20px] font-semibold text-[var(--text-primary)]">{title}</div>
        </div>
        <span className={cn('rounded-full border px-3 py-1.5 text-[12px] font-semibold', tone)}>
          {items.length} 个问题
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {items.length > 0 ? (
          items.map((item) => <ScenarioRow key={item.scenario_id || item.scenario_label} item={item} tone={tone} />)
        ) : (
          <div className="rounded-[18px] border border-dashed border-[var(--border-subtle)] px-4 py-8 text-[13px] text-[var(--text-tertiary)]">
            当前没有可展示的问题样本。
          </div>
        )}
      </div>
    </div>
  );
}

export function ScenarioCoverageSection({ data }: ScenarioCoverageSectionProps) {
  const items = (data?.items ?? []).filter((item) => item.brand_present && item.battle_status !== 'missing');
  const missingItems = (data?.missing_items ?? []).filter((item) => !item.brand_present || item.battle_status === 'missing');
  const riskItems = (data?.risk_items ?? []).filter((item) => item.battle_status !== 'missing');
  const lenses = data?.semantic_lenses ?? [];

  return (
    <ReportSection title={data?.title || '场景覆盖'}>
      <div className="rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-5">
        <div className="space-y-4">
          {lenses.map((lens) => (
            <div key={lens.key} className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-4 py-4">
              <div className="text-[18px] font-semibold text-[var(--text-primary)]">{lens.label}</div>
              <div className="mt-3">
                <LensChips items={lens.items} />
              </div>
            </div>
          ))}
          {lenses.length === 0 ? (
            <div className="rounded-[18px] border border-dashed border-[var(--border-subtle)] px-4 py-8 text-[13px] text-[var(--text-tertiary)]">
              当前还没有足够的场景标签可供归纳。
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-6 space-y-5">
        <SectionBlock
          title={SECTION_META.effective.title}
          items={items}
          tone={SECTION_META.effective.tone}
        />
        <SectionBlock
          title={SECTION_META.missing.title}
          items={missingItems}
          tone={SECTION_META.missing.tone}
        />
        <SectionBlock
          title={SECTION_META.risk.title}
          items={riskItems}
          tone={SECTION_META.risk.tone}
        />
      </div>
    </ReportSection>
  );
}

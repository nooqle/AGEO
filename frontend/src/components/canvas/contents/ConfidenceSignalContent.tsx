'use client';

import { type ReactNode, useEffect, useRef } from 'react';
import { RiArrowRightUpLine, RiShieldCheckLine } from '@remixicon/react';
import { Card } from '@/components/ui/card';
import { ReportHero, ReportMetricCard, ReportPage, ReportSection } from './ReportScaffold';
import type {
  ConfidenceAuditActionStep,
  ConfidenceAuditPoint,
  ConfidenceEntityClassification,
  ConfidenceQuadrant,
  ConfidenceQuadrantOverview,
  ConfidenceSignalDimensionScore,
  ConfidenceSignalItem,
  ReportCanvasContent,
} from '@/types/canvas';

interface ConfidenceSignalContentProps {
  content: ReportCanvasContent;
  printMode?: boolean;
}

type MatrixPoint = {
  item_id: string;
  title: string;
  domain?: string;
  url?: string;
  entity: ConfidenceEntityClassification;
  entityLabel: string;
  quadrant: ConfidenceQuadrant;
  quadrantLabel: string;
  score: number;
  frequency: number;
  count: number;
  scoreBandLabel: string;
  sampleTitles: string[];
};

type RawMatrixPoint = Omit<
  MatrixPoint,
  'count' | 'scoreBandLabel' | 'sampleTitles'
>;

const ENTITY_META: Record<
  ConfidenceEntityClassification,
  { label: string; fill: string; softBg: string; softText: string }
> = {
  brand: {
    label: '我方阵营',
    fill: '#3B82F6',
    softBg: 'rgba(59,130,246,0.12)',
    softText: '#2563EB',
  },
  competitor: {
    label: '竞方阵营',
    fill: '#F43F5E',
    softBg: 'rgba(244,63,94,0.12)',
    softText: '#E11D48',
  },
  general_knowledge: {
    label: '共业阵营',
    fill: '#64748B',
    softBg: 'rgba(100,116,139,0.12)',
    softText: '#475569',
  },
};

const QUADRANT_META: Record<
  ConfidenceQuadrant,
  {
    label: string;
    plainLabel: string;
    feature: string;
    border: string;
    glow: string;
    area: string;
  }
> = {
  q1_anchor: {
    label: '定海神针',
    plainLabel: '第一象限',
    feature: '高频 + 高分',
    border: 'rgba(22,163,74,0.25)',
    glow: 'rgba(22,163,74,0.10)',
    area: 'rgba(22,163,74,0.08)',
  },
  q2_false_prosperity: {
    label: '虚假繁荣',
    plainLabel: '第二象限',
    feature: '高频 + 低分',
    border: 'rgba(245,158,11,0.28)',
    glow: 'rgba(245,158,11,0.10)',
    area: 'rgba(245,158,11,0.09)',
  },
  q3_noise: {
    label: '沉寂噪音',
    plainLabel: '第三象限',
    feature: '低频 + 低分',
    border: 'rgba(148,163,184,0.28)',
    glow: 'rgba(148,163,184,0.10)',
    area: 'rgba(148,163,184,0.08)',
  },
  q4_sleeping_asset: {
    label: '高潜伏藏',
    plainLabel: '第四象限',
    feature: '低频 + 高分',
    border: 'rgba(14,165,233,0.28)',
    glow: 'rgba(14,165,233,0.10)',
    area: 'rgba(14,165,233,0.08)',
  },
};

const QUADRANT_ORDER: ConfidenceQuadrant[] = [
  'q1_anchor',
  'q2_false_prosperity',
  'q3_noise',
  'q4_sleeping_asset',
];

function formatScore(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return value.toFixed(1);
}

function formatUpdatedAt(value?: string) {
  if (!value) return '刚刚更新';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function MetaPill({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'accent';
}) {
  return (
    <span
      className="inline-flex items-center rounded-full px-3 py-1.5 text-[12px]"
      style={{
        background:
          tone === 'accent'
            ? 'color-mix(in srgb, var(--color-primary) 12%, var(--bg-secondary))'
            : 'var(--bg-secondary)',
        color: tone === 'accent' ? 'var(--brand-text)' : 'var(--text-secondary)',
        border: `1px solid ${
          tone === 'accent'
            ? 'color-mix(in srgb, var(--color-primary) 22%, transparent)'
            : 'var(--border-subtle)'
        }`,
      }}
    >
      {children}
    </span>
  );
}

function MatrixSummaryStat({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div
      className="min-w-[132px] rounded-[18px] px-4 py-3"
      style={{
        background: 'color-mix(in srgb, var(--bg-elevated) 88%, transparent)',
        border: '1px solid color-mix(in srgb, var(--border-subtle) 72%, rgba(255,255,255,0.08) 28%)',
      }}
    >
      <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-[20px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">{value}</div>
    </div>
  );
}

function getEntityMeta(entity?: ConfidenceEntityClassification) {
  return ENTITY_META[entity ?? 'general_knowledge'];
}

function getQuadrantMeta(quadrant?: ConfidenceQuadrant) {
  return QUADRANT_META[quadrant ?? 'q3_noise'];
}

function toMatrixPoint(item: ConfidenceSignalItem): RawMatrixPoint | null {
  const score = item.aice_score ?? item.overall_score;
  const frequency = item.frequency ?? item.occurrences;
  if (typeof score !== 'number' || typeof frequency !== 'number') return null;
  const entity = item.entity_classification ?? 'general_knowledge';
  const quadrant = item.quadrant ?? 'q3_noise';
  return {
    item_id: item.item_id,
    title: item.label,
    domain: item.domain,
    url: item.url,
    entity,
    entityLabel: item.entity_label || ENTITY_META[entity].label,
    quadrant,
    quadrantLabel: item.quadrant_label || QUADRANT_META[quadrant].label,
    score,
    frequency,
  };
}

const SCORE_BUCKET_SIZE = 5;

const MATRIX_LAYOUT: ConfidenceQuadrant[][] = [
  ['q4_sleeping_asset', 'q1_anchor'],
  ['q3_noise', 'q2_false_prosperity'],
];

function buildScoreBucket(score: number, threshold: number) {
  const isHighScore = score >= threshold;
  const zoneStart = isHighScore ? threshold : 0;
  const zoneEnd = isHighScore ? 100 : threshold;
  const relative = Math.max(0, score - zoneStart);
  const bucketIndex = Math.floor(relative / SCORE_BUCKET_SIZE);
  const start = Math.min(zoneEnd, zoneStart + bucketIndex * SCORE_BUCKET_SIZE);
  const end = Math.min(zoneEnd, start + SCORE_BUCKET_SIZE);
  const center = start + Math.max(1, end - start) / 2;
  return {
    key: `${isHighScore ? 'high' : 'low'}::${bucketIndex}`,
    start,
    end,
    center,
    label: `${formatScore(start)}-${formatScore(end)}`,
  };
}

function buildMatrixPoints(
  points: RawMatrixPoint[],
  aiceThreshold: number,
): MatrixPoint[] {
  const grouped = new Map<string, { bucket: ReturnType<typeof buildScoreBucket>; items: RawMatrixPoint[] }>();

  points.forEach((point) => {
    const scoreBucket = buildScoreBucket(point.score, aiceThreshold);
    const key = `${point.entity}::${point.frequency}::${scoreBucket.key}`;
    const entry = grouped.get(key);
    if (entry) {
      entry.items.push(point);
      return;
    }
    grouped.set(key, { bucket: scoreBucket, items: [point] });
  });

  return [...grouped.values()]
    .map(({ bucket, items }) => {
      const sample = items[0];
      const averageScore = items.reduce((sum, item) => sum + item.score, 0) / items.length;
      return {
        ...sample,
        title: items.length === 1 ? sample.title : `${sample.entityLabel} · ${items.length} 个来源`,
        url: items.length === 1 ? sample.url : undefined,
        domain: items.length === 1 ? sample.domain : undefined,
        score: averageScore,
        count: items.length,
        scoreBandLabel: bucket.label,
        sampleTitles: items.slice(0, 3).map((item) => item.title),
      };
    })
    .sort((left, right) => {
      if (left.frequency !== right.frequency) return right.frequency - left.frequency;
      if (left.score !== right.score) return right.score - left.score;
      if (left.count !== right.count) return right.count - left.count;
      return left.entity.localeCompare(right.entity);
    });
}

function buildFallbackQuadrantOverview(items: ConfidenceSignalItem[]): ConfidenceQuadrantOverview[] {
  return QUADRANT_ORDER.map((quadrant) => {
    const filtered = items.filter((item) => item.quadrant === quadrant);
    return {
      quadrant,
      quadrant_label: QUADRANT_META[quadrant].label,
      count: filtered.length,
      entity_breakdown: {
        brand: filtered.filter((item) => item.entity_classification === 'brand').length,
        competitor: filtered.filter((item) => item.entity_classification === 'competitor').length,
        general_knowledge: filtered.filter((item) => item.entity_classification === 'general_knowledge').length,
      },
    };
  });
}

function dimensionRatio(dimension: ConfidenceSignalDimensionScore) {
  const max = Number(dimension.max_score ?? 0) || 1;
  const score = Number(dimension.score ?? 0) || 0;
  return score / max;
}

function shortReason(text?: string) {
  return (text || '').split('。', 1)[0]?.trim() || '当前维度暂无进一步说明。';
}

function buildFallbackAuditReport(item: ConfidenceSignalItem) {
  const dimensions = [...(item.dimension_scores ?? [])];
  if (!dimensions.length) return item.audit_report;

  const rankedHigh = [...dimensions]
    .sort((left, right) => dimensionRatio(right) - dimensionRatio(left))
    .slice(0, 3);
  const rankedLow = [...dimensions]
    .sort((left, right) => dimensionRatio(left) - dimensionRatio(right))
    .slice(0, 3);

  return {
    score_formula: `${dimensions
      .map((dimension) => `${formatScore(dimension.score)} (${String(dimension.key || '').toUpperCase()})`)
      .join(' + ')} = ${formatScore(item.aice_score ?? item.overall_score)}`,
    core_summary:
      item.repair_action ||
      `该来源当前置信分为 ${formatScore(item.aice_score ?? item.overall_score)}，可先从高分维度和低分维度两侧审视。`,
    high_confidence_points: rankedHigh.map((dimension) => ({
      dimension_key: dimension.key,
      dimension_label: dimension.label,
      fact: shortReason(dimension.reasoning),
      logic: '该维度当前得分相对更高，是 AI 更容易采信的部分。',
      evidence: dimension.reasoning,
    })),
    risk_points: rankedLow.map((dimension) => ({
      dimension_key: dimension.key,
      dimension_label: dimension.label,
      fact: shortReason(dimension.reasoning),
      logic: '该维度当前得分相对更低，是需要优先排查的风险点。',
      evidence: dimension.reasoning,
    })),
    action_steps:
      item.recommendations?.map((recommendation, index) => ({
        priority: index + 1,
        dimension_key: undefined,
        dimension_label: recommendation.title,
        issue_type: '动作',
        instruction: recommendation.action,
        reason: recommendation.reason,
        example: null,
      })) ?? [],
  };
}


function StatusBanner({
  phase,
  message,
}: {
  phase?: 'idle' | 'running' | 'ready' | 'error';
  message?: string;
}) {
  if (!message || phase === 'idle' || !phase) {
    return null;
  }

  const tone =
    phase === 'running'
      ? {
          border: 'rgba(59,130,246,0.22)',
          bg: 'rgba(59,130,246,0.10)',
          text: '#1d4ed8',
          label: '额外评估进行中',
        }
      : phase === 'error'
      ? {
          border: 'rgba(244,63,94,0.22)',
          bg: 'rgba(244,63,94,0.10)',
          text: '#be123c',
          label: '额外评估失败',
        }
      : {
          border: 'rgba(16,185,129,0.22)',
          bg: 'rgba(16,185,129,0.10)',
          text: '#047857',
          label: '额外评估已完成',
        };

  return (
    <div
      className="rounded-[20px] border px-4 py-4"
      style={{ borderColor: tone.border, backgroundColor: tone.bg }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex items-center gap-2 text-[13px] font-semibold" style={{ color: tone.text }}>
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: tone.text }} />
          {tone.label}
        </div>
        <div className="text-[12px]" style={{ color: tone.text }}>
          {phase === 'running' ? '请稍候' : phase === 'ready' ? '已写回当前报告' : '请检查输入'}
        </div>
      </div>
      <div className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">{message}</div>
    </div>
  );
}

function AuditSectionTitle({ children }: { children: ReactNode }) {
  return <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">{children}</div>;
}

function DimensionScoreList({ dimensions }: { dimensions?: ConfidenceSignalDimensionScore[] }) {
  if (!dimensions?.length) return null;
  return (
    <div className="space-y-2.5">
      {dimensions.map((dimension, index) => (
        <div
          key={`${dimension.key}_${index}`}
          className="rounded-[18px] border px-4 py-3"
          style={{
            borderColor: 'var(--border-subtle)',
            background: 'var(--bg-secondary)',
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-[13px] font-medium text-[var(--text-primary)]">{dimension.label || dimension.key}</div>
            <MetaPill>
              {formatScore(dimension.score)} / {formatScore(dimension.max_score)}
            </MetaPill>
          </div>
          {dimension.reasoning ? (
            <div className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">{dimension.reasoning}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function AuditPointList({
  title,
  points,
  emptyText,
}: {
  title: string;
  points?: ConfidenceAuditPoint[];
  emptyText: string;
}) {
  return (
    <div className="space-y-3">
      <AuditSectionTitle>{title}</AuditSectionTitle>
      {points?.length ? (
        <div className="space-y-2.5">
          {points.map((point, index) => (
            <div
              key={`${point.dimension_key}_${index}`}
              className="rounded-[18px] border px-4 py-3"
              style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}
            >
              <div className="flex flex-wrap items-center gap-2">
                {point.dimension_label ? <MetaPill>{point.dimension_label}</MetaPill> : null}
              </div>
              {point.fact ? (
                <div className="mt-2 text-[14px] font-medium leading-6 text-[var(--text-primary)]">{point.fact}</div>
              ) : null}
              {point.logic ? (
                <div className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">{point.logic}</div>
              ) : null}
              {point.evidence ? (
                <div className="mt-2 text-[12px] leading-6 text-[var(--text-tertiary)]">证据：{point.evidence}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-[18px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[13px] text-[var(--text-tertiary)]">
          {emptyText}
        </div>
      )}
    </div>
  );
}

function ModificationBasisList({
  points,
  steps,
}: {
  points?: ConfidenceAuditPoint[];
  steps?: ConfidenceAuditActionStep[];
}) {
  const pointMap = new Map((points ?? []).map((point) => [point.dimension_key, point]));
  const rows = (steps ?? []).map((step, index) => ({
    step,
    point: pointMap.get(step.dimension_key),
    index,
  }));

  return (
    <div className="space-y-3">
      <AuditSectionTitle>修改方向的事实依据</AuditSectionTitle>
      {rows.length ? (
        <div className="space-y-2.5">
          {rows.map(({ step, point, index }) => (
            <div
              key={`${step.dimension_key}_${index}`}
              className="rounded-[18px] border px-4 py-3"
              style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}
            >
              <div className="flex flex-wrap items-center gap-2">
                <MetaPill tone="accent">P{step.priority ?? index + 1}</MetaPill>
                {step.dimension_label ? <MetaPill>{step.dimension_label}</MetaPill> : null}
                {step.issue_type ? <MetaPill>{step.issue_type}</MetaPill> : null}
              </div>
              {point?.fact ? (
                <div className="mt-3 text-[14px] font-medium leading-6 text-[var(--text-primary)]">{point.fact}</div>
              ) : null}
              {point?.evidence ? (
                <div className="mt-2 text-[12px] leading-6 text-[var(--text-tertiary)]">事实依据：{point.evidence}</div>
              ) : null}
              {step.instruction ? (
                <div className="mt-3 text-[14px] font-medium leading-6 text-[var(--text-primary)]">{step.instruction}</div>
              ) : null}
              {step.reason ? (
                <div className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">为什么这么改：{step.reason}</div>
              ) : null}
              {step.example ? (
                <div className="mt-2 text-[12px] leading-6 text-[var(--text-tertiary)]">修改示例：{step.example}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-[18px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[13px] text-[var(--text-tertiary)]">
          当前没有明确的修改方向依据。
        </div>
      )}
    </div>
  );
}

function AuditBody({ item }: { item: ConfidenceSignalItem }) {
  const audit = item.audit_report ?? buildFallbackAuditReport(item);
  return (
    <div className="mt-5 space-y-5">
      {audit?.core_summary ? (
        <div className="space-y-3">
          <AuditSectionTitle>评估结论</AuditSectionTitle>
          <div
            className="rounded-[20px] border px-4 py-4"
            style={{
              borderColor: 'var(--border-subtle)',
              background: 'color-mix(in srgb, var(--bg-secondary) 90%, transparent)',
            }}
          >
            <div className="text-[14px] leading-7 text-[var(--text-primary)]">{audit.core_summary}</div>
          </div>
        </div>
      ) : null}

      <AuditPointList
        title="高分事实依据"
        points={audit?.high_confidence_points}
        emptyText="当前没有足够强的高分维度证据。"
      />

      <ModificationBasisList points={audit?.risk_points} steps={audit?.action_steps} />

      <div className="space-y-3">
        <AuditSectionTitle>维度参考</AuditSectionTitle>
        <DimensionScoreList dimensions={item.dimension_scores} />
      </div>
    </div>
  );
}

function DetailItemCard({ item }: { item: ConfidenceSignalItem }) {
  const entityMeta = getEntityMeta(item.entity_classification);
  const quadrantMeta = getQuadrantMeta(item.quadrant);

  return (
    <Card padding="none" className="rounded-[24px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: quadrantMeta.border }}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-[20px] font-semibold leading-8 text-[var(--text-primary)]">{item.label}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <span
              className="rounded-full px-3 py-1 text-[12px] font-medium"
              style={{ backgroundColor: entityMeta.softBg, color: entityMeta.softText }}
            >
              {item.entity_label || entityMeta.label}
            </span>
            <span
              className="rounded-full border px-3 py-1 text-[12px] font-medium text-[var(--text-primary)]"
              style={{ borderColor: quadrantMeta.border, backgroundColor: quadrantMeta.glow }}
            >
              {quadrantMeta.plainLabel} · {item.quadrant_label || quadrantMeta.label}
            </span>
            <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1 text-[12px] text-[var(--text-secondary)]">
              频次 {item.frequency ?? item.occurrences ?? '--'}
            </span>
            <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1 text-[12px] text-[var(--text-secondary)]">
              置信分 {formatScore(item.aice_score ?? item.overall_score)}
            </span>
          </div>
        </div>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[13px] text-[var(--color-primary)] hover:underline"
          >
            查看链接
            <RiArrowRightUpLine className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </div>
      <AuditBody item={item} />
    </Card>
  );
}

function GeneralKnowledgeRow({ item }: { item: ConfidenceSignalItem }) {
  return (
    <div className="rounded-[20px] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-medium leading-7 text-[var(--text-primary)]">{item.label}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1 text-[12px] text-[var(--text-secondary)]">
              频次 {item.frequency ?? item.occurrences ?? '--'}
            </span>
            <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1 text-[12px] text-[var(--text-secondary)]">
              置信分 {formatScore(item.aice_score ?? item.overall_score)}
            </span>
            {item.site_name ? (
              <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1 text-[12px] text-[var(--text-secondary)]">
                {item.site_name}
              </span>
            ) : null}
          </div>
        </div>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[13px] text-[var(--color-primary)] hover:underline"
          >
            查看链接
            <RiArrowRightUpLine className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </div>
    </div>
  );
}

function ExtraResultCard({
  item,
  indexLabel,
  isLatest = false,
}: {
  item: ConfidenceSignalItem;
  indexLabel: string;
  isLatest?: boolean;
}) {
  const entityMeta = getEntityMeta(item.entity_classification);
  const quadrantMeta = getQuadrantMeta(item.quadrant);

  return (
    <div
      className="rounded-[24px] border px-5 py-5"
      style={{
        borderColor: isLatest ? entityMeta.fill : 'var(--border-subtle)',
        background: isLatest
          ? `linear-gradient(180deg, color-mix(in srgb, ${entityMeta.fill} 14%, var(--bg-elevated)), var(--bg-elevated) 72%)`
          : 'var(--bg-elevated)',
        boxShadow: isLatest ? '0 14px 36px rgba(4, 10, 24, 0.22)' : undefined,
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">{indexLabel}</span>
            {isLatest ? (
              <span
                className="rounded-full px-3 py-1 text-[11px] font-semibold"
                style={{
                  backgroundColor: 'var(--status-success-bg)',
                  color: 'var(--status-success)',
                }}
              >
                最近追加
              </span>
            ) : null}
          </div>
          <div className="mt-3 text-[24px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">{item.label}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <span
              className="rounded-full px-3 py-1 text-[12px] font-medium"
              style={{ backgroundColor: entityMeta.softBg, color: entityMeta.softText }}
            >
              {item.entity_label || entityMeta.label}
            </span>
            <span
              className="rounded-full border px-3 py-1 text-[12px] font-medium text-[var(--text-primary)]"
              style={{ borderColor: quadrantMeta.border, backgroundColor: quadrantMeta.glow }}
            >
              {quadrantMeta.plainLabel} · {item.quadrant_label || quadrantMeta.label}
            </span>
            <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1 text-[12px] text-[var(--text-secondary)]">
              频次 {item.frequency ?? item.occurrences ?? '--'}
            </span>
            <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1 text-[12px] text-[var(--text-secondary)]">
              置信分 {formatScore(item.aice_score ?? item.overall_score)}
            </span>
          </div>
        </div>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[13px] text-[var(--color-primary)] hover:underline"
          >
            查看链接
            <RiArrowRightUpLine className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </div>

      {item.site_name || item.domain ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {item.site_name ? <MetaPill>{item.site_name}</MetaPill> : null}
          {!item.site_name && item.domain ? <MetaPill>{item.domain}</MetaPill> : null}
        </div>
      ) : null}
      <AuditBody item={item} />
    </div>
  );
}

function MatrixCluster({
  point,
}: {
  point: MatrixPoint;
}) {
  const entityMeta = getEntityMeta(point.entity);

  return (
    <div
      className="rounded-[18px] border px-4 py-3"
      style={{
        borderColor: 'color-mix(in srgb, var(--border-subtle) 70%, rgba(255,255,255,0.10) 30%)',
        background:
          'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 88%, rgba(255,255,255,0.02) 12%), var(--bg-secondary))',
        boxShadow: '0 8px 24px rgba(4, 10, 24, 0.16)',
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: entityMeta.fill }} />
            <span className="text-[12px] font-medium" style={{ color: entityMeta.softText }}>
              {point.entityLabel}
            </span>
          </div>
          <div className="mt-2 text-[14px] font-semibold leading-6 text-[var(--text-primary)]">
            {point.count > 1 ? `${point.count} 个来源聚合` : point.title}
          </div>
          <div className="mt-1 text-[12px] leading-6 text-[var(--text-secondary)]">
            频次 {point.frequency} · 均分 {formatScore(point.score)}
            {point.domain ? ` · ${point.domain}` : ''}
          </div>
        </div>
        <div
          className="flex h-10 min-w-10 items-center justify-center rounded-full px-3 text-[13px] font-semibold"
          style={{ backgroundColor: entityMeta.softBg, color: entityMeta.softText }}
        >
          {point.count}
        </div>
      </div>
      <div className="mt-3 text-[11px] tracking-[0.08em] text-[var(--text-tertiary)]">代表事实</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {point.sampleTitles.slice(0, 3).map((title, index) => (
          <span
            key={`${point.item_id}_${index}`}
            className="rounded-full bg-[var(--bg-secondary)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]"
          >
            {title}
          </span>
        ))}
      </div>
    </div>
  );
}

function QuadrantMatrixCard({
  quadrant,
  points,
  overview,
}: {
  quadrant: ConfidenceQuadrant;
  points: MatrixPoint[];
  overview?: ConfidenceQuadrantOverview;
}) {
  const meta = getQuadrantMeta(quadrant);
  const count = overview?.count ?? points.reduce((sum, point) => sum + point.count, 0);
  const breakdown = overview?.entity_breakdown;

  return (
    <div
      className="rounded-[24px] border px-5 py-5"
      style={{
        borderColor: meta.border,
        background: `linear-gradient(180deg, color-mix(in srgb, ${meta.area} 82%, var(--bg-elevated)), color-mix(in srgb, var(--bg-elevated) 92%, var(--bg-secondary)) 68%)`,
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)',
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">{meta.plainLabel}</div>
          <div className="mt-2 text-[22px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">{overview?.quadrant_label || meta.label}</div>
          <div className="mt-1 text-[13px] text-[var(--text-secondary)]">{meta.feature}</div>
        </div>
        <div className="text-right">
          <div className="text-[30px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">{count}</div>
          <div className="text-[12px] text-[var(--text-tertiary)]">来源</div>
        </div>
      </div>

      <div
        className="mt-4 rounded-[18px] border px-4 py-3 text-[12px] leading-6 text-[var(--text-secondary)]"
        style={{
          borderColor: 'color-mix(in srgb, var(--border-subtle) 68%, rgba(255,255,255,0.08) 32%)',
          background: 'color-mix(in srgb, var(--bg-secondary) 88%, transparent)',
        }}
      >
        我方 {breakdown?.brand ?? 0} · 竞方 {breakdown?.competitor ?? 0} · 共业 {breakdown?.general_knowledge ?? 0}
      </div>

      <div className="mt-4 space-y-3">
        {points.length > 0 ? (
          <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">代表来源</div>
        ) : null}
        {points.length > 0 ? (
          points.slice(0, 4).map((point) => <MatrixCluster key={`${quadrant}_${point.item_id}_${point.frequency}`} point={point} />)
        ) : (
          <div className="rounded-[18px] border border-dashed border-[var(--border-subtle)] px-4 py-8 text-[13px] text-[var(--text-tertiary)]">
            当前没有落在这个象限的代表来源。
          </div>
        )}
      </div>
    </div>
  );
}

export function ConfidenceSignalContent({ content, printMode = false }: ConfidenceSignalContentProps) {
  const extraResultRef = useRef<HTMLDivElement | null>(null);
  const didHydrateManualStateRef = useRef(false);
  const previousManualCountRef = useRef(0);
  const previousPhaseRef = useRef<string | undefined>(undefined);
  const summary = content.data.summary;
  const matrixConfig = content.data.matrix_config;
  const ecosystemMatrix = content.data.ecosystem_matrix;
  const allItems = [...(content.data.auto_items ?? []), ...(content.data.manual_items ?? [])];
  const manualItems = content.data.manual_items ?? [];
  const confidenceStatus = content.data.status;
  const aiceThreshold = Number(matrixConfig?.aice_threshold ?? 75);
  const frequencyThreshold = Number(matrixConfig?.frequency_threshold ?? 1);
  const matrixPoints = buildMatrixPoints(
    allItems.map(toMatrixPoint).filter((item): item is RawMatrixPoint => Boolean(item)),
    aiceThreshold,
  );
  const quadrantOverview = content.data.quadrant_overview?.length
    ? content.data.quadrant_overview
    : buildFallbackQuadrantOverview(allItems);
  const analysisBlocks = (content.data.analysis_blocks ?? []).filter(
    (block) => (block.item_count ?? block.items?.length ?? 0) > 0
  );
  const generalKnowledgeInsight = content.data.general_knowledge_insight;
  const quadrantOverviewMap = new Map(quadrantOverview.map((item) => [item.quadrant, item]));
  const quadrantPointsMap = new Map<ConfidenceQuadrant, MatrixPoint[]>(
    QUADRANT_ORDER.map((quadrant) => [quadrant, matrixPoints.filter((point) => point.quadrant === quadrant)]),
  );
  const generalKnowledgeItems =
    generalKnowledgeInsight?.representative_items?.length
      ? generalKnowledgeInsight.representative_items
      : [
          ...(generalKnowledgeInsight?.top_frequency_items ?? []),
          ...(generalKnowledgeInsight?.top_score_items ?? []),
        ].filter(
          (item, index, array) =>
            array.findIndex((candidate) => candidate.item_id === item.item_id) === index,
        );
  const latestManualItem = manualItems.length > 0 ? manualItems[manualItems.length - 1] : null;
  const previousManualItems = manualItems.length > 1 ? manualItems.slice(0, -1).reverse() : [];

  useEffect(() => {
    const previousCount = previousManualCountRef.current;
    const previousPhase = previousPhaseRef.current;
    const nextCount = manualItems.length;
    const nextPhase = confidenceStatus?.phase;

    if (!didHydrateManualStateRef.current) {
      previousManualCountRef.current = nextCount;
      previousPhaseRef.current = nextPhase;
      didHydrateManualStateRef.current = true;
      return;
    }

    if (
      !printMode &&
      extraResultRef.current &&
      nextCount > 0 &&
      (nextCount > previousCount || (previousPhase === 'running' && nextPhase === 'ready'))
    ) {
      extraResultRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    previousManualCountRef.current = nextCount;
    previousPhaseRef.current = nextPhase;
  }, [manualItems.length, confidenceStatus?.phase, printMode]);

  return (
    <ReportPage>
      <ReportHero
        eyebrow="置信度报告"
        title={content.data.headline || '置信度报告'}
        meta={
          <>
            <span>最近更新 {formatUpdatedAt(summary?.updated_at || content.data.updated_at)}</span>
            <span>平均置信分 {formatScore(summary?.average_confidence_score ?? summary?.average_score)}</span>
            <span>共业阵营 {summary?.general_knowledge_count ?? 0}</span>
          </>
        }
      />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <ReportMetricCard
          label="已评估来源"
          value={summary?.evaluated_count ?? matrixPoints.length}
          accent="rgba(59,130,246,0.08)"
        />
        <ReportMetricCard
          label="我方阵营"
          value={summary?.brand_count ?? 0}
          accent="rgba(59,130,246,0.08)"
        />
        <ReportMetricCard
          label="竞方阵营"
          value={summary?.competitor_count ?? 0}
          accent="rgba(244,63,94,0.08)"
        />
        <ReportMetricCard
          label="重点修缮来源"
          value={summary?.vulnerable_source_count ?? summary?.second_quadrant_count ?? 0}
          accent="rgba(245,158,11,0.08)"
        />
        <ReportMetricCard
          label="额外评估条数"
          value={manualItems.length}
          accent="rgba(16,185,129,0.08)"
        />
      </div>

      <div className="flex flex-wrap gap-2 text-[12px] text-[var(--text-secondary)]">
        <MetaPill tone="accent">高分线 {formatScore(aiceThreshold)}</MetaPill>
        <MetaPill>
          高频从 {Number.isInteger(frequencyThreshold) ? `${frequencyThreshold} 次` : `${formatScore(frequencyThreshold)} 次`} 开始
        </MetaPill>
      </div>

      <StatusBanner phase={confidenceStatus?.phase} message={confidenceStatus?.message} />

      <ReportSection
        eyebrow="语境生态坐标系"
        title={ecosystemMatrix?.title || '引用来源生态矩阵'}
        description="用矩阵辅助看整体分布，不替代单条来源的审计判断。"
        className="rounded-[30px]"
      >
        <div className="flex flex-wrap items-stretch justify-between gap-3">
          <div className="flex flex-wrap gap-3">
            <MatrixSummaryStat label="评估来源" value={summary?.evaluated_count ?? allItems.length} />
            <MatrixSummaryStat label="图上聚合" value={`${matrixPoints.length} 组`} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <MetaPill tone="accent">高分线 {formatScore(matrixConfig?.aice_threshold)}</MetaPill>
            <MetaPill>
              高频线 {Number.isInteger(frequencyThreshold) ? `${frequencyThreshold} 次` : formatScore(matrixConfig?.frequency_threshold)}
            </MetaPill>
            <MetaPill>气泡大小代表聚合来源数</MetaPill>
          </div>
        </div>

        <div
          className="relative mt-6 overflow-hidden rounded-[32px] border px-4 py-4 md:px-5"
          style={{
            borderColor: 'color-mix(in srgb, var(--border-subtle) 70%, rgba(255,255,255,0.08) 30%)',
            background:
              'radial-gradient(circle at top right, color-mix(in srgb, #0ea5e9 14%, transparent), transparent 32%), radial-gradient(circle at top left, color-mix(in srgb, #f59e0b 14%, transparent), transparent 32%), linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 86%, #13273a 14%), color-mix(in srgb, var(--bg-secondary) 94%, #17130f 6%))',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 10px 30px rgba(4, 10, 24, 0.22)',
          }}
        >
          <div
            className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-[20px] border px-4 py-3 backdrop-blur-sm"
            style={{
              borderColor: 'color-mix(in srgb, var(--border-subtle) 64%, rgba(255,255,255,0.08) 36%)',
              background: 'color-mix(in srgb, var(--bg-elevated) 88%, transparent)',
              boxShadow: '0 8px 24px rgba(4, 10, 24, 0.16)',
            }}
          >
            <div className="flex flex-wrap gap-2">
              {(Object.keys(ENTITY_META) as ConfidenceEntityClassification[]).map((key) => {
                const meta = ENTITY_META[key];
                return (
                  <span
                    key={key}
                    className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] font-medium"
                    style={{ backgroundColor: meta.softBg, color: meta.softText }}
                  >
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: meta.fill }} />
                    {meta.label}
                  </span>
                );
              })}
            </div>
            <div className="flex flex-wrap gap-2">
              <MetaPill>横轴：引用频次</MetaPill>
              <MetaPill>纵轴：置信分</MetaPill>
            </div>
          </div>

          <div
            className="rounded-[28px] border p-4 backdrop-blur-sm md:p-5"
            style={{
              borderColor: 'color-mix(in srgb, var(--border-subtle) 68%, rgba(255,255,255,0.08) 32%)',
              background: 'color-mix(in srgb, var(--bg-secondary) 82%, transparent)',
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)',
            }}
          >
            <div className="grid gap-4 md:grid-cols-[84px_minmax(0,1fr)] md:grid-rows-[auto_minmax(0,1fr)_auto]">
              <div />
              <div className="grid grid-cols-2 gap-4 text-[12px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">
                <div className="rounded-full bg-[var(--bg-secondary)] px-4 py-2 text-center">低频</div>
                <div className="rounded-full bg-[var(--bg-secondary)] px-4 py-2 text-center">高频</div>
              </div>

              <div className="hidden flex-col justify-between py-4 md:flex">
                <div className="rounded-full bg-[var(--bg-secondary)] px-3 py-2 text-center text-[12px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">高分</div>
                <div className="rounded-full bg-[var(--bg-secondary)] px-3 py-2 text-center text-[12px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">低分</div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                {MATRIX_LAYOUT.flatMap((row) =>
                  row.map((quadrant) => (
                    <QuadrantMatrixCard
                      key={quadrant}
                      quadrant={quadrant}
                      points={quadrantPointsMap.get(quadrant) ?? []}
                      overview={quadrantOverviewMap.get(quadrant)}
                    />
                  )),
                )}
              </div>

              <div />
              <div className="grid grid-cols-2 gap-4 text-[12px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">
                <div className="rounded-full bg-[var(--bg-secondary)] px-4 py-2 text-center">引用少</div>
                <div className="rounded-full bg-[var(--bg-secondary)] px-4 py-2 text-center">引用多</div>
              </div>
            </div>
          </div>
        </div>
      </ReportSection>

      <ReportSection
        eyebrow="AICE 审计"
        title="重点审计来源"
        description="先用坐标判断整体分布，再展开关键来源的事实依据、风险点和修改方向。"
      >
        <div className="space-y-6">
          {analysisBlocks.length ? (
            analysisBlocks.map((block) => (
              <Card
                key={block.key}
                padding="none"
                className="rounded-[28px] border bg-[var(--bg-tertiary)] p-5 md:p-6"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-[24px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">{block.title}</div>
                    {block.description ? (
                      <div className="mt-2 max-w-4xl text-[14px] leading-7 text-[var(--text-secondary)]">{block.description}</div>
                    ) : null}
                  </div>
                  <MetaPill>{block.item_count ?? block.items?.length ?? 0} 条样本</MetaPill>
                </div>

                <div className="mt-5 space-y-4">
                  {block.items?.map((item) => <DetailItemCard key={item.item_id} item={item} />)}
                </div>
              </Card>
            ))
          ) : (
            <div className="rounded-[20px] border border-dashed border-[var(--border-subtle)] px-5 py-10 text-[14px] text-[var(--text-tertiary)]">
              当前高频高分和高频低分区域里还没有足够的品牌/竞品代表样本，暂不展开阵地分析。
            </div>
          )}
        </div>
      </ReportSection>

      <div ref={extraResultRef}>
        <ReportSection
          eyebrow="额外评估"
          title="额外评估结果"
          description="手动追加的链接或文本会单独写回这里，方便和原始引用来源分开看。"
        >
          {manualItems.length > 0 ? (
            <div className="space-y-5">
              {latestManualItem ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">最新结果</div>
                      <div className="mt-1 text-[18px] font-semibold text-[var(--text-primary)]">最近一次额外评估</div>
                    </div>
                    <MetaPill tone="accent">新增</MetaPill>
                  </div>
                  <ExtraResultCard item={latestManualItem} indexLabel={`追加评估 #${manualItems.length}`} isLatest />
                </div>
              ) : null}

              {previousManualItems.length > 0 ? (
                <div className="rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4">
                  <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">历史补样</div>
                  <div className="mt-3 space-y-3">
                    {previousManualItems.map((item, reverseIndex) => {
                      const itemIndex = manualItems.length - reverseIndex - 1;
                      return (
                        <ExtraResultCard
                          key={`manual_${item.item_id}`}
                          item={item}
                          indexLabel={`追加评估 #${itemIndex}`}
                        />
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="rounded-[20px] border border-dashed border-[var(--border-subtle)] px-5 py-10 text-[14px] text-[var(--text-tertiary)]">
              当前还没有额外评估结果。你可以从右上角“额外评估”继续追加链接或文本。
            </div>
          )}
        </ReportSection>
      </div>

      <section className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-5 md:p-6">
        <div className="flex items-center gap-2 text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">
          <RiShieldCheckLine className="h-4 w-4" />
          共业阵营观察
        </div>
        <div className="mt-3 text-[14px] leading-8 text-[var(--text-secondary)]">
          {generalKnowledgeInsight?.summary || '当前没有足够的共业语料可供进一步分析。'}
        </div>
        <div className="mt-5 space-y-3">
          {generalKnowledgeItems.length ? (
            generalKnowledgeItems.map((item) => <GeneralKnowledgeRow key={item.item_id} item={item} />)
          ) : (
            <div className="rounded-[18px] border border-dashed px-4 py-8 text-[14px] text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }}>
              当前没有可展示的共业样本。
            </div>
          )}
        </div>
      </section>
    </ReportPage>
  );
}

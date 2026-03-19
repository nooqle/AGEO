'use client';

import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import { RiArrowRightUpLine } from '@remixicon/react';
import { ReportHero, ReportMetricCard, ReportPage, ReportSection } from './ReportScaffold';
import type {
  ConfidenceOverview,
  ConfidencePattern,
  ConfidenceSignalDimensionScore,
  ConfidenceSignalItem,
  ReportCanvasContent,
} from '@/types/canvas';

interface ConfidenceSignalContentProps {
  content: ReportCanvasContent;
  printMode?: boolean;
}

function formatScore(value?: number | null) {
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

function MetaPill({ children }: { children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-3 py-1.5 text-[12px]"
      style={{
        background: 'var(--bg-secondary)',
        color: 'var(--text-secondary)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      {children}
    </span>
  );
}

function StatusBanner({
  phase,
  message,
}: {
  phase?: 'idle' | 'running' | 'ready' | 'error';
  message?: string;
}) {
  if (!phase || phase === 'idle' || !message) return null;

  const tone =
    phase === 'running'
      ? {
          border: 'rgba(59,130,246,0.22)',
          bg: 'rgba(59,130,246,0.10)',
          text: '#2563eb',
          label: '额外评估进行中',
        }
      : phase === 'error'
      ? {
          border: 'rgba(244,63,94,0.22)',
          bg: 'rgba(244,63,94,0.10)',
          text: '#e11d48',
          label: '额外评估失败',
        }
      : {
          border: 'rgba(16,185,129,0.22)',
          bg: 'rgba(16,185,129,0.10)',
          text: '#059669',
          label: '额外评估已完成',
        };

  return (
    <div className="rounded-[20px] border px-4 py-4" style={{ borderColor: tone.border, backgroundColor: tone.bg }}>
      <div className="flex items-center gap-2 text-[13px] font-semibold" style={{ color: tone.text }}>
        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: tone.text }} />
        {tone.label}
      </div>
      <div className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">{message}</div>
    </div>
  );
}

function OverviewCard({
  title,
  overview,
  accent,
}: {
  title: string;
  overview?: ConfidenceOverview;
  accent: string;
}) {
  const sources = overview?.representative_sources ?? [];
  return (
    <div
      className="rounded-[22px] border p-5"
      style={{
        borderColor: 'var(--border-subtle)',
        background: `linear-gradient(180deg, ${accent}, transparent 120%), var(--bg-elevated)`,
      }}
    >
      <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">{title}</div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <ReportMetricCard
          label="平均置信度"
          value={formatScore(overview?.average_confidence)}
          caption="按来源简单平均，用来看整体质量。"
          className="min-h-[150px]"
        />
        <ReportMetricCard
          label="加权平均置信度"
          value={formatScore(overview?.weighted_average_confidence)}
          caption="按引用频次加权，用来看真正进入回答链路的质量。"
          className="min-h-[150px]"
        />
        <ReportMetricCard
          label="样本数"
          value={overview?.source_count ?? 0}
          caption={`低置信来源 ${overview?.low_confidence_source_count ?? 0} 个`}
          className="min-h-[150px]"
        />
      </div>

      {sources.length ? (
        <div className="mt-5 rounded-[18px] border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
          <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">代表来源</div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            {sources.map((source) => (
              <div
                key={`${source.item_id || source.label}_${source.domain || ''}`}
                className="rounded-[16px] border px-4 py-4"
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
              >
                <div className="line-clamp-2 text-[15px] font-medium leading-6 text-[var(--text-primary)]">
                  {source.label || '未命名来源'}
                </div>
                <div className="mt-2 text-[13px] text-[var(--text-secondary)]">
                  置信度 {formatScore(source.score)} · 频次 {source.frequency ?? 1}
                </div>
                {source.url ? (
                  <a
                    className="mt-3 inline-flex items-center gap-1 text-[13px] text-[var(--brand-text)]"
                    href={source.url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    查看链接
                    <RiArrowRightUpLine size={14} />
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PatternCard({
  pattern,
  tone,
}: {
  pattern: ConfidencePattern;
  tone: 'brand' | 'competitor';
}) {
  const accent = tone === 'brand' ? 'rgba(59,130,246,0.10)' : 'rgba(244,63,94,0.10)';
  const border = tone === 'brand' ? 'rgba(59,130,246,0.22)' : 'rgba(244,63,94,0.22)';
  return (
    <div className="rounded-[20px] border p-5" style={{ borderColor: border, background: accent }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">低置信共性</div>
          <div className="mt-2 text-[20px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            {pattern.pattern_label || '未命名问题'}
          </div>
        </div>
        <MetaPill>{pattern.sample_count ?? 0} 个来源</MetaPill>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <ReportMetricCard
          label="平均置信度"
          value={formatScore(pattern.average_confidence)}
          caption={
            pattern.affected_dimensions?.length
              ? `主要受 ${pattern.affected_dimensions.join('、')} 影响`
              : '当前未识别出更多维度信息'
          }
          className="min-h-[132px]"
        />
        <ReportMetricCard
          label="加权平均置信度"
          value={formatScore(pattern.weighted_average_confidence)}
          caption={pattern.suggestion || '当前暂无建议'}
          className="min-h-[132px]"
        />
      </div>

      {pattern.evidence_examples?.length ? (
        <div className="mt-5 space-y-3">
          {pattern.evidence_examples.map((example, index) => (
            <div
              key={`${example.label || 'example'}_${index}`}
              className="rounded-[16px] border px-4 py-4"
              style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
            >
              <div className="text-[15px] font-medium text-[var(--text-primary)]">
                {example.label || example.domain || '来源样本'}
              </div>
              <div className="mt-2 text-[13px] text-[var(--text-secondary)]">置信度 {formatScore(example.score)}</div>
              {example.evidence ? (
                <div className="mt-3 text-[14px] leading-7 text-[var(--text-secondary)]">{example.evidence}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function topLowDimensions(item: ConfidenceSignalItem): ConfidenceSignalDimensionScore[] {
  return [...(item.dimension_scores ?? [])]
    .filter((dimension) => typeof dimension.score === 'number' && typeof dimension.max_score === 'number')
    .sort((left, right) => {
      const leftRatio = (left.score ?? 0) / Math.max(left.max_score ?? 1, 1);
      const rightRatio = (right.score ?? 0) / Math.max(right.max_score ?? 1, 1);
      return leftRatio - rightRatio;
    })
    .slice(0, 2);
}

function ExtraEvaluationCard({
  item,
  badge,
}: {
  item: ConfidenceSignalItem;
  badge?: string;
}) {
  const weakDimensions = topLowDimensions(item);
  return (
    <div
      className="rounded-[20px] border p-5"
      style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">
            {item.input_type === 'text' ? '文本额外评估' : '链接额外评估'}
          </div>
          <div className="mt-2 text-[18px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            {item.label || item.domain || '额外评估结果'}
          </div>
        </div>
        {badge ? <MetaPill>{badge}</MetaPill> : null}
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        <MetaPill>置信度 {formatScore(item.aice_score ?? item.overall_score)}</MetaPill>
        <MetaPill>{item.entity_label || '未分类'}</MetaPill>
        <MetaPill>频次 {item.frequency ?? item.occurrences ?? 1}</MetaPill>
      </div>

      {weakDimensions.length ? (
        <div className="mt-5 space-y-3">
          {weakDimensions.map((dimension) => (
            <div
              key={`${item.item_id}_${dimension.key || dimension.label}`}
              className="rounded-[16px] border px-4 py-4"
              style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}
            >
              <div className="text-[14px] font-medium text-[var(--text-primary)]">
                {dimension.label || dimension.key}
              </div>
              <div className="mt-2 text-[13px] text-[var(--text-secondary)]">
                得分 {formatScore(dimension.score)} / {formatScore(dimension.max_score)}
              </div>
              {dimension.reasoning ? (
                <div className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">{dimension.reasoning}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ConfidenceSignalContent({
  content,
  printMode = false,
}: ConfidenceSignalContentProps) {
  const data = content.data;
  const summary = data.summary;
  const config = data.config;
  const brandOverview = data.brand_confidence_overview;
  const competitorOverview = data.competitor_confidence_overview;
  const brandPatterns = data.brand_low_confidence_patterns ?? [];
  const competitorPatterns = data.competitor_low_confidence_patterns ?? [];
  const recommendations = data.strategic_recommendations ?? [];
  const manualItems = data.extra_evaluation?.items ?? data.manual_items ?? [];
  const status = data.status;
  const extraResultRef = useRef<HTMLDivElement | null>(null);
  const previousManualCount = useRef(manualItems.length);
  const previousPhase = useRef(status?.phase);

  useEffect(() => {
    if (printMode) return;
    const nextPhase = status?.phase;
    const manualIncreased = manualItems.length > previousManualCount.current;
    const justCompleted = previousPhase.current === 'running' && nextPhase === 'ready';
    if ((manualIncreased || justCompleted) && manualItems.length > 0 && extraResultRef.current) {
      extraResultRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    previousManualCount.current = manualItems.length;
    previousPhase.current = nextPhase;
  }, [manualItems.length, printMode, status?.phase]);

  return (
    <ReportPage>
      <ReportHero
        eyebrow="置信度报告"
        title={data.headline || '置信度报告'}
        meta={
          <>
            <span>最近更新 {formatUpdatedAt(summary?.updated_at || data.updated_at)}</span>
            <span>评估来源 {summary?.auto_evaluated_count ?? summary?.total_citations ?? 0}</span>
            <span>额外评估 {summary?.manual_count ?? manualItems.length}</span>
          </>
        }
        note={
          <div className="space-y-3">
            <div className="text-[15px] leading-7 text-[var(--text-primary)]">
              {data.overall_conclusion || '当前暂无可展示的置信度对比结论。'}
            </div>
            <div className="flex flex-wrap gap-2">
              <MetaPill>低置信阈值 {formatScore(config?.low_confidence_threshold)}</MetaPill>
              <MetaPill>我方样本 {brandOverview?.source_count ?? 0}</MetaPill>
              <MetaPill>竞品样本 {competitorOverview?.source_count ?? 0}</MetaPill>
            </div>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-4">
        <ReportMetricCard
          label="我方平均置信度"
          value={formatScore(brandOverview?.average_confidence)}
          caption={`加权平均 ${formatScore(brandOverview?.weighted_average_confidence)}`}
        />
        <ReportMetricCard
          label="竞品平均置信度"
          value={formatScore(competitorOverview?.average_confidence)}
          caption={`加权平均 ${formatScore(competitorOverview?.weighted_average_confidence)}`}
        />
        <ReportMetricCard
          label="我方低置信来源"
          value={brandOverview?.low_confidence_source_count ?? 0}
          caption={`样本数 ${brandOverview?.source_count ?? 0}`}
        />
        <ReportMetricCard
          label="竞品低置信来源"
          value={competitorOverview?.low_confidence_source_count ?? 0}
          caption={`样本数 ${competitorOverview?.source_count ?? 0}`}
        />
      </div>

      <StatusBanner phase={status?.phase} message={status?.message} />

      <ReportSection title="品牌 vs 竞品置信度对比">
        <div className="grid gap-5 xl:grid-cols-2">
          <OverviewCard title="我方引用来源" overview={brandOverview} accent="rgba(59,130,246,0.08)" />
          <OverviewCard title="竞品引用来源" overview={competitorOverview} accent="rgba(244,63,94,0.08)" />
        </div>
      </ReportSection>

      <ReportSection title="我方低置信内容共性">
        {brandPatterns.length ? (
          <div className="space-y-4">
            {brandPatterns.map((pattern) => (
              <PatternCard key={`brand_${pattern.pattern_key || pattern.pattern_label}`} pattern={pattern} tone="brand" />
            ))}
          </div>
        ) : (
          <div className="text-[14px] leading-7 text-[var(--text-secondary)]">
            当前没有稳定识别到我方低置信内容共性，说明我方样本不足或整体质量较稳。
          </div>
        )}
      </ReportSection>

      <ReportSection title="竞品低置信内容共性">
        {competitorPatterns.length ? (
          <div className="space-y-4">
            {competitorPatterns.map((pattern) => (
              <PatternCard
                key={`competitor_${pattern.pattern_key || pattern.pattern_label}`}
                pattern={pattern}
                tone="competitor"
              />
            ))}
          </div>
        ) : (
          <div className="text-[14px] leading-7 text-[var(--text-secondary)]">
            当前没有稳定识别到竞品低置信内容共性，说明竞品样本不足或整体质量较稳。
          </div>
        )}
      </ReportSection>

      <ReportSection title="补位建议">
        {recommendations.length ? (
          <div className="grid gap-4 xl:grid-cols-3">
            {recommendations.map((item, index) => (
              <div
                key={`${item.title || 'recommendation'}_${index}`}
                className="rounded-[20px] border p-5"
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
              >
                <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">建议 {index + 1}</div>
                <div className="mt-2 text-[18px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
                  {item.title || '未命名建议'}
                </div>
                {item.reason ? (
                  <div className="mt-3 text-[14px] leading-7 text-[var(--text-secondary)]">{item.reason}</div>
                ) : null}
                {item.action ? (
                  <div className="mt-3 rounded-[16px] border px-4 py-4 text-[14px] leading-7 text-[var(--text-primary)]" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
                    {item.action}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[14px] leading-7 text-[var(--text-secondary)]">
            当前没有足够的低置信模式来形成补位建议。
          </div>
        )}
      </ReportSection>

      <div ref={extraResultRef}>
        <ReportSection title="额外评估结果">
          {manualItems.length ? (
            <div className="space-y-4">
              {manualItems.map((item, index) => (
                <ExtraEvaluationCard
                  key={`${item.item_id}_${index}`}
                  item={item}
                  badge={index === manualItems.length - 1 ? '最近追加' : `追加评估 #${index + 1}`}
                />
              ))}
            </div>
          ) : (
            <div className="text-[14px] leading-7 text-[var(--text-secondary)]">
              当前还没有额外评估结果。你可以在报告头部继续追加链接或文本做单条评估。
            </div>
          )}
        </ReportSection>
      </div>
    </ReportPage>
  );
}

'use client';

import {
  RiArrowRightUpLine,
  RiCompass3Line,
  RiFlag2Line,
  RiFocus3Line,
  RiShieldCheckLine,
  RiSparklingLine,
} from '@remixicon/react';
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/cn';
import { axisTick, tooltipStyle } from '@/styles/chart-theme';
import type {
  ConfidenceAnalysisBlock,
  ConfidenceEntityClassification,
  ConfidenceQuadrant,
  ConfidenceQuadrantOverview,
  ConfidenceRepairAction,
  ConfidenceSignalItem,
  ConfidenceSignalStatus,
  ReportCanvasContent,
} from '@/types/canvas';

interface ConfidenceSignalContentProps {
  content: ReportCanvasContent;
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
  z: number;
};

const ENTITY_META: Record<ConfidenceEntityClassification, { label: string; fill: string; softBg: string; softText: string }> = {
  brand: { label: '我方阵营', fill: '#38BDF8', softBg: 'rgba(56,189,248,0.12)', softText: '#38BDF8' },
  competitor: { label: '竞方阵营', fill: '#FB7185', softBg: 'rgba(251,113,133,0.12)', softText: '#FB7185' },
  general_knowledge: { label: '共业阵营', fill: '#A3A3A3', softBg: 'rgba(163,163,163,0.14)', softText: '#D4D4D4' },
};

const QUADRANT_META: Record<ConfidenceQuadrant, { label: string; short: string; border: string; glow: string }> = {
  q1_anchor: { label: '定海神针', short: 'Q1', border: 'rgba(16,185,129,0.28)', glow: 'rgba(16,185,129,0.12)' },
  q2_false_prosperity: { label: '虚假繁荣', short: 'Q2', border: 'rgba(245,158,11,0.28)', glow: 'rgba(245,158,11,0.12)' },
  q3_noise: { label: '沉寂噪音', short: 'Q3', border: 'rgba(148,163,184,0.22)', glow: 'rgba(148,163,184,0.10)' },
  q4_sleeping_asset: { label: '高潜伏藏', short: 'Q4', border: 'rgba(59,130,246,0.28)', glow: 'rgba(59,130,246,0.12)' },
};

function formatScore(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return value.toFixed(1);
}

function formatUpdatedAt(value?: string) {
  if (!value) return '刚刚更新';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function statusTone(status?: ConfidenceSignalStatus) {
  switch (status?.phase) {
    case 'running':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
    case 'error':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-100';
    default:
      return 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  }
}

function getEntityMeta(entity?: ConfidenceEntityClassification) {
  return ENTITY_META[entity ?? 'general_knowledge'];
}

function getQuadrantMeta(quadrant?: ConfidenceQuadrant) {
  return QUADRANT_META[quadrant ?? 'q3_noise'];
}

function toMatrixPoint(item: ConfidenceSignalItem): MatrixPoint | null {
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
    z: Math.max(10, frequency * 12),
  };
}

function buildFallbackQuadrantOverview(items: ConfidenceSignalItem[]): ConfidenceQuadrantOverview[] {
  const quadrants: ConfidenceQuadrant[] = ['q1_anchor', 'q2_false_prosperity', 'q3_noise', 'q4_sleeping_asset'];
  return quadrants.map((quadrant) => {
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

function buildFallbackAnalysisBlocks(items: ConfidenceSignalItem[]): ConfidenceAnalysisBlock[] {
  const defs = [
    ['brand_q1', '我方阵地：坚如磐石（善因固化）', '我方第一象限内容是当前 AI 语境中的稳定资产。', '高置信度归因分析'],
    ['competitor_q1', '竞方阵地：坚如磐石（见贤思齐）', '竞方第一象限内容说明对方已有稳定投喂能力。', '高置信度归因分析'],
    ['brand_q2', '我方阵地：被引用但置信度不高（发露修缮）', '我方第二象限内容是当前最优先的修缮区。', '低置信度归因分析'],
    ['competitor_q2', '竞方阵地：被引用但置信度不高（法施填补）', '竞方第二象限内容是降维覆盖的主要机会位。', '低置信度归因分析'],
  ] as const;
  return defs.map(([key, title, description, reasonLabel]) => {
    const blockItems = items.filter((item) => item.analysis_group === key).slice(0, 5);
    return { key, title, description, reason_label: reasonLabel, action_label: '修我/行动指南', item_count: blockItems.length, items: blockItems };
  });
}

function buildFallbackRepairActions(items: ConfidenceSignalItem[]): ConfidenceRepairAction[] {
  return [
    { priority: 'P0', title: '立即修缮', summary: '优先修复我方高频低置信来源。', count: items.filter((item) => item.analysis_group === 'brand_q2').length },
    { priority: 'P1', title: '对标固化', summary: '抽取第一象限优秀样本，沉淀为 SOP。', count: items.filter((item) => item.analysis_group === 'brand_q1' || item.analysis_group === 'competitor_q1').length },
    { priority: 'P2', title: '降维覆盖', summary: '针对竞方高频低置信来源供给更高质量内容。', count: items.filter((item) => item.analysis_group === 'competitor_q2').length },
    { priority: 'P3', title: '战略性忽略', summary: '低频低置信内容不投入专项资源。', count: items.filter((item) => item.quadrant === 'q3_noise').length },
  ];
}

function MatrixTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: MatrixPoint }> }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  const entityMeta = getEntityMeta(point.entity);
  return (
    <div className="w-[260px] rounded-[18px] border p-4 shadow-xl" style={{ ...tooltipStyle, borderRadius: '18px' }}>
      <div className="text-[14px] font-semibold text-[var(--text-primary)]">{point.title}</div>
      <div className="mt-2 flex flex-wrap gap-2">
        <span className="rounded-full px-2.5 py-1 text-[11px] font-medium" style={{ backgroundColor: entityMeta.softBg, color: entityMeta.softText }}>{point.entityLabel}</span>
        <span className="rounded-full bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">{point.quadrantLabel}</span>
      </div>
      <div className="mt-3 space-y-1.5 text-[12px] text-[var(--text-secondary)]">
        <div>AICE：{formatScore(point.score)}</div>
        <div>引用频次：{point.frequency}</div>
        {point.domain ? <div>域名：{point.domain}</div> : null}
      </div>
    </div>
  );
}

function SummaryMetric({ label, value, description }: { label: string; value: string | number; description: string }) {
  return (
    <Card padding="none" className="rounded-[24px] border border-white/10 bg-white/[0.06] p-5">
      <div className="text-[12px] tracking-[0.16em] text-white/60">{label}</div>
      <div className="mt-3 text-[34px] font-semibold tracking-[-0.06em] text-white">{value}</div>
      <div className="mt-2 text-[13px] leading-6 text-white/70">{description}</div>
    </Card>
  );
}

function DetailItemCard({ item, reasonLabel, actionLabel }: { item: ConfidenceSignalItem; reasonLabel?: string; actionLabel?: string }) {
  const entityMeta = getEntityMeta(item.entity_classification);
  const quadrantMeta = getQuadrantMeta(item.quadrant);
  const reasons = item.primary_reasons ?? item.top_signals ?? [];
  return (
    <Card padding="none" className="rounded-[24px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-[16px] font-semibold leading-7 text-[var(--text-primary)]">{item.label}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="rounded-full px-2.5 py-1 text-[11px] font-medium" style={{ backgroundColor: entityMeta.softBg, color: entityMeta.softText }}>{item.entity_label || entityMeta.label}</span>
            <span className="rounded-full border px-2.5 py-1 text-[11px] font-medium" style={{ borderColor: quadrantMeta.border, backgroundColor: quadrantMeta.glow, color: 'var(--text-primary)' }}>{item.quadrant_label || quadrantMeta.label}</span>
            <span className="rounded-full bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">频次 {item.frequency ?? item.occurrences ?? '--'}</span>
            <span className="rounded-full bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">AICE {formatScore(item.aice_score ?? item.overall_score)}</span>
          </div>
        </div>
        {item.url ? (
          <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[13px] text-[var(--color-primary)] hover:underline">
            查看链接
            <RiArrowRightUpLine className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <div>
          <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">{reasonLabel || '原因分析'}</div>
          <div className="mt-2 space-y-2">
            {reasons.length > 0 ? reasons.slice(0, 3).map((reason, index) => (
              <div key={`${item.item_id}_reason_${index}`} className="rounded-[16px] border px-4 py-3 text-[13px] leading-6 text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                {reason}
              </div>
            )) : (
              <div className="rounded-[16px] border border-dashed px-4 py-3 text-[13px] text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                当前还没有可展示的原因拆解。
              </div>
            )}
          </div>
        </div>
        <div>
          <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">{actionLabel || '行动建议'}</div>
          <div className="mt-2 rounded-[18px] border px-4 py-4 text-[13px] leading-7 text-[var(--text-secondary)]" style={{ borderColor: quadrantMeta.border, background: quadrantMeta.glow }}>
            {item.repair_action || '当前还没有返回修我动作。'}
          </div>
        </div>
      </div>
    </Card>
  );
}

function CompactItemList({ title, items }: { title: string; items: ConfidenceSignalItem[] }) {
  return (
    <Card padding="none" className="rounded-[22px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="text-[16px] font-semibold text-[var(--text-primary)]">{title}</div>
      <div className="mt-4 space-y-3">
        {items.length > 0 ? items.map((item) => (
          <div key={item.item_id} className="rounded-[16px] border px-4 py-3" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-[var(--text-primary)]">{item.label}</div>
                <div className="mt-1 text-[12px] text-[var(--text-secondary)]">频次 {item.frequency ?? item.occurrences ?? '--'} · AICE {formatScore(item.aice_score ?? item.overall_score)}</div>
              </div>
              {item.url ? <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12px] text-[var(--color-primary)] hover:underline"><RiArrowRightUpLine className="h-3.5 w-3.5" /></a> : null}
            </div>
          </div>
        )) : (
          <div className="rounded-[16px] border border-dashed px-4 py-6 text-[13px] text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }}>
            当前没有可展示的样本。
          </div>
        )}
      </div>
    </Card>
  );
}

export function ConfidenceSignalContent({ content }: ConfidenceSignalContentProps) {
  const summary = content.data.summary;
  const status = content.data.status;
  const findings = content.data.aggregate_findings ?? [];
  const matrixConfig = content.data.matrix_config;
  const ecosystemMatrix = content.data.ecosystem_matrix;
  const allItems = [...(content.data.auto_items ?? []), ...(content.data.manual_items ?? [])];
  const matrixPoints = allItems.map(toMatrixPoint).filter((item): item is MatrixPoint => Boolean(item));
  const quadrantOverview = content.data.quadrant_overview?.length ? content.data.quadrant_overview : buildFallbackQuadrantOverview(allItems);
  const analysisBlocks = content.data.analysis_blocks?.length ? content.data.analysis_blocks : buildFallbackAnalysisBlocks(allItems);
  const repairActions = content.data.repair_actions?.length ? content.data.repair_actions : buildFallbackRepairActions(allItems);
  const generalKnowledgeInsight = content.data.general_knowledge_insight;
  const brandPoints = matrixPoints.filter((point) => point.entity === 'brand');
  const competitorPoints = matrixPoints.filter((point) => point.entity === 'competitor');
  const generalPoints = matrixPoints.filter((point) => point.entity === 'general_knowledge');

  return (
    <div className="mx-auto max-w-[1360px] space-y-6 px-6 py-6 md:px-8 md:py-8">
      <section className="overflow-hidden rounded-[30px] border" style={{ borderColor: 'rgba(148,163,184,0.18)', background: 'radial-gradient(circle at top left, rgba(56,189,248,0.18), transparent 28%), radial-gradient(circle at top right, rgba(251,113,133,0.16), transparent 26%), linear-gradient(180deg, rgba(15,23,42,0.95), rgba(17,24,39,0.92))' }}>
        <div className="grid gap-6 px-6 py-6 md:px-7 md:py-7 lg:grid-cols-[1.15fr_0.85fr]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-[11px] tracking-[0.16em] text-white/70"><RiSparklingLine className="h-3.5 w-3.5" />CONFIDENCE REPORT</span>
              <span className={cn('inline-flex items-center rounded-full border px-3 py-1 text-[12px]', statusTone(status))}>{status?.message || '置信度报告已就绪'}</span>
            </div>
            <h1 className="mt-5 text-[clamp(2.3rem,4vw,3.8rem)] font-semibold tracking-[-0.05em] text-white">{content.data.headline || '置信度报告'}</h1>
            <p className="mt-4 max-w-3xl text-[15px] leading-8 text-white/74">{content.data.subtitle || '评估 AI 回答引用语料的阵营分布、生态位置与修我方向。'}</p>
            <div className="mt-5 rounded-[20px] border border-white/10 bg-white/[0.06] px-5 py-4">
              <div className="text-[12px] tracking-[0.14em] text-white/55">总诊断</div>
              <div className="mt-2 text-[15px] leading-8 text-white/80">{content.data.diagnosis || ecosystemMatrix?.diagnosis || '当前引用生态诊断数据正在生成。'}</div>
            </div>
            <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-white/50">
              <span>额外评估结果会继续合并进同一份报告</span>
              <span>AICE 高分阈值 {formatScore(matrixConfig?.aice_threshold)} / 高频阈值 {formatScore(matrixConfig?.frequency_threshold)}</span>
              <span>最近更新 {formatUpdatedAt(summary?.updated_at || content.data.updated_at)}</span>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <SummaryMetric label="总引用来源" value={summary?.evaluated_count ?? 0} description="当前已进入分析的自动引用与手动追加来源总数。" />
            <SummaryMetric label="我方阵营" value={summary?.brand_count ?? 0} description="明确服务于我方品牌认知的语料来源。" />
            <SummaryMetric label="竞方阵营" value={summary?.competitor_count ?? 0} description="当前被 AI 引用的竞品相关语料数量。" />
            <SummaryMetric label="共业阵营" value={summary?.general_knowledge_count ?? 0} description="行业默认解释框架中的通用知识来源。" />
            <SummaryMetric label="第二象限" value={summary?.second_quadrant_count ?? 0} description="被引用但置信度不高的脆弱来源数量。" />
            <SummaryMetric label="平均 AICE" value={formatScore(summary?.average_score)} description="当前整体语料质量与可采信稳定性的平均水平。" />
          </div>
        </div>
      </section>

      {findings.length > 0 ? (
        <section className="grid gap-4 xl:grid-cols-3">
          {findings.slice(0, 3).map((finding, index) => (
            <Card key={`${finding.title}_${index}`} padding="none" className="rounded-[24px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">摘要 {index + 1}</div>
              <div className="mt-2 text-[18px] font-semibold text-[var(--text-primary)]">{finding.title || `发现 ${index + 1}`}</div>
              <div className="mt-3 text-[13px] leading-7 text-[var(--text-secondary)]">{finding.description}</div>
            </Card>
          ))}
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card padding="none" className="rounded-[28px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]"><RiCompass3Line className="h-4 w-4" />语境生态坐标系</div>
              <div className="mt-2 text-[20px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">{ecosystemMatrix?.title || '引用语料生态矩阵'}</div>
              <div className="mt-1 text-[13px] leading-7 text-[var(--text-secondary)]">X 轴表示 AICE 置信度，Y 轴表示引用频次。颜色表示阵营归属，阈值线决定四象限分布。</div>
            </div>
            <div className="text-[12px] text-[var(--text-tertiary)]">共 {matrixPoints.length} 个来源</div>
          </div>
          <div className="mt-5 h-[420px] rounded-[24px] bg-[var(--bg-elevated)] px-2 py-4">
            {matrixPoints.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 16, right: 18, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(115,115,115,0.18)" />
                  <XAxis type="number" dataKey="score" name="AICE 置信度" domain={[0, 100]} tick={axisTick} label={{ value: ecosystemMatrix?.x_axis_label || 'AICE 置信度', position: 'insideBottom', offset: -4, fill: axisTick.fill, fontSize: 12 }} />
                  <YAxis type="number" dataKey="frequency" allowDecimals={false} tick={axisTick} label={{ value: ecosystemMatrix?.y_axis_label || '引用频次', angle: -90, position: 'insideLeft', fill: axisTick.fill, fontSize: 12 }} />
                  <ZAxis type="number" dataKey="z" range={[80, 300]} />
                  <ReferenceLine x={matrixConfig?.aice_threshold ?? 75} stroke="rgba(245,158,11,0.8)" strokeDasharray="6 6" />
                  <ReferenceLine y={matrixConfig?.frequency_threshold ?? 1} stroke="rgba(14,165,233,0.8)" strokeDasharray="6 6" />
                  <Tooltip cursor={{ strokeDasharray: '3 3' }} content={<MatrixTooltip />} />
                  <Scatter data={brandPoints} fill={ENTITY_META.brand.fill} />
                  <Scatter data={competitorPoints} fill={ENTITY_META.competitor.fill} />
                  <Scatter data={generalPoints} fill={ENTITY_META.general_knowledge.fill} />
                </ScatterChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center rounded-[20px] border border-dashed border-[var(--border-subtle)] text-[14px] text-[var(--text-tertiary)]">当前还没有足够的来源数据可绘制生态矩阵。</div>
            )}
          </div>
        </Card>
        <div className="space-y-6">
          <Card padding="none" className="rounded-[28px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-2 text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]"><RiFlag2Line className="h-4 w-4" />阵营图例</div>
            <div className="mt-4 space-y-3">
              {(Object.keys(ENTITY_META) as ConfidenceEntityClassification[]).map((key) => {
                const meta = ENTITY_META[key];
                return <div key={key} className="rounded-[18px] border px-4 py-3" style={{ borderColor: 'var(--border-subtle)' }}><div className="flex items-center gap-3"><span className="h-3.5 w-3.5 rounded-full" style={{ backgroundColor: meta.fill }} /><div className="text-[13px] font-medium text-[var(--text-primary)]">{meta.label}</div></div></div>;
              })}
            </div>
          </Card>
          <Card padding="none" className="rounded-[28px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-2 text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]"><RiFocus3Line className="h-4 w-4" />象限释义</div>
            <div className="mt-4 space-y-3">
              {(Object.keys(QUADRANT_META) as ConfidenceQuadrant[]).map((quadrant) => {
                const meta = QUADRANT_META[quadrant];
                const label = meta.label === '定海神针' ? '高频 + 高分' : meta.label === '虚假繁荣' ? '高频 + 低分' : meta.label === '沉寂噪音' ? '低频 + 低分' : '低频 + 高分';
                return <div key={quadrant} className="rounded-[18px] border px-4 py-3" style={{ borderColor: meta.border, backgroundColor: meta.glow }}><div className="text-[13px] font-medium text-[var(--text-primary)]">{meta.short} · {meta.label}</div><div className="mt-1 text-[12px] leading-6 text-[var(--text-secondary)]">{label}</div></div>;
              })}
            </div>
          </Card>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-4">
        {quadrantOverview.map((quadrant) => {
          const meta = getQuadrantMeta(quadrant.quadrant);
          return (
            <Card key={quadrant.quadrant} padding="none" className="rounded-[24px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: meta.border, background: `linear-gradient(180deg, ${meta.glow}, transparent 85%), var(--bg-tertiary)` }}>
              <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">{meta.short}</div>
              <div className="mt-2 text-[18px] font-semibold text-[var(--text-primary)]">{quadrant.quadrant_label || meta.label}</div>
              <div className="mt-2 text-[30px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">{quadrant.count ?? 0}</div>
              <div className="mt-3 text-[13px] leading-7 text-[var(--text-secondary)]">{quadrant.description || meta.label}</div>
              <div className="mt-4 rounded-[18px] bg-[var(--bg-elevated)] px-4 py-3 text-[12px] leading-6 text-[var(--text-secondary)]">我方 {quadrant.entity_breakdown?.brand ?? 0} · 竞方 {quadrant.entity_breakdown?.competitor ?? 0} · 共业 {quadrant.entity_breakdown?.general_knowledge ?? 0}</div>
              {quadrant.strategy ? <div className="mt-3 text-[12px] leading-6 text-[var(--text-tertiary)]">{quadrant.strategy}</div> : null}
            </Card>
          );
        })}
      </section>

      <section className="space-y-6">
        {analysisBlocks.map((block) => (
          <Card key={block.key} padding="none" className="rounded-[28px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-[22px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">{block.title}</div>
                <div className="mt-2 max-w-4xl text-[14px] leading-7 text-[var(--text-secondary)]">{block.description}</div>
              </div>
              <div className="rounded-full bg-[var(--bg-elevated)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)]">{block.item_count ?? block.items?.length ?? 0} 条样本</div>
            </div>
            <div className="mt-5 space-y-4">
              {block.items && block.items.length > 0 ? block.items.map((item) => <DetailItemCard key={item.item_id} item={item} reasonLabel={block.reason_label} actionLabel={block.action_label} />) : (
                <div className="rounded-[18px] border border-dashed px-4 py-8 text-[14px] text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }}>当前这一区块还没有可展示的代表样本。</div>
              )}
            </div>
          </Card>
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Card padding="none" className="rounded-[28px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center gap-2 text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]"><RiShieldCheckLine className="h-4 w-4" />共业阵营观察</div>
          <div className="mt-3 text-[14px] leading-8 text-[var(--text-secondary)]">{generalKnowledgeInsight?.summary || '当前没有足够的共业语料可供进一步分析。'}</div>
        </Card>
        <div className="grid gap-6 lg:grid-cols-2">
          <CompactItemList title="共业高频来源" items={generalKnowledgeInsight?.top_frequency_items ?? []} />
          <CompactItemList title="共业高分来源" items={generalKnowledgeInsight?.top_score_items ?? []} />
        </div>
      </section>

      <section>
        <div className="mb-4 text-[24px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">修我行动清单</div>
        <div className="grid gap-4 xl:grid-cols-4">
          {repairActions.map((action) => (
            <Card key={`${action.priority}_${action.title}`} padding="none" className="rounded-[24px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="text-[12px] tracking-[0.16em] text-[var(--text-tertiary)]">{action.priority}</div>
              <div className="mt-2 text-[18px] font-semibold text-[var(--text-primary)]">{action.title}</div>
              <div className="mt-3 text-[13px] leading-7 text-[var(--text-secondary)]">{action.summary}</div>
              <div className="mt-4 rounded-[16px] bg-[var(--bg-elevated)] px-4 py-3 text-[12px] text-[var(--text-secondary)]">涉及样本 {action.count ?? 0} 条</div>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}

'use client';

import type { ReactNode } from 'react';
import type {
  DashboardCitationDomain,
  DashboardCitationSourceType,
  DashboardEmotionWord,
  DashboardHomeAdvantageCard,
  DashboardHomeData,
  DashboardHomeMetric,
  DashboardMonitoringIssue,
  DashboardHomeRiskCard,
  DashboardLatestReport,
  DashboardMentionRankingRow,
  DashboardPlatformDiagnosisRow,
  DashboardSourceStructure,
} from '@/types/dashboard';
import { DashboardSectionHeader } from './DashboardSectionHeader';
import {
  getUserFacingStageLabel,
  sanitizeUserFacingErrorMessage,
} from '@/lib/workflowStageLabels';

interface DashboardHomeBoardsProps {
  home: DashboardHomeData;
  onOpenLatestReport?: () => void;
  isOpeningLatestReport?: boolean;
  onAskMetric?: (metric: DashboardHomeMetric) => void;
  onOpenIssueChat?: (issue: DashboardMonitoringIssue) => void;
  onRetryIssue?: (issue: DashboardMonitoringIssue) => void;
}

function formatMetricValue(metric: DashboardHomeMetric): string {
  if (metric.value == null) return '--';
  if (metric.format === 'percent') {
    const normalized = metric.value <= 1 ? metric.value * 100 : metric.value;
    return `${normalized.toFixed(1)}%`;
  }
  if (metric.format === 'rank') {
    return `#${Math.round(metric.value)}`;
  }
  return Number.isInteger(metric.value) ? String(metric.value) : metric.value.toFixed(1);
}

function formatPercent(value: number | null): string {
  if (value == null) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function percentWidth(value: number | null): string {
  if (value == null) return '0%';
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.max(5, Math.min(100, normalized))}%`;
}

function SectionBlock({
  title,
  compact = false,
  children,
}: {
  title: string;
  compact?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={`rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] ${compact ? 'px-4 py-4' : 'px-5 py-5'}`}>
      <div className="text-[17px] font-semibold text-[var(--text-primary)]">{title}</div>
      <div className={compact ? 'mt-3' : 'mt-4'}>{children}</div>
    </section>
  );
}

function EmptyInline({ label = '暂无数据' }: { label?: string }) {
  return <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-report-muted)] px-4 py-3 text-[14px] text-[var(--text-tertiary)]">{label}</div>;
}

function MetricStrip({
  metrics,
  onAskMetric,
}: {
  metrics: DashboardHomeMetric[];
  onAskMetric?: (metric: DashboardHomeMetric) => void;
}) {
  if (metrics.length === 0) {
    return <EmptyInline />;
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {metrics.slice(0, 4).map((metric) => (
        <div
          key={metric.id}
          className="rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="text-[13px] text-[var(--text-tertiary)]">{metric.label}</div>
            {onAskMetric ? (
              <button
                type="button"
                onClick={() => onAskMetric(metric)}
                className="shrink-0 rounded-lg border px-2 py-1 text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
                style={{
                  borderColor: 'var(--border-subtle)',
                  background: 'var(--bg-elevated)',
                }}
              >
                让 AI 分析
              </button>
            ) : null}
          </div>
          <div className="mt-2 text-[30px] font-semibold text-[var(--text-primary)]">
            {formatMetricValue(metric)}
          </div>
          {metric.subtitle ? (
            <div className="mt-1 text-[12px] leading-5 text-[var(--text-tertiary)]">
              {metric.subtitle}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function LatestReportScope({ report }: { report?: DashboardLatestReport }) {
  if (!report) return null;

  const facts = [
    report.scope_label ? `指标口径：${report.scope_label}` : null,
    report.question_set_label ? `问题集：${report.question_set_label}` : null,
    report.sample_summary ? `样本：${report.sample_summary}` : null,
  ].filter((item): item is string => Boolean(item));

  if (facts.length === 0 && !report.scope_description && !report.question_preview?.length) {
    return null;
  }

  return (
    <div className="mt-3 border-t border-[var(--border-subtle)] pt-3 text-[13px] leading-6 text-[var(--text-secondary)]">
      {facts.length ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {facts.map((fact) => (
            <span key={fact}>{fact}</span>
          ))}
        </div>
      ) : null}
      {report.scope_description ? (
        <p className="mt-1 text-[var(--text-tertiary)]">{report.scope_description}</p>
      ) : null}
      {report.question_preview?.length ? (
        <div className="mt-1 text-[var(--text-tertiary)]">
          <span className="text-[var(--text-secondary)]">问题样例：</span>
          {report.question_preview.slice(0, 2).join('；')}
        </div>
      ) : null}
    </div>
  );
}

function isUsefulSignalText(text: string): boolean {
  const normalized = text.trim();
  if (!normalized) return false;
  return !['其他', '--', '-', '无', '暂无', '未知'].includes(normalized);
}

function normalizeSignalWords(words: DashboardEmotionWord[], limit: number): DashboardEmotionWord[] {
  const seen = new Set<string>();
  const output: DashboardEmotionWord[] = [];
  for (const word of words) {
    const text = word.text.trim();
    if (!isUsefulSignalText(text) || seen.has(text)) continue;
    seen.add(text);
    output.push(word);
    if (output.length >= limit) break;
  }
  return output;
}

function splitSignalText(value?: string): string[] {
  if (!value) return [];
  return value
    .split(/[、,，/|]/)
    .map((item) => item.trim())
    .filter(isUsefulSignalText);
}

function normalizeRiskEvidence(value?: string): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!isUsefulSignalText(trimmed)) return null;
  if (trimmed === '不提任何品牌') return '未提及品牌';
  return trimmed;
}

function buildRiskMeta(risk: DashboardHomeRiskCard): string[] {
  const meta: string[] = [];
  if (risk.platform?.trim()) {
    meta.push(`AI来源：${risk.platform.trim()}`);
  }

  const evidence = normalizeRiskEvidence(risk.evidence);
  if (!evidence) return meta;
  const evidenceLabel = evidence === '未提及品牌' ? `结果：${evidence}` : `顾虑：${evidence}`;
  meta.push(evidenceLabel);
  return meta;
}

function buildRiskSignals(
  negative: DashboardEmotionWord[],
  risks: DashboardHomeRiskCard[],
): DashboardEmotionWord[] {
  const fromWords = normalizeSignalWords(negative, 8);
  if (fromWords.length >= 4) return fromWords;

  const seen = new Set(fromWords.map((word) => word.text));
  const output = [...fromWords];
  for (const risk of risks) {
    for (const label of splitSignalText(risk.evidence)) {
      if (seen.has(label)) continue;
      seen.add(label);
      output.push({
        text: label,
        weight: 0,
        sentiment: 'negative',
        count: undefined,
      });
      if (output.length >= 8) return output;
    }
  }
  return output;
}

function SignalChip({
  word,
  tone,
}: {
  word: DashboardEmotionWord;
  tone: 'positive' | 'negative';
}) {
  const toneClass =
    tone === 'positive'
      ? 'text-[var(--success)]'
      : 'text-[var(--evidence-risk)]';
  const toneStyle =
    tone === 'positive'
      ? { backgroundColor: 'var(--status-success-bg)' }
      : { backgroundColor: 'var(--status-error-bg)' };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[12px] font-medium ${toneClass}`}
      style={toneStyle}
      title={word.count ? `${word.count} 次` : undefined}
    >
      {word.text}
      {word.count ? <span className="ml-1 opacity-70">{word.count}</span> : null}
    </span>
  );
}

function ThemeSignalColumn({
  title,
  description,
  words,
  tone,
  emptyLabel,
}: {
  title: string;
  description: string;
  words: DashboardEmotionWord[];
  tone: 'positive' | 'negative';
  emptyLabel: string;
}) {
  return (
    <div className="min-h-[150px] rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-report-muted)] px-5 py-4">
      <div className="text-[14px] font-semibold text-[var(--text-primary)]">{title}</div>
      <p className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">{description}</p>
      {words.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] text-[var(--text-tertiary)]">
          {emptyLabel}
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          {words.map((word) => (
            <SignalChip key={`${tone}-${word.text}`} word={word} tone={tone} />
          ))}
        </div>
      )}
    </div>
  );
}

function ThemeSignals({
  positive,
  negative,
  risks,
}: {
  positive: DashboardEmotionWord[];
  negative: DashboardEmotionWord[];
  risks: DashboardHomeRiskCard[];
}) {
  const positiveSignals = normalizeSignalWords(positive, 8);
  const riskSignals = buildRiskSignals(negative, risks);
  const sampleRisk = risks.find((risk) => risk.title);
  const sampleRiskMeta = sampleRisk ? buildRiskMeta(sampleRisk) : [];

  return (
    <SectionBlock title="主题信号">
      <div className="grid gap-3 xl:grid-cols-2">
        <ThemeSignalColumn
          title="正向信号"
          description="AI 回答中用于支持品牌推荐的主要理由。"
          words={positiveSignals}
          tone="positive"
          emptyLabel="本轮没有可展示的正向主题信号。"
        />
        <ThemeSignalColumn
          title="风险顾虑"
          description="会影响决策的提醒，不直接等同于品牌口碑负面。"
          words={riskSignals}
          tone="negative"
          emptyLabel="本轮没有可展示的风险顾虑主题。"
        />
      </div>
      {sampleRisk ? (
        <div className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-report-muted)] px-4 py-3 text-[13px] leading-6 text-[var(--text-secondary)]">
          <div>
            <span className="font-medium text-[var(--text-primary)]">触发问题：</span>
            {sampleRisk.title}
          </div>
          {sampleRiskMeta.length ? (
            <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
              {sampleRiskMeta.join(' · ')}
            </div>
          ) : null}
        </div>
      ) : null}
    </SectionBlock>
  );
}

const PLATFORM_STATUS_LABEL: Record<DashboardPlatformDiagnosisRow['status'], string> = {
  good: '优势',
  watch: '观察',
  risk: '风险',
  unknown: '待观察',
};

function PlatformDiagnosis({ rows }: { rows: DashboardPlatformDiagnosisRow[] }) {
  return (
    <SectionBlock title="平台来源诊断">
      {rows.length === 0 ? (
        <EmptyInline />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] border-separate border-spacing-0 text-left">
            <thead>
              <tr className="text-[12px] text-[var(--text-tertiary)]">
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">平台来源</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">状态</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">回答</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">提及</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">正向</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">负向</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">主要顾虑</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.platform} className="text-[14px] text-[var(--text-primary)]">
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4 font-semibold">{row.platform}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4">
                    <span className="rounded-full bg-[var(--bg-tertiary)] px-2.5 py-1 text-[12px] text-[var(--text-secondary)]">
                      {PLATFORM_STATUS_LABEL[row.status]}
                    </span>
                  </td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4">{row.answer_count}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4">{row.brand_mention_count}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4 text-[var(--success)]">{row.positive_count}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4 text-[var(--evidence-risk)]">{row.negative_count}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4 text-[var(--text-secondary)]">
                    {row.main_concern || '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionBlock>
  );
}

function RiskLevelBadge({ level }: { level: DashboardHomeRiskCard['level'] }) {
  const label = level === 'high' ? '高风险' : level === 'low' ? '低风险' : '需防守';
  return <span className="rounded-full px-2.5 py-1 text-[12px] font-medium text-[var(--evidence-risk)]" style={{ backgroundColor: 'var(--status-error-bg)' }}>{label}</span>;
}

function RiskCards({ risks }: { risks: DashboardHomeRiskCard[] }) {
  return (
    <SectionBlock title="高风险问题" compact>
      {risks.length === 0 ? (
        <EmptyInline />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {risks.slice(0, 4).map((risk) => (
            <div key={`${risk.title}-${risk.platform || ''}`} className="rounded-[20px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="text-[16px] font-semibold text-[var(--text-primary)]">{risk.title}</div>
                <RiskLevelBadge level={risk.level} />
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[13px] text-[var(--text-secondary)]">
                {risk.platform ? <span>{risk.platform}</span> : null}
                {normalizeRiskEvidence(risk.evidence) ? (
                  <span>{normalizeRiskEvidence(risk.evidence)}</span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionBlock>
  );
}

function AdvantageCards({ advantages }: { advantages: DashboardHomeAdvantageCard[] }) {
  return (
    <SectionBlock title="优势场景" compact>
      {advantages.length === 0 ? (
        <EmptyInline />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {advantages.slice(0, 4).map((advantage) => (
            <div key={advantage.title} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-report-muted)] px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="text-[16px] font-semibold text-[var(--text-primary)]">{advantage.title}</div>
                <span className="rounded-full px-2.5 py-1 text-[12px] font-medium text-[var(--success)]" style={{ backgroundColor: 'var(--status-success-bg)' }}>优势</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[13px] text-[var(--text-secondary)]">
                {advantage.platform_count ? <span>{advantage.platform_count} 个来源平台</span> : null}
                {advantage.evidence ? <span>{advantage.evidence}</span> : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionBlock>
  );
}

function MentionRanking({ rows }: { rows: DashboardMentionRankingRow[] }) {
  return (
    <SectionBlock title="提及率排行">
      {rows.length === 0 ? (
        <EmptyInline label="暂无排行" />
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 10).map((row) => (
            <div
              key={`${row.rank}-${row.brand}`}
              className={`grid grid-cols-[42px_minmax(0,1fr)_84px_72px] items-center gap-3 rounded-[16px] px-3 py-3 text-[14px] ${
                row.is_current_brand ? 'bg-[var(--brand-bg)] text-[var(--text-primary)]' : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
              }`}
            >
              <div className="font-semibold text-[var(--text-primary)]">#{row.rank}</div>
              <div className="truncate font-medium text-[var(--text-primary)]">{row.brand}</div>
              <div className="text-right font-semibold text-[var(--text-primary)]">{formatPercent(row.mention_rate)}</div>
              <div className="text-right text-[12px] text-[var(--text-tertiary)]">{row.mention_count} 次</div>
            </div>
          ))}
        </div>
      )}
    </SectionBlock>
  );
}

function SourceTypeList({ items }: { items: DashboardCitationSourceType[] }) {
  if (items.length === 0) {
    return <EmptyInline />;
  }

  return (
    <ul className="space-y-3">
      {items.slice(0, 5).map((item) => (
        <li key={item.key} className="space-y-1.5">
          <div className="flex items-center justify-between gap-3 text-[14px]">
            <span className="text-[var(--text-primary)]">{item.label}</span>
            <span className="font-medium text-[var(--text-primary)]">{formatPercent(item.share)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
            <div className="h-full rounded-full bg-[var(--brand-primary)]" style={{ width: percentWidth(item.share) }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function TopDomainList({ items }: { items: DashboardCitationDomain[] }) {
  if (items.length === 0) {
    return <EmptyInline />;
  }

  return (
    <ul className="space-y-3">
      {items.slice(0, 5).map((item) => (
        <li key={`${item.domain}-${item.display_name}`} className="rounded-[16px] bg-[var(--bg-tertiary)] px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-[14px] font-medium text-[var(--text-primary)]">{item.display_name}</div>
              <div className="mt-1 truncate text-[12px] text-[var(--text-tertiary)]">{item.domain}</div>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-[14px] font-semibold text-[var(--text-primary)]">{item.count} 次</div>
              <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">{formatPercent(item.share)}</div>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function resolveSourceStructure(home: DashboardHomeData): DashboardSourceStructure {
  const sourceStructure = home.source_structure;
  const hasSourceStructure = Boolean(
    sourceStructure
      && (sourceStructure.official_conversion_rate != null
        || sourceStructure.source_types.length > 0
        || sourceStructure.top_domains.length > 0),
  );

  if (hasSourceStructure && sourceStructure) {
    return sourceStructure;
  }

  return {
    official_conversion_rate: null,
    source_types: home.citation_distribution?.source_types || [],
    top_domains: home.citation_distribution?.top_domains || [],
  };
}

function SourceStructure({ source }: { source: DashboardSourceStructure }) {
  return (
    <SectionBlock title="信源结构">
      <div className="grid gap-5 xl:grid-cols-[0.75fr_1fr_1fr]">
        <div className="rounded-[18px] bg-[var(--bg-tertiary)] px-4 py-4">
          <div className="text-[13px] text-[var(--text-tertiary)]">官网转化率</div>
          <div className="mt-3 text-[32px] font-semibold text-[var(--text-primary)]">
            {formatPercent(source.official_conversion_rate)}
          </div>
        </div>
        <div>
          <div className="mb-3 text-[13px] font-medium text-[var(--text-tertiary)]">来源分布</div>
          <SourceTypeList items={source.source_types} />
        </div>
        <div>
          <div className="mb-3 text-[13px] font-medium text-[var(--text-tertiary)]">主要站点</div>
          <TopDomainList items={source.top_domains} />
        </div>
      </div>
    </SectionBlock>
  );
}

function MonitoringIssueBanner({
  issue,
  onOpenChat,
  onRetry,
}: {
  issue?: DashboardMonitoringIssue;
  onOpenChat?: (issue: DashboardMonitoringIssue) => void;
  onRetry?: (issue: DashboardMonitoringIssue) => void;
}) {
  if (!issue) return null;
  const sourceLabel = issue.endpoint_labels.join('、') || '平台来源待确认';
  const stageLabel = getUserFacingStageLabel(issue.error_stage) || '自动监测';
  const errorMessage = sanitizeUserFacingErrorMessage(
    issue.error_message,
    '本次自动监测没有生成可用于看板展示的报告。'
  );
  return (
    <div
      className="rounded-[16px] border px-5 py-4"
      style={{
        background: 'var(--status-error-bg)',
        borderColor: 'color-mix(in srgb, var(--evidence-risk) 22%, var(--border-subtle) 78%)',
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[12px] font-semibold text-[var(--evidence-risk)]">监测异常</div>
          <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">
            {issue.title}
          </div>
          <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
            处理环节：{stageLabel} · {issue.question_count} 个问题 · {sourceLabel}
          </p>
          {errorMessage && (
            <p className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">
              {errorMessage}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onOpenChat?.(issue)}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2 text-[13px] font-medium text-[var(--text-primary)]"
          >
            对话处理
          </button>
          <button
            type="button"
            onClick={() => onRetry?.(issue)}
            className="rounded-lg bg-[var(--brand-primary)] px-4 py-2 text-[13px] font-medium text-[var(--brand-contrast)]"
          >
            重新触发快速复测
          </button>
        </div>
      </div>
    </div>
  );
}

export function DashboardHomeBoards({
  home,
  onOpenLatestReport,
  isOpeningLatestReport = false,
  onAskMetric,
  onOpenIssueChat,
  onRetryIssue,
}: DashboardHomeBoardsProps) {
  const metrics = home.metrics || [];
  const latestReport = home.latest_report;
  const sourceStructure = resolveSourceStructure(home);
  const wordCloud = home.word_cloud || { positive: [], negative: [] };

  return (
    <section className="dashboard-shell rounded-[18px] px-6 py-6">
      <DashboardSectionHeader
        title="周期监测结果"
        action={latestReport?.created_at ? (
          <div className="text-right">
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">最近更新</div>
            <div className="mt-1 text-[13px] text-[var(--text-secondary)]">
              {new Date(latestReport.created_at).toLocaleString('zh-CN', { hour12: false })}
            </div>
          </div>
        ) : undefined}
      />

      <div className="space-y-4 rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-5">
        <MonitoringIssueBanner
          issue={home.recent_issue}
          onOpenChat={onOpenIssueChat}
          onRetry={onRetryIssue}
        />

        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">
              最新诊断报告
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h2 className="text-[28px] font-semibold text-[var(--text-primary)]">
                {latestReport?.title || '暂无最新报告'}
              </h2>
              {latestReport?.badge_label ? (
                  <span className="inline-flex items-center rounded-full bg-[var(--bg-tertiary)] px-2.5 py-1 text-[12px] font-medium text-[var(--brand-primary)]">
                  {latestReport.badge_label}
                </span>
              ) : null}
            </div>
            <LatestReportScope report={latestReport} />
          </div>

          {onOpenLatestReport && latestReport?.session_id ? (
            <button
              type="button"
              onClick={onOpenLatestReport}
              disabled={isOpeningLatestReport}
              aria-busy={isOpeningLatestReport}
              className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2 text-[13px] font-medium text-[var(--text-primary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)] disabled:cursor-wait disabled:opacity-70"
            >
              {isOpeningLatestReport ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : null}
              {isOpeningLatestReport ? '打开中' : latestReport.action_label || '打开报告'}
            </button>
          ) : null}
        </div>

        <MetricStrip metrics={metrics} onAskMetric={onAskMetric} />
        <ThemeSignals
          positive={wordCloud.positive}
          negative={wordCloud.negative}
          risks={home.risks || []}
        />
        <PlatformDiagnosis rows={home.platform_diagnosis || []} />
        <RiskCards risks={home.risks || []} />
        <AdvantageCards advantages={home.advantages || []} />
        <MentionRanking rows={home.mention_ranking || []} />
        <SourceStructure source={sourceStructure} />
      </div>
    </section>
  );
}

'use client';

import dynamic from 'next/dynamic';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type MutableRefObject,
  type ReactNode,
} from 'react';
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  BarChart3,
  CheckCircle2,
  ExternalLink,
  FileText,
  LineChart,
  MessageSquareText,
  Network,
  SearchCheck,
  Settings,
  ShieldCheck,
} from 'lucide-react';
import type { ForceGraphMethods } from 'react-force-graph-3d';
import { AdditiveBlending, CanvasTexture, Group, Sprite, SpriteMaterial, type Object3D } from 'three';

import { useOntologyStore } from '@/stores/ontologyStore';
import type { DashboardHomeData } from '@/types/dashboard';
import type {
  OntologyAnswerEvidenceSample,
  OntologyEvidenceProjection,
  OntologyExternalDomainRow,
  OntologyGraphNode,
  OntologyGraphProjection,
  OntologyMetricProjection,
  OntologyRecommendationProjection,
  OntologyPlatformMetricRow,
  OntologyRecommendationItem,
  OntologySummaryProjection,
} from '@/types/ontology';

interface BrandOntologyHomeProps {
  entityId: string;
  brandName?: string;
  brandDomain?: string;
  brandIndustry?: string;
  brandUpdatedAt?: string | null;
  dashboardHome?: DashboardHomeData | null;
  hasLatestReport?: boolean;
  onOpenLatestReport?: () => void;
  onAskIntelligence?: (
    prompt: string,
    handoff?: { taskTitle?: string; taskGoal?: string },
    options?: { autosend?: boolean },
  ) => void;
  onOpenMonitoringSettings?: (context?: {
    recommendationId?: string;
    targetMetric?: string;
    contentFormat?: string;
  }) => void;
  isAskingIntelligence?: boolean;
}

type MainTab = 'brief' | 'evidence' | 'world' | 'recommendations';
type EvidenceTab = 'mention_rate' | 'mention_ranking' | 'official_citation_rate' | 'sentiment_distribution';
type BrandWorldViewMode = 'map' | 'galaxy';

type GalaxyGraphNode = {
  id: string;
  label: string;
  type: string;
  group: string;
  kind: string;
  level: number;
  selected: boolean;
  value?: string | null;
  summary?: string;
  color: string;
  val: number;
  x?: number;
  y?: number;
  z?: number;
  fx?: number;
  fy?: number;
  fz?: number;
};

type GalaxyGraphLink = {
  source: string;
  target: string;
  label: string;
  color: string;
  width: number;
};

type GalaxyGraphData = {
  nodes: GalaxyGraphNode[];
  links: GalaxyGraphLink[];
  limited?: boolean;
};

type ForceGraph3DProps = {
  ref?: MutableRefObject<ForceGraphMethods<GalaxyGraphNode, GalaxyGraphLink> | undefined>;
  graphData?: GalaxyGraphData;
  width?: number;
  height?: number;
  backgroundColor?: string;
  showNavInfo?: boolean;
  nodeId?: string;
  nodeVal?: string | ((node: GalaxyGraphNode) => number);
  nodeLabel?: string | ((node: GalaxyGraphNode) => string);
  nodeColor?: string | ((node: GalaxyGraphNode) => string);
  nodeResolution?: number;
  nodeThreeObject?: (node: GalaxyGraphNode) => Object3D;
  nodeThreeObjectExtend?: boolean;
  linkSource?: string;
  linkTarget?: string;
  linkLabel?: string | ((link: GalaxyGraphLink) => string);
  linkColor?: string | ((link: GalaxyGraphLink) => string);
  linkWidth?: string | ((link: GalaxyGraphLink) => number);
  linkOpacity?: number;
  linkDirectionalArrowLength?: number;
  linkDirectionalArrowRelPos?: number;
  linkDirectionalParticles?: number;
  warmupTicks?: number;
  cooldownTicks?: number;
  cooldownTime?: number;
  d3VelocityDecay?: number;
  enableNodeDrag?: boolean;
  enableNavigationControls?: boolean;
  showPointerCursor?: boolean | ((obj: GalaxyGraphNode | GalaxyGraphLink | undefined) => boolean);
  onNodeClick?: (node: GalaxyGraphNode, event: MouseEvent) => void;
  onEngineStop?: () => void;
};

const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center">
      <EmptyLine text="正在加载立体图谱。" />
    </div>
  ),
}) as ComponentType<ForceGraph3DProps>;

const MAIN_TABS: Array<{
  key: MainTab;
  label: string;
  sublabel: string;
  icon: ReactNode;
}> = [
  { key: 'brief', label: '简要情报', sublabel: '提及、排名、官网、语气', icon: <BarChart3 size={18} /> },
  { key: 'evidence', label: '情报来源', sublabel: '指标证据', icon: <ShieldCheck size={18} /> },
  { key: 'world', label: '品牌世界', sublabel: '关系图', icon: <Network size={18} /> },
  { key: 'recommendations', label: '跟进反馈', sublabel: '内容投放', icon: <CheckCircle2 size={18} /> },
];

const EVIDENCE_TABS: Array<{ key: EvidenceTab; label: string }> = [
  { key: 'mention_rate', label: '提及率' },
  { key: 'mention_ranking', label: '提及排名' },
  { key: 'official_citation_rate', label: '官网引用率' },
  { key: 'sentiment_distribution', label: '语气性质' },
];

export function BrandOntologyHome({
  entityId,
  brandName,
  brandDomain,
  brandIndustry,
  brandUpdatedAt,
  dashboardHome,
  hasLatestReport,
  onOpenLatestReport,
  onAskIntelligence,
  onOpenMonitoringSettings,
  isAskingIntelligence,
}: BrandOntologyHomeProps) {
  const [activeTab, setActiveTab] = useState<MainTab>('brief');
  const [activeEvidenceMetric, setActiveEvidenceMetric] = useState<EvidenceTab>('mention_rate');
  const { worldsByEntity, loadingByEntity, errorByEntity, fetchWorld } = useOntologyStore();

  useEffect(() => {
    if (!entityId) return;
    void fetchWorld(entityId);
  }, [entityId, fetchWorld]);

  const world = worldsByEntity[entityId];
  const loading = Boolean(loadingByEntity[entityId]);
  const error = errorByEntity[entityId];
  const fallbackSummary = useMemo(
    () =>
      buildFallbackSummary({
        brandName,
        brandDomain,
        brandIndustry,
        dashboardHome,
      }),
    [brandDomain, brandIndustry, brandName, dashboardHome],
  );
  const hasWorld = Boolean(world?.summary_projection);
  const summary = world?.summary_projection || fallbackSummary;
  const evidence = world?.evidence_projection;
  const graph = world?.graph_projection;
  const recommendations = world?.recommendation_projection?.recommendations || [];

  const openEvidence = (metricKey: EvidenceTab) => {
    setActiveEvidenceMetric(metricKey);
    setActiveTab('evidence');
    window.setTimeout(() => {
      document.getElementById(`evidence-${metricKey}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }, 50);
  };

  const explainMetric = (metricKey: EvidenceTab) => {
    const metricLabel = metricLabelFor(metricKey);
    onAskIntelligence?.(
      `请分析${summary.brand?.name || brandName || '当前品牌'}的${metricLabel}。按结论、证据、影响、需要确认什么、下一步建议回答。`,
    );
  };
  const continueAnswerSampling = () => {
    const name = summary.brand?.name || brandName || '当前品牌';
    const scope = summary.sample_scope || {};
    const hasQuestions = Number(scope.question_count ?? 0) > 0;
    onAskIntelligence?.(
      hasQuestions
        ? `请基于当前品牌已生成的问题列表，继续抓取「${name}」在 AI 平台里的回答，并完成品牌情报分析。重点输出 AI 提及率、提及排名、官网引用率和语气性质。`
        : `请为「${name}」生成品牌情报问题，继续抓取 AI 平台里的回答，并完成品牌情报分析。重点输出 AI 提及率、提及排名、官网引用率和语气性质。`,
      {
        taskTitle: hasQuestions ? '继续抓取 AI 回答' : '开始品牌情报分析',
        taskGoal: hasQuestions
          ? '补齐答案样本，生成可用于判断的品牌情报。'
          : '生成问题并补齐答案样本，形成可用于判断的品牌情报。',
      },
      { autosend: true },
    );
  };

  if (!hasWorld) {
    return (
      <section className="space-y-5">
        <HeaderBand
          summary={summary}
          brandName={brandName}
          brandDomain={brandDomain}
          brandIndustry={brandIndustry}
          brandUpdatedAt={brandUpdatedAt}
          loading={loading}
          error={error}
          metricsReady={false}
        />
        {loading ? (
          <BrandIntelligenceLoading />
        ) : (
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-10">
            <EmptyLine text={error ? '品牌情报读取失败，可稍后重试。' : '暂无可展示的品牌情报。'} />
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="space-y-5">
      <HeaderBand
        summary={summary}
        brandName={brandName}
        brandDomain={brandDomain}
        brandIndustry={brandIndustry}
        brandUpdatedAt={brandUpdatedAt}
        loading={loading}
        error={error}
        metricsReady={hasWorld}
      />

      <MobileMetricStrip summary={summary} onOpenEvidence={openEvidence} />

      <nav className="grid grid-cols-4 gap-2 md:gap-3" aria-label="品牌情报视图">
        {MAIN_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`flex min-h-[58px] flex-col items-center justify-center gap-1 rounded-xl border px-2 py-2 text-center transition md:min-h-[72px] md:flex-row md:justify-start md:gap-3 md:px-4 md:text-left ${
              activeTab === tab.key
                ? 'border-[var(--brand-primary)] bg-[var(--brand-soft)] text-[var(--brand-primary)]'
                : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:border-[var(--brand-border)]'
            }`}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-current/20 md:h-9 md:w-9">
              {tab.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-[12px] font-semibold leading-4 md:text-sm">{tab.label}</span>
              <span className="mt-0.5 hidden text-xs opacity-70 md:block">{tab.sublabel}</span>
            </span>
          </button>
        ))}
      </nav>

      {activeTab === 'brief' && (
        <BriefPanel
          summary={summary}
          hasLatestReport={hasLatestReport}
          onOpenLatestReport={onOpenLatestReport}
          onOpenEvidence={openEvidence}
          onAskMetric={explainMetric}
          onContinueAnalysis={continueAnswerSampling}
          isAskingIntelligence={isAskingIntelligence}
        />
      )}

      {activeTab === 'evidence' && (
        <EvidencePanel
          evidence={evidence}
          summary={summary}
          activeMetric={activeEvidenceMetric}
          onActiveMetricChange={setActiveEvidenceMetric}
          onOpenBrief={() => setActiveTab('brief')}
          onAskMetric={explainMetric}
          isAskingIntelligence={isAskingIntelligence}
        />
      )}

      {activeTab === 'world' && (
        <BrandWorldPanel
          graph={graph}
          summary={summary}
          onAskNode={(node) => {
            onAskIntelligence?.(
              `请分析${summary.brand?.name || brandName || '当前品牌'}和「${node.label}」的关系。按结论、证据、影响、需要确认什么、下一步建议回答。`,
            );
          }}
          onOpenEvidence={(metricKey) => openEvidence(metricKey)}
          onOpenRecommendations={() => setActiveTab('recommendations')}
          isAskingIntelligence={isAskingIntelligence}
        />
      )}

      {activeTab === 'recommendations' && (
        <RecommendationPanel
          entityId={entityId}
          recommendations={recommendations}
          summary={summary}
          sampleStatus={world?.recommendation_projection?.sample_status}
          onAsk={(item) => {
            onAskIntelligence?.(
              buildRecommendationChatRequest(item, summary),
              {
                taskTitle: item.title,
                taskGoal: buildRecommendationHandoffGoal(item),
              },
            );
          }}
          onContinueAnalysis={continueAnswerSampling}
          onOpenMonitoringSettings={onOpenMonitoringSettings}
          isAskingIntelligence={isAskingIntelligence}
        />
      )}
    </section>
  );
}

function HeaderBand({
  summary,
  brandName,
  brandDomain,
  brandIndustry,
  brandUpdatedAt,
  loading,
  error,
  metricsReady,
}: {
  summary: OntologySummaryProjection;
  brandName?: string;
  brandDomain?: string;
  brandIndustry?: string;
  brandUpdatedAt?: string | null;
  loading: boolean;
  error?: string | null;
  metricsReady: boolean;
}) {
  const scope = summary.sample_scope || {};
  return (
    <div className="border-b border-[var(--border-subtle)] pb-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-medium text-[var(--brand-primary)]">品牌情报</p>
          <h2 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
            {summary.brand?.name || brandName || '当前品牌'}
          </h2>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-[var(--text-secondary)]">
            <span>{summary.brand?.domain || brandDomain || '官网待补充'}</span>
            <span>{summary.brand?.industry || brandIndustry || '行业待补充'}</span>
            {brandUpdatedAt && <span>更新 {formatDate(brandUpdatedAt)}</span>}
          </div>
        </div>
        <div className="grid grid-cols-4 gap-1.5 text-sm md:gap-3">
          <ScopeItem label="平台" value={metricsReady ? scope.platform_count ?? 0 : '读取中'} />
          <ScopeItem label="问题" value={metricsReady ? scope.question_count ?? 0 : '读取中'} />
          <ScopeItem label="回答" value={metricsReady ? scope.answer_count ?? 0 : '读取中'} />
          <ScopeItem label="引用" value={metricsReady ? scope.citation_count ?? 0 : '读取中'} />
        </div>
      </div>
      {loading && <p className="mt-3 text-sm text-[var(--text-secondary)]">正在读取品牌情报。</p>}
      {error && <p className="mt-3 text-sm text-[var(--error)]">{error}</p>}
    </div>
  );
}

function ScopeItem({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1.5 md:min-w-[86px] md:px-3 md:py-2">
      <div className="text-xs text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)] md:mt-1 md:text-base">{value}</div>
    </div>
  );
}

function BrandIntelligenceLoading() {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-5">
      <div className="h-4 w-24 rounded bg-[var(--bg-secondary)]" />
      <div className="mt-5 space-y-5">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="grid gap-4 lg:grid-cols-[52px_1fr_150px] lg:items-center">
            <div className="h-7 w-7 rounded-full bg-[var(--bg-secondary)]" />
            <div className="space-y-3">
              <div className="h-5 w-48 rounded bg-[var(--bg-secondary)]" />
              <div className="h-3 max-w-2xl rounded bg-[var(--bg-secondary)]" />
              <div className="h-3 w-64 rounded bg-[var(--bg-secondary)]" />
            </div>
            <div className="h-9 rounded-lg bg-[var(--bg-secondary)]" />
          </div>
        ))}
      </div>
    </div>
  );
}

function SampleNeededBanner({
  summary,
  onContinueAnalysis,
  disabled,
}: {
  summary: OntologySummaryProjection;
  onContinueAnalysis: () => void;
  disabled?: boolean;
}) {
  const scope = summary.sample_scope || {};
  const hasQuestions = Number(scope.question_count ?? 0) > 0;
  return (
    <div className="border-b border-[var(--border-subtle)] px-5 py-4">
      <div className="flex flex-col gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            {hasQuestions ? '需要先抓取 AI 回答' : '需要先生成问题'}
          </div>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {hasQuestions
              ? `当前有 ${scope.question_count ?? 0} 个问题，暂无可分析的答案样本。抓取完成后再计算提及率、排名、官网引用率和语气性质。`
              : '当前还没有可用于采集的问题。先生成问题并抓取答案，再计算提及率、排名、官网引用率和语气性质。'}
          </p>
        </div>
        <button
          type="button"
          disabled={disabled}
          onClick={onContinueAnalysis}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--brand-primary)] px-4 py-2 text-sm font-medium text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-50"
        >
          <MessageSquareText size={16} />
          {hasQuestions ? '继续抓取答案' : '开始分析'}
        </button>
      </div>
    </div>
  );
}

function MobileMetricStrip({
  summary,
  onOpenEvidence,
}: {
  summary: OntologySummaryProjection;
  onOpenEvidence: (metricKey: EvidenceTab) => void;
}) {
  const metrics = summary.metrics || {};
  const tiles = [
    buildMetricTile('mention_rate', metrics.mention_rate),
    buildMetricTile('mention_ranking', metrics.mention_ranking),
    buildMetricTile('official_citation_rate', metrics.official_citation_rate),
    buildMetricTile('sentiment_distribution', metrics.sentiment_distribution),
  ];

  return (
    <div className="grid grid-cols-2 gap-2 lg:hidden">
      {tiles.map((tile) => (
        <button
          key={tile.key}
          type="button"
          onClick={() => onOpenEvidence(tile.key)}
          className="min-h-[76px] rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-left"
        >
          <div className="text-[11px] leading-4 text-[var(--text-tertiary)]">{tile.label}</div>
          <div className="mt-1 truncate text-[17px] font-semibold text-[var(--text-primary)]">{tile.value}</div>
          <div className="mt-1 truncate text-[11px] text-[var(--text-secondary)]">{tile.evidence}</div>
        </button>
      ))}
    </div>
  );
}

function BriefPanel({
  summary,
  hasLatestReport,
  onOpenLatestReport,
  onOpenEvidence,
  onAskMetric,
  onContinueAnalysis,
  isAskingIntelligence,
}: {
  summary: OntologySummaryProjection;
  hasLatestReport?: boolean;
  onOpenLatestReport?: () => void;
  onOpenEvidence: (metricKey: EvidenceTab) => void;
  onAskMetric: (metricKey: EvidenceTab) => void;
  onContinueAnalysis: () => void;
  isAskingIntelligence?: boolean;
}) {
  const metrics = summary.metrics || {};
  const needsSampling = needsAnswerSampling(summary);
  const metricRows = [
    buildMetricRow('mention_rate', metrics.mention_rate),
    buildMetricRow('mention_ranking', metrics.mention_ranking),
    buildMetricRow('official_citation_rate', metrics.official_citation_rate),
    buildMetricRow('sentiment_distribution', metrics.sentiment_distribution),
  ];

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
      <div className="border-b border-[var(--border-subtle)] px-5 py-4">
        <h3 className="text-base font-semibold text-[var(--text-primary)]">简要情报</h3>
      </div>
      {needsSampling && (
        <SampleNeededBanner
          summary={summary}
          onContinueAnalysis={onContinueAnalysis}
          disabled={isAskingIntelligence}
        />
      )}
      <div className="divide-y divide-[var(--border-subtle)]">
        {metricRows.map((row, index) => (
          <div key={row.key} className="grid gap-4 px-5 py-5 lg:grid-cols-[52px_1fr_auto] lg:items-center">
            <div className="text-sm text-[var(--text-tertiary)]">{String(index + 1).padStart(2, '0')}</div>
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--brand-soft)] text-[var(--brand-primary)]">
                  {row.icon}
                </span>
                <h4 className="text-lg font-semibold text-[var(--text-primary)]">{row.title}</h4>
              </div>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">{row.body}</p>
              <p className="mt-2 text-xs text-[var(--text-tertiary)]">{row.evidence}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onOpenEvidence(row.key)}
                className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)]"
              >
                查看来源
              </button>
              <button
                type="button"
                disabled={isAskingIntelligence}
                onClick={() => onAskMetric(row.key)}
                className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)] disabled:opacity-50"
              >
                解释指标
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-3 border-t border-[var(--border-subtle)] px-5 py-4 md:flex-row md:items-center md:justify-between">
        <div className="grid gap-3 md:grid-cols-2">
          <Judgment label="机会" item={summary.top_opportunity} />
          <Judgment label="风险" item={summary.top_risk} />
        </div>
        <button
          type="button"
          disabled={!hasLatestReport || !onOpenLatestReport}
          onClick={onOpenLatestReport}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <FileText size={16} />
          查看报告
        </button>
      </div>
    </div>
  );
}

function EvidencePanel({
  evidence,
  summary,
  activeMetric,
  onActiveMetricChange,
  onOpenBrief,
  onAskMetric,
  isAskingIntelligence,
}: {
  evidence?: OntologyEvidenceProjection;
  summary: OntologySummaryProjection;
  activeMetric: EvidenceTab;
  onActiveMetricChange: (metric: EvidenceTab) => void;
  onOpenBrief: () => void;
  onAskMetric: (metricKey: EvidenceTab) => void;
  isAskingIntelligence?: boolean;
}) {
  const [platformFilter, setPlatformFilter] = useState('all');
  const platforms = useMemo(() => evidencePlatforms(evidence), [evidence]);
  const filteredEvidence = useMemo(
    () => filterEvidenceByPlatform(evidence, platformFilter),
    [evidence, platformFilter],
  );

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
      <div className="flex flex-col gap-3 border-b border-[var(--border-subtle)] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <h3 className="text-base font-semibold text-[var(--text-primary)]">情报来源</h3>
        <div className="flex flex-wrap gap-2">
          {EVIDENCE_TABS.map((tab) => (
            <button
              id={`evidence-${tab.key}`}
              key={tab.key}
              type="button"
              onClick={() => onActiveMetricChange(tab.key)}
              className={`rounded-lg border px-3 py-2 text-sm ${
                activeMetric === tab.key
                  ? 'border-[var(--brand-primary)] bg-[var(--brand-soft)] text-[var(--brand-primary)]'
                  : 'border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--brand-border)]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border-subtle)] px-5 py-3">
        <span className="text-xs text-[var(--text-tertiary)]">平台</span>
        <select
          value={platformFilter}
          onChange={(event) => setPlatformFilter(event.target.value)}
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-secondary)] outline-none focus:border-[var(--brand-border)]"
        >
          <option value="all">全部平台</option>
          {platforms.map((platform) => (
            <option key={platform} value={platform}>
              {platformLabel(platform)}
            </option>
          ))}
        </select>
        <span className="text-xs text-[var(--text-tertiary)]">异常样本可在代表性证据里标记复核</span>
      </div>
      <div className="p-5">
        {activeMetric === 'mention_rate' && (
          <MentionRateDetail
            detail={filteredEvidence?.mention_rate_detail}
            metric={summary.metrics?.mention_rate}
          />
        )}
        {activeMetric === 'mention_ranking' && (
          <RankingDetail detail={filteredEvidence?.ranking_detail} />
        )}
        {activeMetric === 'official_citation_rate' && (
          <OfficialCitationDetail detail={filteredEvidence?.official_citation_detail} />
        )}
        {activeMetric === 'sentiment_distribution' && (
          <SentimentDetail detail={filteredEvidence?.sentiment_detail} />
        )}
      </div>
      <div className="border-t border-[var(--border-subtle)] px-5 py-4">
        <button
          type="button"
          onClick={onOpenBrief}
          className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)]"
        >
          回到简要情报
        </button>
        <button
          type="button"
          disabled={isAskingIntelligence}
          onClick={() => onAskMetric(activeMetric)}
          className="inline-flex items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-4 py-2 text-sm font-medium text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-50"
        >
          <MessageSquareText size={16} />
          解释这个指标
        </button>
      </div>
    </div>
  );
}

function MentionRateDetail({
  detail,
  metric,
}: {
  detail?: NonNullable<OntologyEvidenceProjection['mention_rate_detail']>;
  metric?: OntologyMetricProjection;
}) {
  const platformRows = detail?.platform_rows || [];
  const samples = detail?.answer_samples || [];
  const unmentionedSamples = detail?.unmentioned_answer_samples || [];
  const mentionCount = detail?.numerator ?? metric?.numerator;
  const answerCount = detail?.denominator ?? metric?.denominator;
  const unmentionedCount =
    detail?.unmentioned_count ??
    (typeof answerCount === 'number' && typeof mentionCount === 'number'
      ? Math.max(answerCount - mentionCount, 0)
      : undefined);
  const unreadableUnmentionedCount = detail?.unmentioned_unreadable_count ?? 0;
  const excludedUnreadableCount = detail?.excluded_unreadable_answer_count ?? 0;
  return (
    <div className="space-y-5">
      <MetricFormula
        title="AI 提及率"
        value={metric?.display_value || percent(detail?.value)}
        formula={
          typeof mentionCount === 'number' && typeof answerCount === 'number'
            ? `${mentionCount} 条提及 / ${answerCount} 条答案样本；${unmentionedCount ?? 0} 条未提及`
            : '当前样本不足，无法计算提及率。'
        }
      />
      {excludedUnreadableCount > 0 && (
        <p className="text-sm leading-6 text-[var(--text-tertiary)]">
          {excludedUnreadableCount} 条采集结果缺少回答正文，未计入本页指标。
        </p>
      )}
      <PlatformTable rows={platformRows} />
      <AnswerSampleList
        title="提及答案样本"
        emptyText="当前还没有提及答案样本。"
        samples={samples}
      />
      <AnswerSampleList
        title="未提及答案样本"
        emptyText={
          unreadableUnmentionedCount > 0
            ? `${unreadableUnmentionedCount} 条未提及结果缺少回答正文，无法查看答案摘录。`
            : '当前没有未提及答案样本。'
        }
        samples={unmentionedSamples}
      />
    </div>
  );
}

function RankingDetail({
  detail,
}: {
  detail?: NonNullable<OntologyEvidenceProjection['ranking_detail']>;
}) {
  const rows = detail?.brands || [];
  return (
    <div className="space-y-5">
      <MetricFormula
        title="提及排名"
        value={detail?.display_rank ? `第 ${detail.display_rank} / ${detail.total || rows.length}` : '排名未形成'}
        formula={detail?.sample_sufficiency?.rank_reason || '同一批问题和平台下，按品牌提及率排序。'}
      />
      <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
        <table className="w-full min-w-[620px] text-sm">
          <thead className="bg-[var(--bg-secondary)] text-left text-[var(--text-tertiary)]">
            <tr>
              <th className="px-4 py-3 font-medium">排名</th>
              <th className="px-4 py-3 font-medium">品牌</th>
              <th className="px-4 py-3 font-medium">提及率</th>
              <th className="px-4 py-3 font-medium">提及回答</th>
              <th className="px-4 py-3 font-medium">样本</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-subtle)]">
            {rows.map((row) => (
              <tr key={row.brand_id} className={row.is_current_brand ? 'bg-[var(--brand-soft)]/60' : ''}>
                <td className="px-4 py-3 text-[var(--text-primary)]">
                  {detail?.sample_sufficiency?.is_comparable ? row.rank : '-'}
                </td>
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{row.brand_name}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{percent(row.mention_rate)}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{row.mention_count}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{row.sample_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && <EmptyLine text="当前还没有可比较的竞品样本。" />}
      {rows.length > 0 && !detail?.sample_sufficiency?.is_comparable && (
        <EmptyLine text={detail?.sample_sufficiency?.rank_status_label || '竞品样本不足，排名暂未形成。'} />
      )}
    </div>
  );
}

function OfficialCitationDetail({
  detail,
}: {
  detail?: NonNullable<OntologyEvidenceProjection['official_citation_detail']>;
}) {
  return (
    <div className="space-y-5">
      <MetricFormula
        title="官网引用率"
        value={percent(detail?.value)}
        formula={
          typeof detail?.official_citation_count === 'number' && typeof detail?.total_citation_count === 'number'
            ? `${detail.official_citation_count} 次官网引用 / ${detail.total_citation_count} 次全部引用`
            : '当前样本不足，无法计算官网引用率。'
        }
      />
      {(detail?.official_domains || []).length ? (
        <p className="text-sm leading-6 text-[var(--text-secondary)]">
          已计入官网域名：{(detail?.official_domains || []).join('、')}
        </p>
      ) : null}
      <div>
        <h4 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">外部来源</h4>
        <DomainList rows={detail?.top_external_domains || []} />
      </div>
      <div>
        <h4 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">官网样本</h4>
        {(detail?.official_samples || []).length ? (
          <div className="space-y-3">
            {(detail?.official_samples || []).map((sample) => (
              <EvidenceSourceItem key={sample.citation_id || sample.url} sample={sample} />
            ))}
          </div>
        ) : (
          <EmptyLine text={`官网 ${detail?.official_domain || '域名'} 暂未进入当前引用样本。`} />
        )}
      </div>
    </div>
  );
}

function SentimentDetail({
  detail,
}: {
  detail?: NonNullable<OntologyEvidenceProjection['sentiment_detail']>;
}) {
  const summary = detail?.summary || {};
  return (
    <div className="space-y-5">
      <MetricFormula
        title="语气性质"
        value={`${summary.positive ?? 0} 正向 / ${summary.neutral ?? 0} 中性 / ${summary.negative ?? 0} 负向`}
        formula="只统计已经提及当前品牌的回答。"
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <SentimentColumn title="正向" samples={detail?.positive || []} />
        <SentimentColumn title="中性" samples={detail?.neutral || []} />
        <SentimentColumn title="负向" samples={detail?.negative || []} />
      </div>
    </div>
  );
}

function BrandWorldPanel({
  graph,
  summary,
  onAskNode,
  onOpenEvidence,
  onOpenRecommendations,
  isAskingIntelligence,
}: {
  graph?: OntologyGraphProjection;
  summary: OntologySummaryProjection;
  onAskNode: (node: OntologyGraphNode) => void;
  onOpenEvidence: (metricKey: EvidenceTab) => void;
  onOpenRecommendations: () => void;
  isAskingIntelligence?: boolean;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(['brand']));
  const [selectedId, setSelectedId] = useState<string | null>(graph?.default_focus || null);
  const [viewMode, setViewMode] = useState<BrandWorldViewMode>('map');
  const [galaxyUnavailable, setGalaxyUnavailable] = useState(false);
  const sourceNodes = useMemo(() => graph?.nodes || [], [graph?.nodes]);
  const sourceEdges = useMemo(() => graph?.edges || [], [graph?.edges]);
  const brandNodeId = sourceNodes.find((node) => node.type === 'brand')?.id || null;
  const effectiveSelectedId = selectedId || brandNodeId || graph?.default_focus || sourceNodes[0]?.id || null;
  const nodeById = useMemo(() => new Map(sourceNodes.map((node) => [node.id, node])), [sourceNodes]);

  const visibleNodeIds = useMemo(() => {
    const ids = new Set<string>();
    sourceNodes.forEach((node) => {
      if (
        (node.level ?? 0) <= 1 ||
        expanded.has(node.parent_id || '') ||
        groupOwnsExpandedNode(node, expanded) ||
        effectiveSelectedId === node.id
      ) {
        ids.add(node.id);
      }
    });
    return ids;
  }, [effectiveSelectedId, expanded, sourceNodes]);
  const nodes: Node[] = useMemo(
    () =>
      sourceNodes
        .filter((node) => visibleNodeIds.has(node.id))
        .map((node) => ({
          id: node.id,
          type: 'graphNode',
          position: positionForNode(node, sourceNodes),
          data: { node, selected: node.id === effectiveSelectedId },
          style: graphNodeStyle(node, node.id === effectiveSelectedId),
          draggable: false,
          selectable: true,
          focusable: true,
          ariaLabel: graphNodeTitle(node),
        })),
    [effectiveSelectedId, sourceNodes, visibleNodeIds],
  );
  const edges: Edge[] = useMemo(
    () =>
      sourceEdges
        .filter(
          (edge) =>
            visibleNodeIds.has(edge.from) &&
            visibleNodeIds.has(edge.to) &&
            shouldShowGraphEdge(edge, nodeById, expanded),
        )
        .map((edge) => ({
          id: edge.id,
          source: edge.from,
          target: edge.to,
          interactionWidth: 18,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: edge.strength === 'strong' ? 'var(--brand-primary)' : 'var(--border-strong)',
          },
          ...graphEdgeHandles(edge, sourceNodes),
          style: {
            stroke: edge.strength === 'strong' ? 'var(--brand-primary)' : 'var(--border-strong)',
            strokeOpacity: edge.strength === 'strong' ? 0.9 : 0.5,
            strokeWidth: edge.strength === 'strong' ? 1.7 : 1.1,
          },
        })),
    [expanded, nodeById, sourceEdges, sourceNodes, visibleNodeIds],
  );
  const selectedNode = sourceNodes.find((node) => node.id === effectiveSelectedId) || sourceNodes[0];
  const selectedSummary = selectedNode ? graphNodeSummary(selectedNode) : '';
  const selectedRelations = useMemo(
    () => (selectedNode ? graphRelationsForNode(selectedNode, sourceEdges, nodeById) : []),
    [nodeById, selectedNode, sourceEdges],
  );
  const selectGraphNode = (nodeId: string) => {
    setSelectedId(nodeId);
    const sourceNode = sourceNodes.find((item) => item.id === nodeId);
    setExpanded((prev) => {
      if ((sourceNode?.level || 0) === 0) return new Set(['brand']);
      if ((sourceNode?.level || 0) === 1) return new Set(['brand', nodeId]);
      const next = new Set(prev);
      next.add(nodeId);
      return next;
    });
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <div className="overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-[var(--text-primary)]">品牌世界</div>
            <div className="mt-1 text-xs text-[var(--text-tertiary)]">中心品牌、核心指标、证据来源和建议</div>
          </div>
          <div className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1">
            {[
              { key: 'map' as BrandWorldViewMode, label: '关系图' },
              { key: 'galaxy' as BrandWorldViewMode, label: '立体图谱' },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setViewMode(item.key)}
                className={`rounded-md px-3 py-1.5 text-sm transition ${
                  viewMode === item.key
                    ? 'bg-[var(--bg-primary)] text-[var(--brand-primary)] shadow-sm'
                    : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="grid gap-2 border-b border-[var(--border-subtle)] px-4 py-3 text-xs text-[var(--text-secondary)] md:grid-cols-4">
          <GraphLegendItem label="节点大小" text="证据量或影响权重" />
          <GraphLegendItem label="节点颜色" text="品牌、指标、来源、建议类型" />
          <GraphLegendItem label="节点距离" text="与品牌判断的关系远近" />
          <GraphLegendItem label="连线方向" text="判断、来源和建议的流向" />
        </div>
        <div className="brand-world-flow h-[640px] overflow-hidden bg-[var(--bg-primary)]">
        <style>{`
          .brand-world-flow .react-flow__handle {
            opacity: 0 !important;
            pointer-events: none !important;
          }
          .brand-world-flow .react-flow__edge-path {
            transition: stroke 160ms ease, stroke-opacity 160ms ease;
          }
        `}</style>
        {nodes.length && viewMode === 'map' ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={GRAPH_NODE_TYPES}
            key={Array.from(visibleNodeIds).sort().join('|')}
            fitView
            fitViewOptions={{ padding: 0.16, includeHiddenNodes: false }}
            minZoom={0.35}
            maxZoom={1.6}
            nodesDraggable={false}
            nodesConnectable={false}
            panOnScroll
            onNodeClick={(_, node) => {
              selectGraphNode(node.id);
            }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="var(--border-subtle)" gap={26} size={1} />
            <Controls className="border border-[var(--border-subtle)] bg-[var(--bg-primary)]" />
          </ReactFlow>
        ) : nodes.length && viewMode === 'galaxy' ? (
          <BrandWorldGalaxyView
            sourceNodes={sourceNodes}
            sourceEdges={sourceEdges}
            visibleNodeIds={visibleNodeIds}
            selectedId={effectiveSelectedId}
            onSelectNode={selectGraphNode}
            onFallback={() => {
              setGalaxyUnavailable(true);
              setViewMode('map');
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <EmptyLine text="当前还没有可展示的品牌图谱。" />
          </div>
        )}
        </div>
      </div>
      <aside className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5">
        <h3 className="text-base font-semibold text-[var(--text-primary)]">品牌世界</h3>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          查看{summary.brand?.name || '当前品牌'}在 AI 回答里的指标、平台、竞品、来源和建议。
        </p>
        {galaxyUnavailable && (
          <p className="mt-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-xs text-[var(--text-tertiary)]">
            当前环境无法打开立体图谱，已切回关系图。
          </p>
        )}
        {selectedNode && (
          <div className="mt-5 space-y-4">
            <div>
              <div className="text-xs text-[var(--text-tertiary)]">{graphNodeKind(selectedNode)}</div>
              <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{graphNodeTitle(selectedNode)}</div>
              {selectedNode.value && (
                <div className="mt-2 text-2xl font-semibold text-[var(--brand-primary)]">{selectedNode.value}</div>
              )}
              {selectedSummary && (
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{selectedSummary}</p>
              )}
            </div>
            <GraphDetailBlock title="它说明什么" text={graphNodeMeaning(selectedNode, summary)} />
            <GraphDetailBlock title="和品牌的关系" text={graphNodeRelationText(selectedNode, selectedRelations)} />
            <GraphDetailBlock title="证据入口" text={graphNodeEvidenceText(selectedNode, summary)} />
            {(selectedNode.metric_key || (selectedNode.next_actions || []).length > 0) && (
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
                <div className="text-xs font-medium text-[var(--text-tertiary)]">下一步</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {isEvidenceTab(selectedNode.metric_key) && (
                    <button
                      type="button"
                      onClick={() => onOpenEvidence(selectedNode.metric_key as EvidenceTab)}
                      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)]"
                    >
                      查看证据
                    </button>
                  )}
                  {(selectedNode.next_actions || []).length > 0 && (
                    <button
                      type="button"
                      onClick={onOpenRecommendations}
                      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)]"
                    >
                      查看建议
                    </button>
                  )}
                </div>
              </div>
            )}
            {selectedRelations.length > 0 && (
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
                <div className="text-xs font-medium text-[var(--text-tertiary)]">证据关系</div>
                <div className="mt-2 space-y-2">
                  {selectedRelations.slice(0, 5).map((relation) => (
                    <div
                      key={`${relation.direction}-${relation.label}-${relation.other.id}`}
                      className="grid gap-1 text-sm md:grid-cols-[minmax(0,1fr)_auto]"
                    >
                      <span className="min-w-0 text-[var(--text-primary)]">
                        {businessRelationVerb(relation)} {graphNodeTitle(relation.other)}
                      </span>
                      <span className="shrink-0 rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-xs text-[var(--text-tertiary)]">
                        {relation.label}
                      </span>
                      {relation.edge.business_meaning && (
                        <span className="text-xs leading-5 text-[var(--text-tertiary)] md:col-span-2">
                          {cleanEvidenceText(relation.edge.business_meaning, '这条关系用于解释品牌表现。')}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <button
              type="button"
              disabled={isAskingIntelligence}
              onClick={() => onAskNode(selectedNode)}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)] disabled:opacity-50"
            >
              <MessageSquareText size={16} />
              解释这段关系
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}

function RecommendationPanel({
  entityId,
  recommendations,
  summary,
  sampleStatus,
  onAsk,
  onContinueAnalysis,
  onOpenMonitoringSettings,
  isAskingIntelligence,
}: {
  entityId: string;
  recommendations: OntologyRecommendationItem[];
  summary: OntologySummaryProjection;
  sampleStatus?: OntologyRecommendationProjection['sample_status'];
  onAsk: (item: OntologyRecommendationItem) => void;
  onContinueAnalysis: () => void;
  onOpenMonitoringSettings?: (context?: {
    recommendationId?: string;
    targetMetric?: string;
    contentFormat?: string;
  }) => void;
  isAskingIntelligence?: boolean;
}) {
  const {
    submitRecommendationTask,
    recommendationTaskSubmittingByKey,
    recommendationTaskErrorByKey,
  } = useOntologyStore();
  const [taskDrafts, setTaskDrafts] = useState<Record<string, {
    owner_label?: string;
    due_at?: string;
    review_at?: string;
    feedback_text?: string;
  }>>({});
  const updateTaskDraft = (
    recommendationId: string,
    patch: Partial<{ owner_label: string; due_at: string; review_at: string; feedback_text: string }>,
  ) => {
    setTaskDrafts((state) => ({
      ...state,
      [recommendationId]: {
        ...(state[recommendationId] || {}),
        ...patch,
      },
    }));
  };
  const saveTaskState = (
    item: OntologyRecommendationItem,
    taskStatus: 'not_started' | 'in_progress' | 'completed' | 'review_pending',
  ) => {
    const draft = taskDrafts[item.id] || {};
    void submitRecommendationTask(entityId, item.id, {
      task_status: taskStatus,
      owner_label: draft.owner_label,
      due_at: draft.due_at,
      review_at: draft.review_at,
      feedback_text: draft.feedback_text,
    });
  };

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
      <div className="border-b border-[var(--border-subtle)] px-5 py-4">
        <h3 className="text-base font-semibold text-[var(--text-primary)]">跟进反馈</h3>
      </div>
      <div className="divide-y divide-[var(--border-subtle)]">
        {recommendations.length ? (
          recommendations.map((item) => (
            <div key={item.id} className="grid gap-5 px-5 py-5 xl:grid-cols-[minmax(0,1fr)_220px]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-lg font-semibold text-[var(--text-primary)]">{item.title}</h4>
                  <PriorityPill priority={item.priority} />
                  <TaskStatePill state={item.task_state} />
                  {item.content_format && (
                    <span className="rounded-lg border border-[var(--border-subtle)] px-2 py-1 text-xs text-[var(--text-tertiary)]">
                      {item.content_format}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{item.reason}</p>
                {item.impact && <p className="mt-1 text-sm text-[var(--text-tertiary)]">{item.impact}</p>}
                {item.content_brief && (
                  <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{item.content_brief}</p>
                )}
                {(item.expected_impact || item.review_criteria) && (
                  <div className="mt-4 grid gap-3 border-t border-[var(--border-subtle)] pt-4 md:grid-cols-2">
                    {item.expected_impact && (
                      <div>
                        <div className="text-xs font-medium text-[var(--text-tertiary)]">预期影响</div>
                        <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{item.expected_impact}</p>
                      </div>
                    )}
                    {item.review_criteria && (
                      <div>
                        <div className="text-xs font-medium text-[var(--text-tertiary)]">复查标准</div>
                        <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{item.review_criteria}</p>
                      </div>
                    )}
                  </div>
                )}
                {(item.execution_steps || []).length > 0 && (
                  <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
                    <div className="text-xs font-medium text-[var(--text-tertiary)]">执行顺序</div>
                    <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm leading-6 text-[var(--text-secondary)]">
                      {(item.execution_steps || []).slice(0, 3).map((step, index) => (
                        <li key={`${item.id}-visible-step-${index}`}>{step}</li>
                      ))}
                    </ol>
                  </div>
                )}
                {(item.content_directions || []).length > 0 && (
                  <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
                    <div className="text-xs font-medium text-[var(--text-tertiary)]">内容方向</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(item.content_directions || []).slice(0, 3).map((direction, index) => (
                        <span
                          key={`${item.id}-direction-${index}`}
                          className="inline-flex max-w-full rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)]"
                          title={[direction.angle, direction.evidence].filter(Boolean).join('\n')}
                        >
                          {direction.title || '内容主题'}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {(item.distribution_targets || []).length > 0 && (
                  <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
                    <div className="text-xs font-medium text-[var(--text-tertiary)]">投放位置</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(item.distribution_targets || []).slice(0, 6).map((target, index) => (
                        <span
                          key={`${item.id}-target-${target.domain || target.name || index}`}
                          className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)]"
                          title={target.reason}
                        >
                          {target.name || target.domain || '待确认位置'}
                          {target.platform && (
                            <span className="text-[var(--text-tertiary)]">· {platformLabel(target.platform)}</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {hasRecommendationBrief(item) && (
                  <details className="mt-4 border-t border-[var(--border-subtle)] pt-4">
                    <summary className="cursor-pointer text-xs font-medium text-[var(--brand-primary)]">
                      查看执行要点
                    </summary>
                    <RecommendationBrief item={item} />
                  </details>
                )}
              </div>
              <div className="space-y-3">
                <div className="grid gap-2">
                  <input
                    value={taskDrafts[item.id]?.owner_label ?? item.owner_label ?? ''}
                    onChange={(event) => updateTaskDraft(item.id, { owner_label: event.target.value })}
                    placeholder="负责人"
                    className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-sm outline-none focus:border-[var(--brand-border)]"
                  />
                  <input
                    value={taskDrafts[item.id]?.due_at ?? item.due_at ?? ''}
                    onChange={(event) => updateTaskDraft(item.id, { due_at: event.target.value })}
                    placeholder="截止时间"
                    className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-sm outline-none focus:border-[var(--brand-border)]"
                  />
                  <input
                    value={taskDrafts[item.id]?.review_at ?? item.review_at ?? ''}
                    onChange={(event) => updateTaskDraft(item.id, { review_at: event.target.value })}
                    placeholder="复查时间"
                    className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-sm outline-none focus:border-[var(--brand-border)]"
                  />
                  <textarea
                    value={taskDrafts[item.id]?.feedback_text ?? ''}
                    onChange={(event) => updateTaskDraft(item.id, { feedback_text: event.target.value })}
                    placeholder="记录本次处理"
                    rows={3}
                    className="w-full resize-none rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-sm outline-none focus:border-[var(--brand-border)]"
                  />
                </div>
                {item.latest_feedback_at && (
                  <div className="text-xs text-[var(--text-tertiary)]">
                    已更新 {formatDate(item.latest_feedback_at)}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2">
                  {[
                    ['not_started', '加入跟进'],
                    ['in_progress', '进行中'],
                    ['completed', '完成'],
                    ['review_pending', '待复查'],
                  ].map(([state, label]) => {
                    const taskKey = `${entityId}:${item.id}`;
                    const submitting = Boolean(recommendationTaskSubmittingByKey[taskKey]);
                    return (
                      <button
                        key={state}
                        type="button"
                        disabled={submitting}
                        onClick={() => saveTaskState(item, state as 'not_started' | 'in_progress' | 'completed' | 'review_pending')}
                        className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)] disabled:opacity-50"
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                {recommendationTaskErrorByKey[`${entityId}:${item.id}`] && (
                  <div className="text-xs text-[var(--error)]">{recommendationTaskErrorByKey[`${entityId}:${item.id}`]}</div>
                )}
                <div className="flex flex-wrap items-start gap-2 xl:justify-end">
                {item.next_action === 'open_monitoring_settings' ? (
                  <button
                    type="button"
                    onClick={() =>
                      onOpenMonitoringSettings?.({
                        recommendationId: item.id,
                        targetMetric: item.target_metric,
                        contentFormat: item.content_format,
                      })
                    }
                    disabled={!onOpenMonitoringSettings}
                    className="inline-flex items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-4 py-2 text-sm font-medium text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)]"
                  >
                    <Settings size={16} />
                    {item.cta_label || '打开监测设置'}
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={isAskingIntelligence}
                    onClick={() => onAsk(item)}
                    className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] hover:border-[var(--brand-border)] disabled:opacity-50"
                  >
                    <MessageSquareText size={16} />
                    {item.cta_label || '生成内容草稿'}
                  </button>
                )}
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="px-5 py-10">
            {isRecommendationSamplePending(sampleStatus, summary) ? (
              <div className="max-w-2xl">
                <div className="text-base font-semibold text-[var(--text-primary)]">
                  {sampleStatus?.status === 'needs_question_samples' ? '先生成问题' : '先补答案样本'}
                </div>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  {sampleStatus?.reason || '还没有可分析的 AI 回答，先补齐样本后再生成跟进建议。'}
                </p>
                <button
                  type="button"
                  disabled={isAskingIntelligence}
                  onClick={onContinueAnalysis}
                  className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-4 py-2 text-sm font-medium text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-50"
                >
                  <MessageSquareText size={16} />
                  {sampleStatus?.status === 'needs_question_samples' ? '开始分析' : '继续抓取答案'}
                </button>
              </div>
            ) : (
              <EmptyLine text={`${summary.brand?.name || '当前品牌'} 暂无新的跟进建议。`} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function RecommendationBrief({ item }: { item: OntologyRecommendationItem }) {
  const evidenceRefs = item.evidence_refs || [];
  const directions = item.content_directions || [];
  const targets = item.distribution_targets || [];
  const steps = item.execution_steps || [];

  return (
    <div className="mt-2 rounded-lg bg-[var(--bg-secondary)] p-3 text-sm leading-6 text-[var(--text-secondary)]">
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">目标</div>
          <div className="mt-1 text-[var(--text-primary)]">
            {targetMetricLabel(item.target_metric)}
            {item.content_format ? ` · ${item.content_format}` : ''}
          </div>
        </div>
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">依据</div>
          <div className="mt-1 text-[var(--text-primary)]">
            {evidenceRefs.length ? evidenceRefs.slice(0, 2).join('；') : item.reason}
          </div>
        </div>
      </div>
      {directions.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">内容重点</div>
          <div className="mt-1 text-[var(--text-primary)]">
            {directions
              .slice(0, 3)
              .map((direction) => direction.title || direction.angle)
              .filter(Boolean)
              .join('；')}
          </div>
        </div>
      )}
      {targets.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">优先位置</div>
          <div className="mt-1 text-[var(--text-primary)]">
            {targets
              .slice(0, 4)
              .map((target) => target.name || target.domain)
              .filter(Boolean)
              .join('、')}
          </div>
        </div>
      )}
      {steps.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">执行顺序</div>
          <ol className="mt-1 list-decimal space-y-1 pl-4 text-[var(--text-primary)]">
            {steps.slice(0, 4).map((step, index) => (
              <li key={`${item.id}-step-${index}`}>{step}</li>
            ))}
          </ol>
        </div>
      )}
      {item.content_generation_brief && (
        <div className="mt-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">生成依据</div>
          <div className="mt-1 text-[var(--text-primary)]">{item.content_generation_brief}</div>
        </div>
      )}
    </div>
  );
}

function hasRecommendationBrief(item: OntologyRecommendationItem) {
  return Boolean(
    item.content_format ||
      item.target_metric ||
      item.reason ||
      item.content_generation_brief ||
      (item.evidence_refs || []).length ||
      (item.content_directions || []).length ||
      (item.distribution_targets || []).length ||
      (item.execution_steps || []).length,
  );
}

function needsAnswerSampling(summary: OntologySummaryProjection) {
  const scope = summary.sample_scope || {};
  const answerCount = Number(scope.answer_count ?? 0);
  const rawAnswerCount = Number(scope.raw_answer_record_count ?? 0);
  const mentionStatus = summary.metrics?.mention_rate?.sample_sufficiency?.status;
  return answerCount <= 0 || rawAnswerCount <= 0 || mentionStatus === 'no_sample';
}

function isRecommendationSamplePending(
  sampleStatus: OntologyRecommendationProjection['sample_status'] | undefined,
  summary: OntologySummaryProjection,
) {
  return (
    sampleStatus?.status === 'needs_question_samples' ||
    sampleStatus?.status === 'needs_answer_samples' ||
    needsAnswerSampling(summary)
  );
}

function buildRecommendationHandoffGoal(item: OntologyRecommendationItem) {
  return [
    item.reason,
    item.impact,
    item.content_brief,
  ]
    .filter(Boolean)
    .join(' ');
}

function buildRecommendationChatRequest(
  item: OntologyRecommendationItem,
  summary: OntologySummaryProjection,
) {
  const brand = summary.brand?.name || '当前品牌';
  const target = targetMetricLabel(item.target_metric);
  const directions = (item.content_directions || [])
    .slice(0, 4)
    .map((direction) => {
      const title = direction.title || direction.angle;
      const evidence = direction.evidence ? `，依据：${direction.evidence}` : '';
      return title ? `- ${title}${evidence}` : '';
    })
    .filter(Boolean)
    .join('\n');
  const targets = (item.distribution_targets || [])
    .slice(0, 6)
    .map((targetItem) => {
      const name = targetItem.name || targetItem.domain;
      const platform = targetItem.platform ? `，面向 ${platformLabel(targetItem.platform)}` : '';
      const reason = targetItem.reason ? `，原因：${targetItem.reason}` : '';
      return name ? `- ${name}${platform}${reason}` : '';
    })
    .filter(Boolean)
    .join('\n');
  const evidence = (item.evidence_refs || []).slice(0, 4).join('；') || item.reason;

  return [
    `请为${brand}生成一版${item.content_format || '可投放内容草稿'}。`,
    `目标指标：${target}。`,
    `当前依据：${evidence}。`,
    item.content_generation_brief ? `任务说明：${item.content_generation_brief}` : '',
    item.content_brief ? `内容方向：${item.content_brief}` : '',
    directions ? `可写主题：\n${directions}` : '',
    targets ? `优先投放位置：\n${targets}` : '',
    '请输出：标题、目标读者、正文结构、关键事实、引用证据、发布位置、复查指标。',
  ]
    .filter(Boolean)
    .join('\n');
}

function PlatformTable({ rows }: { rows: OntologyPlatformMetricRow[] }) {
  if (!rows.length) return <EmptyLine text="当前还没有平台拆分样本。" />;
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
      <table className="w-full min-w-[620px] text-sm">
        <thead className="bg-[var(--bg-secondary)] text-left text-[var(--text-tertiary)]">
          <tr>
            <th className="px-4 py-3 font-medium">平台</th>
            <th className="px-4 py-3 font-medium">提及率</th>
            <th className="px-4 py-3 font-medium">提及回答</th>
            <th className="px-4 py-3 font-medium">答案样本</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border-subtle)]">
          {rows.map((row) => (
            <tr key={row.platform}>
              <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{platformLabel(row.platform)}</td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">{percent(row.mention_rate)}</td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">{row.mention_count}</td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">{row.answer_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function evidencePlatforms(evidence?: OntologyEvidenceProjection) {
  const platforms = new Set<string>();
  for (const row of evidence?.mention_rate_detail?.platform_rows || []) {
    if (row.platform) platforms.add(row.platform);
  }
  const sampleGroups = [
    evidence?.mention_rate_detail?.answer_samples || [],
    evidence?.mention_rate_detail?.unmentioned_answer_samples || [],
    evidence?.sentiment_detail?.positive || [],
    evidence?.sentiment_detail?.neutral || [],
    evidence?.sentiment_detail?.negative || [],
  ];
  for (const samples of sampleGroups) {
    for (const sample of samples) {
      if (sample.platform) platforms.add(sample.platform);
    }
  }
  return Array.from(platforms).sort();
}

function filterEvidenceByPlatform(
  evidence?: OntologyEvidenceProjection,
  platform = 'all',
): OntologyEvidenceProjection | undefined {
  if (!evidence || platform === 'all') return evidence;
  const sampleMatches = (sample: OntologyAnswerEvidenceSample) => sample.platform === platform;
  return {
    ...evidence,
    mention_rate_detail: evidence.mention_rate_detail
      ? {
          ...evidence.mention_rate_detail,
          platform_rows: evidence.mention_rate_detail.platform_rows.filter((row) => row.platform === platform),
          answer_samples: evidence.mention_rate_detail.answer_samples.filter(sampleMatches),
          unmentioned_answer_samples: (evidence.mention_rate_detail.unmentioned_answer_samples || []).filter(sampleMatches),
        }
      : undefined,
    sentiment_detail: evidence.sentiment_detail
      ? {
          ...evidence.sentiment_detail,
          positive: evidence.sentiment_detail.positive.filter(sampleMatches),
          neutral: evidence.sentiment_detail.neutral.filter(sampleMatches),
          negative: evidence.sentiment_detail.negative.filter(sampleMatches),
        }
      : undefined,
  };
}

function AnswerSampleList({
  title,
  emptyText,
  samples,
}: {
  title: string;
  emptyText: string;
  samples: OntologyAnswerEvidenceSample[];
}) {
  const [reviewStateByKey, setReviewStateByKey] = useState<Record<string, 'review' | 'excluded'>>({});
  if (!samples.length) return <EmptyLine text={emptyText} />;
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h4>
      {samples.map((sample) => {
        const sampleKey = sample.answer_id || `${sample.platform}-${sample.question}`;
        const reviewState = reviewStateByKey[sampleKey];
        return (
        <div key={sampleKey} className="rounded-lg border border-[var(--border-subtle)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-tertiary)]">
            <span>{platformLabel(sample.platform)}</span>
            <span>{sentimentLabel(sample.sentiment)}</span>
            {sample.captured_at && <span>{formatDate(sample.captured_at)}</span>}
            {(sample.cited_domains || []).slice(0, 3).map((domain) => (
              <span key={domain} className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5">{domain}</span>
            ))}
            {reviewState === 'review' && <span className="rounded-full border border-[var(--warning)]/40 px-2 py-0.5 text-[var(--warning)]">待复核</span>}
            {reviewState === 'excluded' && <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5">已排除</span>}
          </div>
          <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">
            {cleanEvidenceText(sample.question, '问题文本待补充')}
          </p>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {cleanEvidenceText(sample.mention_quote || sample.answer_preview, '答案摘录待补充')}
          </p>
          {(sample.citation_sources || []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {(sample.citation_sources || []).slice(0, 4).map((source) => (
                <EvidenceSourceLink
                  key={source.citation_id || source.url || source.domain}
                  source={source}
                />
              ))}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setReviewStateByKey((state) => ({ ...state, [sampleKey]: 'review' }))}
              className="rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:border-[var(--brand-border)]"
            >
              标记复核
            </button>
            <button
              type="button"
              onClick={() => setReviewStateByKey((state) => ({ ...state, [sampleKey]: 'excluded' }))}
              className="rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:border-[var(--brand-border)]"
            >
              排除样本
            </button>
          </div>
        </div>
      );
      })}
    </div>
  );
}

function DomainList({ rows }: { rows: OntologyExternalDomainRow[] }) {
  if (!rows.length) return <EmptyLine text="当前还没有外部来源样本。" />;
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {rows.map((row) => (
        <div key={row.domain} className="rounded-lg border border-[var(--border-subtle)] px-4 py-3">
          <div className="font-medium text-[var(--text-primary)]">{row.domain}</div>
          <div className="mt-2 text-sm text-[var(--text-secondary)]">
            {row.citation_count} 次引用，{row.answer_count} 条回答
          </div>
          {(row.sample_titles || []).length > 0 && (
            <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
              {cleanEvidenceText(row.sample_titles?.[0], '来源样本待补充')}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function SentimentColumn({ title, samples }: { title: string; samples: OntologyAnswerEvidenceSample[] }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] p-4">
      <h4 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h4>
      <div className="mt-3 space-y-3">
        {samples.length ? (
          samples.map((sample) => (
            <div key={sample.answer_id || sample.mention_quote} className="text-sm leading-6 text-[var(--text-secondary)]">
              <div className="text-xs text-[var(--text-tertiary)]">{platformLabel(sample.platform)}</div>
              <p>{cleanEvidenceText(sample.mention_quote || sample.answer_preview, '答案摘录待补充')}</p>
            </div>
          ))
        ) : (
          <p className="text-sm text-[var(--text-tertiary)]">暂无样本</p>
        )}
      </div>
    </div>
  );
}

function EvidenceSourceItem({ sample }: { sample: { citation_id?: string; url?: string; domain?: string; title?: string; snippet_preview?: string } }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] px-4 py-3">
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
        <ExternalLink size={15} />
        {sample.url ? (
          <a href={sample.url} target="_blank" rel="noreferrer" className="hover:text-[var(--brand-primary)]">
            {cleanEvidenceText(sample.title || sample.domain || sample.url, '来源')}
          </a>
        ) : (
          cleanEvidenceText(sample.title || sample.domain || sample.url, '来源')
        )}
      </div>
      {sample.snippet_preview && (
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          {cleanEvidenceText(sample.snippet_preview, '来源摘录待补充')}
        </p>
      )}
    </div>
  );
}

function EvidenceSourceLink({
  source,
}: {
  source: { url?: string; domain?: string; title?: string; snippet_preview?: string };
}) {
  const label = cleanEvidenceText(source.title || source.domain || source.url, '来源');
  if (!source.url) {
    return (
      <span className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-xs text-[var(--text-tertiary)]">
        {label}
      </span>
    );
  }
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noreferrer"
      title={cleanEvidenceText(source.snippet_preview, label)}
      className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-xs text-[var(--text-secondary)] hover:border-[var(--brand-border)] hover:text-[var(--brand-primary)]"
    >
      <ExternalLink size={12} />
      {label}
    </a>
  );
}

function MetricFormula({ title, value, formula }: { title: string; value: string; formula: string }) {
  return (
    <div className="grid gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 md:grid-cols-[180px_1fr] md:items-center">
      <div>
        <div className="text-sm text-[var(--text-tertiary)]">{title}</div>
        <div className="mt-1 text-2xl font-semibold text-[var(--brand-primary)]">{value}</div>
      </div>
      <div className="text-sm leading-6 text-[var(--text-secondary)]">{formula}</div>
    </div>
  );
}

function Judgment({ label, item }: { label: string; item?: { title?: string; reason?: string } }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] px-4 py-3">
      <div className="text-xs text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">{item?.title || '暂无'}</div>
      {item?.reason && <p className="mt-1 text-xs text-[var(--text-secondary)]">{item.reason}</p>}
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <p className="rounded-lg border border-dashed border-[var(--border-subtle)] px-4 py-3 text-sm text-[var(--text-tertiary)]">{text}</p>;
}

function PriorityPill({ priority }: { priority?: string }) {
  const label = priority === 'high' ? '高优先级' : priority === 'medium' ? '中优先级' : '低优先级';
  return <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-xs text-[var(--text-tertiary)]">{label}</span>;
}

function TaskStatePill({ state }: { state?: string }) {
  const label =
    state === 'in_progress'
      ? '进行中'
      : state === 'completed'
        ? '已完成'
        : state === 'review_pending'
          ? '待复查'
          : '未跟进';
  const active = state === 'in_progress' || state === 'completed' || state === 'review_pending';
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs ${
        active
          ? 'border-[var(--brand-border)] bg-[var(--brand-soft)] text-[var(--brand-primary)]'
          : 'border-[var(--border-subtle)] text-[var(--text-tertiary)]'
      }`}
    >
      {label}
    </span>
  );
}

function GraphLegendItem({ label, text }: { label: string; text: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2 w-2 rounded-full bg-[var(--brand-primary)]" />
      <span className="font-medium text-[var(--text-primary)]">{label}</span>
      <span>{text}</span>
    </div>
  );
}

function GraphDetailBlock({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
      <div className="text-xs font-medium text-[var(--text-tertiary)]">{title}</div>
      <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{text}</p>
    </div>
  );
}

type GraphRelationView = {
  direction: 'in' | 'out';
  label: string;
  edge: OntologyGraphProjection['edges'][number];
  other: OntologyGraphNode;
};

type GraphNodeData = {
  node: OntologyGraphNode;
  selected: boolean;
};

const GRAPH_NODE_TYPES = {
  graphNode: GraphFlowNode,
};

function GraphFlowNode({ data }: { data: GraphNodeData }) {
  return (
    <>
      {GRAPH_HANDLE_POSITIONS.map(({ id, position }) => (
        <Handle key={`source-${id}`} id={`source-${id}`} type="source" position={position} />
      ))}
      {GRAPH_HANDLE_POSITIONS.map(({ id, position }) => (
        <Handle key={`target-${id}`} id={`target-${id}`} type="target" position={position} />
      ))}
      <GraphNodeLabel node={data.node} selected={data.selected} />
    </>
  );
}

function BrandWorldGalaxyView({
  sourceNodes,
  sourceEdges,
  visibleNodeIds,
  selectedId,
  onSelectNode,
  onFallback,
}: {
  sourceNodes: OntologyGraphNode[];
  sourceEdges: OntologyGraphProjection['edges'];
  visibleNodeIds: Set<string>;
  selectedId: string | null;
  onSelectNode: (nodeId: string) => void;
  onFallback: () => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<ForceGraphMethods<GalaxyGraphNode, GalaxyGraphLink> | undefined>(undefined);
  const [webglStatus, setWebglStatus] = useState<'checking' | 'ready' | 'blocked'>('checking');
  const [size, setSize] = useState({ width: 900, height: 600 });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  const galaxyData = useMemo(
    () => buildGalaxyGraphData(sourceNodes, sourceEdges, visibleNodeIds, selectedId),
    [selectedId, sourceEdges, sourceNodes, visibleNodeIds],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setWebglStatus(hasWebGLSupport() ? 'ready' : 'blocked');
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (webglStatus === 'blocked') onFallback();
  }, [onFallback, webglStatus]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(320, Math.floor(entry.contentRect.width));
      const height = Math.max(520, Math.floor(entry.contentRect.height));
      setSize({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (webglStatus !== 'ready') return;
    window.setTimeout(() => graphRef.current?.zoomToFit(500, 70), 80);
  }, [galaxyData, webglStatus]);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === containerRef.current);
      window.setTimeout(() => graphRef.current?.zoomToFit(400, 70), 80);
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  if (webglStatus === 'blocked') {
    return (
      <div className="flex h-full items-center justify-center px-5">
        <EmptyLine text="当前浏览器不支持立体图谱，请使用关系图查看品牌世界。" />
      </div>
    );
  }

  return (
    <div ref={containerRef} className="brand-world-galaxy relative h-full overflow-hidden bg-[#070a10]">
      <style>{`
        .brand-world-galaxy::before {
          content: "";
          position: absolute;
          inset: 0;
          background:
            radial-gradient(circle at 52% 42%, rgba(31, 122, 107, 0.22), transparent 28%),
            radial-gradient(circle at 22% 76%, rgba(120, 103, 156, 0.18), transparent 24%),
            radial-gradient(circle at 80% 22%, rgba(217, 228, 220, 0.12), transparent 22%),
            linear-gradient(180deg, rgba(6, 9, 15, 0.62), rgba(6, 9, 15, 0.96));
          pointer-events: none;
        }
        .brand-world-galaxy::after {
          content: "";
          position: absolute;
          inset: 0;
          background-image:
            radial-gradient(circle, rgba(255, 255, 255, 0.92) 0 1px, transparent 1.5px),
            radial-gradient(circle, rgba(189, 230, 218, 0.62) 0 1px, transparent 1.6px);
          background-position: 13px 21px, 51px 72px;
          background-size: 78px 86px, 132px 142px;
          opacity: 0.34;
          pointer-events: none;
        }
      `}</style>
      <div className="absolute left-4 top-4 z-10 flex flex-wrap items-center gap-2">
        <span className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-white/70 shadow-sm backdrop-blur-sm">
          拖拽旋转 · 滚轮缩放
        </span>
        {galaxyData.limited && (
          <span className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-white/70 shadow-sm backdrop-blur-sm">
            已聚合高密节点
          </span>
        )}
      </div>
      <div className="absolute right-4 top-4 z-10 flex items-center gap-2">
        <button
          type="button"
          onClick={() => graphRef.current?.zoomToFit(500, 70)}
          className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-white/75 shadow-sm backdrop-blur-sm hover:border-white/25"
        >
          回到全图
        </button>
        <button
          type="button"
          onClick={() => {
            if (document.fullscreenElement === containerRef.current) {
              void document.exitFullscreen();
              return;
            }
            void containerRef.current?.requestFullscreen();
          }}
          className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-white/75 shadow-sm backdrop-blur-sm hover:border-white/25"
        >
          {isFullscreen ? '退出全屏' : '全屏'}
        </button>
      </div>
      {webglStatus === 'checking' ? (
        <div className="flex h-full items-center justify-center">
          <EmptyLine text="正在检查立体图谱环境。" />
        </div>
      ) : (
        <ForceGraph3D
          ref={graphRef}
          graphData={{ nodes: galaxyData.nodes, links: galaxyData.links }}
          width={size.width}
          height={size.height}
          backgroundColor="rgba(7, 10, 16, 0)"
          showNavInfo={false}
          nodeId="id"
          nodeVal={(node) => node.val}
          nodeColor={(node) => node.color}
          nodeLabel={(node) =>
            [node.kind, node.label, node.value, node.summary].filter(Boolean).join(' · ')
          }
          nodeResolution={24}
          nodeThreeObject={buildGalaxyNodeSprite}
          nodeThreeObjectExtend={false}
          linkSource="source"
          linkTarget="target"
          linkColor={(link) => link.color}
          linkWidth={(link) => link.width}
          linkLabel={(link) => link.label}
          linkOpacity={0.2}
          linkDirectionalArrowLength={0}
          linkDirectionalArrowRelPos={0}
          linkDirectionalParticles={0}
          warmupTicks={reducedMotion ? 0 : 80}
          cooldownTicks={reducedMotion ? 1 : 80}
          cooldownTime={reducedMotion ? 250 : 2600}
          d3VelocityDecay={0.58}
          enableNodeDrag={false}
          enableNavigationControls
          showPointerCursor={(obj) => Boolean(obj)}
          onNodeClick={(node) => onSelectNode(node.id)}
          onEngineStop={() => graphRef.current?.zoomToFit(450, 70)}
        />
      )}
    </div>
  );
}

function GraphNodeLabel({ node, selected }: { node: OntologyGraphNode; selected: boolean }) {
  const summary = graphNodeSummary(node);
  return (
    <div className="min-w-[120px] max-w-[190px]">
      <div className="text-sm font-semibold">{graphNodeTitle(node)}</div>
      {node.value && <div className="mt-1 text-lg font-semibold text-[var(--brand-primary)]">{node.value}</div>}
      {summary && <div className="mt-1 line-clamp-2 text-xs opacity-75">{summary}</div>}
      {selected && <div className="mt-2 h-1 w-8 rounded-full bg-[var(--brand-primary)]" />}
    </div>
  );
}

function buildMetricRow(key: EvidenceTab, metric?: { display_value?: string | null; numerator?: number; denominator?: number; rank?: number | null; display_rank?: number | null; total?: number; sample_sufficiency?: { is_comparable?: boolean; rank_status_label?: string }; positive?: number; neutral?: number; negative?: number }) {
  if (key === 'mention_rate') {
    const hasSample = typeof metric?.denominator === 'number' && metric.denominator > 0;
    return {
      key,
      icon: <SearchCheck size={17} />,
      title: `AI 提及率 ${metric?.display_value || '样本不足'}`,
      body: hasSample
        ? `当前 AI 回答样本中，${metric?.numerator ?? 0} 条提到当前品牌。`
        : '当前还没有可用于计算提及率的答案样本。',
      evidence: hasSample
        ? `${metric?.numerator ?? 0} 条提及，${metric?.denominator ?? 0} 条答案样本`
        : '等待答案样本',
    };
  }
  if (key === 'mention_ranking') {
    const displayRank = metric?.sample_sufficiency?.is_comparable === false
      ? null
      : (metric?.display_rank ?? metric?.rank ?? null);
    return {
      key,
      icon: <LineChart size={17} />,
      title: displayRank ? `提及排名 第 ${displayRank} / ${metric?.total || 1}` : '提及排名 未形成',
      body: '同一批问题和平台下，对当前品牌与竞品的提及率排序。',
      evidence: displayRank ? `${metric?.total || 1} 个品牌参与对比` : (metric?.sample_sufficiency?.rank_status_label || '需要补充竞品同场样本'),
    };
  }
  if (key === 'official_citation_rate') {
    const hasSample = typeof metric?.denominator === 'number' && metric.denominator > 0;
    return {
      key,
      icon: <ExternalLink size={17} />,
      title: `官网引用率 ${metric?.display_value || '样本不足'}`,
      body: 'AI 回答是否引用品牌官网，决定品牌自有信息能否成为回答依据。',
      evidence: hasSample
        ? `${metric?.numerator ?? 0} 次官网引用，${metric?.denominator ?? 0} 次全部引用`
        : '等待引用样本',
    };
  }
  const sentimentTotal =
    typeof metric?.positive === 'number' ||
    typeof metric?.neutral === 'number' ||
    typeof metric?.negative === 'number'
      ? (metric?.positive ?? 0) + (metric?.neutral ?? 0) + (metric?.negative ?? 0)
      : null;
  return {
    key,
    icon: <ShieldCheck size={17} />,
    title: sentimentTotal === null
      ? '语气性质 样本不足'
      : `语气性质 ${metric?.positive ?? 0} 正向 / ${metric?.neutral ?? 0} 中性 / ${metric?.negative ?? 0} 负向`,
    body: '只统计已经提及当前品牌的回答，判断 AI 对品牌的描述倾向。',
    evidence: sentimentTotal === null ? '等待提及样本' : `${sentimentTotal} 条提及样本`,
  };
}

function buildMetricTile(key: EvidenceTab, metric?: { display_value?: string | null; numerator?: number; denominator?: number; rank?: number | null; display_rank?: number | null; total?: number; sample_sufficiency?: { is_comparable?: boolean; rank_status_label?: string }; positive?: number; neutral?: number; negative?: number }) {
  if (key === 'mention_rate') {
    const hasSample = typeof metric?.denominator === 'number' && metric.denominator > 0;
    return {
      key,
      label: 'AI 提及率',
      value: metric?.display_value || '样本不足',
      evidence: hasSample ? `${metric?.numerator ?? 0}/${metric?.denominator ?? 0} 条答案` : '等待样本',
    };
  }
  if (key === 'mention_ranking') {
    const displayRank = metric?.sample_sufficiency?.is_comparable === false
      ? null
      : (metric?.display_rank ?? metric?.rank ?? null);
    return {
      key,
      label: '提及排名',
      value: displayRank ? `第 ${displayRank}` : '未形成',
      evidence: displayRank ? `${metric?.total || 1} 个品牌` : (metric?.sample_sufficiency?.rank_status_label || '需补样本'),
    };
  }
  if (key === 'official_citation_rate') {
    const hasSample = typeof metric?.denominator === 'number' && metric.denominator > 0;
    return {
      key,
      label: '官网引用率',
      value: metric?.display_value || '样本不足',
      evidence: hasSample ? `${metric?.numerator ?? 0}/${metric?.denominator ?? 0} 次引用` : '等待样本',
    };
  }
  const sentimentTotal =
    typeof metric?.positive === 'number' ||
    typeof metric?.neutral === 'number' ||
    typeof metric?.negative === 'number'
      ? (metric?.positive ?? 0) + (metric?.neutral ?? 0) + (metric?.negative ?? 0)
      : null;
  return {
    key,
    label: '语气性质',
    value: sentimentTotal === null ? '样本不足' : `${metric?.positive ?? 0}/${metric?.neutral ?? 0}/${metric?.negative ?? 0}`,
    evidence: sentimentTotal === null ? '等待样本' : '正向 / 中性 / 负向',
  };
}

function buildFallbackSummary({
  brandName,
  brandDomain,
  brandIndustry,
  dashboardHome,
}: {
  brandName?: string;
  brandDomain?: string;
  brandIndustry?: string;
  dashboardHome?: DashboardHomeData | null;
}): OntologySummaryProjection {
  const mentionRate = dashboardHome?.mention_board?.mention_rate ?? null;
  const sentiment = dashboardHome?.mention_board?.sentiment_summary || {
    positive: 0,
    neutral: 0,
    negative: 0,
  };
  return {
    brand: { name: brandName, domain: brandDomain, industry: brandIndustry },
    sample_scope: {
      platform_count: dashboardHome?.platform_diagnosis?.length || 0,
      question_count: dashboardHome?.data_point_count || 0,
      answer_count: dashboardHome?.mention_board?.report?.brand_mentions?.length || 0,
      citation_count: 0,
      mention_count: dashboardHome?.mention_board?.report?.brand_mentions?.length || 0,
    },
    metrics: {
      mention_rate: {
        key: 'mention_rate',
        label: 'AI 提及率',
        value: mentionRate,
        display_value: percent(mentionRate),
        numerator: dashboardHome?.mention_board?.report?.brand_mentions?.length || 0,
        denominator: dashboardHome?.data_point_count || 0,
      },
      mention_ranking: { key: 'mention_ranking', label: '提及排名', rank: null, total: 0 },
      official_citation_rate: {
        key: 'official_citation_rate',
        label: '官网引用率',
        value: null,
        display_value: '样本不足',
        numerator: 0,
        denominator: 0,
      },
      sentiment_distribution: {
        key: 'sentiment_distribution',
        label: '语气性质',
        positive: sentiment.positive || 0,
        neutral: sentiment.neutral || 0,
        negative: sentiment.negative || 0,
      },
    },
  };
}

type GraphSide = 'top' | 'right' | 'bottom' | 'left';

const GRAPH_CENTER = { x: 430, y: 300 };
const FIRST_RING_RADIUS = { x: 300, y: 210 };
const SECOND_RING_RADIUS = { x: 450, y: 350 };
const GALAXY_MAX_VISIBLE_NODES = 80;
const GRAPH_HANDLE_POSITIONS: Array<{ id: GraphSide; position: Position }> = [
  { id: 'top', position: Position.Top },
  { id: 'right', position: Position.Right },
  { id: 'bottom', position: Position.Bottom },
  { id: 'left', position: Position.Left },
];

function positionForNode(node: OntologyGraphNode, allNodes: OntologyGraphNode[]): { x: number; y: number } {
  const level = node.level || 0;
  if (level === 0) return GRAPH_CENTER;
  const siblings = allNodes.filter((item) => (item.level || 0) === level && item.parent_id === node.parent_id);
  const index = Math.max(siblings.findIndex((item) => item.id === node.id), 0);
  if (level === 1) {
    const angle = firstRingAngle(node, index, siblings.length);
    return {
      x: GRAPH_CENTER.x + Math.cos(angle) * FIRST_RING_RADIUS.x,
      y: GRAPH_CENTER.y + Math.sin(angle) * FIRST_RING_RADIUS.y,
    };
  }
  const parent = allNodes.find((item) => item.id === node.parent_id);
  const parentSiblings = allNodes.filter((item) => (item.level || 0) === 1 && item.parent_id === parent?.parent_id);
  const parentIndex = Math.max(parentSiblings.findIndex((item) => item.id === parent?.id), 0);
  const baseAngle = parent ? firstRingAngle(parent, parentIndex, parentSiblings.length) : -Math.PI / 2;
  const spread = Math.min(Math.PI * 0.82, Math.max(0.34, siblings.length * 0.18));
  const step = siblings.length > 1 ? spread / (siblings.length - 1) : 0;
  const angle = baseAngle + (index - (siblings.length - 1) / 2) * step;
  return {
    x: GRAPH_CENTER.x + Math.cos(angle) * SECOND_RING_RADIUS.x,
    y: GRAPH_CENTER.y + Math.sin(angle) * SECOND_RING_RADIUS.y,
  };
}

function graphNodeStyle(node: OntologyGraphNode, selected: boolean) {
  const isBrand = node.type === 'brand';
  const isMetric = node.type === 'metric';
  const isRecommendation = node.type === 'recommendation' || node.id.includes('recommendation');
  return {
    border: selected ? '2px solid var(--brand-primary)' : '1px solid var(--border-subtle)',
    borderRadius: isBrand ? 18 : 14,
    padding: isBrand ? 18 : 12,
    background: isBrand
      ? 'var(--brand-soft)'
      : isRecommendation
        ? 'var(--status-warning-bg)'
        : isMetric
          ? 'var(--bg-primary)'
          : 'var(--bg-secondary)',
    color: 'var(--text-primary)',
    minWidth: isBrand ? 150 : 132,
    boxShadow: selected ? '0 12px 30px rgba(20, 78, 70, 0.14)' : '0 8px 20px rgba(20, 78, 70, 0.04)',
  };
}

function buildGalaxyGraphData(
  sourceNodes: OntologyGraphNode[],
  sourceEdges: OntologyGraphProjection['edges'],
  visibleNodeIds: Set<string>,
  selectedId: string | null,
): GalaxyGraphData {
  const visibleNodes = sourceNodes.filter((node) => visibleNodeIds.has(node.id));
  const requiredNodes = visibleNodes.filter(
    (node) => (node.level || 0) <= 1 || node.id === selectedId || node.parent_id === selectedId,
  );
  const secondaryNodes = visibleNodes.filter((node) => !requiredNodes.some((item) => item.id === node.id));
  const cappedNodes = [...requiredNodes, ...secondaryNodes].slice(0, GALAXY_MAX_VISIBLE_NODES);
  const cappedIds = new Set(cappedNodes.map((node) => node.id));
  return {
    nodes: cappedNodes.map((node) => galaxyNodeFor(node, sourceNodes, selectedId)),
    links: sourceEdges
      .filter((edge) => cappedIds.has(edge.from) && cappedIds.has(edge.to))
      .map((edge) => galaxyLinkFor(edge, selectedId)),
    limited: visibleNodes.length > cappedNodes.length,
  };
}

function galaxyNodeFor(
  node: OntologyGraphNode,
  allNodes: OntologyGraphNode[],
  selectedId: string | null,
): GalaxyGraphNode {
  const position = galaxyPositionForNode(node, allNodes);
  const selected = node.id === selectedId;
  return {
    id: node.id,
    label: graphNodeTitle(node),
    type: node.type,
    group: galaxyGroupForNode(node),
    kind: graphNodeKind(node),
    level: node.level || 0,
    selected,
    value: node.value,
    summary: graphNodeSummary(node),
    color: galaxyColorForNode(node, selected),
    val: selected ? galaxyNodeWeight(node) + 1.6 : galaxyNodeWeight(node),
    x: position.x,
    y: position.y,
    z: position.z,
    fx: position.x,
    fy: position.y,
    fz: position.z,
  };
}

function galaxyLinkFor(
  edge: OntologyGraphProjection['edges'][number],
  selectedId: string | null,
): GalaxyGraphLink {
  const selected = edge.from === selectedId || edge.to === selectedId;
  const strong = edge.strength === 'strong';
  return {
    source: edge.from,
    target: edge.to,
    label: edge.label,
    color: selected ? 'rgba(189, 255, 237, 0.78)' : strong ? 'rgba(130, 212, 194, 0.48)' : 'rgba(180, 190, 184, 0.22)',
    width: selected ? 1.25 : strong ? 0.72 : 0.42,
  };
}

function galaxyPositionForNode(node: OntologyGraphNode, allNodes: OntologyGraphNode[]) {
  const level = node.level || 0;
  if (level === 0) return { x: 0, y: 0, z: 0 };
  const siblings = allNodes.filter((item) => (item.level || 0) === level && item.parent_id === node.parent_id);
  const index = Math.max(siblings.findIndex((item) => item.id === node.id), 0);
  if (level === 1) {
    const angle = firstRingAngle(node, index, siblings.length);
    return {
      x: Math.cos(angle) * 170,
      y: Math.sin(angle) * 130,
      z: Math.sin(angle * 2) * 66,
    };
  }
  const parent = allNodes.find((item) => item.id === node.parent_id);
  const parentSiblings = allNodes.filter((item) => (item.level || 0) === 1 && item.parent_id === parent?.parent_id);
  const parentIndex = Math.max(parentSiblings.findIndex((item) => item.id === parent?.id), 0);
  const baseAngle = parent ? firstRingAngle(parent, parentIndex, parentSiblings.length) : -Math.PI / 2;
  const spread = Math.min(Math.PI * 0.68, Math.max(0.3, siblings.length * 0.14));
  const step = siblings.length > 1 ? spread / (siblings.length - 1) : 0;
  const angle = baseAngle + (index - (siblings.length - 1) / 2) * step;
  return {
    x: Math.cos(angle) * 295,
    y: Math.sin(angle) * 230,
    z: 92 + Math.cos(index * 1.7) * 62,
  };
}

function galaxyGroupForNode(node: OntologyGraphNode) {
  if (node.type === 'brand') return 'brand';
  if (node.type === 'metric') return 'metric';
  if (node.type === 'platform') return 'platform';
  if (node.type === 'competitor') return 'competitor';
  if (node.type === 'source_domain' || node.type === 'official_domain') return 'source';
  if (node.type === 'sentiment' || node.type === 'answer_sample') return 'sample';
  if (node.type === 'recommendation') return 'recommendation';
  return 'group';
}

function galaxyColorForNode(node: OntologyGraphNode, selected: boolean) {
  if (selected) return '#FFFFFF';
  if (node.type === 'brand') return '#F8FFFB';
  if (node.type === 'metric') return '#9BE8D6';
  if (node.type === 'group') return '#DCE6E0';
  if (node.type === 'platform') return '#C9E8E0';
  if (node.type === 'competitor') return '#FFD7A1';
  if (node.type === 'official_domain') return '#AAFFE9';
  if (node.type === 'source_domain') return '#D5D9EF';
  if (node.type === 'recommendation') return '#FFC66D';
  if (node.type === 'sentiment' || node.type === 'answer_sample') return '#F0E8FF';
  return '#DCE6E0';
}

function galaxyNodeWeight(node: OntologyGraphNode) {
  if (node.type === 'brand') return 8;
  if (node.type === 'metric') return 5.6;
  if (node.type === 'group') return 5.1;
  if ((node.level || 0) <= 1) return 4.4;
  return 2.9;
}

function buildGalaxyNodeSprite(node: GalaxyGraphNode): Object3D {
  const group = new Group();
  const level = node.level || 0;
  const baseSize = level === 0 ? 36 : level === 1 ? 22 : 13;
  const haloTexture = createGalaxyHaloTexture(node.color, node.selected);
  const haloMaterial = new SpriteMaterial({
    map: haloTexture,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: AdditiveBlending,
  });
  const halo = new Sprite(haloMaterial);
  halo.renderOrder = 8;
  halo.scale.set(baseSize * 3.8, baseSize * 3.8, 1);
  group.add(halo);

  const coreTexture = createGalaxyCoreTexture(node.color);
  const coreMaterial = new SpriteMaterial({
    map: coreTexture,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: AdditiveBlending,
  });
  const core = new Sprite(coreMaterial);
  core.renderOrder = 12;
  core.scale.set(baseSize, baseSize, 1);
  group.add(core);

  if (level <= 1 || node.selected) {
    const label = new Sprite(
      new SpriteMaterial({
        map: createGalaxyLabelTexture(node),
        transparent: true,
        depthWrite: false,
        depthTest: false,
      }),
    );
    label.renderOrder = 15;
    label.position.set(0, -baseSize * 1.45, 0);
    const labelWidth = level === 0 ? 118 : 92;
    label.scale.set(labelWidth, labelWidth * 0.28, 1);
    group.add(label);
  }

  return group;
}

function createGalaxyHaloTexture(color: string, selected: boolean) {
  const canvas = document.createElement('canvas');
  canvas.width = 160;
  canvas.height = 160;
  const context = canvas.getContext('2d');
  if (!context) return new CanvasTexture(canvas);
  const gradient = context.createRadialGradient(80, 80, 0, 80, 80, 80);
  gradient.addColorStop(0, selected ? 'rgba(255, 255, 255, 1)' : 'rgba(255, 255, 255, 0.92)');
  gradient.addColorStop(0.18, hexToRgba(color, selected ? 0.88 : 0.66));
  gradient.addColorStop(0.48, hexToRgba(color, selected ? 0.34 : 0.18));
  gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, 160, 160);
  const texture = new CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function createGalaxyCoreTexture(color: string) {
  const canvas = document.createElement('canvas');
  canvas.width = 96;
  canvas.height = 96;
  const context = canvas.getContext('2d');
  if (!context) return new CanvasTexture(canvas);
  const gradient = context.createRadialGradient(48, 48, 0, 48, 48, 48);
  gradient.addColorStop(0, '#FFFFFF');
  gradient.addColorStop(0.42, color);
  gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, 96, 96);
  const texture = new CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function createGalaxyLabelTexture(node: GalaxyGraphNode) {
  const canvas = document.createElement('canvas');
  const width = 420;
  const height = 118;
  const ratio = 2;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext('2d');
  if (!context) return new CanvasTexture(canvas);
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.shadowColor = hexToRgba(node.color, 0.88);
  context.shadowBlur = 12;
  context.fillStyle = 'rgba(255, 255, 255, 0.92)';
  context.font = `${node.level === 0 ? 30 : 24}px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
  context.fillText(truncateGraphLabel(node.label, node.level === 0 ? 12 : 10), width / 2, node.value ? 46 : 58);
  if (node.value) {
    context.shadowBlur = 8;
    context.fillStyle = hexToRgba(node.color, 0.92);
    context.font = '20px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    context.fillText(truncateGraphLabel(String(node.value), 14), width / 2, 78);
  }
  const texture = new CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function hexToRgba(value: string, alpha: number) {
  const normalized = value.replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return `rgba(255, 255, 255, ${alpha})`;
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function truncateGraphLabel(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
}

function hasWebGLSupport() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    return Boolean(
      window.WebGLRenderingContext &&
        (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')),
    );
  } catch {
    return false;
  }
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const timer = window.setTimeout(() => setReduced(media.matches), 0);
    const onChange = () => setReduced(media.matches);
    media.addEventListener?.('change', onChange);
    return () => {
      window.clearTimeout(timer);
      media.removeEventListener?.('change', onChange);
    };
  }, []);
  return reduced;
}

function firstRingAngle(node: OntologyGraphNode, fallbackIndex: number, fallbackTotal: number) {
  const key = node.metric_key || node.id;
  const slots: Record<string, number> = {
    mention_rate: -Math.PI / 2,
    mention_ranking: -Math.PI / 4,
    official_citation_rate: 0,
    sentiment_distribution: Math.PI / 4,
    'group:competitors': Math.PI / 2,
    'group:platforms': (Math.PI * 3) / 4,
    'group:sources': Math.PI,
    'group:recommendations': (-Math.PI * 3) / 4,
  };
  if (slots[key] !== undefined) return slots[key];
  return (Math.PI * 2 * fallbackIndex) / Math.max(fallbackTotal, 1) - Math.PI / 2;
}

function graphEdgeHandles(edge: { from: string; to: string }, allNodes: OntologyGraphNode[]) {
  const from = allNodes.find((node) => node.id === edge.from);
  const to = allNodes.find((node) => node.id === edge.to);
  if (!from || !to) return {};
  const fromPosition = positionForNode(from, allNodes);
  const toPosition = positionForNode(to, allNodes);
  const sourceSide = graphSideBetween(fromPosition, toPosition);
  const targetSide = graphSideBetween(toPosition, fromPosition);
  return {
    sourceHandle: `source-${sourceSide}`,
    targetHandle: `target-${targetSide}`,
  };
}

function graphSideBetween(from: { x: number; y: number }, to: { x: number; y: number }): GraphSide {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.abs(dx) > Math.abs(dy)) return dx >= 0 ? 'right' : 'left';
  return dy >= 0 ? 'bottom' : 'top';
}

function groupOwnsExpandedNode(node: OntologyGraphNode, expanded: Set<string>) {
  return (
    (node.type === 'platform' && expanded.has('group:platforms')) ||
    (node.type === 'competitor' && expanded.has('group:competitors')) ||
    ((node.type === 'source_domain' || node.type === 'official_domain') && expanded.has('group:sources')) ||
    (node.type === 'recommendation' && expanded.has('group:recommendations'))
  );
}

function groupOwnsNode(node: OntologyGraphNode, groupId: string) {
  return (
    (node.type === 'platform' && groupId === 'group:platforms') ||
    (node.type === 'competitor' && groupId === 'group:competitors') ||
    ((node.type === 'source_domain' || node.type === 'official_domain') && groupId === 'group:sources') ||
    (node.type === 'recommendation' && groupId === 'group:recommendations')
  );
}

function shouldShowGraphEdge(
  edge: { from: string; to: string },
  nodeById: Map<string, OntologyGraphNode>,
  expanded: Set<string>,
) {
  const from = nodeById.get(edge.from);
  const to = nodeById.get(edge.to);
  if (!from || !to) return true;
  const fromLevel = from.level || 0;
  const toLevel = to.level || 0;
  if (fromLevel === 0 && toLevel === 1) return true;
  if (toLevel >= 2) {
    return to.parent_id === edge.from || (expanded.has(edge.from) && groupOwnsNode(to, edge.from));
  }
  return true;
}

function graphNodeTitle(node: OntologyGraphNode) {
  if (node.type === 'platform') return platformLabel(node.label);
  return node.label;
}

function graphNodeKind(node: OntologyGraphNode) {
  const kinds: Record<string, string> = {
    brand: '品牌',
    metric: '指标',
    group: '分类',
    platform: 'AI 平台',
    competitor: '竞品',
    official_domain: '官网',
    source_domain: '引用来源',
    sentiment: '语气样本',
    answer_sample: '回答样本',
    recommendation: '跟进建议',
  };
  return kinds[node.type] || '相关内容';
}

function graphNodeSummary(node: OntologyGraphNode) {
  if (node.type === 'platform' && node.value) return `${graphNodeTitle(node)} 提及率 ${node.value}`;
  if (node.type === 'official_domain' && node.value) return `官网引用 ${node.value} 次`;
  if (node.type === 'source_domain' && node.value) return `${node.value} 次引用`;
  if (node.type === 'competitor' && node.value) return `竞品提及率 ${node.value}`;
  if (node.type === 'sentiment' && node.value) return `${node.value} 条样本`;
  if (node.type === 'answer_sample') {
    return [node.value ? platformLabel(node.value) : '', cleanEvidenceText(node.summary, '')].filter(Boolean).join(' · ');
  }
  return cleanEvidenceText(node.summary, '');
}

function graphRelationsForNode(
  node: OntologyGraphNode,
  edges: OntologyGraphProjection['edges'],
  nodeById: Map<string, OntologyGraphNode>,
): GraphRelationView[] {
  const relations: GraphRelationView[] = [];
  edges.forEach((edge) => {
    if (edge.from === node.id) {
      const other = nodeById.get(edge.to);
      if (other) {
        relations.push({ direction: 'out', label: edge.label, edge, other });
      }
      return;
    }
    if (edge.to === node.id) {
      const other = nodeById.get(edge.from);
      if (other) {
        relations.push({ direction: 'in', label: edge.label, edge, other });
      }
    }
  });
  return relations;
}

function graphNodeMeaning(node: OntologyGraphNode, summary: OntologySummaryProjection) {
  const brandName = summary.brand?.name || '当前品牌';
  if (node.business_meaning) return cleanEvidenceText(node.business_meaning, '这项内容帮助解释品牌表现。');
  if (node.type === 'brand') return `${brandName} 是本页所有问题、回答、引用、竞品和建议的中心。`;
  if (node.type === 'metric') {
    if (node.metric_key === 'mention_rate') return '判断品牌是否进入 AI 回答，以及进入了多少回答。';
    if (node.metric_key === 'mention_ranking') return '比较品牌和竞品在同一批问题里的提及情况。';
    if (node.metric_key === 'official_citation_rate') return '判断 AI 回答是否引用品牌官网或官网别名域名。';
    if (node.metric_key === 'sentiment_distribution') return '观察 AI 提到品牌时的描述倾向。';
    return '这是当前品牌表现的一个核心指标。';
  }
  if (node.type === 'platform') return '这是产生回答样本的 AI 平台，用来判断平台差异。';
  if (node.type === 'competitor') return '这是和当前品牌进入同一批问题比较的竞品。';
  if (node.type === 'official_domain') return '这是品牌官网，判断 AI 是否引用品牌自有信息。';
  if (node.type === 'source_domain') return '这是 AI 回答引用过的来源域名，用来判断信息依据来自哪里。';
  if (node.type === 'sentiment') return '这是已提及品牌回答里的语气分组。';
  if (node.type === 'answer_sample') return '这是 AI 提到品牌时的一条代表性回答摘录。';
  if (node.type === 'recommendation') return '这是根据指标缺口生成的下一步处理建议。';
  return '这组内容帮助你从品牌表现继续展开证据。';
}

function graphNodeRelationText(node: OntologyGraphNode, relations: GraphRelationView[]) {
  if (node.type === 'brand') return '所有指标、平台、竞品、来源和建议都围绕这个品牌汇总。';
  if (!relations.length) return '当前没有可解释关系，建议先查看上一级内容。';
  const relation = relations[0];
  return relation.edge.business_meaning
    ? cleanEvidenceText(relation.edge.business_meaning, '这条关系用于解释品牌表现。')
    : `${graphNodeTitle(node)}与${graphNodeTitle(relation.other)}存在“${relation.label}”关系。`;
}

function graphNodeEvidenceText(node: OntologyGraphNode, summary: OntologySummaryProjection) {
  const scope = summary.sample_scope || {};
  if (typeof node.evidence_count === 'number' && node.evidence_count > 0) {
    return `${node.evidence_count} 条相关证据，可从情报来源继续查看。`;
  }
  if (node.type === 'brand') {
    return `${scope.platform_count ?? 0} 个平台、${scope.question_count ?? 0} 个问题、${scope.answer_count ?? 0} 条答案样本。`;
  }
  if (node.type === 'metric' && node.metric_key) {
    const metric = summary.metrics?.[node.metric_key as EvidenceTab];
    if (node.metric_key === 'mention_ranking') {
      const reason = metric?.sample_sufficiency?.rank_reason;
      return reason || '同一批问题和平台下的品牌提及率对比。';
    }
    if (metric?.numerator !== undefined && metric?.denominator !== undefined) {
      return `${metric.numerator} / ${metric.denominator}，可在“情报来源”里查看样本。`;
    }
  }
  if (node.type === 'platform') return '点击 AI 提及率，可查看该平台下的提及和未提及回答。';
  if (node.type === 'competitor') return '点击提及排名，可查看当前品牌和竞品的同场样本。';
  if (node.type === 'official_domain') return '点击官网引用率，可查看官网引用次数和官网样本。';
  if (node.type === 'source_domain') return '点击官网引用率，可查看官网和外部来源的引用明细。';
  if (node.type === 'sentiment') return '点击语气性质，可查看正向、中性或负向回答片段。';
  if (node.type === 'answer_sample') return node.summary || '可在语气性质里查看同类回答片段。';
  if (node.type === 'recommendation') return '在跟进反馈里可以查看内容方向、投放位置和复查指标。';
  return '可从情报来源继续查看问题、回答和引用样本。';
}

function businessRelationVerb(relation: GraphRelationView) {
  if (relation.edge.type === 'compares') return '被比较：';
  if (relation.edge.type === 'cites' || relation.edge.type === 'official_source') return '被引用：';
  if (relation.edge.type === 'breakdown') return '拆分到：';
  if (relation.edge.type === 'recommends') return '建议：';
  if (relation.edge.type === 'contains') return '包含：';
  return relation.direction === 'out' ? '关系：' : '来源：';
}

function metricLabelFor(key: EvidenceTab) {
  if (key === 'mention_rate') return 'AI 提及率';
  if (key === 'mention_ranking') return '提及排名';
  if (key === 'official_citation_rate') return '官网引用率';
  return '语气性质';
}

function isEvidenceTab(value?: string | null): value is EvidenceTab {
  return (
    value === 'mention_rate' ||
    value === 'mention_ranking' ||
    value === 'official_citation_rate' ||
    value === 'sentiment_distribution'
  );
}

function targetMetricLabel(value?: string) {
  if (value === 'mention_rate') return 'AI 提及率';
  if (value === 'mention_ranking') return '提及排名';
  if (value === 'official_citation_rate') return '官网引用率';
  if (value === 'sentiment_distribution') return '语气性质';
  return value || '当前指标';
}

function sentimentLabel(value?: string) {
  if (value === 'positive') return '正向';
  if (value === 'negative') return '负向';
  if (value === 'not_mentioned') return '未提及';
  return '中性';
}

function cleanEvidenceText(value?: string | null, fallback = '证据样本待补充') {
  const text = (value || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !looksLikeInternalProcessText(line))
    .join(' ')
    .replace(/[^。！？.!?]*web[_\s-]*search[^。！？.!?]*(?:[。！？.!?]|$)/gi, ' ')
    .replace(/[^。！？.!?]*(?:调用工具|工具调用|浏览器工具|推理过程|思考过程|内部过程|调度日志|模型过程)[^。！？.!?]*(?:[。！？.!?]|$)/gi, ' ')
    .replace(/[^。！？.!?]*(?:作为\s*AI|我将|首先我需要|接下来我会)[^。！？.!?]*(?:[。！？.!?]|$)/gi, ' ')
    .replace(/\p{Extended_Pictographic}/gu, '')
    .replace(/[#*_`>~]/g, '')
    .replace(/\|[-:\s|]+\|/g, ' ')
    .replace(/\s*\|\s*/g, '，')
    .replace(/\s+/g, ' ')
    .trim();
  if (!text || looksLikeInternalQuestionLabel(text)) return fallback;
  return text;
}

function looksLikeInternalProcessText(value: string) {
  return /(prompt|debug|trace|chain[-_ ]?of[-_ ]?thought|web[_\s-]*search|调用工具|工具调用|浏览器工具|推理过程|思考过程|内部过程|调度日志|模型过程|作为\s*AI|我将|首先我需要|接下来我会)/i.test(value);
}

function looksLikeInternalQuestionLabel(value: string) {
  const text = value.trim().toLowerCase().replace(/^问题\s*/, '');
  return /^(q|question|id)[_-]?\d+$/.test(text) || /^\d+$/.test(text);
}

function platformLabel(value?: string) {
  const key = String(value || '').toLowerCase();
  const labels: Record<string, string> = {
    yuanbao: '腾讯元宝',
    doubao: '豆包',
    deepseek: 'DeepSeek',
    kimi: 'Kimi',
    chatgpt: 'ChatGPT',
  };
  return labels[key] || value || '未知平台';
}

function percent(value: unknown) {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '样本不足';
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

export default BrandOntologyHome;

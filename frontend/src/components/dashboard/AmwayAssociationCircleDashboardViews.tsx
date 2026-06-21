import { useState, type ChangeEvent } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Download,
  MessageCircle,
  RefreshCw,
  Upload,
  X,
} from 'lucide-react';
import type { DashboardHomeData } from '@/types/dashboard';
import type {
  OntologyAssociationCircleEvidence,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleAnalysisTraceItem,
  OntologyAssociationCircleNarrativeSection,
  OntologyAssociationCircleNode,
  OntologyAssociationCirclePlatformSourceSummary,
  OntologyAssociationCirclePlatformComparison,
  OntologyAssociationCirclePriorityItem,
  OntologyAssociationCirclePrioritySummary,
  OntologyAssociationCircleProjection,
  OntologyAssociationCircleQuestionDefinition,
  OntologyAssociationCircleQuestion,
  OntologyAssociationCircleSourceAppendixItem,
  OntologyAssociationCircleStrategyValidation,
  OntologyWorldSummary,
} from '@/types/ontology';
import {
  displayQuestionMetadataStatus,
  hasVisibleAssociationTags,
  normalizeAssociationQuestionForReview,
} from './amwayQuestionBank';
import type { UploadedAssociationQuestion } from './AmwayAssociationCircleDashboard';

type AssociationMapGroupKey = 'strong' | 'growth' | 'story' | 'risk';
type AssociationMapMode = 'associations' | 'risk';
type AssociationMapViewMode = 'flat' | 'spatial';
type OrbitDistanceBand = 'near' | 'bridge' | 'far' | 'risk';
type AssociationNodeFilterKey = 'stable' | 'opportunity' | 'watch';
type ReportNarrativeSection = {
  sectionId?: string;
  title: string;
  text: string;
  readerQuestion?: string;
  takeaway?: string;
  claims?: string[];
  soWhat?: string;
  supportingFacts?: string[];
  evidenceRefs?: string[];
  nextProbe?: string;
};

type OrbitEvidenceItem = {
  evidence_id?: string;
  node_id?: string;
  node_term?: string;
  platform?: string;
  question_id?: string;
  question?: string;
  answer_excerpt?: string;
};

type PlatformEvidenceSummary = {
  platform: string;
  label: string;
  answerCount: number;
  questionCount: number;
  samples: OrbitEvidenceItem[];
};

const DEFAULT_CENTER_TERMS = ['安利', '安利中国', '纽崔莱'];
const REPORT_SERIF_FONT = 'ui-serif, "Noto Serif SC", "Source Han Serif SC", "Songti SC", Georgia, serif';
const QUESTION_PAGE_SIZE = 8;

export function AssociationProjectionLoadingPanel({ centerTerm }: { centerTerm: string }) {
  return (
    <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
      <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]">
          <RefreshCw size={20} className="animate-spin" />
        </div>
        <h2 className="mt-5 text-2xl font-semibold">{centerTerm}圈层报告读取中</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
          正在读取最近一次图谱、报告和证据链。读取完成前不会展示空态，也不会把已有结果误判为未生成。
        </p>
      </div>
    </section>
  );
}

export function InfoPill({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  tone?: 'brand' | 'warning' | 'neutral';
}) {
  const className =
    tone === 'brand'
      ? 'border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]'
      : tone === 'warning'
        ? 'border-[var(--status-warning-bg)] bg-[var(--status-warning-bg)] text-[var(--text-secondary)]'
        : 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  return (
    <span className={`rounded-full border px-3 py-1 ${className}`}>
      <span className="font-medium">{label}：</span>{value}
    </span>
  );
}

function QuestionUploadButton({
  isReadingUpload,
  onUploadFileChange,
  compact = false,
}: {
  isReadingUpload: boolean;
  onUploadFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  compact?: boolean;
}) {
  return (
    <label
      className={`inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--brand-border)] bg-[var(--bg-primary)] text-sm font-medium text-[var(--brand-primary)] hover:bg-[var(--brand-bg)] ${
        compact ? 'h-9 px-3' : 'px-4 py-2'
      }`}
    >
      <Upload size={16} />
      {isReadingUpload ? '正在读取' : '上传问题'}
      <input
        type="file"
        accept=".csv,.xlsx,.txt,text/csv,text/plain,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="sr-only"
        disabled={isReadingUpload}
        onChange={onUploadFileChange}
      />
    </label>
  );
}

interface AssociationMapGroup {
  key: AssociationMapGroupKey;
  title: string;
  subtitle: string;
  emptyText: string;
  tone: 'brand' | 'opportunity' | 'story' | 'risk';
  nodes: OntologyAssociationCircleNode[];
}

interface AssociationNodeFilterOption {
  key: AssociationNodeFilterKey;
  label: string;
  hint: string;
  count: number;
  tone: 'strong' | 'growth' | 'story';
}

export function CommercialOrbitView({
  centerTerm,
  groups,
  selectedNode,
  selectedNodeId,
  sampleScope,
  targetPlatforms = [],
  liveProgressMessage = null,
  liveCurrentStage = null,
  evidenceSamples,
  evidenceFindings,
  sourceAppendix,
  strategyTerms,
  prioritySummary,
  onSelectNode,
}: {
  centerTerm: string;
  groups: AssociationMapGroup[];
  selectedNode: OntologyAssociationCircleNode | null;
  selectedNodeId: string | null;
  sampleScope: Record<string, unknown>;
  targetPlatforms?: string[];
  liveProgressMessage?: string | null;
  liveCurrentStage?: string | null;
  evidenceSamples: OntologyAssociationCircleEvidence[];
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  strategyTerms: string[];
  prioritySummary?: OntologyAssociationCirclePrioritySummary | null;
  onSelectNode: (nodeId: string | null) => void;
}) {
  const [mapMode, setMapMode] = useState<AssociationMapMode>('associations');
  const [activeNodeFilters, setActiveNodeFilters] = useState<AssociationNodeFilterKey[]>([]);
  const [hoverTrackFilter, setHoverTrackFilter] = useState<AssociationNodeFilterKey | null>(null);
  const viewMode: AssociationMapViewMode = 'flat';
  const riskGroup = groups.find((group) => group.key === 'risk') || null;
  const riskNodes = riskGroup?.nodes || [];
  const associationGroups = groups.filter((group) => group.key !== 'risk');
  const showDefaultRiskNodes = mapMode === 'associations' && activeNodeFilters.length === 0;
  const filterOptions = buildAssociationNodeFilterOptions(associationGroups);
  const activeTrackFilter = activeNodeFilters[0] || null;
  const visibleGroups = mapMode === 'risk'
    ? (riskGroup ? [riskGroup] : [])
    : associationGroups;
  const strongest = visibleGroups.find((group) => group.key === 'strong')?.nodes[0] || null;
  const opportunity = visibleGroups.find((group) => group.key === 'growth')?.nodes[0] || visibleGroups.find((group) => group.key === 'story')?.nodes[0] || null;
  const selectedGroupKey = selectedNode ? classifyAssociationNode(selectedNode) : null;
  const selectedRiskNodeVisible = selectedGroupKey === 'risk' && (
    mapMode === 'risk' || showDefaultRiskNodes
  );
  const selectedAssociationNodeVisible = Boolean(
    selectedNode
    && selectedGroupKey
    && selectedGroupKey !== 'risk'
    && mapMode === 'associations'
    && nodePassesAssociationFilters(selectedNode, selectedGroupKey, activeNodeFilters),
  );
  const selectedNodeInMode = selectedNode && (
    selectedRiskNodeVisible || selectedAssociationNodeVisible
  )
    ? selectedNode
    : null;
  const focusNode = selectedNodeInMode || (mapMode === 'risk' ? riskNodes[0] || null : strongest || opportunity);
  const isLivePreview = String(sampleScope?.status || '') === 'live_preview';
  const liveStats = readLiveExtractionStats(sampleScope);
  const targetPlatformNames = uniqueStrings(targetPlatforms.map((platform) => platformLabel(platform)).filter(Boolean));
  const totalAssociationNodeCount = associationGroups.reduce((total, group) => total + group.nodes.length, 0);
  const totalDefaultNodeCount = totalAssociationNodeCount + riskNodes.length;
  const trackCounts = {
    stable: associationGroups.find((group) => group.key === 'strong')?.nodes.length || 0,
    opportunity: associationGroups.find((group) => group.key === 'growth')?.nodes.length || 0,
    watch: associationGroups.find((group) => group.key === 'story')?.nodes.length || 0,
  };
  const previewTrackFilter = hoverTrackFilter || activeTrackFilter;
  const visibleNodeCount = previewTrackFilter
    ? trackCounts[previewTrackFilter]
    : totalDefaultNodeCount;
  const updateNodeFilters = (nextFilters: AssociationNodeFilterKey[]) => {
    setActiveNodeFilters(nextFilters);
    if (
      selectedNode
      && selectedGroupKey
      && selectedGroupKey !== 'risk'
      && !nodePassesAssociationFilters(selectedNode, selectedGroupKey, nextFilters)
    ) {
      onSelectNode(null);
    }
  };
  const closeRiskView = () => {
    setMapMode('associations');
    onSelectNode(null);
  };
  const openRiskView = () => {
    setMapMode('risk');
    setHoverTrackFilter(null);
    onSelectNode(null);
  };

  return (
    <section className="space-y-5">
      <section className="space-y-5">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
            <div>
              <h2 className="text-2xl font-semibold">
                {mapMode === 'risk' ? `${centerTerm} 风险认知关系图` : `${centerTerm} 品牌联想圈层图`}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-tertiary)]">
                {mapMode === 'risk'
                  ? '当前只展开风险认知：看回答如何把品牌带向需要澄清的旧认知，以及这些风险来自哪些语境。'
                  : '每条轨道是一种关系状态：绿色稳定，黄色可拉近，灰色待观察，红色为风险关系。'}
              </p>
              <OrbitMapReadingGuide mapMode={mapMode} />
              {mapMode === 'associations' && totalAssociationNodeCount > 0 ? (
                <AssociationNodeFilterBar
                  options={filterOptions}
                  activeFilters={activeNodeFilters}
                  totalCount={totalDefaultNodeCount}
                  visibleCount={visibleNodeCount}
                  riskCount={riskNodes.length}
                  previewFilter={hoverTrackFilter}
                  onChange={updateNodeFilters}
                  onPreviewChange={setHoverTrackFilter}
                  onOpenRiskView={openRiskView}
                />
              ) : null}
              {isLivePreview ? (
                <LiveExtractionStatusStrip
                  answerCount={liveStats.answerCount}
                  signalCount={liveStats.signalCount}
                  eventCount={liveStats.eventCount}
                  nodeCount={visibleNodeCount}
                  targetPlatforms={targetPlatformNames}
                  progressMessage={liveProgressMessage}
                  currentStage={liveCurrentStage}
                />
              ) : null}
            </div>
            <div className="flex flex-wrap justify-end gap-2 text-xs text-[var(--text-secondary)]">
              {isLivePreview && targetPlatformNames.length ? (
                <InfoPill label="目标平台" value={String(targetPlatformNames.length)} />
              ) : null}
              <InfoPill label="有效回答" value={String(sampleAnswerCount(sampleScope) || '-')} />
              <InfoPill label="有效平台" value={String(samplePlatformCount(sampleScope) || '-')} />
            </div>
          </div>
          <PriorityFocusStrip
            summary={prioritySummary}
            groups={groups}
            onSelectNode={onSelectNode}
            onOpenRiskView={openRiskView}
          />
          <CommercialOrbitMap
            centerTerm={centerTerm}
            groups={visibleGroups}
            mapMode={mapMode}
            viewMode={viewMode}
            riskNodes={riskNodes}
            showDefaultRiskNodes={showDefaultRiskNodes}
            focusNode={focusNode}
            evidenceSamples={evidenceSamples}
            evidenceFindings={evidenceFindings}
            sourceAppendix={sourceAppendix}
            strategyTerms={strategyTerms}
            sampleScope={sampleScope}
            targetPlatforms={targetPlatformNames}
            liveProgressMessage={liveProgressMessage}
            liveCurrentStage={liveCurrentStage}
            selectedNodeId={focusNode?.node_id === selectedNodeId ? selectedNodeId : null}
            isLivePreview={isLivePreview}
            onSelectNode={onSelectNode}
            onOpenRiskView={openRiskView}
            onExitRiskView={closeRiskView}
            activeTrackFilter={activeTrackFilter}
            hoverTrackFilter={hoverTrackFilter}
            onHoverTrackFilterChange={setHoverTrackFilter}
            onTrackFilterChange={(track) => updateNodeFilters(activeTrackFilter === track ? [] : [track])}
          />
        </div>
      </section>
    </section>
  );
}

function LiveExtractionStatusStrip({
  answerCount,
  signalCount,
  eventCount,
  nodeCount,
  targetPlatforms,
  progressMessage,
  currentStage,
}: {
  answerCount: number;
  signalCount: number;
  eventCount: number;
  nodeCount: number;
  targetPlatforms: string[];
  progressMessage?: string | null;
  currentStage?: string | null;
}) {
  const cleanProgress = cleanWorkflowProgressMessage(progressMessage);
  const stageLabel = currentStage ? currentStage.toUpperCase() : 'A4';
  const steps = [
    { label: '目标平台', value: targetPlatforms.length ? `${targetPlatforms.length} 个` : '读取中', active: targetPlatforms.length > 0 },
    { label: `${stageLabel} 抓取`, value: cleanProgress || '进行中', active: true },
    { label: '回答入库', value: answerCount ? `${answerCount} 条` : '等待首条', active: answerCount > 0 },
    { label: '抽取事件', value: eventCount ? `${eventCount} 条` : '等待事件', active: eventCount > 0 },
    { label: '实体信号', value: signalCount ? `${signalCount} 个` : '等待信号', active: signalCount > 0 },
    { label: '图谱入轨', value: nodeCount ? `${nodeCount} 个节点` : '等待节点', active: nodeCount > 0 },
    { label: '校准收束', value: eventCount ? '抓完后确认' : '排队中', active: false },
  ];

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-[var(--brand-border)] bg-[var(--brand-bg)] px-3 py-2 text-xs">
      <span className="inline-flex items-center gap-2 font-semibold text-[var(--brand-primary)]">
        <span className="h-2 w-2 rounded-full bg-[var(--brand-primary)] shadow-[0_0_0_5px_rgba(31,122,107,0.10)]" />
        实时入轨中
      </span>
      {steps.map((step) => (
        <span
          key={step.label}
          className="inline-flex items-center gap-1.5 rounded-full border bg-[var(--bg-primary)] px-2.5 py-1"
          style={{
            borderColor: step.active ? 'var(--brand-border)' : 'var(--border-subtle)',
            color: step.active ? 'var(--brand-primary)' : 'var(--text-tertiary)',
          }}
        >
          <span>{step.label}</span>
          <span className="font-semibold">{step.value}</span>
        </span>
      ))}
    </div>
  );
}

function PriorityFocusStrip({
  summary,
  groups,
  onSelectNode,
  onOpenRiskView,
}: {
  summary?: OntologyAssociationCirclePrioritySummary | null;
  groups: AssociationMapGroup[];
  onSelectNode: (nodeId: string | null) => void;
  onOpenRiskView: () => void;
}) {
  const fallbackRisks = groups.find((group) => group.key === 'risk')?.nodes || [];
  const fallbackOpportunities = [
    ...(groups.find((group) => group.key === 'growth')?.nodes || []),
    ...(groups.find((group) => group.key === 'story')?.nodes || []),
  ];
  const riskItems = priorityItemsOrFallback(summary?.top_risks, fallbackRisks, 'risk');
  const competitorItems = priorityItemsOrFallback(
    summary?.top_competitors,
    fallbackRisks.filter((node) => node.business_tag === '竞争关系'),
    'competitor',
  );
  const opportunityItems = priorityItemsOrFallback(summary?.top_opportunities, fallbackOpportunities, 'opportunity');
  const hasItems = riskItems.length || competitorItems.length || opportunityItems.length;
  if (!hasItems) return null;
  return (
    <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-5 py-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">本周先看</div>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            按证据量、平台覆盖和关系性质排序。其他节点保留在图谱里作为复测背景。
          </p>
        </div>
        {riskItems.length ? (
          <button
            type="button"
            onClick={onOpenRiskView}
            className="rounded-full border border-[var(--error)] bg-[var(--bg-primary)] px-3 py-1 text-xs font-semibold text-[var(--error)] hover:bg-[var(--bg-secondary)]"
          >
            查看风险关系
          </button>
        ) : null}
      </div>
      <div className="grid gap-3 xl:grid-cols-3">
        <PriorityColumn
          title="风险先处理"
          emptyText="本轮没有高优先级风险。"
          items={riskItems}
          tone="risk"
          onSelectNode={onSelectNode}
        />
        <PriorityColumn
          title="竞品替代"
          emptyText="本轮没有明显竞品替代。"
          items={competitorItems}
          tone="competitor"
          onSelectNode={onSelectNode}
        />
        <PriorityColumn
          title="机会先拉近"
          emptyText="本轮机会词还不够稳定。"
          items={opportunityItems}
          tone="opportunity"
          onSelectNode={onSelectNode}
        />
      </div>
    </div>
  );
}

function PriorityColumn({
  title,
  emptyText,
  items,
  tone,
  onSelectNode,
}: {
  title: string;
  emptyText: string;
  items: OntologyAssociationCirclePriorityItem[];
  tone: 'risk' | 'competitor' | 'opportunity';
  onSelectNode: (nodeId: string | null) => void;
}) {
  const color = tone === 'risk'
    ? 'var(--error)'
    : tone === 'competitor'
      ? 'var(--warning)'
      : 'var(--brand-primary)';
  return (
    <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ background: color }} />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="mt-3 space-y-2">
        {items.length ? items.slice(0, 3).map((item, index) => (
          <button
            key={`${title}-${item.node_id || item.term || index}`}
            type="button"
            onClick={() => item.node_id && onSelectNode(item.node_id)}
            className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-left transition hover:border-[var(--brand-border)] hover:bg-[var(--brand-bg)]"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-sm font-semibold">
                {item.rank ? `${item.rank}. ` : ''}{item.term || '待命名节点'}
              </span>
              <span className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-0.5 text-[11px] text-[var(--text-tertiary)]">
                {item.evidence_count || 0} 条
              </span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
              {priorityItemBrief(item)}
            </p>
          </button>
        )) : (
          <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-xs leading-5 text-[var(--text-tertiary)]">
            {emptyText}
          </p>
        )}
      </div>
    </section>
  );
}

function priorityItemsOrFallback(
  items: OntologyAssociationCirclePriorityItem[] | undefined,
  nodes: OntologyAssociationCircleNode[],
  focusType: OntologyAssociationCirclePriorityItem['focus_type'],
): OntologyAssociationCirclePriorityItem[] {
  if (Array.isArray(items) && items.length) return items.slice(0, 3);
  return nodes.slice(0, 3).map((node, index) => ({
    rank: index + 1,
    node_id: node.node_id,
    term: node.term,
    focus_type: focusType,
    business_tag: node.business_tag,
    score: node.gravity_score || node.closeness_score || node.association_score,
    evidence_count: nodeEvidenceCount(node),
    platform_count: nodePlatformCount(node),
    scene_hint: (node.primary_opportunity_points || [])[0] || '',
    recommended_action: focusType === 'risk' ? '先看原文语境和澄清证据' : '补问题和证据',
  }));
}

function priorityItemBrief(item: OntologyAssociationCirclePriorityItem): string {
  const scene = item.scene_hint ? `场景：${item.scene_hint}。` : '';
  const platform = item.platform_count ? `${item.platform_count} 个平台。` : '';
  const action = item.recommended_action || '点击查看原文语境。';
  return `${scene}${platform}${action}`;
}

function cleanWorkflowProgressMessage(value?: string | null): string {
  const text = String(value || '').trim();
  if (!text) return '';
  return text
    .replace(/\s+/g, ' ')
    .replace(/^API抓取进度:\s*/i, 'API ')
    .replace(/完成（/g, '（')
    .replace(/完成\(/g, '(')
    .slice(0, 56);
}

function OrbitMapReadingGuide({ mapMode }: { mapMode: AssociationMapMode }) {
  if (mapMode === 'risk') {
    return (
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
        <OrbitGuidePill label="风险中心" text="旧认知和争议入口" tone="risk" />
        <OrbitGuidePill label="连线" text="看它如何回到品牌" />
        <OrbitGuidePill label="证据" text="点击节点查看问题、平台和回答摘录" />
      </div>
    );
  }
  return (
    <div className="mt-3 grid max-w-5xl gap-2 text-xs text-[var(--text-secondary)] xl:grid-cols-2">
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 leading-5">
        <span className="font-semibold text-[var(--text-primary)]">读图：</span>
        轨道越靠近中心，回答越容易把词带回品牌。悬停轨道带临时聚焦，点击轨道锁定，点击节点查看关系证据。
      </div>
      <div className="flex flex-wrap gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
        <OrbitGuidePill label="绿" text="稳定轨" tone="strong" />
        <OrbitGuidePill label="黄" text="机会轨" tone="growth" />
        <OrbitGuidePill label="灰" text="观察轨" tone="story" />
        <OrbitGuidePill label="红" text="风险关系" tone="risk" />
      </div>
    </div>
  );
}

function OrbitGuidePill({
  label,
  text,
  tone = 'neutral',
}: {
  label: string;
  text: string;
  tone?: 'strong' | 'growth' | 'story' | 'risk' | 'neutral';
}) {
  const color = orbitGuideToneColor(tone);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 py-1">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      <span className="font-medium" style={{ color }}>{label}</span>
      <span>{text}</span>
    </span>
  );
}

function orbitGuideToneColor(tone: 'strong' | 'growth' | 'story' | 'risk' | 'neutral') {
  if (tone === 'strong') return 'var(--brand-primary)';
  if (tone === 'growth') return 'var(--evidence-opportunity)';
  if (tone === 'risk') return 'var(--evidence-risk)';
  if (tone === 'story') return 'var(--text-tertiary)';
  return 'var(--text-secondary)';
}

function AssociationNodeFilterBar({
  options,
  activeFilters,
  totalCount,
  visibleCount,
  riskCount,
  previewFilter,
  onChange,
  onPreviewChange,
  onOpenRiskView,
}: {
  options: AssociationNodeFilterOption[];
  activeFilters: AssociationNodeFilterKey[];
  totalCount: number;
  visibleCount: number;
  riskCount: number;
  previewFilter: AssociationNodeFilterKey | null;
  onChange: (filters: AssociationNodeFilterKey[]) => void;
  onPreviewChange: (filter: AssociationNodeFilterKey | null) => void;
  onOpenRiskView: () => void;
}) {
  const allActive = activeFilters.length === 0;
  const toggleFilter = (key: AssociationNodeFilterKey) => {
    onChange(activeFilters.includes(key) ? [] : [key]);
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-xs">
      <span className="font-medium text-[var(--text-primary)]">轨道筛选</span>
      <button
        type="button"
        aria-pressed={allActive}
        onMouseEnter={() => onPreviewChange(null)}
        onFocus={() => onPreviewChange(null)}
        onClick={() => onChange([])}
        className={`rounded-full border px-2.5 py-1 font-medium transition ${
          allActive
            ? 'border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]'
            : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:border-[var(--brand-border)] hover:text-[var(--brand-primary)]'
        }`}
      >
        全部轨道 {totalCount}
      </button>
      {options.map((option) => {
        const active = activeFilters.includes(option.key);
        const previewed = previewFilter === option.key;
        const color = orbitGuideToneColor(option.tone);
        return (
          <button
            key={option.key}
            type="button"
            aria-pressed={active}
            disabled={!option.count}
            title={option.hint}
            onMouseEnter={() => onPreviewChange(option.key)}
            onMouseLeave={() => onPreviewChange(null)}
            onFocus={() => onPreviewChange(option.key)}
            onBlur={() => onPreviewChange(null)}
            onClick={() => toggleFilter(option.key)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${
              active
                ? 'bg-[var(--bg-primary)]'
                : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:border-[var(--brand-border)] hover:text-[var(--brand-primary)]'
            }`}
            style={active || previewed ? { borderColor: color, color } : undefined}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: color }} />
            {option.label} {option.count}
          </button>
        );
      })}
      <button
        type="button"
        disabled={!riskCount}
        title="进入风险认知关系图"
        onClick={onOpenRiskView}
        className="rounded-full border px-2.5 py-1 font-medium text-[var(--evidence-risk)] transition disabled:cursor-not-allowed disabled:opacity-45"
        style={{
          borderColor: 'color-mix(in srgb, var(--evidence-risk) 30%, var(--border-subtle) 70%)',
          background: 'var(--bg-primary)',
        }}
      >
        风险关系 {riskCount}
      </button>
      <span className="ml-auto text-[var(--text-tertiary)]">显示 {visibleCount} / {totalCount}</span>
    </div>
  );
}

function buildAssociationNodeFilterOptions(
  groups: AssociationMapGroup[],
): AssociationNodeFilterOption[] {
  const nodes = groups.flatMap((group) => group.nodes.map((node) => ({ node, groupKey: group.key })));
  return [
    {
      key: 'stable',
      label: '稳定轨',
      hint: '回答已经较稳定绑定品牌',
      count: nodes.filter(({ node, groupKey }) => nodePassesAssociationFilters(node, groupKey, ['stable'])).length,
      tone: 'strong',
    },
    {
      key: 'opportunity',
      label: '机会轨',
      hint: '已有连接，还需要更多直接证据',
      count: nodes.filter(({ node, groupKey }) => nodePassesAssociationFilters(node, groupKey, ['opportunity'])).length,
      tone: 'growth',
    },
    {
      key: 'watch',
      label: '观察轨',
      hint: '远端机会或待观察词',
      count: nodes.filter(({ node, groupKey }) => nodePassesAssociationFilters(node, groupKey, ['watch'])).length,
      tone: 'story',
    },
  ];
}

function nodePassesAssociationFilters(
  _node: OntologyAssociationCircleNode,
  groupKey: AssociationMapGroupKey | null,
  activeFilters: AssociationNodeFilterKey[],
): boolean {
  if (!activeFilters.length) return true;
  return activeFilters.some((filterKey) => {
    if (filterKey === 'stable') return groupKey === 'strong';
    if (filterKey === 'opportunity') return groupKey === 'growth';
    if (filterKey === 'watch') return groupKey === 'story';
    return false;
  });
}

function CommercialOrbitMap({
  centerTerm,
  groups,
  mapMode,
  viewMode,
  riskNodes,
  showDefaultRiskNodes,
  focusNode,
  evidenceSamples,
  evidenceFindings,
  sourceAppendix,
  strategyTerms,
  sampleScope,
  targetPlatforms,
  liveProgressMessage,
  liveCurrentStage,
  selectedNodeId,
  isLivePreview,
  onSelectNode,
  onOpenRiskView,
  onExitRiskView,
  activeTrackFilter,
  hoverTrackFilter,
  onHoverTrackFilterChange,
  onTrackFilterChange,
}: {
  centerTerm: string;
  groups: AssociationMapGroup[];
  mapMode: AssociationMapMode;
  viewMode: AssociationMapViewMode;
  riskNodes: OntologyAssociationCircleNode[];
  showDefaultRiskNodes: boolean;
  focusNode: OntologyAssociationCircleNode | null;
  evidenceSamples: OntologyAssociationCircleEvidence[];
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  strategyTerms: string[];
  sampleScope: Record<string, unknown>;
  targetPlatforms: string[];
  liveProgressMessage?: string | null;
  liveCurrentStage?: string | null;
  selectedNodeId: string | null;
  isLivePreview?: boolean;
  onSelectNode: (nodeId: string | null) => void;
  onOpenRiskView: () => void;
  onExitRiskView: () => void;
  activeTrackFilter: AssociationNodeFilterKey | null;
  hoverTrackFilter: AssociationNodeFilterKey | null;
  onHoverTrackFilterChange: (track: AssociationNodeFilterKey | null) => void;
  onTrackFilterChange: (track: AssociationNodeFilterKey) => void;
}) {
  const entries = mapMode === 'risk'
    ? buildRiskMapEntries(riskNodes)
    : buildCommercialOrbitEntries(groups, showDefaultRiskNodes ? riskNodes : []);
  const focusNodeId = selectedNodeId || focusNode?.node_id || null;
  const isRiskMode = mapMode === 'risk';
  const isSpatialMode = !isRiskMode && viewMode === 'spatial';
  const focusTrackFilter = hoverTrackFilter || activeTrackFilter;
  const focusGroupKey = trackFilterToGroupKey(focusTrackFilter);
  const selectedFocusNodeId = selectedNodeId || null;
  const selectedEntry = selectedNodeId
    ? entries.find((entry) => entry.node.node_id === selectedNodeId) || null
    : null;
  const selectedNodeForInsight = selectedEntry?.node || null;
  const liveStats = readLiveExtractionStats(sampleScope);
  const liveSamples = isLivePreview
    ? buildLiveExtractionStreamSamples(sourceAppendix, evidenceSamples).slice(0, 4)
    : [];
  return (
    <div
      data-amway-orbit-map="true"
      className={`relative min-h-[720px] overflow-hidden bg-[var(--bg-secondary)] lg:min-h-[780px] 2xl:min-h-[860px] ${
        isSpatialMode ? 'isolate' : ''
      }`}
      style={isSpatialMode ? { perspective: '1200px' } : undefined}
    >
      <OrbitLiveAnimationStyle />
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <radialGradient id="amway-orbit-core" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--brand-bg)" stopOpacity="0.72" />
            <stop offset="64%" stopColor="var(--brand-bg)" stopOpacity="0.26" />
            <stop offset="100%" stopColor="var(--bg-secondary)" stopOpacity="0" />
          </radialGradient>
        </defs>
        {isRiskMode ? (
          <>
            <line x1="50" y1="39" x2="50" y2="57" stroke="var(--error)" strokeWidth="0.34" strokeDasharray="1.2 1.2" opacity="0.58" />
            {entries.map((entry) => (
              <line
                key={`risk-link-${entry.node.node_id}`}
                x1="50"
                y1="57"
                x2={entry.left}
                y2={entry.top}
                stroke="var(--error)"
                strokeWidth={entry.node.node_id === selectedFocusNodeId ? 0.32 : 0.12}
                strokeDasharray={entry.node.node_id === selectedFocusNodeId ? undefined : '0.8 1.2'}
                opacity={entry.node.node_id === selectedFocusNodeId ? 0.58 : 0.08}
              />
            ))}
          </>
        ) : isSpatialMode ? (
          <>
            <ellipse cx="50" cy="53" rx="21" ry="7.2" fill="url(#amway-orbit-core)" stroke="var(--brand-border)" strokeWidth="0.2" />
            <ellipse cx="50" cy="53" rx="24" ry="8.4" fill="none" stroke="var(--brand-border)" strokeOpacity="0.7" strokeWidth="0.18" />
            <ellipse cx="50" cy="53" rx="35" ry="12.3" fill="none" stroke="var(--border-subtle)" strokeWidth="0.15" strokeDasharray="0.8 1" />
            <ellipse cx="50" cy="53" rx="47" ry="16.8" fill="none" stroke="var(--border-subtle)" strokeWidth="0.15" />
            <line x1="18" y1="53" x2="82" y2="53" stroke="var(--border-subtle)" strokeWidth="0.1" opacity="0.54" />
            {entries.map((entry) => (
              <line
                key={`spatial-ray-${entry.node.node_id}`}
                x1="50"
                y1="53"
                x2={entry.left}
                y2={entry.top}
                stroke={entry.node.node_id === focusNodeId ? selectedRelationLineColor(entry.groupKey) : 'var(--border-subtle)'}
                strokeWidth={entry.node.node_id === focusNodeId ? 0.3 : 0.08}
                opacity={entry.node.node_id === focusNodeId ? 0.6 : 0.2}
              />
            ))}
          </>
        ) : (
          <>
            <ellipse cx="50" cy="50" rx="22" ry="16" fill="url(#amway-orbit-core)" stroke="var(--brand-border)" strokeWidth="0.18" pointerEvents="none" />
            <OrbitTrackBand
              track="watch"
              rx={47}
              ry={33.8}
              strokeWidth={5.4}
              focusTrackFilter={focusTrackFilter}
            />
            <OrbitTrackBand
              track="opportunity"
              rx={35}
              ry={25.2}
              strokeWidth={4.9}
              focusTrackFilter={focusTrackFilter}
            />
            <OrbitTrackBand
              track="stable"
              rx={24}
              ry={17.3}
              strokeWidth={4.4}
              focusTrackFilter={focusTrackFilter}
            />
            <OrbitTrackHitEllipse
              track="watch"
              rx={47}
              ry={33.8}
              activeTrackFilter={activeTrackFilter}
              onHoverChange={onHoverTrackFilterChange}
              onTrackFilterChange={onTrackFilterChange}
            />
            <OrbitTrackHitEllipse
              track="opportunity"
              rx={35}
              ry={25.2}
              activeTrackFilter={activeTrackFilter}
              onHoverChange={onHoverTrackFilterChange}
              onTrackFilterChange={onTrackFilterChange}
            />
            <OrbitTrackHitEllipse
              track="stable"
              rx={24}
              ry={17.3}
              activeTrackFilter={activeTrackFilter}
              onHoverChange={onHoverTrackFilterChange}
              onTrackFilterChange={onTrackFilterChange}
            />
            {entries.map((entry) => (
              <line
                key={`ray-${entry.node.node_id}`}
                x1="50"
                y1="50"
                x2={entry.left}
                y2={entry.top}
                stroke={entry.node.node_id === selectedFocusNodeId ? selectedRelationLineColor(entry.groupKey) : 'transparent'}
                strokeWidth={entry.node.node_id === selectedFocusNodeId ? 0.34 : 0}
                opacity={entry.node.node_id === selectedFocusNodeId ? 0.72 : 0}
                pointerEvents="none"
              />
            ))}
          </>
        )}
      </svg>
      <button
        type="button"
        onClick={isRiskMode ? onExitRiskView : () => onSelectNode(null)}
        className={`absolute left-1/2 z-20 flex h-40 w-40 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border-2 border-[var(--brand-primary)] bg-[var(--brand-bg)] text-center shadow-sm ${
          isRiskMode ? 'top-[39%]' : isSpatialMode ? 'top-[53%]' : 'top-1/2'
        }`}
      >
        <span className="text-xs text-[var(--brand-primary)]">中心品牌</span>
        <span className="mt-2 text-3xl font-semibold text-[var(--brand-primary)]">{centerTerm}</span>
      </button>
      {isRiskMode ? (
        <>
          <div
            aria-label={`风险认知中心，${riskNodes.length} 个节点`}
            className="absolute left-1/2 top-[57%] z-20 flex h-28 w-28 -translate-x-1/2 -translate-y-1/2 select-none flex-col items-center justify-center rounded-full border-2 border-[var(--error)] bg-[var(--bg-primary)] text-center text-[var(--error)] shadow-sm"
          >
            <span className="text-xs">风险认知</span>
            <span className="mt-1 text-2xl font-semibold">{riskNodes.length}</span>
            <span className="mt-1 text-[11px] text-[var(--text-tertiary)]">个节点</span>
          </div>
          <div className="absolute left-5 top-5 z-40 max-w-[280px] rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]/92 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)] shadow-sm">
            <p className="font-semibold text-[var(--error)]">风险关系读法</p>
            <p className="mt-1">
              先看外围风险词的分布，再点击具体风险词查看问题、平台和原文语境。
            </p>
          </div>
          <button
            type="button"
            onClick={onExitRiskView}
            className="absolute right-5 top-5 z-40 rounded-xl border border-[var(--brand-border)] bg-[var(--brand-bg)] px-4 py-2 text-sm font-semibold text-[var(--brand-primary)] shadow-sm hover:bg-[var(--bg-primary)]"
          >
            退出风险聚焦
          </button>
        </>
      ) : (
        <>
          {riskNodes.length ? (
            <button
              type="button"
              onClick={onOpenRiskView}
              className={`absolute left-[15%] top-[74%] flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border-2 border-[var(--error)] bg-[var(--bg-primary)] text-center text-[var(--error)] shadow-sm transition hover:scale-105 hover:bg-[var(--bg-secondary)] ${
                focusTrackFilter ? 'z-10 opacity-25 saturate-50' : 'z-30 opacity-100'
              }`}
              title={`聚焦查看 ${riskNodes.length} 个风险认知节点`}
            >
              <span className="text-xs">风险认知</span>
              <span className="mt-1 text-2xl font-semibold">{riskNodes.length}</span>
              <span className="mt-1 text-[11px] text-[var(--text-tertiary)]">聚焦查看</span>
            </button>
          ) : null}
        </>
      )}
      {isLivePreview ? (
        <LiveExtractionMapPanel
          answerCount={liveStats.answerCount}
          signalCount={liveStats.signalCount}
          eventCount={liveStats.eventCount}
          nodeCount={entries.length}
          targetPlatforms={targetPlatforms}
          progressMessage={liveProgressMessage}
          currentStage={liveCurrentStage}
          samples={liveSamples}
        />
      ) : null}
      <OrbitNodeInsightPanel
        node={selectedNodeForInsight}
        centerTerm={centerTerm}
        evidenceSamples={evidenceSamples}
        evidenceFindings={evidenceFindings}
        sourceAppendix={sourceAppendix}
        strategyTerms={strategyTerms}
        sampleScope={sampleScope}
        onClose={() => onSelectNode(null)}
      />
      {entries.length ? entries.map((entry) => {
        const selected = selectedNodeId === entry.node.node_id;
        const focused = entry.node.node_id === selectedFocusNodeId;
        const trackFocused = orbitFocusedEntry(entry, focusGroupKey);
        const mutedByTrack = Boolean(focusTrackFilter) && !trackFocused;
        const depth = isSpatialMode ? spatialDepthForEntry(entry) : 1;
        const origin = nodeOriginRead(entry.node, strategyTerms);
        return (
          <button
            key={entry.node.node_id}
            type="button"
            onFocus={(event) => {
              onSelectNode(entry.node.node_id);
              scrollOrbitMapIntoView(event.currentTarget);
            }}
            onClick={(event) => {
              onSelectNode(entry.node.node_id);
              scrollOrbitMapIntoView(event.currentTarget);
            }}
            className={`group absolute z-30 h-11 w-11 -translate-x-1/2 -translate-y-1/2 rounded-full transition duration-200 hover:z-40 hover:scale-105 ${
              selected ? 'ring-2 ring-[var(--brand-border)] ring-offset-2 ring-offset-[var(--bg-secondary)]' : ''
            } ${mutedByTrack ? 'pointer-events-none blur-[1.5px]' : ''} ${isLivePreview ? 'amway-orbit-live-node' : ''}`}
            style={{
              left: `${entry.left}%`,
              top: `${entry.top}%`,
              zIndex: mutedByTrack ? 18 : isSpatialMode ? Math.round(20 + entry.top) : undefined,
              transform: `translate(-50%, -50%) scale(${depth})`,
              animationDelay: isLivePreview ? `${nodeAnimationDelay(entry.node.node_id)}ms` : undefined,
              opacity: mutedByTrack ? 0.035 : 1,
            }}
            title={`${entry.node.term}：${relationshipRead(entry.node).headline}`}
          >
            <span
              className="absolute left-1/2 top-1/2 rounded-full shadow-sm transition duration-200 group-hover:shadow-md"
              style={{
                transform: 'translate(-50%, -50%)',
                width: entry.size,
                height: entry.size,
                background: orbitNodeFillColor(entry, focusGroupKey),
                opacity: focused || trackFocused ? 1 : 0.76,
                boxShadow: focused
                  ? `0 0 0 8px ${orbitHaloColor(entry.groupKey)}`
                  : isSpatialMode
                    ? `0 ${Math.max(4, depth * 7)}px ${Math.max(10, depth * 13)}px rgba(38, 45, 43, 0.16)`
                    : undefined,
              }}
            />
            <span
              className={`pointer-events-none absolute left-1/2 top-[calc(100%+6px)] inline-flex min-w-max -translate-x-1/2 items-center gap-1.5 rounded-full border bg-[var(--bg-primary)] px-2.5 py-1 text-xs font-medium shadow-sm transition duration-200 ${
                !mutedByTrack && (focused || trackFocused || entry.labelPriority) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
              } hidden sm:inline-flex`}
              style={{
                borderColor: focused ? orbitToneColor(entry.groupKey) : 'var(--border-subtle)',
                color: focused ? orbitToneColor(entry.groupKey) : 'var(--text-secondary)',
              }}
            >
              <span>{entry.node.term}</span>
              <span
                className="rounded-full border px-1.5 py-0.5 text-[10px] leading-none"
                style={{
                  borderColor: origin.kind === 'strategy' ? 'var(--brand-border)' : 'var(--border-subtle)',
                  background: origin.kind === 'strategy' ? 'var(--brand-bg)' : 'var(--bg-secondary)',
                  color: origin.kind === 'strategy' ? 'var(--brand-primary)' : 'var(--text-tertiary)',
                }}
                title={origin.label}
              >
                {nodeOriginShortLabel(origin.kind)}
              </span>
            </span>
          </button>
        );
      }) : (
        <div className="absolute left-1/2 top-[62%] w-[min(520px,calc(100%-48px))] -translate-x-1/2 text-center text-sm leading-6 text-[var(--text-secondary)]">
          还没有外围节点。开始抓取并完成解析后，图谱会收录回答中出现的真实联想。
        </div>
      )}
    </div>
  );
}

function OrbitLiveAnimationStyle() {
  return (
    <style>{`
      @keyframes amwayOrbitNodeIn {
        0% {
          opacity: 0;
          transform: translate(-50%, -50%) scale(0.54);
        }
        58% {
          opacity: 1;
          transform: translate(-50%, -50%) scale(1.08);
        }
        100% {
          opacity: 1;
          transform: translate(-50%, -50%) scale(1);
        }
      }
      @keyframes amwayOrbitPulse {
        0%, 100% {
          box-shadow: 0 0 0 0 rgba(31, 122, 107, 0.18);
        }
        50% {
          box-shadow: 0 0 0 9px rgba(31, 122, 107, 0);
        }
      }
      .amway-orbit-live-node {
        animation: amwayOrbitNodeIn 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
      }
      .amway-orbit-live-node > span:first-child {
        animation: amwayOrbitPulse 1600ms cubic-bezier(0.25, 1, 0.5, 1) infinite;
      }
      @media (prefers-reduced-motion: reduce) {
        .amway-orbit-live-node,
        .amway-orbit-live-node > span:first-child {
          animation: none !important;
        }
      }
    `}</style>
  );
}

function OrbitTrackBand({
  track,
  rx,
  ry,
  strokeWidth,
  focusTrackFilter,
}: {
  track: AssociationNodeFilterKey;
  rx: number;
  ry: number;
  strokeWidth: number;
  focusTrackFilter: AssociationNodeFilterKey | null;
}) {
  const active = focusTrackFilter === track;
  const faded = Boolean(focusTrackFilter && !active);
  const color = orbitTrackColor(track);
  return (
    <>
      <ellipse
        cx="50"
        cy="50"
        rx={rx}
        ry={ry}
        fill="none"
        stroke={color}
        strokeOpacity={faded ? 0.025 : active ? 0.18 : 0.07}
        strokeWidth={strokeWidth}
        pointerEvents="none"
      />
      <ellipse
        cx="50"
        cy="50"
        rx={rx}
        ry={ry}
        fill="none"
        stroke={color}
        strokeOpacity={faded ? 0.05 : active ? 0.82 : 0.28}
        strokeWidth={active ? 0.34 : 0.16}
        pointerEvents="none"
      />
    </>
  );
}

function OrbitTrackHitEllipse({
  track,
  rx,
  ry,
  activeTrackFilter,
  onHoverChange,
  onTrackFilterChange,
}: {
  track: AssociationNodeFilterKey;
  rx: number;
  ry: number;
  activeTrackFilter: AssociationNodeFilterKey | null;
  onHoverChange: (track: AssociationNodeFilterKey | null) => void;
  onTrackFilterChange: (track: AssociationNodeFilterKey) => void;
}) {
  return (
    <ellipse
      cx="50"
      cy="50"
      rx={rx}
      ry={ry}
      fill="none"
      stroke="transparent"
      strokeWidth="7"
      pointerEvents="stroke"
      tabIndex={0}
      role="button"
      aria-pressed={activeTrackFilter === track}
      aria-label={`聚焦${trackLabel(track)}`}
      onMouseEnter={() => onHoverChange(track)}
      onMouseLeave={() => onHoverChange(null)}
      onFocus={() => onHoverChange(track)}
      onBlur={() => onHoverChange(null)}
      onClick={() => onTrackFilterChange(track)}
      style={{ cursor: 'pointer' }}
    />
  );
}

function LiveExtractionMapPanel({
  answerCount,
  signalCount,
  eventCount,
  nodeCount,
  targetPlatforms,
  progressMessage,
  currentStage,
  samples,
}: {
  answerCount: number;
  signalCount: number;
  eventCount: number;
  nodeCount: number;
  targetPlatforms: string[];
  progressMessage?: string | null;
  currentStage?: string | null;
  samples: OrbitEvidenceItem[];
}) {
  const cleanProgress = cleanWorkflowProgressMessage(progressMessage);
  const stageLabel = currentStage ? currentStage.toUpperCase() : 'A4';
  return (
    <aside className="absolute left-5 top-5 z-40 w-[min(420px,calc(100%-40px))] rounded-2xl border border-[var(--border-subtle)] bg-[rgba(250,248,242,0.92)] p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-[var(--brand-primary)]">{stageLabel} 抓取中</div>
          <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">答案入库后立即抽词，节点同步进入图谱</div>
        </div>
        <div className="rounded-full border border-[var(--brand-border)] bg-[var(--brand-bg)] px-2.5 py-1 text-xs font-semibold text-[var(--brand-primary)]">
          运行中
        </div>
      </div>
      {cleanProgress ? (
        <div className="mt-3 rounded-xl border border-[var(--brand-border)] bg-[var(--brand-bg)] px-3 py-2 text-xs font-semibold text-[var(--brand-primary)]">
          当前进度：{cleanProgress}
        </div>
      ) : null}
      <div className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
        <LiveMapMetric label="回答" value={answerCount || 0} />
        <LiveMapMetric label="事件" value={eventCount || 0} />
        <LiveMapMetric label="信号" value={signalCount || 0} />
        <LiveMapMetric label="节点" value={nodeCount || 0} />
      </div>
      {targetPlatforms.length ? (
        <div className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]/86 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
          目标平台：{targetPlatforms.join('、')}。返回一条，抽取一条，图谱更新一条；抓取收尾后进入汇总校准。
        </div>
      ) : null}
      {samples.length ? (
        <div className="mt-3 space-y-2">
          {samples.map((sample) => (
            <div key={sampleKey(sample)} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]/86 px-3 py-2 text-xs leading-5">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-[var(--text-primary)]">{sample.node_term || '新实体'}</span>
                <span className="text-[var(--text-tertiary)]">{platformLabel(sample.platform || '')}</span>
              </div>
              <p className="mt-1 max-h-10 overflow-hidden text-[var(--text-secondary)]">
                {cleanEvidenceExcerpt(sample.answer_excerpt, 86)}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]/86 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
          正在等待第一批实体信号。出现命中后，节点会进入对应轨道。
        </p>
      )}
    </aside>
  );
}

function LiveMapMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]/86 px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{value}</div>
    </div>
  );
}

function scrollOrbitMapIntoView(target: Element) {
  const map = target.closest('[data-amway-orbit-map="true"]');
  window.setTimeout(() => {
    map?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, 0);
}

function OrbitNodeInsightPanel({
  node,
  centerTerm,
  evidenceSamples,
  evidenceFindings,
  sourceAppendix,
  strategyTerms,
  sampleScope,
  onClose,
}: {
  node: OntologyAssociationCircleNode | null;
  centerTerm: string;
  evidenceSamples: OntologyAssociationCircleEvidence[];
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  strategyTerms: string[];
  sampleScope: Record<string, unknown>;
  onClose: () => void;
}) {
  if (!node) {
    return null;
  }
  const evidence = buildNodeEvidenceForPanel(node, evidenceSamples, sourceAppendix, evidenceFindings);
  const origin = nodeOriginRead(node, strategyTerms);
  const groupKey = classifyAssociationNode(node);
  const distanceBand = orbitDistanceBandForNode(groupKey, node);
  const questionCount = sampleQuestionCount(sampleScope);
  const totalAnswerCount = sampleAnswerCount(sampleScope);
  const mentionAnswerCount = nodeEvidenceCount(node) || evidence.length;
  const relatedQuestionCount = distinctEvidenceQuestionCount(evidence);
  const platformNames = nodePlatformNames(node, evidence);
  const platformSummaries = buildPlatformEvidenceSummaries(node, evidence);
  const sampledEvidence = sampleEvidenceAcrossPlatforms(evidence, 4);
  const hasLargeEvidenceSet = mentionAnswerCount > 5;
  return (
    <aside
      className="absolute inset-4 z-50 overflow-hidden rounded-[22px] border border-[var(--border-subtle)] bg-[rgba(250,248,242,0.88)] shadow-sm lg:inset-7"
      aria-label={`${node.term}节点解读`}
    >
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] bg-[rgba(250,248,242,0.72)] px-5 py-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="rounded-full border px-2 py-1 text-xs font-medium"
                style={{
                  borderColor: origin.kind === 'strategy' ? 'var(--brand-border)' : 'var(--border-subtle)',
                  background: origin.kind === 'strategy' ? 'var(--brand-bg)' : 'var(--bg-secondary)',
                  color: origin.kind === 'strategy' ? 'var(--brand-primary)' : 'var(--text-secondary)',
                }}
              >
                {origin.label}
              </span>
              <span
                className="rounded-full border px-2 py-1 text-xs font-medium"
                style={orbitDistanceBandChipStyle(distanceBand)}
              >
                {orbitDistanceBandLabel(distanceBand)}
              </span>
              <span className="text-xs text-[var(--text-tertiary)]">{relationshipRead(node).label}</span>
            </div>
            <h3 className="mt-2 truncate text-2xl font-semibold">{node.term}</h3>
          </div>
          <button
            type="button"
            aria-label="关闭节点解读"
            onClick={onClose}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
          >
            <X size={15} />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(340px,440px)_minmax(0,1fr)]">
          <div className="min-h-0 overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]/95 p-5 shadow-sm">
            <InsightSection
              title={`它和${centerTerm}的关系`}
              text={nodeBrandRelationText(node, centerTerm, origin)}
            />

            <InsightSection
              title="为什么在这个圈"
              text={orbitBandExplanationText(node, distanceBand)}
            />

            <InsightSection
              title="证据是否验证了它"
              text={nodeEvidenceSummaryText({
                term: node.term,
                questionCount,
                totalAnswerCount,
                mentionAnswerCount,
                relatedQuestionCount,
                platformNames,
              })}
            />

            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <InsightMetric label="样本问题" value={String(questionCount || '-')} />
              <InsightMetric label="提及回答" value={String(mentionAnswerCount || '-')} />
              <InsightMetric label="覆盖平台" value={String(platformNames.length || nodePlatformCount(node) || '-')} />
            </div>

            <InsightSection
              title="这意味着什么"
              text={nodeBrandImplicationText(node, centerTerm, origin)}
              emphasized
            />
          </div>

          <div className="min-h-0 overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]/88 p-5 shadow-sm">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-[var(--text-tertiary)]">平台倾向与抽样原文</div>
                <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                  {hasLargeEvidenceSet
                    ? `${mentionAnswerCount} 条回答提及，先看平台分布，再看每个平台的代表性片段。`
                    : '样本量较少，直接查看平台样例。'}
                </p>
              </div>
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1 text-xs text-[var(--text-secondary)]">
                原文样例 {sampledEvidence.length} 个平台
              </span>
            </div>

            {platformSummaries.length ? (
              <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                {platformSummaries.map((item) => (
                  <div key={item.platform} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-[var(--text-primary)]">{item.label}</div>
                      <div className="text-lg font-semibold text-[var(--brand-primary)]">{item.answerCount}</div>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                      {platformTendencyText(item)}
                    </p>
                    <div className="mt-2 rounded-lg bg-[var(--bg-primary)] px-2 py-1 text-[11px] text-[var(--text-tertiary)]">
                      {item.samples.length ? '有可读原文样例' : '统计有提及，原文样例未收录'}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="mt-5">
              <div className="text-xs font-medium text-[var(--text-tertiary)]">代表性原文（按平台去重）</div>
              {sampledEvidence.length ? (
                <div className="mt-2 grid gap-3 xl:grid-cols-2">
                  {sampledEvidence.map((item) => (
                    <blockquote
                      key={sampleKey(item)}
                      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-xs leading-5 text-[var(--text-secondary)]"
                    >
                      <div className="mb-1 font-medium text-[var(--text-primary)]">
                        {platformLabel(item.platform || '')}
                      </div>
                      {item.question ? (
                        <p className="text-[var(--text-tertiary)]">问题：{cleanEvidenceExcerpt(item.question, 72)}</p>
                      ) : null}
                      <p className="mt-1">回答摘录：“{cleanEvidenceExcerpt(item.answer_excerpt, 160)}”</p>
                    </blockquote>
                  ))}
                </div>
              ) : (
                <p className="mt-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                  当前历史报告只保留了这个词的计数和平台分布，没有保留可读原文。重新生成图谱后，系统会优先保留该节点的回答摘录。
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function InsightSection({
  title,
  text,
  emphasized = false,
}: {
  title: string;
  text: string;
  emphasized?: boolean;
}) {
  return (
    <section
      className={`mt-4 rounded-xl px-3 py-2 text-sm leading-6 ${
        emphasized
          ? 'bg-[var(--brand-bg)] text-[var(--brand-primary)]'
          : 'border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-primary)]'
      }`}
    >
      <div className={`text-xs font-medium ${emphasized ? 'text-[var(--brand-primary)]' : 'text-[var(--text-tertiary)]'}`}>
        {title}
      </div>
      <p className="mt-1">{text}</p>
    </section>
  );
}

function InsightMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

interface CommercialOrbitEntry {
  node: OntologyAssociationCircleNode;
  groupKey: AssociationMapGroupKey;
  distanceBand: OrbitDistanceBand;
  left: number;
  top: number;
  angle: number;
  radius: number;
  size: number;
  labelPriority: boolean;
}

function buildCommercialOrbitEntries(
  groups: AssociationMapGroup[],
  defaultRiskNodes: OntologyAssociationCircleNode[] = [],
): CommercialOrbitEntry[] {
  const rawEntries: Array<{
    node: OntologyAssociationCircleNode;
    groupKey: AssociationMapGroupKey;
    groupIndex: number;
  }> = [
    ...groups.flatMap((group) => {
      if (group.key === 'risk') return [];
      return group.nodes.map((node, index) => ({
        node,
        groupKey: group.key,
        groupIndex: index,
      }));
    }),
    ...defaultRiskNodes.map((node, index) => ({
      node,
      groupKey: 'risk' as const,
      groupIndex: index,
    })),
  ];
  const totalEntries = Math.max(rawEntries.length, 1);
  const entries = rawEntries.map(({ node, groupKey, groupIndex }, index) => {
    const angle = orbitDistributedAngle(groupKey, index, groupIndex, totalEntries);
    const distanceBand = orbitDistanceBandForNode(groupKey, node);
    const radius = orbitRadiusForNode(distanceBand, node, groupIndex);
    const radians = (angle * Math.PI) / 180;
    const evidence = nodeEvidenceCount(node);
    const gravity = nodeClosenessValue(node);
    const size = nodeVisualSize(node, groupKey);
    return {
      node,
      groupKey,
      distanceBand,
      left: clampNumber(50 + Math.cos(radians) * radius, 9, 91),
      top: clampNumber(50 + Math.sin(radians) * radius * 0.72, 10, 90),
      angle,
      radius,
      size,
      labelPriority: distanceBand === 'risk'
        ? groupIndex < 2
        : groupIndex < 3 || gravity >= 58 || evidence >= 20 || distanceBand === 'near',
    };
  });
  return separateOrbitEntries(entries, {
    minGap: 6.2,
    maxIterations: 10,
    leftBounds: [7, 93],
    topBounds: [8, 92],
  });
}

function buildRiskMapEntries(riskNodes: OntologyAssociationCircleNode[]): CommercialOrbitEntry[] {
  const total = Math.max(riskNodes.length, 1);
  const entries: CommercialOrbitEntry[] = riskNodes.map((node, index) => {
    const angle = total > 1 ? 18 + (144 * index) / (total - 1) : 90;
    const radians = (angle * Math.PI) / 180;
    const radius = 29 + [0, 5.2, 2.6, 7][index % 4];
    return {
      node,
      groupKey: 'risk',
      distanceBand: 'risk',
      left: clampNumber(50 + Math.cos(radians) * radius, 12, 88),
      top: clampNumber(57 + Math.sin(radians) * radius * 0.72, 60, 86),
      angle,
      radius,
      size: 13 + Math.min(18, Math.max(0, nodeEvidenceCount(node) / 2.6)),
      labelPriority: index < 8 || nodeEvidenceCount(node) >= 20,
    };
  });
  return separateOrbitEntries(entries, {
    minGap: 6.2,
    maxIterations: 10,
    leftBounds: [10, 90],
    topBounds: [58, 88],
  });
}

function orbitDistributedAngle(
  groupKey: AssociationMapGroupKey,
  index: number,
  groupIndex: number,
  total: number,
) {
  const goldenAngle = 137.508;
  const groupOffset = orbitGroupAngleOffset(groupKey);
  const densitySpread = total >= 70 ? 5.2 : total >= 40 ? 4.2 : total >= 20 ? 3.2 : 2;
  const lane = [-1, 1, -0.55, 0.55, -1.45, 1.45, 0][groupIndex % 7] * densitySpread;
  const rawAngle = (index * goldenAngle + groupOffset + orbitAngleNudge(groupKey, groupIndex) + lane) % 360;
  return rawAngle > 180 ? rawAngle - 360 : rawAngle;
}

function orbitGroupAngleOffset(groupKey: AssociationMapGroupKey) {
  if (groupKey === 'strong') return -88;
  if (groupKey === 'growth') return 12;
  if (groupKey === 'story') return 76;
  return 0;
}

function orbitAngleNudge(groupKey: AssociationMapGroupKey, index: number) {
  if (groupKey === 'growth') return [-7, 5, -3, 7][index % 4];
  if (groupKey === 'strong') return [-5, 5, 0, 2][index % 4];
  if (groupKey === 'risk') return [-4, 4, 0][index % 3];
  return [4, -4, 0, -2][index % 4];
}

function orbitDistanceBandForNode(groupKey: AssociationMapGroupKey, node: OntologyAssociationCircleNode): OrbitDistanceBand {
  if (groupKey === 'risk') return 'risk';
  const distance = nodeVisualDistanceValue(node);
  if (distance > 0) {
    if (distance <= 35) return 'near';
    if (distance <= 65) return 'bridge';
    return 'far';
  }
  if (groupKey === 'strong') return 'near';
  if (groupKey === 'growth') return 'bridge';
  return 'far';
}

function orbitRadiusForNode(distanceBand: OrbitDistanceBand, node: OntologyAssociationCircleNode, index: number) {
  const distance = effectiveDistanceForBand(node, distanceBand);
  const lane = orbitRadiusLane(distanceBand, index);
  if (distanceBand === 'risk') {
    const evidence = nodeEvidenceCount(node);
    const platform = nodePlatformCount(node);
    const sampleWeakOffset = platform <= 1 && evidence <= 1
      ? 7
      : platform <= 1 && evidence <= 3
        ? 5
        : platform <= 1
          ? 3
          : platform === 2 && evidence <= 2
            ? 2
            : 0;
    const evidencePull = Math.min(3.5, Math.max(0, evidence - 1) / 12 + platform * 0.65);
    return clampNumber(45 + lane + sampleWeakOffset - evidencePull, 40, 52);
  }
  if (distanceBand === 'near') {
    return clampNumber(scaleDistanceToRadius(distance, 0, 35, 15.2, 23.8) + lane, 14.2, 25.5);
  }
  if (distanceBand === 'bridge') {
    return clampNumber(scaleDistanceToRadius(distance, 36, 65, 28.5, 36.5) + lane, 27.5, 38.5);
  }
  if (distanceBand === 'far') {
    return clampNumber(scaleDistanceToRadius(distance, 66, 100, 40, 47.5) + lane, 38.5, 49);
  }
  return 31;
}

function orbitRadiusLane(distanceBand: OrbitDistanceBand, index: number) {
  if (distanceBand === 'near') return [-1.8, 1.8, 0, -3, 3][index % 5];
  if (distanceBand === 'bridge') return [-2.8, 2.8, 0, -4.4, 4.4][index % 5];
  if (distanceBand === 'far') return [-3.4, 3.4, 0, -5.2, 5.2][index % 5];
  return [-2.5, 2.5, 0, -4, 4][index % 5];
}

function separateOrbitEntries(
  entries: CommercialOrbitEntry[],
  options: {
    minGap: number;
    maxIterations: number;
    leftBounds: [number, number];
    topBounds: [number, number];
  },
) {
  const placed: CommercialOrbitEntry[] = [];
  entries.forEach((entry) => {
    let next = { ...entry };
    for (let attempt = 0; attempt < options.maxIterations; attempt += 1) {
      let adjusted = false;
      placed.forEach((previous) => {
        const distance = orbitEntryDistance(next, previous);
        const requiredGap = orbitEntryRequiredGap(next, previous, options.minGap);
        if (distance >= requiredGap) return;
        const fallbackAngle = ((placed.length + attempt + 1) * 43 * Math.PI) / 180;
        const dx = next.left - previous.left || Math.cos(fallbackAngle);
        const dy = next.top - previous.top || Math.sin(fallbackAngle);
        const length = Math.max(0.01, Math.sqrt(dx * dx + dy * dy));
        const push = requiredGap - distance + 0.55;
        const nextLeft = clampNumber(next.left + (dx / length) * push, options.leftBounds[0], options.leftBounds[1]);
        const nextTop = clampNumber(next.top + (dy / length) * push * 0.86, options.topBounds[0], options.topBounds[1]);
        const atHorizontalBound = nextLeft === options.leftBounds[0] || nextLeft === options.leftBounds[1];
        const tangentPush = atHorizontalBound
          ? ((placed.length + attempt) % 2 === 0 ? -1 : 1) * Math.max(1.1, push * 0.72)
          : 0;
        next = {
          ...next,
          left: nextLeft,
          top: clampNumber(nextTop + tangentPush, options.topBounds[0], options.topBounds[1]),
        };
        adjusted = true;
      });
      if (!adjusted) break;
    }
    if (placed.some((previous) => orbitEntriesCollide(next, previous, options.minGap))) {
      next = findOpenOrbitPosition(next, placed, options);
    }
    placed.push(next);
  });
  return placed;
}

function findOpenOrbitPosition(
  entry: CommercialOrbitEntry,
  placed: CommercialOrbitEntry[],
  options: {
    minGap: number;
    leftBounds: [number, number];
    topBounds: [number, number];
  },
) {
  const angleOffsets = [0, 18, -18, 36, -36, 54, -54, 72, -72, 96, -96, 126, -126, 162, -162, 180];
  const radiusOffsets = orbitFallbackRadiusOffsets(entry.distanceBand);
  let best = entry;
  let bestScore = orbitPositionScore(entry, placed, options.minGap);
  angleOffsets.forEach((angleOffset) => {
    radiusOffsets.forEach((radiusOffset) => {
      const angle = entry.angle + angleOffset;
      const radius = clampNumber(entry.radius + radiusOffset, 12, 51);
      const radians = (angle * Math.PI) / 180;
      const centerTop = entry.distanceBand === 'risk' ? 57 : 50;
      const candidate = {
        ...entry,
        angle,
        radius,
        left: clampNumber(50 + Math.cos(radians) * radius, options.leftBounds[0], options.leftBounds[1]),
        top: clampNumber(centerTop + Math.sin(radians) * radius * 0.72, options.topBounds[0], options.topBounds[1]),
      };
      const score = orbitPositionScore(candidate, placed, options.minGap);
      if (score > bestScore) {
        best = candidate;
        bestScore = score;
      }
    });
  });
  return best;
}

function orbitFallbackRadiusOffsets(distanceBand: OrbitDistanceBand) {
  if (distanceBand === 'near') return [0, -2.5, 2.5, -4.5, 4.5];
  if (distanceBand === 'bridge') return [0, -3.5, 3.5, -6, 6];
  if (distanceBand === 'far') return [0, -4, 4, -7, 7];
  return [0, -3, 3, -5, 5];
}

function orbitPositionScore(entry: CommercialOrbitEntry, placed: CommercialOrbitEntry[], minGap: number) {
  if (!placed.length) return Number.POSITIVE_INFINITY;
  return placed.reduce((score, previous) => {
    const requiredGap = orbitEntryRequiredGap(entry, previous, minGap);
    const distance = orbitEntryDistance(entry, previous);
    return Math.min(score, distance / requiredGap);
  }, Number.POSITIVE_INFINITY);
}

function orbitEntriesCollide(left: CommercialOrbitEntry, right: CommercialOrbitEntry, minGap: number) {
  return orbitEntryDistance(left, right) < orbitEntryRequiredGap(left, right, minGap);
}

function orbitEntryDistance(left: CommercialOrbitEntry, right: CommercialOrbitEntry) {
  const dx = left.left - right.left;
  const dy = (left.top - right.top) * 1.18;
  return Math.sqrt(dx * dx + dy * dy);
}

function orbitEntryRequiredGap(left: CommercialOrbitEntry, right: CommercialOrbitEntry, minGap: number) {
  const sameGroupGap = left.groupKey === right.groupKey ? 0.45 : 0;
  const labelGap = left.labelPriority || right.labelPriority ? 0.95 : 0;
  const sizeGap = Math.min(1.1, (left.size + right.size) / 46);
  return minGap + sameGroupGap + labelGap + sizeGap;
}

function effectiveDistanceForBand(node: OntologyAssociationCircleNode, distanceBand: OrbitDistanceBand) {
  const distance = nodeVisualDistanceValue(node);
  if (distance > 0) return distance;
  if (distanceBand === 'near') return 24;
  if (distanceBand === 'bridge') return 50;
  if (distanceBand === 'far') return 78;
  return 50;
}

function scaleDistanceToRadius(
  distance: number,
  minDistance: number,
  maxDistance: number,
  minRadius: number,
  maxRadius: number,
) {
  if (!distance) return minRadius;
  const ratio = clampNumber((distance - minDistance) / (maxDistance - minDistance), 0, 1);
  return minRadius + (maxRadius - minRadius) * ratio;
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function nodeAnimationDelay(nodeId?: string) {
  const source = String(nodeId || '');
  let hash = 0;
  for (let index = 0; index < source.length; index += 1) {
    hash = (hash * 31 + source.charCodeAt(index)) % 240;
  }
  return hash;
}

function spatialDepthForEntry(entry: CommercialOrbitEntry) {
  const frontDepth = (entry.top - 38) / 54;
  const evidenceDepth = Math.min(0.12, nodeEvidenceCount(entry.node) / 260);
  return clampNumber(0.86 + frontDepth * 0.24 + evidenceDepth, 0.84, 1.16);
}

function nodeVisualSize(node: OntologyAssociationCircleNode, groupKey: AssociationMapGroupKey) {
  const evidence = nodeEvidenceCount(node);
  const platform = nodePlatformCount(node);
  if (groupKey === 'risk' || isCompetitorNode(node)) {
    const weakSampleFloor = platform <= 1 && evidence <= 1 ? 8.8 : 10.2;
    return clampNumber(weakSampleFloor + Math.min(15, Math.max(0, evidence / 3.2)), 8.8, 25);
  }
  return clampNumber(11 + Math.min(18, Math.max(0, evidence / 2.8)), 9.8, 29);
}

function nodeVisualDistanceValue(node: OntologyAssociationCircleNode) {
  const baseDistance = nodeDistanceValue(node);
  const distance = baseDistance > 0 ? baseDistance : 100 - nodeClosenessValue(node);
  return clampNumber(distance + nodeConfidenceDistancePenalty(node), 0, 100);
}

function nodeConfidenceDistancePenalty(node: OntologyAssociationCircleNode) {
  const evidence = nodeEvidenceCount(node);
  const platform = nodePlatformCount(node);
  if (isCompetitorNode(node)) {
    if (platform <= 1 && evidence <= 1) return 36;
    if (platform <= 1 && evidence <= 3) return 28;
    if (platform <= 1) return 18;
    if (platform === 2 && evidence <= 3) return 12;
    return 0;
  }
  if (platform <= 1 && evidence <= 1) return 24;
  if (platform <= 1 && evidence <= 3) return 16;
  if (platform <= 1) return 8;
  if (platform === 2 && evidence <= 2) return 10;
  return 0;
}

function orbitToneColor(groupKey: AssociationMapGroupKey) {
  if (groupKey === 'risk') return 'var(--evidence-risk)';
  if (groupKey === 'growth') return 'var(--evidence-opportunity)';
  if (groupKey === 'story') return 'var(--text-tertiary)';
  return 'var(--brand-primary)';
}

function selectedRelationLineColor(groupKey: AssociationMapGroupKey) {
  return orbitToneColor(groupKey);
}

function trackFilterToGroupKey(track: AssociationNodeFilterKey | null): AssociationMapGroupKey | null {
  if (track === 'stable') return 'strong';
  if (track === 'opportunity') return 'growth';
  if (track === 'watch') return 'story';
  return null;
}

function trackLabel(track: AssociationNodeFilterKey) {
  if (track === 'stable') return '稳定轨';
  if (track === 'opportunity') return '机会轨';
  return '观察轨';
}

function orbitTrackColor(track: AssociationNodeFilterKey) {
  if (track === 'stable') return 'var(--brand-primary)';
  if (track === 'opportunity') return 'var(--evidence-opportunity)';
  return 'var(--text-tertiary)';
}

function orbitFocusedEntry(entry: CommercialOrbitEntry, focusGroupKey: AssociationMapGroupKey | null) {
  return Boolean(focusGroupKey && entry.groupKey === focusGroupKey);
}

function orbitNodeFillColor(entry: CommercialOrbitEntry, focusGroupKey: AssociationMapGroupKey | null) {
  if (focusGroupKey && entry.groupKey === focusGroupKey) return orbitToneColor(entry.groupKey);
  if (entry.node.node_id && entry.groupKey === 'risk') return 'color-mix(in srgb, var(--text-tertiary) 82%, var(--evidence-risk) 18%)';
  return 'color-mix(in srgb, var(--text-secondary) 72%, var(--brand-primary) 18%)';
}

function orbitHaloColor(groupKey: AssociationMapGroupKey) {
  if (groupKey === 'risk') return 'rgba(185, 80, 70, 0.14)';
  if (groupKey === 'growth') return 'rgba(186, 122, 38, 0.15)';
  if (groupKey === 'story') return 'rgba(115, 121, 111, 0.13)';
  return 'rgba(31, 122, 107, 0.16)';
}

function orbitDistanceBandLabel(distanceBand: OrbitDistanceBand) {
  if (distanceBand === 'near') return '稳定联想';
  if (distanceBand === 'bridge') return '可拉近';
  if (distanceBand === 'far') return '待观察';
  return '风险';
}

function orbitDistanceBandChipStyle(distanceBand: OrbitDistanceBand) {
  if (distanceBand === 'near') {
    return {
      borderColor: 'var(--brand-border)',
      background: 'var(--brand-bg)',
      color: 'var(--brand-primary)',
    };
  }
  if (distanceBand === 'bridge') {
    return {
      borderColor: 'color-mix(in srgb, var(--evidence-opportunity) 28%, var(--border-subtle) 72%)',
      background: 'var(--status-warning-bg)',
      color: 'var(--evidence-opportunity)',
    };
  }
  if (distanceBand === 'far') {
    return {
      borderColor: 'var(--border-subtle)',
      background: 'var(--bg-secondary)',
      color: 'var(--text-tertiary)',
    };
  }
  return {
    borderColor: 'color-mix(in srgb, var(--evidence-risk) 32%, var(--border-subtle) 68%)',
    background: 'var(--status-error-bg)',
    color: 'var(--evidence-risk)',
  };
}

function orbitBandExplanationText(node: OntologyAssociationCircleNode, distanceBand: OrbitDistanceBand) {
  const evidence = nodeEvidenceCount(node);
  const platform = nodePlatformCount(node);
  const distance = nodeDistanceValue(node);
  if (distanceBand === 'risk') {
    return `风险认知单独展开，避免和正向联想共用同一套强弱判断。本轮 ${evidence || 0} 条回答提及，覆盖 ${platform || 0} 个平台，需要回看原文确认风险语境。`;
  }
  const distanceText = distance > 0 ? `距离值 ${distance}` : '距离值待补';
  if (distanceBand === 'near') {
    return `系统把它放入稳定联想区，表示回答已经较稳定地把它带回品牌。本轮 ${evidence || 0} 条回答提及，覆盖 ${platform || 0} 个平台，${distanceText}。`;
  }
  if (distanceBand === 'bridge') {
    return `系统把它放入连接轨，表示它已经能连到品牌，还需要更多直接证据拉近。本轮 ${evidence || 0} 条回答提及，覆盖 ${platform || 0} 个平台，${distanceText}。`;
  }
  return `系统把它放入观察轨，表示它仍处在远端机会或待观察阶段。本轮 ${evidence || 0} 条回答提及，覆盖 ${platform || 0} 个平台，${distanceText}。`;
}

function nodeOriginShortLabel(kind: ReturnType<typeof nodeOriginRead>['kind']) {
  return kind === 'strategy' ? '战' : '答';
}

function nodeOriginRead(node: OntologyAssociationCircleNode, strategyTerms: string[]) {
  const backendOrigin = String(node.term_origin || '').toLowerCase();
  const isStrategy = backendOrigin === 'strategy' || (
    backendOrigin !== 'answer' && nodeMatchesStrategyTerms(node, strategyTerms)
  );
  const evidenceCount = nodeEvidenceCount(node);
  if (isStrategy) {
    return {
      kind: 'strategy' as const,
      label: '战略词',
      description: evidenceCount
        ? '这是本轮战略或题目定义里要验证的词，并且已经在抓取回答中被命中。'
        : '这是本轮战略或题目定义里要验证的词，目前还需要回答证据把它带回品牌。',
    };
  }
  return {
    kind: 'answer' as const,
    label: '回答词',
    description: '这是从 AI 平台回答中解析出来的联想词，前端没有预设进图。',
  };
}

function nodeMatchesStrategyTerms(node: OntologyAssociationCircleNode, strategyTerms: string[]) {
  const source = String(node.source || '').toLowerCase();
  if (node.is_target_term || /strategy|target|seed|manual/.test(source)) return true;
  const nodeTerm = compactStrategyText(node.term);
  if (!nodeTerm) return false;
  return strategyTerms.some((term) => {
    const strategyTerm = compactStrategyText(term);
    return Boolean(strategyTerm) && (
      strategyTerm === nodeTerm ||
      strategyTerm.includes(nodeTerm) ||
      nodeTerm.includes(strategyTerm)
    );
  });
}

function compactStrategyText(value?: string | null) {
  return String(value || '').replace(/\s+/g, '').trim();
}

function nodeBrandRelationText(
  node: OntologyAssociationCircleNode,
  centerTerm: string,
  origin: ReturnType<typeof nodeOriginRead>,
) {
  const groupKey = classifyAssociationNode(node);
  const path = associationPathLabel(node);

  if (groupKey === 'risk') {
    return `“${node.term}”和${centerTerm}的关系会把品牌带回旧认知风险，属于需要单独管理的风险入口。它需要进入风险关系图，避免混在正向战略轨道里解读。`;
  }

  if (origin.kind === 'strategy') {
    if (groupKey === 'strong') {
      return `“${node.term}”是${centerTerm}本轮要验证的战略词，也已经被平台回答稳定带回品牌。这个词来自本轮战略定义，当前证据显示它已经被回答接住。`;
    }
    if (groupKey === 'growth') {
      return `“${node.term}”是${centerTerm}未来发展的战略方向之一。回答已经能沿着“${path}”把它带回品牌，但它尚未成为平台的第一反应，所以更像正在形成的机会资产。`;
    }
    return `“${node.term}”是${centerTerm}未来想建立的新联想。当前它通过“${path}”和品牌发生连接，但还停留在远端机会区，平台还没有稳定把它记成${centerTerm}的代表性表达。`;
  }

  if (groupKey === 'strong') {
    return `“${node.term}”由平台回答主动带出，属于回答端形成的强联想。用户问到“${path}”相关问题时，AI 已经容易把${centerTerm}放进回答。`;
  }

  return `“${node.term}”来自平台回答解析，属于可继续观察的机会线索。它目前能连接到${centerTerm}，但还需要更清楚的品牌内容和外部证据把关系讲实。`;
}

function nodeBrandImplicationText(
  node: OntologyAssociationCircleNode,
  centerTerm: string,
  origin: ReturnType<typeof nodeOriginRead>,
) {
  const groupKey = classifyAssociationNode(node);
  if (groupKey === 'risk') {
    return `这意味着${centerTerm}需要先处理旧认知：补澄清内容、替代叙事和可验证证据。下一轮要观察这个风险词是否减少出现，或者是否被新的正向解释覆盖。`;
  }
  if (origin.kind === 'strategy') {
    if (groupKey === 'strong') {
      return `这意味着这个战略方向已经被回答接住，适合沉淀成可复述的问题回答素材。下一轮重点观察它是否继续被平台带回品牌、是否被更多平台主动提起。`;
    }
    return `这意味着它仍在培育期。更合理的做法是先补人群故事、场景内容和可引用证据，再看下一轮它是否更稳定地回到品牌。`;
  }
  if (groupKey === 'strong') {
    return `这意味着${centerTerm}已有一个被平台自然带出的优势资产。品牌可以优先把它整理成可复用表达，并在官网、内容和问答素材里继续放大。`;
  }
  return `这意味着它是一个可培育机会，尚未成为已经成立的品牌资产。下一轮应围绕对应人群和场景继续发问，看它是否能被更多平台稳定带回${centerTerm}。`;
}

function nodeEvidenceSummaryText({
  term,
  questionCount,
  totalAnswerCount,
  mentionAnswerCount,
  relatedQuestionCount,
  platformNames,
}: {
  term: string;
  questionCount: number;
  totalAnswerCount: number;
  mentionAnswerCount: number;
  relatedQuestionCount: number;
  platformNames: string[];
}) {
  const questionPart = questionCount ? `本轮围绕 ${questionCount} 个问题发问` : '本轮问题样本中';
  const answerPart = totalAnswerCount ? `，抓取到 ${totalAnswerCount} 条有效回答` : '';
  const mentionPart = mentionAnswerCount
    ? `其中 ${mentionAnswerCount} 条回答提到“${term}”`
    : `目前还没有稳定回答提到“${term}”`;
  const relatedPart = relatedQuestionCount ? `，覆盖 ${relatedQuestionCount} 个相关问题` : '';
  const platformPart = platformNames.length ? `，来自 ${platformNames.join('、')}` : '';
  const verdict = mentionAnswerCount
    ? '它已经进入 AI 回答的可观察范围，还要结合平台分布和原文语境判断是否真正成立。'
    : '它仍属于待验证方向，当前先按观察中的品牌联想处理。';
  return `${questionPart}${answerPart}；${mentionPart}${relatedPart}${platformPart}。${verdict}`;
}

function buildPlatformEvidenceSummaries(
  node: OntologyAssociationCircleNode,
  evidence: OrbitEvidenceItem[],
): PlatformEvidenceSummary[] {
  const rows = new Map<string, PlatformEvidenceSummary>();
  const distribution = node.platform_distribution || {};
  const hasDistribution = Object.keys(distribution).length > 0;
  const ensureRow = (platform?: string): PlatformEvidenceSummary => {
    const label = platformLabel(platform || '');
    const key = label || '未知平台';
    const existing = rows.get(key);
    if (existing) return existing;
    const row = {
      platform: key,
      label: key,
      answerCount: 0,
      questionCount: 0,
      samples: [],
    };
    rows.set(key, row);
    return row;
  };

  Object.entries(distribution).forEach(([platform, count]) => {
    const row = ensureRow(platform);
    row.answerCount = scoreNumber(count);
  });

  evidence.forEach((item) => {
    const row = ensureRow(item.platform);
    if (!hasDistribution) row.answerCount += 1;
    if (!row.samples.some((sample) => sampleKey(sample) === sampleKey(item))) {
      row.samples.push(item);
    }
  });

  rows.forEach((row) => {
    row.questionCount = distinctEvidenceQuestionCount(row.samples);
  });

  return Array.from(rows.values())
    .filter((row) => row.answerCount > 0 || row.samples.length > 0)
    .sort((a, b) => b.answerCount - a.answerCount || a.label.localeCompare(b.label, 'zh-Hans'));
}

function platformTendencyText(item: PlatformEvidenceSummary) {
  const questionText = item.questionCount ? `，样例覆盖 ${item.questionCount} 个问题` : '';
  if (item.answerCount >= 20) {
    return `高频提及${questionText}，该平台容易把这个词放进核心回答路径。`;
  }
  if (item.answerCount >= 6) {
    return `多次提及${questionText}，已经形成可观察的平台倾向。`;
  }
  if (item.answerCount > 0) {
    return `少量提及${questionText}，需要结合样例语境继续观察。`;
  }
  return `当前只有样例摘录，缺少稳定计数。`;
}

function sampleEvidenceAcrossPlatforms(evidence: OrbitEvidenceItem[], limit: number) {
  const selected: OrbitEvidenceItem[] = [];
  const usedPlatforms = new Set<string>();
  const usedSamples = new Set<string>();
  const addSample = (item: OrbitEvidenceItem) => {
    const key = sampleKey(item);
    if (usedSamples.has(key)) return;
    const platform = platformLabel(item.platform || '');
    if (usedPlatforms.has(platform)) return;
    selected.push(item);
    usedSamples.add(key);
    usedPlatforms.add(platform);
  };

  for (const item of evidence) {
    const platform = platformLabel(item.platform || '');
    if (usedPlatforms.has(platform)) continue;
    addSample(item);
    if (selected.length >= limit) return selected;
  }
  return selected;
}

function sampleKey(item: OrbitEvidenceItem) {
  return [
    platformLabel(item.platform || ''),
    String(item.question_id || '').trim(),
    cleanEvidenceExcerpt(item.question, 80),
    cleanEvidenceExcerpt(item.answer_excerpt, 120),
  ].join('|');
}

function buildLiveExtractionStreamSamples(
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[],
  evidenceSamples: OntologyAssociationCircleEvidence[],
): OrbitEvidenceItem[] {
  const rows: OrbitEvidenceItem[] = [];
  const used = new Set<string>();
  const append = (item: OrbitEvidenceItem) => {
    const key = sampleKey(item);
    if (used.has(key)) return;
    if (!item.node_term && !item.answer_excerpt) return;
    rows.unshift(item);
    used.add(key);
  };

  sourceAppendix.forEach((item) => append({
    evidence_id: item.evidence_id,
    node_term: item.node_term,
    platform: item.platform,
    question_id: item.question_id,
    question: item.question,
    answer_excerpt: item.answer_excerpt,
  }));
  evidenceSamples.forEach((item) => append({
    evidence_id: item.evidence_id,
    node_id: item.node_id,
    node_term: item.node_term,
    platform: item.platform,
    question_id: item.question_id,
    question: item.question,
    answer_excerpt: item.answer_excerpt,
  }));

  return rows;
}

function buildNodeEvidenceForPanel(
  node: OntologyAssociationCircleNode,
  evidenceSamples: OntologyAssociationCircleEvidence[],
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[],
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[],
): OrbitEvidenceItem[] {
  const evidenceRefSet = new Set((node.evidence_samples || []).map((item) => String(item || '').trim()).filter(Boolean));
  const sourceItems = sourceAppendix.map((item): OrbitEvidenceItem => ({
    evidence_id: item.evidence_id,
    node_term: item.node_term,
    platform: item.platform,
    question_id: item.question_id,
    question: item.question,
    answer_excerpt: item.answer_excerpt,
  }));
  const findingItems = evidenceFindings
    .filter((item) => evidenceFindingMatchesNode(item, node, evidenceRefSet))
    .map((item, index): OrbitEvidenceItem => ({
      evidence_id: item.evidence_refs?.[0] || `${node.node_id}-finding-${index}`,
      node_id: item.node_id,
      node_term: item.node_term,
      platform: item.sample_platform,
      question: item.sample_question,
      answer_excerpt: item.sample_excerpt,
    }));
  const matched = [
    ...evidenceSamples.filter((item) => evidenceItemMatchesNode(item, node, evidenceRefSet)),
    ...sourceItems.filter((item) => evidenceItemMatchesNode(item, node, evidenceRefSet)),
    ...findingItems,
  ].filter((item) => String(item.answer_excerpt || '').trim());

  const seen = new Set<string>();
  return matched.filter((item) => {
    const key = sampleKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function evidenceItemMatchesNode(
  item: OrbitEvidenceItem,
  node: OntologyAssociationCircleNode,
  evidenceRefSet: Set<string>,
) {
  const itemId = String(item.evidence_id || '').trim();
  const nodeTerm = compactStrategyText(node.term);
  const itemTerm = compactStrategyText(item.node_term);
  if (item.node_id && item.node_id === node.node_id) return true;
  if (itemId && evidenceRefSet.has(itemId)) return true;
  if (nodeTerm && itemTerm && nodeTerm === itemTerm) return true;
  const text = compactStrategyText(`${item.question || ''}${item.answer_excerpt || ''}`);
  return Boolean(nodeTerm && text.includes(nodeTerm));
}

function evidenceFindingMatchesNode(
  item: OntologyAssociationCircleEvidenceFinding,
  node: OntologyAssociationCircleNode,
  evidenceRefSet: Set<string>,
) {
  if (item.node_id && item.node_id === node.node_id) return true;
  const nodeTerm = compactStrategyText(node.term);
  const itemTerm = compactStrategyText(item.node_term);
  if (nodeTerm && itemTerm && nodeTerm === itemTerm) return true;
  return Boolean(item.evidence_refs?.some((ref) => evidenceRefSet.has(String(ref || '').trim())));
}

function distinctEvidenceQuestionCount(evidence: OrbitEvidenceItem[]) {
  const keys = evidence
    .map((item) => item.question_id || item.question)
    .map((item) => String(item || '').trim())
    .filter(Boolean);
  return new Set(keys).size;
}

function nodePlatformNames(
  node: OntologyAssociationCircleNode,
  evidence: OrbitEvidenceItem[],
) {
  const fromEvidence = evidence.map((item) => item.platform).filter(Boolean) as string[];
  const fromDistribution = Object.keys(node.platform_distribution || {});
  return Array.from(new Set([...fromEvidence, ...fromDistribution]))
    .map((platform) => platformLabel(platform))
    .filter(Boolean)
    .slice(0, 4);
}

function nodeClosenessValue(node: OntologyAssociationCircleNode) {
  return scoreNumber(node.gravity_score ?? node.closeness_score ?? node.association_score);
}

function nodeDistanceValue(node: OntologyAssociationCircleNode) {
  const distance = scoreNumber(node.distance_score);
  if (distance > 0) return distance;
  const closeness = nodeClosenessValue(node);
  return closeness > 0 ? 100 - closeness : 0;
}

function nodeEvidenceCount(node: OntologyAssociationCircleNode) {
  return scoreNumber(node.evidence_count ?? node.answer_count ?? node.evidence_samples?.length);
}

function nodePlatformCount(node: OntologyAssociationCircleNode) {
  const explicitCount = scoreNumber(node.platform_count);
  if (explicitCount > 0) return explicitCount;
  return node.platform_distribution ? Object.keys(node.platform_distribution).length : 0;
}

function isCompetitorNode(node: OntologyAssociationCircleNode) {
  return String(node.entity_type || '').toLowerCase() === 'competitor';
}

function isProtectedEvidenceAssetNode(node: OntologyAssociationCircleNode) {
  const entityType = String(node.entity_type || '').toLowerCase();
  const entityId = String(node.entity_id || '').toLowerCase();
  return entityType === 'evidenceasset' && entityId !== 'evidence_regulation';
}

function isRiskNodeForMap(node: OntologyAssociationCircleNode) {
  if (isProtectedEvidenceAssetNode(node)) return false;
  const entityType = String(node.entity_type || '').toLowerCase();
  if (entityType === 'risklabel' || entityType === 'competitor') return true;
  if (node.orbit === 'risk_shadow' || node.is_risk_term) return true;
  const text = `${node.term || ''} ${node.business_tag || ''} ${node.semantic_direction || ''} ${node.orbit_label || ''} ${node.maturity_label || ''}`;
  return /风险|竞争|竞品|传销|智商税|夸大|压力|负面/.test(text);
}

function answerPresenceText(node: OntologyAssociationCircleNode) {
  const evidence = nodeEvidenceCount(node);
  if (evidence >= 20) return `${evidence} 条回答反复提到，已形成可观察联想`;
  if (evidence >= 8) return `${evidence} 条回答提到，具备可观察样本`;
  if (evidence > 0) return `${evidence} 条回答提到，仍需继续观察`;
  return '当前样本里只有很弱的出现痕迹';
}

function platformPresenceText(node: OntologyAssociationCircleNode) {
  const platform = nodePlatformCount(node);
  if (platform >= 3) return `${platform} 个平台同时出现，平台共识较强`;
  if (platform === 2) return '2 个平台出现，已经跨过单平台偶然性';
  if (platform === 1) return '只在 1 个平台出现，先按单平台线索观察';
  return '平台一致性还没有形成';
}

function associationPathLabel(node: OntologyAssociationCircleNode) {
  const candidates = [
    ...(node.primary_opportunity_points || []),
    ...(node.primary_mother_themes || []),
    ...(node.primary_audience_segments || []),
    node.theme,
    node.planet_group,
    node.orbit_label,
  ]
    .map((item) => String(item || '').trim())
    .filter(Boolean);
  const unique = Array.from(new Set(candidates));
  return unique.length ? unique.slice(0, 2).join(' / ') : '连接路径待继续确认';
}

function relationshipRead(node: OntologyAssociationCircleNode) {
  const groupKey = classifyAssociationNode(node);
  const distance = nodeDistanceValue(node);
  const answerText = answerPresenceText(node);
  const platformText = platformPresenceText(node);
  const pathText = associationPathLabel(node);

  if (groupKey === 'risk') {
    return {
      label: '风险旧认知',
      headline: '它会干扰品牌解释，需要单独管理。',
      reasons: [
        `回答表现：${answerText}。`,
        `平台一致性：${platformText}。`,
        `关系来源：回答把它带到“${pathText}”语境，需要回看原文判断风险来源。`,
      ],
      nextStep: '下一步：优先追溯原文，设计澄清内容或替代叙事，下轮看它是否减少出现、是否被正向解释替代。',
    };
  }

  if (groupKey === 'strong') {
    return {
      label: '已绑定资产',
      headline: '平台回答已经容易把它和品牌放在一起，可以作为当前品牌资产来管理。',
      reasons: [
        `回答表现：${answerText}。`,
        `平台一致性：${platformText}。`,
        `连接路径：主要通过“${pathText}”进入品牌解释。`,
      ],
      nextStep: '下一步：把它作为稳定卖点保留，同时补更多权威证据，防止被风险词稀释。',
    };
  }

  if (groupKey === 'story') {
    return {
      label: '远端机会 / 待观察',
      headline: '它代表未来想建立的联想，目前还没有被平台回答稳定绑定。',
      reasons: [
        `回答表现：${answerText}。`,
        `平台一致性：${platformText}。`,
        `连接路径：需要先用“${pathText}”补足人群故事和场景证据。`,
      ],
      nextStep: '下一步：先做内容铺垫，下轮观察是否更稳定地回到品牌。',
    };
  }

  if (distance <= 44) {
    return {
      label: '近端机会',
      headline: '它已经能通向品牌，但还没有成为多数回答的第一反应。',
      reasons: [
        `回答表现：${answerText}。`,
        `平台一致性：${platformText}。`,
        `连接路径：主要沿“${pathText}”把用户需求带回品牌。`,
      ],
      nextStep: '下一步：补充更直接的品牌证据，让它从机会区进入稳定资产区。',
    };
  }

  return {
    label: '待培育机会',
    headline: '它和品牌之间已有线索，但用户还需要看到更明确的内容证据。',
    reasons: [
      `回答表现：${answerText}。`,
      `平台一致性：${platformText}。`,
      `连接路径：目前还需要通过“${pathText}”多绕一层才能回到品牌。`,
    ],
    nextStep: '下一步：围绕对应人群和场景补内容，下轮看它能否进入可拉近区。',
  };
}

function topTermsForReport(groups: AssociationMapGroup[], key: AssociationMapGroupKey, limit = 3) {
  return (groups.find((group) => group.key === key)?.nodes || [])
    .slice(0, limit)
    .map((node) => node.term)
    .filter(Boolean);
}

function sentenceJoin(items: string[], fallback: string) {
  if (!items.length) return fallback;
  if (items.length === 1) return items[0];
  return `${items.slice(0, -1).join('、')}和${items[items.length - 1]}`;
}

function buildAssociationNarrativeReport({
  centerTerm,
  groups,
  platformComparison,
  evidenceSamples,
  sampleScope,
}: {
  centerTerm: string;
  groups: AssociationMapGroup[];
  platformComparison: OntologyAssociationCirclePlatformComparison[];
  evidenceSamples: OntologyAssociationCircleEvidence[];
  sampleScope: Record<string, unknown>;
}) {
  const answerCount = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope);
  const strongTerms = topTermsForReport(groups, 'strong', 3);
  const growthTerms = topTermsForReport(groups, 'growth', 3);
  const storyTerms = topTermsForReport(groups, 'story', 2);
  const riskTerms = topTermsForReport(groups, 'risk', 3);
  const firstPlatform = platformComparison[0];
  const firstEvidence = evidenceSamples[0];
  const strongText = sentenceJoin(strongTerms, '近端资产');
  const growthText = sentenceJoin(growthTerms, '机会词');
  const storyText = sentenceJoin(storyTerms, '观察词');
  const riskText = sentenceJoin(riskTerms, '风险词');
  const firstEvidenceRefs = firstEvidence?.evidence_id ? [firstEvidence.evidence_id] : [];
  const centerLinkedSignalCount = Number(sampleScope.center_linked_signal_count || 0);
  const marketContextSignalCount = Number(sampleScope.market_context_signal_count || 0);
  const competitionTerms = platformComparison
    .flatMap((row) => row.competition_nodes || [])
    .map((term) => String(term || '').trim())
    .filter(Boolean)
    .filter((term, index, terms) => terms.indexOf(term) === index)
    .slice(0, 4);
  const competitionText = sentenceJoin(competitionTerms, '本轮未形成明显竞品参照');
  const opportunityText = [...growthTerms, ...storyTerms].length
    ? `近端机会包括${growthText}；远端观察包括${storyText}`
    : '新的机会词还需要继续采样';
  const riskAndCompetitionText = [
    competitionTerms.length ? competitionText : '',
    riskTerms.length ? riskText : '',
  ].filter(Boolean).join('、') || '竞品与风险关系';
  const overallStatus = fallbackOverallStrategyStatus({
    strongCount: strongTerms.length,
    growthCount: growthTerms.length,
    storyCount: storyTerms.length,
    riskCount: riskTerms.length + competitionTerms.length,
  });

  return [
    {
      title: '核心判断',
      readerQuestion: '这一轮 AI 到底怎样理解品牌？',
      takeaway: answerCount && platformCount
        ? `${centerTerm}本轮最容易被回答带回的联想集中在${strongText}；近端机会集中在${growthText}；总体判断为${overallStatus}。`
        : `${centerTerm}先以回答里真实出现的词作为观察边界。`,
      claims: [
        answerCount && platformCount ? `样本边界：${answerCount} 条有效回答，有效平台 ${platformCount} 个。` : '样本边界还需要继续补齐。',
        `回答最容易带回品牌的联想：${strongText}。`,
        `主要优势：平台已经能把${strongText}带回${centerTerm}。`,
        `当前短板：${sentenceJoin([...growthTerms, ...storyTerms], '机会词')}还需要更多证据。`,
        `最大风险：${riskText}。`,
        `总体判断：${overallStatus}。`,
      ],
      text: [
        answerCount && platformCount
          ? `这一轮读到 ${answerCount} 条有效回答，有效平台 ${platformCount} 个。图上越靠近中心的词，越容易在回答里和${centerTerm}形成同一段解释；越靠外的词，还停留在机会、观察或风险语境里。`
          : '这一轮先读取回答里真实出现过的词，战略词只作为解释背景。',
        `${centerTerm}的主要优势来自${strongText}。这些词已经具备内容沉淀价值，适合继续补产品事实、使用场景和权威背书。`,
        `当前短板集中在尚未完全站稳的机会：${opportunityText}。这些词已经进入品牌故事边缘，但还需要更多点名问题、原文证据和跨平台一致性。`,
        `最大风险来自${riskAndCompetitionText}。这类关系要回到触发它们的问题场景，判断用户是在比较、疑虑、误读，还是在寻找替代方案。`,
        `综合来看，${centerTerm}本轮品牌战略处于${overallStatus}状态。已被回答接住的资产可以先放大，尚未站稳的机会需要继续补问题、补场景和补证据。`,
      ].join('\n\n'),
      soWhat: '品牌团队可以先守住已绑定资产，再把机会词补成平台愿意引用的证据链。',
      supportingFacts: [
        answerCount ? `${answerCount} 条有效回答进入本轮解析。` : '有效回答样本待补充。',
        platformCount ? `${platformCount} 个平台进入本轮比较。` : '平台样本待补充。',
        centerLinkedSignalCount ? `${centerLinkedSignalCount} 条信号进入品牌关系判断。` : '',
        marketContextSignalCount ? `${marketContextSignalCount} 条信号仅作为市场背景保留。` : '',
      ].filter(Boolean),
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下一轮保持同一批核心问题，继续追踪正向资产、部分验证战略词和风险词的位置变化。',
    },
    {
      title: `${centerTerm}的 AI 档案里写了什么`,
      readerQuestion: '平台给品牌贴上的默认标签是什么？',
      takeaway: strongTerms.length
        ? `越靠近中心，代表 AI 回答越容易自然地把该词带回${centerTerm}。`
        : `${centerTerm}暂时还没有形成足够稳定的第一反应。`,
      claims: [
        `内圈：${strongText}。`,
        `中圈：${growthText}。`,
        `外圈：${storyText}。`,
        '风险采用独立关系层，不进入远近轨道。',
      ],
      text: [
        strongTerms.length
          ? `${sentenceJoin(strongTerms, '')}位于更靠近中心的位置，代表回答已经较稳定地把这些词和${centerTerm}放在同一段品牌解释里。`
          : `这一轮还没有出现足够稳定的第一反应。${centerTerm}需要更多可被回答引用的公开证据，先把已有事实讲得更清楚。`,
        `中圈看${growthText}，它们已经有连接路径，但还需要更明确的问题、内容和证据。外圈看${storyText}，它们适合作为下一轮战略验证对象。`,
        `越靠近中心，代表 AI 回答越容易自然地把该词带回${centerTerm}。风险关系单独展开，处理信任、合规、销售方式或争议语境。`,
      ].join('\n\n'),
      soWhat: '读图时先看远近，再看词源和证据，最后回到原文判断它和品牌的真实关系。',
      supportingFacts: [
        strongTerms.length ? `本轮近端资产包括：${strongText}。` : '本轮近端资产不足。',
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下一轮围绕近端资产追加产品事实题、场景题和品牌锚定题，观察它们是否仍被平台稳定带回品牌。',
    },
    {
      title: '四个价值支柱，在 AI 叙事里是什么状态',
      readerQuestion: '四有分别被接住、牵制、反转还是缺席？',
      takeaway: growthTerms.length || storyTerms.length
        ? `${sentenceJoin([...growthTerms, ...storyTerms], '机会词')}可以作为下一轮战略验证对象，节点只是证据。`
        : '新的需求场景尚未形成稳定机会词。',
      claims: [
        `近端机会：${growthText}。`,
        `长期观察词：${storyText}。`,
      ],
      text: [
        '这一章不再逐词填表，只看几个价值支柱分别处在什么差距类型里。',
        growthTerms.length
          ? `${sentenceJoin(growthTerms, '')}已经能通向${centerTerm}，但出现频率和平台一致性还不够稳。下一轮要把这些词拆回具体问题，逐项检查哪些回答、哪些平台、哪些原文把它们带回品牌。`
          : '这一轮机会区还不明显，新的需求场景暂时没有稳定地回到品牌。',
        storyTerms.length
          ? `${sentenceJoin(storyTerms, '')}更适合作为观察词。它们尚未成为成熟资产，但可能接到长寿、陪伴、人生阶段和美好生活这些长期议题。`
          : '如果要建立新的品牌联想，下一轮问题和内容应更多覆盖人群、生活场景和真实使用理由。',
      ].join('\n\n'),
      soWhat: '机会词需要通过问题、内容和回答证据反复带回中心品牌。',
      supportingFacts: [
        `机会词：${sentenceJoin([...growthTerms, ...storyTerms], '暂未形成')}。`,
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '把机会词拆成自然提问、路径提问和品牌锚定提问，分别看平台是否会主动连回品牌。',
    },
    {
      title: '平台差异',
      readerQuestion: '不同平台怎样验证同一个战略词？',
      takeaway: firstPlatform
        ? `${platformLabel(firstPlatform.platform)}这一轮更容易从“${firstPlatform.answer_preference || '偏好待观察'}”进入${centerTerm}，但平台差异需要绑定战略词来看。`
        : '平台偏好样本还不足，暂不形成稳定判断。',
      claims: [
        firstPlatform
          ? `${platformLabel(firstPlatform.platform)}有效回答 ${firstPlatform.valid_answer_count || 0} 条。`
          : '平台有效样本不足。',
        firstPlatform
          ? `代表节点：${(firstPlatform.preferred_nodes || []).join('、') || '待观察'}。`
          : '代表节点待观察。',
      ],
      text: firstPlatform
        ? [
            `${platformLabel(firstPlatform.platform)}这一轮偏向“${firstPlatform.answer_preference || '偏好待观察'}”。同一个中心品牌，在不同平台会先进入不同入口：产品、健康、社群，或风险解释；每个平台的差异要回到具体战略词判断。`,
            firstPlatform.recommendation
              ? `内容准备要跟着平台入口走。${firstPlatform.recommendation}`
              : '内容准备要跟着平台入口走，每个平台优先补它最容易采用的证据。',
          ].join('\n\n')
        : '这一轮平台样本还不足以形成明确差异。等有效平台样本更完整后，报告应继续比较不同平台的回答偏好。',
      soWhat: '同一品牌在不同平台会被不同入口接住；内容建设应按平台补证据，避免用一套话术覆盖所有平台。',
      supportingFacts: [
        firstPlatform
          ? `${platformLabel(firstPlatform.platform)}代表节点：${(firstPlatform.preferred_nodes || []).join('、') || '待观察'}。`
          : '平台样本不足。',
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下一轮按平台分别补材料，比较它们是否仍沿同一入口组织回答。',
    },
    {
      title: '从数据到行动',
      readerQuestion: '品牌团队这周先做哪三件事？',
      takeaway: riskTerms.length
        ? `${centerTerm}应先守住${strongText}，再拉近${growthText}，并单独处理${riskText}。`
        : `${centerTerm}应先守住${strongText}，再拉近${growthText}。`,
      claims: [
        `已绑定资产：${strongText}。`,
        `正在形成的机会：${growthText}。`,
        `风险关系：${riskText}。`,
      ],
      text: [
        `${strongText}适合沉淀成可复述的问题回答素材，继续补产品事实、使用场景和权威证据。`,
        `${growthText}仍需要更多直接证据，暂时适合作为下一轮重点验证对象。`,
        competitionTerms.length
          ? `${sentenceJoin(competitionTerms, '')}要纳入竞争场景复盘，追踪它们在什么问题里替代了${centerTerm}。`
          : '竞品参照暂时不强，但后续要持续观察替代品牌是否进入同类问题。',
        riskTerms.length
          ? `${sentenceJoin(riskTerms, '')}会把回答带向信任、争议或销售方式，需要先看原文语境，再设计澄清和替代表达。`
          : '风险认知这一轮没有被明显放大，但仍需保留为复测基线。',
      ].join('\n\n'),
      soWhat: '这部分结论可以直接用于内部策略会：哪些放大、哪些补证据、哪些先澄清。',
      supportingFacts: [
        `稳定资产：${strongText}。`,
        `机会词：${growthText}。`,
        competitionTerms.length ? `竞品参照：${competitionText}。` : '本轮竞品参照未明显放大。',
        riskTerms.length ? `风险词：${riskText}。` : '本轮风险认知未明显放大。',
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下一轮分别复测已绑定资产、机会词、未验证战略词和风险关系，看它们是否发生位置变化。',
    },
    {
      title: '附录：样本、平台与原文证据',
      readerQuestion: '这轮判断的样本边界是什么？',
      takeaway: '下一轮要固定题库口径，分别追踪战略词、核心问题、风险词和机会词的轨道变化。',
      claims: [
        `继续追踪：${growthText}。`,
        `新增问题聚焦：${storyText}。`,
        `风险复测对象：${riskText}。`,
      ],
      text: [
        `${growthText}要继续追踪，重点看它们是否从中圈进入内圈。`,
        `本轮能触发${strongText}和${riskText}的问题要保留，保证下一轮可以比较位置变化。`,
        `新增问题应围绕${storyText}，补充人群、生活场景、产品证据和品牌锚定探针。`,
        `${riskText}要看提及是否下降，${growthText}和${storyText}要看是否向中心移动。`,
      ].join('\n\n'),
      soWhat: '下一轮追踪要服务决策：哪些词可以放大，哪些词继续补证据，哪些风险需要先澄清。',
      supportingFacts: [
        answerCount ? `${answerCount} 条有效回答作为本轮复测基线。` : '有效回答样本待补充。',
        platformCount ? `${platformCount} 个平台作为本轮平台基线。` : '平台样本待补充。',
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下轮报告应输出同一批战略词的位置变化、平台提及变化和风险词变化。',
    },
  ];
}

function fallbackOverallStrategyStatus({
  strongCount,
  growthCount,
  storyCount,
  riskCount,
}: {
  strongCount: number;
  growthCount: number;
  storyCount: number;
  riskCount: number;
}) {
  if (riskCount >= Math.max(strongCount + growthCount, 1) && riskCount >= 3) {
    return '被风险遮蔽';
  }
  if (strongCount >= 3 && growthCount === 0 && storyCount === 0) {
    return '回答接住较多';
  }
  if (strongCount || growthCount) {
    return '部分验证';
  }
  return '尚未验证';
}

function normalizeReportNarrativeSections(
  sections?: OntologyAssociationCircleNarrativeSection[] | null,
): ReportNarrativeSection[] | null {
  if (!Array.isArray(sections) || !sections.length) return null;
  const normalized = sections
    .map((section): ReportNarrativeSection | null => {
      const title = String(section?.title || '').trim();
      const paragraphs = Array.isArray(section?.paragraphs)
        ? section.paragraphs.map((paragraph) => commercialReportCopy(paragraph)).filter(Boolean)
        : [];
      const supportingFacts = Array.isArray(section?.supporting_facts)
        ? section.supporting_facts.map((fact) => commercialReportCopy(fact)).filter(Boolean)
        : [];
      const evidenceRefs = Array.isArray(section?.evidence_refs)
        ? section.evidence_refs.map((ref) => String(ref || '').trim()).filter(Boolean)
        : [];
      const readerQuestion = commercialReportCopy(section?.reader_question);
      const nextProbe = commercialReportCopy(section?.next_probe);
      const takeaway = commercialReportCopy(section?.takeaway);
      const claims = Array.isArray(section?.claims)
        ? section.claims.map((claim) => commercialReportCopy(claim)).filter(Boolean)
        : [];
      const soWhat = commercialReportCopy(section?.so_what);
      if (!title || !paragraphs.length) return null;
      return {
        sectionId: String(section?.section_id || '').trim() || undefined,
        title,
        text: paragraphs.join('\n\n'),
        readerQuestion,
        takeaway,
        claims,
        soWhat,
        supportingFacts,
        evidenceRefs,
        nextProbe,
      };
    })
    .filter((section): section is ReportNarrativeSection => Boolean(section));
  return normalized.length ? normalized : null;
}

function readableNarrativeSections(
  sections: ReportNarrativeSection[] | null,
): ReportNarrativeSection[] | null {
  if (!sections?.length) return null;
  const titles = sections.map((section) => section.title);
  const legacyStoryTitles = [
    '品牌联想裁决',
    '有健康｜唯一被接住的有',
    '有陪伴｜萌芽被旧认知牵制',
    '有保障 + 有价值｜先修复信任，再谈人生再出发',
    '本周 3 件事',
  ];
  const aiArchiveStoryTitles = [
    '核心判断',
    '四个价值支柱，在 AI 叙事里是什么状态',
    '平台差异',
    '从数据到行动',
  ];
  const hasStoryShape = legacyStoryTitles.every((title) => titles.includes(title))
    || aiArchiveStoryTitles.every((title) => titles.includes(title));
  if (!hasStoryShape) return null;
  const completeCount = sections.filter((section) => (
    section.readerQuestion
    && section.takeaway
    && section.claims?.length
    && section.soWhat
    && section.nextProbe
  )).length;
  return completeCount >= Math.min(3, sections.length) ? sections : null;
}

function commercialReportCopy(value?: string | null) {
  return String(value || '')
    .trim()
    .replace(new RegExp('强' + '关联轨', 'g'), '已绑定资产')
    .replace(new RegExp('弱' + '关联轨', 'g'), '待观察')
    .replace(new RegExp('可' + '争夺轨', 'g'), '近端机会')
    .replace(new RegExp('风险' + '阴影', 'g'), '风险关系')
    .replace(new RegExp('不' + '是把战略愿望直接画进图谱', 'g'), '战略愿望需要先变成回答证据，再进入图谱')
    .replace(new RegExp('不' + '是把战略词直接写进图谱', 'g'), '战略词需要先经过回答证据验证，再进入图谱')
    .replace(new RegExp('不' + '是漂亮但不可复核的图', 'g'), '需要成为可复核的图')
    .replace(new RegExp('贴' + '近度', 'g'), '图谱贴近值')
    .replace(new RegExp('疏' + '远度', 'g'), '证据缺口')
    .replace(new RegExp('证据' + '编号', 'g'), '回答证据')
    .replace('下一轮先恢复失败平台的抓取，再按战略词比较各平台的提及方式、原文摘录和图谱位置。', '下一轮沿用同一批题库，按战略词比较各平台的提及方式、原文摘录和图谱位置。')
    .replace(new RegExp('更贴' + '近中心品牌', 'g'), '更稳定地回到中心品牌')
    .replace(new RegExp('更贴' + '近品牌', 'g'), '更稳定地回到品牌')
    .replace(new RegExp('贴' + '近中心品牌', 'g'), '稳定回到中心品牌')
    .replace(new RegExp('贴' + '近品牌', 'g'), '稳定回到品牌')
    .replace(/A5/g, '圈层解析')
    .replace(new RegExp('G/' + 'D/E/P|G' + 'DE', 'g'), '工程读数');
}

function buildQuestionDefinitionFallback(
  projection: OntologyAssociationCircleProjection,
  centerTerm: string,
): OntologyAssociationCircleQuestionDefinition | undefined {
  const questionBank = projection.question_bank || [];
  const sampleScope = projection.sample_scope || {};
  const questionCount = sampleQuestionCount(sampleScope) || questionBank.length;
  if (!questionCount && !questionBank.length) return undefined;
  const uniqueValues = (key: keyof OntologyAssociationCircleQuestion) =>
    Array.from(new Set(questionBank.map((question) => String(question[key] || '').trim()).filter(Boolean))).slice(0, 6);
  const audienceSegments = uniqueValues('audience_segment');
  const probeTypes = uniqueValues('probe_type');
  const opportunityPoints = uniqueValues('opportunity_point');
  const lifeScenes = uniqueValues('life_scene');
  return {
    center_term: centerTerm,
    center_terms: projection.center_terms || [centerTerm],
    question_count: questionCount,
    question_bank_count: questionBank.length,
    audience_segments: audienceSegments,
    probe_types: probeTypes,
    opportunity_points: opportunityPoints,
    life_scenes: lifeScenes,
    sample_questions: questionBank.slice(0, 8).map((question) => ({
      id: question.id,
      text: question.text || question.question || question.question_text,
      audience_segment: question.audience_segment || undefined,
      life_scene: question.life_scene || undefined,
      opportunity_point: question.opportunity_point || undefined,
      probe_type: question.probe_type || undefined,
      metadata_status: question.metadata_status,
    })),
    definition_sentence: `中心品牌：${centerTerm}；题目数：${questionCount}；人群：${audienceSegments.join('、') || '待补充'}；探针：${probeTypes.join('、') || '待补充'}。`,
  };
}

function buildPlatformSourceSummaryFallback(
  projection: OntologyAssociationCircleProjection,
): OntologyAssociationCirclePlatformSourceSummary | undefined {
  const rows = projection.platform_comparison || [];
  const sampleScope = projection.sample_scope || {};
  if (!rows.length && !samplePlatformCount(sampleScope)) return undefined;
  const totalValidAnswers = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope) || rows.length;
  const estimatedPerPlatform = totalValidAnswers && platformCount
    ? Math.max(1, Math.round(totalValidAnswers / platformCount))
    : undefined;
  const platforms = rows.map((row) => ({
    platform: row.platform,
    total_answer_count: estimatedPerPlatform,
    valid_answer_count: estimatedPerPlatform,
    failed_answer_count: 0,
    empty_answer_count: 0,
    answer_preference: row.answer_preference,
    preferred_nodes: row.preferred_nodes,
    dominant_orbit: row.dominant_orbit,
    risk_bias: row.risk_bias,
    opportunity_bias: row.opportunity_bias,
    recommendation: row.recommendation,
  }));
  return {
    total_answer_count: totalValidAnswers || platforms.reduce((sum, row) => sum + (row.valid_answer_count || 0), 0),
    valid_answer_count: totalValidAnswers || platforms.reduce((sum, row) => sum + (row.valid_answer_count || 0), 0),
    failed_answer_count: firstSampleNumber(sampleScope.failed_answer_count),
    empty_answer_count: firstSampleNumber(sampleScope.empty_answer_count),
    platform_count: platformCount,
    platform_names: platforms.map((row) => row.platform || '').filter(Boolean),
    platforms,
  };
}

function buildEvidenceFindingsFallback(
  projection: OntologyAssociationCircleProjection,
): OntologyAssociationCircleEvidenceFinding[] {
  if (projection.evidence_findings?.length) return projection.evidence_findings;
  const samplesById = new Map((projection.evidence_samples || []).map((sample) => [sample.evidence_id, sample]));
  return (projection.nodes || []).slice(0, 12).map((node) => {
    const evidenceRefs = (node.evidence_samples || []).filter(Boolean);
    const sample = evidenceRefs.length ? samplesById.get(evidenceRefs[0]) : undefined;
    return {
      node_id: node.node_id,
      node_term: node.term,
      claim: node.orbit_reason || `${node.term}已经进入本轮回答，需要结合平台和证据继续判断。`,
      orbit: node.orbit,
      orbit_label: node.orbit_label,
      business_tag: node.business_tag,
      supporting_facts: [
        `${node.answer_count || node.evidence_count || 0} 条回答提到，有效平台 ${node.platform_count || 0} 个。`,
        `图谱贴近值 ${node.closeness_score ?? node.gravity_score ?? '-'}，距离值 ${node.distance_score ?? '-'}。`,
      ],
      evidence_refs: evidenceRefs,
      sample_platform: sample?.platform,
      sample_question: sample?.question,
      sample_excerpt: sample?.answer_excerpt,
      implication: node.orbit_reason,
    };
  }).filter((finding) => finding.node_term);
}

function buildAnalysisTraceFallback(
  questionDefinition?: OntologyAssociationCircleQuestionDefinition,
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary,
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[] = [],
): OntologyAssociationCircleAnalysisTraceItem[] {
  return [
    {
      step: 'question_scope_scan',
      title: '题目范围扫描',
      summary: questionDefinition?.definition_sentence || '从题库恢复题目、人群和探针范围。',
      outputs: questionDefinition?.probe_types || [],
    },
    {
      step: 'platform_scope_scan',
      title: '平台样本扫描',
      summary: `有效回答 ${platformSourceSummary?.valid_answer_count || 0} 条，平台 ${platformSourceSummary?.platform_count || 0} 个。`,
      outputs: platformSourceSummary?.platform_names || [],
    },
    {
      step: 'association_evidence_forge',
      title: '联想证据锻造',
      summary: '把节点、有效平台数和原文摘录合并成可解释判断。',
      outputs: evidenceFindings.slice(0, 6).map((finding) => finding.node_term || '').filter(Boolean),
    },
  ];
}

function buildSourceAppendixFallback(
  evidenceSamples: OntologyAssociationCircleEvidence[] = [],
): OntologyAssociationCircleSourceAppendixItem[] {
  return evidenceSamples.slice(0, 20).map((sample) => ({
    evidence_id: sample.evidence_id,
    node_term: sample.node_term,
    platform: sample.platform,
    question_id: sample.question_id,
    question: sample.question,
    answer_excerpt: sample.answer_excerpt,
    audience_segment: sample.audience_segment || undefined,
    life_scene: sample.life_scene || undefined,
    opportunity_point: sample.opportunity_point || undefined,
    probe_type: sample.probe_type || undefined,
  }));
}

function buildReportQualityChecksFallback({
  questionDefinition,
  platformSourceSummary,
  evidenceFindings,
  actions,
  sourceAppendix,
}: {
  questionDefinition?: OntologyAssociationCircleQuestionDefinition;
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  actions: OntologyAssociationCircleProjection['association_actions'];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
}): Record<string, unknown> {
  const requiredChecks = [
    {
      key: 'question_definition',
      label: '题目定义',
      passed: Boolean(questionDefinition?.definition_sentence || questionDefinition?.sample_questions?.length),
    },
    {
      key: 'platform_source_summary',
      label: '平台来源',
      passed: Boolean(platformSourceSummary?.platform_count || platformSourceSummary?.platforms?.length),
    },
    {
      key: 'evidence_findings',
      label: '证据链',
      passed: Boolean(evidenceFindings.length),
    },
    {
      key: 'source_appendix',
      label: '来源附录',
      passed: Boolean(sourceAppendix.length),
    },
    {
      key: 'action_review',
      label: '行动复测',
      passed: Boolean(actions?.length),
    },
  ];
  return {
    version: 'frontend_legacy_artifact_fallback',
    passed: requiredChecks.every((check) => check.passed),
    required_checks: requiredChecks,
  };
}

export function AssociationReportPanel({
  projection,
  activeCenterTerm,
  groups,
  onOpenChat,
  isOpeningChat,
}: {
  projection: OntologyAssociationCircleProjection;
  activeCenterTerm: string;
  groups: AssociationMapGroup[];
  onOpenChat: () => void;
  isOpeningChat?: boolean;
}) {
  const nodes = projection.nodes || [];
  const actions = projection.association_actions || [];
  const evidenceSamples = projection.evidence_samples || [];
  const platformComparison = projection.platform_comparison || [];
  const questionDefinition = projection.question_definition || buildQuestionDefinitionFallback(projection, activeCenterTerm);
  const platformSourceSummary = projection.platform_source_summary || buildPlatformSourceSummaryFallback(projection);
  const evidenceFindings = buildEvidenceFindingsFallback(projection);
  const sourceAppendix = projection.source_appendix?.length
    ? projection.source_appendix
    : buildSourceAppendixFallback(evidenceSamples);
  const reportQualityChecks = projection.report_quality_checks || buildReportQualityChecksFallback({
    questionDefinition,
    platformSourceSummary,
    evidenceFindings,
    actions,
    sourceAppendix,
  });
  const analysisTrace = projection.analysis_tool_trace?.length
    ? projection.analysis_tool_trace
    : buildAnalysisTraceFallback(questionDefinition, platformSourceSummary, evidenceFindings);
  const generatedReportSections = buildAssociationNarrativeReport({
    centerTerm: activeCenterTerm,
    groups,
    platformComparison,
    evidenceSamples,
    sampleScope: projection.sample_scope || {},
  });
  const hasBackendReportSpine = Boolean(
    projection.question_definition
      || projection.platform_source_summary
      || projection.evidence_findings?.length
      || projection.analysis_tool_trace?.length,
  );
  const normalizedReportSections = normalizeReportNarrativeSections(projection.report_narrative_sections);
  const reportSections = hasBackendReportSpine
    ? readableNarrativeSections(normalizedReportSections) || generatedReportSections
    : generatedReportSections;
  const compactReportSections = reportSections.slice(0, 6);
  const exportReportSections = compactReportSections;
  return (
    <section>
      <article className="bg-[var(--bg-primary)] px-6 py-7 sm:px-10 sm:py-10">
        <header className="mx-auto max-w-[1040px]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="text-xs font-medium text-[var(--text-tertiary)]">
              解读报告
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => downloadAssociationReportHtml(activeCenterTerm, exportReportSections, {
                  questionDefinition,
                  platformSourceSummary,
                  evidenceFindings,
                  analysisTrace,
                  sourceAppendix,
                  actions,
                  reportQualityChecks,
                  groups,
                  platformComparison,
                  sampleScope: projection.sample_scope || {},
                })}
                disabled={!nodes.length}
                className="inline-flex h-10 items-center gap-2 rounded-xl border border-[var(--brand-border)] px-3 text-sm text-[var(--brand-primary)] hover:bg-[var(--brand-bg)] disabled:opacity-50"
              >
                <Download size={16} />
                导出 HTML
              </button>
              <button
                type="button"
                onClick={onOpenChat}
                disabled={isOpeningChat}
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-[var(--brand-primary)] px-3 text-sm font-medium text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-60"
              >
                <MessageCircle size={16} />
                进入对话
              </button>
            </div>
          </div>
        </header>

        <div className="mx-auto mt-9 max-w-[1040px] space-y-10">
          {compactReportSections.map((section, index) => {
            const sectionId = 'sectionId' in section ? section.sectionId : undefined;
            const shouldRenderStrategyDetails =
              sectionId === 'strategy_validation' || section.title.includes('战略词逐项验证');
            return (
              <div key={section.title} className="space-y-8">
                <ReportSection
                  section={section}
                  index={index}
                  groups={groups}
                  platformComparison={platformComparison}
                  sampleScope={projection.sample_scope || {}}
                  centerTerm={activeCenterTerm}
                />
                {shouldRenderStrategyDetails ? (
                  <StrategyValidationSection
                    activeCenterTerm={activeCenterTerm}
                    questionBank={projection.question_bank || []}
                    nodes={nodes}
                    sourceAppendix={sourceAppendix}
                    platformSourceSummary={platformSourceSummary}
                    strategyValidation={projection.strategy_validation || []}
                  />
                ) : null}
              </div>
            );
          })}

          <ReportEvidenceSamples quotes={compactReportSections.flatMap((section) => (section.supportingFacts || []).filter(reportEvidenceLine))} />

          <ReportEvidenceBrief
            questionDefinition={questionDefinition}
            platformSourceSummary={platformSourceSummary}
            evidenceFindings={evidenceFindings}
            sourceAppendix={sourceAppendix}
          />
        </div>
      </article>
    </section>
  );
}

export function AssociationTrackingPanel({
  projection,
  groups,
  activeCenterTerm,
}: {
  projection: OntologyAssociationCircleProjection;
  groups: AssociationMapGroup[];
  activeCenterTerm: string;
}) {
  const nodes = projection.nodes || [];
  const tracking = readTrackingProjection(projection);
  const trackingStatus = String(tracking?.status || '');
  const trackingStatusLabel = String(tracking?.status_label || '首期基线');
  const actions = projection.association_actions || [];
  const riskNodes = groups.find((group) => group.key === 'risk')?.nodes || [];
  const growthNodes = groups.find((group) => group.key === 'growth')?.nodes || [];
  const storyNodes = groups.find((group) => group.key === 'story')?.nodes || [];

  return (
    <section className="space-y-5">
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium text-[var(--text-tertiary)]">下一轮追踪</div>
            <h2 className="mt-2 text-2xl font-semibold">{activeCenterTerm} 联想变化追踪</h2>
            <p className="mt-2 max-w-4xl text-sm leading-7 text-[var(--text-secondary)]">
              每一轮抓取都会形成一个可比较版本。追踪页关注节点是否被拉近、风险是否下降、平台偏好是否改变。
            </p>
          </div>
          <InfoPill
            label="当前状态"
            value={trackingStatusLabel}
            tone={trackingStatus === 'baseline' ? 'warning' : 'brand'}
          />
        </div>
        <div className="mt-6 grid gap-4 xl:grid-cols-4">
          <TrackingMetric title="本轮节点" value={String(nodes.length)} text="本轮可追踪的联想节点总数" />
          <TrackingMetric title="机会节点" value={String(growthNodes.length + storyNodes.length)} text="下轮观察是否继续靠近" />
          <TrackingMetric title="风险节点" value={String(riskNodes.length)} text="下轮观察是否被压降" tone="risk" />
          <TrackingMetric title="行动闭环" value={String(actions.length)} text="可进入复测的行动建议" />
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
          <h3 className="text-xl font-semibold">本轮基线</h3>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            没有上一轮时，先把当前强联想、机会、新叙事和风险作为基线。下一轮会观察哪些正向节点被拉近，哪些风险认知被压低。
          </p>
          <div className="mt-5 space-y-3">
            {groups.map((group) => (
              <div key={group.key} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold">{group.title}</div>
                  <div className="text-sm text-[var(--text-tertiary)]">{group.nodes.length} 个节点</div>
                </div>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  {group.nodes.length ? group.nodes.slice(0, 5).map((node) => `${node.term} ${scoreText(node.gravity_score ?? node.closeness_score)}`).join(' / ') : group.emptyText}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5">
            <h3 className="text-lg font-semibold">下轮重点看什么</h3>
            <div className="mt-4 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">
              <TrackingRule title="机会是否拉近" text="增长机会和新叙事是否更稳定地回到中心品牌，回答数量和平台共识是否增加。" />
              <TrackingRule title="风险是否压降" text="风险旧认知是否减少出现，是否被正向解释路径替代。" />
              <TrackingRule title="平台是否转向" text="不同平台是否从旧认知转向健康、社群、抗衰和生活方式路径。" />
            </div>
          </section>
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5">
            <h3 className="text-lg font-semibold">行动复测</h3>
            <div className="mt-4 space-y-3">
              {actions.length ? actions.slice(0, 4).map((action) => (
                <div key={action.id} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
                  <div className="text-sm font-semibold">{action.title || action.node_term || '圈层行动'}</div>
                  <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                    {commercialReportCopy(action.review_criteria || action.expected_impact || '下一轮复测该节点是否发生变化。')}
                  </p>
                  <div className="mt-3 grid gap-2 text-xs leading-5 text-[var(--text-tertiary)]">
                    {action.target_scene ? <div>场景：{action.target_scene}</div> : null}
                    {action.target_platforms?.length ? <div>平台：{action.target_platforms.slice(0, 3).join('、')}</div> : null}
                    {action.goal_metric ? <div>目标：{action.goal_metric}</div> : null}
                  </div>
                </div>
              )) : (
                <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-6 text-sm leading-6 text-[var(--text-secondary)]">
                  暂无行动建议。生成行动后，这里会展示下一轮复测标准。
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}

export function QuestionBankPanel({
  home,
  sampleScope,
  questionBank,
  uploadedQuestions,
  uploadedQuestionSource,
  uploadError,
  isReadingUpload,
  onUploadFileChange,
  onStart,
}: {
  home?: DashboardHomeData | null;
  sampleScope: Record<string, unknown>;
  questionBank: OntologyAssociationCircleQuestion[];
  uploadedQuestions: UploadedAssociationQuestion[];
  uploadedQuestionSource: string | null;
  uploadError: string | null;
  isReadingUpload: boolean;
  onUploadFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onStart: () => void;
}) {
  const [questionPage, setQuestionPage] = useState(0);
  const preview = home?.latest_report?.question_preview || [];
  const historicalQuestions = questionBank
    .map((question, index) => normalizeAssociationQuestionForReview(question, index))
    .filter((question): question is UploadedAssociationQuestion => Boolean(question));
  const displayedQuestions: UploadedAssociationQuestion[] = uploadedQuestions.length
    ? uploadedQuestions
    : historicalQuestions.length
      ? historicalQuestions
      : preview.map((question, index) => ({
        id: `report_preview_${index + 1}`,
        text: question,
        metadata_status: '来自最近报告',
        source: 'latest_report_preview',
      }));
  const questionPageCount = Math.max(1, Math.ceil(displayedQuestions.length / QUESTION_PAGE_SIZE));
  const safeQuestionPage = Math.min(questionPage, questionPageCount - 1);
  const questionStartIndex = safeQuestionPage * QUESTION_PAGE_SIZE;
  const pagedQuestions = displayedQuestions.slice(
    questionStartIndex,
    questionStartIndex + QUESTION_PAGE_SIZE,
  );
  const reviewQuestionCount = uploadedQuestions.length || historicalQuestions.length;
  const taggedQuestionCount = displayedQuestions.filter((question) => hasVisibleAssociationTags(question)).length;

  return (
    <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">问题与样本</h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">问题需要带人群、场景、探针类型和机会点标签，后续抓取和解析都复用这些元数据。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <QuestionUploadButton isReadingUpload={isReadingUpload} onUploadFileChange={onUploadFileChange} />
          <button type="button" onClick={onStart} className="rounded-xl bg-[var(--brand-primary)] px-4 py-2 text-sm font-medium text-[var(--brand-contrast)]">
            开始抓取并解析
          </button>
        </div>
      </div>
      {uploadError ? (
        <div className="mt-4 rounded-xl border border-[var(--status-warning-bg)] bg-[var(--status-warning-bg)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
          {uploadError}
        </div>
      ) : null}
      <MetricGrid
        rows={[
          ['问题数量', String(uploadedQuestions.length || sampleQuestionCount(sampleScope))],
          ['答案样本', String(sampleAnswerCount(sampleScope))],
          ['有效平台', String(samplePlatformCount(sampleScope))],
          ['关键标签覆盖', reviewQuestionCount ? `${taggedQuestionCount}/${reviewQuestionCount}` : '待生成'],
        ]}
      />
      {uploadedQuestions.length ? (
        <div className="mt-5 rounded-xl border border-[var(--brand-border)] bg-[var(--brand-bg)] px-4 py-3 text-sm leading-6 text-[var(--brand-primary)]">
          已读取 {uploadedQuestions.length} 条上传问题{uploadedQuestionSource ? `：${uploadedQuestionSource}` : ''}。缺失标签会按安利圈层规则补标，并标记为待复核。
        </div>
      ) : historicalQuestions.length ? (
        <div className="mt-5 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
          已从最近一次圈层报告恢复 {historicalQuestions.length} 条问题。上传新问题后，本页会切换为本轮待抓取清单。
        </div>
      ) : null}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-5">
        <div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">题目审阅</div>
          <div className="mt-1 text-xs text-[var(--text-tertiary)]">
            {displayedQuestions.length
              ? `显示 ${questionStartIndex + 1}-${Math.min(questionStartIndex + QUESTION_PAGE_SIZE, displayedQuestions.length)} / ${displayedQuestions.length}`
              : '暂无题目'}
          </div>
        </div>
        {questionPageCount > 1 ? (
          <div className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1">
            <button
              type="button"
              aria-label="上一页问题"
              disabled={safeQuestionPage === 0}
              onClick={() => setQuestionPage((page) => Math.max(0, page - 1))}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="w-16 px-1 text-center text-xs font-medium text-[var(--text-tertiary)]">
              {safeQuestionPage + 1} / {questionPageCount}
            </span>
            <button
              type="button"
              aria-label="下一页问题"
              disabled={safeQuestionPage >= questionPageCount - 1}
              onClick={() => setQuestionPage((page) => Math.min(questionPageCount - 1, page + 1))}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        ) : null}
      </div>
      <div className="mt-4 space-y-3">
        {pagedQuestions.length ? pagedQuestions.map((question, index) => (
          <div key={`${question.id}-${questionStartIndex + index}`} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-[var(--text-primary)]">{question.text}</span>
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-xs text-[var(--text-tertiary)]">
                {displayQuestionMetadataStatus(question)}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--text-tertiary)]">
              <span>人群：{question.audience_segment || '待补充'}</span>
              <span>场景：{question.life_scene || '待补充'}</span>
              <span>探针：{question.probe_type || '待补充'}</span>
              <span>机会点：{question.opportunity_point || '待补充'}</span>
            </div>
          </div>
        )) : (
          <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-6 text-sm leading-6 text-[var(--text-secondary)]">
            暂无问题预览。上传问题或生成问题矩阵后，这里展示入库问题和标签覆盖情况。
          </div>
        )}
      </div>
    </section>
  );
}

export function EvidenceWorkbenchPanel({
  projection,
  activeCenterTerm,
}: {
  projection: OntologyAssociationCircleProjection;
  activeCenterTerm: string;
}) {
  const evidenceSamples = projection.evidence_samples || [];
  const platformComparison = projection.platform_comparison || [];
  const questionDefinition = projection.question_definition || buildQuestionDefinitionFallback(projection, activeCenterTerm);
  const platformSourceSummary = projection.platform_source_summary || buildPlatformSourceSummaryFallback(projection);
  const evidenceFindings = buildEvidenceFindingsFallback(projection);
  const sourceAppendix = projection.source_appendix?.length
    ? projection.source_appendix
    : buildSourceAppendixFallback(evidenceSamples);
  const analysisTrace = projection.analysis_tool_trace?.length
    ? projection.analysis_tool_trace
    : buildAnalysisTraceFallback(questionDefinition, platformSourceSummary, evidenceFindings);
  const actions = projection.association_actions || [];
  return (
    <section className="space-y-5">
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6 sm:p-8">
        <div className="text-xs font-medium text-[var(--text-tertiary)]">Evidence Workbench</div>
        <h2 className="mt-2 text-3xl font-semibold leading-tight">证据与原文</h2>
        <p className="mt-3 max-w-5xl text-sm leading-7 text-[var(--text-secondary)]">
          这里把判断读数放回证据链：这一轮问了什么、哪些平台给了有效回答、哪些原文把节点带回品牌，以及下一轮应该复测什么。
        </p>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <EvidenceMetric title="问题边界" value={String(questionDefinition?.question_count || sampleQuestionCount(projection.sample_scope || {}) || '-')} text="上传或生成的问题数量" />
          <EvidenceMetric title="有效回答" value={String(platformSourceSummary?.valid_answer_count || sampleAnswerCount(projection.sample_scope || {}) || '-')} text="进入圈层解析的回答" />
          <EvidenceMetric title="平台来源" value={String(platformSourceSummary?.platform_count || samplePlatformCount(projection.sample_scope || {}) || '-')} text="有可读答案的平台" />
          <EvidenceMetric title="证据节点" value={String(evidenceFindings.length || projection.nodes.length || '-')} text="能追溯到原文的判断" />
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">判断步骤</div>
          <h3 className="mt-2 text-2xl font-semibold">回答怎样进入圈层</h3>
          <div className="mt-5 space-y-4">
            {analysisTrace.length ? analysisTrace.slice(0, 6).map((trace, index) => (
              <div key={trace.step || trace.title || index} className="grid grid-cols-[34px_minmax(0,1fr)] gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--brand-border)] bg-[var(--brand-bg)] text-sm font-semibold text-[var(--brand-primary)]">
                  {index + 1}
                </div>
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
                  <div className="font-semibold">{trace.title || trace.step}</div>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{trace.summary}</p>
                  {trace.outputs?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {trace.outputs.slice(0, 6).map((output) => (
                        <span key={output} className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 py-1 text-xs text-[var(--text-tertiary)]">
                          {output}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            )) : (
              <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-6 text-sm leading-6 text-[var(--text-secondary)]">
                暂无分析轨迹。完成抓取和解析后，这里会展示题目扫描、平台核验、节点归并和行动合成。
              </div>
            )}
          </div>
        </article>

        <aside className="space-y-5">
          <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
            <div className="text-xs font-medium text-[var(--text-tertiary)]">问题范围</div>
            <h3 className="mt-2 text-xl font-semibold">这轮题目覆盖了什么</h3>
            {questionDefinition?.definition_sentence ? (
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">{questionDefinition.definition_sentence}</p>
            ) : (
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">暂无题目定义。上传问题或生成问题矩阵后，报告会记录人群、场景、探针和机会点。</p>
            )}
            <div className="mt-4 grid gap-3">
              <EvidenceScopeCard title="人群" items={questionDefinition?.audience_segments || []} />
              <EvidenceScopeCard title="机会点" items={questionDefinition?.opportunity_points || []} />
              <EvidenceScopeCard title="探针" items={questionDefinition?.probe_types || []} />
            </div>
          </article>

          <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
            <div className="text-xs font-medium text-[var(--text-tertiary)]">平台来源</div>
            <h3 className="mt-2 text-xl font-semibold">哪些平台贡献了样本</h3>
            <div className="mt-4 space-y-3">
              {(platformSourceSummary?.platforms?.length ? platformSourceSummary.platforms : platformComparison).slice(0, 6).map((item) => (
                <div key={item.platform} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-semibold">{platformLabel(item.platform || '')}</span>
                    {'valid_answer_count' in item ? (
                      <span className="text-xs text-[var(--text-tertiary)]">{item.valid_answer_count || 0} 条有效</span>
                    ) : null}
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                    {item.answer_preference || '偏好待观察'}
                  </p>
                </div>
              ))}
              {!(platformSourceSummary?.platforms?.length || platformComparison.length) ? (
                <div className="text-sm leading-6 text-[var(--text-secondary)]">暂无平台对比样本。</div>
              ) : null}
            </div>
          </article>
        </aside>
      </div>

      <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6 sm:p-8">
        <div className="text-xs font-medium text-[var(--text-tertiary)]">节点证据</div>
        <h3 className="mt-2 text-2xl font-semibold">每个判断回到哪条回答</h3>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {evidenceFindings.length ? evidenceFindings.slice(0, 8).map((finding) => (
            <div key={finding.node_id || finding.node_term} className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-lg font-semibold">{finding.node_term || '联想节点'}</h4>
                {finding.business_tag ? (
                  <span className="rounded-full border border-[var(--brand-border)] bg-[var(--brand-bg)] px-2 py-1 text-xs text-[var(--brand-primary)]">
                    {finding.business_tag}
                  </span>
                ) : null}
              </div>
              <p className="mt-3 text-sm leading-7 text-[var(--text-primary)]">{commercialReportCopy(finding.claim)}</p>
              <ul className="mt-3 space-y-1 text-xs leading-5 text-[var(--text-secondary)]">
                {(finding.supporting_facts || []).slice(0, 3).map((fact) => (
                  <li key={fact}>• {commercialReportCopy(fact)}</li>
                ))}
              </ul>
              {finding.sample_excerpt ? (
                <blockquote className="mt-4 border-l-2 border-[var(--brand-border)] pl-3 text-xs leading-5 text-[var(--text-secondary)]">
                  {finding.sample_platform} / {finding.sample_question}: {finding.sample_excerpt}
                </blockquote>
              ) : null}
            </div>
          )) : (
            <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-6 text-sm leading-6 text-[var(--text-secondary)] lg:col-span-2">
              暂无回答证据。启动抓取后，有效回答、失败回答和样本不足会在样本口径中区分。
            </div>
          )}
        </div>
      </article>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">原文附录</div>
          <h3 className="mt-2 text-xl font-semibold">可复核回答样本</h3>
          <div className="mt-4 space-y-3">
            {sourceAppendix.length ? sourceAppendix.slice(0, 10).map((item) => (
              <div key={item.evidence_id || `${item.platform}-${item.node_term}`} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
                <div className="text-xs text-[var(--text-tertiary)]">{item.evidence_id || '证据'} · {platformLabel(item.platform || '')} · {item.node_term || '节点'}</div>
                <p className="mt-2 text-sm leading-6 text-[var(--text-primary)]">{item.question}</p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{cleanEvidenceExcerpt(item.answer_excerpt, 160)}</p>
              </div>
            )) : (
              <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-6 text-sm leading-6 text-[var(--text-secondary)]">
                暂无来源附录。
              </div>
            )}
          </div>
        </article>

        <aside className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">复测动作</div>
          <h3 className="mt-2 text-xl font-semibold">这轮之后怎么验证</h3>
          <div className="mt-4 space-y-3">
            {actions.length ? actions.slice(0, 6).map((action) => (
              <div key={action.id} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
                <div className="text-sm font-semibold">{action.title || action.action_label || action.node_term || '圈层行动'}</div>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{commercialReportCopy(action.review_criteria || action.expected_impact || '下一轮复测该节点是否发生变化。')}</p>
                {(action.evidence_refs || []).length ? (
                  <p className="mt-2 text-xs text-[var(--text-tertiary)]">证据：{(action.evidence_refs || []).join('、')}</p>
                ) : null}
              </div>
            )) : (
              <div className="text-sm leading-6 text-[var(--text-secondary)]">暂无复测动作。报告生成后，这里会列出对应节点、平台和回答摘录。</div>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}

function EvidenceMetric({ title, value, text }: { title: string; value: string; text: string }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
      <div className="text-xs text-[var(--text-tertiary)]">{title}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">{text}</p>
    </div>
  );
}

export function WeightRulePanel() {
  return (
    <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6">
      <h2 className="text-2xl font-semibold">判断规则</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
        圈层位置不由前端手工摆放，只读取回答解析后的关系强弱、出现位置、证据规模和平台一致性。
      </p>
      <div className="mt-6 grid gap-4 xl:grid-cols-5">
        <WeightCard title="出现频率" value="30%" text="概念在有效回答中出现得越多，越容易成为稳定联想。" />
        <WeightCard title="位置分" value="20%" text="答案开头、定义句或推荐前列出现，比尾部补充更靠近中心。" />
        <WeightCard title="关系类型" value="20%" text="定义、推荐和风险关系强于普通解释关系。" />
        <WeightCard title="场景覆盖" value="15%" text="覆盖越多母题、人群或生活场景，联想越稳定。" />
        <WeightCard title="模型一致性" value="15%" text="跨平台都出现的节点，比单平台信号更接近中心。" />
      </div>
    </section>
  );
}

export function buildAssociationMapGroups(nodes: OntologyAssociationCircleNode[]): AssociationMapGroup[] {
  const grouped: Record<AssociationMapGroupKey, OntologyAssociationCircleNode[]> = {
    strong: [],
    growth: [],
    story: [],
    risk: [],
  };

  nodes.forEach((node) => {
    grouped[classifyAssociationNode(node)].push(node);
  });

  Object.values(grouped).forEach((groupNodes) => {
    groupNodes.sort(compareAssociationNodesForPriority);
  });

  return [
    {
      key: 'strong',
      title: '已绑定资产',
      subtitle: '平台回答已经稳定绑定的第一反应',
      emptyText: '本轮还没有稳定强联想。',
      tone: 'brand',
      nodes: grouped.strong,
    },
    {
      key: 'growth',
      title: '近端机会',
      subtitle: '已有回答证据，下一步补直接证据',
      emptyText: '本轮还没有明显近端机会。',
      tone: 'opportunity',
      nodes: grouped.growth,
    },
    {
      key: 'story',
      title: '远端机会 / 待观察',
      subtitle: '战略上重要，仍需补样本和场景',
      emptyText: '本轮还没有识别到远端机会。',
      tone: 'story',
      nodes: grouped.story,
    },
    {
      key: 'risk',
      title: '风险关系',
      subtitle: '单独观察是否干扰品牌解释',
      emptyText: '本轮没有明显风险认知。',
      tone: 'risk',
      nodes: grouped.risk,
    },
  ];
}

function compareAssociationNodesForPriority(
  left: OntologyAssociationCircleNode,
  right: OntologyAssociationCircleNode,
) {
  const leftPriority = typeof left.priority_rank === 'number' ? left.priority_rank : 99;
  const rightPriority = typeof right.priority_rank === 'number' ? right.priority_rank : 99;
  if (leftPriority !== rightPriority) return leftPriority - rightPriority;
  const leftEvidence = nodeEvidenceCount(left);
  const rightEvidence = nodeEvidenceCount(right);
  if (leftEvidence !== rightEvidence) return rightEvidence - leftEvidence;
  const leftPlatform = nodePlatformCount(left);
  const rightPlatform = nodePlatformCount(right);
  if (leftPlatform !== rightPlatform) return rightPlatform - leftPlatform;
  return scoreNumber(right.gravity_score ?? right.closeness_score ?? right.association_score)
    - scoreNumber(left.gravity_score ?? left.closeness_score ?? left.association_score);
}


function classifyAssociationNode(node: OntologyAssociationCircleNode): AssociationMapGroupKey {
  const text = `${node.term || ''} ${node.business_tag || ''} ${node.semantic_direction || ''} ${node.orbit_label || ''} ${node.maturity_label || ''}`;
  if (isRiskNodeForMap(node)) {
    return 'risk';
  }
  if (node.orbit === 'core_near' || node.orbit === 'strong' || node.orbit === 'R1') {
    return 'strong';
  }
  if (node.orbit === 'near_opportunity' || node.maturity_tier === 'near_opportunity' || /近端机会/.test(text)) {
    return 'growth';
  }
  if (
    node.orbit === 'far_opportunity'
    || node.maturity_tier === 'far_opportunity'
    || node.maturity_tier === 'watch_signal'
    || node.maturity_tier === 'evidence_gap'
    || /远端机会|待观察|待验证|长寿|人生再出发|被需要|价值感|新叙事/.test(text)
    || node.orbit === 'weak'
    || node.orbit === 'R3'
    || node.orbit === 'blank'
  ) {
    return 'story';
  }
  return 'growth';
}

function cleanEvidenceExcerpt(value?: string, maxLength = 180) {
  const text = String(value || '证据摘录待补充。')
    .replace(/[\u{1F300}-\u{1FAFF}]/gu, '')
    .replace(/[#*_`>|[\]()]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function scoreNumber(value?: number) {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : 0;
}

function readTrackingProjection(projection: OntologyAssociationCircleProjection) {
  const tracking = projection.tracking_projection;
  return tracking && typeof tracking === 'object' ? tracking as Record<string, unknown> : null;
}

function TrackingMetric({
  title,
  value,
  text,
  tone = 'neutral',
}: {
  title: string;
  value: string;
  text: string;
  tone?: 'neutral' | 'risk';
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-5">
      <div className="text-xs text-[var(--text-tertiary)]">{title}</div>
      <div className={`mt-2 text-3xl font-semibold ${tone === 'risk' ? 'text-[var(--error)]' : 'text-[var(--text-primary)]'}`}>
        {value}
      </div>
      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{text}</p>
    </div>
  );
}

function TrackingRule({ title, text }: { title: string; text: string }) {
  return (
    <div className="border-l-4 border-[var(--brand-border)] bg-[var(--bg-secondary)] px-4 py-3">
      <div className="font-semibold text-[var(--text-primary)]">{title}</div>
      <p className="mt-1">{text}</p>
    </div>
  );
}

function MetricGrid({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="mt-5 grid grid-cols-2 gap-3">
      {rows.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
          <div className="text-xs text-[var(--text-tertiary)]">{label}</div>
          <div className="mt-1 text-xl font-semibold">{value}</div>
        </div>
      ))}
    </div>
  );
}

interface StrategyValidationRow {
  term: string;
  status: 'validated' | 'partial' | 'risk' | 'missing';
  statusLabel: string;
  validationLabel?: string;
  decisionTier?: string;
  stanceSummary?: OntologyAssociationCircleStrategyValidation['stance_summary'];
  intent: string;
  questionCount: number;
  relatedQuestions: OntologyAssociationCircleQuestion[];
  relatedNodes: OntologyAssociationCircleNode[];
  platformNames: string[];
  platformMentions: string[];
  answerResult: string;
  graphPerformance: string;
  implication: string;
  actionRecommendation?: string;
  evidenceRefs: string[];
}

function StrategyValidationSection({
  activeCenterTerm,
  questionBank,
  nodes,
  sourceAppendix,
  platformSourceSummary,
  strategyValidation,
}: {
  activeCenterTerm: string;
  questionBank: OntologyAssociationCircleQuestion[];
  nodes: OntologyAssociationCircleNode[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
  strategyValidation: OntologyAssociationCircleStrategyValidation[];
}) {
  const rows = buildStrategyValidationRows({
    strategyValidation,
    questionBank,
    nodes,
    sourceAppendix,
    platformSourceSummary,
  });
  if (!rows.length) return null;
  const validatedCount = rows.filter((row) => row.status === 'validated').length;
  const partialCount = rows.filter((row) => row.status === 'partial').length;
  const riskCount = rows.filter((row) => row.status === 'risk').length;

  return (
    <section className="border-t border-[var(--border-subtle)] pt-10">
      <header>
        <div className="text-xs font-medium text-[var(--text-tertiary)]">战略验证</div>
        <h3 className="mt-2 text-[26px] font-semibold leading-snug" style={{ fontFamily: REPORT_SERIF_FONT }}>
          把安利的战略词放回 AI 回答里检验
        </h3>
        <p className="mt-4 text-[17px] leading-9 text-[var(--text-secondary)]" style={{ fontFamily: REPORT_SERIF_FONT }}>
          这一部分按品牌战略词展开。先看哪些题在验证它，再看各个平台是否把它带回{activeCenterTerm}，最后回到图谱里的位置和证据。
        </p>
        <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
          回答接住 {validatedCount} 个，部分验证 {partialCount} 个，风险相关 {riskCount} 个。
        </p>
      </header>

      <div className="mt-7 space-y-8">
        {rows.map((row) => (
          <article key={row.term} className="border-t border-[var(--border-subtle)] pt-7 first:border-t-0 first:pt-0">
            <h4 className="text-2xl font-semibold" style={{ fontFamily: REPORT_SERIF_FONT }}>{row.term}</h4>
            <p className="mt-1 text-sm text-[var(--text-tertiary)]">{row.statusLabel}</p>

            <div className="mt-5 space-y-4 text-[16px] leading-8 text-[var(--text-secondary)]" style={{ fontFamily: REPORT_SERIF_FONT }}>
              <p><span className="font-semibold text-[var(--text-primary)]">战略意图：</span>{row.intent}</p>
              <p><span className="font-semibold text-[var(--text-primary)]">相关问题：</span>共 {row.questionCount} 道题在验证这个方向。</p>
              {row.relatedQuestions.length ? (
                <ul className="space-y-2 pl-5 text-sm leading-7 text-[var(--text-secondary)]" style={{ fontFamily: 'var(--font-sans, inherit)' }}>
                  {row.relatedQuestions.slice(0, 3).map((question) => (
                    <li key={question.id || question.text || question.question} className="list-disc">
                      {question.text || question.question || question.question_text}
                    </li>
                  ))}
                </ul>
              ) : null}
              <p><span className="font-semibold text-[var(--text-primary)]">AI 回答结果：</span>{row.answerResult}</p>
              <p><span className="font-semibold text-[var(--text-primary)]">图谱表现：</span>{row.graphPerformance}</p>
              <p>
                <span className="font-semibold text-[var(--text-primary)]">品牌判断：</span>{row.implication}
              </p>
              {row.actionRecommendation ? (
                <p>
                  <span className="font-semibold text-[var(--text-primary)]">下一步动作：</span>
                  {row.actionRecommendation}
                </p>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function buildStrategyValidationRows({
  strategyValidation,
  questionBank,
  nodes,
  sourceAppendix,
  platformSourceSummary,
}: {
  strategyValidation: OntologyAssociationCircleStrategyValidation[];
  questionBank: OntologyAssociationCircleQuestion[];
  nodes: OntologyAssociationCircleNode[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
}): StrategyValidationRow[] {
  const backendRows = buildBackendStrategyValidationRows({
    strategyValidation,
    questionBank,
    nodes,
    sourceAppendix,
    platformSourceSummary,
  });
  if (backendRows.length) return backendRows;
  return buildFallbackStrategyValidationRows({
    questionBank,
    nodes,
    sourceAppendix,
    platformSourceSummary,
  });
}

function buildBackendStrategyValidationRows({
  strategyValidation,
  questionBank,
  nodes,
  sourceAppendix,
  platformSourceSummary,
}: {
  strategyValidation: OntologyAssociationCircleStrategyValidation[];
  questionBank: OntologyAssociationCircleQuestion[];
  nodes: OntologyAssociationCircleNode[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
}): StrategyValidationRow[] {
  if (!Array.isArray(strategyValidation) || !strategyValidation.length) return [];
  const nodesById = new Map(nodes.map((node) => [node.node_id, node]));
  const questionsById = new Map(
    questionBank
      .map((question) => [String(question.id || '').trim(), question] as const)
      .filter(([id]) => Boolean(id)),
  );
  const platformNames = uniqueStrings([
    ...(platformSourceSummary?.platform_names || []),
    ...((platformSourceSummary?.platforms || []).map((row) => row.platform || '')),
    ...sourceAppendix.map((item) => item.platform || ''),
  ]);

  return strategyValidation.slice(0, 12).map((row) => {
    const term = String(row.strategy_term || '').trim() || '未命名战略词';
    const relatedNodes = (row.related_node_ids || [])
      .map((id) => nodesById.get(String(id || '').trim()))
      .filter((item): item is OntologyAssociationCircleNode => Boolean(item));
    const evidenceQuestionIds = uniqueStrings(
      relatedNodes.flatMap((node) => (node.trigger_questions || []).map((id) => String(id || '').trim())),
    );
    const displayQuestionIds = evidenceQuestionIds.length
      ? evidenceQuestionIds
      : uniqueStrings((row.question_refs || []).map((id) => String(id || '').trim()));
    const relatedQuestions = displayQuestionIds
      .map((id) => questionsById.get(id))
      .filter((item): item is OntologyAssociationCircleQuestion => Boolean(item));
    const platformMentions = buildBackendPlatformMentions(row, platformNames);
    const status = normalizeStrategyStatus(row.status, relatedNodes);
    return {
      term,
      status,
      statusLabel: String(row.validation_label || '').trim() || strategyStatusLabel(status),
      validationLabel: String(row.validation_label || '').trim() || undefined,
      decisionTier: String(row.decision_tier || '').trim() || undefined,
      stanceSummary: row.stance_summary,
      intent: strategyIntentText(term),
      questionCount: displayQuestionIds.length || Number(row.question_count || 0),
      relatedQuestions,
      relatedNodes,
      platformNames,
      platformMentions,
      answerResult: strategyAnswerResultText({
        answerMentionCount: Number(row.answer_mention_count || 0),
        platformCount: Number(row.platform_count || 0),
        platformMentions,
      }),
      graphPerformance: strategyGraphPerformanceText(relatedNodes),
      implication: strategyImplication(term, status, relatedNodes, Number(row.platform_count || 0), row),
      actionRecommendation: strategyActionRecommendationText(
        String(row.action_recommendation || '').trim(),
        term,
        status,
        relatedNodes,
        Number(row.platform_count || 0),
        row,
      ),
      evidenceRefs: Array.isArray(row.evidence_refs) ? row.evidence_refs : [],
    };
  });
}

function buildFallbackStrategyValidationRows({
  questionBank,
  nodes,
  sourceAppendix,
  platformSourceSummary,
}: {
  questionBank: OntologyAssociationCircleQuestion[];
  nodes: OntologyAssociationCircleNode[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
}): StrategyValidationRow[] {
  const questionsById = new Map(
    questionBank
      .map((question) => [String(question.id || '').trim(), question] as const)
      .filter(([id]) => Boolean(id)),
  );
  const fallbackPlatforms = uniqueStrings([
    ...(platformSourceSummary?.platform_names || []),
    ...((platformSourceSummary?.platforms || []).map((row) => row.platform || '')),
    ...sourceAppendix.map((item) => item.platform || ''),
  ]);
  const strategyNodes = nodes
    .filter((node) => isStrategyNode(node))
    .sort((left, right) => nodeClosenessValue(right) - nodeClosenessValue(left))
    .slice(0, 12);

  return strategyNodes.map((node) => {
    const evidenceRows = sourceAppendix.filter((item) => item.node_term === node.term);
    const relatedQuestionIds = uniqueStrings([
      ...((node.trigger_questions || []).map((id) => String(id || ''))),
      ...evidenceRows.map((item) => item.question_id || ''),
    ]);
    const relatedQuestions = relatedQuestionIds
      .map((id) => questionsById.get(id))
      .filter((item): item is OntologyAssociationCircleQuestion => Boolean(item));
    const platformDistribution = node.platform_distribution || {};
    const platformMentions = buildFallbackPlatformMentions({
      distribution: platformDistribution,
      evidenceRows,
      fallbackPlatforms,
    });
    const platformCount = Number(node.platform_count || Object.keys(platformDistribution).length || 0);
    const answerMentionCount = Number(node.answer_count || node.evidence_count || evidenceRows.length || 0);
    const relatedNodes = [node];
    const status = normalizeStrategyStatus(undefined, relatedNodes);
    return {
      term: node.term || '未命名战略词',
      status,
      statusLabel: strategyStatusLabel(status),
      intent: strategyIntentText(node.term || ''),
      questionCount: relatedQuestionIds.length || relatedQuestions.length,
      relatedQuestions,
      relatedNodes,
      platformNames: fallbackPlatforms,
      platformMentions,
      answerResult: strategyAnswerResultText({
        answerMentionCount,
        platformCount,
        platformMentions,
      }),
      graphPerformance: strategyGraphPerformanceText(relatedNodes),
      implication: strategyImplication(node.term || '', status, relatedNodes, platformCount),
      actionRecommendation: strategyActionRecommendationText(
        '',
        node.term || '',
        status,
        relatedNodes,
        platformCount,
      ),
      evidenceRefs: Array.isArray(node.evidence_samples) ? node.evidence_samples : [],
    };
  });
}

function isStrategyNode(node: OntologyAssociationCircleNode): boolean {
  const originText = `${node.term_origin || ''} ${node.origin_label || ''} ${node.business_tag || ''}`;
  return Boolean(
    node.term
      && !node.is_risk_term
      && (
        node.is_target_term
        || node.term_origin === 'strategy'
        || /战略词|目标心智|战略验证/.test(originText)
      ),
  );
}

function buildFallbackPlatformMentions({
  distribution,
  evidenceRows,
  fallbackPlatforms,
}: {
  distribution: Record<string, number>;
  evidenceRows: OntologyAssociationCircleSourceAppendixItem[];
  fallbackPlatforms: string[];
}): string[] {
  const rowsByPlatform = new Map<string, OntologyAssociationCircleSourceAppendixItem[]>();
  evidenceRows.forEach((item) => {
    const platform = String(item.platform || '').trim();
    if (!platform) return;
    const rows = rowsByPlatform.get(platform) || [];
    rows.push(item);
    rowsByPlatform.set(platform, rows);
  });
  const platformNames = uniqueStrings([
    ...Object.keys(distribution || {}),
    ...Array.from(rowsByPlatform.keys()),
    ...fallbackPlatforms,
  ]);
  return platformNames.slice(0, 6).map((platform) => {
    const count = Number(distribution?.[platform] || rowsByPlatform.get(platform)?.length || 0);
    const sample = rowsByPlatform.get(platform)?.find((item) => item.answer_excerpt)?.answer_excerpt || '';
    if (sample && count > 0) {
      return `${platform}提及 ${count} 次，代表摘录：“${cleanEvidenceExcerpt(sample, 64)}”`;
    }
    return count > 0 ? `${platform}提及 ${count} 次` : `${platform}暂未形成稳定提及`;
  });
}

function buildBackendPlatformMentions(
  row: OntologyAssociationCircleStrategyValidation,
  fallbackPlatforms: string[],
): string[] {
  const outcomes = Array.isArray(row.platform_outcomes) ? row.platform_outcomes : [];
  if (outcomes.length) {
    return outcomes.map((item) => {
      const platform = String(item.platform || '').trim() || '未知平台';
      const count = Number(item.answer_count || 0);
      const excerpt = String(item.sample_excerpt || '').trim();
      const stanceText = strategyStanceLabel(item.stance);
      const mentionText = count > 0 ? `${platform}${stanceText} ${count} 次` : `${platform}暂未形成稳定提及`;
      return excerpt
        ? `${mentionText}，样本：“${cleanEvidenceExcerpt(excerpt, 72)}”`
        : mentionText;
    });
  }
  const distribution = row.platform_distribution || {};
  const platforms = uniqueStrings([...Object.keys(distribution), ...fallbackPlatforms]);
  return platforms.slice(0, 6).map((platform) => {
    const count = Number(distribution[platform] || 0);
    return count > 0 ? `${platform}提及 ${count} 次` : `${platform}暂未形成稳定提及`;
  });
}

function normalizeStrategyStatus(
  status: OntologyAssociationCircleStrategyValidation['status'],
  relatedNodes: OntologyAssociationCircleNode[],
): StrategyValidationRow['status'] {
  if (relatedNodes.some((node) => node.is_risk_term)) return 'risk';
  if (status === 'validated') return 'validated';
  if (status === 'partial') return 'partial';
  if (status === 'missing') return 'missing';
  if (status === 'risk') return 'risk';
  return relatedNodes.length ? 'partial' : 'missing';
}

function strategyStatusLabel(status: StrategyValidationRow['status']): string {
  if (status === 'validated') return '已被回答接住';
  if (status === 'partial') return '部分验证';
  if (status === 'risk') return '被风险遮蔽';
  return '尚未验证';
}

function strategyStanceLabel(stance?: string): string {
  if (stance === 'supportive') return '正向提及';
  if (stance === 'skeptical') return '质疑提及';
  if (stance === 'risk') return '风险提醒';
  if (stance === 'competitive') return '竞品替代';
  if (stance === 'neutral') return '中性提及';
  return '提及';
}

function strategyIntentText(term: string): string {
  if (/健康|抗衰|长寿|百岁|营养/.test(term)) {
    return '让品牌从产品认知进入长期健康管理和人生周期支持。';
  }
  if (/陪伴|关系|社群|一起/.test(term)) {
    return '让品牌承担关系连接、社群支持和持续陪伴的心智角色。';
  }
  if (/人生|价值|再出发|安利人|成长/.test(term)) {
    return '让品牌连接个人成长、角色转换和重新被需要的生活叙事。';
  }
  return '让这个词成为平台回答可以自然带回品牌的目标心智。';
}

function strategyAnswerResultText({
  answerMentionCount,
  platformCount,
  platformMentions,
}: {
  answerMentionCount: number;
  platformCount?: number;
  platformMentions: string[];
}): string {
  const summary = `回答提及 ${answerMentionCount} 条，覆盖 ${platformCount ?? 0} 个平台。`;
  return platformMentions.length ? `${summary}${platformMentions.join('；')}` : summary;
}

function strategyGraphPerformanceText(nodes: OntologyAssociationCircleNode[]): string {
  if (!nodes.length) return '图谱上还没有形成稳定节点。';
  return nodes.slice(0, 4).map((node) => (
    `${node.term}位于${relationshipRead(node).label}，距离值 ${nodeDistanceValue(node)}，证据 ${nodeEvidenceCount(node)} 条，覆盖 ${nodePlatformCount(node)} 个平台`
  )).join('；');
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const text = String(value || '').trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
  }
  return result;
}

function strategyImplication(
  term: string,
  status: StrategyValidationRow['status'],
  nodes: OntologyAssociationCircleNode[],
  platformCount: number,
  backendRow?: OntologyAssociationCircleStrategyValidation,
): string {
  const nodeText = nodes.length ? nodes.slice(0, 3).map((node) => node.term).join('、') : '稳定节点';
  const stance = backendRow?.stance_summary || {};
  const supportive = Number(stance.supportive || 0);
  const skeptical = Number(stance.skeptical || 0);
  const riskLike = Number(stance.risk || 0) + Number(stance.competitive || 0);
  const evidenceCount = Number(backendRow?.answer_mention_count || 0);
  const tier = backendRow?.decision_tier || '';
  const lane = strategyLane(term);
  const focus = strategyMeaningFocus(term, lane, tier, status);
  if (tier === 'amplify' || (status === 'validated' && supportive >= 30)) {
    return `${term}已有 ${supportive || evidenceCount} 条正向支撑，覆盖 ${platformCount} 个平台，并通过${nodeText}回到品牌。${focus}`;
  }
  if (tier === 'risk_first' || status === 'risk') {
    return `${term}当前有 ${riskLike || evidenceCount} 条风险或竞品替代语境。${focus}`;
  }
  if (tier === 'evidence_building' || status === 'partial') {
    const cautionText = skeptical || riskLike ? `同时出现 ${skeptical + riskLike} 条质疑或风险语境，` : '';
    return `${term}已经有 ${evidenceCount} 条回答线索，${cautionText}${focus}`;
  }
  return `${term}在本轮问题里被测试过，回答证据仍不足。${focus}`;
}

function strategyLane(term: string): 'relationship' | 'career' | 'green' | 'health' | 'general' {
  if (/财务|保障|事业|安利人|价值|再出发|成长/.test(term)) return 'career';
  if (/关系|陪伴|社群|一起/.test(term)) return 'relationship';
  if (/绿色|和谐|环境/.test(term)) return 'green';
  if (/健康|抗衰|长寿|活力|营养|身体|情绪|大健康/.test(term)) return 'health';
  return 'general';
}

function strategyMeaningFocus(
  term: string,
  lane: ReturnType<typeof strategyLane>,
  tier: string,
  status: StrategyValidationRow['status'],
) {
  if (tier === 'amplify' || status === 'validated') {
    return ({
      relationship: '关系陪伴已经被平台理解，下一步要补社群边界、真实陪伴案例和弱销售压力表达。',
      career: '事业与价值感已经能带回品牌，下一步要补收入边界、投入成本和合规参与路径。',
      green: '绿色生活已经有回答线索，下一步要用家庭环境健康、净水净化和清洁场景承接。',
      health: '健康资产已经较清晰，下一步要沉淀科学依据、产品组合和人群使用场景。',
      general: `${term}具备放大基础，下一步要沉淀稳定表达和可引用证据。`,
    })[lane];
  }
  if (tier === 'risk_first' || status === 'risk') {
    return ({
      relationship: '风险多来自熟人压力和销售边界，需要先解释社群支持机制。',
      career: '风险多来自收益预期和参与成本，需要先写清合规边界。',
      green: '风险多来自口号化表达，需要先补具体产品和场景证据。',
      health: '风险多来自功效和信任问题，需要先补科学依据和适用边界。',
      general: '需要先处理质疑来源，再判断能否进入正向资产。',
    })[lane];
  }
  if (tier === 'evidence_building' || status === 'partial') {
    return ({
      relationship: '关系词已经有入口，但还需要更多退休、朋友网络和社群陪伴问题。',
      career: '成长或事业词已有入口，但需要拆清价值感、投入和收益边界。',
      green: '绿色词还要落到家庭环境健康、净水、空气净化和清洁场景。',
      health: '健康词需要更多具体方案、产品组合和长期管理证据。',
      general: `${term}已有入口，但仍需补问题和证据。`,
    })[lane];
  }
  return ({
    relationship: '下一轮先补一条点名安利的关系题和一条不点名的陪伴场景题。',
    career: '下一轮先补一条事业机会边界题和一条退休后价值感场景题。',
    green: '下一轮先补一条家庭环境健康题和一条产品证据题。',
    health: '下一轮先补一条长期健康管理题和一条具体解决方案题。',
    general: '下一轮先补品牌锚定问题和可引用原文。',
  })[lane];
}

function strategyActionRecommendationText(
  rawAction: string,
  term: string,
  status: StrategyValidationRow['status'],
  nodes: OntologyAssociationCircleNode[],
  platformCount: number,
  backendRow?: OntologyAssociationCircleStrategyValidation,
): string | undefined {
  const raw = rawAction.trim();
  if (raw && !isTemplateStrategyAction(raw)) return raw;
  const stance = backendRow?.stance_summary || {};
  const supportive = Number(stance.supportive || 0);
  const skeptical = Number(stance.skeptical || 0);
  const riskLike = Number(stance.risk || 0) + Number(stance.competitive || 0);
  const answerMentions = Number(backendRow?.answer_mention_count || nodes.reduce((sum, node) => sum + nodeEvidenceCount(node), 0));
  const tier = backendRow?.decision_tier || '';
  const lane = strategyLane(term);
  if (tier === 'amplify' || (status === 'validated' && supportive >= 30)) {
    const focus = ({
      relationship: '沉淀 3 条社群陪伴案例，并单独写清社群支持和熟人销售压力的边界',
      career: '整理收入边界、合规说明和真实参与路径，避免平台把它写成收益承诺',
      green: '补齐家庭环境健康、净水净化和绿色生活的产品证据',
      health: '沉淀科学依据、产品组合和人群使用场景',
      general: '整理为可复用的品牌解释和原文证据包',
    })[lane];
    return `把${term}放入放大清单，优先${focus}；下轮看是否至少 ${Math.max(platformCount, 3)} 个平台继续自然提及。`;
  }
  if (tier === 'risk_first' || status === 'risk') {
    const focus = ({
      relationship: '补社群边界、陪伴机制和非强销售场景，降低熟人压力联想',
      career: '先写清收入预期、投入成本、合规边界和不承诺收益的表达',
      green: '把环保理念落到具体产品、检测依据和家庭场景',
      health: '补科学依据、适用边界和不可替代医疗建议的说明',
      general: '先补澄清证据、替代表达和可核验事实',
    })[lane];
    return `${term}先处理质疑语境：${focus}；下轮目标是相关质疑低于本轮 ${Math.max(skeptical + riskLike, 1)} 条。`;
  }
  if (tier === 'evidence_building' || status === 'partial') {
    const focus = ({
      relationship: '增加退休后陪伴、朋友网络和社群支持类问题',
      career: '增加第二曲线、长期参与、收入预期和合规收益边界类问题',
      green: '增加家庭清洁、净水、空气净化和绿色生活方式问题',
      health: '增加具体健康方案、长期管理和产品组合问题',
      general: '增加品牌锚定题和场景题',
    })[lane];
    return `围绕${term}${focus}，同时补 2 条可引用原文和 1 组品牌事实；下轮目标是证据超过 ${Math.max(answerMentions + 3, 6)} 条。`;
  }
  return `${term}当前证据不足，先${strategyMeaningFocus(term, lane, '', 'missing')}形成可展示节点后再进入战略验证。`;
}

function isTemplateStrategyAction(text: string): boolean {
  return /补\s*2\s*条品牌锚定题和\s*2\s*条场景题/.test(text)
    || /补产品证据、使用场景和可复述案例/.test(text)
    || /下轮目标是进入稳定资产/.test(text);
}

function ReportExecutiveDecisionPanel({
  centerTerm,
  prioritySummary,
  groups,
  platformComparison,
  sampleScope,
}: {
  centerTerm: string;
  prioritySummary?: OntologyAssociationCirclePrioritySummary | null;
  groups: AssociationMapGroup[];
  platformComparison: OntologyAssociationCirclePlatformComparison[];
  sampleScope: Record<string, unknown>;
}) {
  const assets = priorityItemsOrFallback(
    prioritySummary?.top_assets,
    groups.find((group) => group.key === 'strong')?.nodes || [],
    'asset',
  );
  const risks = priorityItemsOrFallback(
    prioritySummary?.top_risks,
    groups.find((group) => group.key === 'risk')?.nodes.filter((node) => node.business_tag !== '竞争关系') || [],
    'risk',
  );
  const competitors = priorityItemsOrFallback(
    prioritySummary?.top_competitors,
    groups.find((group) => group.key === 'risk')?.nodes.filter((node) => node.business_tag === '竞争关系') || [],
    'competitor',
  );
  const opportunities = priorityItemsOrFallback(
    prioritySummary?.top_opportunities,
    [
      ...(groups.find((group) => group.key === 'growth')?.nodes || []),
      ...(groups.find((group) => group.key === 'story')?.nodes || []),
    ],
    'opportunity',
  );
  const answerCount = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope);
  const strongestAsset = assets[0]?.term || topTermsForReport(groups, 'strong', 1)[0] || '稳定资产';
  const strongestRisk = risks[0]?.term || topTermsForReport(groups, 'risk', 1)[0] || '风险关系';
  const firstPlatform = platformComparison[0];
  return (
    <section className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-6 sm:p-7">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">一屏结论</div>
          <h3 className="mt-2 text-2xl font-semibold leading-tight" style={{ fontFamily: REPORT_SERIF_FONT }}>
            {centerTerm}这一轮先守住{strongestAsset}，先处理{strongestRisk}
          </h3>
          <p className="mt-4 text-[15px] leading-8 text-[var(--text-secondary)]" style={{ fontFamily: REPORT_SERIF_FONT }}>
            本轮读取 {answerCount || '-'} 条有效回答，覆盖 {platformCount || '-'} 个平台。读图时不需要处理全部节点，先看风险、竞品和机会的 Top 项，再回到原文判断它们是否真的影响品牌解释。
          </p>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <ExecutiveMetric title="优势" value={assets[0]?.term || '-'} text={priorityItemBrief(assets[0] || {})} />
            <ExecutiveMetric title="先处理" value={risks[0]?.term || '-'} text={priorityItemBrief(risks[0] || {})} tone="risk" />
            <ExecutiveMetric title="平台差异" value={firstPlatform ? platformLabel(firstPlatform.platform) : '-'} text={firstPlatform?.answer_preference || '平台偏好待观察'} />
          </div>
        </div>
        <div className="space-y-3">
          <ExecutivePriorityList title="风险 Top 3" items={risks} />
          <ExecutivePriorityList title="竞品替代 Top 3" items={competitors} />
          <ExecutivePriorityList title="机会 Top 3" items={opportunities} />
        </div>
      </div>
    </section>
  );
}

function buildPriorityReportSection({
  centerTerm,
  prioritySummary,
  groups,
  sampleScope,
}: {
  centerTerm: string;
  prioritySummary?: OntologyAssociationCirclePrioritySummary | null;
  groups: AssociationMapGroup[];
  sampleScope: Record<string, unknown>;
}): ReportNarrativeSection {
  const risks = priorityItemsOrFallback(
    prioritySummary?.top_risks,
    groups.find((group) => group.key === 'risk')?.nodes.filter((node) => node.business_tag !== '竞争关系') || [],
    'risk',
  );
  const competitors = priorityItemsOrFallback(
    prioritySummary?.top_competitors,
    groups.find((group) => group.key === 'risk')?.nodes.filter((node) => node.business_tag === '竞争关系') || [],
    'competitor',
  );
  const opportunities = priorityItemsOrFallback(
    prioritySummary?.top_opportunities,
    [
      ...(groups.find((group) => group.key === 'growth')?.nodes || []),
      ...(groups.find((group) => group.key === 'story')?.nodes || []),
    ],
    'opportunity',
  );
  const answerCount = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope);
  return {
    title: '一屏结论与优先级',
    readerQuestion: '品牌方这一轮先处理什么？',
    takeaway: `${centerTerm}本轮先看风险 Top 3、竞品替代 Top 3 和机会 Top 3。`,
    claims: [
      `样本：${answerCount || '-'} 条有效回答，覆盖 ${platformCount || '-'} 个平台。`,
      `风险 Top 3：${priorityTermLine(risks)}。`,
      `竞品替代 Top 3：${priorityTermLine(competitors)}。`,
      `机会 Top 3：${priorityTermLine(opportunities)}。`,
    ],
    text: [
      `本轮不要求品牌团队逐个处理全部节点。先处理证据量高、平台覆盖广、会影响品牌解释的 Top 项，再把其他节点作为复测背景。`,
      `风险优先级：${priorityDetailLine(risks)}`,
      `竞品替代：${priorityDetailLine(competitors)}`,
      `机会拉近：${priorityDetailLine(opportunities)}`,
    ].join('\n\n'),
    soWhat: '这部分可以直接变成下一周内容与复测任务清单。',
    supportingFacts: [
      prioritySummary?.reading || '优先级来自校准后的节点排序。',
    ],
    evidenceRefs: [
      ...risks.flatMap((item) => item.evidence_refs || []),
      ...competitors.flatMap((item) => item.evidence_refs || []),
      ...opportunities.flatMap((item) => item.evidence_refs || []),
    ].slice(0, 8),
    nextProbe: '下一轮优先复测 Top 风险是否下降、竞品替代是否减少、机会词是否向内圈移动。',
  };
}

function priorityTermLine(items: OntologyAssociationCirclePriorityItem[]): string {
  return items.length
    ? items.slice(0, 3).map((item) => item.term).filter(Boolean).join('、')
    : '暂未形成';
}

function priorityDetailLine(items: OntologyAssociationCirclePriorityItem[]): string {
  return items.length
    ? items.slice(0, 3).map((item) => `${item.term || '待命名节点'}（${priorityItemBrief(item)}）`).join('；')
    : '本轮暂未形成明确对象。';
}

function ExecutiveMetric({
  title,
  value,
  text,
  tone = 'default',
}: {
  title: string;
  value: string;
  text: string;
  tone?: 'default' | 'risk';
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3">
      <div className="text-xs text-[var(--text-tertiary)]">{title}</div>
      <div className={`mt-2 truncate text-lg font-semibold ${tone === 'risk' ? 'text-[var(--error)]' : 'text-[var(--text-primary)]'}`}>
        {value}
      </div>
      <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">{text}</p>
    </div>
  );
}

function ExecutivePriorityList({
  title,
  items,
}: {
  title: string;
  items: OntologyAssociationCirclePriorityItem[];
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3">
      <div className="text-xs font-medium text-[var(--text-tertiary)]">{title}</div>
      <div className="mt-2 space-y-2">
        {items.length ? items.slice(0, 3).map((item, index) => (
          <div key={`${title}-${item.node_id || item.term || index}`} className="grid grid-cols-[24px_minmax(0,1fr)] gap-2 text-sm">
            <span className="text-[var(--text-tertiary)]">{item.rank || index + 1}</span>
            <div className="min-w-0">
              <div className="truncate font-semibold">{item.term || '待命名节点'}</div>
              <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
                {priorityItemBrief(item)}
              </p>
            </div>
          </div>
        )) : (
          <p className="text-xs leading-5 text-[var(--text-tertiary)]">本轮暂未形成明确 Top 项。</p>
        )}
      </div>
    </div>
  );
}

function reportEvidenceLine(value: string) {
  const text = String(value || '').trim();
  return /^(AI 原文|平台原文|平台原文样本)/.test(text);
}

function parseReportEvidenceLine(value: string) {
  const text = String(value || '').trim();
  const cleaned = text
    .replace(/^平台原文样本：/, '')
    .replace(/^平台原文：/, '')
    .replace(/^AI 原文：/, '');
  const platformMatch = cleaned.match(/^([^｜；:：]+)[｜；:：]/);
  const platform = platformMatch?.[1]?.trim() || '平台';
  const body = platformMatch ? cleaned.slice(platformMatch[0].length).trim() : cleaned;
  return { platform, body };
}

function reportPlatformAccent(platform: string) {
  const value = platform.toLowerCase();
  if (value.includes('豆包')) return '#1f7a6b';
  if (value.includes('元宝')) return '#4f7f72';
  if (value.includes('kimi')) return '#b9822d';
  if (value.includes('deepseek')) return '#586f9a';
  return '#1f7a6b';
}

function escapeRegexValue(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function buildReportEntityTerms(
  groups: AssociationMapGroup[] | undefined,
  centerTerm?: string,
): string[] {
  const terms = new Set<string>();
  groups?.forEach((group) => {
    group.nodes.forEach((node) => {
      const term = String(node.term || '').trim();
      if (term.length >= 2) terms.add(term);
    });
  });
  ['豆包', '元宝', 'Kimi', 'DeepSeek', '安利', '安利中国', '纽崔莱'].forEach((term) => terms.add(term));
  if (centerTerm) {
    const trimmed = String(centerTerm).trim();
    if (trimmed.length >= 2) terms.add(trimmed);
  }
  return Array.from(terms).sort((a, b) => b.length - a.length);
}

function renderParagraphWithBoldEntities(text: string, entities: string[]) {
  // 先解析 **加粗** Markdown 语法，再对非加粗部分做实体词加粗
  const boldSplit = text.split(/\*\*(.+?)\*\*/g);
  return boldSplit.map((segment, segmentIndex) => {
    if (!segment) return null;
    if (segmentIndex % 2 === 1) {
      return (
        <strong key={`m-${segmentIndex}`} className="font-semibold text-[var(--text-primary)]">
          {segment}
        </strong>
      );
    }
    if (!entities.length) {
      return <span key={`t-${segmentIndex}`}>{segment}</span>;
    }
    const pattern = new RegExp(`(${entities.map(escapeRegexValue).join('|')})`, 'g');
    const subParts = segment.split(pattern);
    return subParts.map((sub, subIndex) => {
      if (!sub) return null;
      if (entities.includes(sub)) {
        return (
          <strong key={`e-${segmentIndex}-${subIndex}`} className="font-semibold text-[var(--text-primary)]">
            {sub}
          </strong>
        );
      }
      return <span key={`s-${segmentIndex}-${subIndex}`}>{sub}</span>;
    });
  });
}

function ReportSection({
  section,
  index,
  groups,
  platformComparison,
  sampleScope,
  centerTerm,
}: {
  section: ReportNarrativeSection;
  index: number;
  groups?: AssociationMapGroup[];
  platformComparison?: OntologyAssociationCirclePlatformComparison[];
  sampleScope?: Record<string, unknown>;
  centerTerm?: string;
}) {
  const paragraphs = section.text.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  const supportingFacts = section.supportingFacts || [];
  const quoteFacts = supportingFacts.filter(reportEvidenceLine);
  const dataFacts = supportingFacts.filter((fact) => !reportEvidenceLine(fact));
  const isVerdict = index === 0 || section.sectionId === 'core_verdict';
  const titleText = section.title || '';
  const isCoreVerdict = isVerdict || titleText === '核心判断';
  const isAiArchive = titleText.includes('AI 档案') || titleText.includes('档案里写了什么');
  const isFourPillars = titleText.includes('四个价值支柱') || titleText.includes('四有');
  const isPlatformDiff = titleText === '平台差异' || titleText.includes('平台差异');
  const isAction = titleText.includes('从数据到行动') || (titleText.includes('本周') && titleText.includes('件事'));
  const isBlindSpot = titleText.includes('盲区') || section.sectionId === 'ai_blind_spot';

  const coreMetrics = isCoreVerdict && sampleScope && groups?.length ? buildCoreVerdictMetrics(sampleScope, groups) : null;
  const barChartItems = isAiArchive && groups?.length ? buildNodeFrequencyBars(groups) : null;
  const platformRows = isPlatformDiff && platformComparison?.length ? platformComparison : null;
  const actionClaims = isAction && section.claims?.length ? section.claims : null;
  const entityTerms = buildReportEntityTerms(groups, centerTerm);

  return (
    <section className={isVerdict ? 'rounded-2xl border border-[var(--brand-border)] bg-[var(--brand-bg)] px-5 py-6 sm:px-7 sm:py-7' : 'border-t border-[var(--border-subtle)] pt-10 first:border-t-0 first:pt-0'}>
      <div className="flex items-start gap-3">
        {!isVerdict ? (
          <span className="mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--brand-bg)] text-sm font-semibold text-[var(--brand-primary)]">
            {index}
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <h3
            className={isVerdict ? 'text-[24px] font-semibold leading-snug text-[var(--brand-primary)] sm:text-[28px]' : 'text-[26px] font-semibold leading-snug text-[var(--text-primary)]'}
            style={{ fontFamily: REPORT_SERIF_FONT }}
          >
            {section.title}
          </h3>
        </div>
      </div>
      {section.readerQuestion ? (
        <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
          {section.readerQuestion}
        </p>
      ) : null}
      {section.takeaway ? (
        isVerdict ? (
          <div
            className="mt-5 rounded-r-lg border-l-4 bg-[rgba(31,122,107,0.18)] px-5 py-4 text-[17px] leading-8 text-[var(--brand-primary)]"
            style={{ fontFamily: REPORT_SERIF_FONT, borderLeftColor: 'var(--brand-primary)' }}
          >
            {renderParagraphWithBoldEntities(section.takeaway, entityTerms)}
          </div>
        ) : isBlindSpot ? (
          <div
            className="mt-5 rounded-r-lg border-l-4 bg-[rgba(239,91,107,0.10)] px-5 py-4 text-[17px] leading-8 text-[var(--error)]"
            style={{ fontFamily: REPORT_SERIF_FONT, borderLeftColor: 'var(--error)' }}
          >
            {renderParagraphWithBoldEntities(section.takeaway, entityTerms)}
          </div>
        ) : (
          <div
            className="mt-5 rounded-r-lg border-l-4 bg-[rgba(31,122,107,0.08)] px-5 py-4 text-[17px] leading-8 text-[var(--text-primary)]"
            style={{ fontFamily: REPORT_SERIF_FONT, borderLeftColor: 'var(--brand-primary)' }}
          >
            {renderParagraphWithBoldEntities(section.takeaway, entityTerms)}
          </div>
        )
      ) : null}
      {coreMetrics?.length ? <ReportMetricRow metrics={coreMetrics} /> : null}
      {isBlindSpot && section.claims?.length ? <ReportBlindSpotTable claims={section.claims} /> : null}
      {isFourPillars && section.claims?.length ? <ReportFourHaveMetricCards claims={section.claims} /> : null}
      {actionClaims?.length ? (
        <ReportActionCards claims={actionClaims} tone="problem" />
      ) : (isAiArchive || isPlatformDiff) && section.claims?.length ? (
        <ReportPersonaClaimCards claims={section.claims} />
      ) : section.claims?.length && !isFourPillars && !isBlindSpot ? (
        <ul className="mt-5 grid gap-2 text-sm leading-7 text-[var(--text-secondary)] sm:grid-cols-2">
          {section.claims.slice(0, 4).map((claim) => (
            <li key={claim} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3">
              {claim}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="mt-4 space-y-4">
        {paragraphs.map((paragraph) => (
          isAction ? (
            <div
              key={paragraph}
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3"
              style={{ borderLeft: '4px solid var(--brand-primary)' }}
            >
              <p className="text-[15px] leading-7 text-[var(--text-secondary)]" style={{ fontFamily: REPORT_SERIF_FONT }}>
                {renderParagraphWithBoldEntities(paragraph, entityTerms)}
              </p>
            </div>
          ) : (
            <p
              key={paragraph}
              className="text-[17px] leading-9 text-[var(--text-secondary)]"
              style={{ fontFamily: REPORT_SERIF_FONT }}
            >
              {renderParagraphWithBoldEntities(paragraph, entityTerms)}
            </p>
          )
        ))}
      </div>
      {barChartItems?.length ? <ReportBarChart items={barChartItems} /> : null}
      {isPlatformDiff && section.claims?.length ? <ReportPlatformEvaluationTable claims={section.claims} /> : null}
      {section.soWhat && !isVerdict ? (
        <p className="mt-6 rounded-xl bg-[var(--bg-secondary)] px-4 py-3 text-sm leading-7 text-[var(--text-primary)]">
          {section.soWhat}
        </p>
      ) : null}
      {section.evidenceRefs?.length && !isVerdict ? (
        <div className="mt-6 border-t border-[var(--border-subtle)] pt-5 text-sm leading-6 text-[var(--text-secondary)]">
          <p>已关联 {section.evidenceRefs.length} 条回答证据，问题、平台和摘录见下方证据链。</p>
        </div>
      ) : null}
    </section>
  );
}

function buildCoreVerdictMetrics(
  sampleScope: Record<string, unknown>,
  groups: AssociationMapGroup[],
): Array<{ label: string; value: string; sub?: string; tone?: 'default' | 'risk' | 'opportunity' }> {
  const answerCount = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope);
  const riskCount = groups.find((g) => g.key === 'risk')?.nodes.length || 0;
  const opportunityCount = (groups.find((g) => g.key === 'growth')?.nodes.length || 0)
    + (groups.find((g) => g.key === 'story')?.nodes.length || 0);
  return [
    { label: '有效回答', value: answerCount ? String(answerCount) : '-', sub: '本轮解析基线' },
    { label: '有效平台', value: platformCount ? String(platformCount) : '-', sub: '进入比较的平台数' },
    { label: '风险节点', value: String(riskCount), sub: '风险关系层节点数', tone: 'risk' },
    { label: '机会节点', value: String(opportunityCount), sub: '机会轨 + 观察轨', tone: 'opportunity' },
  ];
}

function buildNodeFrequencyBars(groups: AssociationMapGroup[]): Array<{ label: string; value: number; tone: 'strong' | 'growth' | 'story' | 'risk' }> {
  const items: Array<{ label: string; value: number; tone: 'strong' | 'growth' | 'story' | 'risk' }> = [];
  (['strong', 'growth', 'story', 'risk'] as const).forEach((key) => {
    const group = groups.find((g) => g.key === key);
    if (!group) return;
    group.nodes.slice(0, 4).forEach((node) => {
      const raw = node.answer_count || node.frequency_score || node.gravity_score || node.closeness_score || 0;
      items.push({ label: node.term, value: Number(raw) || 0, tone: key });
    });
  });
  items.sort((a, b) => b.value - a.value);
  return items.slice(0, 8);
}

function reportBarToneColor(tone: string) {
  switch (tone) {
    case 'strong': return 'var(--brand-primary)';
    case 'growth': return 'var(--success)';
    case 'story': return 'var(--text-tertiary)';
    case 'risk': return 'var(--error)';
    default: return 'var(--brand-primary)';
  }
}

function ReportMetricRow({ metrics }: { metrics: Array<{ label: string; value: string; sub?: string; tone?: 'default' | 'risk' | 'opportunity' }> }) {
  return (
    <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map((metric) => (
        <div key={metric.label} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3">
          <div className="text-xs text-[var(--text-tertiary)]">{metric.label}</div>
          <div className={`mt-1 text-2xl font-semibold tabular-nums ${metric.tone === 'risk' ? 'text-[var(--error)]' : metric.tone === 'opportunity' ? 'text-[var(--brand-primary)]' : 'text-[var(--text-primary)]'}`}>
            {metric.value}
          </div>
          {metric.sub ? <div className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">{metric.sub}</div> : null}
        </div>
      ))}
    </div>
  );
}

function ReportBarChart({ items }: { items: Array<{ label: string; value: number; tone: 'strong' | 'growth' | 'story' | 'risk' }> }) {
  if (!items.length) return null;
  const maxValue = Math.max(...items.map((item) => item.value), 1);
  return (
    <div className="mt-6 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-4">
      <div className="text-xs font-medium text-[var(--text-tertiary)]">节点频率（按回答带回次数）</div>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-3 text-sm">
            <span className="w-28 shrink-0 truncate text-right text-[var(--text-secondary)]" title={item.label}>{item.label}</span>
            <div className="h-5 flex-1 overflow-hidden rounded bg-[var(--bg-secondary)]">
              <div
                className="h-full rounded transition-all"
                style={{ width: `${Math.max(4, (item.value / maxValue) * 100)}%`, backgroundColor: reportBarToneColor(item.tone) }}
              />
            </div>
            <span className="w-10 shrink-0 text-right font-semibold tabular-nums text-[var(--text-primary)]">{item.value}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-[var(--text-tertiary)]">
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: reportBarToneColor('strong') }} />稳定轨</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: reportBarToneColor('growth') }} />机会轨</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: reportBarToneColor('story') }} />观察轨</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: reportBarToneColor('risk') }} />风险关系</span>
      </div>
    </div>
  );
}

function ReportGapBadges() {
  const badges: Array<{ label: string; gap: string; desc: string; tone: 'warning' | 'risk' | 'muted' }> = [
    { label: '有健康', gap: '叙事层级差距', desc: '停在产品层，未进方案层', tone: 'warning' },
    { label: '有陪伴', gap: '叙事被劫持', desc: '高可见低可信', tone: 'risk' },
    { label: '有保障', gap: '叙事被反转', desc: '被风险语境笼罩', tone: 'risk' },
    { label: '有价值', gap: '叙事缺位', desc: 'AI 几乎不主动提及', tone: 'muted' },
  ];
  const toneClass = (tone: string) => {
    switch (tone) {
      case 'warning': return 'border-l-4 border-[var(--status-warning)] bg-[var(--status-warning-bg)] text-[var(--status-warning)]';
      case 'risk': return 'border-l-4 border-[var(--error)] bg-[rgba(239,91,107,0.10)] text-[var(--error)]';
      case 'muted': return 'border-l-4 border-[var(--text-tertiary)] bg-[var(--bg-secondary)] text-[var(--text-tertiary)]';
      default: return 'border-l-4 border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
    }
  };
  return (
    <div className="mt-6 grid gap-2 sm:grid-cols-2">
      {badges.map((badge) => (
        <div key={badge.label} className={`rounded-r-lg px-4 py-3 ${toneClass(badge.tone)}`}>
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold">{badge.label}</span>
            <span className="text-xs font-medium opacity-90">差距类型：{badge.gap}</span>
          </div>
          <p className="mt-1 text-xs leading-5 opacity-80">{badge.desc}</p>
        </div>
      ))}
    </div>
  );
}

function ReportPlatformTable({ rows }: { rows: OntologyAssociationCirclePlatformComparison[] }) {
  return (
    <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border-subtle)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[var(--bg-secondary)] text-left text-xs text-[var(--text-tertiary)]">
            <th className="px-3 py-2 font-medium">平台</th>
            <th className="px-3 py-2 text-right font-medium">有效回答</th>
            <th className="px-3 py-2 font-medium">回答偏好</th>
            <th className="px-3 py-2 font-medium">代表节点</th>
            <th className="px-3 py-2 font-medium">竞品参照</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.platform} className={index > 0 ? 'border-t border-[var(--border-subtle)]' : ''}>
              <td className="px-3 py-2">
                <span
                  className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold text-white"
                  style={{ backgroundColor: reportPlatformAccent(row.platform) }}
                >
                  {platformLabel(row.platform)}
                </span>
              </td>
              <td className="px-3 py-2 text-right font-semibold tabular-nums text-[var(--text-primary)]">{row.valid_answer_count || 0}</td>
              <td className="px-3 py-2 text-[var(--text-secondary)]">{row.answer_preference || '偏好待观察'}</td>
              <td className="px-3 py-2 text-[var(--text-secondary)]">{(row.preferred_nodes || []).slice(0, 3).join('、') || '—'}</td>
              <td className="px-3 py-2 text-[var(--text-secondary)]">{(row.competition_nodes || []).slice(0, 3).join('、') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportActionCards({ claims, tone = 'action' }: { claims: string[]; tone?: 'problem' | 'action' }) {
  const borderColor = tone === 'problem' ? 'var(--error)' : 'var(--brand-primary)';
  return (
    <div className="mt-5 space-y-3">
      {claims.slice(0, 4).map((claim, index) => (
        <div
          key={claim}
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3"
          style={{ borderLeft: `4px solid ${borderColor}` }}
        >
          <div className="flex items-start gap-3">
            <span
              className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-[var(--brand-contrast)]"
              style={{ backgroundColor: borderColor }}
            >
              {index + 1}
            </span>
            <p className="min-w-0 flex-1 text-sm leading-7 text-[var(--text-secondary)]">{claim}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function ReportPersonaClaimCards({ claims }: { claims: string[] }) {
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {claims.slice(0, 4).map((claim) => {
        const match = claim.match(/^([^｜]+)｜(.+)$/);
        const platform = match?.[1]?.trim() || '';
        const rest = match?.[2] || claim;
        const accent = platform ? reportPlatformAccent(platform) : 'var(--brand-primary)';
        const parenIndex = rest.indexOf('（');
        const personaLine = parenIndex > 0 ? rest.slice(0, parenIndex).trim() : rest;
        const dataLine = parenIndex > 0 ? rest.slice(parenIndex) : '';
        return (
          <div
            key={claim}
            className="overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
            style={{ borderTop: `3px solid ${accent}` }}
          >
            <div className="px-4 pt-3 pb-3">
              <div className="text-base font-semibold" style={{ color: accent }}>{platform}</div>
              <p className="mt-1.5 text-sm leading-6 text-[var(--text-primary)]">{personaLine}</p>
              {dataLine ? (
                <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">{dataLine}</p>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ReportBlindSpotTable({ claims }: { claims: string[] }) {
  let brandNamed = 0;
  let openAnswers = 0;
  let openMentions = 0;
  let activeRate = '0';
  claims.forEach((c) => {
    const numMatch = c.match(/(\d+)\s*条/);
    const rateMatch = c.match(/([\d.]+)%/);
    if (c.includes('含品牌名') && numMatch) brandNamed = parseInt(numMatch[1], 10);
    if (c.includes('开放问题回答') && numMatch) openAnswers = parseInt(numMatch[1], 10);
    if (c.includes('开放问题主动提及') && numMatch) openMentions = parseInt(numMatch[1], 10);
    if (c.includes('主动提及率') && rateMatch) activeRate = rateMatch[1];
  });
  return (
    <div className="mt-6 rounded-xl border border-[var(--error)] bg-[rgba(239,91,107,0.06)] p-5">
      <div className="text-sm font-semibold text-[var(--error)]">最值得重视的一组数字</div>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-[var(--text-tertiary)]">
            <th className="py-2 font-medium">问题类型</th>
            <th className="py-2 text-right font-medium">回答总量</th>
            <th className="py-2 text-right font-medium">主动提到安利</th>
            <th className="py-2 text-right font-medium">比率</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="py-2">问题中包含"安利"</td>
            <td className="py-2 text-right tabular-nums">{brandNamed}</td>
            <td className="py-2 text-right tabular-nums text-[var(--brand-primary)]">{brandNamed}</td>
            <td className="py-2 text-right tabular-nums text-[var(--brand-primary)]">100%</td>
          </tr>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="py-2">问题中不含"安利"</td>
            <td className="py-2 text-right tabular-nums">{openAnswers}</td>
            <td className="py-2 text-right tabular-nums text-[var(--error)]">{openMentions}</td>
            <td className="py-2 text-right tabular-nums text-[var(--error)]">{activeRate}%</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function ReportFourHaveMetricCards({ claims }: { claims: string[] }) {
  const parseClaim = (claim: string) => {
    const labelMatch = claim.match(/^有(健康|陪伴|保障|价值)/);
    const label = labelMatch ? `有${labelMatch[1]}` : '';
    const gapMatch = claim.match(/差距类型为([^；；]+)/);
    const gap = gapMatch?.[1]?.trim() || '';
    const countMatch = claim.match(/(\d+)\s*条/);
    const count = countMatch?.[1] || '0';
    const pctMatch = claim.match(/占\s*([\d.]+)%/);
    const pct = pctMatch?.[1] || '';
    const nodeMatch = claim.match(/代表节点为([^。]+)|风险入口为([^。]+)|线索为([^。]+)/);
    const nodes = nodeMatch?.[1] || nodeMatch?.[2] || nodeMatch?.[3] || '';
    return { label, gap, count, pct, nodes };
  };
  const items = claims.map(parseClaim).filter((item) => item.label);
  const toneColor = (gap: string) => {
    if (gap.includes('缺位')) return 'var(--text-tertiary)';
    if (gap.includes('反转') || gap.includes('劫持')) return 'var(--error)';
    if (gap.includes('层级')) return 'var(--status-warning)';
    return 'var(--brand-primary)';
  };
  return (
    <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3"
          style={{ borderTop: `3px solid ${toneColor(item.gap)}` }}
        >
          <div className="text-sm font-semibold text-[var(--text-primary)]">{item.label}</div>
          <div className="mt-1 text-xs text-[var(--text-tertiary)]">{item.gap}</div>
          <div className="mt-2 text-2xl font-semibold tabular-nums" style={{ color: toneColor(item.gap) }}>
            {item.pct ? `${item.pct}%` : item.count}
          </div>
          <div className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
            {item.count} 条{item.pct ? ` · 占 ${item.pct}%` : ''}
          </div>
          {item.nodes ? (
            <div className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{item.nodes}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function ReportPlatformEvaluationTable({ claims }: { claims: string[] }) {
  const platforms = claims.map((claim) => {
    const match = claim.match(/^([^｜]+)｜(.+)$/);
    const platform = match?.[1]?.trim() || '';
    const rest = match?.[2] || claim;
    const parenIndex = rest.indexOf('（');
    const dataLine = parenIndex > 0 ? rest.slice(parenIndex) : '';
    const answerMatch = dataLine.match(/回答\s*(\d+)\s*条/);
    const riskMatch = dataLine.match(/风险语境\s*(\d+)\s*条/);
    const transMatch = dataLine.match(/转型叙事\s*(\d+)\s*条/);
    const activeMatch = dataLine.match(/主动带出品牌\s*(\d+)\s*条/);
    const answers = answerMatch ? parseInt(answerMatch[1], 10) : 0;
    const risks = riskMatch ? parseInt(riskMatch[1], 10) : 0;
    const trans = transMatch ? parseInt(transMatch[1], 10) : 0;
    const active = activeMatch ? parseInt(activeMatch[1], 10) : 0;
    const riskRate = answers ? risks / answers : 0;
    const transRate = answers ? trans / answers : 0;
    return {
      platform,
      answers,
      riskDensity: riskRate >= 0.45 ? '高' : riskRate >= 0.3 ? '中' : '低',
      transitionNarrative: transRate >= 0.6 ? '高' : transRate >= 0.3 ? '中' : '低',
      activeRecommend: active >= 1 ? '有' : '无',
    };
  }).filter((p) => p.platform);
  if (!platforms.length) return null;
  const riskColor = (val: string) => {
    if (val === '高') return 'text-[var(--error)]';
    if (val === '低') return 'text-[var(--brand-primary)]';
    return 'text-[var(--status-warning)]';
  };
  const goodColor = (val: string) => {
    if (val === '高' || val === '有') return 'text-[var(--brand-primary)]';
    if (val === '低' || val === '无') return 'text-[var(--error)]';
    return 'text-[var(--status-warning)]';
  };
  return (
    <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border-subtle)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[var(--bg-secondary)] text-left text-xs text-[var(--text-tertiary)]">
            <th className="px-3 py-2 font-medium">维度</th>
            {platforms.map((p) => (
              <th key={p.platform} className="px-3 py-2 font-medium">{p.platform}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="px-3 py-2 text-[var(--text-secondary)]">安利回答量</td>
            {platforms.map((p) => (
              <td key={p.platform} className="px-3 py-2 font-semibold tabular-nums text-[var(--text-primary)]">{p.answers}</td>
            ))}
          </tr>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="px-3 py-2 text-[var(--text-secondary)]">风险语境密度</td>
            {platforms.map((p) => (
              <td key={p.platform} className={`px-3 py-2 font-semibold ${riskColor(p.riskDensity)}`}>{p.riskDensity}</td>
            ))}
          </tr>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="px-3 py-2 text-[var(--text-secondary)]">转型叙事认可度</td>
            {platforms.map((p) => (
              <td key={p.platform} className={`px-3 py-2 font-semibold ${goodColor(p.transitionNarrative)}`}>{p.transitionNarrative}</td>
            ))}
          </tr>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="px-3 py-2 text-[var(--text-secondary)]">主动推荐安利</td>
            {platforms.map((p) => (
              <td key={p.platform} className={`px-3 py-2 font-semibold ${goodColor(p.activeRecommend === '有' ? '高' : '低')}`}>{p.activeRecommend}</td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function renderAnswerMarkdown(text: string) {
  const normalized = text
    .replace(/([^\n])\s*(#{1,6}\s)/g, '$1\n$2')
    .replace(/([^\n])\s+([-*]\s)/g, '$1\n$2');
  const lines = normalized.split('\n');
  return lines.map((line, i) => {
    const trimmed = line.trim();
    const hMatch = trimmed.match(/^#{1,6}\s+(.+)$/);
    if (hMatch) {
      return (
        <div key={i} className="mt-3 mb-1 font-semibold text-[var(--text-primary)]" style={{ fontFamily: REPORT_SERIF_FONT }}>
          {renderParagraphWithBoldEntities(hMatch[1], [])}
        </div>
      );
    }
    const liMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (liMatch) {
      return (
        <div key={i} className="pl-3 leading-7" style={{ fontFamily: REPORT_SERIF_FONT }}>
          <span className="text-[var(--text-tertiary)]">· </span>
          {renderParagraphWithBoldEntities(liMatch[1], [])}
        </div>
      );
    }
    if (!trimmed) {
      return <div key={i} className="h-2" />;
    }
    return (
      <div key={i} className="leading-7" style={{ fontFamily: REPORT_SERIF_FONT }}>
        {renderParagraphWithBoldEntities(line, [])}
      </div>
    );
  });
}

function ReportEvidenceSamples({ quotes }: { quotes: string[] }) {
  const uniqueQuotes = Array.from(new Set(quotes));
  if (!uniqueQuotes.length) return null;
  return (
    <section className="border-t border-[var(--border-subtle)] pt-10">
      <h3 className="text-[26px] font-semibold leading-snug text-[var(--text-primary)]" style={{ fontFamily: REPORT_SERIF_FONT }}>
        事实举例
      </h3>
      <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
        以下是平台回答安利相关问题的原文摘录，按平台色区分。点击展开可查看完整原文。
      </p>
      <div className="mt-6 space-y-3">
        {uniqueQuotes.map((fact, index) => {
          const parsed = parseReportEvidenceLine(fact);
          const accent = reportPlatformAccent(parsed.platform);
          const body = parsed.body;
          const isPlatformQuote = fact.startsWith('平台原文');
          const label = isPlatformQuote ? '平台原文' : 'AI 摘录';
          const isComplete = body.length > 500 || /[。？！…」"']$/.test(body.trim());
          const isLong = body.length > 120;
          const preview = isLong ? `${body.slice(0, 120)}...` : body;
          return (
            <blockquote
              key={`${index}-${parsed.platform}`}
              className="overflow-hidden rounded-r-xl rounded-l-sm border-l-4 bg-[var(--bg-secondary)] pr-4 text-sm leading-7 text-[var(--text-secondary)]"
              style={{ borderLeftColor: accent }}
            >
              <div className="flex items-center gap-2 px-4 pt-3">
                <span
                  className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold text-white"
                  style={{ backgroundColor: accent }}
                >
                  {parsed.platform}
                </span>
                <span className="text-[11px] font-medium text-[var(--text-tertiary)]">{label}</span>
                {!isComplete ? (
                  <span className="text-[11px] font-medium text-[var(--status-warning)]">· 摘录可能不完整</span>
                ) : null}
              </div>
              {isLong ? (
                <details className="px-4 pb-3 pt-2">
                  <summary className="cursor-pointer leading-7" style={{ fontFamily: REPORT_SERIF_FONT }}>
                    {preview}
                  </summary>
                  <div className="mt-3">{renderAnswerMarkdown(body)}</div>
                </details>
              ) : (
                <div className="px-4 pb-3 pt-2">{renderAnswerMarkdown(body)}</div>
              )}
            </blockquote>
          );
        })}
      </div>
    </section>
  );
}

function ReportEvidenceBrief({
  questionDefinition,
  platformSourceSummary,
  evidenceFindings,
  sourceAppendix,
}: {
  questionDefinition?: OntologyAssociationCircleQuestionDefinition;
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
}) {
  if (!questionDefinition && !platformSourceSummary && !evidenceFindings.length) return null;
  const audienceText = (questionDefinition?.audience_segments || []).join('、') || '题库未携带人群标签';
  const probeText = (questionDefinition?.probe_types || []).join('、') || '题库未携带探针标签';
  const opportunityText = (questionDefinition?.opportunity_points || []).join('、') || '题库未携带机会点标签';
  return (
    <section className="border-t border-[var(--border-subtle)] pt-10">
      <div className="text-xs font-medium text-[var(--text-tertiary)]">附录</div>
      <h3 className="mt-2 text-[26px] font-semibold leading-snug" style={{ fontFamily: REPORT_SERIF_FONT }}>
        样本、平台与原文证据
      </h3>
      {questionDefinition?.definition_sentence ? (
        <p className="mt-4 text-[16px] leading-8 text-[var(--text-secondary)]" style={{ fontFamily: REPORT_SERIF_FONT }}>
          {questionDefinition.definition_sentence}
        </p>
      ) : null}

      <div className="mt-6 space-y-7">
        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">问题定义</h4>
          <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
            人群：{audienceText}；探针：{probeText}；机会点：{opportunityText}。
          </p>
          {(questionDefinition?.sample_questions || []).length ? (
            <ul className="mt-3 space-y-2 pl-5 text-sm leading-7 text-[var(--text-secondary)]">
              {(questionDefinition?.sample_questions || []).slice(0, 5).map((question) => (
                <li key={question.id || question.text} className="list-disc">
                  {question.text}
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">平台来源</h4>
          <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
            本轮记录有效回答 {platformSourceSummary?.valid_answer_count ?? 0} 条，有效平台 {platformSourceSummary?.platform_count ?? 0} 个；失败 {platformSourceSummary?.failed_answer_count ?? 0} 条，空回答 {platformSourceSummary?.empty_answer_count ?? 0} 条。
          </p>
          <ul className="mt-3 space-y-2 pl-5 text-sm leading-7 text-[var(--text-secondary)]">
            {(platformSourceSummary?.platforms || []).slice(0, 5).map((row) => (
              <li key={row.platform} className="list-disc">
                {row.platform}：{row.valid_answer_count || 0} 条有效；{row.answer_preference || '偏好待观察'}；代表节点：{(row.preferred_nodes || []).join('、') || '暂无'}{(row.competition_nodes || []).length ? `；竞品参照：${(row.competition_nodes || []).join('、')}` : ''}。
              </li>
            ))}
          </ul>
        </section>

        {evidenceFindings.length ? (
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">证据样本</h4>
            <ul className="mt-3 space-y-3 pl-5 text-sm leading-7 text-[var(--text-secondary)]">
              {evidenceFindings.slice(0, 8).map((finding) => (
                <li key={finding.node_id || finding.node_term} className="list-disc">
                  <span className="font-semibold text-[var(--text-primary)]">{finding.node_term}：</span>
                  {commercialReportCopy(finding.claim)}
                  {(() => {
                    const facts = finding.supporting_facts || [];
                    return facts.length ? ` ${facts.slice(0, 2).map(commercialReportCopy).join('；')}` : '';
                  })()}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {sourceAppendix.length ? (
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">原文摘录</h4>
            <div className="mt-3 space-y-4 text-sm leading-7 text-[var(--text-secondary)]">
              {sourceAppendix.slice(0, 8).map((item, index) => (
                <div key={`${item.evidence_id || index}`} className="border-t border-[var(--border-subtle)] pt-4 first:border-t-0 first:pt-0">
                  <p className="font-semibold text-[var(--text-primary)]">
                    {item.node_term || '节点'} / {item.platform || '平台'}
                  </p>
                  <p className="mt-1">{cleanEvidenceExcerpt(item.question, 120)}</p>
                  <p className="mt-1 text-[var(--text-tertiary)]">{cleanEvidenceExcerpt(item.answer_excerpt, 180)}</p>
                </div>
              ))}
            </div>
          </section>
        ) : null}

      </div>
    </section>
  );
}

function EvidenceScopeCard({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
      <div className="text-xs text-[var(--text-tertiary)]">{title}</div>
      <div className="mt-2 text-sm leading-6 text-[var(--text-primary)]">
        {items.length ? items.join('、') : '待补充'}
      </div>
    </div>
  );
}

function downloadAssociationReportHtml(
  centerTerm: string,
  sections: ReportNarrativeSection[],
  evidence?: {
    questionDefinition?: OntologyAssociationCircleQuestionDefinition;
    platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
    evidenceFindings?: OntologyAssociationCircleEvidenceFinding[];
    analysisTrace?: OntologyAssociationCircleAnalysisTraceItem[];
    sourceAppendix?: OntologyAssociationCircleSourceAppendixItem[];
    actions?: OntologyAssociationCircleProjection['association_actions'];
    reportQualityChecks?: Record<string, unknown>;
    groups?: AssociationMapGroup[];
    platformComparison?: OntologyAssociationCirclePlatformComparison[];
    sampleScope?: Record<string, unknown>;
  },
) {
  if (typeof window === 'undefined') return;
  const groups = evidence?.groups;
  const platformComparison = evidence?.platformComparison || [];
  const sampleScope = evidence?.sampleScope || {};
  const entityTerms = buildReportEntityTerms(groups, centerTerm);

  const sectionHtml = sections.map((section, index) => {
    const titleText = section.title || '';
    const isVerdict = index === 0 || section.sectionId === 'core_verdict';
    const isAiArchive = titleText.includes('AI 档案') || titleText.includes('档案里写了什么');
    const isAction = titleText.includes('从数据到行动') || (titleText.includes('本周') && titleText.includes('件事'));
    const isBlindSpot = titleText.includes('盲区') || section.sectionId === 'ai_blind_spot';
    const isPlatformDiff = titleText === '平台差异' || titleText.includes('平台差异');

    const takeawayClass = isBlindSpot ? 'takeaway-box-red' : isVerdict ? 'takeaway-box-green-strong' : 'takeaway-box-green';
    const takeawayHtml = section.takeaway ? `<div class="${takeawayClass}">${renderExportParagraphHtml(section.takeaway, entityTerms)}</div>` : '';

    let claimsHtml = '';
    if (isAiArchive && section.claims?.length) {
      claimsHtml = `<div class="persona-grid">${section.claims.slice(0, 4).map((claim) => {
        const match = claim.match(/^([^｜]+)｜(.+)$/);
        const platform = match?.[1]?.trim() || '';
        const rest = match?.[2] || claim;
        const accent = platform ? reportPlatformAccent(platform) : '#1f7a6b';
        const parenIndex = rest.indexOf('（');
        const personaLine = parenIndex > 0 ? rest.slice(0, parenIndex).trim() : rest;
        const dataLine = parenIndex > 0 ? rest.slice(parenIndex) : '';
        return `<div class="persona-card" style="border-top:3px solid ${accent}"><div class="persona-name" style="color:${accent}">${escapeHtml(platform)}</div><div class="persona-desc">${escapeHtml(personaLine)}</div>${dataLine ? `<div class="persona-data">${escapeHtml(dataLine)}</div>` : ''}</div>`;
      }).join('')}</div>`;
    } else if (isAction && section.claims?.length) {
      claimsHtml = `<div class="action-list">${section.claims.slice(0, 4).map((claim, i) => `<div class="problem-card"><span class="action-num" style="background:#ef5b6b">${i + 1}</span><span class="action-text">${escapeHtml(claim)}</span></div>`).join('')}</div>`;
    } else if (section.claims?.length) {
      claimsHtml = `<ul class="claims">${section.claims.slice(0, 4).map((claim) => `<li>${escapeHtml(claim)}</li>`).join('')}</ul>`;
    }

    const paragraphs = section.text.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
    const paragraphsHtml = paragraphs.map((p) => {
      const inner = renderExportParagraphHtml(p, entityTerms);
      return isAction
        ? `<div class="action-paragraph">${inner}</div>`
        : `<p>${inner}</p>`;
    }).join('');

    let metricsHtml = '';
    if (isVerdict && groups?.length) {
      const metrics = buildCoreVerdictMetrics(sampleScope, groups);
      metricsHtml = `<div class="metric-row">${metrics.map((m) => `<div class="metric-card"><div class="metric-label">${escapeHtml(m.label)}</div><div class="metric-value ${m.tone === 'risk' ? 'val-red' : m.tone === 'opportunity' ? 'val-green' : ''}">${escapeHtml(m.value)}</div>${m.sub ? `<div class="metric-sub">${escapeHtml(m.sub)}</div>` : ''}</div>`).join('')}</div>`;
    }

    let barChartHtml = '';
    if (isAiArchive && groups?.length) {
      const items = buildNodeFrequencyBars(groups);
      if (items.length) {
        const maxValue = Math.max(...items.map((item) => item.value), 1);
        barChartHtml = `<div class="bar-chart"><div class="bar-chart-title">节点频率（按回答带回次数）</div><div class="bar-chart-body">${items.map((item) => `<div class="bar-row"><span class="bar-label">${escapeHtml(item.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, (item.value / maxValue) * 100)}%;background:${reportBarToneColor(item.tone)}"></div></div><span class="bar-value">${item.value}</span></div>`).join('')}</div></div>`;
      }
    }

    let platformTableHtml = '';
    if (isPlatformDiff && platformComparison.length) {
      platformTableHtml = `<table class="platform-table"><thead><tr><th>平台</th><th>有效回答</th><th>回答偏好</th><th>代表节点</th><th>竞品参照</th></tr></thead><tbody>${platformComparison.map((row) => `<tr><td><span class="platform-tag" style="background:${reportPlatformAccent(row.platform)}">${escapeHtml(platformLabel(row.platform))}</span></td><td class="num">${row.valid_answer_count || 0}</td><td>${escapeHtml(row.answer_preference || '偏好待观察')}</td><td>${escapeHtml((row.preferred_nodes || []).slice(0, 3).join('、') || '—')}</td><td>${escapeHtml((row.competition_nodes || []).slice(0, 3).join('、') || '—')}</td></tr>`).join('')}</tbody></table>`;
    }

    const supportingFacts = section.supportingFacts || [];
    const quoteFacts = supportingFacts.filter(reportEvidenceLine);
    const quoteHtml = quoteFacts.length && !isVerdict ? quoteFacts.slice(0, 4).map((fact) => {
      const parsed = parseReportEvidenceLine(fact);
      const accent = reportPlatformAccent(parsed.platform);
      return `<blockquote style="border-left-color:${accent}"><span class="quote-tag" style="background:${accent}">${escapeHtml(parsed.platform)}</span> <span class="quote-label">平台原文</span><br />${escapeHtml(parsed.body)}</blockquote>`;
    }).join('') : '';

    return `
    <section>
      <h2>${index === 0 ? '' : `<span class="section-num">${index}</span>`}${escapeHtml(section.title)}</h2>
      ${section.readerQuestion ? `<p class="chapter-question">${escapeHtml(section.readerQuestion)}</p>` : ''}
      ${takeawayHtml}
      ${metricsHtml}
      ${claimsHtml}
      ${paragraphsHtml}
      ${barChartHtml}
      ${platformTableHtml}
      ${quoteHtml}
      ${section.soWhat && !isVerdict ? `<p class="source-line">${escapeHtml(section.soWhat)}</p>` : ''}
    </section>
  `;
  }).join('\n');
  const questionDefinition = evidence?.questionDefinition;
  const platformSourceSummary = evidence?.platformSourceSummary;
  const evidenceFindings = evidence?.evidenceFindings || [];
  const analysisTrace = evidence?.analysisTrace || [];
  const sourceAppendix = evidence?.sourceAppendix || [];
  const actions = evidence?.actions || [];
  const reportQualityChecks = evidence?.reportQualityChecks || {};
  const requiredChecks = Array.isArray(reportQualityChecks.required_checks)
    ? reportQualityChecks.required_checks.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    : [];
  const questionHtml = questionDefinition ? `
    <section>
      <h2>这轮问题在问什么</h2>
      <p>${escapeHtml(questionDefinition.definition_sentence || '')}</p>
      <div class="scope-grid">
        <div><b>人群</b><span>${escapeHtml((questionDefinition.audience_segments || []).join('、') || '题库未携带人群标签')}</span></div>
        <div><b>探针</b><span>${escapeHtml((questionDefinition.probe_types || []).join('、') || '题库未携带探针标签')}</span></div>
        <div><b>机会点</b><span>${escapeHtml((questionDefinition.opportunity_points || []).join('、') || '题库未携带机会点标签')}</span></div>
        <div><b>生活场景</b><span>${escapeHtml((questionDefinition.life_scenes || []).join('、') || '题库未携带生活场景标签')}</span></div>
      </div>
      ${(questionDefinition.sample_questions || []).slice(0, 6).map((question) => `
        <p class="source-line">${escapeHtml(question.text || '')}</p>
      `).join('')}
    </section>
  ` : '';
  const platformHtml = platformSourceSummary ? `
    <section>
      <h2>答案来源与平台样本</h2>
      <p>有效回答 ${platformSourceSummary.valid_answer_count || 0} 条，失败 ${platformSourceSummary.failed_answer_count || 0} 条，空回答 ${platformSourceSummary.empty_answer_count || 0} 条。</p>
      <table>
        <thead><tr><th>平台</th><th>有效回答</th><th>偏好</th><th>代表节点</th><th>竞品参照</th></tr></thead>
        <tbody>
          ${(platformSourceSummary.platforms || []).map((row) => `
            <tr>
              <td>${escapeHtml(row.platform || '')}</td>
              <td>${row.valid_answer_count || 0}</td>
              <td>${escapeHtml(row.answer_preference || '待观察')}</td>
              <td>${escapeHtml((row.preferred_nodes || []).join('、') || '暂无')}</td>
              <td>${escapeHtml((row.competition_nodes || []).join('、') || '暂无')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </section>
  ` : '';
  const evidenceHtml = evidenceFindings.length ? `
    <section>
      <h2>关键证据链</h2>
      ${evidenceFindings.slice(0, 8).map((finding) => `
        <article class="evidence-card">
          <h3>${escapeHtml(finding.node_term || '')}</h3>
          <p>${escapeHtml(commercialReportCopy(finding.claim))}</p>
          <ul>
            ${(finding.supporting_facts || []).slice(0, 4).map((fact) => `<li>${escapeHtml(commercialReportCopy(fact))}</li>`).join('')}
          </ul>
          ${finding.sample_excerpt ? `<blockquote>${escapeHtml(finding.sample_platform || '')} / ${escapeHtml(finding.sample_question || '')}: ${escapeHtml(finding.sample_excerpt || '')}</blockquote>` : ''}
        </article>
      `).join('')}
    </section>
  ` : '';
  const traceHtml = analysisTrace.length ? `
    <section>
      <h2>分析依据轨迹</h2>
      ${analysisTrace.slice(0, 6).map((trace, index) => `
        <p class="source-line"><b>${index + 1}. ${escapeHtml(trace.title || '')}</b><br />${escapeHtml(trace.summary || '')}</p>
      `).join('')}
    </section>
  ` : '';
  const actionHtml = actions.length ? `
    <section>
      <h2>下一轮行动</h2>
      ${actions.slice(0, 8).map((action) => `
        <article class="evidence-card">
          <h3>${escapeHtml(action.title || action.action_label || action.node_term || '圈层行动')}</h3>
          <p>${escapeHtml(commercialReportCopy(action.expected_impact || action.reason))}</p>
          ${action.review_criteria ? `<p class="source-line"><b>复测标准</b><br />${escapeHtml(commercialReportCopy(action.review_criteria))}</p>` : ''}
          ${(action.evidence_refs || []).length ? `<p class="source-line">已关联 ${(action.evidence_refs || []).length} 条回答证据，复测时回看对应节点和平台摘录。</p>` : ''}
        </article>
      `).join('')}
    </section>
  ` : '';
  const appendixHtml = sourceAppendix.length ? `
    <section>
      <h2>来源附录</h2>
      ${sourceAppendix.slice(0, 16).map((item) => `
        <p class="source-line"><b>${escapeHtml(item.node_term || '联想节点')} / ${escapeHtml(item.platform || '平台')} / ${escapeHtml(item.question_id ? `Q${item.question_id}` : '问题样本')}</b><br />${escapeHtml(cleanEvidenceExcerpt(item.question, 160))}<br />${escapeHtml(cleanEvidenceExcerpt(item.answer_excerpt, 220))}</p>
      `).join('')}
    </section>
  ` : '';
  const qualityHtml = requiredChecks.length ? `
    <section>
      <h2>报告完整性</h2>
      <div class="scope-grid">
        ${requiredChecks.map((check) => `
          <div><b>${escapeHtml(String(check.label || check.key || '检查项'))}</b><span>${check.passed ? '已满足' : '待补齐'}</span></div>
        `).join('')}
      </div>
    </section>
  ` : '';
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(centerTerm)}品牌圈层解读报告</title>
  <style>
    :root {
      color: #1f2933;
      background: #f7f4ed;
      font-family: ui-serif, "Noto Serif SC", "Source Han Serif SC", "Songti SC", Georgia, serif;
    }
    body { margin: 0; background: #f7f4ed; }
    main {
      width: min(920px, calc(100vw - 48px));
      margin: 56px auto;
      border: 1px solid #ded8cc;
      background: #fffdf8;
      padding: 56px;
      box-shadow: 0 18px 50px rgba(31, 41, 51, 0.08);
    }
    .eyebrow {
      color: #657184;
      font: 600 12px/1.4 ui-sans-serif, system-ui, sans-serif;
      letter-spacing: .16em;
    }
    h1 {
      margin: 14px 0 8px;
      font-size: 40px;
      line-height: 1.18;
      font-weight: 700;
      letter-spacing: 0;
    }
    .meta {
      color: #657184;
      font: 14px/1.8 ui-sans-serif, system-ui, sans-serif;
    }
    section {
      margin-top: 34px;
      padding-top: 26px;
      border-top: 1px solid #ebe5da;
    }
    h2 { margin: 0; font-size: 22px; line-height: 1.35; }
    h3 { margin: 0; font-size: 18px; line-height: 1.5; }
    p {
      margin: 14px 0 0;
      color: #384556;
      font-size: 16px;
      line-height: 2;
      white-space: normal;
    }
    table { width: 100%; margin-top: 16px; border-collapse: collapse; font: 14px/1.7 ui-sans-serif, system-ui, sans-serif; }
    th, td { border-top: 1px solid #ebe5da; padding: 10px 8px; text-align: left; vertical-align: top; }
    th { color: #657184; font-weight: 600; }
    .scope-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 24px; margin-top: 18px; }
    .source-line { padding-left: 14px; border-left: 3px solid #ded8cc; }
    .chapter-question { color: #657184; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; }
    .takeaway { color: #1f2933; font-weight: 600; }
    .claims { margin: 16px 0 0; padding-left: 22px; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    .claims li { margin-top: 6px; }
    .evidence-strip { margin-top: 18px; color: #384556; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; }
    .evidence-strip ul { margin: 8px 0 0; padding-left: 22px; }
    .scope-grid b, .scope-grid span { display: block; }
    .scope-grid b { color: #657184; font: 600 12px/1.4 ui-sans-serif, system-ui, sans-serif; }
    .scope-grid span { margin-top: 6px; font: 14px/1.7 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    .evidence-card { margin-top: 18px; padding-left: 14px; border-left: 3px solid #ded8cc; }
    .evidence-card ul { margin: 12px 0 0; padding-left: 20px; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    blockquote { margin: 14px 0 0; padding-left: 14px; border-left: 3px solid #1f7a6b; color: #4b5565; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; }
    p strong, .action-paragraph strong { font-weight: 700; color: #1f2933; }

    /* takeaway 高亮框 */
    .takeaway-box-green, .takeaway-box-green-strong, .takeaway-box-red {
      margin: 16px 0 0; padding: 14px 18px; border-left: 4px solid #1f7a6b;
      border-radius: 0 8px 8px 0; font: 600 17px/1.8 ui-serif, "Noto Serif SC", Georgia, serif;
    }
    .takeaway-box-green { background: rgba(31,122,107,0.08); color: #1f2933; }
    .takeaway-box-green-strong { background: rgba(31,122,107,0.18); color: #1f7a6b; }
    .takeaway-box-red { background: rgba(239,91,107,0.10); color: #ef5b6b; border-left-color: #ef5b6b; }

    /* persona card */
    .persona-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 16px 0 0; }
    .persona-card { background: #fffdf8; border: 1px solid #ebe5da; border-radius: 10px; padding: 12px 14px; }
    .persona-name { font: 700 16px/1.4 ui-sans-serif, system-ui, sans-serif; margin-bottom: 6px; }
    .persona-desc { font: 14px/1.7 ui-sans-serif, system-ui, sans-serif; color: #1f2933; }
    .persona-data { margin-top: 8px; font: 12px/1.6 ui-sans-serif, system-ui, sans-serif; color: #657184; }

    /* action / problem card */
    .action-list { margin: 16px 0 0; display: flex; flex-direction: column; gap: 10px; }
    .problem-card { background: #fffdf8; border: 1px solid #ebe5da; border-left: 4px solid #ef5b6b; border-radius: 8px; padding: 12px 14px; display: flex; align-items: flex-start; gap: 10px; }
    .action-num { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; color: #fff; font: 700 12px/1 ui-sans-serif, system-ui, sans-serif; flex-shrink: 0; }
    .action-text { font: 14px/1.7 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    .action-paragraph { margin: 12px 0 0; background: #fffdf8; border: 1px solid #ebe5da; border-left: 4px solid #1f7a6b; border-radius: 8px; padding: 12px 14px; font: 15px/1.8 ui-serif, "Noto Serif SC", Georgia, serif; color: #384556; }

    /* metric card */
    .metric-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0 0; }
    .metric-card { background: #fffdf8; border: 1px solid #ebe5da; border-radius: 10px; padding: 12px 14px; }
    .metric-label { font: 12px/1.4 ui-sans-serif, system-ui, sans-serif; color: #657184; }
    .metric-value { font: 700 26px/1.2 ui-sans-serif, system-ui, sans-serif; color: #1f2933; margin-top: 4px; }
    .metric-value.val-red { color: #ef5b6b; }
    .metric-value.val-green { color: #1f7a6b; }
    .metric-sub { margin-top: 4px; font: 12px/1.5 ui-sans-serif, system-ui, sans-serif; color: #657184; }

    /* bar chart */
    .bar-chart { margin: 16px 0 0; background: #fffdf8; border: 1px solid #ebe5da; border-radius: 10px; padding: 14px; }
    .bar-chart-title { font: 600 12px/1.4 ui-sans-serif, system-ui, sans-serif; color: #657184; }
    .bar-chart-body { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
    .bar-row { display: flex; align-items: center; gap: 10px; font: 13px/1.4 ui-sans-serif, system-ui, sans-serif; }
    .bar-label { width: 100px; flex-shrink: 0; text-align: right; color: #384556; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar-track { flex: 1; height: 20px; background: #f4eee2; border-radius: 4px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 4px; }
    .bar-value { width: 36px; flex-shrink: 0; text-align: right; font-weight: 700; color: #1f2933; }

    /* platform table */
    .platform-table { width: 100%; margin: 16px 0 0; border-collapse: collapse; font: 13px/1.6 ui-sans-serif, system-ui, sans-serif; }
    .platform-table th { background: #f4eee2; padding: 8px 10px; text-align: left; font-weight: 600; color: #657184; border-bottom: 1px solid #ebe5da; }
    .platform-table td { padding: 8px 10px; border-bottom: 1px solid #ebe5da; vertical-align: top; }
    .platform-table td.num { text-align: right; font-weight: 700; color: #1f2933; }
    .platform-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; color: #fff; font: 700 12px/1.4 ui-sans-serif, system-ui, sans-serif; }

    /* quote tag */
    .quote-tag { display: inline-block; padding: 1px 6px; border-radius: 3px; color: #fff; font: 700 11px/1.4 ui-sans-serif, system-ui, sans-serif; }
    .quote-label { font: 600 11px/1.4 ui-sans-serif, system-ui, sans-serif; color: #657184; }
  </style>
</head>
<body>
  <main>
    <div class="eyebrow">Specta AI 品牌圈层报告</div>
    <h1>${escapeHtml(centerTerm)}品牌圈层解读报告</h1>
    <div class="meta">由平台回答解析结果生成。外围节点来自回答证据，战略词只作为解释背景。</div>
    ${sectionHtml}
    ${questionHtml}
    ${platformHtml}
    ${evidenceHtml}
    ${traceHtml}
    ${actionHtml}
    ${appendixHtml}
    ${qualityHtml}
  </main>
</body>
</html>`;
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${centerTerm}-brand-association-report.html`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderExportParagraphHtml(text: string, entities: string[]): string {
  const boldSplit = text.split(/\*\*(.+?)\*\*/g);
  const parts: string[] = [];
  boldSplit.forEach((segment, segmentIndex) => {
    if (!segment) return;
    if (segmentIndex % 2 === 1) {
      parts.push(`<strong>${escapeHtml(segment)}</strong>`);
      return;
    }
    if (!entities.length) {
      parts.push(escapeHtml(segment));
      return;
    }
    const pattern = new RegExp(`(${entities.map(escapeRegexValue).join('|')})`, 'g');
    const subParts = segment.split(pattern);
    subParts.forEach((sub) => {
      if (!sub) return;
      if (entities.includes(sub)) {
        parts.push(`<strong>${escapeHtml(sub)}</strong>`);
      } else {
        parts.push(escapeHtml(sub));
      }
    });
  });
  return parts.join('');
}

function WeightCard({ title, value, text }: { title: string; value: string; text: string }) {
  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">{title}</h3>
        <span className="rounded-full border border-[var(--brand-border)] bg-[var(--bg-primary)] px-2 py-1 text-xs text-[var(--brand-primary)]">{value}</span>
      </div>
      <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{text}</p>
    </div>
  );
}

export function buildAssociationProjection(
  world?: OntologyWorldSummary | null,
  home?: DashboardHomeData | null,
): OntologyAssociationCircleProjection {
  if (world?.association_circle_projection) {
    return {
      ...world.association_circle_projection,
      center_terms: normalizeCenterTerms(world.association_circle_projection.center_terms),
      nodes: Array.isArray(world.association_circle_projection.nodes)
        ? world.association_circle_projection.nodes
        : [],
      question_bank: Array.isArray(world.association_circle_projection.question_bank)
        ? world.association_circle_projection.question_bank
        : [],
      evidence_samples: Array.isArray(world.association_circle_projection.evidence_samples)
        ? world.association_circle_projection.evidence_samples
        : [],
      platform_comparison: Array.isArray(world.association_circle_projection.platform_comparison)
        ? world.association_circle_projection.platform_comparison
        : [],
      association_actions: Array.isArray(world.association_circle_projection.association_actions)
        ? world.association_circle_projection.association_actions
        : [],
      report_narrative_sections: Array.isArray(world.association_circle_projection.report_narrative_sections)
        ? world.association_circle_projection.report_narrative_sections
        : [],
      evidence_findings: Array.isArray(world.association_circle_projection.evidence_findings)
        ? world.association_circle_projection.evidence_findings
        : [],
      analysis_tool_trace: Array.isArray(world.association_circle_projection.analysis_tool_trace)
        ? world.association_circle_projection.analysis_tool_trace
        : [],
      report_outline: Array.isArray(world.association_circle_projection.report_outline)
        ? world.association_circle_projection.report_outline
        : [],
      strategy_validation: Array.isArray(world.association_circle_projection.strategy_validation)
        ? world.association_circle_projection.strategy_validation
        : [],
      source_appendix: Array.isArray(world.association_circle_projection.source_appendix)
        ? world.association_circle_projection.source_appendix
        : [],
    };
  }
  return {
    dashboard_variant: 'amway_association_circle',
    analysis_mode: 'brand_association_circle',
    report_kind: 'brand_association_circle',
    status: 'not_generated',
    center_terms: normalizeCenterTerms(home?.center_terms),
    nodes: [],
    question_bank: [],
    evidence_samples: [],
    platform_comparison: [],
    association_actions: [],
    report_narrative_sections: [],
    evidence_findings: [],
    analysis_tool_trace: [],
    report_outline: [],
    strategy_validation: [],
    source_appendix: [],
    sample_scope: {},
    executive_summary: {},
  };
}

export function normalizeCenterTerms(value?: unknown): string[] {
  if (!Array.isArray(value)) return DEFAULT_CENTER_TERMS;
  const result = value.map((item) => String(item || '').trim()).filter(Boolean);
  return result.length ? Array.from(new Set(result)).slice(0, 3) : DEFAULT_CENTER_TERMS;
}

function scoreText(value?: number) {
  return typeof value === 'number' && Number.isFinite(value) ? String(Math.round(value)) : '-';
}

function sampleQuestionCount(sampleScope: Record<string, unknown>) {
  return firstSampleNumber(sampleScope.question_count, sampleScope.total_question_count);
}

export function sampleAnswerCount(sampleScope: Record<string, unknown>) {
  return firstSampleNumber(
    sampleScope.answer_count,
    sampleScope.valid_answer_count,
    sampleScope.total_answer_count,
  );
}

function samplePlatformCount(sampleScope: Record<string, unknown>) {
  return firstSampleNumber(sampleScope.platform_count, sampleScope.valid_platform_count);
}

function readLiveExtractionStats(sampleScope: Record<string, unknown>) {
  return {
    answerCount: sampleAnswerCount(sampleScope),
    signalCount: firstSampleNumber(sampleScope.signal_count),
    eventCount: firstSampleNumber(sampleScope.extraction_event_count),
  };
}

function firstSampleNumber(...values: unknown[]) {
  for (const value of values) {
    const numericValue = toNumber(value);
    if (numericValue > 0) return numericValue;
  }
  return 0;
}

function toNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : 0;
}

function platformLabel(platform: string) {
  const normalized = platform.toLowerCase();
  if (normalized.includes('doubao')) return '豆包';
  if (normalized.includes('yuanbao') || normalized.includes('hunyuan')) return '腾讯元宝';
  if (normalized.includes('kimi') || normalized.includes('moonshot')) return 'Kimi';
  if (normalized.includes('deepseek')) return 'DeepSeek';
  return platform || '未知平台';
}


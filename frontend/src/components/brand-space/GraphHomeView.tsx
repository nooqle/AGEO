'use client';

import { useState } from 'react';
import { AlertTriangle, Check, GitBranch, Layers, RotateCcw, ShieldCheck, X } from 'lucide-react';
import { GraphUpdateQueue } from './GraphUpdateQueue';
import styles from './BrandSpace.module.css';
import { evidenceRefs, graphEntities, graphRelations } from '@/mocks/brandSpaceMock';
import type {
  BrandSpaceGraph,
  BrandSpaceGraphUpdate,
  EvidenceRef,
  GraphEntity,
  GraphPatch,
  GraphPatchStatus,
  GraphReviewItem,
} from '@/types/brandSpace';

interface GraphHomeViewProps {
  patches: GraphPatch[];
  graph?: BrandSpaceGraph;
  graphUpdate?: BrandSpaceGraphUpdate | null;
  brandName?: string;
  reviewItems?: GraphReviewItem[];
  pendingPatchDecisionIds?: string[];
  onPatchDecision: (patchId: string, status: Extract<GraphPatchStatus, 'accepted' | 'rejected' | 'needs_review'>) => void;
}

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function entityClass(entity: GraphEntity) {
  return classNames(
    styles.graphEntity,
    entity.zone === 'risk' && styles.entityRisk,
    entity.zone === 'competitor' && styles.entityCompetitor,
    entity.zone === 'pending_review' && styles.entityPending,
  );
}

const zoneLabels: Record<GraphEntity['zone'], string> = {
  center: '品牌中心',
  inner: '内圈',
  middle: '中圈',
  outer: '外圈',
  risk: '风险圈',
  competitor: '竞品圈',
  pending_review: '待审阅',
};

const polarityLabels: Record<string, string> = {
  positive: '正向',
  neutral: '中性',
  questioning: '质疑',
  negative: '负向',
};

const categoryLabels: Record<string, string> = {
  all: '全部',
  risk: '风险',
  competitor: '竞品',
  new_entity: '新实体',
  low_confidence: '低置信',
  conflict: '冲突',
  graph_change: '图谱变化',
};

const priorityLabels: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
};

const graphUpdateStatusLabels: Record<string, string> = {
  pending: '待处理',
  needs_review: '待审阅',
  partial: '部分应用',
  accepted: '已接受',
  applied: '已应用',
  failed: '未应用',
};

const relationKindLabels: Record<string, string> = {
  belongs_to: '归属',
  supports: '支持',
  associated_with: '关联',
  solution_for: '方案',
  risk_of: '风险',
  competes_with: '竞品',
  scenario_for: '场景',
  risk_related: '风险',
  evidence_missing: '证据缺口',
  update_strength: '增强',
  add_risk_relation: '风险',
  add_competitor_relation: '竞品',
};

function relationKindLabel(kind: string) {
  return relationKindLabels[kind] ?? '关系';
}

const emptyEntity: GraphEntity = {
  id: 'empty-brand',
  label: '品牌中心',
  zone: 'center',
  x: 50,
  y: 50,
  strength: 100,
  evidenceCount: 0,
};

function fallbackCategory(patch: GraphPatch) {
  if (patch.category) return patch.category;
  if (patch.patchType === 'add_competitor_relation' || patch.relationType === 'competes_with') return 'competitor';
  if (patch.patchType === 'add_risk_relation') return 'risk';
  if (patch.patchType === 'add_entity') return 'new_entity';
  if (patch.confidence !== null && patch.confidence !== undefined && patch.confidence < 0.7) return 'low_confidence';
  return patch.status === 'blocked' ? 'conflict' : 'graph_change';
}

function reviewItemsFromPatches(patches: GraphPatch[]): GraphReviewItem[] {
  return patches
    .filter((patch) => patch.status === 'needs_review' || patch.status === 'blocked')
    .map((patch) => ({
      ...patch,
      graphUpdateId: patch.graphUpdateId ?? 'local-graph-update',
      graphUpdateStatus: 'needs_review',
      boardRunId: null,
      beforeGraphVersion: 'v0.0.0',
      afterGraphVersion: 'v0.1.0',
      graphUpdateCreatedAt: patch.createdAt ?? '',
      category: fallbackCategory(patch),
      priority: patch.priority ?? (patch.status === 'blocked' ? 'high' : 'medium'),
    }));
}

function evidenceForPatch(patch?: GraphPatch | null): EvidenceRef[] {
  return patch?.evidenceRefs?.length ? patch.evidenceRefs : [];
}

function patchIdForEntity(entity: GraphEntity, patches: GraphPatch[], inboxItems: GraphReviewItem[]) {
  if (entity.patchId) return entity.patchId;
  const candidates: GraphPatch[] = [...inboxItems, ...patches];
  const match = candidates.find((patch) => (
    patch.affectedEntityId === entity.id ||
    patch.affectedObjectId === entity.id ||
    patch.id === entity.id
  ));
  return match?.id;
}

function formatTimelineTime(value?: string | null) {
  if (!value) return '时间待记录';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function GraphHomeView({
  patches,
  graph,
  graphUpdate,
  brandName,
  reviewItems = [],
  pendingPatchDecisionIds = [],
  onPatchDecision,
}: GraphHomeViewProps) {
  const emptyCenterEntity = {
    ...emptyEntity,
    label: brandName || emptyEntity.label,
  };
  const visibleEntities = graph
    ? (graph.entities.length ? graph.entities : [emptyCenterEntity])
    : graphEntities;
  const visibleRelations = graph ? graph.relations : graphRelations;
  const fallbackEvidence = graph
    ? (graph.evidenceRefs.length ? graph.evidenceRefs : [])
    : evidenceRefs;
  const versionConflict = graphUpdate?.summary?.version_conflict as Record<string, unknown> | undefined;
  const currentGraphVersion = typeof versionConflict?.current_graph_version === 'string'
    ? versionConflict.current_graph_version
    : undefined;
  const expectedGraphVersion = typeof versionConflict?.expected_before_graph_version === 'string'
    ? versionConflict.expected_before_graph_version
    : undefined;
  const inboxItems = reviewItems.length ? reviewItems : reviewItemsFromPatches(patches);
  const [selectedEntityId, setSelectedEntityId] = useState('');
  const [selectedPatchId, setSelectedPatchId] = useState(inboxItems[0]?.id ?? patches[0]?.id ?? '');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const selectedEntity = visibleEntities.find((entity) => entity.id === selectedEntityId) ?? visibleEntities[0] ?? emptyEntity;
  const entityById = new Map(visibleEntities.map((entity) => [entity.id, entity]));
  const filteredInboxItems = inboxItems.filter((item) => categoryFilter === 'all' || item.category === categoryFilter);
  const selectedPatch =
    inboxItems.find((item) => item.id === selectedPatchId) ??
    patches.find((patch) => patch.id === selectedPatchId) ??
    inboxItems[0] ??
    patches[0] ??
    null;
  const selectedEvidence = evidenceForPatch(selectedPatch).length ? evidenceForPatch(selectedPatch) : fallbackEvidence;
  const selectedPatchPending = selectedPatch ? pendingPatchDecisionIds.includes(selectedPatch.id) : false;
  const selectedPatchNeedsAction = selectedPatch?.status === 'needs_review' || selectedPatch?.status === 'blocked';
  const categoryCounts = inboxItems.reduce<Record<string, number>>((acc, item) => {
    const category = item.category ?? 'graph_change';
    acc[category] = (acc[category] ?? 0) + 1;
    return acc;
  }, {});
  const categoryOptions = ['all', ...Object.keys(categoryCounts)];
  const zoneCounts = visibleEntities.reduce<Record<string, number>>((acc, entity) => {
    if (entity.zone === 'center') return acc;
    acc[entity.zone] = (acc[entity.zone] ?? 0) + 1;
    return acc;
  }, {});
  const timelineItems = graphUpdate
    ? [
        `本次更新：${graphUpdate.before_graph_version} → ${graphUpdate.after_graph_version}`,
        `状态：${graphUpdateStatusLabels[graphUpdate.status] ?? graphUpdate.status}`,
        `记录时间：${formatTimelineTime(graphUpdate.updated_at ?? graphUpdate.created_at)}`,
      ]
    : ['尚未生成图谱更新，当前只展示品牌实体库基础状态。'];
  const selectGraphEntity = (entity: GraphEntity) => {
    setSelectedEntityId(entity.id);
    const linkedPatchId = patchIdForEntity(entity, patches, inboxItems);
    if (linkedPatchId) {
      setSelectedPatchId(linkedPatchId);
    }
  };

  return (
    <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-4">
        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">品牌圈层图谱</p>
              <h1 className="mt-1 text-xl font-semibold text-[var(--text-primary)]">
                {brandName ? `${brandName}实体关系状态` : '品牌实体关系状态'}
              </h1>
              {graph?.meta?.message ? (
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{graph.meta.message}</p>
              ) : null}
              {graphUpdate?.status === 'failed' ? (
                <div
                  className="mt-3 flex max-w-2xl items-start gap-2 rounded-lg border px-3 py-2 text-xs"
                  style={{ borderColor: 'var(--error)', background: 'rgba(220, 38, 38, 0.06)', color: 'var(--text-secondary)' }}
                >
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--error)]" />
                  <div>
                    <p className="font-semibold text-[var(--text-primary)]">图谱更新未应用</p>
                    <p className="mt-1">
                      这次更新基于旧图谱版本，系统已阻止覆盖正式图谱
                      {currentGraphVersion ? `。当前版本：${currentGraphVersion}` : ''}
                      {expectedGraphVersion ? `，更新基线：${expectedGraphVersion}` : ''}。
                    </p>
                  </div>
                </div>
              ) : null}
            </div>
            <div className={styles.graphLegend} aria-label="图谱图例">
              {(['inner', 'middle', 'risk', 'competitor', 'pending_review'] as const).map((zone) => (
                <span key={zone} data-zone={zone}>
                  <i />
                  {zoneLabels[zone]} {zoneCounts[zone] ?? 0}
                </span>
              ))}
            </div>
          </div>

          <div className={classNames(styles.graphPanel, 'rounded-xl')}>
            <div className={styles.graphMap}>
              <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-hidden>
                <circle cx="50" cy="50" r="16" className={styles.graphZoneRing} />
                <circle cx="50" cy="50" r="29" className={styles.graphZoneRing} />
                <circle cx="50" cy="50" r="42" className={styles.graphZoneRingOuter} />
                {visibleRelations.map((relation) => {
                  const from = entityById.get(relation.from);
                  const to = entityById.get(relation.to);
                  if (!from || !to) return null;
                  const strength = Math.max(0.35, Math.min(1, relation.strength || 0.35));
                  return (
                    <g key={relation.id}>
                      <line
                        x1={from.x}
                        y1={from.y}
                        x2={to.x}
                        y2={to.y}
                        className={classNames(
                          styles.graphLink,
                          relation.kind.includes('risk') && styles.graphLinkRisk,
                          relation.kind.includes('compet') && styles.graphLinkCompetitor,
                        )}
                        style={{ strokeWidth: 1.4 + strength * 3 }}
                      />
                      <text
                        x={(from.x + to.x) / 2}
                        y={(from.y + to.y) / 2 - 2}
                        className={styles.graphRelationLabel}
                      >
                        {relationKindLabel(relation.kind)} · {Math.round(strength * 100)}
                      </text>
                    </g>
                  );
                })}
              </svg>

              {visibleEntities.map((entity) => {
                const zoneLabel = zoneLabels[entity.zone] ?? '待分层';
                const strengthLabel = Number.isFinite(entity.strength) ? Math.round(entity.strength) : 0;
                return (
                  <button
                    key={entity.id}
                    type="button"
                    onClick={() => selectGraphEntity(entity)}
                    className={entityClass(entity)}
                    style={{ left: `${entity.x}%`, top: `${entity.y}%` }}
                    aria-label={`查看实体：${entity.label}，圈层${zoneLabel}，连接强度${strengthLabel}`}
                  >
                    <span className={entity.zone === 'center' ? styles.entityCenter : styles.entityPoint} />
                    <span className={styles.entityLabel}>
                      <strong>{entity.label}</strong>
                      <em>{zoneLabel} · {strengthLabel}</em>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        <GraphUpdateQueue
          patches={patches}
          graphUpdate={graphUpdate}
          onPatchDecision={onPatchDecision}
          onPatchSelect={setSelectedPatchId}
          selectedPatchId={selectedPatch?.id}
          pendingPatchDecisionIds={pendingPatchDecisionIds}
        />
      </div>

      <aside className="space-y-4">
        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">审阅队列</p>
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">待审阅图谱变化</h2>
            </div>
            <span className="rounded-lg border px-2.5 py-1 text-xs text-[var(--brand-text)]" style={{ borderColor: 'var(--brand-border)', background: 'var(--brand-bg)' }}>
              {inboxItems.length} 项
            </span>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {categoryOptions.map((category) => (
              <button
                key={category}
                type="button"
                onClick={() => setCategoryFilter(category)}
                className="rounded-lg border px-2.5 py-1.5 text-xs font-medium"
                aria-pressed={categoryFilter === category}
                aria-label={`筛选审阅项：${categoryLabels[category] ?? category}`}
                style={{
                  borderColor: categoryFilter === category ? 'var(--brand-border)' : 'var(--border-subtle)',
                  background: categoryFilter === category ? 'var(--brand-bg)' : 'transparent',
                  color: categoryFilter === category ? 'var(--brand-text)' : 'var(--text-secondary)',
                }}
              >
                {categoryLabels[category] ?? category}
                {category !== 'all' ? ` ${categoryCounts[category] ?? 0}` : ''}
              </button>
            ))}
          </div>
          <div className="mt-3 space-y-2">
            {filteredInboxItems.length ? filteredInboxItems.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedPatchId(item.id)}
                className={classNames(
                  'w-full rounded-xl border p-3 text-left transition-colors',
                  selectedPatch?.id === item.id && styles.queueSelected,
                )}
                aria-label={`查看待审阅补丁：${item.title}`}
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{item.title}</p>
                    <p className="mt-1 text-xs text-[var(--text-secondary)]">
                      {categoryLabels[item.category ?? 'graph_change'] ?? item.category} · {priorityLabels[String(item.priority ?? 'medium')] ?? item.priority}优先级
                    </p>
                  </div>
                  <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-[11px] text-[var(--text-tertiary)]">
                    {item.evidenceRefIds.length}
                  </span>
                </div>
              </button>
            )) : (
              <div className="rounded-xl border p-3 text-xs leading-5 text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                当前筛选下没有待审阅项。
              </div>
            )}
          </div>
        </section>

        {selectedPatch ? (
          <section className={classNames(styles.surface, 'rounded-xl p-4')}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">补丁详情</p>
                <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">{selectedPatch.title}</h2>
              </div>
              <span className="rounded-lg border px-2 py-1 text-xs text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                {selectedPatch.score}
              </span>
            </div>
            <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">{selectedPatch.description}</p>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-lg bg-[var(--bg-tertiary)] p-2">
                <p className="text-[var(--text-tertiary)]">类型</p>
                <p className="mt-1 font-medium text-[var(--text-primary)]">{categoryLabels[selectedPatch.category ?? 'graph_change'] ?? selectedPatch.category}</p>
              </div>
              <div className="rounded-lg bg-[var(--bg-tertiary)] p-2">
                <p className="text-[var(--text-tertiary)]">置信度</p>
                <p className="mt-1 font-medium text-[var(--text-primary)]">{selectedPatch.confidence ?? '-'}</p>
              </div>
              <div className="rounded-lg bg-[var(--bg-tertiary)] p-2">
                <p className="text-[var(--text-tertiary)]">风险/情绪</p>
                <p className="mt-1 font-medium text-[var(--text-primary)]">{selectedPatch.sentimentOrRiskScore ?? '-'}</p>
              </div>
              <div className="rounded-lg bg-[var(--bg-tertiary)] p-2">
                <p className="text-[var(--text-tertiary)]">证据</p>
                <p className="mt-1 font-medium text-[var(--text-primary)]">{selectedPatch.evidenceRefIds.length} 条</p>
              </div>
            </div>
            {selectedPatch.suggestedAction ? (
              <div className="mt-3 rounded-xl border p-3 text-xs leading-5 text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                {selectedPatch.suggestedAction}
              </div>
            ) : null}
            {selectedPatchNeedsAction ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={selectedPatchPending}
                  onClick={() => onPatchDecision(selectedPatch.id, 'accepted')}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[var(--brand-primary)] px-2.5 text-xs font-medium text-[var(--brand-contrast)] disabled:opacity-55"
                  aria-label={`接受补丁：${selectedPatch.title}`}
                >
                  <Check className="h-3.5 w-3.5" />
                  {selectedPatchPending ? '处理中' : '接受'}
                </button>
                <button
                  type="button"
                  disabled={selectedPatchPending}
                  onClick={() => onPatchDecision(selectedPatch.id, 'needs_review')}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium text-[var(--text-secondary)] disabled:opacity-55"
                  aria-label={`保留审阅补丁：${selectedPatch.title}`}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  保留
                </button>
                <button
                  type="button"
                  disabled={selectedPatchPending}
                  onClick={() => onPatchDecision(selectedPatch.id, 'rejected')}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium text-[var(--error)] disabled:opacity-55"
                  aria-label={`拒绝补丁：${selectedPatch.title}`}
                >
                  <X className="h-3.5 w-3.5" />
                  拒绝
                </button>
              </div>
            ) : (
              <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                {selectedPatch.reviewedAt ? `已审阅：${selectedPatch.reviewReason || '无备注'}` : '该补丁当前不可操作。'}
              </p>
            )}
          </section>
        ) : null}

        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">当前实体</p>
              <h2 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{selectedEntity.label}</h2>
            </div>
            <span className="rounded-lg border px-2 py-1 text-xs capitalize text-[var(--brand-text)]" style={{ borderColor: 'var(--brand-border)', background: 'var(--brand-bg)' }}>
              {zoneLabels[selectedEntity.zone]}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
              <p className="text-xs text-[var(--text-tertiary)]">连接强度</p>
              <p className="mt-1 text-xl font-semibold text-[var(--text-primary)]">{selectedEntity.strength}</p>
            </div>
            <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
              <p className="text-xs text-[var(--text-tertiary)]">证据</p>
              <p className="mt-1 text-xl font-semibold text-[var(--text-primary)]">{selectedEntity.evidenceCount}</p>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            <div className="flex items-start gap-3 rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
              <ShieldCheck className="mt-0.5 h-4 w-4 text-[var(--brand-primary)]" />
              <p className="text-xs leading-5 text-[var(--text-secondary)]">
                圈层位置由连接评分、情绪阈值和审阅状态共同决定。
              </p>
            </div>
            <div className="flex items-start gap-3 rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
              <AlertTriangle className="mt-0.5 h-4 w-4 text-[var(--warning)]" />
              <p className="text-xs leading-5 text-[var(--text-secondary)]">
                风险关系和竞品关系默认保持可见，普通筛选不能隐藏。
              </p>
            </div>
          </div>
        </section>

        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-[var(--brand-primary)]" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">证据预览</h2>
          </div>
          <div className="mt-3 space-y-3">
            {selectedEvidence.map((evidence) => (
              <div key={evidence.id} className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-[var(--text-primary)]">{evidence.platform}</span>
                  <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-[11px] text-[var(--text-tertiary)]">
                    {polarityLabels[evidence.polarity] ?? evidence.polarity}
                  </span>
                </div>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{evidence.excerpt}</p>
              </div>
            ))}
          </div>
        </section>

        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-[var(--brand-primary)]" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">更新时间线</h2>
          </div>
          <div className="mt-3 space-y-2 text-xs text-[var(--text-secondary)]">
            {timelineItems.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

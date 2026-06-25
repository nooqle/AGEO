'use client';

import { useState } from 'react';
import { AlertTriangle, Check, GitBranch, Layers, RotateCcw, ShieldCheck, X } from 'lucide-react';
import { GraphUpdateQueue } from './GraphUpdateQueue';
import styles from './BrandSpace.module.css';
import type {
  BrandSpaceGraph,
  BrandSpaceGraphUpdate,
  EvidenceRef,
  GraphEntity,
  GraphPatch,
  GraphPatchStatus,
  GraphRelation,
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

const graphZones = ['center', 'inner', 'middle', 'outer', 'risk', 'competitor', 'pending_review'] as const;
const graphZoneSet = new Set<string>(graphZones);
const graphRelationStrengthMap: Record<string, number> = {
  weak: 0.35,
  low: 0.35,
  medium: 0.6,
  moderate: 0.6,
  strong: 0.85,
  high: 0.85,
};

function normalizeGraphZone(value: unknown): GraphEntity['zone'] {
  return typeof value === 'string' && graphZoneSet.has(value)
    ? value as GraphEntity['zone']
    : 'pending_review';
}

function normalizeEntityStrength(value: unknown, fallback: number) {
  const numeric = typeof value === 'number'
    ? value
    : typeof value === 'string'
      ? Number.parseFloat(value)
      : Number.NaN;
  return Number.isFinite(numeric) ? Math.max(0, Math.min(100, numeric)) : fallback;
}

function normalizeRelationStrength(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 1 ? Math.max(0, Math.min(1, value / 100)) : Math.max(0, Math.min(1, value));
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    const numeric = Number.parseFloat(normalized);
    if (Number.isFinite(numeric)) return numeric > 1 ? Math.max(0, Math.min(1, numeric / 100)) : Math.max(0, Math.min(1, numeric));
    return graphRelationStrengthMap[normalized] ?? 0.35;
  }
  return 0.35;
}

function normalizeGraphEntity(entity: GraphEntity, index: number): GraphEntity {
  const raw = entity as GraphEntity & Record<string, unknown>;
  const zone = normalizeGraphZone(raw.zone);
  return {
    ...entity,
    id: typeof raw.id === 'string' && raw.id ? raw.id : `graph-entity-${index}`,
    label: typeof raw.label === 'string' && raw.label ? raw.label : '未命名实体',
    zone,
    x: normalizeEntityStrength(raw.x, 50),
    y: normalizeEntityStrength(raw.y, 50),
    strength: normalizeEntityStrength(raw.strength, zone === 'center' ? 100 : 50),
    evidenceCount: Math.round(normalizeEntityStrength(raw.evidenceCount, 0)),
  };
}

function normalizeGraphRelation(relation: GraphRelation, index: number): GraphRelation | null {
  const raw = relation as GraphRelation & Record<string, unknown>;
  if (typeof raw.from !== 'string' || typeof raw.to !== 'string' || !raw.from || !raw.to) {
    return null;
  }
  return {
    ...relation,
    id: typeof raw.id === 'string' && raw.id ? raw.id : `graph-relation-${index}`,
    from: raw.from,
    to: raw.to,
    kind: typeof raw.kind === 'string' && raw.kind ? raw.kind : 'associated_with',
    strength: normalizeRelationStrength(raw.strength),
  };
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

const legendZoneLabels: Record<GraphEntity['zone'], string> = {
  ...zoneLabels,
  pending_review: '待审阅实体',
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

function visualZoneForEntity(entity: GraphEntity): GraphEntity['zone'] {
  const safeZone = normalizeGraphZone(entity.zone);
  if (entity.patchStatus !== 'accepted' && entity.patchStatus !== 'auto_applied') {
    return safeZone;
  }
  if (entity.patchType === 'add_competitor_relation' || entity.category === 'competitor') {
    return 'competitor';
  }
  if (entity.patchType === 'add_risk_relation' || entity.category === 'risk') {
    return 'risk';
  }
  if (safeZone !== 'pending_review') {
    return safeZone;
  }
  if (entity.strength >= 80) return 'inner';
  if (entity.strength >= 60) return 'middle';
  return 'outer';
}

const graphCenter = { x: 50, y: 50 };

const zoneRadii: Record<GraphEntity['zone'], number> = {
  center: 0,
  inner: 23,
  middle: 33,
  outer: 42,
  risk: 38,
  competitor: 39,
  pending_review: 31,
};

const zoneAngleSeeds: Record<Exclude<GraphEntity['zone'], 'center'>, number[]> = {
  inner: [-138, -88, -36, 26, 138],
  middle: [-166, -118, -62, -10, 44, 102, 154],
  outer: [-176, -132, -86, -42, 6, 52, 96, 142],
  risk: [72, 108, 144, 36],
  competitor: [-26, 18, 58, -66],
  pending_review: [-156, -126, -96, -66, -36, -6, 24, 54, 84, 114, 144, 174],
};

function clampGraphPoint(value: number) {
  return Math.max(8, Math.min(92, value));
}

function resolveGraphCollisions(entities: GraphEntity[]) {
  const next = entities.map((entity) => ({ ...entity }));
  const minX = 12.8;
  const minY = 10.5;

  for (let pass = 0; pass < 80; pass += 1) {
    let moved = false;

    for (let leftIndex = 0; leftIndex < next.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < next.length; rightIndex += 1) {
        const left = next[leftIndex];
        const right = next[rightIndex];
        const deltaX = right.x - left.x;
        const deltaY = right.y - left.y;
        const horizontalOverlap = minX - Math.abs(deltaX);
        const verticalOverlap = minY - Math.abs(deltaY);

        if (horizontalOverlap <= 0 || verticalOverlap <= 0) continue;

        const distance = Math.hypot(deltaX, deltaY);
        const fallbackAngle = ((leftIndex + rightIndex + pass) * 47 * Math.PI) / 180;
        const unitX = distance > 0.01 ? deltaX / distance : Math.cos(fallbackAngle);
        const unitY = distance > 0.01 ? deltaY / distance : Math.sin(fallbackAngle);
        const push = Math.min(3.4, Math.max(0.7, Math.max(horizontalOverlap, verticalOverlap) / 2));
        const leftFixed = left.zone === 'center';
        const rightFixed = right.zone === 'center';

        if (!leftFixed) {
          left.x = clampGraphPoint(left.x - unitX * push);
          left.y = clampGraphPoint(left.y - unitY * push);
        }
        if (!rightFixed) {
          right.x = clampGraphPoint(right.x + unitX * push);
          right.y = clampGraphPoint(right.y + unitY * push);
        }
        moved = true;
      }
    }

    if (!moved) break;
  }

  return next;
}

function layoutGraphEntities(entities: GraphEntity[], relations: GraphRelation[]): GraphEntity[] {
  const normalizedEntities: GraphEntity[] = entities.map((entity, index) => normalizeGraphEntity(entity, index)).map((entity): GraphEntity => ({
    ...entity,
    zone: visualZoneForEntity(entity),
  }));
  const centerEntityId = (normalizedEntities.find((entity) => entity.zone === 'center') ?? normalizedEntities[0] ?? emptyEntity).id;
  const relationDegree = relations.reduce<Record<string, number>>((acc, relation) => {
    acc[relation.from] = (acc[relation.from] ?? 0) + 1;
    acc[relation.to] = (acc[relation.to] ?? 0) + 1;
    return acc;
  }, {});
  const zoneIndex: Partial<Record<GraphEntity['zone'], number>> = {};

  const positioned: GraphEntity[] = normalizedEntities.map((entity): GraphEntity => {
    if (entity.id === centerEntityId) {
      return { ...entity, zone: 'center', x: graphCenter.x, y: graphCenter.y };
    }

    const normalizedZone = normalizeGraphZone(entity.zone);
    const zone: GraphEntity['zone'] = normalizedZone === 'center' ? 'pending_review' : normalizedZone;
    const index = zoneIndex[zone] ?? 0;
    zoneIndex[zone] = index + 1;
    const seeds = zoneAngleSeeds[zone];
    const angle = seeds[index % seeds.length] + Math.floor(index / seeds.length) * 12;
    const degreeOffset = Math.min(4, relationDegree[entity.id] ?? 0);
    const radius = zoneRadii[zone] + Math.floor(index / seeds.length) * 2 + degreeOffset * 0.35;
    const radians = (angle * Math.PI) / 180;

    return {
      ...entity,
      zone,
      x: clampGraphPoint(graphCenter.x + Math.cos(radians) * radius),
      y: clampGraphPoint(graphCenter.y + Math.sin(radians) * radius),
    };
  });

  return resolveGraphCollisions(positioned);
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
  const sourceEntities = graph
    ? (graph.entities.length ? graph.entities : [emptyCenterEntity])
    : [emptyCenterEntity];
  const visibleRelations = graph
    ? graph.relations
        .map((relation, index) => normalizeGraphRelation(relation, index))
        .filter((relation): relation is GraphRelation => Boolean(relation))
    : [];
  const visibleEntities = layoutGraphEntities(sourceEntities, visibleRelations);
  const fallbackEvidence = graph
    ? (graph.evidenceRefs.length ? graph.evidenceRefs : [])
    : [];
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
  const selectedPatchObject = selectedPatch?.affectedObjectId
    ? entityById.get(selectedPatch.affectedObjectId)
    : undefined;
  const selectedPatchRelationLabel = selectedPatch
    ? relationKindLabel(selectedPatch.relationType ?? selectedPatch.patchType)
    : '';
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
  const pendingEntityCount = zoneCounts.pending_review ?? 0;
  const reviewQueueEmptyMessage = pendingEntityCount
    ? `当前没有待处理 Graph Update 补丁。图谱中仍有 ${pendingEntityCount} 个待审阅实体，它们是实体库分层状态；需要新一轮运行生成补丁后才会进入这里。`
    : graphUpdate
      ? '本次 Graph Update 没有需要人工处理的补丁。'
      : '尚未生成 Graph Update 补丁。完成一次画布运行后，需要人工处理的图谱变化会出现在这里。';
  const relationSummaries = visibleRelations
    .map((relation) => {
      const from = entityById.get(relation.from);
      const to = entityById.get(relation.to);
      if (!from || !to) return null;
      const strength = Math.round(Math.max(0.35, Math.min(1, relation.strength || 0.35)) * 100);
      return {
        id: relation.id,
        kind: relation.kind,
        fromId: relation.from,
        toId: relation.to,
        fromLabel: from.label,
        toLabel: to.label,
        label: relationKindLabel(relation.kind),
        strength,
        text: `${from.label} → ${to.label}`,
        x: (from.x + to.x) / 2,
        y: (from.y + to.y) / 2,
      };
    })
    .filter(Boolean);
  const selectedRelationSummaries = relationSummaries.filter((relation) => (
    relation && (relation.fromId === selectedEntity.id || relation.toId === selectedEntity.id)
  ));
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
                  {legendZoneLabels[zone]} {zoneCounts[zone] ?? 0}
                </span>
              ))}
            </div>
          </div>
          <div className={styles.graphRelationSummary} aria-label="图谱关系摘要">
            {relationSummaries.map((relation) => relation ? (
              <span key={relation.id} data-kind={relation.kind}>
                <strong>{relation.label}</strong>
                {relation.text}
                <em>{relation.strength}</em>
              </span>
            ) : null)}
          </div>

          <div className={classNames(styles.graphPanel, 'rounded-xl')}>
            <div className={styles.graphMap}>
              <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-hidden>
                <circle cx="50" cy="50" r="16" className={styles.graphZoneRing} />
                <circle cx="50" cy="50" r="29" className={styles.graphZoneRing} />
                <circle cx="50" cy="50" r="42" className={styles.graphZoneRingOuter} />
                <text x="50" y="33" textAnchor="middle" className={styles.graphZoneText}>内圈</text>
                <text x="50" y="20" textAnchor="middle" className={styles.graphZoneText}>中圈</text>
                <text x="50" y="7" textAnchor="middle" className={styles.graphZoneText}>外圈</text>
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
                    className={classNames(entityClass(entity), selectedEntity.id === entity.id && styles.graphEntitySelected)}
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
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">待处理图谱变化</h2>
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
                {reviewQueueEmptyMessage}
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

          <div className="mt-4 rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold text-[var(--text-primary)]">直接关系</p>
              <span className="text-xs text-[var(--text-tertiary)]">{selectedRelationSummaries.length} 条</span>
            </div>
            <div className="mt-3 space-y-2">
              {selectedRelationSummaries.length ? selectedRelationSummaries.map((relation) => relation ? (
                <div key={relation.id} className={styles.entityRelationRow}>
                  <span data-kind={relation.kind}>{relation.label}</span>
                  <strong>{relation.text}</strong>
                  <em>{relation.strength}</em>
                </div>
              ) : null) : (
                <p className="text-xs leading-5 text-[var(--text-secondary)]">
                  当前实体还没有可视化直接关系。
                </p>
              )}
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
            {selectedPatch ? (
              <div className="rounded-xl border p-3" style={{ borderColor: 'var(--brand-border)', background: 'var(--brand-bg)' }}>
                <p className="text-xs font-semibold text-[var(--text-primary)]">当前补丁判定</p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                  {selectedPatchRelationLabel ? `关系：${selectedPatchRelationLabel}。` : ''}
                  {selectedPatchObject ? `对象：${selectedPatchObject.label}。` : ''}
                  状态：{graphUpdateStatusLabels[selectedPatch.status] ?? selectedPatch.status}，得分：{selectedPatch.score}。
                </p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{selectedPatch.description}</p>
              </div>
            ) : null}
            {selectedEvidence.length ? selectedEvidence.map((evidence) => (
              <div key={evidence.id} className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-[var(--text-primary)]">{evidence.platform}</span>
                  <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-[11px] text-[var(--text-tertiary)]">
                    {polarityLabels[evidence.polarity] ?? evidence.polarity}
                  </span>
                </div>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{evidence.excerpt}</p>
              </div>
            )) : (
              <div className="rounded-xl border p-3 text-xs leading-5 text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                当前图谱更新没有可展示的证据摘录。需要重新运行画布或补充资产后再生成 Graph Update。
              </div>
            )}
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

'use client';

import { useState } from 'react';
import { AlertTriangle, GitBranch, Layers, ShieldCheck } from 'lucide-react';
import { GraphUpdateQueue } from './GraphUpdateQueue';
import styles from './BrandSpace.module.css';
import { evidenceRefs, graphEntities, graphRelations } from '@/mocks/brandSpaceMock';
import type { BrandSpaceGraph, GraphEntity, GraphPatch, GraphPatchStatus } from '@/types/brandSpace';

interface GraphHomeViewProps {
  patches: GraphPatch[];
  graph?: BrandSpaceGraph;
  brandName?: string;
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

const lensLabels = ['圈层状态', '本次更新', '风险认知', '竞品压力'];

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

const emptyEntity: GraphEntity = {
  id: 'empty-brand',
  label: '品牌中心',
  zone: 'center',
  x: 50,
  y: 50,
  strength: 100,
  evidenceCount: 0,
};

export function GraphHomeView({ patches, graph, brandName, onPatchDecision }: GraphHomeViewProps) {
  const visibleEntities = graph?.entities?.length ? graph.entities : graphEntities;
  const visibleRelations = graph?.relations?.length ? graph.relations : graphRelations;
  const visibleEvidence = graph?.evidenceRefs?.length ? graph.evidenceRefs : evidenceRefs;
  const [selectedEntityId, setSelectedEntityId] = useState('amway');
  const selectedEntity = visibleEntities.find((entity) => entity.id === selectedEntityId) ?? visibleEntities[0] ?? emptyEntity;
  const entityById = new Map(visibleEntities.map((entity) => [entity.id, entity]));

  return (
    <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">品牌圈层图谱</p>
              <h1 className="mt-1 text-xl font-semibold text-[var(--text-primary)]">
                {brandName ? `${brandName}实体关系状态` : '品牌实体关系状态'}
              </h1>
            </div>
            <div className="flex flex-wrap gap-2">
              {lensLabels.map((lens, index) => (
                <button
                  key={lens}
                  type="button"
                  className="rounded-lg border px-3 py-2 text-xs font-medium"
                  style={{
                    borderColor: index === 0 ? 'var(--brand-border)' : 'var(--border-subtle)',
                    background: index === 0 ? 'var(--brand-bg)' : 'transparent',
                    color: index === 0 ? 'var(--brand-text)' : 'var(--text-secondary)',
                  }}
                >
                  {lens}
                </button>
              ))}
            </div>
          </div>

          <div className={classNames(styles.graphPanel, 'rounded-xl')}>
            <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
              {visibleRelations.map((relation) => {
                const from = entityById.get(relation.from);
                const to = entityById.get(relation.to);
                if (!from || !to) return null;
                return <line key={relation.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={styles.graphLink} />;
              })}
            </svg>

            {visibleEntities.map((entity) => (
              <button
                key={entity.id}
                type="button"
                onClick={() => setSelectedEntityId(entity.id)}
                className={entityClass(entity)}
                style={{ left: `${entity.x}%`, top: `${entity.y}%` }}
              >
                <span className={entity.zone === 'center' ? styles.entityCenter : styles.entityPoint} />
                <span className="mt-2 block rounded-md bg-[var(--bg-elevated)] px-2 py-1 text-[11px] font-medium text-[var(--text-secondary)] shadow-sm">
                  {entity.label}
                </span>
              </button>
            ))}
          </div>
        </section>

        <GraphUpdateQueue patches={patches} onPatchDecision={onPatchDecision} />
      </div>

      <aside className="space-y-4">
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
            {visibleEvidence.map((evidence) => (
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
            <p>v3.2.1 · 当前运行正在应用低风险补丁</p>
            <p>v3.2.0 · 上一次 AI 能见度监测</p>
            <p>v3.1.8 · 手动问题源导入</p>
          </div>
        </section>
      </aside>
    </div>
  );
}

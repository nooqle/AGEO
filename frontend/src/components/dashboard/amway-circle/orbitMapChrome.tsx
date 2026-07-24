/**
 * Orbit map chrome UI (knife 4a, zero behavior).
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, Info, Orbit, ShieldAlert } from 'lucide-react';
import type {
  OntologyAssociationCirclePriorityItem,
  OntologyAssociationCirclePrioritySummary,
} from '@/types/ontology';
import { platformLabel } from './constants';
import {
  cleanEvidenceExcerpt,
  cleanWorkflowProgressMessage,
  commercialReportCopy,
  priorityItemBrief,
  priorityItemsOrFallback,
  sampleKey,
} from './evidenceHelpers';
import {
  isCompetitorNode,
  nodeCountPhrase,
  nodeEvidenceCount,
} from './nodeMetrics';
import { orbitTrackColor } from './orbitMapVisual';
import type {
  AssociationMapGroup,
  AssociationMapMode,
  AssociationNodeFilterKey,
  AssociationNodeFilterOption,
  OrbitEvidenceItem,
} from './types';

export function LiveExtractionStatusStrip({
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
  const normalizedStage = String(currentStage || '').trim().toUpperCase();
  const activeStepIndex = normalizedStage === 'A5'
    ? 5
    : normalizedStage === 'A4'
      ? nodeCount > 0
        ? 4
        : signalCount > 0 || eventCount > 0
          ? 3
          : answerCount > 0
            ? 2
            : 1
      : 0;
  const stepContent: Array<{
    label: string;
    value: string;
  }> = [
    {
      label: '运行配置',
      value: targetPlatforms.length ? `${targetPlatforms.length} 个平台已就绪` : '读取运行配置',
    },
    {
      label: '平台抓取',
      value: cleanProgress || '正在获取平台回答',
    },
    {
      label: '回答入库',
      value: answerCount ? `${answerCount} 条已保存` : '等待首条回答',
    },
    {
      label: '实体抽取',
      value: signalCount ? `${signalCount} 个信号 / ${eventCount} 条事件` : '等待可抽取答案',
    },
    {
      label: '图谱入轨',
      value: nodeCount ? `${nodeCount} 个节点已出现` : '等待实体信号',
    },
    {
      label: '校准收束',
      value: normalizedStage === 'A5' ? '正在确认最终轨道' : '抓取完成后确认轨道',
    },
  ];
  const steps = stepContent.map((step, index) => ({
    ...step,
    state: index < activeStepIndex
      ? 'complete' as const
      : index === activeStepIndex
        ? 'active' as const
        : 'pending' as const,
  }));

  return (
    <div className="mt-4 overflow-x-auto border-y border-[var(--border-subtle)] bg-[var(--bg-primary)] px-1 py-3">
      <div className="flex items-center justify-between gap-3 px-1">
        <span className="text-xs font-semibold text-[var(--text-primary)]">本轮进度</span>
        <span className="text-xs text-[var(--text-tertiary)]">节点为阶段产物，最终轨道以校准结果为准</span>
      </div>
      <ol className="relative mt-3 grid min-w-[900px] grid-cols-6" aria-label="实时抓取与图谱生成流程">
        <span
          aria-hidden="true"
          data-amway-live-flow-track="base"
          className="absolute top-3 h-px bg-[var(--border-strong)]"
          style={{ left: '8.333%', right: '8.333%' }}
        />
        <span
          aria-hidden="true"
          data-amway-live-flow-track="progress"
          className="absolute top-3 h-px bg-[var(--text-secondary)] transition-[width] duration-300"
          style={{ left: '8.333%', width: `${activeStepIndex * 16.667}%` }}
        />
        {steps.map((step, index) => {
          const complete = step.state === 'complete';
          const active = step.state === 'active';
          return (
            <li
              key={step.label}
              className="relative z-10 flex min-w-0 flex-col items-center px-2 text-center"
              aria-current={active ? 'step' : undefined}
            >
              <span
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold"
                style={{
                  borderColor: active ? 'var(--brand-primary)' : complete ? 'var(--text-secondary)' : 'var(--border-strong)',
                  background: complete ? 'var(--text-secondary)' : 'var(--bg-primary)',
                  color: complete ? 'var(--bg-primary)' : active ? 'var(--brand-primary)' : 'var(--text-tertiary)',
                }}
              >
                {complete ? <Check size={13} strokeWidth={2.2} /> : index + 1}
              </span>
              <div className="mt-2 min-w-0 w-full">
                <div className={`text-xs font-semibold ${active ? 'text-[var(--brand-primary)]' : 'text-[var(--text-primary)]'}`}>
                  {step.label}
                </div>
                <div className="mt-0.5 truncate text-xs text-[var(--text-tertiary)]" title={step.value}>
                  {step.value}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function PriorityFocusStrip({
  summary,
  groups,
  onSelectNode,
}: {
  summary?: OntologyAssociationCirclePrioritySummary | null;
  groups: AssociationMapGroup[];
  onSelectNode: (nodeId: string | null, returnFocusTarget?: HTMLButtonElement) => void;
}) {
  const fallbackRiskGroup = groups.find((group) => group.key === 'risk')?.nodes || [];
  const fallbackRisks = fallbackRiskGroup.filter((node) => !isCompetitorNode(node));
  const fallbackCompetitors = fallbackRiskGroup.filter(isCompetitorNode);
  const fallbackOpportunities = [
    ...(groups.find((group) => group.key === 'growth')?.nodes || []),
    ...(groups.find((group) => group.key === 'story')?.nodes || []),
  ];
  const riskItems = priorityItemsOrFallback(
    summary?.top_risks?.filter((item) => item.focus_type !== 'competitor' && item.business_tag !== '竞争关系'),
    fallbackRisks,
    'risk',
  );
  const competitorItems = priorityItemsOrFallback(
    summary?.top_competitors,
    fallbackCompetitors,
    'competitor',
  );
  const opportunityItems = priorityItemsOrFallback(summary?.top_opportunities, fallbackOpportunities, 'opportunity');
  const hasItems = riskItems.length || competitorItems.length || opportunityItems.length;
  if (!hasItems) return null;
  return (
    <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-5 py-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">本周先看</div>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            按证据量、平台覆盖和关系性质排序。其他节点保留在图谱里作为复测背景。
          </p>
        </div>
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

export function PriorityColumn({
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
  onSelectNode: (nodeId: string | null, returnFocusTarget?: HTMLButtonElement) => void;
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
            onClick={(event) => item.node_id && onSelectNode(item.node_id, event.currentTarget)}
            className="amway-card-interactive w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-left hover:border-[var(--brand-border)] hover:bg-[var(--brand-bg)]"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-sm font-semibold">
                {item.rank ? `${item.rank}. ` : ''}{item.term || '待命名节点'}
              </span>
              <span className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-0.5 text-[11px] text-[var(--text-tertiary)]">
                {nodeCountPhrase(item, item.evidence_count || 0)}
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

export function OrbitMapLegend({ mapMode }: { mapMode: AssociationMapMode }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [prevMapMode, setPrevMapMode] = useState(mapMode);
  if (prevMapMode !== mapMode) {
    setPrevMapMode(mapMode);
    if (open) setOpen(false);
  }
  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [open]);
  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? '收起图例' : '查看图例'}
        onClick={() => setOpen((current) => !current)}
        className={`inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition ${
          open
            ? 'border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]'
            : 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-tertiary)] hover:border-[var(--brand-border)] hover:text-[var(--brand-primary)]'
        }`}
      >
        <Info size={12} strokeWidth={2} aria-hidden="true" />
        图例
      </button>
      {open ? (
        <div className="animate-scale-in absolute left-0 top-[calc(100%+8px)] z-40 w-max max-w-[min(560px,calc(100vw-48px))] rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3 shadow-lg">
          {mapMode === 'risk' ? (
            <div className="flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
              <OrbitGuidePill label="风险中心" text="旧认知和争议入口" tone="risk" />
              <OrbitGuidePill label="连线" text="看它如何回到品牌" />
              <OrbitGuidePill label="证据" text="点击节点查看问题、平台和回答摘录" />
            </div>
          ) : (
            <div className="flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
              <OrbitGuidePill label="稳定" text="已绑定" tone="strong" />
              <OrbitGuidePill label="机会" text="可拉近" tone="growth" />
              <OrbitGuidePill label="观察" text="待补证" tone="story" />
              <OrbitGuidePill label="战略" text="方形" tone="strong" marker="square" />
              <OrbitGuidePill label="回答" text="圆形" marker="circle" />
              <OrbitGuidePill label="大小" text="节点出现量" marker="scale" />
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export function OrbitGuidePill({
  label,
  text,
  tone = 'neutral',
  marker = 'circle',
}: {
  label: string;
  text: string;
  tone?: 'strong' | 'growth' | 'story' | 'risk' | 'neutral';
  marker?: 'circle' | 'square' | 'scale';
}) {
  const color = orbitGuideToneColor(tone);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 py-1">
      {marker === 'scale' ? (
        <span className="inline-flex h-3 w-4 items-end justify-center gap-0.5" aria-hidden="true">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
        </span>
      ) : (
        <span
          className="h-2.5 w-2.5"
          style={{ background: color, borderRadius: marker === 'square' ? '3px' : '9999px' }}
          aria-hidden="true"
        />
      )}
      <span className="font-medium" style={{ color }}>{label}</span>
      <span>{text}</span>
    </span>
  );
}

export function orbitGuideToneColor(tone: 'strong' | 'growth' | 'story' | 'risk' | 'neutral') {
  if (tone === 'strong') return 'var(--brand-primary)';
  if (tone === 'growth') return 'var(--evidence-opportunity)';
  if (tone === 'risk') return 'var(--evidence-risk)';
  if (tone === 'story') return 'var(--text-tertiary)';
  return 'var(--text-secondary)';
}

export function AssociationNodeFilterBar({
  options,
  activeFilters,
  totalCount,
  visibleCount,
  previewFilter,
  onChange,
  onPreviewChange,
}: {
  options: AssociationNodeFilterOption[];
  activeFilters: AssociationNodeFilterKey[];
  totalCount: number;
  visibleCount: number;
  previewFilter: AssociationNodeFilterKey | null;
  onChange: (filters: AssociationNodeFilterKey[]) => void;
  onPreviewChange: (filter: AssociationNodeFilterKey | null) => void;
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
            ? 'border-[var(--brand-border)] bg-[var(--bg-primary)] text-[var(--text-primary)]'
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
            onMouseEnter={() => onPreviewChange(active ? null : option.key)}
            onMouseLeave={() => onPreviewChange(null)}
            onFocus={() => onPreviewChange(active ? null : option.key)}
            onBlur={() => onPreviewChange(null)}
            onClick={() => toggleFilter(option.key)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${
              active
                ? 'bg-[var(--bg-primary)]'
                : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:border-[var(--brand-border)] hover:text-[var(--brand-primary)]'
            }`}
            style={active
              ? { borderColor: color, color, boxShadow: `inset 0 0 0 1px ${color}` }
              : previewed
                ? { borderColor: color, color, borderStyle: 'dashed' }
                : undefined}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: color }} />
            {option.label} {option.count}
          </button>
        );
      })}
      <span className="ml-auto text-[var(--text-secondary)]">重点标注 {visibleCount} / 全部节点 {totalCount}</span>
    </div>
  );
}

export function AssociationMapModeControl({
  mode,
  riskCount,
  onChange,
}: {
  mode: AssociationMapMode;
  riskCount: number;
  onChange: (mode: AssociationMapMode) => void;
}) {
  return (
    <div className="inline-flex rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1" aria-label="图谱模式">
      <button
        type="button"
        aria-pressed={mode === 'associations'}
        onClick={() => onChange('associations')}
        className={`inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition duration-200 ease-out ${mode === 'associations' ? 'bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-secondary)]'}`}
      >
        <Orbit size={14} strokeWidth={1.8} />
        联想总览
      </button>
      <button
        type="button"
        aria-pressed={mode === 'risk'}
        disabled={!riskCount}
        onClick={() => onChange('risk')}
        className={`inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition duration-200 ease-out disabled:cursor-not-allowed disabled:opacity-45 ${mode === 'risk' ? 'bg-[var(--bg-primary)] text-[var(--evidence-risk)] shadow-sm' : 'text-[var(--text-secondary)]'}`}
      >
        <ShieldAlert size={14} strokeWidth={1.8} />
        风险与竞争 {riskCount}
      </button>
    </div>
  );
}

export function OrbitLiveAnimationStyle() {
  return (
    <style>{`
      .amway-orbit-surface {
        background-color: var(--bg-primary);
        background-image: radial-gradient(circle, color-mix(in srgb, var(--text-tertiary) 15%, transparent) 0 0.7px, transparent 0.8px);
        background-size: 22px 22px;
      }
      .amway-orbit-surface::after {
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        background: linear-gradient(180deg, color-mix(in srgb, var(--bg-primary) 4%, transparent), color-mix(in srgb, var(--brand-bg) 18%, transparent));
        opacity: 0.28;
      }
      @keyframes amwayOrbitLinkDraw {
        from { stroke-dashoffset: 1; opacity: 0.22; }
        to { stroke-dashoffset: 0; }
      }
      .amway-orbit-link-active {
        stroke-dasharray: 1;
        animation: amwayOrbitLinkDraw 360ms cubic-bezier(0.22, 1, 0.36, 1) both;
      }
      @keyframes amwayNodeInsightEnter {
        from { opacity: 0; transform: translateX(18px); }
        to { opacity: 1; transform: translateX(0); }
      }
      .amway-node-insight-enter {
        animation: amwayNodeInsightEnter 260ms cubic-bezier(0.22, 1, 0.36, 1) both;
      }
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
      .amway-orbit-live-node {
        animation: amwayOrbitNodeIn 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
      }
      @keyframes amwayOrbitStartPulse {
        0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--brand-primary) 26%, transparent); }
        55% { box-shadow: 0 0 0 12px transparent; }
      }
      .amway-orbit-start-cta {
        animation: amwayOrbitStartPulse 2.4s ease-out infinite;
      }
      .amway-orbit-node:focus .amway-orbit-node-label {
        opacity: 1 !important;
      }
      .amway-orbit-node::after {
        content: "";
        position: absolute;
        inset: 3px;
        border-radius: 9999px;
        border: 1.5px solid transparent;
        transition: border-color 150ms ease-out;
        pointer-events: none;
      }
      .amway-orbit-node:hover::after,
      .amway-orbit-node:focus-visible::after {
        border-color: var(--border-strong);
      }
      @media (prefers-reduced-motion: reduce) {
        .amway-orbit-live-node {
          animation: none !important;
        }
        .amway-orbit-link-active,
        .amway-node-insight-enter {
          animation: none !important;
        }
      }
    `}</style>
  );
}

export function OrbitTrackBand({
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
        strokeWidth={strokeWidth}
        pointerEvents="none"
        style={{
          strokeOpacity: faded ? 0.025 : active ? 0.18 : 'var(--amway-track-band, 0.07)',
          transition: 'stroke-opacity 220ms cubic-bezier(0.22, 1, 0.36, 1)',
        }}
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
        strokeDasharray={trackLinePattern(track)}
        pointerEvents="none"
        style={{ transition: 'stroke-opacity 220ms cubic-bezier(0.22, 1, 0.36, 1)' }}
      />
    </>
  );
}

export function trackLinePattern(track: AssociationNodeFilterKey) {
  if (track === 'opportunity') return '1.2 0.8';
  if (track === 'watch') return '0.35 0.75';
  return undefined;
}

export function LiveExtractionMapPanel({
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
  const stageLabel = String(currentStage || '').trim().toUpperCase() === 'A5'
    ? '图谱校准中'
    : '平台抓取中';
  return (
    <aside className="absolute left-5 top-5 z-50 w-[min(420px,calc(100%-40px))] rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)]/95 p-4 shadow-md backdrop-blur-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">{stageLabel}</div>
          <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">答案入库后立即抽词，节点同步进入图谱</div>
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--brand-primary)]" aria-hidden="true" />
          运行中
        </div>
      </div>
      {cleanProgress ? (
        <div className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
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
                <span className="font-semibold text-[var(--text-primary)]">{commercialReportCopy(sample.node_term || '新实体')}</span>
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

export function LiveMapMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]/86 px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{value}</div>
    </div>
  );
}

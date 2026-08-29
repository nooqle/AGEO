/**
 * Commercial orbit map canvas UI (knife 4b, zero behavior).
 */

'use client';

import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { ArrowLeft, Play, ShieldAlert } from 'lucide-react';
import type {
  OntologyAssociationCircleEvidence,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleNode,
  OntologyAssociationCircleSourceAppendixItem,
} from '@/types/ontology';
import {
  DEFAULT_OVERVIEW_HIGHLIGHT_LIMIT,
  FOCUSED_TRACK_LABEL_LIMIT,
} from './constants';
import {
  buildLiveExtractionStreamSamples,
  trackFilterToGroupKey,
} from './evidenceHelpers';
import {
  nodeClosenessValue,
  nodeEvidenceCount,
} from './nodeMetrics';
import {
  nodeOriginRead,
  nodeOriginShortLabel,
  relationshipRead,
} from './nodeInsightCopy';
import {
  buildCommercialOrbitEntries,
  buildRiskMapEntries,
  clampNumber,
  nodeAnimationDelay,
  orbitScreenPosition,
} from './orbitLayout';
import {
  LiveExtractionMapPanel,
  OrbitLiveAnimationStyle,
  OrbitTrackBand,
} from './orbitMapChrome';
import {
  orbitFocusedEntry,
  orbitHaloColor,
  orbitNodeFillColor,
  orbitToneColor,
  selectedRelationLineColor,
  scrollOrbitMapIntoView,
} from './orbitMapVisual';
import { OrbitNodeInsightPanel } from './OrbitNodeInsightPanel';
import {
  readLiveExtractionStats,
  sampleAnswerCount,
} from './projection';
import type {
  AssociationMapGroup,
  AssociationMapMode,
  AssociationNodeFilterKey,
} from './types';

export function CommercialOrbitMap({
  centerTerm,
  groups,
  mapMode,
  riskNodes,
  showDefaultRiskNodes,
  evidenceSamples,
  evidenceFindings,
  sourceAppendix,
  strategyTerms,
  sampleScope,
  targetPlatforms,
  liveProgressMessage,
  liveCurrentStage,
  selectedNodeId,
  restoreExternalFocus,
  isLivePreview,
  onSelectNode,
  onOpenRiskView,
  onExitRiskView,
  onStartRun,
  activeTrackFilter,
  hoverTrackFilter,
}: {
  centerTerm: string;
  groups: AssociationMapGroup[];
  mapMode: AssociationMapMode;
  riskNodes: OntologyAssociationCircleNode[];
  showDefaultRiskNodes: boolean;
  evidenceSamples: OntologyAssociationCircleEvidence[];
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  strategyTerms: string[];
  sampleScope: Record<string, unknown>;
  targetPlatforms: string[];
  liveProgressMessage?: string | null;
  liveCurrentStage?: string | null;
  selectedNodeId: string | null;
  restoreExternalFocus: () => boolean;
  isLivePreview?: boolean;
  onSelectNode: (nodeId: string | null) => void;
  onOpenRiskView: () => void;
  onExitRiskView: () => void;
  onStartRun?: () => void;
  activeTrackFilter: AssociationNodeFilterKey | null;
  hoverTrackFilter: AssociationNodeFilterKey | null;
}) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const [mapSize, setMapSize] = useState({ width: 1440, height: 680 });
  useEffect(() => {
    const element = mapRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setMapSize({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const collisionXScale = Math.min(1, mapSize.height / Math.max(1, mapSize.width));
  const collisionMinGap = clampNumber(4800 / Math.max(1, mapSize.height), 7, 13);
  const entries = mapMode === 'risk'
    ? buildRiskMapEntries(riskNodes)
    : buildCommercialOrbitEntries(
        groups,
        showDefaultRiskNodes ? riskNodes : [],
        collisionXScale,
        collisionMinGap,
      );
  const isRiskMode = mapMode === 'risk';
  const showStartCta = !isRiskMode && !isLivePreview && entries.length === 0 && Boolean(onStartRun);
  const trackBandFocusFilter = activeTrackFilter || hoverTrackFilter;
  const focusTrackFilter = activeTrackFilter;
  const focusGroupKey = trackFilterToGroupKey(activeTrackFilter);
  const selectedFocusNodeId = selectedNodeId || null;
  const selectedEntry = selectedNodeId
    ? entries.find((entry) => entry.node.node_id === selectedNodeId) || null
    : null;
  const overviewHighlightedNodeIds = new Set(
    [...entries]
      .sort((left, right) => (
        nodeEvidenceCount(right.node) * 2 + nodeClosenessValue(right.node)
        - nodeEvidenceCount(left.node) * 2 - nodeClosenessValue(left.node)
      ))
      .slice(0, DEFAULT_OVERVIEW_HIGHLIGHT_LIMIT)
      .map((entry) => entry.node.node_id),
  );
  const focusedTrackLabelNodeIds = new Set(
    focusGroupKey
      ? entries
          .filter((entry) => entry.groupKey === focusGroupKey)
          .sort((left, right) => (
            nodeEvidenceCount(right.node) * 2 + nodeClosenessValue(right.node)
            - nodeEvidenceCount(left.node) * 2 - nodeClosenessValue(left.node)
          ))
          .slice(0, focusGroupKey === 'strong' ? undefined : FOCUSED_TRACK_LABEL_LIMIT)
          .map((entry) => entry.node.node_id)
      : [],
  );
  const [keyboardNodeId, setKeyboardNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const keyboardEntryIds = entries
    .filter((entry) => {
      const trackFocused = orbitFocusedEntry(entry, focusGroupKey);
      const mutedByTrack = Boolean(focusTrackFilter) && !trackFocused;
      return !mutedByTrack;
    })
    .map((entry) => entry.node.node_id);
  const activeKeyboardNodeId = keyboardEntryIds.includes(keyboardNodeId || '')
    ? keyboardNodeId
    : selectedFocusNodeId && keyboardEntryIds.includes(selectedFocusNodeId)
      ? selectedFocusNodeId
      : keyboardEntryIds[0] || null;
  const moveKeyboardFocus = (currentNodeId: string, direction: number | 'first' | 'last') => {
    const currentIndex = Math.max(0, keyboardEntryIds.indexOf(currentNodeId));
    const nextIndex = direction === 'first'
      ? 0
      : direction === 'last'
        ? keyboardEntryIds.length - 1
        : (currentIndex + direction + keyboardEntryIds.length) % keyboardEntryIds.length;
    const nextNodeId = keyboardEntryIds[nextIndex];
    if (!nextNodeId) return;
    setKeyboardNodeId(nextNodeId);
    window.requestAnimationFrame(() => {
      const buttons = mapRef.current?.querySelectorAll<HTMLButtonElement>('[data-amway-orbit-node="true"]');
      Array.from(buttons || []).find((button) => button.dataset.nodeId === nextNodeId)?.focus();
    });
  };
  const canvasWidthPercent = selectedEntry ? 64 : 100;
  const associationXScale = Math.min(
    1,
    mapSize.height / Math.max(1, mapSize.width * canvasWidthPercent / 100),
  );
  const selectedNodeForInsight = selectedEntry?.node || null;
  const selectedNodeTriggerRef = useRef<HTMLButtonElement | null>(null);
  const closeNodeInsight = () => {
    const mapFocusTarget = selectedNodeTriggerRef.current;
    onSelectNode(null);
    window.requestAnimationFrame(() => {
      if (!restoreExternalFocus()) mapFocusTarget?.focus();
    });
  };
  const liveStats = readLiveExtractionStats(sampleScope);
  const liveSamples = isLivePreview
    ? buildLiveExtractionStreamSamples(sourceAppendix, evidenceSamples).slice(0, 4)
    : [];
  const renderedEntries = entries.map((entry) => {
    const selected = selectedNodeId === entry.node.node_id;
    const focused = entry.node.node_id === selectedFocusNodeId;
    const trackFocused = orbitFocusedEntry(entry, focusGroupKey);
    const mutedByTrack = Boolean(focusTrackFilter) && !trackFocused;
    const mutedByOverview = !isRiskMode
      && !focusTrackFilter
      && !focused
      && !overviewHighlightedNodeIds.has(entry.node.node_id);
    const origin = nodeOriginRead(entry.node, strategyTerms);
    const position = orbitScreenPosition(entry, associationXScale, isRiskMode);
    const labelVisible = focusGroupKey
      ? focusedTrackLabelNodeIds.has(entry.node.node_id)
      : entry.labelPriority;
    const labelShown = !mutedByTrack && (
      focused
      || labelVisible
      || hoveredNodeId === entry.node.node_id
      || keyboardNodeId === entry.node.node_id
    );
    return {
      entry,
      selected,
      focused,
      trackFocused,
      mutedByTrack,
      mutedByOverview,
      origin,
      position,
      labelShown,
    };
  });
  return (
    <div
      ref={mapRef}
      data-amway-orbit-map="true"
      className="amway-orbit-surface relative min-h-[380px] overflow-hidden lg:min-h-[640px] 2xl:min-h-[680px]"
    >
      <OrbitLiveAnimationStyle />
      <p className="sr-only">图谱重点节点可用方向键、Home 和 End 键移动。</p>
      <svg
        className="pointer-events-none absolute inset-y-0 left-0 h-full"
        style={{ width: `${canvasWidthPercent}%` }}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {isRiskMode ? (
          <>
            <line
              x1="50"
              y1="30"
              x2="50"
              y2="61"
              stroke="var(--error)"
              strokeWidth={selectedFocusNodeId ? 0.42 : 0.28}
              strokeDasharray={selectedFocusNodeId ? undefined : '1.2 1.2'}
              opacity={selectedFocusNodeId ? 0.86 : 0.62}
            />
            {entries.map((entry) => (
              <line
                key={`risk-link-${entry.node.node_id}`}
                className={entry.node.node_id === selectedFocusNodeId ? 'amway-orbit-link-active' : undefined}
                pathLength="1"
                x1="50"
                y1="61"
                x2={entry.left}
                y2={entry.top}
                stroke="var(--error)"
                strokeWidth={entry.node.node_id === selectedFocusNodeId ? 0.4 : 0.17}
                strokeDasharray={entry.node.node_id === selectedFocusNodeId ? undefined : '0.8 1.2'}
                opacity={entry.node.node_id === selectedFocusNodeId ? 0.82 : 0.12}
              />
            ))}
          </>
        ) : (
          <>
            <ellipse cx="50" cy="50" rx={22 * associationXScale} ry="22" fill="var(--brand-bg)" fillOpacity="0.42" stroke="var(--brand-border)" strokeWidth="0.18" pointerEvents="none" />
            <OrbitTrackBand
              track="watch"
              rx={47 * associationXScale}
              ry={47}
              strokeWidth={4.2}
              focusTrackFilter={trackBandFocusFilter}
            />
            <OrbitTrackBand
              track="opportunity"
              rx={35 * associationXScale}
              ry={35}
              strokeWidth={3.8}
              focusTrackFilter={trackBandFocusFilter}
            />
            <OrbitTrackBand
              track="stable"
              rx={24 * associationXScale}
              ry={24}
              strokeWidth={3.4}
              focusTrackFilter={trackBandFocusFilter}
            />
            {entries.map((entry) => {
              const position = orbitScreenPosition(entry, associationXScale, false);
              return (
                <line
                  key={`ray-${entry.node.node_id}`}
                  className={entry.node.node_id === selectedFocusNodeId ? 'amway-orbit-link-active' : undefined}
                  pathLength="1"
                  x1="50"
                  y1="50"
                  x2={position.left}
                  y2={position.top}
                  stroke={entry.node.node_id === selectedFocusNodeId ? selectedRelationLineColor(entry.groupKey) : 'transparent'}
                  strokeWidth={entry.node.node_id === selectedFocusNodeId ? 0.34 : 0}
                  opacity={entry.node.node_id === selectedFocusNodeId ? 0.72 : 0}
                  pointerEvents="none"
                />
              );
            })}
          </>
        )}
      </svg>
      <button
        type="button"
        onClick={showStartCta ? onStartRun : isRiskMode ? onExitRiskView : () => onSelectNode(null)}
        title={showStartCta ? '设置并运行图谱采集' : isRiskMode ? '退出风险聚焦' : '点击取消节点选中'}
        className={`absolute z-20 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border-2 border-[var(--brand-primary)] bg-[var(--brand-bg)] text-center shadow-sm transition duration-200 ease-out hover:border-[var(--brand-hover)] hover:shadow-[0_0_0_8px_var(--brand-bg)] ${
          isRiskMode ? 'top-[30%] h-32 w-32' : 'top-1/2 h-40 w-40'
        }`}
        style={{ left: `${canvasWidthPercent / 2}%` }}
      >
        {showStartCta ? (
          <>
            <span className="amway-orbit-start-cta flex h-14 w-14 items-center justify-center rounded-full bg-[var(--brand-primary)] text-[var(--brand-contrast)]">
              <Play size={22} fill="currentColor" aria-hidden="true" />
            </span>
            <span className="mt-2.5 text-sm font-semibold text-[var(--brand-primary)]">开始运行</span>
          </>
        ) : (
          <>
            <span className="text-xs text-[var(--brand-primary)]">中心品牌</span>
            <span className="mt-2 text-3xl font-semibold tracking-tight text-[var(--brand-primary)]">{centerTerm}</span>
          </>
        )}
      </button>
      {isRiskMode ? (
        <>
          <div
            aria-label={`风险与竞争中心，${riskNodes.length} 个节点`}
            className="absolute top-[61%] z-20 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 select-none flex-col items-center justify-center rounded-full border-2 border-[var(--error)] bg-[var(--bg-primary)] text-center text-[var(--error)] shadow-sm"
            style={{ left: `${canvasWidthPercent / 2}%` }}
          >
            <span className="text-xs">风险与竞争</span>
            <span className="mt-1 text-2xl font-semibold">{riskNodes.length}</span>
            <span className="mt-1 text-[11px] text-[var(--text-tertiary)]">个节点</span>
          </div>
          <button
            type="button"
            onClick={onExitRiskView}
            className="absolute right-5 top-5 z-40 inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3.5 py-2 text-sm font-semibold text-[var(--text-secondary)] shadow-sm transition duration-200 ease-out hover:border-[var(--brand-border)] hover:text-[var(--brand-primary)]"
            style={selectedNodeForInsight ? { right: 'calc(min(520px, 36vw) + 1.25rem)' } : undefined}
          >
            <ArrowLeft size={15} strokeWidth={1.8} />
            退出风险聚焦
          </button>
        </>
      ) : (
        <>
          {riskNodes.length ? (
            <button
              type="button"
              onClick={onOpenRiskView}
              className={`absolute left-[15%] top-[74%] flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 rounded-full border border-[var(--error)] bg-[var(--bg-elevated)] px-3.5 py-2 text-xs font-semibold text-[var(--error)] shadow-sm transition duration-200 ease-out hover:-translate-y-[54%] hover:shadow-md ${
                focusTrackFilter ? 'z-10 opacity-25 saturate-50' : 'z-30 opacity-100'
              }`}
              title={`聚焦查看 ${riskNodes.length} 个风险与竞争节点`}
            >
              <ShieldAlert size={13} strokeWidth={2} aria-hidden="true" />
              风险与竞争 {riskNodes.length}
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
        onClose={closeNodeInsight}
      />
      {renderedEntries.length ? renderedEntries.map((renderedEntry) => {
        const {
          entry,
          selected,
          focused,
          trackFocused,
          mutedByTrack,
          mutedByOverview,
          origin,
          position,
        } = renderedEntry;
        return (
          <button
            key={entry.node.node_id}
            type="button"
            data-amway-orbit-node="true"
            data-node-id={entry.node.node_id}
            tabIndex={mutedByTrack || entry.node.node_id !== activeKeyboardNodeId ? -1 : 0}
            aria-hidden={mutedByTrack ? true : undefined}
            aria-label={entry.node.term}
            onFocus={(event) => {
              selectedNodeTriggerRef.current = event.currentTarget;
              setKeyboardNodeId(entry.node.node_id);
            }}
            onMouseEnter={() => setHoveredNodeId(entry.node.node_id)}
            onMouseLeave={() => setHoveredNodeId(null)}
            onKeyDown={(event) => {
              const direction = event.key === 'ArrowRight' || event.key === 'ArrowDown'
                ? 1
                : event.key === 'ArrowLeft' || event.key === 'ArrowUp'
                  ? -1
                  : event.key === 'Home'
                    ? 'first'
                    : event.key === 'End'
                      ? 'last'
                      : null;
              if (direction === null) return;
              event.preventDefault();
              moveKeyboardFocus(entry.node.node_id, direction);
            }}
            onClick={(event) => {
              selectedNodeTriggerRef.current = event.currentTarget;
              onSelectNode(entry.node.node_id);
              scrollOrbitMapIntoView(event.currentTarget);
            }}
            className={`amway-orbit-node group absolute z-30 rounded-full transition-[width,height,transform,opacity,filter] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:z-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--brand-primary)] ${
              focusTrackFilter ? 'h-8 w-8' : 'h-11 w-11'
            } ${
              selected
                ? isRiskMode
                  ? 'ring-2 ring-[var(--error)] ring-offset-2 ring-offset-[var(--bg-secondary)]'
                  : 'ring-2 ring-[var(--brand-border)] ring-offset-2 ring-offset-[var(--bg-secondary)]'
                : ''
            } ${mutedByTrack ? 'pointer-events-none' : ''} ${isLivePreview ? 'amway-orbit-live-node' : ''}`}
            style={{
              left: `${position.left * canvasWidthPercent / 100}%`,
              top: `${position.top}%`,
              zIndex: mutedByTrack || mutedByOverview
                ? 10
                : selected
                  ? 40
                  : 30,
              transform: `translate(-50%, -50%) scale(${selected ? 1.06 : 1})`,
              animationDelay: isLivePreview ? `${nodeAnimationDelay(entry.node.node_id)}ms` : undefined,
              opacity: mutedByTrack ? 0.14 : mutedByOverview ? 0.12 : 1,
              ...(selected && !isRiskMode
                ? { '--tw-ring-color': orbitToneColor(entry.groupKey) } as CSSProperties
                : {}),
            }}
            title={`${entry.node.term}：${relationshipRead(entry.node).headline}`}
          >
            <span
              className="pointer-events-none absolute left-1/2 top-1/2 rounded-full shadow-sm transition-[box-shadow,opacity,transform] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:shadow-md"
              style={{
                transform: 'translate(-50%, -50%)',
                width: entry.size,
                height: entry.size,
                borderRadius: origin.kind === 'strategy' ? '28%' : '9999px',
                background: focused
                  ? orbitToneColor(entry.groupKey)
                  : orbitNodeFillColor(entry, focusGroupKey),
                opacity: focused || trackFocused ? 1 : 0.76,
                boxShadow: focused
                  ? `0 0 0 8px ${orbitHaloColor(entry.groupKey)}`
                  : undefined,
              }}
            />
          </button>
        );
      }) : null}
      <div
        aria-hidden="true"
        data-amway-orbit-label-layer="true"
        className="pointer-events-none absolute inset-0 z-[45]"
      >
        {renderedEntries.map(({ entry, focused, origin, position, labelShown }) => {
          const labelOffset = focusTrackFilter ? 22 : 28;
          const labelHeightEstimate = 32;
          const labelAbove = position.top > (
            (mapSize.height - labelOffset - labelHeightEstimate) / Math.max(1, mapSize.height) * 100
          );
          return (
            <span
              key={`label-${entry.node.node_id}`}
              className={`amway-orbit-node-label absolute inline-flex min-w-max -translate-x-1/2 items-center gap-1.5 rounded-full border bg-[var(--bg-elevated)] px-2.5 py-1 text-xs font-medium shadow-sm transition duration-200 hidden sm:inline-flex ${
                labelAbove ? '-translate-y-full' : ''
              } ${labelShown ? 'opacity-100' : 'opacity-0'}`}
              style={{
                left: `${position.left * canvasWidthPercent / 100}%`,
                top: labelAbove
                  ? `calc(${position.top}% - ${labelOffset}px)`
                  : `calc(${position.top}% + ${labelOffset}px)`,
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
          );
        })}
      </div>
    </div>
  );
}

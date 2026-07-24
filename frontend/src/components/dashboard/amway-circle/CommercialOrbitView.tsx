/**
 * Commercial orbit view composition shell (knife 4c, zero behavior).
 */

'use client';

import { useRef, useState } from 'react';
import type {
  OntologyAssociationCircleEvidence,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleNode,
  OntologyAssociationCirclePrioritySummary,
  OntologyAssociationCircleSourceAppendixItem,
} from '@/types/ontology';
import { DEFAULT_OVERVIEW_HIGHLIGHT_LIMIT, platformLabel } from './constants';
import { CommercialOrbitMap } from './CommercialOrbitMap';
import {
  buildAssociationNodeFilterOptions,
  groupKeyToTrackFilter,
  nodePassesAssociationFilters,
  trackFilterToGroupKey,
  uniqueStrings,
} from './evidenceHelpers';
import { classifyAssociationNode } from './mapGroups';
import {
  AssociationMapModeControl,
  AssociationNodeFilterBar,
  LiveExtractionStatusStrip,
  OrbitMapLegend,
  PriorityFocusStrip,
} from './orbitMapChrome';
import { readLiveExtractionStats } from './projection';
import type {
  AssociationMapGroup,
  AssociationMapMode,
  AssociationNodeFilterKey,
} from './types';

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
  onStartRun,
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
  onStartRun?: () => void;
}) {
  const [mapMode, setMapMode] = useState<AssociationMapMode>('associations');
  const [activeNodeFilters, setActiveNodeFilters] = useState<AssociationNodeFilterKey[]>([]);
  const [hoverTrackFilter, setHoverTrackFilter] = useState<AssociationNodeFilterKey | null>(null);
  const externalReturnFocusRef = useRef<HTMLButtonElement | null>(null);
  const autoFocusedTrackRef = useRef(false);
  const riskGroup = groups.find((group) => group.key === 'risk') || null;
  const riskNodes = riskGroup?.nodes || [];
  const associationGroups = groups.filter((group) => group.key !== 'risk');
  const showDefaultRiskNodes = mapMode === 'associations' && activeNodeFilters.length === 0;
  const filterOptions = buildAssociationNodeFilterOptions(associationGroups);
  const activeTrackFilter = activeNodeFilters[0] || null;
  const activeTrackGroupKey = trackFilterToGroupKey(activeTrackFilter);
  const focusGroups = mapMode === 'risk'
    ? (riskGroup ? [riskGroup] : [])
    : activeTrackGroupKey
      ? associationGroups.filter((group) => group.key === activeTrackGroupKey)
      : associationGroups;
  const strongest = focusGroups.find((group) => group.key === 'strong')?.nodes[0] || null;
  const opportunity = focusGroups.find((group) => group.key === 'growth')?.nodes[0] || focusGroups.find((group) => group.key === 'story')?.nodes[0] || null;
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
  const visibleNodeCount = activeTrackFilter
    ? trackCounts[activeTrackFilter]
    : Math.min(totalDefaultNodeCount, DEFAULT_OVERVIEW_HIGHLIGHT_LIMIT);
  const updateNodeFilters = (nextFilters: AssociationNodeFilterKey[]) => {
    autoFocusedTrackRef.current = false;
    setHoverTrackFilter(null);
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
    autoFocusedTrackRef.current = false;
    setMapMode('associations');
    setHoverTrackFilter(null);
    setActiveNodeFilters([]);
    onSelectNode(null);
  };
  const openRiskView = () => {
    autoFocusedTrackRef.current = false;
    setMapMode('risk');
    setHoverTrackFilter(null);
    setActiveNodeFilters([]);
    onSelectNode(null);
  };
  const revealNode = (nodeId: string | null, returnFocusTarget?: HTMLButtonElement) => {
    if (!nodeId) {
      if (autoFocusedTrackRef.current) {
        setActiveNodeFilters([]);
        setHoverTrackFilter(null);
        autoFocusedTrackRef.current = false;
      }
      onSelectNode(null);
      return;
    }
    const node = groups.flatMap((group) => group.nodes).find((item) => item.node_id === nodeId);
    if (!node) return;
    externalReturnFocusRef.current = returnFocusTarget || null;
    const groupKey = classifyAssociationNode(node);
    setHoverTrackFilter(null);
    if (groupKey === 'risk') {
      setMapMode('risk');
      setActiveNodeFilters([]);
      autoFocusedTrackRef.current = false;
    } else if (returnFocusTarget) {
      setMapMode('associations');
      setActiveNodeFilters([groupKeyToTrackFilter(groupKey)]);
      autoFocusedTrackRef.current = true;
    }
    onSelectNode(nodeId);
  };

  return (
    <section className="space-y-5">
      <section className="space-y-5">
        <div className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold tracking-tight">
                  {mapMode === 'risk' ? `${centerTerm} 风险与竞争关系图` : `${centerTerm} 品牌联想圈层图`}
                </h2>
                <OrbitMapLegend mapMode={mapMode} />
              </div>
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
              {mapMode === 'associations' && totalAssociationNodeCount > 0 ? (
                <AssociationNodeFilterBar
                  options={filterOptions}
                  activeFilters={activeNodeFilters}
                  totalCount={totalDefaultNodeCount}
                  visibleCount={visibleNodeCount}
                  previewFilter={hoverTrackFilter}
                  onChange={updateNodeFilters}
                  onPreviewChange={setHoverTrackFilter}
                />
              ) : null}
            </div>
            <div className="flex flex-col items-end gap-2">
              <AssociationMapModeControl
                mode={mapMode}
                riskCount={riskNodes.length}
                onChange={(mode) => mode === 'risk' ? openRiskView() : closeRiskView()}
              />
            </div>
          </div>
          <CommercialOrbitMap
            centerTerm={centerTerm}
            groups={mapMode === 'risk' ? (riskGroup ? [riskGroup] : []) : associationGroups}
            mapMode={mapMode}
            riskNodes={riskNodes}
            showDefaultRiskNodes={showDefaultRiskNodes}
            evidenceSamples={evidenceSamples}
            evidenceFindings={evidenceFindings}
            sourceAppendix={sourceAppendix}
            strategyTerms={strategyTerms}
            sampleScope={sampleScope}
            targetPlatforms={targetPlatformNames}
            liveProgressMessage={liveProgressMessage}
            liveCurrentStage={liveCurrentStage}
            selectedNodeId={focusNode?.node_id === selectedNodeId ? selectedNodeId : null}
            restoreExternalFocus={() => {
              if (!externalReturnFocusRef.current?.isConnected) return false;
              externalReturnFocusRef.current.focus();
              return true;
            }}
            isLivePreview={isLivePreview}
            onSelectNode={revealNode}
            onOpenRiskView={openRiskView}
            onExitRiskView={closeRiskView}
            onStartRun={onStartRun}
            activeTrackFilter={activeTrackFilter}
            hoverTrackFilter={hoverTrackFilter}
          />
          <PriorityFocusStrip
            summary={prioritySummary}
            groups={groups}
            onSelectNode={revealNode}
          />
        </div>
      </section>
    </section>
  );
}

/**
 * Pure orbit layout geometry for association-circle map (knife 2, zero behavior).
 * Extracted from AmwayAssociationCircleDashboardViews.
 */

import type { OntologyAssociationCircleNode } from '@/types/ontology';
import {
  isCompetitorNode,
  nodeClosenessValue,
  nodeDistanceValue,
  nodeEvidenceCount,
  nodePlatformCount,
} from './nodeMetrics';
import type {
  AssociationMapGroup,
  AssociationMapGroupKey,
  CommercialOrbitEntry,
  OrbitDistanceBand,
} from './types';

export function orbitScreenPosition(
  entry: CommercialOrbitEntry,
  associationXScale: number,
  isRiskMode: boolean,
) {
  if (isRiskMode) return { left: entry.left, top: entry.top };
  return {
    left: 50 + (entry.left - 50) * associationXScale,
    top: entry.top,
  };
}

export function buildCommercialOrbitEntries(
  groups: AssociationMapGroup[],
  defaultRiskNodes: OntologyAssociationCircleNode[] = [],
  associationXScale = 1,
  collisionMinGap = 6.2,
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
  const layoutEntries = [...rawEntries].sort((left, right) => (
    nodeEvidenceCount(right.node) * 2 + nodeClosenessValue(right.node)
    - nodeEvidenceCount(left.node) * 2 - nodeClosenessValue(left.node)
  ));
  const totalEntries = Math.max(layoutEntries.length, 1);
  const defaultLabels = new Set(
    layoutEntries
      .slice(0, 16)
      .map((entry) => entry.node),
  );
  const entries = layoutEntries.map(({ node, groupKey, groupIndex }, index) => {
    const angle = orbitDistributedAngle(groupKey, index, groupIndex, totalEntries);
    const distanceBand = orbitDistanceBandForNode(groupKey, node);
    const radius = orbitRadiusForNode(distanceBand, node, groupIndex);
    const radians = (angle * Math.PI) / 180;
    const size = nodeVisualSize(node, groupKey);
    return {
      node,
      groupKey,
      distanceBand,
      left: clampNumber(50 + Math.cos(radians) * radius, 2, 98),
      top: clampNumber(50 + Math.sin(radians) * radius, 2, 98),
      angle,
      radius,
      size,
      labelPriority: defaultLabels.has(node),
    };
  });
  return separateOrbitEntries(entries, {
    minGap: collisionMinGap,
    maxIterations: 18,
    leftBounds: [2, 98],
    topBounds: [2, 98],
    xScale: associationXScale,
  });
}

export function buildRiskMapEntries(riskNodes: OntologyAssociationCircleNode[]): CommercialOrbitEntry[] {
  const total = Math.max(riskNodes.length, 1);
  const sideCount = Math.ceil(total / 2);
  const defaultLabels = new Set(
    [...riskNodes]
      .sort((left, right) => nodeEvidenceCount(right) - nodeEvidenceCount(left))
      .slice(0, 16),
  );
  const entries: CommercialOrbitEntry[] = riskNodes.map((node, index) => {
    const side = index % 2 === 0 ? -1 : 1;
    const row = Math.floor(index / 2);
    const progress = sideCount > 1 ? row / (sideCount - 1) : 0.5;
    const horizontalOffset = 29 + Math.sin(progress * Math.PI) * 5;
    const angle = side < 0 ? 180 : 0;
    const radius = horizontalOffset;
    return {
      node,
      groupKey: 'risk',
      distanceBand: 'risk',
      left: clampNumber(50 + side * horizontalOffset, 8, 92),
      top: clampNumber(33 + progress * 52, 30, 87),
      angle,
      radius,
      size: 13 + Math.min(18, Math.max(0, nodeEvidenceCount(node) / 2.6)),
      labelPriority: defaultLabels.has(node),
    };
  });
  return separateOrbitEntries(entries, {
    minGap: 6.2,
    maxIterations: 10,
    leftBounds: [7, 93],
    topBounds: [29, 88],
  });
}

export function orbitDistributedAngle(
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

export function orbitGroupAngleOffset(groupKey: AssociationMapGroupKey) {
  if (groupKey === 'strong') return -88;
  if (groupKey === 'growth') return 12;
  if (groupKey === 'story') return 76;
  return 0;
}

export function orbitAngleNudge(groupKey: AssociationMapGroupKey, index: number) {
  if (groupKey === 'growth') return [-7, 5, -3, 7][index % 4];
  if (groupKey === 'strong') return [-5, 5, 0, 2][index % 4];
  if (groupKey === 'risk') return [-4, 4, 0][index % 3];
  return [4, -4, 0, -2][index % 4];
}

export function orbitDistanceBandForNode(groupKey: AssociationMapGroupKey, node: OntologyAssociationCircleNode): OrbitDistanceBand {
  if (groupKey === 'risk') return 'risk';
  if (groupKey === 'strong') return 'near';
  if (groupKey === 'growth') return 'bridge';
  if (groupKey === 'story') return 'far';
  const distance = nodeVisualDistanceValue(node);
  if (distance > 0) {
    if (distance <= 35) return 'near';
    if (distance <= 65) return 'bridge';
    return 'far';
  }
  return 'far';
}

export function orbitRadiusForNode(distanceBand: OrbitDistanceBand, node: OntologyAssociationCircleNode, index: number) {
  const distance = effectiveDistanceForBand(node, distanceBand);
  const lane = distanceBand === 'risk' ? orbitRadiusLane(distanceBand, index) : 0;
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
    return clampNumber(scaleDistanceToRadius(distance, 0, 35, 22.8, 24.8) + lane, 21.4, 26.4);
  }
  if (distanceBand === 'bridge') {
    return clampNumber(scaleDistanceToRadius(distance, 36, 65, 33.5, 36.2) + lane, 32.2, 37.8);
  }
  if (distanceBand === 'far') {
    return clampNumber(scaleDistanceToRadius(distance, 66, 100, 44.5, 47.2) + lane, 43, 49.4);
  }
  return 31;
}

export function orbitRadiusLane(distanceBand: OrbitDistanceBand, index: number) {
  if (distanceBand === 'near') return [-1.2, 1.2, 0, -2, 2][index % 5];
  if (distanceBand === 'bridge') return [-1.4, 1.4, 0, -2.2, 2.2][index % 5];
  if (distanceBand === 'far') return [-1.7, 1.7, 0, -2.6, 2.6][index % 5];
  return [-2.5, 2.5, 0, -4, 4][index % 5];
}

export function separateOrbitEntries(
  entries: CommercialOrbitEntry[],
  options: {
    minGap: number;
    maxIterations: number;
    leftBounds: [number, number];
    topBounds: [number, number];
    xScale?: number;
  },
) {
  const placed: CommercialOrbitEntry[] = [];
  entries.forEach((entry) => {
    let next = constrainOrbitEntryToBand({ ...entry }, options.leftBounds, options.topBounds);
    for (let attempt = 0; attempt < options.maxIterations; attempt += 1) {
      let adjusted = false;
      placed.forEach((previous) => {
        const distance = orbitEntryDistance(next, previous, options.xScale);
        const requiredGap = orbitEntryRequiredGap(next, previous, options.minGap);
        if (distance >= requiredGap) return;
        const fallbackAngle = ((placed.length + attempt + 1) * 43 * Math.PI) / 180;
        const xScale = options.xScale || 1;
        const dx = (next.left - previous.left) * xScale || Math.cos(fallbackAngle);
        const dy = next.top - previous.top || Math.sin(fallbackAngle);
        const length = Math.max(0.01, Math.sqrt(dx * dx + dy * dy));
        const push = requiredGap - distance + 0.55;
        const nextLeft = clampNumber(
          next.left + (dx / length) * push / xScale,
          options.leftBounds[0],
          options.leftBounds[1],
        );
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
        next = constrainOrbitEntryToBand(next, options.leftBounds, options.topBounds);
        adjusted = true;
      });
      if (!adjusted) break;
    }
    if (placed.some((previous) => orbitEntriesCollide(next, previous, options.minGap, options.xScale))) {
      next = findOpenOrbitPosition(next, placed, options);
    }
    placed.push(next);
  });
  return placed;
}

export function findOpenOrbitPosition(
  entry: CommercialOrbitEntry,
  placed: CommercialOrbitEntry[],
  options: {
    minGap: number;
    leftBounds: [number, number];
    topBounds: [number, number];
    xScale?: number;
  },
) {
  const angleOffsets = [
    0, 9, -9, 18, -18, 27, -27, 36, -36, 54, -54, 72, -72, 96, -96, 126, -126, 162, -162, 180,
  ];
  const radiusOffsets = orbitFallbackRadiusOffsets(entry.distanceBand);
  let best = entry;
  let bestScore = orbitPositionScore(entry, placed, options.minGap, options.xScale);
  angleOffsets.forEach((angleOffset) => {
    radiusOffsets.forEach((radiusOffset) => {
      const angle = entry.angle + angleOffset;
      const [minRadius, maxRadius] = orbitRadiusBoundsForBand(entry.distanceBand);
      const radius = clampNumber(entry.radius + radiusOffset, minRadius, maxRadius);
      const radians = (angle * Math.PI) / 180;
      const centerTop = entry.distanceBand === 'risk' ? 57 : 50;
      const candidate = constrainOrbitEntryToBand({
        ...entry,
        angle,
        radius,
        left: clampNumber(50 + Math.cos(radians) * radius, options.leftBounds[0], options.leftBounds[1]),
        top: clampNumber(centerTop + Math.sin(radians) * radius, options.topBounds[0], options.topBounds[1]),
      }, options.leftBounds, options.topBounds);
      const score = orbitPositionScore(candidate, placed, options.minGap, options.xScale);
      if (score > bestScore) {
        best = candidate;
        bestScore = score;
      }
    });
  });
  return best;
}

export function orbitFallbackRadiusOffsets(distanceBand: OrbitDistanceBand) {
  if (distanceBand === 'near') return [0, -1.2, 1.2, -2.4, 2.4];
  if (distanceBand === 'bridge') return [0, -1.4, 1.4, -2.8, 2.8];
  if (distanceBand === 'far') return [0, -1.6, 1.6, -3.2, 3.2];
  return [0, -3, 3, -5, 5];
}

export function orbitRadiusBoundsForBand(distanceBand: OrbitDistanceBand): [number, number] {
  if (distanceBand === 'near') return [21.4, 26.4];
  if (distanceBand === 'bridge') return [32.2, 37.8];
  if (distanceBand === 'far') return [43, 49.4];
  if (distanceBand === 'risk') return [40, 52];
  return [12, 51];
}

export function constrainOrbitEntryToBand(
  entry: CommercialOrbitEntry,
  leftBounds: [number, number],
  topBounds: [number, number],
): CommercialOrbitEntry {
  const centerTop = entry.distanceBand === 'risk' ? 57 : 50;
  const dx = entry.left - 50;
  const dy = entry.top - centerTop;
  const currentRadius = Math.sqrt(dx * dx + dy * dy);
  const [minRadius, maxRadius] = orbitRadiusBoundsForBand(entry.distanceBand);
  const radius = clampNumber(entry.radius, minRadius, maxRadius);
  const radians = currentRadius > 0 ? Math.atan2(dy, dx) : (entry.angle * Math.PI) / 180;
  return {
    ...entry,
    angle: (radians * 180) / Math.PI,
    radius,
    left: clampNumber(50 + Math.cos(radians) * radius, leftBounds[0], leftBounds[1]),
    top: clampNumber(centerTop + Math.sin(radians) * radius, topBounds[0], topBounds[1]),
  };
}

export function orbitPositionScore(
  entry: CommercialOrbitEntry,
  placed: CommercialOrbitEntry[],
  minGap: number,
  xScale = 1,
) {
  if (!placed.length) return Number.POSITIVE_INFINITY;
  return placed.reduce((score, previous) => {
    const requiredGap = orbitEntryRequiredGap(entry, previous, minGap);
    const distance = orbitEntryDistance(entry, previous, xScale);
    return Math.min(score, distance / requiredGap);
  }, Number.POSITIVE_INFINITY);
}

export function orbitEntriesCollide(
  left: CommercialOrbitEntry,
  right: CommercialOrbitEntry,
  minGap: number,
  xScale = 1,
) {
  return orbitEntryDistance(left, right, xScale) < orbitEntryRequiredGap(left, right, minGap);
}

export function orbitEntryDistance(left: CommercialOrbitEntry, right: CommercialOrbitEntry, xScale = 1) {
  const dx = (left.left - right.left) * xScale;
  const dy = left.top - right.top;
  return Math.sqrt(dx * dx + dy * dy);
}

export function orbitEntryRequiredGap(left: CommercialOrbitEntry, right: CommercialOrbitEntry, minGap: number) {
  const sameGroupGap = left.groupKey === right.groupKey ? 0.45 : 0;
  const labelGap = left.labelPriority || right.labelPriority ? 0.95 : 0;
  const sizeGap = Math.min(1.1, (left.size + right.size) / 46);
  return minGap + sameGroupGap + labelGap + sizeGap;
}

export function effectiveDistanceForBand(node: OntologyAssociationCircleNode, distanceBand: OrbitDistanceBand) {
  const distance = nodeVisualDistanceValue(node);
  if (distance > 0) return distance;
  if (distanceBand === 'near') return 24;
  if (distanceBand === 'bridge') return 50;
  if (distanceBand === 'far') return 78;
  return 50;
}

export function scaleDistanceToRadius(
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

export function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function nodeAnimationDelay(nodeId?: string) {
  const source = String(nodeId || '');
  let hash = 0;
  for (let index = 0; index < source.length; index += 1) {
    hash = (hash * 31 + source.charCodeAt(index)) % 240;
  }
  return hash;
}

export function nodeVisualSize(node: OntologyAssociationCircleNode, groupKey: AssociationMapGroupKey) {
  const evidence = nodeEvidenceCount(node);
  const platform = nodePlatformCount(node);
  if (groupKey === 'risk' || isCompetitorNode(node)) {
    const weakSampleFloor = platform <= 1 && evidence <= 1 ? 8.8 : 10.2;
    return clampNumber(weakSampleFloor + Math.min(15, Math.max(0, evidence / 3.2)), 8.8, 25);
  }
  return clampNumber(11 + Math.min(18, Math.max(0, evidence / 2.8)), 9.8, 29);
}

export function nodeVisualDistanceValue(node: OntologyAssociationCircleNode) {
  const baseDistance = nodeDistanceValue(node);
  const distance = baseDistance > 0 ? baseDistance : 100 - nodeClosenessValue(node);
  return clampNumber(distance, 0, 100);
}

/**
 * Pure map-group builders for association circle (knife 1).
 */

import type { OntologyAssociationCircleNode } from '@/types/ontology';
import {
  isRiskNodeForMap,
  nodeDistanceValue,
  nodeEvidenceCount,
  nodePlatformCount,
  scoreNumber,
} from './nodeMetrics';
import type { AssociationMapGroup, AssociationMapGroupKey } from './types';

export function normalizeAssociationNodeDisplay(
  node: OntologyAssociationCircleNode,
): OntologyAssociationCircleNode {
  if (
    node.entity_id === 'evidence_regulation'
    && isRiskNodeForMap(node)
    && node.term === '监管信息'
  ) {
    return { ...node, term: '监管合规质疑' };
  }
  return node;
}

export function classifyAssociationNode(
  node: OntologyAssociationCircleNode,
): AssociationMapGroupKey {
  const text = `${node.term || ''} ${node.business_tag || ''} ${node.semantic_direction || ''} ${node.orbit_label || ''} ${node.maturity_label || ''}`;
  if (isRiskNodeForMap(node)) {
    return 'risk';
  }
  if (node.orbit === 'core_near' || node.orbit === 'strong' || node.orbit === 'R1') {
    return 'strong';
  }
  if (
    node.orbit === 'near_opportunity'
    || node.orbit === 'contestable'
    || node.orbit === 'far_opportunity'
    || node.orbit === 'R2'
    || node.maturity_tier === 'near_opportunity'
    || node.maturity_tier === 'far_opportunity'
    || /近端机会|远端机会/.test(text)
  ) {
    return 'growth';
  }
  if (
    node.orbit === 'weak'
    || node.orbit === 'R3'
    || node.orbit === 'blank'
    || node.maturity_tier === 'watch_signal'
    || node.maturity_tier === 'evidence_gap'
    || /待观察|待验证|长寿|人生再出发|被需要|价值感|新叙事/.test(text)
  ) {
    return 'story';
  }
  const distance = nodeDistanceValue(node);
  if (distance > 0) {
    if (distance <= 40) return 'strong';
    if (distance <= 65) return 'growth';
    return 'story';
  }
  return 'growth';
}

export function compareAssociationNodesForPriority(
  left: OntologyAssociationCircleNode,
  right: OntologyAssociationCircleNode,
): number {
  const leftPriority = typeof left.priority_rank === 'number' ? left.priority_rank : 99;
  const rightPriority = typeof right.priority_rank === 'number' ? right.priority_rank : 99;
  if (leftPriority !== rightPriority) return leftPriority - rightPriority;
  const leftEvidence = nodeEvidenceCount(left);
  const rightEvidence = nodeEvidenceCount(right);
  if (leftEvidence !== rightEvidence) return rightEvidence - leftEvidence;
  const leftPlatform = nodePlatformCount(left);
  const rightPlatform = nodePlatformCount(right);
  if (leftPlatform !== rightPlatform) return rightPlatform - leftPlatform;
  return (
    scoreNumber(right.gravity_score ?? right.closeness_score ?? right.association_score)
    - scoreNumber(left.gravity_score ?? left.closeness_score ?? left.association_score)
  );
}

export function buildAssociationMapGroups(
  nodes: OntologyAssociationCircleNode[],
): AssociationMapGroup[] {
  const grouped: Record<AssociationMapGroupKey, OntologyAssociationCircleNode[]> = {
    strong: [],
    growth: [],
    story: [],
    risk: [],
  };

  nodes.forEach((rawNode) => {
    const node = normalizeAssociationNodeDisplay(rawNode);
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

/**
 * Pure node metrics / risk classification for association circle map.
 * Extracted from AmwayAssociationCircleDashboardViews (knife 1, zero behavior).
 */

import type { OntologyAssociationCircleNode } from '@/types/ontology';
import type { NodeCountSource } from './types';

export function scoreNumber(value?: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : 0;
}

export function nodeClosenessValue(node: OntologyAssociationCircleNode): number {
  return scoreNumber(node.gravity_score ?? node.closeness_score ?? node.association_score);
}

export function nodeDistanceValue(node: OntologyAssociationCircleNode): number {
  const distance = scoreNumber(node.distance_score);
  if (distance > 0) return distance;
  const closeness = nodeClosenessValue(node);
  return closeness > 0 ? 100 - closeness : 0;
}

export function nodeEvidenceCount(node: OntologyAssociationCircleNode): number {
  return scoreNumber(
    node.answer_count ?? node.evidence_count ?? node.evidence_samples?.length,
  );
}

export function nodeCountMode(
  node: NodeCountSource,
): 'answers' | 'lower_bound' | 'mentions' {
  if (node.answer_count_is_exact === true) return 'answers';
  if (node.answer_count_is_exact === false) {
    return node.count_semantics === 'known_answer_refs_lower_bound'
      ? 'lower_bound'
      : 'mentions';
  }
  if (node.count_semantics === 'distinct_answer_refs') return 'answers';
  if (node.count_semantics === 'known_answer_refs_lower_bound') return 'lower_bound';
  if (node.count_semantics === 'legacy_summed_mentions') return 'mentions';
  return Array.isArray(node.answer_refs) ? 'answers' : 'mentions';
}

export function nodeCountPhrase(node: NodeCountSource, count: number): string {
  const mode = nodeCountMode(node);
  if (mode === 'answers') return `${count} 条回答`;
  if (mode === 'lower_bound') return `至少 ${count} 条可确认回答`;
  return `${count} 次节点提及`;
}

export function nodeCountMetricLabel(node: NodeCountSource): string {
  const mode = nodeCountMode(node);
  if (mode === 'answers') return '提及回答';
  if (mode === 'lower_bound') return '可确认回答';
  return '节点提及';
}

export function nodeCountShortUnit(node: NodeCountSource): '答' | '答+' | '次' {
  const mode = nodeCountMode(node);
  if (mode === 'answers') return '答';
  if (mode === 'lower_bound') return '答+';
  return '次';
}

export function nodePlatformCount(node: OntologyAssociationCircleNode): number {
  const explicitCount = scoreNumber(node.platform_count);
  if (explicitCount > 0) return explicitCount;
  return node.platform_distribution ? Object.keys(node.platform_distribution).length : 0;
}

export function isCompetitorNode(node: OntologyAssociationCircleNode): boolean {
  return String(node.entity_type || '').toLowerCase() === 'competitor';
}

export function isProtectedEvidenceAssetNode(
  node: OntologyAssociationCircleNode,
): boolean {
  const entityType = String(node.entity_type || '').toLowerCase();
  const entityId = String(node.entity_id || '').toLowerCase();
  return entityType === 'evidenceasset' && entityId !== 'evidence_regulation';
}

export function isRiskNodeForMap(node: OntologyAssociationCircleNode): boolean {
  if (isProtectedEvidenceAssetNode(node)) return false;
  const entityType = String(node.entity_type || '').toLowerCase();
  if (entityType === 'risklabel' || entityType === 'competitor') return true;
  if (node.orbit === 'risk_shadow' || node.is_risk_term) return true;
  const text = `${node.term || ''} ${node.business_tag || ''} ${node.semantic_direction || ''} ${node.orbit_label || ''} ${node.maturity_label || ''}`;
  return /风险|竞争|竞品|传销|智商税|夸大|压力|负面/.test(text);
}

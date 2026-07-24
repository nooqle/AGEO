/**
 * Amway association-circle FE types (circle split knife 1).
 * Shared by map grouping pure helpers and DashboardViews shell.
 */

import type { OntologyAssociationCircleNode } from '@/types/ontology';

export type AssociationMapGroupKey = 'strong' | 'growth' | 'story' | 'risk';
export type AssociationMapMode = 'associations' | 'risk';
export type OrbitDistanceBand = 'near' | 'bridge' | 'far' | 'risk';
export type AssociationNodeFilterKey = 'stable' | 'opportunity' | 'watch';

export interface AssociationMapGroup {
  key: AssociationMapGroupKey;
  title: string;
  subtitle: string;
  emptyText: string;
  tone: 'brand' | 'opportunity' | 'story' | 'risk';
  nodes: OntologyAssociationCircleNode[];
}

export type NodeCountSource = Pick<
  OntologyAssociationCircleNode,
  'answer_refs' | 'answer_count_is_exact' | 'count_semantics'
>;

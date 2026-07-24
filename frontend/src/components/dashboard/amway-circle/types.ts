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

export interface CommercialOrbitEntry {
  node: OntologyAssociationCircleNode;
  groupKey: AssociationMapGroupKey;
  distanceBand: OrbitDistanceBand;
  left: number;
  top: number;
  angle: number;
  radius: number;
  size: number;
  labelPriority: boolean;
}

export type OrbitEvidenceItem = {
  evidence_id?: string;
  entity_id?: string;
  lexicon_entity_id?: string;
  node_id?: string;
  node_term?: string;
  platform?: string;
  question_id?: string;
  question?: string;
  answer_excerpt?: string;
  relation_type?: string;
  context_polarity?: string;
};

export type PlatformEvidenceSummary = {
  platform: string;
  label: string;
  answerCount: number;
  questionCount: number;
  samples: OrbitEvidenceItem[];
};

export interface AssociationNodeFilterOption {
  key: AssociationNodeFilterKey;
  label: string;
  hint: string;
  count: number;
  tone: 'strong' | 'growth' | 'story';
}

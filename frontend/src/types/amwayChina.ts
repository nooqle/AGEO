export interface AmwayEntityTypeDefinition {
  type_id: string;
  label: string;
  definition: string;
  default_graph_role: string;
  extractable_from: string[];
  allowed_relation_types: string[];
  review_required: boolean;
}

export interface AmwayEntityLexiconEntry {
  id: string;
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  aliases: string[];
  description: string;
  related_terms: string[];
  graph_policy: {
    main_orbit: string;
    risk_view: string;
    target_gap_view: string;
  };
  source_policy: {
    source_kind: string;
    source_document_section: string;
    user_confirmed: boolean;
  };
  review_status: string;
  origin: 'default' | 'overridden' | 'custom';
  is_deleted: boolean;
  updated_at: string | null;
}

export interface AmwayEntityLexiconResponse {
  entity_id: string;
  entity_name: string;
  ontology_id: string;
  version: string;
  entity_types: AmwayEntityTypeDefinition[];
  entries: AmwayEntityLexiconEntry[];
  deleted_entry_ids: string[];
}

export interface AmwayEntityLexiconMutationInput {
  canonical_name?: string;
  entity_type?: string;
  aliases?: string[];
  description?: string;
  related_terms?: string[];
  review_status?: string;
}

export interface AmwayQuestionHistorySet {
  id: string;
  source_type: 'question_set' | 'run_input';
  title: string;
  source: string;
  status: string;
  question_count: number;
  questions: Array<Record<string, unknown>>;
  center_terms: string[];
  source_file_name?: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AmwayQuestionHistoryResponse {
  question_sets: AmwayQuestionHistorySet[];
  total: number;
}

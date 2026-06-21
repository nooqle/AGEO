export interface Entity {
  id: string;
  name: string;
  aliases: string[];
  domain: string;
  industry: string;
  description: string;
  visibilityScope: 'personal' | 'organization';
  ownerUserId: string | null;
  organizationId: string | null;
  lastAnalyzed: string | null;
  status: 'active' | 'pending' | 'inactive';
  dashboardVariant?: string | null;
  analysisMode?: string | null;
  reportKind?: string | null;
  centerTerms?: string[];
  enabledSurfaces?: string[];
  associationBrandCluster?: string[];
  isInternalTestData: boolean;
  hygieneLabels: string[];
  createdAt: string;
  updatedAt: string;
}

export interface CreateEntityInput {
  name: string;
  aliases: string[];
  domain: string;
  industry: string;
  description: string;
  visibilityScope: 'personal' | 'organization';
}

export interface UpdateEntityInput {
  name?: string;
  aliases?: string[];
  domain?: string;
  industry?: string;
  description?: string;
  visibilityScope?: 'personal' | 'organization';
}

/**
 * Normalize a backend entity response (snake_case) to frontend Entity (camelCase).
 */
export function normalizeEntity(raw: Record<string, unknown>): Entity {
  return {
    id: String(raw.id ?? ''),
    name: String(raw.name ?? ''),
    aliases: (raw.aliases || []) as string[],
    domain: String(raw.domain ?? ''),
    industry: String(raw.industry ?? ''),
    description: String(raw.description ?? ''),
    visibilityScope: (raw.visibility_scope ?? raw.visibilityScope ?? 'personal') as Entity['visibilityScope'],
    ownerUserId: (raw.owner_user_id ?? raw.ownerUserId ?? null) as string | null,
    organizationId: (raw.organization_id ?? raw.organizationId ?? null) as string | null,
    lastAnalyzed: (raw.last_analyzed ?? raw.lastAnalyzed ?? null) as string | null,
    status: (raw.status || 'pending') as Entity['status'],
    dashboardVariant: (raw.dashboard_variant ?? raw.dashboardVariant ?? null) as string | null,
    analysisMode: (raw.analysis_mode ?? raw.analysisMode ?? null) as string | null,
    reportKind: (raw.report_kind ?? raw.reportKind ?? null) as string | null,
    centerTerms: Array.isArray(raw.center_terms ?? raw.centerTerms)
      ? ((raw.center_terms ?? raw.centerTerms) as unknown[]).map(String)
      : [],
    enabledSurfaces: Array.isArray(raw.enabled_surfaces ?? raw.enabledSurfaces)
      ? ((raw.enabled_surfaces ?? raw.enabledSurfaces) as unknown[]).map(String)
      : [],
    associationBrandCluster: Array.isArray(raw.association_brand_cluster ?? raw.associationBrandCluster)
      ? ((raw.association_brand_cluster ?? raw.associationBrandCluster) as unknown[]).map(String)
      : [],
    isInternalTestData: Boolean(
      raw.is_internal_test_data ?? raw.isInternalTestData ?? false,
    ),
    hygieneLabels: Array.isArray(raw.hygiene_labels ?? raw.hygieneLabels)
      ? ((raw.hygiene_labels ?? raw.hygieneLabels) as unknown[]).map(String)
      : [],
    createdAt: String(raw.created_at ?? raw.createdAt ?? new Date().toISOString()),
    updatedAt: String(raw.updated_at ?? raw.updatedAt ?? new Date().toISOString()),
  };
}

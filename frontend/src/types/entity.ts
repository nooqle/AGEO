export interface Entity {
  id: string;
  name: string;
  aliases: string[];
  domain: string;
  industry: string;
  description: string;
  lastAnalyzed: string | null;
  status: 'active' | 'pending' | 'inactive';
  createdAt: string;
  updatedAt: string;
}

export interface CreateEntityInput {
  name: string;
  aliases: string[];
  domain: string;
  industry: string;
  description: string;
}

export interface UpdateEntityInput {
  name?: string;
  aliases?: string[];
  domain?: string;
  industry?: string;
  description?: string;
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
    lastAnalyzed: (raw.last_analyzed ?? raw.lastAnalyzed ?? null) as string | null,
    status: (raw.status || 'pending') as Entity['status'],
    createdAt: String(raw.created_at ?? raw.createdAt ?? new Date().toISOString()),
    updatedAt: String(raw.updated_at ?? raw.updatedAt ?? new Date().toISOString()),
  };
}

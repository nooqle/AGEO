import type { AmwayEntityLexiconEntry } from '@/types/amwayChina';

export type LexiconView = 'topics' | 'objects' | 'context' | 'unclassified';

/** UI grouping follows the stored graph role; semantic type never determines role. */
export function lexiconView(entry: AmwayEntityLexiconEntry): LexiconView {
  switch (entry.semantic_definition?.graph_role) {
    case 'topic': return 'topics';
    case 'object': return 'objects';
    case 'anchor':
    case 'context': return 'context';
    default: return 'unclassified';
  }
}

export function matchesLexiconQuery(entry: AmwayEntityLexiconEntry, query: string): boolean {
  const keyword = query.trim().toLowerCase();
  return !keyword || [entry.canonical_name, entry.description, ...entry.aliases, ...entry.related_terms]
    .join(' ').toLowerCase().includes(keyword);
}

export function indexLexiconViews(entries: AmwayEntityLexiconEntry[]) {
  const groups: Record<LexiconView, AmwayEntityLexiconEntry[]> = {
    topics: [], objects: [], context: [], unclassified: [],
  };
  const byId = new Map<string, AmwayEntityLexiconEntry>();
  for (const entry of entries) {
    if (byId.has(entry.entity_id)) continue;
    byId.set(entry.entity_id, entry);
    groups[lexiconView(entry)].push(entry);
  }
  const objectsByTopic = new Map<string, AmwayEntityLexiconEntry[]>();
  for (const object of groups.objects) {
    const topicIds = new Set(object.semantic_definition?.topic_mappings.filter((mapping) => mapping.review_status === 'approved').map((mapping) => mapping.target_entity_id));
    for (const topicId of topicIds) {
      if (byId.get(topicId)?.semantic_definition?.graph_role !== 'topic') continue;
      objectsByTopic.set(topicId, [...(objectsByTopic.get(topicId) || []), object]);
    }
  }
  return { groups, byId, objectsByTopic };
}

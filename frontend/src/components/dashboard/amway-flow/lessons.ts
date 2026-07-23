/**
 * Wave O UX: client-side topology lesson synthesis.
 * Must stay aligned with backend flow_run_lesson_service.lessons_from_topology.
 * Local synthesis removes the PUT-then-GET race so canvas/panel update instantly.
 */

import { PLATFORM_META } from './constants';

export type FlowLessonItem = {
  id: string;
  node_id: string;
  kind: string;
  headline: string;
  source?: string;
};

const PLATFORM_LABELS: Record<string, string> = Object.fromEntries(
  PLATFORM_META.map((p) => [p.id, p.label]),
);

function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] || platform;
}

/** Platforms gated by removed e-fetch-* edges → same copy as backend. */
export function lessonsFromTopologyRemovedEdges(
  removedEdgeIds: string[] | null | undefined,
): FlowLessonItem[] {
  const removed = new Set(
    (removedEdgeIds || []).map(String).filter((id) => id.trim().length > 0),
  );
  const out: FlowLessonItem[] = [];
  const skipped: string[] = [];

  for (const platform of PLATFORM_META.map((p) => p.id)) {
    const edge = `e-fetch-${platform}`;
    if (!removed.has(edge)) continue;
    skipped.push(platform);
    const label = platformLabel(platform);
    out.push({
      id: `topology:skip:${platform}`,
      node_id: `platform-${platform}`,
      kind: 'skipped_platform',
      headline: `当前生产线未连接${label}，运行将跳过该平台采集。`,
      source: 'topology',
    });
  }

  if (skipped.length) {
    const names = skipped.map(platformLabel).join('、');
    out.push({
      id: `topology:fetch-skip:${skipped.join(',')}`,
      node_id: 'fetch',
      kind: 'fetch_partial',
      headline: `答案采集将跳过：${names}（拓扑门控）。`,
      source: 'topology',
    });
  }

  return out;
}

/** Prefer local topology; ignore server topology rows (stale until PUT lands). */
export function mergeFlowLessons(
  localTopology: FlowLessonItem[],
  server: FlowLessonItem[],
): FlowLessonItem[] {
  const rest = (server || []).filter((item) => item.source !== 'topology');
  const seen = new Set<string>();
  const merged: FlowLessonItem[] = [];
  for (const item of [...localTopology, ...rest]) {
    if (!item?.node_id || !item?.headline) continue;
    const key = `${item.node_id}:${item.kind || ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(item);
  }
  return merged;
}

/** First headline per node_id (merged list should already prioritize topology). */
export function lessonsToNodeHeadlineMap(
  lessons: FlowLessonItem[],
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const item of lessons) {
    if (!item?.node_id || !item?.headline) continue;
    if (!map[item.node_id]) map[item.node_id] = item.headline;
  }
  return map;
}

export function removedEdgeIdsKey(removedEdgeIds: string[] | null | undefined): string {
  return [...(removedEdgeIds || [])].map(String).sort().join('\0');
}

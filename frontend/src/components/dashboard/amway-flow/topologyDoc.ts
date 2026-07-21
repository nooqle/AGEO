/** Topology document parse/persist + platform switch storage. */
import {
  ALL_PLATFORM_IDS,
  EDGE_DEFS,
  MAX_CUSTOM_NODES,
  NODE_DEFINITIONS,
  PLATFORMS_STORAGE_PREFIX,
  TOPOLOGY_STORAGE_PREFIX,
} from './constants';
import type {
  FlowTopology,
  FlowTopologyCustomEdge,
  FlowTopologyCustomNode,
} from './types';

export function readEnabledFlowPlatforms(entityId: string): string[] {
  if (typeof window === 'undefined') return ALL_PLATFORM_IDS;
  try {
    const raw = window.localStorage.getItem(PLATFORMS_STORAGE_PREFIX + entityId);
    if (!raw) return ALL_PLATFORM_IDS;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return ALL_PLATFORM_IDS;
    const valid = parsed.filter((id) => ALL_PLATFORM_IDS.includes(String(id))).map(String);
    return valid.length ? valid : ALL_PLATFORM_IDS;
  } catch {
    return ALL_PLATFORM_IDS;
  }
}

export function writeEnabledFlowPlatforms(entityId: string, platforms: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PLATFORMS_STORAGE_PREFIX + entityId, JSON.stringify(platforms));
  } catch {
    // 忽略持久化失败
  }
}


export function emptyFlowTopology(): FlowTopology {
  return { version: 1, customNodes: [], customEdges: [], removedEdgeIds: [] };
}

export function parseFlowTopology(raw: unknown): FlowTopology {
  const parsed = raw as Partial<FlowTopology> | null;
  if (!parsed || typeof parsed !== 'object') return emptyFlowTopology();
  const customNodes = (Array.isArray(parsed.customNodes) ? parsed.customNodes : [])
    .filter((node): node is FlowTopologyCustomNode => {
      if (!node || typeof node !== 'object') return false;
      const candidate = node as Partial<FlowTopologyCustomNode>;
      return (
        typeof candidate.id === 'string'
        && (candidate.type === 'analysis' || candidate.type === 'content')
        && Boolean(candidate.position)
        && typeof candidate.position!.x === 'number'
        && typeof candidate.position!.y === 'number'
      );
    })
    .slice(0, MAX_CUSTOM_NODES)
    .map((node) => ({ ...node, config: node.config && typeof node.config === 'object' ? node.config : {} }));
  const nodeIds = new Set(customNodes.map((node) => node.id));
  const isKnownEndpoint = (id: unknown): id is string =>
    typeof id === 'string'
    && (NODE_DEFINITIONS.some((definition) => definition.id === id)
      || ALL_PLATFORM_IDS.includes(id.replace(/^platform-/, ''))
      || nodeIds.has(id));
  const customEdges = (Array.isArray(parsed.customEdges) ? parsed.customEdges : [])
    .filter((edge): edge is FlowTopologyCustomEdge => {
      if (!edge || typeof edge !== 'object') return false;
      const candidate = edge as Partial<FlowTopologyCustomEdge>;
      return (
        typeof candidate.id === 'string'
        && isKnownEndpoint(candidate.source)
        && isKnownEndpoint(candidate.target)
        && candidate.source !== candidate.target
      );
    });
  const removedEdgeIds = (Array.isArray(parsed.removedEdgeIds) ? parsed.removedEdgeIds : [])
    .filter((id): id is string => typeof id === 'string' && EDGE_DEFS.some((definition) => definition.id === id));
  return { version: 1, customNodes, customEdges, removedEdgeIds };
}

export function readFlowTopology(entityId: string): FlowTopology {
  if (typeof window === 'undefined') return emptyFlowTopology();
  try {
    const raw = window.localStorage.getItem(TOPOLOGY_STORAGE_PREFIX + entityId);
    if (!raw) return emptyFlowTopology();
    return parseFlowTopology(JSON.parse(raw));
  } catch {
    return emptyFlowTopology();
  }
}

export function writeFlowTopology(entityId: string, topology: FlowTopology): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(TOPOLOGY_STORAGE_PREFIX + entityId, JSON.stringify(topology));
  } catch {
    // 忽略持久化失败
  }
}

export function clearFlowTopology(entityId: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(TOPOLOGY_STORAGE_PREFIX + entityId);
  } catch {
    // 忽略
  }
}

export function layoutStorageKey(entityId: string, centerTerm: string): string {
  return `amway-flow-layout:${entityId}:${centerTerm}`;
}

export function readStoredPositions(entityId: string, centerTerm: string): Record<string, { x: number; y: number }> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(layoutStorageKey(entityId, centerTerm));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, { x: number; y: number }>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}


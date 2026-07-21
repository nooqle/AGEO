/** Port typing + DAG cycle check for custom edges. */
import {
  BUILTIN_ACCEPTED_INPUTS,
  BUILTIN_OUTPUT_TYPE,
  CUSTOM_NODE_ACCEPTED_INPUTS,
  CUSTOM_NODE_OUTPUT_TYPE,
  NODE_DEFINITIONS,
  PLATFORM_META,
  PLATFORM_POSITIONS,
} from './constants';
import type { CustomFlowNodeType, FlowTopology } from './types';

export function buildDefaultPositions(): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  NODE_DEFINITIONS.forEach((definition) => {
    positions[definition.id] = definition.position;
  });
  PLATFORM_META.forEach((platform, index) => {
    positions[`platform-${platform.id}`] = PLATFORM_POSITIONS[index] || { x: 660, y: index * 80 };
  });
  return positions;
}

export function customNodeTypeOf(topology: FlowTopology, nodeId: string): CustomFlowNodeType | null {
  return topology.customNodes.find((node) => node.id === nodeId)?.type || null;
}

export function nodeOutputTypeOf(topology: FlowTopology, nodeId: string): string | null {
  const customType = customNodeTypeOf(topology, nodeId);
  if (customType) return CUSTOM_NODE_OUTPUT_TYPE[customType];
  return BUILTIN_OUTPUT_TYPE[nodeId] || null;
}

export function nodeAcceptedInputsOf(topology: FlowTopology, nodeId: string): string[] {
  const customType = customNodeTypeOf(topology, nodeId);
  if (customType) return CUSTOM_NODE_ACCEPTED_INPUTS[customType];
  return BUILTIN_ACCEPTED_INPUTS[nodeId] || [];
}

/** 从 newTarget 沿现有连线出发能否到达 newSource（能则新连线会成环）。 */
export function wouldCreateCycle(
  edges: Array<{ source: string; target: string }>,
  newSource: string,
  newTarget: string,
): boolean {
  const adjacency = new Map<string, string[]>();
  edges.forEach((edge) => {
    const list = adjacency.get(edge.source);
    if (list) list.push(edge.target);
    else adjacency.set(edge.source, [edge.target]);
  });
  const stack = [newTarget];
  const visited = new Set<string>();
  while (stack.length) {
    const current = stack.pop()!;
    if (current === newSource) return true;
    if (visited.has(current)) continue;
    visited.add(current);
    (adjacency.get(current) || []).forEach((next) => stack.push(next));
  }
  return false;
}

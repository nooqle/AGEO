'use client';

import { useCallback, useMemo, useEffect, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { TouchpointNodeCard } from './TouchpointNodeCard';
import type { TouchpointNode, TouchpointTree } from '@/types/touchpoint';

const nodeTypes: NodeTypes = {
  touchpoint: TouchpointNodeCard as unknown as NodeTypes['touchpoint'],
};

type FilterType = 'all' | 'profile' | 'scenario' | 'intent' | 'optimization';

const FILTER_MAX_DEPTH: Record<FilterType, number | undefined> = {
  all: undefined,
  profile: 1,
  scenario: 2,
  intent: 3,
  optimization: 4,
};

interface TouchpointMapProps {
  tree: TouchpointTree;
  onNodeSelect: (nodeId: string) => void;
  mode?: 'view' | 'select';
  checkedNodeIds?: Set<string>;
  onCheckChange?: (nodeId: string, checked: boolean) => void;
  selectableTypes?: string[];
  newNodeIds?: string[];
  filterType?: FilterType;
  onSendChatMessage?: (message: string) => void;
  direction?: 'TB' | 'LR';
}

// Collect all child node IDs (recursively) for a given node
function collectChildIds(node: TouchpointNode): string[] {
  const ids: string[] = [];
  if (node.children) {
    for (const child of node.children) {
      ids.push(child.id);
      ids.push(...collectChildIds(child));
    }
  }
  return ids;
}

// Collect child IDs from tree nodes matching given parent IDs
function collectChildIdsForParents(nodes: TouchpointNode[], parentIds: Set<string>): Set<string> {
  const result = new Set<string>();

  function walk(nodeList: TouchpointNode[]) {
    for (const node of nodeList) {
      if (parentIds.has(node.id) && node.children) {
        for (const child of node.children) {
          result.add(child.id);
          // Add all descendents too
          for (const id of collectChildIds(child)) {
            result.add(id);
          }
        }
      }
      if (node.children) {
        walk(node.children);
      }
    }
  }

  walk(nodes);
  return result;
}

const NODE_WIDTH = 180;
const NODE_HEIGHT = 80;

interface LayoutOptions {
  mode?: 'view' | 'select';
  selectableTypes?: string[];
  checkedNodeIds?: Set<string>;
  highlightedChildIds?: Set<string>;
  newNodeIds?: string[];
  maxDepth?: number;
  direction?: 'TB' | 'LR';
  callbacks?: {
    onFocus?: (nodeId: string) => void;
    onChatAnalysis?: (label: string) => void;
    onViewDetails?: (nodeId: string) => void;
  };
}

/** Walk the TouchpointNode tree and collect flat nodes + edges for dagre. */
function collectNodesAndEdges(
  nodes: TouchpointNode[],
  parentId: string | null,
  depth: number,
  options: LayoutOptions,
  out: {
    flowNodes: Array<{ id: string; data: Record<string, unknown> }>;
    edges: Edge[];
  },
) {
  if (options.maxDepth !== undefined && depth > options.maxDepth) return;

  const selectableSet = options.selectableTypes ? new Set(options.selectableTypes) : null;
  const newNodeSet = options.newNodeIds ? new Set(options.newNodeIds) : null;
  const isSelectMode = options.mode === 'select';

  for (const node of nodes) {
    const isSelectable = isSelectMode && selectableSet ? selectableSet.has(node.type) : false;
    const isChecked = options.checkedNodeIds?.has(node.id) ?? false;
    const isHighlighted = options.highlightedChildIds?.has(node.id) ?? false;
    const isNew = newNodeSet?.has(node.id) ?? false;
    const metrics = node.metadata?.metrics as
      | { visibility?: number; prompts?: number; articles?: number }
      | undefined;
    const childCount = node.children?.length ?? 0;

    out.flowNodes.push({
      id: node.id,
      data: {
        label: node.label,
        nodeType: node.type,
        description: node.description,
        isSelectable,
        isChecked,
        isSelected: isHighlighted,
        isNew,
        metrics,
        childCount,
        direction: options.direction,
        onFocus: options.callbacks?.onFocus,
        onChatAnalysis: options.callbacks?.onChatAnalysis,
        onViewDetails: options.callbacks?.onViewDetails,
      },
    });

    if (parentId) {
      out.edges.push({
        id: `${parentId}-${node.id}`,
        source: parentId,
        target: node.id,
        style: { stroke: 'var(--border-default)', strokeWidth: 1 },
        animated: false,
      });
    }

    if (node.children && node.children.length > 0) {
      collectNodesAndEdges(node.children, node.id, depth + 1, options, out);
    }
  }
}

/** Build ReactFlow nodes + edges using dagre for layout. */
function buildDagreLayout(
  rootNode: TouchpointNode,
  options: LayoutOptions,
): { nodes: Node[]; edges: Edge[] } {
  const collected: {
    flowNodes: Array<{ id: string; data: Record<string, unknown> }>;
    edges: Edge[];
  } = { flowNodes: [], edges: [] };

  collectNodesAndEdges([rootNode], null, 0, options, collected);

  // Create dagre graph
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  const dir = options.direction ?? 'LR';
  g.setGraph({ rankdir: dir, ranksep: dir === 'LR' ? 80 : 100, nodesep: dir === 'LR' ? 40 : 60 });

  for (const n of collected.flowNodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const e of collected.edges) {
    g.setEdge(e.source, e.target);
  }

  dagre.layout(g);

  // Map dagre positions to ReactFlow nodes
  const flowNodes: Node[] = collected.flowNodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      type: 'touchpoint',
      position: {
        x: (pos?.x ?? 0) - NODE_WIDTH / 2,
        y: (pos?.y ?? 0) - NODE_HEIGHT / 2,
      },
      data: n.data,
    };
  });

  return { nodes: flowNodes, edges: collected.edges };
}

/** Find a node by ID in the tree and return it as a subtree root. */
function findSubtreeRoot(nodes: TouchpointNode[], id: string): TouchpointNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const found = findSubtreeRoot(node.children, id);
      if (found) return found;
    }
  }
  return null;
}

export function TouchpointMap({
  tree,
  onNodeSelect,
  mode = 'view',
  checkedNodeIds,
  onCheckChange,
  selectableTypes,
  newNodeIds,
  filterType = 'all',
  onSendChatMessage,
  direction = 'LR',
}: TouchpointMapProps) {
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  const handleFocusNode = useCallback((nodeId: string) => {
    setFocusNodeId(nodeId);
  }, []);

  const handleChatAnalysis = useCallback((nodeLabel: string) => {
    if (onSendChatMessage) {
      onSendChatMessage(`请分析触点节点「${nodeLabel}」的详细数据`);
    }
  }, [onSendChatMessage]);

  const handleViewDetails = useCallback((nodeId: string) => {
    onNodeSelect(nodeId);
  }, [onNodeSelect]);

  // Compute highlighted child IDs (children of checked profile nodes)
  const highlightedChildIds = useMemo(() => {
    if (mode !== 'select' || !checkedNodeIds || checkedNodeIds.size === 0) {
      return new Set<string>();
    }
    return collectChildIdsForParents(tree.nodes, checkedNodeIds);
  }, [mode, checkedNodeIds, tree.nodes]);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    // Determine root node
    let rootNode: TouchpointNode;
    if (focusNodeId) {
      const found = findSubtreeRoot(tree.nodes, focusNodeId);
      rootNode = found ?? {
        id: 'brand-root',
        type: 'brand',
        label: tree.brand,
        children: tree.nodes,
      };
    } else {
      rootNode = {
        id: 'brand-root',
        type: 'brand',
        label: tree.brand,
        children: tree.nodes,
      };
    }

    return buildDagreLayout(rootNode, {
      mode,
      selectableTypes,
      checkedNodeIds,
      highlightedChildIds,
      newNodeIds,
      maxDepth: FILTER_MAX_DEPTH[filterType],
      direction,
      callbacks: {
        onFocus: handleFocusNode,
        onChatAnalysis: handleChatAnalysis,
        onViewDetails: handleViewDetails,
      },
    });
  }, [tree, mode, selectableTypes, checkedNodeIds, highlightedChildIds, newNodeIds, filterType, direction, focusNodeId, handleFocusNode, handleChatAnalysis, handleViewDetails]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync nodes/edges when props change
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (mode === 'select' && onCheckChange) {
        const nodeData = node.data as Record<string, unknown>;
        if (nodeData.isSelectable) {
          onCheckChange(node.id, !nodeData.isChecked);
          return;
        }
      }
      onNodeSelect(node.id);
    },
    [onNodeSelect, mode, onCheckChange]
  );

  return (
    <div className="w-full h-full relative">
      {focusNodeId && (
        <button
          onClick={() => setFocusNodeId(null)}
          className="absolute top-3 left-3 z-10 px-3 py-1.5 text-xs rounded-lg bg-[--bg-secondary] border border-[--border-default] text-[--text-primary] hover:bg-[--bg-tertiary] transition-colors"
        >
          返回全景
        </button>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.3}
        maxZoom={2}
        defaultEdgeOptions={{
          style: { stroke: 'var(--border-default)', strokeWidth: 1 },
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--bg-tertiary)"
        />
        <Controls
          className="!bg-[--bg-secondary] !border-[--border-default] !rounded-lg [&_button]:!bg-[--bg-secondary] [&_button]:!border-[--border-default] [&_button]:!fill-[--text-tertiary] [&_button:hover]:!bg-[--bg-tertiary]"
        />
        <MiniMap
          className="!bg-[--bg-secondary] !border-[--border-default]"
          nodeColor="var(--border-default)"
          maskColor="rgba(0, 0, 0, 0.5)"
        />
      </ReactFlow>
    </div>
  );
}

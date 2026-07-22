/** Shared types for Amway flow canvas (topology orchestration). */
import type { Node } from '@xyflow/react';

export type FlowNodeStatus = 'idle' | 'active' | 'done' | 'failed' | 'skipped';
export type FlowArtifactKey =
  | 'questions'
  | 'answers'
  | 'entities'
  | 'circle'
  | 'report'
  | 'lexicon'
  | 'analysisResult'
  | 'contentDraft';

export type FlowNodeOutput = {
  key: FlowArtifactKey;
  label: string;
  count?: number | null;
  disabled?: boolean;
};

export type AmwayFlowNodeData = {
  label: string;
  subtitle: string;
  icon: string;
  status: FlowNodeStatus;
  variant: 'asset' | 'process' | 'platform' | 'analysis' | 'content';
  outputs: FlowNodeOutput[];
  description: string;
  enabled?: boolean;
  planned?: boolean;
  /** Wave O: visible run/topology lesson (no silent apply). */
  lesson?: string | null;
  onOutput?: (nodeId: string, key: FlowArtifactKey) => void;
  onToggle?: (nodeId: string) => void;
};

export type AmwayFlowNode = Node<AmwayFlowNodeData, 'amway'>;

export type PanelState =
  | { kind: 'node'; nodeId: string }
  | { kind: 'artifact'; nodeId: string; artifact: FlowArtifactKey }
  | null;

export type CustomFlowNodeType = 'analysis' | 'content';

export type FlowTopologyCustomNode = {
  id: string;
  type: CustomFlowNodeType;
  position: { x: number; y: number };
  config: Record<string, unknown>;
};

export type FlowTopologyCustomEdge = {
  id: string;
  source: string;
  target: string;
};

export type FlowTopology = {
  version: 1;
  customNodes: FlowTopologyCustomNode[];
  customEdges: FlowTopologyCustomEdge[];
  removedEdgeIds: string[];
};

export type FlowAnalysisDimension = 'platform' | 'entities' | 'risk';

export type FlowAnalysisCard = { title: string; lines: string[] };

export type FlowAnalysisResult = {
  generatedAt: string;
  dimensions: FlowAnalysisDimension[];
  cards: FlowAnalysisCard[];
  mode?: 'llm' | 'deterministic' | string;
  summary?: string;
  fallback_reason?: string;
};

export type FlowContentResult = {
  generatedAt: string;
  mode?: 'llm' | 'template' | string;
  draft?: string;
  promptUsed?: string;
  fallback_reason?: string;
};

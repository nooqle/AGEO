export type TouchpointNodeType =
  | 'brand'
  | 'profile'
  | 'scenario'
  | 'intent'
  | 'optimization';

export interface TouchpointNode {
  id: string;
  type: TouchpointNodeType;
  label: string;
  description?: string;
  metadata?: Record<string, unknown>;
  children?: TouchpointNode[];
}

export interface TouchpointTree {
  brand: string;
  nodes: TouchpointNode[];
  buildPhase?: 'personas' | 'questions' | 'metrics' | 'complete';
  selectableNodeTypes?: string[];
  newNodeIds?: string[];
}

// Pipeline (3-column marketing touchpoint map)
export interface PipelineNode {
  id: string;
  label: string;
  subtitle?: string;
  tags?: Record<string, string | string[]>;
  priority?: string;
}

export interface PipelineColumn {
  key: 'profile' | 'scenario' | 'intent';
  label: string;
  color: string;
  nodes: PipelineNode[];
}

export interface PipelineEdge {
  source: string;
  target: string;
}

export interface PipelineData {
  columns: PipelineColumn[];
  edges: PipelineEdge[];
}

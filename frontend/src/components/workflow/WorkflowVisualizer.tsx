'use client';

import React, { useEffect, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  ConnectionLineType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { motion } from 'framer-motion';

// Workflow step definitions
const WORKFLOW_STEPS = [
  { id: 'A1', label: '品牌档案分析', description: '梳理品牌定位和竞品关系' },
  { id: 'A2', label: '用户画像分析', description: '生成可选的营销画像' },
  { id: 'A3', label: '问题生成', description: '模拟用户会提出的问题' },
  { id: 'A4', label: '答案抓取', description: '从平台抓取真实回答' },
  { id: 'A5', label: '报告生成', description: '输出可追问的分析结果' },
];

interface WorkflowVisualizerProps {
  currentStep?: string;
  executionStatus?: 'idle' | 'running' | 'paused' | 'completed' | 'error';
  completedSteps?: string[];
  className?: string;
}

type WorkflowNodeStatus = 'idle' | 'running' | 'paused' | 'completed' | 'error' | 'waiting';

interface WorkflowNodeData {
  stepIndex: string;
  label: string;
  description: string;
  status: WorkflowNodeStatus;
}

// Custom node component
const WorkflowNode = ({ data, selected }: { data: WorkflowNodeData; selected?: boolean }) => {
  const status = data.status;
  
  const statusStyles = {
    idle: 'bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-tertiary)]',
    running: 'bg-[var(--bg-secondary)] border-[var(--brand-primary)] text-[var(--brand-text)] shadow-sm',
    completed: 'bg-[var(--bg-secondary)] border-[var(--success)] text-[var(--success)]',
    error: 'bg-[var(--bg-secondary)] border-[var(--error)] text-[var(--error)]',
    waiting: 'bg-[var(--bg-secondary)] border-[var(--warning)] text-[var(--warning)]',
  };

  return (
    <motion.div
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className={`
        px-4 py-3 rounded-xl border-2 min-w-[160px]
        transition-all duration-300
        ${statusStyles[status as keyof typeof statusStyles] || statusStyles.idle}
        ${selected ? 'ring-2 ring-[var(--brand-border)] ring-offset-2 ring-offset-[var(--bg-primary)]' : ''}
      `}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs opacity-60">{data.stepIndex}</span>
        {status === 'running' && (
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            className="w-3 h-3 border-2 border-current border-t-transparent rounded-full"
          />
        )}
        {status === 'completed' && (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        )}
      </div>
      <div className="font-medium text-sm">{data.label}</div>
      <div className="text-xs opacity-60 mt-1">{data.description}</div>
    </motion.div>
  );
};

const nodeTypes = {
  workflowNode: WorkflowNode,
};

export function WorkflowVisualizer({
  currentStep,
  executionStatus = 'idle',
  completedSteps = [],
  className,
}: WorkflowVisualizerProps) {
  // Generate nodes
  const initialNodes: Node[] = useMemo(() => {
    return WORKFLOW_STEPS.map((step, index) => {
      let status = 'idle';
      if (completedSteps.includes(step.id)) {
        status = 'completed';
      } else if (currentStep === step.id) {
        status = executionStatus === 'paused' ? 'waiting' : 'running';
      }

      return {
        id: step.id,
        type: 'workflowNode',
        position: { x: index * 220, y: 100 },
        data: {
          stepIndex: `步骤 ${index + 1}`,
          label: step.label,
          description: step.description,
          status,
        },
        selected: currentStep === step.id,
      };
    });
  }, [currentStep, executionStatus, completedSteps]);

  // Generate edges
  const initialEdges: Edge[] = useMemo(() => {
    return WORKFLOW_STEPS.slice(0, -1).map((step, index) => {
      const nextStep = WORKFLOW_STEPS[index + 1];
      const isActive = completedSteps.includes(step.id);
      const isCurrent = currentStep === step.id;

      return {
        id: `e-${step.id}-${nextStep.id}`,
        source: step.id,
        target: nextStep.id,
        type: 'smoothstep',
        animated: isCurrent && executionStatus === 'running',
        style: {
          stroke: isActive ? 'var(--success)' : isCurrent ? 'var(--brand-primary)' : 'var(--border-subtle)',
          strokeWidth: 2,
        },
        markerEnd: {
          type: 'arrowclosed',
          color: isActive ? 'var(--success)' : isCurrent ? 'var(--brand-primary)' : 'var(--border-subtle)',
        },
      };
    });
  }, [currentStep, executionStatus, completedSteps]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes when props change
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  return (
    <div className={`w-full h-[300px] bg-[var(--bg-primary)] rounded-xl border border-[var(--border-subtle)] overflow-hidden ${className}`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        connectionLineType={ConnectionLineType.SmoothStep}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.5}
        maxZoom={1.5}
        defaultEdgeOptions={{
          type: 'smoothstep',
          style: { strokeWidth: 2 },
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="var(--border-subtle)" gap={20} size={1} />
        <Controls className="bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-secondary)]" />
        <MiniMap
          className="bg-[var(--bg-secondary)] border-[var(--border-subtle)]"
          nodeColor={(node) => {
            switch (node.data?.status) {
              case 'completed':
                return 'var(--success)';
              case 'running':
                return 'var(--brand-primary)';
              case 'error':
                return 'var(--error)';
              case 'waiting':
                return 'var(--warning)';
              default:
                return 'var(--border-subtle)';
            }
          }}
          maskColor="rgba(13, 13, 13, 0.8)"
        />
      </ReactFlow>
    </div>
  );
}

export default WorkflowVisualizer;

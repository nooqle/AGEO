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
  { id: 'A1', label: '品牌信息采集', description: '分析品牌档案和竞品' },
  { id: 'A2', label: '用户画像生成', description: '生成营销画像（可选）' },
  { id: 'A3', label: '问题模拟生成', description: '模拟用户提问' },
  { id: 'A4', label: 'AI答案抓取', description: '从平台抓取答案' },
  { id: 'A5', label: '数据分析报告', description: '生成分析报告' },
];

interface WorkflowVisualizerProps {
  currentStep?: string;
  executionStatus?: 'idle' | 'running' | 'paused' | 'completed' | 'error';
  completedSteps?: string[];
  className?: string;
}

type WorkflowNodeStatus = 'idle' | 'running' | 'paused' | 'completed' | 'error' | 'waiting';

interface WorkflowNodeData {
  stepId: string;
  label: string;
  description: string;
  status: WorkflowNodeStatus;
}

// Custom node component
const WorkflowNode = ({ data, selected }: { data: WorkflowNodeData; selected?: boolean }) => {
  const status = data.status;
  
  const statusStyles = {
    idle: 'bg-[--bg-secondary] border-[--border-subtle] text-[--text-tertiary]',
    running: 'bg-[--bg-secondary] border-[#6366F1] text-[#6366F1] shadow-[0_0_20px_rgba(99,102,241,0.3)]',
    completed: 'bg-[--bg-secondary] border-[#10B981] text-[#10B981]',
    error: 'bg-[--bg-secondary] border-[#EF4444] text-[#EF4444]',
    waiting: 'bg-[--bg-secondary] border-[#F59E0B] text-[#F59E0B]',
  };

  return (
    <motion.div
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className={`
        px-4 py-3 rounded-xl border-2 min-w-[160px]
        transition-all duration-300
        ${statusStyles[status as keyof typeof statusStyles] || statusStyles.idle}
        ${selected ? 'ring-2 ring-[#6366F1] ring-offset-2 ring-offset-[--bg-primary]' : ''}
      `}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-mono opacity-60">{data.stepId}</span>
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
          stepId: step.id,
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
          stroke: isActive ? '#10B981' : isCurrent ? '#6366F1' : 'var(--border-subtle)',
          strokeWidth: 2,
        },
        markerEnd: {
          type: 'arrowclosed',
          color: isActive ? '#10B981' : isCurrent ? '#6366F1' : 'var(--border-subtle)',
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
    <div className={`w-full h-[300px] bg-[--bg-primary] rounded-xl border border-[--border-subtle] overflow-hidden ${className}`}>
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
        <Controls className="bg-[--bg-secondary] border-[--border-subtle] text-[--text-secondary]" />
        <MiniMap
          className="bg-[--bg-secondary] border-[--border-subtle]"
          nodeColor={(node) => {
            switch (node.data?.status) {
              case 'completed':
                return '#10B981';
              case 'running':
                return '#6366F1';
              case 'error':
                return '#EF4444';
              case 'waiting':
                return '#F59E0B';
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

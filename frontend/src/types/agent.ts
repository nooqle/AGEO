export type TPAORPhase = 'thought' | 'plan' | 'action' | 'observation' | 'response';

// 导入编排类型
import type { ExecutionPlanStep, AgentCall, AgentCapability } from './orchestration';

export interface TPAORUpdate {
  phase: TPAORPhase;
  content: string;
  isComplete: boolean;
  timestamp: Date;
}

export interface SubTask {
  id: string;
  name: string;
  platform?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress?: number;
  message?: string;
}

export interface ProgressStep {
  id: string;
  label: string;
  description?: string;
  status: 'completed' | 'in_progress' | 'pending' | 'error' | 'skipped';
}

export interface ExecutionProgress {
  stage: string;
  stageName: string;
  stageIndex: number;
  totalStages: number;
  progress: number; // 0-1
  status: 'pending' | 'running' | 'completed' | 'failed';
  details?: string;
  steps?: ProgressStep[];  // 步骤列表
  subTasks?: SubTask[];
  estimatedTimeRemaining?: number;

  // LLM 编排相关（v2 新增）
  execution_plan?: ExecutionPlanStep[];  // 完整执行计划
  current_agent?: AgentCall;             // 当前执行的 Agent
  available_agents?: AgentCapability[];  // 可用 Agent 列表
}

export type BrowserStateType =
  | 'idle'
  | 'initializing'
  | 'navigating'
  | 'checking_login'
  | 'waiting_for_login'
  | 'logged_in'
  | 'enabling_search'
  | 'submitting'
  | 'waiting_response'
  | 'extracting'
  | 'completed'
  | 'error';

export interface BrowserState {
  state: BrowserStateType;
  platform: 'kimi' | 'deepseek' | 'doubao' | 'hunyuan';
  message: string;
  requiresAction: boolean;
  actionHint?: string;
  progress?: number;
}

export interface StopState {
  isStopped: boolean;
  stoppedAt: Date;
  completedStages: Array<{
    name: string;
    description?: string;
    completedAt: Date;
  }>;
  pendingStages: Array<{
    name: string;
    description?: string;
  }>;
  partialResults?: {
    fetchedCount: number;
    totalCount: number;
    platforms: Record<string, { completed: number; total: number }>;
  };
  canResume: boolean;
  canRetry: boolean;
}

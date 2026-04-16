export type MessageType = 'user' | 'agent' | 'system' | 'execution_step' | 'system_notice';
export type MessageStatus = 'sending' | 'sent' | 'error';

// 执行步骤状态
export type ExecutionStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'waiting_confirmation';

// 导入编排类型
import type { ExecutionPlanStep, LLMDecision, IntentType } from './orchestration';
import type { CanvasContentType, CanvasPreviewMetricValue } from './canvas';

// Legacy TPAOR type (kept for backward compatibility during transition)
export interface TPAORContent {
  thought?: string;
  plan?: string;
  action?: string;
  observation?: string;
  response?: string;
}

// New: Action log entry for Layer 3
export interface ActionLogEntry {
  id: string;
  actionType: 'agent_call' | 'llm_call' | 'search' | 'browser' | 'parse' | 'generic';
  message: string;
  step?: string;
  timestamp: string;
  isComplete: boolean;
}

// New: Agent message layers (4-layer architecture)
export interface AgentMessageLayers {
  planText?: string;              // Layer 2: LLM-generated plan description
  actionLogs: ActionLogEntry[];   // Layer 3: Action log entries
  thought?: string;               // Collapsible thinking/reasoning
}

// New: Inline confirmation (Layer 4, replaces modal)
export interface InlineConfirmation {
  requestId?: string;
  message: string;
  options: Array<{ id: string; label: string; description?: string; recommended?: boolean }>;
  selectedOptionId?: string;      // Set after user selects
  type?: 'simple' | 'guided';    // 'simple' = buttons, 'guided' = A/B/C cards
  waitingTips?: string[];         // Tips shown during long operations
  estimatedTime?: string;         // e.g., "5-10 minutes"
  checklist?: Array<{             // Completion checklist items
    id: string;
    label: string;
    status: 'completed' | 'in_progress' | 'pending' | 'failed';
  }>;
}

// 执行步骤详情
export interface ExecutionStep {
  stepId: string;
  stepName: string;
  stepIndex: number;
  totalSteps: number;
  status: ExecutionStepStatus;
  description?: string;
  logs?: string[]; // 流式执行日志
  result?: Record<string, unknown>; // 执行结果
  startTime?: Date;
  endTime?: Date;
}

export interface OutputCard {
  id: string;
  type: CanvasContentType;
  title: string;
  preview: {
    metrics?: Record<string, CanvasPreviewMetricValue>;
    description?: string;
    itemCount?: number;
  };
}

export interface ConfirmationOption {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  recommended?: boolean;
}

export interface ConfirmationRequest {
  requestId: string;
  type: 'brand_info' | 'persona_selection' | 'action_choice' | 'continue' | 'step_confirmation';
  message: string;
  options: ConfirmationOption[];
  allowTextInput: boolean;
  timeout?: number;
  // 步骤确认特有
  stepId?: string;
  stepName?: string;
}

// System notice data for degradation/platform_status events
export interface SystemNoticeData {
  subtype: 'degradation' | 'platform_status';
  level: 'info' | 'warning' | 'error';
  title: string;
  description?: string;
  impact?: string;
  platforms?: Array<{
    name: string;
    status: 'success' | 'failed' | 'skipped';
    detail?: string;
  }>;
}

export interface MessageMetadata {
  canEdit: boolean;
  canRollback: boolean;
  relatedOutputIds: string[];
  executionTime?: number;
}

export interface Message {
  id: string;
  type: MessageType;
  content: string;
  timestamp: Date;
  status?: MessageStatus;

  // Agent 消息特有
  tpaor?: TPAORContent;
  outputCards?: OutputCard[];
  confirmationRequest?: ConfirmationRequest;

  // New: 4-layer architecture
  layers?: AgentMessageLayers;
  inlineConfirmation?: InlineConfirmation;

  // File attachments
  attachments?: Array<{
    id?: string;
    name: string;
    size?: number;
    type?: string | null;
    url?: string;
  }>;

  // 执行步骤消息特有
  executionStep?: ExecutionStep;

  // System notice data (for system_notice type messages)
  systemNotice?: SystemNoticeData;

  // 元数据
  metadata: MessageMetadata;

  // LLM 编排相关（v2 新增）
  execution_plan?: ExecutionPlanStep[];  // 执行计划
  llm_decision?: LLMDecision;            // LLM 决策
  intent_type?: IntentType;              // 用户意图类型
  reasoning?: string;                    // 决策理由（调试用）
}

/**
 * Orchestration Types - LLM 驱动编排相关类型定义
 *
 * 这些类型与后端 app/schemas/orchestration.py 保持同步
 */

/** 意图类型 */
export type IntentType =
  | 'start_analysis'      // 开始新分析
  | 'continue_execution'  // 继续执行
  | 'modify_plan'         // 修改计划
  | 'ask_question'        // 用户提问
  | 'provide_info'        // 用户提供信息
  | 'confirm_action'      // 用户确认
  | 'cancel_action'       // 用户取消
  | 'help_request'        // 请求帮助
  | 'unknown';            // 无法识别

/** 行动类型 */
export type ActionType =
  | 'call_agent'          // 调用 Agent
  | 'ask_confirmation'    // 请求确认
  | 'respond_to_user'     // 回复用户
  | 'wait_for_input'      // 等待输入
  | 'complete';           // 完成

/** Agent 调用信息 */
export interface AgentCall {
  agent_id: string;
  agent_name?: string;
  input_params: Record<string, unknown>;
  skip_confirmation?: boolean;
  reason: string;
}

/** 执行计划步骤 */
export interface ExecutionPlanStep {
  step_number: number;
  agent_id: string;
  description: string;
  depends_on?: number[];
  can_parallel?: boolean;
  estimated_duration: string;
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
}

/** LLM 决策输出 */
export interface LLMDecision {
  user_intent: string;
  intent_type: IntentType;
  next_action: ActionType;
  agent_call?: AgentCall;
  execution_plan?: ExecutionPlanStep[];
  response_message?: string;
  confirmation_request?: ConfirmationRequestData;
  reasoning: string;
}

/** 确认请求数据 */
export interface ConfirmationRequestData {
  type: 'step_confirmation' | 'action_choice';
  step_id?: string;
  step_name?: string;
  options: ConfirmationOption[];
}

/** 确认选项 */
export interface ConfirmationOption {
  id: string;
  label: string;
  description?: string;
}

/** Agent 能力描述 */
export interface AgentCapability {
  agent_id: string;
  name: string;
  description: string;
  estimated_duration: string;
  prerequisites: string[];
  produces: string[];
  can_skip: boolean;
  requires_confirmation: boolean;
}

/** 编排事件类型 */
export type OrchestrationEventType =
  | 'llm_decision'        // LLM 决策结果
  | 'plan_created'        // 执行计划创建
  | 'plan_updated'        // 执行计划更新
  | 'agent_call_start'    // Agent 调用开始
  | 'agent_call_complete' // Agent 调用完成
  | 'context_updated';    // 上下文数据更新

/** 编排事件 */
export interface OrchestrationEvent {
  event_type: OrchestrationEventType;
  data: Record<string, unknown>;
  timestamp: string;
}

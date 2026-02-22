// WebSocket 消息类型定义

// 客户端 → 服务端
interface ClientMessage {
  type: 'user_message' | 'confirmation' | 'stop' | 'ping';
  payload: any;
  session_id: string;
  message_id?: string;
}

// 服务端 → 客户端
interface ServerMessage {
  type: 
    | 'agent_message'           // Agent 文本消息
    | 'tpaor_update'            // TPAOR 状态更新
    | 'execution_progress'      // 执行进度
    | 'output_ready'            // 产出就绪 (触发 Canvas)
    | 'confirmation_request'    // 需要用户确认
    | 'execution_complete'      // 执行完成
    | 'execution_stopped'       // 执行已停止
    | 'error'                   // 错误
    | 'pong';                   // 心跳响应
  payload: any;
  timestamp: string;
  session_id: string;
}

// TPAOR 更新
interface TPAORUpdate {
  phase: 'thought' | 'plan' | 'action' | 'observation' | 'response';
  content: string;
  is_complete: boolean;
}

// 执行进度
interface ExecutionProgress {
  stage: string;
  stage_name: string;  // 中文名
  progress: number;    // 0-100
  status: 'pending' | 'running' | 'completed' | 'failed';
  details?: string;
  sub_tasks?: SubTask[];
}

// 产出就绪
interface OutputReady {
  output_id: string;
  type: 'report' | 'chart' | 'dataTable' | 'selection';
  title: string;
  preview: object;
  full_data: object;
  auto_open_canvas: boolean;
}
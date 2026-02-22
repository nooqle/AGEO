# OpenAPI 3.0 规范摘要

# 会话管理
POST   /api/v1/sessions
  - 创建新会话
  - Response: { id, status, created_at }

GET    /api/v1/sessions/{session_id}
  - 获取会话详情
  - Response: { id, status, current_phase, pipeline_state, ... }

DELETE /api/v1/sessions/{session_id}
  - 删除会话

# 消息管理
GET    /api/v1/sessions/{session_id}/messages
  - 获取消息列表
  - Query: ?limit=50&before=<message_id>
  - Response: { messages: [...], has_more }

POST   /api/v1/sessions/{session_id}/messages
  - 发送用户消息 (触发 Agent 执行)
  - Body: { content: string }
  - Response: { message_id }

DELETE /api/v1/sessions/{session_id}/messages/{message_id}/after
  - 回退：删除指定消息之后的所有内容
  - Response: { deleted_count, deleted_outputs }

# 产出管理
GET    /api/v1/sessions/{session_id}/outputs
  - 获取所有产出
  - Response: { outputs: [...] }

GET    /api/v1/sessions/{session_id}/outputs/{output_id}
  - 获取单个产出详情
  
GET    /api/v1/sessions/{session_id}/outputs/{output_id}/export
  - 导出产出 (PDF/Excel)
  - Query: ?format=pdf|excel

# Agent 控制
POST   /api/v1/sessions/{session_id}/agent/stop
  - 停止当前执行
  - Response: { stopped: true, completed_stages, pending_stages }

POST   /api/v1/sessions/{session_id}/agent/resume
  - 恢复执行

POST   /api/v1/sessions/{session_id}/agent/confirm
  - 发送确认选择
  - Body: { request_id, selection: {...} }
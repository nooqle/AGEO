## 执行计划

### Step 1: 创建服务层

**1.1 WebSocket 管理器**
**文件**: `backend/app/services/websocket_manager.py`
- `WebSocketManager` 类
- `connect()` / `disconnect()` - 连接管理
- `send_to_session()` - 向会话发送消息
- `broadcast_event()` - 广播事件

**1.2 Agent 调度器**
**文件**: `backend/app/services/agent_orchestrator.py`
- `AgentOrchestrator` 类
- `process_message()` - 处理用户消息，转发事件到 WebSocket
- `handle_confirmation()` - 处理用户确认
- `stop_execution()` - 停止执行

**1.3 Session 服务**
**文件**: `backend/app/services/session_service.py`
- `SessionService` 类
- `create_session()` - 创建会话
- `get_session()` - 获取会话
- `delete_session()` - 删除会话

**1.4 Message 服务**
**文件**: `backend/app/services/message_service.py`
- `MessageService` 类
- `get_messages()` - 获取消息列表
- `save_message()` - 保存消息
- `rollback_after()` - 回退消息

**1.5 Output 服务**
**文件**: `backend/app/services/output_service.py`
- `OutputService` 类
- `get_outputs()` - 获取产出列表
- `get_output()` - 获取单个产出
- `export_output()` - 导出产出

### Step 2: 创建 API 层

**2.1 依赖注入**
**文件**: `backend/app/api/deps.py`
- `get_db()` - 获取数据库会话

**2.2 Sessions API**
**文件**: `backend/app/api/v1/sessions.py`
- `POST /sessions` - 创建会话
- `GET /sessions/{session_id}` - 获取会话详情
- `DELETE /sessions/{session_id}` - 删除会话

**2.3 Messages API**
**文件**: `backend/app/api/v1/messages.py`
- `GET /sessions/{session_id}/messages` - 获取消息列表
- `POST /sessions/{session_id}/messages` - 发送消息
- `DELETE /sessions/{session_id}/messages/{message_id}/after` - 回退消息

**2.4 Outputs API**
**文件**: `backend/app/api/v1/outputs.py`
- `GET /sessions/{session_id}/outputs` - 获取产出列表
- `GET /sessions/{session_id}/outputs/{output_id}` - 获取产出详情
- `GET /sessions/{session_id}/outputs/{output_id}/export` - 导出产出

**2.5 WebSocket API**
**文件**: `backend/app/api/v1/websocket.py`
- `WebSocket /ws/{session_id}` - WebSocket 端点
- 支持消息类型：user_message, confirmation, stop, ping
- 支持事件类型：agent_message, tpaor_update, execution_progress, browser_state, output_ready, confirmation_request, execution_complete, execution_stopped, error, pong

**2.6 路由汇总**
**文件**: `backend/app/api/v1/router.py`
- 汇总所有 API 路由

### Step 3: 创建主应用入口
**文件**: `backend/app/main.py`
- FastAPI 应用实例
- CORS 配置
- 路由注册
- 健康检查端点

### 目录结构
```
backend/app/
├── api/
│   ├── __init__.py
│   ├── deps.py
│   └── v1/
│       ├── __init__.py
│       ├── router.py
│       ├── sessions.py
│       ├── messages.py
│       ├── outputs.py
│       └── websocket.py
├── services/
│   ├── __init__.py
│   ├── websocket_manager.py
│   ├── agent_orchestrator.py
│   ├── session_service.py
│   ├── message_service.py
│   └── output_service.py
└── main.py
```

请确认此计划后，我将开始执行具体的代码实现。
# 任务：实现后端 API 层和 WebSocket 通信

## 背景
需要将 Agent 系统通过 API 和 WebSocket 暴露给前端，支持：
1. REST API：会话管理、消息历史、产出查询
2. WebSocket：实时事件推送（TPAOR 状态、进度、浏览器状态等）

## 参考文档
- `Mittus AEO平台 - 前端交互设计文档 v2.md` 中的 API 接口规范
- `WebSocket 协议规范.md`

## 任务要求

### 1. 目录结构
```
backend/app/
├── api/
│   ├── __init__.py
│   ├── deps.py                 # 依赖注入
│   └── v1/
│       ├── __init__.py
│       ├── router.py           # 路由汇总
│       ├── sessions.py         # 会话管理
│       ├── messages.py         # 消息处理
│       ├── outputs.py          # 产出内容
│       └── websocket.py        # WebSocket 端点
│
├── services/
│   ├── __init__.py
│   ├── session_service.py      # 会话业务逻辑
│   ├── message_service.py      # 消息业务逻辑
│   ├── agent_orchestrator.py   # Agent 调度器
│   └── websocket_manager.py    # WebSocket 连接管理
```

### 2. WebSocket 管理器
```python
# backend/app/services/websocket_manager.py
from typing import Dict, Set
from fastapi import WebSocket
import json
from datetime import datetime


class WebSocketManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # session_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """建立连接"""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, session_id: str):
        """断开连接"""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
    
    async def send_to_session(self, session_id: str, message: dict):
        """向指定会话的所有连接发送消息"""
        if session_id in self.active_connections:
            dead_connections = set()
            for websocket in self.active_connections[session_id]:
                try:
                    await websocket.send_json(message)
                except:
                    dead_connections.add(websocket)
            
            # 清理断开的连接
            for ws in dead_connections:
                self.active_connections[session_id].discard(ws)
    
    async def broadcast_event(self, session_id: str, event_type: str, payload: dict):
        """广播事件"""
        message = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
        }
        await self.send_to_session(session_id, message)


# 全局实例
ws_manager = WebSocketManager()
```

### 3. Agent 调度器
```python
# backend/app/services/agent_orchestrator.py
from typing import AsyncGenerator
from app.agents.general_react import GeneralReActAgent
from app.services.websocket_manager import ws_manager
from app.schemas.message import MessageCreate, AgentEvent


class AgentOrchestrator:
    """
    Agent 调度器
    
    职责：
    1. 接收用户消息
    2. 调用 General ReAct Agent
    3. 将事件流转发到 WebSocket
    4. 保存消息到数据库
    """
    
    def __init__(self, session_id: str, db):
        self.session_id = session_id
        self.db = db
        self.agent = GeneralReActAgent()
    
    async def process_message(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        处理用户消息
        
        1. 保存用户消息到数据库
        2. 调用 Agent 处理
        3. 实时推送事件到 WebSocket
        4. 保存 Agent 回复到数据库
        """
        # 1. 保存用户消息
        await self._save_user_message(user_message)
        
        # 2. 通知前端开始处理
        await ws_manager.broadcast_event(
            self.session_id,
            "agent_start",
            {"message": "开始处理..."}
        )
        
        # 3. 调用 Agent 并转发事件
        async for event in self.agent.handle_user_message(
            message=user_message,
            session_id=self.session_id,
        ):
            # 转发 TPAOR 状态更新
            if event.tpaor_phase:
                await ws_manager.broadcast_event(
                    self.session_id,
                    "tpaor_update",
                    {
                        "phase": event.tpaor_phase,
                        "content": event.message,
                        "is_complete": event.is_complete,
                    }
                )
            
            # 转发执行进度
            if event.progress is not None:
                await ws_manager.broadcast_event(
                    self.session_id,
                    "execution_progress",
                    {
                        "stage": event.stage,
                        "progress": event.progress,
                        "status": event.status,
                        "details": event.details,
                    }
                )
            
            # 转发浏览器状态（FetchAgent 产生）
            if event.browser_state:
                await ws_manager.broadcast_event(
                    self.session_id,
                    "browser_state",
                    {
                        "state": event.browser_state,
                        "message": event.message,
                        "requires_action": event.requires_action,
                        "action_hint": event.action_hint,
                    }
                )
            
            # 产出就绪（触发 Canvas 展开）
            if event.output_ready:
                await ws_manager.broadcast_event(
                    self.session_id,
                    "output_ready",
                    {
                        "output_id": event.output_id,
                        "type": event.output_type,
                        "title": event.output_title,
                        "preview": event.output_preview,
                        "auto_open_canvas": True,
                    }
                )
            
            # 需要用户确认
            if event.confirmation_request:
                await ws_manager.broadcast_event(
                    self.session_id,
                    "confirmation_request",
                    event.confirmation_request,
                )
            
            yield event
        
        # 4. 保存 Agent 回复
        await self._save_agent_message(event)
        
        # 5. 通知完成
        await ws_manager.broadcast_event(
            self.session_id,
            "execution_complete",
            {"message": "处理完成"}
        )
    
    async def handle_confirmation(self, request_id: str, selection: dict):
        """处理用户确认"""
        # 将确认传递给 Agent
        await self.agent.receive_confirmation(request_id, selection)
    
    async def stop_execution(self):
        """停止执行"""
        await self.agent.stop()
        await ws_manager.broadcast_event(
            self.session_id,
            "execution_stopped",
            {"message": "已停止执行"}
        )
    
    async def _save_user_message(self, content: str):
        """保存用户消息"""
        # 数据库操作
        pass
    
    async def _save_agent_message(self, event: AgentEvent):
        """保存 Agent 消息"""
        # 数据库操作
        pass
```

### 4. API 端点实现
```python
# backend/app/api/v1/sessions.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_db
from app.schemas.session import SessionCreate, SessionResponse, SessionDetail
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
async def create_session(db: AsyncSession = Depends(get_db)):
    """创建新会话"""
    service = SessionService(db)
    session = await service.create_session()
    return session


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """获取会话详情"""
    service = SessionService(db)
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}")
async def delete_session(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """删除会话"""
    service = SessionService(db)
    await service.delete_session(session_id)
    return {"status": "deleted"}


# backend/app/api/v1/messages.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from app.api.deps import get_db
from app.schemas.message import MessageCreate, MessageResponse
from app.services.message_service import MessageService
from app.services.agent_orchestrator import AgentOrchestrator

router = APIRouter(prefix="/sessions/{session_id}/messages", tags=["messages"])


@router.get("", response_model=List[MessageResponse])
async def get_messages(
    session_id: UUID,
    limit: int = 50,
    before: UUID = None,
    db: AsyncSession = Depends(get_db),
):
    """获取消息列表"""
    service = MessageService(db)
    messages = await service.get_messages(session_id, limit=limit, before=before)
    return messages


@router.post("")
async def send_message(
    session_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    发送用户消息
    
    消息会被保存，Agent 处理会在后台进行。
    实时进度通过 WebSocket 推送。
    """
    # 启动后台任务处理 Agent
    orchestrator = AgentOrchestrator(str(session_id), db)
    background_tasks.add_task(
        process_message_task,
        orchestrator,
        message.content,
    )
    
    return {"status": "processing", "message": "消息已接收，正在处理"}


async def process_message_task(orchestrator: AgentOrchestrator, content: str):
    """后台任务：处理消息"""
    async for event in orchestrator.process_message(content):
        pass  # 事件已通过 WebSocket 推送


@router.delete("/{message_id}/after")
async def rollback_to_message(
    session_id: UUID,
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    回退：删除指定消息之后的所有内容
    """
    service = MessageService(db)
    result = await service.rollback_after(session_id, message_id)
    return result


# backend/app/api/v1/outputs.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_db
from app.services.output_service import OutputService

router = APIRouter(prefix="/sessions/{session_id}/outputs", tags=["outputs"])


@router.get("")
async def get_outputs(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """获取所有产出"""
    service = OutputService(db)
    outputs = await service.get_outputs(session_id)
    return outputs


@router.get("/{output_id}")
async def get_output(
    session_id: UUID,
    output_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取单个产出详情"""
    service = OutputService(db)
    output = await service.get_output(session_id, output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    return output


@router.get("/{output_id}/export")
async def export_output(
    session_id: UUID,
    output_id: UUID,
    format: str = "pdf",  # pdf | excel
    db: AsyncSession = Depends(get_db),
):
    """导出产出"""
    service = OutputService(db)
    file_path = await service.export_output(session_id, output_id, format)
    return FileResponse(file_path)


# backend/app/api/v1/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.websocket_manager import ws_manager
from app.services.agent_orchestrator import AgentOrchestrator

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
):
    """
    WebSocket 端点
    
    客户端消息类型：
    - user_message: 发送用户消息
    - confirmation: 发送确认选择
    - stop: 停止执行
    - ping: 心跳
    
    服务端消息类型：
    - agent_message: Agent 文本消息
    - tpaor_update: TPAOR 状态更新
    - execution_progress: 执行进度
    - browser_state: 浏览器状态
    - output_ready: 产出就绪
    - confirmation_request: 需要确认
    - execution_complete: 执行完成
    - execution_stopped: 执行已停止
    - error: 错误
    - pong: 心跳响应
    """
    await ws_manager.connect(websocket, session_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            payload = data.get("payload", {})
            
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif message_type == "user_message":
                # 处理用户消息
                orchestrator = AgentOrchestrator(session_id, None)  # TODO: 注入 db
                async for event in orchestrator.process_message(payload.get("content")):
                    pass  # 事件已通过 ws_manager 推送
            
            elif message_type == "confirmation":
                orchestrator = AgentOrchestrator(session_id, None)
                await orchestrator.handle_confirmation(
                    payload.get("request_id"),
                    payload.get("selection"),
                )
            
            elif message_type == "stop":
                orchestrator = AgentOrchestrator(session_id, None)
                await orchestrator.stop_execution()
    
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)


# backend/app/api/v1/router.py
from fastapi import APIRouter
from app.api.v1 import sessions, messages, outputs, websocket

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(sessions.router)
api_router.include_router(messages.router)
api_router.include_router(outputs.router)
api_router.include_router(websocket.router)
```

### 5. 主应用入口
```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(
    title="AEO Platform API",
    description="AI Engine Optimization 智能分析平台",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

## 预期产出
1. `backend/app/api/__init__.py`
2. `backend/app/api/deps.py`
3. `backend/app/api/v1/__init__.py`
4. `backend/app/api/v1/router.py`
5. `backend/app/api/v1/sessions.py`
6. `backend/app/api/v1/messages.py`
7. `backend/app/api/v1/outputs.py`
8. `backend/app/api/v1/websocket.py`
9. `backend/app/services/websocket_manager.py`
10. `backend/app/services/agent_orchestrator.py`
11. `backend/app/services/session_service.py`
12. `backend/app/services/message_service.py`
13. `backend/app/services/output_service.py`
14. `backend/app/main.py`
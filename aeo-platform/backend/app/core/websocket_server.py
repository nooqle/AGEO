"""WebSocket server for real-time communication using FastAPI native WebSocket."""

import logging
from fastapi import WebSocket


# 定义执行步骤模板
EXECUTION_STEPS = [
    {"id": "A1", "label": "品牌信息采集", "threshold": 0.4},
    {"id": "A2", "label": "用户画像生成", "threshold": 0.6},
    {"id": "A3", "label": "问题模拟生成", "threshold": 0.75},
    {"id": "A4", "label": "AI答案抓取", "threshold": 0.95},
    {"id": "A5", "label": "数据分析报告", "threshold": 1.0},
]

# TPAOR 阶段中文到英文的映射
TPAOR_PHASE_MAP = {
    "思考": "thought",
    "规划": "plan",
    "行动": "action",
    "观察": "observation",
    "回复": "response",
}

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connection manager."""

    def __init__(self):
        # session_id -> Set[WebSocket]
        self.session_connections: dict[str, set[WebSocket]] = {}
        # WebSocket -> session_id
        self.ws_to_session: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Register connection."""
        # Note: websocket.accept() should be called before this method
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        self.session_connections[session_id].add(websocket)
        self.ws_to_session[websocket] = session_id
        logger.info(
            f"[WebSocket] Client connected: {id(websocket)} to session {session_id}"
        )

    def disconnect(self, websocket: WebSocket):
        """Unregister connection."""
        session_id = self.ws_to_session.pop(websocket, None)
        if session_id and session_id in self.session_connections:
            self.session_connections[session_id].discard(websocket)
            if not self.session_connections[session_id]:
                del self.session_connections[session_id]
        logger.info(
            f"[WebSocket] Client disconnected: {id(websocket)} from session {session_id}"
        )

    def get_session_id(self, websocket: WebSocket) -> str | None:
        """Get session ID for a WebSocket connection."""
        return self.ws_to_session.get(websocket)

    async def emit_to_session(self, session_id: str, event: str, data: dict):
        """Emit event to all connections in a session."""
        if session_id not in self.session_connections:
            return

        disconnected = []
        for ws in list(self.session_connections[session_id]):
            try:
                await ws.send_json({"event": event, "data": data})
            except Exception as e:
                logger.error(f"[WebSocket] Error emitting to {id(ws)}: {e}")
                disconnected.append(ws)

        # Clean up disconnected WebSockets
        for ws in disconnected:
            self.disconnect(ws)

    async def emit_to_websocket(self, websocket: WebSocket, event: str, data: dict):
        """Emit event to a specific WebSocket connection."""
        try:
            await websocket.send_json({"event": event, "data": data})
        except Exception as e:
            logger.error(f"[WebSocket] Error emitting to {id(websocket)}: {e}")
            self.disconnect(websocket)


# Global manager instance
manager = ConnectionManager()


# ========== Event Handlers ==========


async def handle_user_message(websocket: WebSocket, session_id: str, data: dict):
    """Handle user message using LangGraph workflow.

    This replaces the old GeneralReActAgent-based implementation.
    """
    logger.info(f"[WebSocket] user_message event from session: {session_id}")
    logger.info(f"[WebSocket] data: {data}")

    # Use new LangGraph handler
    from app.api.v1.websocket_langgraph import handle_user_message_langgraph

    await handle_user_message_langgraph(websocket, session_id, data)


async def handle_confirmation(websocket: WebSocket, session_id: str, data: dict):
    """Handle confirmation using LangGraph workflow."""
    # Use new LangGraph handler
    from app.api.v1.websocket_langgraph import handle_confirmation_langgraph

    await handle_confirmation_langgraph(websocket, session_id, data)


async def handle_stop(websocket: WebSocket, session_id: str):
    """Handle stop request."""
    logger.info(f"[WebSocket] Stop requested from session {session_id}")

    # TODO: Stop execution through AgentOrchestrator
    await manager.emit_to_websocket(
        websocket,
        "execution_stopped",
        {
            "completed_stages": [],
            "pending_stages": [],
        },
    )


async def handle_recall(websocket: WebSocket, session_id: str, data: dict):
    """Handle recall (rollback + re-execute) using LangGraph workflow."""
    logger.info(f"[WebSocket] recall event from session: {session_id}")

    from app.api.v1.websocket_langgraph import handle_recall_langgraph

    await handle_recall_langgraph(websocket, session_id, data)


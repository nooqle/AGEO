"""WebSocket connection manager for real-time event streaming."""

from typing import Dict, Set
from fastapi import WebSocket
from datetime import datetime, timezone


class WebSocketManager:
    """WebSocket connection manager."""

    def __init__(self):
        # session_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Establish connection.

        Args:
            websocket: WebSocket connection
            session_id: Session ID
        """
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        """Disconnect.

        Args:
            websocket: WebSocket connection
            session_id: Session ID
        """
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def send_to_session(self, session_id: str, message: dict):
        """Send message to all connections in a session.

        Args:
            session_id: Session ID
            message: Message to send
        """
        if session_id in self.active_connections:
            dead_connections = set()
            for websocket in self.active_connections[session_id]:
                try:
                    await websocket.send_json(message)
                except Exception:
                    dead_connections.add(websocket)

            # Clean up dead connections
            for ws in dead_connections:
                self.active_connections[session_id].discard(ws)

    async def broadcast_event(self, session_id: str, event_type: str, payload: dict):
        """Broadcast event.

        Args:
            session_id: Session ID
            event_type: Event type
            payload: Event payload
        """
        message = {
            "event": event_type,
            "data": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
        }
        await self.send_to_session(session_id, message)

    async def emit_to_websocket(self, websocket: WebSocket, event: str, data: dict):
        """Emit event to a specific WebSocket connection."""
        try:
            await websocket.send_json({"event": event, "data": data})
        except Exception:
            pass


# Global instance
ws_manager = WebSocketManager()

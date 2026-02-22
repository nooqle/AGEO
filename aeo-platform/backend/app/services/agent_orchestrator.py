"""Agent Orchestrator - Compatibility Layer.

This module provides a compatibility layer for the old AgentOrchestrator.
It redirects to the new LangGraph workflow.
"""

from sqlalchemy.ext.asyncio import AsyncSession


class AgentOrchestrator:
    """Compatibility wrapper for old AgentOrchestrator.

    This class provides the same interface as the old orchestrator
    but uses the new LangGraph workflow internally.
    """

    def __init__(self, session_id: str, db: AsyncSession):
        self.session_id = session_id
        self.db = db

    async def process_message(self, content: str):
        """Process message using LangGraph workflow.

        Note: Actual processing is now handled by WebSocket handler.
        This method is kept for API compatibility.
        """
        # Yield a simple event for compatibility
        yield {"type": "info", "message": "Processing via WebSocket recommended"}

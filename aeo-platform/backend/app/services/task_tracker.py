"""Task tracker for monitoring Celery task progress.

This module provides real-time tracking of async task execution.
"""

import json
from typing import Any, Optional
from datetime import datetime

from app.core.redis_client import get_redis_client


class TaskTracker:
    """Track Celery task progress and status."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.redis = get_redis_client()
        self.key_prefix = f"task:{session_id}"

    def _get_key(self, task_id: str) -> str:
        """Get Redis key for task."""
        return f"{self.key_prefix}:{task_id}"

    def start_task(
        self, task_id: str, task_type: str, total_items: int, metadata: Optional[dict] = None
    ) -> None:
        """Mark task as started."""
        data = {
            "task_id": task_id,
            "task_type": task_type,
            "status": "started",
            "progress": 0,
            "total_items": total_items,
            "completed_items": 0,
            "started_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self.redis.setex(
            self._get_key(task_id), 3600, json.dumps(data)  # 1 hour expiry
        )

    def update_progress(
        self,
        task_id: str,
        completed_items: int,
        current_item: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        """Update task progress."""
        key = self._get_key(task_id)
        data = self.redis.get(key)

        if data:
            task_data = json.loads(data)
            task_data["completed_items"] = completed_items
            task_data["progress"] = (completed_items / task_data["total_items"]) * 100

            if current_item:
                task_data["current_item"] = current_item
            if message:
                task_data["message"] = message

            self.redis.setex(key, 3600, json.dumps(task_data))

    def complete_task(self, task_id: str, result: Any = None) -> None:
        """Mark task as completed."""
        key = self._get_key(task_id)
        data = self.redis.get(key)

        if data:
            task_data = json.loads(data)
            task_data["status"] = "completed"
            task_data["progress"] = 100
            task_data["completed_items"] = task_data["total_items"]
            task_data["completed_at"] = datetime.now().isoformat()

            if result:
                task_data["result"] = result

            self.redis.setex(key, 3600, json.dumps(task_data))

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark task as failed."""
        key = self._get_key(task_id)
        data = self.redis.get(key)

        if data:
            task_data = json.loads(data)
            task_data["status"] = "failed"
            task_data["error"] = error
            task_data["failed_at"] = datetime.now().isoformat()

            self.redis.setex(key, 3600, json.dumps(task_data))

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """Get current task status."""
        key = self._get_key(task_id)
        data = self.redis.get(key)

        if data:
            return json.loads(data)
        return None

    def get_all_tasks(self) -> list[dict]:
        """Get all tasks for session."""
        pattern = f"{self.key_prefix}:*"
        keys = self.redis.keys(pattern)

        tasks = []
        for key in keys:
            data = self.redis.get(key)
            if data:
                tasks.append(json.loads(data))

        return tasks


def get_task_tracker(session_id: str) -> TaskTracker:
    """Get task tracker instance."""
    return TaskTracker(session_id)

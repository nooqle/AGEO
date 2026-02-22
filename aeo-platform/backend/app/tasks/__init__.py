"""Celery tasks package."""

from app.tasks.fetch_tasks import fetch_answers_task

__all__ = ["fetch_answers_task"]

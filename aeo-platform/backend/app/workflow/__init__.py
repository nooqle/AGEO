"""LangGraph workflow for Specta AI platform."""

from app.workflow.state import AgentState

__all__ = ["AgentState", "get_compiled_workflow"]


def __getattr__(name: str):
    if name == "get_compiled_workflow":
        from app.workflow.graph import get_compiled_workflow

        return get_compiled_workflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

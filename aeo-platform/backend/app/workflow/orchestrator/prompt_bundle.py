"""Orchestrator prompt bundle construction (P2 knife 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.workflow.prompt_assembly import PromptAssembly
from app.workflow.prompt_fingerprint import fingerprint_text

@dataclass(frozen=True)
class OrchestratorPromptBundle:
    """Rendered prompt parts for one orchestrator LLM call."""

    system_prompt: str
    runtime_reminder_message: str
    runtime_reminder_enabled: bool
    static_prompt_hash: str = ""
    runtime_reminder_hash: str = ""
    prompt_layer_manifest: dict[str, Any] | None = None

def _runtime_reminder_message_enabled() -> bool:
    return bool(
        getattr(get_settings(), "ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED", False)
    )

def _wrap_runtime_reminder_message(message: str) -> str:
    body = str(message or "").strip()
    if not body:
        return ""
    return f"<本轮系统提醒>\n{body}\n</本轮系统提醒>"

def _build_orchestrator_prompt_bundle_from_assembly(
    assembly: PromptAssembly,
) -> OrchestratorPromptBundle:
    """Build cache-friendly prompt parts while preserving the legacy default."""

    runtime_enabled = _runtime_reminder_message_enabled()
    static_system_prompt = assembly.render_static_system_prompt()
    runtime_reminder_source = assembly.render_runtime_reminder_message()
    layer_manifest = assembly.cache_layer_manifest(
        runtime_reminder_enabled=runtime_enabled
    )
    if not runtime_enabled:
        system_prompt = assembly.render()
        return OrchestratorPromptBundle(
            system_prompt=system_prompt,
            runtime_reminder_message="",
            runtime_reminder_enabled=False,
            static_prompt_hash=fingerprint_text(static_system_prompt),
            runtime_reminder_hash="",
            prompt_layer_manifest=layer_manifest,
        )

    runtime_reminder_message = _wrap_runtime_reminder_message(runtime_reminder_source)
    return OrchestratorPromptBundle(
        system_prompt=static_system_prompt,
        runtime_reminder_message=runtime_reminder_message,
        runtime_reminder_enabled=True,
        static_prompt_hash=fingerprint_text(static_system_prompt),
        runtime_reminder_hash=fingerprint_text(runtime_reminder_message),
        prompt_layer_manifest=layer_manifest,
    )


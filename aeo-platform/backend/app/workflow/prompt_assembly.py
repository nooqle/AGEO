"""Structured prompt assembly primitives for orchestrator and executors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PromptSection:
    """A named prompt section with optional metadata."""

    key: str
    title: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_body(self) -> str:
        return str(self.body or "").strip()

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "body": self.normalized_body(),
            "metadata": dict(self.metadata or {}),
        }

    def render(self) -> str:
        body = self.normalized_body()
        if not body:
            return ""
        if not self.title:
            return body
        return f"## {self.title}\n{body}"


@dataclass(frozen=True)
class PromptAssembly:
    """Composable prompt assembly with stable section groups."""

    base_policy_sections: tuple[PromptSection, ...] = ()
    skill_sections: tuple[PromptSection, ...] = ()
    runtime_context_sections: tuple[PromptSection, ...] = ()
    runtime_reminder_sections: tuple[PromptSection, ...] = ()

    def ordered_sections(self) -> list[PromptSection]:
        sections: list[PromptSection] = []
        for group in (
            self.base_policy_sections,
            self.skill_sections,
            self.runtime_context_sections,
            self.runtime_reminder_sections,
        ):
            sections.extend(section for section in group if section.normalized_body())
        return sections

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "base_policy_sections": [
                section.to_state_payload() for section in self.base_policy_sections
            ],
            "skill_sections": [
                section.to_state_payload() for section in self.skill_sections
            ],
            "runtime_context_sections": [
                section.to_state_payload() for section in self.runtime_context_sections
            ],
            "runtime_reminder_sections": [
                section.to_state_payload()
                for section in self.runtime_reminder_sections
            ],
        }

    def render(self) -> str:
        rendered = [section.render() for section in self.ordered_sections()]
        return "\n\n".join(part for part in rendered if part).strip()

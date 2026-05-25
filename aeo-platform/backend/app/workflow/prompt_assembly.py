"""Structured prompt assembly primitives for orchestrator and executors."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import Any, Literal


PromptDropPolicy = Literal["keep", "compress", "drop"]

_GROUP_BUDGETS: dict[str, int] = {
    "base_policy_sections": 2200,
    "skill_sections": 900,
    "runtime_context_sections": 2200,
    "runtime_reminder_sections": 500,
}
_GROUP_ORDER: tuple[str, ...] = (
    "base_policy_sections",
    "skill_sections",
    "runtime_context_sections",
    "runtime_reminder_sections",
)
_SOFT_PROMPT_LIMIT = 5200
_HARD_PROMPT_LIMIT = 6500
_SECTION_SEPARATOR = "\n\n"


def _fingerprint_text(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _metadata_int(
    metadata: dict[str, Any],
    key: str,
    default: int,
) -> int:
    raw_value = metadata.get(key, default)
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _metadata_drop_policy(
    metadata: dict[str, Any],
    key: str,
    default: PromptDropPolicy,
) -> PromptDropPolicy:
    raw_value = str(metadata.get(key, default) or "").strip()
    if raw_value in {"keep", "compress", "drop"}:
        return raw_value  # type: ignore[return-value]
    return default


@dataclass(frozen=True)
class PromptSection:
    """A named prompt section with optional metadata."""

    key: str
    title: str
    body: str
    priority: int = 100
    budget_cost: int = 0
    drop_policy: PromptDropPolicy = "compress"
    group: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_body(self) -> str:
        return str(self.body or "").strip()

    def header(self) -> str:
        if not self.title:
            return ""
        return f"## {self.title}\n"

    def estimated_cost(self) -> int:
        if self.budget_cost > 0:
            return self.budget_cost
        return len(self.render())

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "body": self.normalized_body(),
            "priority": self.priority,
            "budget_cost": self.estimated_cost(),
            "drop_policy": self.drop_policy,
            "group": self.group,
            "metadata": dict(self.metadata or {}),
        }

    def render(self) -> str:
        body = self.normalized_body()
        if not body:
            return ""
        if not self.title:
            return body
        return f"{self.header()}{body}"

    def cache_layer(self) -> str:
        explicit = str((self.metadata or {}).get("cache_layer") or "").strip()
        if explicit:
            return explicit
        if self.group == "base_policy_sections":
            return "static_policy"
        if self.group == "skill_sections":
            if (self.metadata or {}).get("static_prompt") is False:
                return "dynamic_tool_surface"
            if (self.metadata or {}).get("runtime_body") is not None:
                return "static_skill_surface"
            return "static_skill_surface"
        if self.group == "runtime_context_sections":
            return "dynamic_context"
        if self.group == "runtime_reminder_sections":
            return "ephemeral_runtime_guard"
        return "unknown"


def _compact_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if limit <= 0 or not text:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


def _separator_cost(count: int) -> int:
    return max(0, count - 1) * len(_SECTION_SEPARATOR)


def _render_section_with_limit(section: PromptSection, limit: int) -> str:
    full = section.render()
    if len(full) <= limit:
        return full
    if section.drop_policy == "keep":
        return full

    header = section.header()
    if not section.title:
        header = ""
    available_body = limit - len(header)
    min_body_chars = 48 if section.drop_policy == "compress" else 24
    if available_body < min_body_chars:
        return ""

    compact_body = _compact_text(section.normalized_body(), available_body)
    if not compact_body:
        return ""
    return f"{header}{compact_body}" if header else compact_body


def _group_total_length(rendered_parts: list[str]) -> int:
    if not rendered_parts:
        return 0
    return sum(len(part) for part in rendered_parts) + _separator_cost(
        len(rendered_parts)
    )


def _render_group_with_budget(
    sections: tuple[PromptSection, ...],
    *,
    budget: int,
) -> list[str]:
    filtered = [section for section in sections if section.normalized_body()]
    if not filtered:
        return []

    keep_indices = list(range(len(filtered)))
    rendered = {index: filtered[index].render() for index in keep_indices}

    def _current_total() -> int:
        return _group_total_length(
            [rendered[index] for index in keep_indices if rendered[index]]
        )

    while _current_total() > budget:
        droppable = [
            index for index in keep_indices if filtered[index].drop_policy == "drop"
        ]
        if not droppable:
            break
        victim = max(
            droppable,
            key=lambda index: (filtered[index].priority, len(rendered.get(index, ""))),
        )
        keep_indices.remove(victim)
        rendered.pop(victim, None)

    if not keep_indices:
        return []

    overflow = _current_total() - budget
    if overflow > 0:
        compressible = sorted(
            [
                index
                for index in keep_indices
                if filtered[index].drop_policy in {"compress", "drop"}
            ],
            key=lambda index: (filtered[index].priority, len(rendered.get(index, ""))),
            reverse=True,
        )
        for index in compressible:
            current = rendered.get(index, "")
            if not current:
                continue
            minimum_length = len(filtered[index].header()) + (
                48 if filtered[index].drop_policy == "compress" else 24
            )
            minimum_length = max(minimum_length, len(filtered[index].header()) + 1)
            available_reduction = len(current) - minimum_length
            if available_reduction <= 0:
                continue
            reduction = min(overflow, available_reduction)
            candidate = _render_section_with_limit(
                filtered[index], len(current) - reduction
            )
            if not candidate:
                if filtered[index].drop_policy == "drop":
                    keep_indices.remove(index)
                    rendered.pop(index, None)
                    overflow = _current_total() - budget
                    if overflow <= 0:
                        break
                continue
            rendered[index] = candidate
            overflow = _current_total() - budget
            if overflow <= 0:
                break

    return [rendered[index] for index in keep_indices if rendered.get(index)]


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
                section.to_state_payload() for section in self.runtime_reminder_sections
            ],
        }

    def _render_group_names(
        self,
        group_order: tuple[str, ...],
        section_overrides: dict[str, tuple[PromptSection, ...]] | None = None,
    ) -> str:
        grouped_rendered: dict[str, list[str]] = {}
        for group_name in group_order:
            sections = tuple(
                (section_overrides or {}).get(group_name, getattr(self, group_name))
            )
            grouped_rendered[group_name] = _render_group_with_budget(
                sections,
                budget=_GROUP_BUDGETS[group_name],
            )

        ordered_parts: list[str] = []
        for group_name in group_order:
            ordered_parts.extend(grouped_rendered[group_name])

        total_length = _group_total_length(ordered_parts)
        if total_length > _SOFT_PROMPT_LIMIT:
            for group_name in (
                "runtime_reminder_sections",
                "runtime_context_sections",
                "skill_sections",
            ):
                if group_name not in grouped_rendered:
                    continue
                current_parts = grouped_rendered[group_name]
                if not current_parts:
                    continue
                overflow = total_length - _SOFT_PROMPT_LIMIT
                if overflow <= 0:
                    break
                current_length = _group_total_length(current_parts)
                target_budget = max(0, current_length - overflow)
                grouped_rendered[group_name] = _render_group_with_budget(
                    tuple(getattr(self, group_name)),
                    budget=target_budget,
                )
                ordered_parts = []
                for ordered_group in group_order:
                    ordered_parts.extend(grouped_rendered[ordered_group])
                total_length = _group_total_length(ordered_parts)

        if total_length > _HARD_PROMPT_LIMIT:
            hard_clamped: list[str] = []
            remaining = _HARD_PROMPT_LIMIT
            for part in ordered_parts:
                if not part or remaining <= 0:
                    continue
                separator_cost = len(_SECTION_SEPARATOR) if hard_clamped else 0
                if remaining <= separator_cost:
                    break
                allowed = remaining - separator_cost
                compact = _compact_text(part, allowed)
                if not compact:
                    continue
                hard_clamped.append(compact)
                remaining -= separator_cost + len(compact)
            ordered_parts = hard_clamped

        return _SECTION_SEPARATOR.join(part for part in ordered_parts if part).strip()

    def _static_skill_sections(self) -> tuple[PromptSection, ...]:
        static_sections: list[PromptSection] = []
        for section in self.skill_sections:
            metadata = section.metadata or {}
            if metadata.get("static_prompt") is False:
                continue
            static_body = metadata.get("static_body")
            if static_body is not None:
                static_sections.append(
                    replace(
                        section,
                        body=str(static_body),
                        metadata={
                            **metadata,
                            "cache_layer": metadata.get(
                                "static_cache_layer",
                                "static_skill_surface",
                            ),
                            "volatility": metadata.get(
                                "static_volatility",
                                "deployment_static",
                            ),
                        },
                    )
                )
                continue
            static_sections.append(section)
        return tuple(static_sections)

    def _runtime_skill_overlay_sections(self) -> tuple[PromptSection, ...]:
        runtime_sections: list[PromptSection] = []
        for section in self.skill_sections:
            metadata = section.metadata or {}
            runtime_body = metadata.get("runtime_body")
            if runtime_body is not None:
                body = str(runtime_body or "").strip()
                if body:
                    runtime_sections.append(
                        replace(
                            section,
                            body=body,
                            priority=_metadata_int(
                                metadata,
                                "runtime_priority",
                                section.priority,
                            ),
                            drop_policy=_metadata_drop_policy(
                                metadata,
                                "runtime_drop_policy",
                                section.drop_policy,
                            ),
                            budget_cost=_metadata_int(
                                metadata,
                                "runtime_budget_cost",
                                section.budget_cost,
                            ),
                            metadata={
                                **metadata,
                                "cache_layer": metadata.get(
                                    "runtime_cache_layer",
                                    "dynamic_tool_surface",
                                ),
                                "volatility": metadata.get(
                                    "runtime_volatility",
                                    "per_turn",
                                ),
                            },
                        )
                    )
                continue
            if metadata.get("static_prompt") is False:
                runtime_sections.append(
                    replace(
                        section,
                        priority=_metadata_int(
                            metadata,
                            "runtime_priority",
                            section.priority,
                        ),
                        drop_policy=_metadata_drop_policy(
                            metadata,
                            "runtime_drop_policy",
                            section.drop_policy,
                        ),
                        budget_cost=_metadata_int(
                            metadata,
                            "runtime_budget_cost",
                            section.budget_cost,
                        ),
                    )
                )
        return tuple(runtime_sections)

    def render_static_system_prompt(self) -> str:
        """Render cache-friendly policy and skill sections for the system message."""

        return self._render_group_names(
            ("base_policy_sections", "skill_sections"),
            section_overrides={"skill_sections": self._static_skill_sections()},
        )

    def render_runtime_reminder_message(self) -> str:
        """Render dynamic per-turn context that can be appended as a reminder."""

        runtime_context_sections = (
            *self._runtime_skill_overlay_sections(),
            *self.runtime_context_sections,
        )
        return self._render_group_names(
            ("runtime_context_sections", "runtime_reminder_sections"),
            section_overrides={
                "runtime_context_sections": runtime_context_sections,
            },
        )

    def render(self) -> str:
        return self._render_group_names(_GROUP_ORDER)

    def cache_layer_manifest(self, *, runtime_reminder_enabled: bool) -> dict[str, Any]:
        """Return body-free prompt layering metadata for cache observability."""

        static_system_prompt = self.render_static_system_prompt()
        runtime_reminder_message = self.render_runtime_reminder_message()
        legacy_system_prompt = self.render()
        static_sections = (
            *self.base_policy_sections,
            *self._static_skill_sections(),
        )
        runtime_sections = (
            *self._runtime_skill_overlay_sections(),
            *self.runtime_context_sections,
            *self.runtime_reminder_sections,
        )
        if runtime_reminder_enabled:
            section_entries = [
                *(
                    _section_cache_manifest_entry(section, placement="system")
                    for section in static_sections
                    if section.normalized_body()
                ),
                *(
                    _section_cache_manifest_entry(
                        section,
                        placement="runtime_reminder",
                    )
                    for section in runtime_sections
                    if section.normalized_body()
                ),
            ]
        else:
            section_entries = [
                _section_cache_manifest_entry(section, placement="legacy_system")
                for section in self.ordered_sections()
                if section.normalized_body()
            ]

        return {
            "mode": (
                "runtime_reminder_split"
                if runtime_reminder_enabled
                else "legacy_single_system"
            ),
            "budgets": dict(_GROUP_BUDGETS),
            "soft_prompt_limit": _SOFT_PROMPT_LIMIT,
            "hard_prompt_limit": _HARD_PROMPT_LIMIT,
            "static_system": {
                "fingerprint": _fingerprint_text(static_system_prompt),
                "length": len(static_system_prompt),
            },
            "runtime_reminder": {
                "fingerprint": _fingerprint_text(runtime_reminder_message),
                "length": len(runtime_reminder_message),
                "enabled": runtime_reminder_enabled,
            },
            "legacy_system": {
                "fingerprint": _fingerprint_text(legacy_system_prompt),
                "length": len(legacy_system_prompt),
            },
            "sections": section_entries,
        }


def _section_cache_manifest_entry(
    section: PromptSection,
    *,
    placement: str,
) -> dict[str, Any]:
    rendered = section.render()
    metadata = dict(section.metadata or {})
    return {
        "key": section.key,
        "title": section.title,
        "group": section.group,
        "placement": placement,
        "cache_layer": section.cache_layer(),
        "volatility": metadata.get("volatility", "unspecified"),
        "source": metadata.get("source", ""),
        "priority": section.priority,
        "drop_policy": section.drop_policy,
        "estimated_cost": section.estimated_cost(),
        "rendered_length": len(rendered),
        "fingerprint": _fingerprint_text(rendered),
    }

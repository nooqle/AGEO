"""3c-C1: natural language → topology ops (rule mode only).

No LLM. Output is always the frozen B ops vocabulary so the existing
preview/apply pipeline can consume it without a second schema.

Cache note (C2): when LLM is added, load static rules from
``prompts/topology_ops_compiler.md`` as a stable system prefix; put the
user utterance + topology summary at the *end* of the message list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.workflow.topology_patch import expand_intent
from app.workflow.topology_resolver import (
    CANVAS_PLATFORM_IDS,
    EDGE_PROJECTION_REPORT,
)

# Stable platform aliases (domain UI words OK here; ops stay domain-agnostic).
_PLATFORM_ALIASES: dict[str, tuple[str, ...]] = {
    "doubao": ("豆包", "doubao"),
    "kimi": ("kimi", "月之暗面"),
    "deepseek": ("deepseek", "深度求索"),
    "hunyuan": ("元宝", "hunyuan", "混元", "腾讯元宝"),
}

_SKIP_VERBS = ("跳过", "不要", "别跑", "禁用", "关掉", "关闭", "去掉", "取消")
_EXAMPLES = (
    "跳过豆包",
    "不要跑 kimi",
    "恢复全部平台",
    "加一个图谱分析节点",
    "这次不生成报告",
)


@dataclass(frozen=True)
class CompileResult:
    ops: list[dict[str, Any]]
    mode: str  # "rule"
    matched: str
    intent_id: str | None = None
    confidence: float = 1.0


def _norm(text: str) -> str:
    """Collapse whitespace; keep case-fold for latin only."""
    t = re.sub(r"\s+", "", str(text or "").strip())
    return t.casefold()


def compile_nl_to_ops(
    text: str,
    base: dict[str, Any] | None = None,
) -> CompileResult:
    """Compile a short Chinese/English instruction into topology ops.

    Raises ValueError with a user-facing Chinese message when unmatched.
    """
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("请输入编排指令，例如：" + "；".join(_EXAMPLES))
    if len(raw) > 500:
        raise ValueError("指令过长（上限 500 字），请缩短后再试")

    n = _norm(raw)

    # --- Intent presets (highest priority) ---
    if any(
        k in n
        for k in (
            "跳过豆包",
            "不要豆包",
            "别跑豆包",
            "禁用豆包",
            "去掉豆包",
            "skipdoubao",
            "nodoubao",
        )
    ):
        return CompileResult(
            ops=expand_intent("skip_doubao", base),
            mode="rule",
            matched="skip_doubao",
            intent_id="skip_doubao",
        )

    if any(
        k in n
        for k in (
            "恢复全部平台",
            "打开全部平台",
            "启用全部平台",
            "全部平台都开",
            "恢复所有平台",
            "enableallplatforms",
        )
    ):
        return CompileResult(
            ops=expand_intent("enable_all_platforms", base),
            mode="rule",
            matched="enable_all_platforms",
            intent_id="enable_all_platforms",
        )

    if any(
        k in n
        for k in (
            "加分析节点",
            "加一个分析",
            "添加分析节点",
            "图谱分析",
            "图谱解读",
            "挂一个分析",
            "增加分析节点",
            "addanalysis",
        )
    ):
        return CompileResult(
            ops=expand_intent("add_projection_analysis", base),
            mode="rule",
            matched="add_projection_analysis",
            intent_id="add_projection_analysis",
        )

    if any(
        k in n
        for k in (
            "不生成报告",
            "不要报告",
            "跳过报告",
            "断开报告",
            "别出报告",
            "noreport",
        )
    ):
        return CompileResult(
            ops=[
                {
                    "op": "remove_builtin_edge",
                    "edge_id": EDGE_PROJECTION_REPORT,
                }
            ],
            mode="rule",
            matched="disable_report",
            intent_id=None,
        )

    # --- Generic: skip/disable one platform ---
    for platform in CANVAS_PLATFORM_IDS:
        aliases = _PLATFORM_ALIASES.get(platform, (platform,))
        for alias in aliases:
            a = _norm(alias)
            for verb in _SKIP_VERBS:
                if f"{_norm(verb)}{a}" in n or f"{a}{_norm(verb)}" in n:
                    return CompileResult(
                        ops=[{"op": "disable_platform", "platform": platform}],
                        mode="rule",
                        matched=f"disable_platform:{platform}",
                        intent_id=None,
                    )
            # "不要跑kimi" style already covered by verb+alias after space strip
            if f"跑{a}" in n and any(_norm(v) in n for v in ("不要", "别", "别再")):
                return CompileResult(
                    ops=[{"op": "disable_platform", "platform": platform}],
                    mode="rule",
                    matched=f"disable_platform:{platform}",
                    intent_id=None,
                )

    raise ValueError(
        "无法识别该编排指令。可试："
        + "；".join(_EXAMPLES)
        + "。更复杂的说法将在后续智能编译支持。"
    )

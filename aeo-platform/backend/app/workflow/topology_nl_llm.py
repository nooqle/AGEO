"""3c-C2: LLM-backed NL → topology ops (cache-friendly message layout).

Message layout (prompt cache):
1. **Stable system prefix** — full content of ``prompts/topology_ops_compiler.md``
   (ops schema, role, output JSON). Rarely edited.
2. **Trailing user message** — only the utterance + compact topology summary.

Never put entity ids / live topology into the system prompt.
Validation always goes through ``apply_topology_ops`` before return.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.workflow.topology_nl_compiler import CompileResult, compile_nl_to_ops
from app.workflow.topology_patch import ALLOWED_OPS, apply_topology_ops

logger = logging.getLogger(__name__)

STABLE_PROMPT_NAME = "topology_ops_compiler"


def _parse_json_object(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if not text:
        return None
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def compact_topology_for_compiler(base: dict[str, Any] | None) -> dict[str, Any]:
    """Small, stable-shaped topology digest for the trailing user message."""
    base = base if isinstance(base, dict) else {}
    nodes = []
    for n in base.get("customNodes") or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        cfg = n.get("config") if isinstance(n.get("config"), dict) else {}
        nodes.append(
            {
                "id": str(n.get("id")),
                "type": str(n.get("type") or ""),
                "label": str(cfg.get("label") or "")[:40],
            }
        )
    edges = []
    for e in base.get("customEdges") or []:
        if not isinstance(e, dict):
            continue
        edges.append(
            {
                "id": str(e.get("id") or ""),
                "source": str(e.get("source") or ""),
                "target": str(e.get("target") or ""),
            }
        )
    return {
        "removedEdgeIds": [
            str(x) for x in (base.get("removedEdgeIds") or []) if isinstance(x, str)
        ][:40],
        "customNodes": nodes[:20],
        "customEdges": edges[:40],
    }


def _load_stable_system_prompt() -> str:
    from app.core.utils import load_prompt_template

    return load_prompt_template(STABLE_PROMPT_NAME).strip()


def _filter_ops(raw_ops: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_ops, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op") or "").strip()
        if op not in ALLOWED_OPS:
            continue
        out.append(dict(item))
    return out


async def compile_nl_with_llm(
    text: str,
    base: dict[str, Any] | None = None,
) -> CompileResult:
    """Call LLM with stable system + trailing user payload; validate ops."""
    from app.core.llm import get_llm_model

    raw = str(text or "").strip()
    if not raw:
        raise ValueError("请输入编排指令")

    system = _load_stable_system_prompt()
    user_payload = {
        "instruction": raw,
        "topology": compact_topology_for_compiler(base),
        "hint": (
            "Prefer smallest valid ops list. "
            "If unclear return {\"ops\":[],\"error\":\"cannot_compile\"}."
        ),
    }
    response = await get_llm_model().async_call(
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False),
            },
        ],
        temperature=0.1,
        max_tokens=900,
        thinking_enabled=False,
        timeout=60,
    )
    parsed = _parse_json_object(getattr(response, "content", None))
    if not parsed:
        raise ValueError("智能编译未返回可解析的 JSON")
    if parsed.get("error") == "cannot_compile" or not parsed.get("ops"):
        raise ValueError(
            str(parsed.get("error") or "无法识别该编排指令，请换更具体的说法")
        )

    ops = _filter_ops(parsed.get("ops"))
    if not ops:
        raise ValueError("智能编译未产出有效 ops")

    # Structural validation (raises ValueError on bad ops)
    apply_topology_ops(base, ops)

    intent_id = parsed.get("intent_id")
    intent_s = str(intent_id).strip() if intent_id else None
    return CompileResult(
        ops=ops,
        mode="llm",
        matched=str(parsed.get("rationale_short") or "llm_ops")[:80],
        intent_id=intent_s or None,
        confidence=0.7,
    )


async def compile_nl_auto(
    text: str,
    base: dict[str, Any] | None = None,
    *,
    allow_llm: bool = True,
) -> CompileResult:
    """Rule-first, then LLM when rules miss (C2 hybrid)."""
    try:
        return compile_nl_to_ops(text, base)
    except ValueError as rule_exc:
        if not allow_llm:
            raise
        try:
            return await compile_nl_with_llm(text, base)
        except Exception as llm_exc:
            logger.info(
                "[topology-nl] rule miss + llm fail rule=%s llm=%s",
                rule_exc,
                llm_exc,
            )
            # Prefer the rule message when it already lists examples;
            # otherwise surface a combined hint.
            rule_msg = str(rule_exc)
            llm_msg = str(llm_exc)
            if "无法识别" in rule_msg:
                raise ValueError(
                    f"{rule_msg}（智能编译也未成功：{llm_msg}）"
                ) from llm_exc
            raise ValueError(llm_msg) from llm_exc

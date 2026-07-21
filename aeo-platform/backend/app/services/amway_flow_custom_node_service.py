"""AmwayChina flow custom-node executors (blueprint 3b-1.5).

Two canvas custom node types:

- ``analysis``: second-pass interpretation over circle projection (+ optional
  report). Always builds a deterministic evidence baseline; then attempts an
  LLM enrichment controlled by the node's prompt / dimensions.
- ``content``: draft generation from lexicon + upstream analysis, driven by the
  node's prompt template (``{{centerTerm}}`` / ``{{entities}}`` / ``{{analysis}}``).

Design rules:
1. Execution kernel is domain-specific (Amway semantics live here / in prompts),
   not in the node contract registry.
2. LLM failure never hard-fails a run — degrade to deterministic / template
   output with an explicit ``mode`` + ``fallback_reason``.
3. Results are JSON-serializable and safe to store on
   ``FlowTopology.customNodes[].config``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

ANALYSIS_DIMENSIONS = ("platform", "entities", "risk")
DEFAULT_ANALYSIS_DIMENSIONS = list(ANALYSIS_DIMENSIONS)

DEFAULT_CONTENT_PROMPT_TEMPLATE = (
    "你是一位熟悉 {{centerTerm}} 品牌的内容策划。\n"
    "请基于以下输入起草一篇内容文案：\n"
    "- 实体词库：{{entities}}\n"
    "- 分析结论：{{analysis}}\n"
    "要求：口吻自然、避免夸大宣传、符合广告法规范。"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _answer_count(node: dict[str, Any]) -> int:
    raw = node.get("answer_count", node.get("mention_answer_count", 0))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def normalize_dimensions(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return list(DEFAULT_ANALYSIS_DIMENSIONS)
    cleaned = [str(item) for item in raw if str(item) in ANALYSIS_DIMENSIONS]
    return cleaned or list(DEFAULT_ANALYSIS_DIMENSIONS)


def build_deterministic_analysis(
    *,
    projection: dict[str, Any] | None,
    dimensions: list[str] | None = None,
) -> dict[str, Any]:
    """Port of the Phase 3a frontend deterministic analysis (zero LLM)."""
    dims = normalize_dimensions(dimensions)
    projection = _as_dict(projection)
    scope = _as_dict(projection.get("sample_scope"))
    nodes = [n for n in _as_list(projection.get("nodes")) if isinstance(n, dict)]
    cards: list[dict[str, Any]] = []

    if "platform" in dims:
        valid_platforms = [str(p) for p in _as_list(scope.get("valid_platform_names"))]
        requested = [str(p) for p in _as_list(scope.get("requested_platforms"))]
        missing = [p for p in requested if p not in valid_platforms]
        cards.append(
            {
                "title": "平台覆盖",
                "lines": [
                    (
                        f"有效回答 {int(scope.get('valid_answer_count') or 0)} 条，"
                        f"覆盖 {len(valid_platforms)}/"
                        f"{len(requested) or len(valid_platforms)} 个请求平台"
                    ),
                    (
                        f"产出平台：{'、'.join(valid_platforms)}"
                        if valid_platforms
                        else "暂无有效产出平台"
                    ),
                    (
                        f"未产出平台：{'、'.join(missing)}（建议下一轮重点观察）"
                        if missing
                        else "请求平台全部有产出"
                    ),
                ],
            }
        )

    if "entities" in dims:
        sorted_nodes = sorted(nodes, key=_answer_count, reverse=True)
        top = [n for n in sorted_nodes[:10] if _answer_count(n) > 0]
        by_track: dict[str, int] = {}
        for node in nodes:
            track = str(node.get("track") or "unknown")
            by_track[track] = by_track.get(track, 0) + 1
        lines = [
            (
                f"{index}. {str(node.get('term') or node.get('node_id') or '未命名')}"
                f"（{_answer_count(node)} 条回答）"
            )
            for index, node in enumerate(top, start=1)
        ]
        if not top:
            lines.append("暂无带回答计数的实体")
        track_text = (
            " / ".join(f"{track} {count}" for track, count in by_track.items()) or "无"
        )
        lines.append(f"轨道分布：{track_text}")
        cards.append({"title": "高频实体 Top 10", "lines": lines})

    if "risk" in dims:
        risk_nodes = [n for n in nodes if str(n.get("track") or "") == "risk"]
        regulatory = [
            n
            for n in nodes
            if "监管" in f"{n.get('term') or ''}{n.get('entity_type') or ''}"
            or "合规" in f"{n.get('term') or ''}{n.get('entity_type') or ''}"
        ]
        risk_map = _as_dict(projection.get("risk_map"))
        risk_names = [
            str(n.get("term") or "") for n in risk_nodes[:5] if n.get("term")
        ]
        risk_line = f"风险轨节点 {len(risk_nodes)} 个"
        if risk_names:
            risk_line += f"：{'、'.join(risk_names)}"
            if len(risk_nodes) > 5:
                risk_line += " 等"
        reg_line = (
            f"监管/合规相关 {len(regulatory)} 个："
            + "、".join(
                str(n.get("term") or "") for n in regulatory[:3] if n.get("term")
            )
            if regulatory
            else "未发现监管/合规相关节点"
        )
        map_line = (
            f"风险地图字段：{'、'.join(list(risk_map.keys())[:4])}"
            if risk_map
            else "风险地图暂无数据"
        )
        cards.append(
            {"title": "风险信号", "lines": [risk_line, reg_line, map_line]}
        )

    return {
        "generatedAt": _now_iso(),
        "dimensions": dims,
        "cards": cards,
        "mode": "deterministic",
    }


def _cards_to_text(cards: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for card in cards:
        title = str(card.get("title") or "").strip()
        lines = [str(line).strip() for line in _as_list(card.get("lines")) if str(line).strip()]
        if title:
            parts.append(f"## {title}")
        parts.extend(f"- {line}" for line in lines)
    return "\n".join(parts).strip()


def _report_excerpt(report: dict[str, Any] | None, limit: int = 2400) -> str:
    report = _as_dict(report)
    if not report:
        return ""
    chunks: list[str] = []
    for key in (
        "executive_summary",
        "summary",
        "title",
        "narrative",
    ):
        value = report.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
    findings = report.get("key_findings")
    if isinstance(findings, list):
        chunks.extend(str(item).strip() for item in findings[:8] if str(item).strip())
    sections = report.get("report_narrative_sections") or report.get("sections")
    if isinstance(sections, list):
        for section in sections[:6]:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or section.get("heading") or "").strip()
            body = str(
                section.get("body")
                or section.get("content")
                or section.get("text")
                or ""
            ).strip()
            if title and body:
                chunks.append(f"{title}: {body}")
            elif body:
                chunks.append(body)
    text = "\n".join(chunks).strip()
    return text[:limit]


def _projection_excerpt(projection: dict[str, Any] | None, limit: int = 2000) -> str:
    projection = _as_dict(projection)
    if not projection:
        return ""
    scope = _as_dict(projection.get("sample_scope"))
    nodes = [n for n in _as_list(projection.get("nodes")) if isinstance(n, dict)]
    top = sorted(nodes, key=_answer_count, reverse=True)[:12]
    lines = [
        f"有效回答: {scope.get('valid_answer_count')}",
        f"请求平台: {', '.join(str(p) for p in _as_list(scope.get('requested_platforms')))}",
        f"产出平台: {', '.join(str(p) for p in _as_list(scope.get('valid_platform_names')))}",
        "高频实体:",
    ]
    for node in top:
        if _answer_count(node) <= 0:
            continue
        lines.append(
            f"- {node.get('term') or node.get('node_id')} "
            f"(track={node.get('track')}, answers={_answer_count(node)})"
        )
    text = "\n".join(lines)
    return text[:limit]


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


def _normalize_llm_cards(raw: Any) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in _as_list(raw):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip() or "解读"
        lines = [
            str(line).strip()
            for line in _as_list(item.get("lines"))
            if str(line).strip()
        ]
        if not lines:
            body = str(item.get("body") or item.get("text") or "").strip()
            if body:
                lines = [body]
        if lines:
            cards.append({"title": title, "lines": lines[:12]})
    return cards[:8]


async def run_analysis_node(
    *,
    projection: dict[str, Any] | None,
    report: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Execute one analysis custom node; returns a result dict for config.result."""
    config = _as_dict(config)
    dimensions = normalize_dimensions(config.get("dimensions"))
    custom_prompt = str(config.get("prompt") or "").strip()
    deterministic = build_deterministic_analysis(
        projection=projection, dimensions=dimensions
    )
    if not use_llm:
        return deterministic

    try:
        from app.core.llm import get_llm_model

        evidence = _cards_to_text(list(deterministic.get("cards") or []))
        user_payload = {
            "dimensions": dimensions,
            "custom_prompt": custom_prompt
            or "请基于证据做二级解读，给出可执行洞察与风险提示。",
            "deterministic_evidence": evidence,
            "projection_excerpt": _projection_excerpt(projection),
            "report_excerpt": _report_excerpt(report),
            "output_schema": {
                "summary": "一句话总览",
                "cards": [{"title": "卡片标题", "lines": ["要点1", "要点2"]}],
            },
        }
        response = await get_llm_model().async_call(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是品牌关联圈层分析顾问。基于给定证据做二级解读，"
                        "只输出严格 JSON 对象，不要 Markdown 围栏。"
                        "cards 至少 1 张，每张 2-5 条可执行要点。"
                        "禁止编造不在证据中的具体数字。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            temperature=0.3,
            max_tokens=1600,
            thinking_enabled=False,
            timeout=90,
        )
        parsed = _parse_json_object(response.content)
        cards = _normalize_llm_cards((parsed or {}).get("cards"))
        if not cards:
            raise ValueError("LLM analysis returned no cards")
        summary = str((parsed or {}).get("summary") or "").strip()
        return {
            "generatedAt": _now_iso(),
            "dimensions": dimensions,
            "cards": cards,
            "summary": summary,
            "mode": "llm",
            "evidence_cards": deterministic.get("cards") or [],
            "prompt": custom_prompt,
        }
    except Exception as exc:  # pragma: no cover - network/provider path
        logger.warning("[flow-custom] analysis LLM failed: %s", exc)
        out = dict(deterministic)
        out["fallback_reason"] = f"llm_unavailable:{exc}"
        out["prompt"] = custom_prompt
        return out


def render_content_prompt(
    template: str | None,
    *,
    center_term: str,
    entities_text: str,
    analysis_text: str,
) -> str:
    text = str(template or "").strip() or DEFAULT_CONTENT_PROMPT_TEMPLATE
    return (
        text.replace("{{centerTerm}}", center_term or "品牌")
        .replace("{{entities}}", entities_text or "（暂无词库）")
        .replace("{{analysis}}", analysis_text or "（暂无分析结论）")
    )


def lexicon_entries_to_text(entries: list[Any], limit: int = 40) -> str:
    names: list[str] = []
    for entry in entries[:limit]:
        if isinstance(entry, dict):
            name = str(
                entry.get("canonical_name")
                or entry.get("name")
                or entry.get("term")
                or ""
            ).strip()
        else:
            name = str(
                getattr(entry, "canonical_name", None)
                or getattr(entry, "name", None)
                or ""
            ).strip()
        if name:
            names.append(name)
    return "、".join(names) if names else "（暂无词库）"


def analysis_result_to_text(result: dict[str, Any] | None) -> str:
    result = _as_dict(result)
    if not result:
        return ""
    summary = str(result.get("summary") or "").strip()
    cards_text = _cards_to_text(list(result.get("cards") or []))
    if summary and cards_text:
        return f"{summary}\n{cards_text}"
    return summary or cards_text


async def run_content_node(
    *,
    center_term: str,
    lexicon_entries: list[Any] | None = None,
    analysis_result: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Execute one content custom node; returns a result dict for config.result."""
    config = _as_dict(config)
    template = str(config.get("promptTemplate") or config.get("prompt_template") or "")
    entities_text = lexicon_entries_to_text(list(lexicon_entries or []))
    analysis_text = analysis_result_to_text(analysis_result)
    prompt_used = render_content_prompt(
        template,
        center_term=center_term,
        entities_text=entities_text,
        analysis_text=analysis_text,
    )
    if not use_llm:
        return {
            "generatedAt": _now_iso(),
            "mode": "template",
            "draft": prompt_used,
            "promptUsed": prompt_used,
        }

    try:
        from app.core.llm import get_llm_model

        response = await get_llm_model().async_call(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是合规的品牌内容策划。按用户给出的任务起草正文，"
                        "直接输出文案，不要标题元信息，不要 Markdown 代码围栏。"
                    ),
                },
                {"role": "user", "content": prompt_used},
            ],
            temperature=0.5,
            max_tokens=1800,
            thinking_enabled=False,
            timeout=90,
        )
        draft = str(response.content or "").strip()
        if not draft:
            raise ValueError("empty draft")
        return {
            "generatedAt": _now_iso(),
            "mode": "llm",
            "draft": draft,
            "promptUsed": prompt_used,
        }
    except Exception as exc:  # pragma: no cover - network/provider path
        logger.warning("[flow-custom] content LLM failed: %s", exc)
        return {
            "generatedAt": _now_iso(),
            "mode": "template",
            "draft": prompt_used,
            "promptUsed": prompt_used,
            "fallback_reason": f"llm_unavailable:{exc}",
        }


async def persist_custom_node_results(
    entity_id: Any,
    results_by_node_id: dict[str, dict[str, Any]],
) -> None:
    """Merge result payloads into flow_topologies.customNodes[].config."""
    raw = str(entity_id or "").strip()
    if not raw or not results_by_node_id:
        return
    try:
        from uuid import UUID

        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.flow_topology import FlowTopologyRecord
        from app.workflow.node_contracts import FlowTopology

        entity_uuid = UUID(raw)
    except Exception as exc:
        logger.warning("[flow-custom] persist skip bad entity_id=%s: %s", entity_id, exc)
        return

    try:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(FlowTopologyRecord).where(
                        FlowTopologyRecord.entity_id == entity_uuid
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                # No topology row yet — nothing to update; on-demand API creates
                # results in the response body and frontend dual-writes.
                return
            topology = FlowTopology.from_dict(row.topology if isinstance(row.topology, dict) else {})
            updated_nodes = []
            changed = False
            for node in topology.custom_nodes:
                patch = results_by_node_id.get(node.id)
                if not patch:
                    updated_nodes.append(node)
                    continue
                new_config = dict(node.config or {})
                new_config.update(patch)
                from app.workflow.node_contracts import TopologyNode

                updated_nodes.append(
                    TopologyNode(
                        id=node.id,
                        type=node.type,
                        position=dict(node.position or {}),
                        config=new_config,
                    )
                )
                changed = True
            if not changed:
                return
            from dataclasses import replace

            new_topology = replace(topology, custom_nodes=tuple(updated_nodes))
            wire = {
                "version": new_topology.version,
                "customNodes": [
                    {
                        "id": n.id,
                        "type": n.type,
                        "position": n.position,
                        "config": n.config,
                    }
                    for n in new_topology.custom_nodes
                ],
                "customEdges": [
                    {"id": e.id, "source": e.source, "target": e.target}
                    for e in new_topology.custom_edges
                ],
                "removedEdgeIds": list(new_topology.removed_edge_ids),
            }
            row.topology = wire
            row.version = int(row.version or 1) + 1
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive persistence
        logger.warning(
            "[flow-custom] persist results failed entity=%s: %s", entity_id, exc
        )

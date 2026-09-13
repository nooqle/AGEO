"""Entity extraction for Amway association-circle answer ingestion.

The service is intentionally deterministic: it matches the approved Amway
ontology against each captured answer and returns evidence-bound signals.
Calibration and report writing live in separate services.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.core.utils import sanitize_model_visible_text
from app.ontology import AmwayEntityDefinition, AmwayEntityOntologyRegistry
from app.ontology import load_default_amway_entity_ontology


EXTRACTION_SCHEMA_VERSION = "2026-09-06-semantic-v2"
IDENTITY_CONTEXT_WINDOW = 64
ANSWER_START_CHARS = 120
ANSWER_MIDDLE_CHARS = 420
CENTER_CONTEXT_WINDOW = 96
NEGATIVE_CONTEXT_CUES = (
    "风险",
    "质疑",
    "争议",
    "警惕",
    "谨慎",
    "高价",
    "变现难",
    "少数赚钱",
    "多数陪跑",
    "直销基因",
    "直销管理条例",
    "禁止多层计酬",
    "多层计酬",
    "枷锁",
    "传销",
    "拉人",
    "发展下线",
    "囤货",
    "熟人压力",
    "强推",
    "压力",
    "夸大",
    "智商税",
    "合规风险",
    "监管风险",
    "巨大影响",
    "现实中的风险",
    "理想图景",
    "不可靠",
    "不适合",
)
RISK_DENIAL_CUES = (
    "不是传销",
    "并非传销",
    "不属于传销",
    "不是非法传销",
    "不构成传销",
    "不能等同传销",
    "不能简单等同于传销",
    "不是拉人头",
    "并非拉人头",
    "不等于拉人头",
    "合法合规",
    "符合监管",
    "持有直销牌照",
    "有直销牌照",
    "取得直销经营许可",
    "获得直销经营许可",
)
REGULATION_POSITIVE_CUES = (
    "蓝帽子",
    "认证",
    "备案",
    "许可",
    "牌照",
    "合规",
    "符合监管",
    "合法合规",
)
COMPARISON_CONTEXT_CUES = (
    "比较",
    "对比",
    "相比",
    "替代",
    "竞品",
    "选择",
    "不如",
    "更适合",
    "会被拿来和",
    "vs",
)
NEGATIVE_CONTEXT_RISK_TYPES: set[str] = set()


@dataclass(frozen=True, slots=True)
class _CandidateTerm:
    entity: AmwayEntityDefinition
    text: str
    match_source: str


class AmwayEntityExtractionService:
    """Extract ontology-backed entity signals from A4 answer payloads."""

    def __init__(self, registry: AmwayEntityOntologyRegistry | None = None) -> None:
        self.registry = registry or load_default_amway_entity_ontology()
        self._answer_candidates = self._build_candidates(source_side="answer")
        self._question_candidates = self._build_candidates(source_side="question")

    def extract_from_fetch_results(
        self,
        fetch_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        answer_signals: list[dict[str, Any]] = []
        signals: list[dict[str, Any]] = []
        total_answer_count = 0
        valid_answer_count = 0

        for question_index, row in enumerate(fetch_results or [], start=1):
            if not isinstance(row, dict):
                continue
            question_id = _question_id(row, question_index)
            question_text = _clean_text(row.get("question_text") or row.get("question"))
            platform_results = row.get("platform_results")
            if not isinstance(platform_results, list):
                continue
            for platform_index, platform_result in enumerate(
                platform_results,
                start=1,
            ):
                if not isinstance(platform_result, dict):
                    continue
                total_answer_count += 1
                answer_text = _answer_text(platform_result)
                if not answer_text:
                    continue
                valid_answer_count += 1
                platform = _normalize_platform(platform_result.get("platform"))
                answer_id = _answer_id(
                    platform_result=platform_result,
                    question_id=question_id,
                    platform=platform,
                    platform_index=platform_index,
                )
                answer_record = {
                    "answer_id": answer_id,
                    "source_answer_id": _source_answer_id(platform_result),
                    "question_id": question_id,
                    "question": question_text,
                    "platform": platform,
                    "signals": self.extract_from_answer(
                        answer_id=answer_id,
                        question_id=question_id,
                        question=question_text,
                        platform=platform,
                        answer_text=answer_text,
                        question_context=_question_context(row, platform_result),
                    ),
                }
                answer_signals.append(answer_record)
                signals.extend(answer_record["signals"])

        return {
            "service": "AmwayEntityExtractionService",
            "schema_version": EXTRACTION_SCHEMA_VERSION,
            "ontology_id": self.registry.definition.ontology_id,
            "ontology_version": self.registry.definition.version,
            "effective_lexicon_hash": self.registry.effective_hash,
            "effective_lexicon_snapshot": self.registry.snapshot(),
            "total_answer_count": total_answer_count,
            "valid_answer_count": valid_answer_count,
            "signal_count": len(signals),
            "answer_signal_count": len(answer_signals),
            "answer_signals": answer_signals,
            "signals": signals,
        }

    def extract_from_answer(
        self,
        *,
        answer_id: str,
        question_id: str,
        question: str,
        platform: str,
        answer_text: str,
        question_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        context = dict(question_context or {})
        center_context_terms = _center_context_terms(self.registry)
        center_context_positions = _center_positions(answer_text, center_context_terms)
        answer_has_center_context = bool(center_context_positions)
        question_mentions_center = _question_mentions_center(
            question=question,
            context=context,
            center_terms=center_context_terms,
        )
        comparison_context = _has_comparison_context(answer_text, question)
        matched_entities: dict[str, dict[str, Any]] = {}

        for candidate, match_index, match_end in _matched_candidates(self._answer_candidates, answer_text):
            existing = matched_entities.get(candidate.entity.entity_id)
            if existing is not None and len(existing["matched_text"]) >= len(
                candidate.text
            ):
                continue
            local_context = _build_excerpt(
                answer_text,
                candidate.text,
                radius=120,
                match_index=match_index,
            )
            local_negative_context = _has_negative_context(local_context, "")
            risk_attribution = _risk_attribution_for_signal(
                entity=candidate.entity,
                local_context=local_context,
                matched_text=candidate.text,
                question_mentions_center=question_mentions_center,
                answer_mentions_center=answer_has_center_context,
                match_index=match_index,
                center_context_positions=center_context_positions,
            )
            near_center_context = _is_near_center_context(
                match_index=match_index,
                center_positions=center_context_positions,
                matched_text=candidate.text,
            )
            center_connection_basis = _center_connection_basis(
                question_mentions_center=question_mentions_center,
                answer_mentions_center=answer_has_center_context,
                near_center_context=near_center_context,
            )
            relation_type = _relation_type_for_signal(
                entity=candidate.entity,
                answer_text=answer_text,
                question=question,
                question_mentions_center=question_mentions_center,
                answer_mentions_center=answer_has_center_context,
                near_center_context=near_center_context,
                negative_context=local_negative_context,
                comparison_context=comparison_context,
                risk_attribution=risk_attribution,
            )
            context_polarity = _context_polarity_for_signal(
                relation_type=relation_type,
                risk_attribution=risk_attribution,
                local_negative_context=local_negative_context,
            )
            matched_entities[candidate.entity.entity_id] = {
                "signal_id": (f"sig_{answer_id}_{candidate.entity.entity_id}"),
                "answer_id": answer_id,
                "question_id": question_id,
                "question": question,
                "platform": platform,
                "entity_id": candidate.entity.entity_id,
                "entity_name": candidate.entity.canonical_name,
                "entity_type": candidate.entity.entity_type,
                "matched_text": candidate.text,
                "match_source": candidate.match_source,
                "match_span": {"start": match_index, "end": match_end},
                "relation_type": relation_type,
                "evidence_text": _build_excerpt(answer_text, candidate.text, match_index=match_index),
                "answer_position": _answer_position(answer_text, candidate.text, match_index=match_index),
                "term_origin": _term_origin(candidate.entity),
                "source_side": "answer",
                "graph_policy": candidate.entity.graph_policy.model_dump(),
                "source_policy": candidate.entity.source_policy.model_dump(),
                "review_status": candidate.entity.review_status,
                "semantic_definition": (
                    candidate.entity.semantic_definition.model_dump(mode="json")
                    if candidate.entity.semantic_definition else None
                ),
                "effective_lexicon_hash": self.registry.effective_hash,
                "question_context": context,
                "question_mentions_center": question_mentions_center,
                "answer_mentions_center": answer_has_center_context,
                "near_center_context": near_center_context,
                "center_connection_basis": center_connection_basis,
                "context_polarity": context_polarity,
                "risk_attribution": risk_attribution,
                "comparison_context": comparison_context,
                "risk_context_cues": _matched_context_cues(
                    local_context,
                    "",
                    NEGATIVE_CONTEXT_CUES,
                ),
                "comparison_context_cues": _matched_context_cues(
                    answer_text,
                    question,
                    COMPARISON_CONTEXT_CUES,
                ),
                "center_context_excerpt": _build_excerpt(
                    answer_text,
                    candidate.text,
                    radius=96,
                    match_index=match_index,
                ),
            }

        return sorted(
            matched_entities.values(),
            key=lambda item: (
                str(item.get("entity_type") or ""),
                str(item.get("entity_name") or ""),
            ),
        )

    def extract_question_entities(self, text: str) -> list[dict[str, Any]]:
        """Return ontology matches in question text for calibration context."""

        matched: dict[str, dict[str, Any]] = {}
        for candidate, match_index, match_end in _matched_candidates(self._question_candidates, text):
            matched[candidate.entity.entity_id] = {
                "entity_id": candidate.entity.entity_id,
                "entity_name": candidate.entity.canonical_name,
                "entity_type": candidate.entity.entity_type,
                "matched_text": candidate.text,
                "match_source": candidate.match_source,
                "match_span": {"start": match_index, "end": match_end},
                "term_origin": _term_origin(candidate.entity),
                "source_side": "question",
                "source_policy": candidate.entity.source_policy.model_dump(),
                "review_status": candidate.entity.review_status,
                "semantic_definition": candidate.entity.semantic_definition.model_dump(mode="json") if candidate.entity.semantic_definition else None,
            }
        return list(matched.values())

    def _build_candidates(self, *, source_side: str) -> list[_CandidateTerm]:
        from app.services.amway_topic_coverage import extraction_eligibility_reason

        candidates: list[_CandidateTerm] = []
        seen: set[tuple[str, str]] = set()
        for entity in self.registry.entities:
            if extraction_eligibility_reason(entity, self.registry, source_side):
                continue
            terms = [
                (entity.canonical_name, "canonical_name"),
                *[(alias, "alias") for alias in entity.aliases],
            ]
            for term, match_source in terms:
                text = _clean_text(term)
                if not text or len(text) <= 1:
                    continue
                key = (entity.entity_id, _compact(text))
                if key in seen:
                    continue
                candidates.append(
                    _CandidateTerm(
                        entity=entity,
                        text=text,
                        match_source=match_source,
                    )
                )
                seen.add(key)
        candidates.sort(key=lambda item: len(item.text), reverse=True)
        return candidates


def _matched_candidates(candidates: list[_CandidateTerm], text: str) -> list[tuple[_CandidateTerm, int, int]]:
    compact_chars, positions = [], []
    for index, char in enumerate(text):
        if not char.isspace():
            for lowered in char.lower():
                compact_chars.append(lowered)
                positions.append(index)
    compact = "".join(compact_chars)
    spans: dict[tuple[int, int], list[_CandidateTerm]] = {}
    for candidate in candidates:
        term = _compact(candidate.text)
        offset = compact.find(term)
        while offset >= 0:
            end = offset + len(term)
            start_raw, end_raw = positions[offset], positions[end - 1] + 1
            boundary_ok = not (
                (term[0].isascii() and term[0].isalnum() and start_raw > 0 and text[start_raw - 1].isascii() and text[start_raw - 1].isalnum())
                or (term[-1].isascii() and term[-1].isalnum() and end_raw < len(text) and text[end_raw].isascii() and text[end_raw].isalnum())
            )
            if (boundary_ok and not _match_is_excluded(candidate.entity, compact, offset, end)
                    and _identity_context_matches(candidate.entity, text, start_raw, end_raw)):
                spans.setdefault((start_raw, end_raw), []).append(candidate)
            offset = compact.find(term, offset + 1)
    selected, covered = [], []
    for (start, end), matches in sorted(spans.items(), key=lambda item: (-(item[0][1] - item[0][0]), item[0][0])):
        if any(start >= outer_start and end <= outer_end for outer_start, outer_end in covered):
            continue
        # Ambiguous long names also reserve their span: a contained short name
        # cannot resolve uncertainty about the full referent.
        covered.append((start, end))
        if len({candidate.entity.entity_id for candidate in matches}) == 1:
            selected.append((matches[0], start, end))
    return selected


def _match_is_excluded(entity, compact_text: str, start: int, end: int) -> bool:
    semantic = entity.semantic_definition
    for phrase in semantic.match_exclusions if semantic else ():
        phrase = _compact(phrase)
        # Only an occurrence containing this match excludes it. A genuine mention
        # elsewhere in the same answer remains eligible, even beside a negative one.
        offset = compact_text.find(phrase, max(0, end - len(phrase)), start + len(phrase))
        if offset >= 0 and offset <= start and offset + len(phrase) >= end:
            return True
    return False


def _identity_context_matches(entity, text: str, start: int, end: int) -> bool:
    semantic = entity.semantic_definition
    if semantic is None or semantic.match_policy == "exact":
        return True
    if semantic.match_policy == "disabled":
        return False
    local = text[max(0, start - IDENTITY_CONTEXT_WINDOW):end + IDENTITY_CONTEXT_WINDOW]
    return any(_find_text(local, term) >= 0 for term in semantic.context_terms if term.strip())


def _question_id(row: dict[str, Any], index: int) -> str:
    return _clean_text(row.get("question_id") or row.get("id")) or f"q_{index:03d}"


def _answer_id(
    *,
    platform_result: dict[str, Any],
    question_id: str,
    platform: str,
    platform_index: int,
) -> str:
    explicit = _source_answer_id(platform_result)
    safe_platform = re.sub(r"[^0-9A-Za-z]+", "_", platform).strip("_").lower()
    safe_question = re.sub(r"[^0-9A-Za-z]+", "_", question_id).strip("_").lower()
    safe_source = re.sub(r"[^0-9A-Za-z]+", "_", explicit).strip("_").lower()
    suffix = safe_source or str(platform_index)
    digest = hashlib.sha256(
        f"{question_id}\x00{platform}\x00{explicit or platform_index}".encode("utf-8")
    ).hexdigest()[:16]
    return (
        f"answer_{safe_question or 'question'}_"
        f"{safe_platform or platform_index}_{suffix}_{digest}"
    )


def _source_answer_id(platform_result: dict[str, Any]) -> str:
    return _clean_text(
        platform_result.get("answer_id")
        or platform_result.get("id")
        or platform_result.get("result_id")
    )


def _question_context(
    row: dict[str, Any],
    platform_result: dict[str, Any],
) -> dict[str, Any]:
    keys = (
        "audience_segment",
        "core_anxiety",
        "life_scene",
        "opportunity_point",
        "probe_type",
        "mother_theme",
        "question_type",
        "mentions_amway",
        "life_stage",
        "four_have",
        "touchpoint",
        "monitoring_purpose",
        "center_terms",
        "question_set_version",
        "metadata_status",
    )
    context: dict[str, Any] = {}
    for key in keys:
        value = row.get(key)
        if value in (None, "", []):
            value = platform_result.get(key)
        if value not in (None, "", []):
            context[key] = value
    return context


def _relation_type_for_signal(
    *,
    entity: AmwayEntityDefinition,
    answer_text: str,
    question: str,
    question_mentions_center: bool,
    answer_mentions_center: bool,
    near_center_context: bool,
    negative_context: bool = False,
    comparison_context: bool = False,
    risk_attribution: str = "none",
) -> str:
    connected_to_center = question_mentions_center or (
        answer_mentions_center and near_center_context
    )
    if entity.entity_type == "CenterBrand":
        return "MENTIONED_IN_ANSWER"
    if entity.entity_type == "Competitor":
        if connected_to_center and (
            comparison_context or answer_mentions_center or question_mentions_center
        ):
            return "COMPETES_WITH"
        return "MARKET_CONTEXT_ONLY"
    if entity.entity_type == "RiskLabel":
        if connected_to_center and risk_attribution == "attributed":
            return "RISKS_AS"
        if connected_to_center and risk_attribution == "denied":
            return "RISK_DENIED"
        return "MARKET_CONTEXT_ONLY"
    if entity.entity_type == "MarketContext":
        if connected_to_center:
            return "MENTIONED_IN_ANSWER"
        return "MARKET_CONTEXT_ONLY"
    if not connected_to_center:
        return "MARKET_CONTEXT_ONLY"
    if entity.entity_id == "evidence_regulation" and risk_attribution == "attributed":
        return "RISKS_AS"
    if negative_context and entity.entity_type in NEGATIVE_CONTEXT_RISK_TYPES:
        return "RISKS_AS"
    if entity.entity_type in {"Solution", "ProductCategory", "ProductFeature"}:
        return "SUPPORTED_BY_PRODUCT"
    if entity.entity_type in {"BrandStrategy", "FourValue", "FlowerDimension"}:
        return "MAPS_TO_STRATEGY"
    return "LINKED_TO_CENTER_BRAND"


def _term_origin(entity: AmwayEntityDefinition) -> str:
    if entity.entity_type in {"BrandStrategy", "FourValue", "FlowerDimension"}:
        return "strategy"
    return "answer"


def _answer_text(platform_result: dict[str, Any]) -> str:
    answer_payload = (
        platform_result.get("answer")
        if isinstance(platform_result.get("answer"), dict)
        else {}
    )
    return _clean_text(
        answer_payload.get("content")
        or platform_result.get("answer_text")
        or platform_result.get("content")
        or platform_result.get("text")
    )


def _normalize_platform(value: Any) -> str:
    text = _clean_text(value)
    aliases = {
        "deepseek": "DeepSeek",
        "kimi": "Kimi",
        "moonshot": "Kimi",
        "doubao": "豆包",
        "豆包": "豆包",
        "yuanbao": "元宝",
        "元宝": "元宝",
        "chatgpt": "ChatGPT",
        "gpt": "ChatGPT",
    }
    return aliases.get(text.lower(), text or "Unknown")


def _answer_position(answer_text: str, matched_text: str, *, match_index: int | None = None) -> str:
    index = _find_text(answer_text, matched_text) if match_index is None else match_index
    if index < 0:
        return "unknown"
    if index <= ANSWER_START_CHARS:
        return "start"
    if index <= ANSWER_MIDDLE_CHARS:
        return "middle"
    return "tail"


def _question_mentions_center(
    *,
    question: str,
    context: dict[str, Any],
    center_terms: list[str],
) -> bool:
    question_text = _clean_text(question)
    if question_text:
        return any(_contains(question_text, term) for term in center_terms)
    return _truthy(context.get("mentions_amway"))


def _center_connection_basis(
    *,
    question_mentions_center: bool,
    answer_mentions_center: bool,
    near_center_context: bool,
) -> str:
    if question_mentions_center:
        return "question_names_center"
    if answer_mentions_center and near_center_context:
        return "answer_near_center"
    if answer_mentions_center:
        return "answer_mentions_center_far"
    return "market_context_only"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _compact(value)
    if not text:
        return False
    return text in {"1", "true", "yes", "y", "是", "点名", "mention", "mentioned"}


def _has_negative_context(answer_text: str, question: str) -> bool:
    return bool(_matched_context_cues(answer_text, question, NEGATIVE_CONTEXT_CUES))


def _has_comparison_context(answer_text: str, question: str) -> bool:
    return bool(_matched_context_cues(answer_text, question, COMPARISON_CONTEXT_CUES))


def _center_context_terms(registry: AmwayEntityOntologyRegistry) -> list[str]:
    policy = registry.definition.center_brand_policy
    return list(
        dict.fromkeys(
            [
                *(policy.allowed_center_brands or []),
                *(policy.market_context_terms or []),
                *(policy.core_asset_terms or []),
            ]
        )
    )


def _context_polarity_for_signal(
    *,
    relation_type: str,
    risk_attribution: str,
    local_negative_context: bool,
) -> str:
    if relation_type == "RISKS_AS" or risk_attribution == "attributed":
        return "negative"
    if relation_type == "RISK_DENIED" or risk_attribution == "denied":
        return "positive"
    if local_negative_context:
        return "negative"
    return "neutral"


def _risk_attribution_for_signal(
    *,
    entity: AmwayEntityDefinition,
    local_context: str,
    matched_text: str,
    question_mentions_center: bool,
    answer_mentions_center: bool,
    match_index: int,
    center_context_positions: list[int],
) -> str:
    if entity.entity_type != "RiskLabel" and entity.entity_id != "evidence_regulation":
        return "none"
    connected_by_answer = answer_mentions_center and _is_near_center_context(
        match_index=match_index,
        center_positions=center_context_positions,
        matched_text=matched_text,
    )
    if not (question_mentions_center or connected_by_answer):
        return "none"
    compact_context = _compact(local_context)
    compact_term = _compact(matched_text)
    if _has_risk_denial_context(compact_context, compact_term):
        return "denied"
    if entity.entity_id == "evidence_regulation" and _has_positive_regulation_context(
        compact_context
    ):
        return "denied"
    if _has_local_risk_attribution(compact_context, compact_term, entity):
        return "attributed"
    if entity.entity_type == "RiskLabel" and connected_by_answer:
        return "attributed"
    return "none"


def _has_risk_denial_context(compact_context: str, compact_term: str) -> bool:
    if any(_compact(cue) in compact_context for cue in RISK_DENIAL_CUES):
        return True
    if compact_term and any(
        pattern in compact_context
        for pattern in (
            f"不是{compact_term}",
            f"并非{compact_term}",
            f"不属于{compact_term}",
            f"不构成{compact_term}",
            f"没有{compact_term}",
            f"不存在{compact_term}",
        )
    ):
        return True
    if (
        "不能" in compact_context
        and "等同" in compact_context
        and compact_term in compact_context
    ):
        return True
    return False


def _has_positive_regulation_context(compact_context: str) -> bool:
    has_positive = any(
        _compact(cue) in compact_context for cue in REGULATION_POSITIVE_CUES
    )
    has_negative = any(
        _compact(cue) in compact_context
        for cue in (
            "风险",
            "处罚",
            "违规",
            "非法",
            "质疑",
            "争议",
            "监管风险",
            "合规风险",
        )
    )
    return has_positive and not has_negative


def _has_local_risk_attribution(
    compact_context: str,
    compact_term: str,
    entity: AmwayEntityDefinition,
) -> bool:
    if entity.entity_id == "evidence_regulation":
        return any(
            _compact(cue) in compact_context
            for cue in (
                "监管风险",
                "合规风险",
                "处罚",
                "违规",
                "非法",
                "许可风险",
                "牌照问题",
                "禁止多层计酬",
                "多层计酬",
                "巨大影响",
            )
        )
    if entity.entity_type == "RiskLabel":
        if compact_term and compact_term in compact_context:
            return any(
                _compact(cue) in compact_context
                for cue in (
                    "涉嫌",
                    "质疑",
                    "争议",
                    "风险",
                    "警惕",
                    "谨慎",
                    "像",
                    "类似",
                    "有关",
                    "关联",
                )
            )
        return False
    return False


def _matched_context_cues(
    answer_text: str,
    question: str,
    cues: tuple[str, ...],
) -> list[str]:
    text = _compact(f"{question} {answer_text}")
    matched: list[str] = []
    for cue in cues:
        compact_cue = _compact(cue)
        if compact_cue and compact_cue in text:
            matched.append(cue)
    return matched[:8]


def _center_positions(answer_text: str, center_terms: list[str]) -> list[int]:
    compact_answer = _compact(answer_text)
    positions: list[int] = []
    for term in center_terms:
        compact_term = _compact(term)
        if not compact_term:
            continue
        start = 0
        while True:
            index = compact_answer.find(compact_term, start)
            if index < 0:
                break
            positions.append(index)
            start = index + max(len(compact_term), 1)
    return sorted(set(positions))


def _is_near_center_context(
    *,
    match_index: int,
    center_positions: list[int],
    matched_text: str,
) -> bool:
    if match_index < 0 or not center_positions:
        return False
    matched_len = max(len(_compact(matched_text)), 1)
    match_mid = match_index + round(matched_len / 2)
    return any(
        abs(match_mid - center_index) <= CENTER_CONTEXT_WINDOW
        for center_index in center_positions
    )


def _build_excerpt(answer_text: str, matched_text: str, radius: int = 72, *, match_index: int | None = None) -> str:
    clean_answer = sanitize_model_visible_text(answer_text)
    index = _find_text(clean_answer, matched_text) if match_index is None else match_index
    if index < 0:
        return clean_answer[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(clean_answer), index + len(matched_text) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(clean_answer) else ""
    return f"{prefix}{clean_answer[start:end].strip()}{suffix}"


def _find_text(haystack: str, needle: str) -> int:
    return _compact(haystack).find(_compact(needle))


def _contains(haystack: str, needle: str) -> bool:
    return _find_text(haystack, needle) >= 0


def _compact(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split())


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

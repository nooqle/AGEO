"""Brand association circle report generation for A5.

A5 consumes calibrated association-map inputs. Entity extraction and graph
calibration are owned by the A4-to-A5 handoff services.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


REPORT_KIND = "brand_association_circle"
ARTIFACT_KIND = "brand_association_circle"
SCHEMA_VERSION = "2026-06-14"
REPORT_COPY_CONSTRAINT_VERSION = "human_brand_diagnosis_v3_mirofish_spine"

REPORT_COPY_FORBIDDEN_PHRASES = (
    "这" + "说" + "明",
    "意义在于",
    "价值在于",
    "漂亮结论",
    "真正要",
    "更重要",
    "下一步不应",
    "报告的读法",
    "一次性覆盖所有问题",
)

REPORT_COPY_FORBIDDEN_PATTERNS = (
    r"不" r"是[^。；\n]{0,80}而" r"是",
    r"关键在于",
    r"重要的是",
    r"需要注意的是",
    r"深入分析",
    r"充分体现",
)

REPORT_REQUIRED_EVIDENCE_SPINE = (
    "question_definition",
    "platform_source_summary",
    "evidence_findings",
    "action_review",
    "source_appendix",
)

REPORT_NARRATIVE_SECTION_REQUIRED_FIELDS = (
    "reader_question",
    "takeaway",
    "claims",
    "paragraphs",
    "so_what",
    "next_probe",
)

DEFAULT_CENTER_TERMS = ["安利", "安利中国", "纽崔莱", "Amway China", "Nutrilite"]

FOUR_HAVE_SECTION_STRATEGY_CUES: dict[str, tuple[str, ...]] = {
    "have_health": (
        "有健康",
        "健康",
        "抗衰",
        "纽崔莱",
        "体重管理",
        "营养",
        "科学研究",
        "认证与标准",
    ),
    "have_companionship": (
        "有陪伴",
        "良好关系",
        "社群陪伴",
        "关系",
        "陪伴",
        "美好生活社群",
    ),
    "have_security_value": (
        "有保障",
        "有价值",
        "财务保障",
        "事业机会",
        "人生再出发",
        "个人成长",
        "社会价值",
        "安利人",
    ),
}

QUESTION_BANK_METADATA_KEYS = (
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

QUESTION_BANK_REQUIRED_METADATA_KEYS = (
    "audience_segment",
    "core_anxiety",
    "life_scene",
    "opportunity_point",
    "probe_type",
)

DEFAULT_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "营养补充": ("营养补充", "营养补剂", "营养品", "营养保健", "营养方案"),
    "纽崔莱": ("纽崔莱", "Nutrilite"),
    "蛋白粉": ("蛋白粉", "蛋白质粉", "植物蛋白"),
    "植物营养": ("植物营养", "植物营养素", "植物基营养", "植萃营养"),
    "健康管理": ("健康管理", "长期健康管理", "家庭健康", "营养管理"),
    "健康习惯": ("健康习惯", "生活方式", "健康生活方式"),
    "整体抗衰": ("整体抗衰", "健康抗衰", "抗衰", "抗衰老", "抗衰管理", "状态管理"),
    "直销模式": ("直销", "直销模式", "多层次营销", "销售代表"),
    "事业机会": ("事业机会", "创业机会", "副业", "收入机会", "安利事业"),
    "社群陪伴": ("社群陪伴", "社群", "陪伴", "关系陪伴", "美好生活社群"),
    "关系抗衰": ("关系抗衰", "关系支持", "孤独", "后天家人", "连接"),
    "人生再出发": ("人生再出发", "再出发", "第二人生", "中年转型"),
    "被需要/价值感": ("被需要", "价值感", "重新找到价值", "角色重构"),
    "长寿时代": ("长寿时代", "长寿", "百岁人生", "长寿社会"),
    "丰盛人生支持体系": ("丰盛人生支持体系", "丰盛人生", "美好生活支持体系"),
    "美好生活": ("美好生活", "美好生活方式"),
    "安利人": ("安利人", "ABO", "营销伙伴", "创业伙伴"),
    "传销/拉人风险": ("传销", "拉人头", "拉人", "发展下线"),
    "熟人销售压力": ("熟人销售", "熟人推荐", "人情压力", "关系压力"),
    "智商税/夸大功效": ("智商税", "夸大功效", "虚假宣传", "功效夸大"),
}

TERM_THEMES: dict[str, str] = {
    "营养补充": "健康与抗衰",
    "纽崔莱": "健康与抗衰",
    "蛋白粉": "健康与抗衰",
    "植物营养": "健康与抗衰",
    "健康管理": "健康与抗衰",
    "健康习惯": "健康与抗衰",
    "整体抗衰": "健康与抗衰",
    "社群陪伴": "社群与陪伴",
    "关系抗衰": "社群与陪伴",
    "人生再出发": "事业与再出发",
    "被需要/价值感": "事业与再出发",
    "事业机会": "事业与再出发",
    "安利人": "品牌角色",
    "长寿时代": "母品牌叙事",
    "丰盛人生支持体系": "母品牌叙事",
    "美好生活": "母品牌叙事",
    "直销模式": "信任与争议",
    "传销/拉人风险": "信任与争议",
    "熟人销售压力": "信任与争议",
    "智商税/夸大功效": "信任与争议",
}

RISK_TERMS = {"直销模式", "传销/拉人风险", "熟人销售压力", "智商税/夸大功效"}
SENSITIVE_TERMS = {"事业机会"}
TARGET_TERMS = {
    "健康管理",
    "整体抗衰",
    "社群陪伴",
    "关系抗衰",
    "人生再出发",
    "被需要/价值感",
    "长寿时代",
    "丰盛人生支持体系",
    "美好生活",
}
ASSET_TERMS = {"营养补充", "纽崔莱", "蛋白粉", "植物营养", "健康管理", "健康习惯"}
PATH_TERMS = {"植物营养", "健康习惯", "健康管理", "整体抗衰", "社群陪伴", "美好生活"}

REPORT_RISK_CONTEXT_TERMS = (
    "传销",
    "拉人头",
    "拉人",
    "发展下线",
    "囤货",
    "熟人压力",
    "熟人销售",
    "过度推销",
    "夸大功效",
    "虚假宣传",
    "智商税",
    "价格高",
    "收入不稳定",
    "合规风险",
)

REPORT_TRANSFORMATION_TERMS = (
    "转型",
    "升级",
    "方案",
    "社群",
    "科技",
    "大健康",
    "生活方式",
    "长期管理",
)

ORBIT_DEFINITIONS: tuple[tuple[str, str, int, int], ...] = (
    ("core_near", "核心稳定", 80, 100),
    ("strong", "已绑定资产", 60, 79),
    ("near_opportunity", "近端机会", 50, 59),
    ("far_opportunity", "远端机会", 35, 49),
    ("weak", "待观察", 20, 34),
    ("blank", "远端待验证", 0, 19),
)
RISK_ORBIT = "risk_shadow"

ANSWER_START_CHARS = 120
ANSWER_MIDDLE_CHARS = 420


@dataclass(slots=True)
class AnswerObservation:
    question_id: str
    question: str
    platform: str
    answer_text: str
    audience_segment: str | None = None
    core_anxiety: str | None = None
    life_scene: str | None = None
    opportunity_point: str | None = None
    probe_type: str | None = None
    mother_theme: str | None = None
    question_type: str | None = None
    mentions_amway: str | None = None
    life_stage: str | None = None
    four_have: str | None = None
    touchpoint: str | None = None
    monitoring_purpose: str | None = None


@dataclass(slots=True)
class TermEvidence:
    evidence_id: str
    node_term: str
    platform: str
    question_id: str
    question: str
    audience_segment: str | None
    core_anxiety: str | None
    life_scene: str | None
    opportunity_point: str | None
    probe_type: str | None
    mother_theme: str | None
    question_type: str | None
    mentions_amway: str | None
    life_stage: str | None
    four_have: str | None
    touchpoint: str | None
    monitoring_purpose: str | None
    answer_excerpt: str
    answer_position: str
    relation_type: str
    evidence_strength: str


@dataclass(slots=True)
class TermAccumulator:
    term: str
    normalized_expressions: set[str] = field(default_factory=set)
    answer_ids: set[str] = field(default_factory=set)
    platforms: Counter[str] = field(default_factory=Counter)
    probe_types: Counter[str] = field(default_factory=Counter)
    audience_segments: Counter[str] = field(default_factory=Counter)
    mother_themes: Counter[str] = field(default_factory=Counter)
    life_stages: Counter[str] = field(default_factory=Counter)
    opportunity_points: Counter[str] = field(default_factory=Counter)
    answer_positions: Counter[str] = field(default_factory=Counter)
    relation_types: Counter[str] = field(default_factory=Counter)
    evidence: list[TermEvidence] = field(default_factory=list)


def is_association_circle_mode(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {
        REPORT_KIND,
        "association_circle",
        "brand-association-circle",
        "amway_association_circle",
        "amway-brand-association-circle",
    }


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _preserve_answer_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _normalize_platform(value: Any) -> str:
    text = _clean_text(value).lower()
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
    return aliases.get(text, _clean_text(value) or "Unknown")


def _normalize_center_terms(
    brand_profile: dict[str, Any], center_terms: list[str] | None
) -> list[str]:
    terms: list[str] = []
    for value in center_terms or []:
        text = _clean_text(value)
        if text and text not in terms:
            terms.append(text)
    if terms:
        return terms

    brand_name = _clean_text(brand_profile.get("brand_name"))
    if brand_name and brand_name not in terms:
        terms.insert(0, brand_name)
    for value in DEFAULT_CENTER_TERMS:
        if value not in terms:
            terms.append(value)
    return terms


def _question_from_fetch_row(row: dict[str, Any], index: int) -> str:
    return (
        _clean_text(row.get("question_text"))
        or _clean_text(row.get("question"))
        or _clean_text(row.get("query"))
        or f"问题 {index}"
    )


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return None


def _iter_observations(fetch_results: list[dict[str, Any]]) -> list[AnswerObservation]:
    observations: list[AnswerObservation] = []
    for question_index, row in enumerate(fetch_results or [], start=1):
        if not isinstance(row, dict):
            continue
        question_id = _clean_text(row.get("question_id")) or f"q_{question_index:03d}"
        question = _question_from_fetch_row(row, question_index)
        platform_results = row.get("platform_results")
        if not isinstance(platform_results, list):
            continue
        for platform_result in platform_results:
            if not isinstance(platform_result, dict):
                continue
            answer_payload = (
                platform_result.get("answer")
                if isinstance(platform_result.get("answer"), dict)
                else {}
            )
            answer_text = _preserve_answer_text(
                answer_payload.get("content")
                or platform_result.get("answer_text")
                or platform_result.get("content")
            )
            if not answer_text:
                continue
            observations.append(
                AnswerObservation(
                    question_id=question_id,
                    question=question,
                    platform=_normalize_platform(platform_result.get("platform")),
                    answer_text=answer_text,
                    audience_segment=_first_non_empty(
                        row.get("audience_segment"),
                        row.get("source_persona"),
                        row.get("persona"),
                        platform_result.get("audience_segment"),
                    ),
                    core_anxiety=_first_non_empty(
                        row.get("core_anxiety"),
                        row.get("linked_pain_point"),
                        platform_result.get("core_anxiety"),
                    ),
                    life_scene=_first_non_empty(
                        row.get("life_scene"),
                        row.get("linked_scenario"),
                        row.get("category"),
                        platform_result.get("life_scene"),
                    ),
                    opportunity_point=_first_non_empty(
                        row.get("opportunity_point"),
                        row.get("monitoring_purpose"),
                        row.get("mother_theme"),
                        row.get("opportunity"),
                        platform_result.get("opportunity_point"),
                    ),
                    probe_type=_first_non_empty(
                        row.get("probe_type"),
                        row.get("question_type"),
                        row.get("intent"),
                        platform_result.get("probe_type"),
                    ),
                    mother_theme=_first_non_empty(
                        row.get("mother_theme"),
                        row.get("category"),
                        platform_result.get("mother_theme"),
                    ),
                    question_type=_first_non_empty(
                        row.get("question_type"),
                        row.get("probe_type"),
                        platform_result.get("question_type"),
                    ),
                    mentions_amway=_first_non_empty(
                        row.get("mentions_amway"),
                        platform_result.get("mentions_amway"),
                    ),
                    life_stage=_first_non_empty(
                        row.get("life_stage"),
                        row.get("audience_segment"),
                        platform_result.get("life_stage"),
                    ),
                    four_have=_first_non_empty(
                        row.get("four_have"),
                        platform_result.get("four_have"),
                    ),
                    touchpoint=_first_non_empty(
                        row.get("touchpoint"),
                        row.get("life_scene"),
                        platform_result.get("touchpoint"),
                    ),
                    monitoring_purpose=_first_non_empty(
                        row.get("monitoring_purpose"),
                        row.get("opportunity_point"),
                        platform_result.get("monitoring_purpose"),
                    ),
                )
            )
    return observations


def _fetch_result_status_counts(fetch_results: list[dict[str, Any]]) -> dict[str, int]:
    total_answer_count = 0
    failed_answer_count = 0
    empty_answer_count = 0
    for row in fetch_results or []:
        if not isinstance(row, dict):
            continue
        platform_results = row.get("platform_results")
        if not isinstance(platform_results, list):
            continue
        for platform_result in platform_results:
            if not isinstance(platform_result, dict):
                continue
            total_answer_count += 1
            answer_payload = (
                platform_result.get("answer")
                if isinstance(platform_result.get("answer"), dict)
                else {}
            )
            answer_text = _preserve_answer_text(
                answer_payload.get("content")
                or platform_result.get("answer_text")
                or platform_result.get("content")
            )
            if answer_text:
                continue
            if (
                platform_result.get("success") is False
                or platform_result.get("error")
                or platform_result.get("error_message")
            ):
                failed_answer_count += 1
            else:
                empty_answer_count += 1
    return {
        "total_answer_count": total_answer_count,
        "failed_answer_count": failed_answer_count,
        "empty_answer_count": empty_answer_count,
    }


def _contains_alias(text: str, alias: str) -> bool:
    if not alias:
        return False
    return alias.lower() in text.lower()


def _find_terms(answer_text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for term, aliases in DEFAULT_TERM_ALIASES.items():
        for alias in aliases:
            if _contains_alias(answer_text, alias):
                matches.append((term, alias))
                break
    return matches


def _answer_position(answer_text: str, alias: str) -> str:
    index = answer_text.lower().find(alias.lower())
    if index < 0:
        return "unknown"
    if index <= ANSWER_START_CHARS:
        return "start"
    if index <= ANSWER_MIDDLE_CHARS:
        return "middle"
    return "tail"


def _build_excerpt(answer_text: str, alias: str, radius: int = 72) -> str:
    index = answer_text.lower().find(alias.lower())
    if index < 0:
        return answer_text[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(answer_text), index + len(alias) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(answer_text) else ""
    return f"{prefix}{answer_text[start:end].strip()}{suffix}"


def _relation_type_for_evidence(term: str, observation: AnswerObservation) -> str:
    question_type = " ".join(
        value
        for value in [
            observation.question_type or "",
            observation.probe_type or "",
            observation.question or "",
        ]
        if value
    )
    answer_text = observation.answer_text
    if term in RISK_TERMS or any(
        cue in question_type or cue in answer_text
        for cue in ("风险", "争议", "合规", "传销", "拉人", "压力", "质疑")
    ):
        return "风险关系"
    if any(cue in answer_text[:ANSWER_START_CHARS] for cue in ("是", "属于", "被理解为", "常被理解为")):
        return "定义关系"
    if any(cue in answer_text for cue in ("推荐", "建议", "可以考虑", "适合", "优先")):
        return "推荐关系"
    if any(cue in question_type for cue in ("缺失", "未出现")):
        return "缺失/未出现"
    return "解释关系"


def _probe_score(probe_types: Counter[str]) -> float:
    score = 0.0
    for probe, count in probe_types.items():
        text = probe.lower()
        if "自然" in probe or "natural" in text:
            score += 1.0 * count
        elif "品牌" in probe or "anchor" in text or "锚定" in probe:
            score += 0.85 * count
        elif "路径" in probe or "path" in text:
            score += 0.7 * count
        elif "机会" in probe or "opportunity" in text:
            score += 0.55 * count
        else:
            score += 0.5 * count
    return min(score / max(sum(probe_types.values()), 1), 1.0)


def _brand_anchor_score(acc: TermAccumulator) -> float:
    anchored = 0
    for evidence in acc.evidence:
        probe = (evidence.probe_type or "").lower()
        if (
            "品牌" in (evidence.probe_type or "")
            or "anchor" in probe
            or "锚定" in (evidence.probe_type or "")
        ):
            anchored += 1
    return min(anchored / max(len(acc.evidence), 1), 1.0)


def _position_score(positions: Counter[str]) -> int:
    weights = {"start": 100.0, "middle": 60.0, "tail": 35.0, "unknown": 20.0}
    total = sum(positions.values())
    if not total:
        return 0
    return round(
        sum(weights.get(position, 20.0) * count for position, count in positions.items())
        / total
    )


def _relation_type_score(relation_types: Counter[str]) -> int:
    weights = {
        "定义关系": 100.0,
        "推荐关系": 88.0,
        "风险关系": 92.0,
        "解释关系": 62.0,
        "缺失/未出现": 0.0,
    }
    total = sum(relation_types.values())
    if not total:
        return 0
    return round(
        sum(
            weights.get(relation_type, 45.0) * count
            for relation_type, count in relation_types.items()
        )
        / total
    )


def _frequency_score(acc: TermAccumulator, total_observations: int) -> int:
    if total_observations <= 0:
        return 0
    return max(0, min(100, round(len(acc.answer_ids) / total_observations * 100)))


def _scene_coverage_score(acc: TermAccumulator, total_scene_count: int) -> int:
    scene_count = len(acc.mother_themes) or len(acc.opportunity_points) or len(
        acc.audience_segments
    )
    denominator = max(total_scene_count, 1)
    return max(0, min(100, round(scene_count / denominator * 100)))


def _model_consistency_score(acc: TermAccumulator, total_platforms: int) -> int:
    if total_platforms <= 0:
        return 0
    return max(0, min(100, round(len(acc.platforms) / total_platforms * 100)))


def _evidence_quality_score(acc: TermAccumulator) -> float:
    evidence_count = len(acc.evidence)
    platform_count = len(acc.platforms)
    if evidence_count >= 8 and platform_count >= 3:
        return 1.0
    if evidence_count >= 4 and platform_count >= 2:
        return 0.78
    if evidence_count >= 2:
        return 0.55
    return 0.32


def _score_node(
    acc: TermAccumulator,
    total_observations: int,
    total_platforms: int,
    total_scene_count: int,
) -> dict[str, int]:
    frequency_score = _frequency_score(acc, total_observations)
    position_score = _position_score(acc.answer_positions)
    relation_type_score = _relation_type_score(acc.relation_types)
    scene_coverage_score = _scene_coverage_score(acc, total_scene_count)
    model_consistency_score = _model_consistency_score(acc, total_platforms)
    gravity_score = round(
        frequency_score * 0.30
        + position_score * 0.20
        + relation_type_score * 0.20
        + scene_coverage_score * 0.15
        + model_consistency_score * 0.15
    )
    return {
        "frequency_score": max(0, min(100, frequency_score)),
        "position_score": max(0, min(100, position_score)),
        "relation_type_score": max(0, min(100, relation_type_score)),
        "scene_coverage_score": max(0, min(100, scene_coverage_score)),
        "model_consistency_score": max(0, min(100, model_consistency_score)),
        "gravity_score": max(0, min(100, gravity_score)),
    }


def _orbit_for(score: int) -> tuple[str, str]:
    for orbit, label, min_score, max_score in ORBIT_DEFINITIONS:
        if min_score <= score <= max_score:
            return orbit, label
    return "blank", "远端待验证"


def _business_tag(term: str, orbit: str, score: int) -> str:
    if term in RISK_TERMS:
        return "风险认知"
    if term in SENSITIVE_TERMS:
        return "敏感资产"
    if term in ASSET_TERMS and orbit in {"core_near", "strong", "near_opportunity", "contestable"}:
        return "当前资产"
    if term in PATH_TERMS and orbit in {"strong", "near_opportunity", "contestable"}:
        return "可借力路径"
    if term in TARGET_TERMS:
        if score >= 50:
            return "战略近端机会"
        if score >= 35:
            return "战略远端机会"
        return "证据不足"
    return "证据不足" if orbit in {"weak", "blank"} else "可借力路径"


def _semantic_direction(term: str) -> str:
    if term in RISK_TERMS:
        return "负向风险"
    if term in SENSITIVE_TERMS:
        return "中性/风险"
    if term in TARGET_TERMS:
        return "机会词"
    if term in ASSET_TERMS:
        return "正向资产"
    return "中性描述"


def _evidence_strength(acc: TermAccumulator) -> str:
    if len(acc.evidence) >= 8 and len(acc.platforms) >= 3:
        return "stable"
    if len(acc.evidence) >= 3 and len(acc.platforms) >= 2:
        return "limited_stable"
    return "weak"


def _orbit_reason(term: str, score: int, acc: TermAccumulator, orbit: str) -> str:
    platform_count = len(acc.platforms)
    answer_count = len(acc.answer_ids)
    if term in RISK_TERMS:
        return (
            f"{term}在 {platform_count} 个平台、{answer_count} 条回答中被带回品牌，"
            "属于当前需要优先转译和压降的风险认知。"
        )
    if orbit == "core_near":
        return f"{term}在多平台回答中稳定靠近中心品牌，当前已经形成核心稳定认知。"
    if orbit == "strong":
        return f"{term}已有稳定回答证据，是当前可放大的品牌资产或连接路径。"
    if orbit in {"near_opportunity", "contestable"}:
        return (
            f"{term}已有 {answer_count} 条回答证据，但还需要提升场景覆盖或平台一致性，"
            "属于可以继续拉近的近端机会。"
        )
    if orbit == "far_opportunity":
        return (
            f"{term}已有 {answer_count} 条回答证据，但平台和问题覆盖还弱，"
            "属于需要先补场景和样本的远端机会。"
        )
    if orbit == "weak":
        return f"{term}已有回答证据但频率、有效平台数或位置仍弱，当前适合作为补证据和复测对象。"
    return f"{term}图谱距离和证据仍弱，当前只能作为远端待验证方向观察。"


def _top_counter_values(counter: Counter[str], limit: int = 3) -> list[str]:
    return [value for value, _ in counter.most_common(limit) if value]


def _build_nodes(
    accumulators: dict[str, TermAccumulator],
    total_observations: int,
    total_platforms: int,
    total_scene_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for acc in accumulators.values():
        score_components = _score_node(
            acc,
            total_observations=total_observations,
            total_platforms=total_platforms,
            total_scene_count=total_scene_count,
        )
        score = score_components["gravity_score"]
        if score < 20:
            continue
        orbit, orbit_label = _orbit_for(score)
        if acc.term in RISK_TERMS:
            orbit = RISK_ORBIT
            orbit_label = "风险关系"
        node_id = f"node_{re.sub(r'[^0-9a-zA-Z]+', '_', acc.term).strip('_') or len(nodes) + 1}"
        node_evidence_ids: list[str] = []
        for evidence in acc.evidence[:6]:
            evidence_payload = {
                "evidence_id": evidence.evidence_id,
                "node_id": node_id,
                "node_term": evidence.node_term,
                "platform": evidence.platform,
                "question_id": evidence.question_id,
                "question": evidence.question,
                "audience_segment": evidence.audience_segment,
                "core_anxiety": evidence.core_anxiety,
                "life_scene": evidence.life_scene,
                "opportunity_point": evidence.opportunity_point,
                "probe_type": evidence.probe_type,
                "mother_theme": evidence.mother_theme,
                "question_type": evidence.question_type,
                "mentions_amway": evidence.mentions_amway,
                "life_stage": evidence.life_stage,
                "four_have": evidence.four_have,
                "touchpoint": evidence.touchpoint,
                "monitoring_purpose": evidence.monitoring_purpose,
                "answer_excerpt": evidence.answer_excerpt,
                "answer_position": evidence.answer_position,
                "relation_type": evidence.relation_type,
                "evidence_strength": evidence.evidence_strength,
            }
            evidence_rows.append(evidence_payload)
            node_evidence_ids.append(evidence.evidence_id)
        nodes.append(
            {
                "node_id": node_id,
                "term": acc.term,
                "normalized_expressions": sorted(acc.normalized_expressions),
                "orbit": orbit,
                "orbit_label": orbit_label,
                "business_tag": _business_tag(acc.term, orbit, score),
                "association_score": score,
                "gravity_score": score,
                "closeness_score": score,
                "distance_score": 100 - score,
                **score_components,
                "semantic_direction": _semantic_direction(acc.term),
                "theme": TERM_THEMES.get(acc.term, "其他联想"),
                "planet_group": TERM_THEMES.get(acc.term, "其他联想"),
                "is_risk_term": acc.term in RISK_TERMS,
                "is_target_term": acc.term in TARGET_TERMS,
                "answer_count": len(acc.answer_ids),
                "platform_count": len(acc.platforms),
                "platform_distribution": dict(acc.platforms),
                "primary_audience_segments": _top_counter_values(acc.audience_segments),
                "primary_mother_themes": _top_counter_values(acc.mother_themes),
                "primary_life_stages": _top_counter_values(acc.life_stages),
                "primary_opportunity_points": _top_counter_values(
                    acc.opportunity_points
                ),
                "relation_type_distribution": dict(acc.relation_types),
                "trigger_questions": sorted(acc.answer_ids)[:8],
                "evidence_samples": node_evidence_ids,
                "evidence_count": len(acc.evidence),
                "evidence_strength": _evidence_strength(acc),
                "source": "answer_parsed",
                "orbit_reason": _orbit_reason(acc.term, score, acc, orbit),
            }
        )
    nodes.sort(
        key=lambda item: (
            {
                "core_near": 0,
                "strong": 1,
                "near_opportunity": 2,
                "contestable": 2,
                "far_opportunity": 3,
                "weak": 4,
                "blank": 5,
                RISK_ORBIT: 5,
            }.get(str(item.get("orbit")), 9),
            -int(item.get("closeness_score") or 0),
            str(item.get("term") or ""),
        )
    )
    return nodes, evidence_rows


def _platform_preference(platform: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    platform_nodes = []
    orbit_counter: Counter[str] = Counter()
    for node in nodes:
        distribution = node.get("platform_distribution")
        if not isinstance(distribution, dict) or platform not in distribution:
            continue
        platform_nodes.append(node)
        orbit_counter[str(node.get("orbit") or "weak")] += int(
            distribution[platform] or 0
        )
    platform_nodes.sort(
        key=lambda item: int(item.get("closeness_score") or 0), reverse=True
    )
    preferred_nodes = [str(node.get("term")) for node in platform_nodes[:3]]
    dominant_orbit = orbit_counter.most_common(1)[0][0] if orbit_counter else "weak"
    if dominant_orbit in {"core_near", "strong"}:
        answer_preference = "更容易给出定义型、品牌锚定型回答，近端联想暴露更充分"
    elif dominant_orbit in {"near_opportunity", "contestable", "far_opportunity"}:
        answer_preference = (
            "更容易给出解释链条，适合观察产品、健康、社群到母品牌的连接路径"
        )
    elif dominant_orbit == RISK_ORBIT:
        answer_preference = "更容易暴露信任、合规、直销或熟人关系相关风险"
    else:
        answer_preference = "回答更保守，弱信号需要通过更多问题补样本验证"
    risk_nodes = [
        node for node in platform_nodes if node.get("business_tag") == "风险认知"
    ]
    opportunity_nodes = [
        node
        for node in platform_nodes
        if node.get("business_tag") in {"战略机会", "证据不足"}
    ]
    return {
        "platform": platform,
        "valid_answer_count": sum(
            int((node.get("platform_distribution") or {}).get(platform) or 0)
            for node in platform_nodes
        ),
        "answer_preference": answer_preference,
        "dominant_orbit": dominant_orbit,
        "preferred_nodes": preferred_nodes,
        "risk_bias": (
            "直销或事业机会等旧认知提及更突出"
            if risk_nodes
            else "未明显过度集中在旧认知风险"
        ),
        "opportunity_bias": (
            "更容易带出"
            + "、".join(str(node.get("term")) for node in opportunity_nodes[:3])
            if opportunity_nodes
            else "对远端机会点仍然保守"
        ),
        "recommendation": (
            "优先补充转译内容，观察近端风险是否下降。"
            if risk_nodes
            else "继续补充路径型内容和证据，观察已绑定资产是否稳定扩张。"
        ),
    }


def _action_type_for_node(node: dict[str, Any]) -> tuple[str, str]:
    business_tag = str(node.get("business_tag") or "")
    orbit = str(node.get("orbit") or "")
    if business_tag == "风险认知":
        return "translate", "需要转译"
    if business_tag == "当前资产":
        return "amplify", "优先放大"
    if orbit in {"weak", "blank"} or business_tag == "证据不足":
        return "build_evidence", "需要补证据"
    return "build_path", "建设连接路径"


def _action_priority(node: dict[str, Any], action_type: str) -> str:
    score = int(node.get("closeness_score") or 0)
    if action_type in {"translate", "amplify"} and score >= 60:
        return "high"
    if action_type == "build_evidence":
        return "medium"
    return "medium" if score >= 45 else "low"


def _action_title(node: dict[str, Any], action_label: str) -> str:
    term = str(node.get("term") or "圈层节点")
    if action_label == "优先放大":
        return f"放大「{term}」作为近端认知资产"
    if action_label == "需要转译":
        return f"转译「{term}」避免旧认知锁定"
    if action_label == "需要补证据":
        return f"为「{term}」补充问题和内容证据"
    return f"建设「{term}」到母品牌的连接路径"


def _action_steps(node: dict[str, Any], action_type: str) -> list[str]:
    term = str(node.get("term") or "该节点")
    if action_type == "translate":
        return [
            f"梳理回答中「{term}」出现的具体语境，区分事实资产与负面包袱。",
            "用健康、社群、长期陪伴或人生再出发语言重写旧表达。",
            "下一轮问题中复测旧词是否下降、新路径词是否上升。",
        ]
    if action_type == "amplify":
        return [
            f"把「{term}」绑定到中心品牌的事实证据整理成稳定内容素材。",
            "优先补充多平台都会引用的权威表述和案例。",
            "观察该节点是否继续被平台带回中心品牌，且风险标签不升高。",
        ]
    if action_type == "build_evidence":
        return [
            f"围绕「{term}」补充自然探针、路径探针和品牌锚定探针。",
            "增加真实案例、产品证据或社群证据，避免只停留在口号。",
            "复测该节点能否从弱信号观察进入可拉近机会或已绑定资产。",
        ]
    return [
        f"明确「{term}」通过哪条人群焦虑或产品路径连接到安利。",
        "把路径拆成可被平台回答引用的短证据链。",
        "在不同平台分别复测路径是否稳定出现。",
    ]


def _fallback_action_platforms(node: dict[str, Any]) -> list[str]:
    distribution = node.get("platform_distribution")
    if not isinstance(distribution, dict):
        return []
    return [
        platform
        for platform, _count in sorted(
            distribution.items(),
            key=lambda item: (-int(item[1] or 0), str(item[0])),
        )
        if _clean_text(platform)
    ][:3]


def _fallback_action_scene(node: dict[str, Any]) -> str:
    scenes = [
        _clean_text(item)
        for item in node.get("primary_opportunity_points") or []
        if _clean_text(item)
    ]
    return _join_report_terms(scenes, "相关生活场景")


def _fallback_action_goal(node: dict[str, Any], action_type: str) -> str:
    platform_count = int(node.get("platform_count") or 0)
    answer_count = int(node.get("answer_count") or node.get("evidence_count") or 0)
    if action_type == "translate":
        return "下轮同类问题中风险提及下降，正向解释样本增加。"
    if action_type == "amplify":
        return (
            f"下轮至少 {max(platform_count, 2)} 个平台继续提及，"
            f"有效回答不低于 {max(answer_count, 3)} 条。"
        )
    if action_type == "build_evidence":
        return "下轮形成至少 2 条可引用回答摘录，并覆盖 2 个平台。"
    return "下轮距离分下降，连接路径被平台稳定复述。"


def _build_association_actions(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for node in nodes:
        action_type, action_label = _action_type_for_node(node)
        target_platforms = _fallback_action_platforms(node)
        target_scene = _fallback_action_scene(node)
        goal_metric = _fallback_action_goal(node, action_type)
        evidence_refs = [
            str(evidence_id)
            for evidence_id in node.get("evidence_samples") or []
            if evidence_id
        ]
        action_id = (
            f"association_{action_type}_{node.get('node_id') or len(actions) + 1}"
        )
        actions.append(
            {
                "id": action_id,
                "action_type": action_type,
                "action_label": action_label,
                "title": _action_title(node, action_label),
                "node_id": node.get("node_id"),
                "node_term": node.get("term"),
                "orbit": node.get("orbit"),
                "business_tag": node.get("business_tag"),
                "priority": _action_priority(node, action_type),
                "priority_reason": _clean_text(node.get("orbit_reason")),
                "target_platforms": target_platforms,
                "target_audience": _join_report_terms(
                    [
                        _clean_text(item)
                        for item in node.get("primary_audience_segments") or []
                        if _clean_text(item)
                    ],
                    "核心题库人群",
                ),
                "target_scene": target_scene,
                "goal_metric": goal_metric,
                "reason": node.get("orbit_reason"),
                "expected_impact": (
                    "提升正向近端联想的稳定性。"
                    if action_type == "amplify"
                    else (
                        "降低旧认知对母品牌升级的锁定。"
                        if action_type == "translate"
                        else "补足弱信号进入路径圈层所需的回答证据。"
                    )
                ),
                "review_criteria": (
                    f"复测「{node.get('term')}」相关问题；目标：{goal_metric}"
                ),
                "execution_steps": _action_steps(node, action_type),
                "evidence_refs": evidence_refs[:6],
                "next_question_suggestion": (
                    f"围绕「{node.get('term')}」追加自然探针、路径探针和品牌锚定探针各 1 条。"
                ),
            }
        )
    actions.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority")), 3),
            {"translate": 0, "amplify": 1, "build_path": 2, "build_evidence": 3}.get(
            str(item.get("action_type")),
                9,
            ),
        )
    )
    return actions[:12]


def _join_report_terms(values: list[str], fallback: str) -> str:
    terms = [str(value).strip() for value in values if str(value or "").strip()]
    if not terms:
        return fallback
    if len(terms) == 1:
        return terms[0]
    return "、".join(terms)


def _format_report_distribution(value: Any, fallback: str) -> str:
    if not isinstance(value, dict) or not value:
        return fallback
    label_map = {
        "fetch_result": "抓取题目",
        "question_bank": "题库题目",
        "uploaded_question": "上传题目",
        "latest_report_preview": "最近报告预览",
        "generated": "生成题目",
    }
    parts = []
    for key, count in sorted(value.items(), key=lambda item: str(item[0])):
        label = label_map.get(_clean_text(key), _clean_text(key) or "未知来源")
        try:
            safe_count = int(count)
        except (TypeError, ValueError):
            safe_count = 0
        if safe_count > 0:
            parts.append(f"{label} {safe_count} 个")
    return "、".join(parts) if parts else fallback


def _top_terms_for_report(
    nodes: list[dict[str, Any]],
    predicate: Any,
    limit: int = 3,
) -> list[str]:
    return [
        str(node.get("term"))
        for node in nodes
        if predicate(node) and str(node.get("term") or "").strip()
    ][:limit]


def _top_far_terms_for_report(nodes: list[dict[str, Any]], limit: int = 3) -> list[str]:
    far_nodes = [
        node
        for node in nodes
        if not _is_risk_report_node(node)
        and str(node.get("orbit") or "") in {"far_opportunity", "weak", "blank"}
        and _clean_text(node.get("term"))
    ]
    far_nodes.sort(
        key=lambda node: (
            -int(node.get("distance_score") or 0),
            -int(node.get("evidence_count") or 0),
            _clean_text(node.get("term")),
        )
    )
    return [_clean_text(node.get("term")) for node in far_nodes[:limit]]


def _top_competition_terms_for_report(
    nodes: list[dict[str, Any]],
    limit: int = 3,
) -> list[str]:
    competitors = [
        node
        for node in nodes
        if _clean_text(node.get("business_tag")) == "竞争关系"
        and _clean_text(node.get("term"))
    ]
    competitors.sort(
        key=lambda node: (
            -int(node.get("evidence_count") or 0),
            -int(node.get("platform_count") or 0),
            _clean_text(node.get("term")),
        )
    )
    return [_clean_text(node.get("term")) for node in competitors[:limit]]


def _is_risk_report_node(node: dict[str, Any]) -> bool:
    graph_policy = (
        node.get("graph_policy") if isinstance(node.get("graph_policy"), dict) else {}
    )
    if graph_policy.get("risk_view") == "not_allowed":
        return False
    if str(node.get("maturity_tier") or "") == "risk":
        return True
    return (
        str(node.get("orbit") or "") == RISK_ORBIT
        or str(node.get("business_tag") or "") == "风险认知"
        or str(node.get("business_tag") or "") == "竞争关系"
    )


def _is_strong_report_node(node: dict[str, Any]) -> bool:
    return (
        str(node.get("orbit") or "") in {"core_near", "strong"}
        and not _is_risk_report_node(node)
    )


def _is_growth_report_node(node: dict[str, Any]) -> bool:
    return (
        str(node.get("orbit") or "") in {"near_opportunity", "contestable"}
        or str(node.get("business_tag") or "")
        in {"战略机会", "可借力路径", "可拉近机会", "近端机会", "战略近端机会", "战略接住"}
        or str(node.get("maturity_tier") or "") == "near_opportunity"
    ) and not _is_risk_report_node(node)


def _is_story_report_node(node: dict[str, Any]) -> bool:
    return (
        str(node.get("orbit") or "") in {"far_opportunity", "weak", "blank"}
        or str(node.get("business_tag") or "") in {"证据不足", "远端机会", "战略远端机会", "弱信号", "战略待验证"}
        or str(node.get("maturity_tier") or "") in {"far_opportunity", "watch_signal", "evidence_gap"}
    ) and not _is_risk_report_node(node)


def _first_center_term(center_terms: list[str]) -> str:
    return next((term for term in center_terms if _clean_text(term)), "安利")


def _counter_values_from_records(
    records: list[dict[str, Any]],
    key: str,
    limit: int = 6,
) -> list[str]:
    counter: Counter[str] = Counter()
    for record in records:
        value = record.get(key)
        if isinstance(value, list):
            for item in value:
                text = _clean_text(item)
                if text:
                    counter[text] += 1
            continue
        text = _clean_text(value)
        if text:
            counter[text] += 1
    return _top_counter_values(counter, limit)


def _build_question_definition(
    *,
    center_terms: list[str],
    question_bank: list[dict[str, Any]],
    sample_scope: dict[str, Any],
) -> dict[str, Any]:
    center_term = _first_center_term(center_terms)
    question_count = int(
        sample_scope.get("question_count")
        or sample_scope.get("question_bank_count")
        or len(question_bank)
    )
    source_counter: Counter[str] = Counter(
        _clean_text(item.get("source")) or "question_bank" for item in question_bank
    )
    sample_questions = []
    for item in question_bank[:8]:
        sample_questions.append(
            {
                "id": _clean_text(item.get("id")),
                "text": _clean_text(item.get("text") or item.get("question")),
                "audience_segment": _clean_text(item.get("audience_segment")),
                "life_scene": _clean_text(item.get("life_scene")),
                "opportunity_point": _clean_text(item.get("opportunity_point")),
                "probe_type": _clean_text(item.get("probe_type")),
                "metadata_status": _clean_text(item.get("metadata_status")),
            }
        )
    audience_segments = _counter_values_from_records(
        question_bank, "audience_segment"
    )
    probe_types = _counter_values_from_records(question_bank, "probe_type")
    opportunity_points = _counter_values_from_records(
        question_bank, "opportunity_point"
    )
    life_scenes = _counter_values_from_records(question_bank, "life_scene")
    definition_parts = [
        f"中心品牌：{center_term}",
        f"题目数：{question_count}",
    ]
    if audience_segments:
        definition_parts.append(
            "人群：" + "、".join(audience_segments[:4])
        )
    if probe_types:
        definition_parts.append(
            "探针：" + "、".join(probe_types[:4])
        )
    if opportunity_points:
        definition_parts.append(
            "机会点：" + "、".join(opportunity_points[:4])
        )
    return {
        "center_term": center_term,
        "center_terms": center_terms,
        "question_count": question_count,
        "question_bank_count": len(question_bank),
        "question_set_version": sample_scope.get("question_set_version"),
        "question_sources": dict(source_counter),
        "audience_segments": audience_segments,
        "probe_types": probe_types,
        "opportunity_points": opportunity_points,
        "life_scenes": life_scenes,
        "sample_questions": sample_questions,
        "definition_sentence": "；".join(definition_parts) + "。",
    }


def _build_platform_source_summary(
    *,
    fetch_results: list[dict[str, Any]],
    platform_comparison: list[dict[str, Any]],
) -> dict[str, Any]:
    platform_rows: dict[str, dict[str, Any]] = {}
    comparison_by_platform = {
        _clean_text(item.get("platform")): item for item in platform_comparison
    }

    for row in fetch_results or []:
        if not isinstance(row, dict):
            continue
        question_id = _clean_text(row.get("question_id"))
        platform_results = row.get("platform_results")
        if not isinstance(platform_results, list):
            continue
        for platform_result in platform_results:
            if not isinstance(platform_result, dict):
                continue
            platform = _normalize_platform(platform_result.get("platform"))
            platform_row = platform_rows.setdefault(
                platform,
                {
                    "platform": platform,
                    "total_answer_count": 0,
                    "valid_answer_count": 0,
                    "failed_answer_count": 0,
                    "empty_answer_count": 0,
                    "question_ids": [],
                },
            )
            platform_row["total_answer_count"] += 1
            if question_id:
                platform_row["question_ids"].append(question_id)
            answer_payload = (
                platform_result.get("answer")
                if isinstance(platform_result.get("answer"), dict)
                else {}
            )
            answer_text = _preserve_answer_text(
                answer_payload.get("content")
                or platform_result.get("answer_text")
                or platform_result.get("content")
            )
            if answer_text:
                platform_row["valid_answer_count"] += 1
            elif (
                platform_result.get("success") is False
                or platform_result.get("error")
                or platform_result.get("error_message")
            ):
                platform_row["failed_answer_count"] += 1
            else:
                platform_row["empty_answer_count"] += 1

    platforms: list[dict[str, Any]] = []
    for platform, platform_row in platform_rows.items():
        comparison = comparison_by_platform.get(platform, {})
        platforms.append(
            {
                **platform_row,
                "question_ids": sorted(set(platform_row["question_ids"])),
                "answer_preference": _clean_text(
                    comparison.get("answer_preference")
                ),
                "preferred_nodes": comparison.get("preferred_nodes") or [],
                "dominant_orbit": _clean_text(comparison.get("dominant_orbit")),
                "risk_bias": _clean_text(comparison.get("risk_bias")),
                "opportunity_bias": _clean_text(comparison.get("opportunity_bias")),
                "recommendation": _clean_text(comparison.get("recommendation")),
            }
        )
    platforms.sort(
        key=lambda item: (
            -int(item.get("valid_answer_count") or 0),
            str(item.get("platform") or ""),
        )
    )
    return {
        "total_answer_count": sum(
            int(row.get("total_answer_count") or 0) for row in platforms
        ),
        "valid_answer_count": sum(
            int(row.get("valid_answer_count") or 0) for row in platforms
        ),
        "failed_answer_count": sum(
            int(row.get("failed_answer_count") or 0) for row in platforms
        ),
        "empty_answer_count": sum(
            int(row.get("empty_answer_count") or 0) for row in platforms
        ),
        "platform_count": len(platforms),
        "platform_names": [str(row.get("platform")) for row in platforms],
        "platforms": platforms,
    }


def _build_evidence_findings(
    *,
    center_terms: list[str],
    nodes: list[dict[str, Any]],
    evidence_samples: list[dict[str, Any]],
    limit: int = 12,
) -> list[dict[str, Any]]:
    center_term = _first_center_term(center_terms)
    evidence_by_id = {
        _clean_text(sample.get("evidence_id")): sample for sample in evidence_samples
    }
    findings: list[dict[str, Any]] = []
    for node in nodes[:limit]:
        term = _clean_text(node.get("term"))
        evidence_refs = [
            evidence_id
            for evidence_id in node.get("evidence_samples") or []
            if _clean_text(evidence_id) in evidence_by_id
        ]
        if not term or not evidence_refs:
            continue
        samples = [evidence_by_id[evidence_id] for evidence_id in evidence_refs[:2]]
        orbit = _clean_text(node.get("orbit"))
        if _is_risk_report_node(node):
            claim = f"{term}会把回答带向信任、合规或销售关系风险。"
        elif _is_strong_report_node(node):
            claim = f"{term}已经是{center_term}当前可使用的近端资产。"
        elif _is_growth_report_node(node):
            claim = f"{term}已经进入回答路径，仍需要更多平台重复出现。"
        else:
            claim = f"{term}是有证据的远端信号，适合放入下一轮复测。"
        platform_distribution = node.get("platform_distribution")
        platform_text = ""
        if isinstance(platform_distribution, dict) and platform_distribution:
            platform_text = "平台分布：" + "、".join(
                f"{platform}{count}"
                for platform, count in sorted(platform_distribution.items())
            )
        first_sample = samples[0] if samples else {}
        supporting_facts = [
            (
                f"{int(node.get('answer_count') or node.get('evidence_count') or 0)} 条回答提到，"
                f"覆盖 {int(node.get('platform_count') or 0)} 个平台。"
            ),
            (
                f"图谱贴近值 {int(node.get('closeness_score') or node.get('gravity_score') or 0)}，"
                f"距离值 {int(node.get('distance_score') or 0)}，轨道为{node.get('orbit_label') or orbit}。"
            ),
        ]
        if platform_text:
            supporting_facts.append(platform_text + "。")
        if first_sample:
            supporting_facts.append(
                "代表问题："
                + _clean_text(first_sample.get("question"))
                + "。"
            )
        findings.append(
            {
                "node_id": node.get("node_id"),
                "node_term": term,
                "claim": claim,
                "orbit": orbit,
                "orbit_label": node.get("orbit_label"),
                "business_tag": node.get("business_tag"),
                "supporting_facts": supporting_facts,
                "evidence_refs": evidence_refs,
                "sample_platform": _clean_text(first_sample.get("platform")),
                "sample_question": _clean_text(first_sample.get("question")),
                "sample_excerpt": _clean_text(first_sample.get("answer_excerpt")),
                "implication": _clean_text(node.get("orbit_reason")),
            }
        )
    return findings


def _build_report_outline(center_terms: list[str]) -> list[dict[str, Any]]:
    center_term = _first_center_term(center_terms)
    return [
        {
            "chapter_id": "executive_read",
            "title": f"{center_term}现在被怎样记住",
            "reader_question": "先用一句话说清楚：AI回答目前把品牌放在什么位置？",
            "required_evidence": ["association_circle.nodes", "evidence_findings"],
        },
        {
            "chapter_id": "question_scope",
            "title": "这轮问题在问什么",
            "reader_question": "这轮题目把哪些人群、场景和机会点带进观察范围？",
            "required_evidence": ["question_bank", "question_metadata"],
        },
        {
            "chapter_id": "platform_scope",
            "title": "样本从哪些平台来",
            "reader_question": "哪些平台给出了回答，哪些回答失败或没有形成可读样本？",
            "required_evidence": ["fetch_results", "platform_comparison"],
        },
        {
            "chapter_id": "association_reading",
            "title": "图谱怎么读",
            "reader_question": "平台回答先把哪些词带回中心品牌，这些词为什么近或远？",
            "required_evidence": ["association_circle.nodes", "evidence_samples"],
        },
        {
            "chapter_id": "risk_relation",
            "title": "需要拆开的风险关系",
            "reader_question": "哪些旧认知会把回答带向信任、合规或销售关系问题？",
            "required_evidence": ["risk_nodes", "risk_evidence_samples"],
        },
        {
            "chapter_id": "actions",
            "title": "下一轮该验证什么",
            "reader_question": "哪些内容证据、澄清动作和复测问题应该先执行？",
            "required_evidence": ["association_actions", "evidence_refs"],
        },
        {
            "chapter_id": "appendix",
            "title": "证据附录",
            "reader_question": "每个判断可以追溯到哪些问题、平台和原文摘录？",
            "required_evidence": ["source_appendix"],
        },
    ]


def _build_analysis_tool_trace(
    *,
    question_definition: dict[str, Any],
    platform_source_summary: dict[str, Any],
    evidence_findings: list[dict[str, Any]],
    association_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    top_findings = [
        _clean_text(finding.get("node_term"))
        for finding in evidence_findings[:6]
        if _clean_text(finding.get("node_term"))
    ]
    action_titles = [
        _clean_text(action.get("title") or action.get("action_label"))
        for action in association_actions[:4]
        if _clean_text(action.get("title") or action.get("action_label"))
    ]
    return [
        {
            "step": "question_scope_scan",
            "title": "读取问题边界",
            "summary": _clean_text(question_definition.get("definition_sentence")),
            "outputs": [
                f"中心品牌：{question_definition.get('center_term')}",
                f"题目数：{question_definition.get('question_count')}",
                "人群："
                + _join_report_terms(
                    question_definition.get("audience_segments") or [],
                    "待补充",
                ),
                "探针："
                + _join_report_terms(
                    question_definition.get("probe_types") or [],
                    "待补充",
                ),
            ],
        },
        {
            "step": "platform_scope_scan",
            "title": "核验平台样本",
            "summary": (
                f"有效回答 {platform_source_summary.get('valid_answer_count', 0)} 条，"
                f"失败 {platform_source_summary.get('failed_answer_count', 0)} 条，"
                f"空回答 {platform_source_summary.get('empty_answer_count', 0)} 条。"
            ),
            "outputs": platform_source_summary.get("platform_names") or [],
        },
        {
            "step": "association_evidence_forge",
            "title": "归并节点证据",
            "summary": "只把回答原文里出现过、且能回到问题和平台的词合并为节点判断。",
            "outputs": top_findings,
        },
        {
            "step": "risk_relation_scan",
            "title": "折叠风险入口",
            "summary": "把风险旧认知从正向轨道中拿出来，单独观察它们怎样干扰品牌解释。",
            "outputs": [
                _clean_text(finding.get("node_term"))
                for finding in evidence_findings
                if _clean_text(finding.get("business_tag")) == "风险认知"
            ][:6],
        },
        {
            "step": "action_synthesis",
            "title": "生成复测动作",
            "summary": "把节点证据、平台入口和风险关系转成下一轮可以复测的行动。",
            "outputs": action_titles,
        },
    ]


def _build_source_appendix(
    *,
    question_bank: list[dict[str, Any]],
    platform_source_summary: dict[str, Any],
    evidence_samples: list[dict[str, Any]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    question_by_id = {
        _clean_text(item.get("id")): item
        for item in question_bank
        if _clean_text(item.get("id"))
    }
    platform_rows = {
        _clean_text(row.get("platform")): row
        for row in platform_source_summary.get("platforms") or []
        if isinstance(row, dict)
    }
    appendix: list[dict[str, Any]] = []
    for sample in evidence_samples[:limit]:
        question_id = _clean_text(sample.get("question_id"))
        platform = _clean_text(sample.get("platform"))
        question = question_by_id.get(question_id, {})
        platform_row = platform_rows.get(platform, {})
        appendix.append(
            {
                "evidence_id": _clean_text(sample.get("evidence_id")),
                "node_term": _clean_text(sample.get("node_term")),
                "platform": platform,
                "question_id": question_id,
                "question": _clean_text(sample.get("question")),
                "answer_excerpt": _preserve_answer_text(sample.get("answer_excerpt")),
                "audience_segment": _clean_text(
                    sample.get("audience_segment")
                    or question.get("audience_segment")
                ),
                "life_scene": _clean_text(
                    sample.get("life_scene") or question.get("life_scene")
                ),
                "opportunity_point": _clean_text(
                    sample.get("opportunity_point")
                    or question.get("opportunity_point")
                ),
                "probe_type": _clean_text(
                    sample.get("probe_type") or question.get("probe_type")
                ),
                "platform_valid_answer_count": int(
                    platform_row.get("valid_answer_count") or 0
                ),
            }
        )
    return appendix


def _prioritize_evidence_samples_for_nodes(
    nodes: list[dict[str, Any]],
    evidence_samples: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    evidence_by_id = {
        _clean_text(sample.get("evidence_id")): sample
        for sample in evidence_samples
        if _clean_text(sample.get("evidence_id"))
    }
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for node in nodes:
        for evidence_id in node.get("evidence_samples") or []:
            evidence_id = _clean_text(evidence_id)
            sample = evidence_by_id.get(evidence_id)
            if not sample or evidence_id in selected_ids:
                continue
            selected.append(sample)
            selected_ids.add(evidence_id)
            if len(selected) >= limit:
                return selected
    for sample in evidence_samples:
        evidence_id = _clean_text(sample.get("evidence_id"))
        if evidence_id and evidence_id in selected_ids:
            continue
        selected.append(sample)
        if evidence_id:
            selected_ids.add(evidence_id)
        if len(selected) >= limit:
            break
    return selected


def _build_report_narrative_sections(
    *,
    center_terms: list[str],
    sample_scope: dict[str, Any],
    executive_summary: dict[str, Any],
    nodes: list[dict[str, Any]],
    platform_comparison: list[dict[str, Any]],
    evidence_samples: list[dict[str, Any]],
    association_actions: list[dict[str, Any]],
    question_definition: dict[str, Any],
    platform_source_summary: dict[str, Any],
    evidence_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    center_term = _first_center_term(center_terms)
    strong_terms = _top_terms_for_report(nodes, _is_strong_report_node, 3)
    growth_terms = _top_terms_for_report(nodes, _is_growth_report_node, 3)
    story_terms = _top_terms_for_report(nodes, _is_story_report_node, 2)
    risk_terms = _top_terms_for_report(nodes, _is_risk_report_node, 3)
    risk_count = sum(1 for node in nodes if _is_risk_report_node(node))
    first_platform = platform_comparison[0] if platform_comparison else {}
    first_evidence = evidence_samples[0] if evidence_samples else {}
    first_action = association_actions[0] if association_actions else {}
    answer_count = int(sample_scope.get("valid_answer_count") or 0)
    platform_count = int(sample_scope.get("platform_count") or 0)
    current_identity = _clean_text(
        executive_summary.get("current_default_identity")
        or executive_summary.get("one_line_judgment")
    )
    current_identity_sentence = (
        f"当前默认联想集中在{current_identity}。"
        if current_identity and current_identity != "暂无稳定外围联想"
        else f"{center_term}暂时还缺少稳定外围联想。"
    )
    platform_name = _clean_text(first_platform.get("platform")) or "平台样本"
    platform_preference = _clean_text(first_platform.get("answer_preference")) or "偏好待观察"
    evidence_platform = _clean_text(first_evidence.get("platform")) or "某个平台"
    evidence_question = _clean_text(first_evidence.get("question"))
    evidence_term = _clean_text(first_evidence.get("node_term")) or "相关联想"
    action_title = _clean_text(
        first_action.get("title")
        or first_action.get("action_label")
        or first_action.get("node_term")
    )
    audience_text = _join_report_terms(
        question_definition.get("audience_segments") or [],
        "未形成稳定人群标签",
    )
    probe_text = _join_report_terms(
        question_definition.get("probe_types") or [],
        "未形成稳定探针标签",
    )
    opportunity_text = _join_report_terms(
        question_definition.get("opportunity_points") or [],
        "未形成稳定机会标签",
    )
    platform_names = _join_report_terms(
        platform_source_summary.get("platform_names") or [],
        "平台样本待补充",
    )
    requested_platform_names = _join_report_terms(
        platform_source_summary.get("requested_platform_names")
        or platform_source_summary.get("platform_names")
        or [],
        "平台样本待补充",
    )
    failed_platform_names = _join_report_terms(
        [
            _clean_text(row.get("platform"))
            for row in platform_source_summary.get("platforms", [])
            if row.get("status") == "failed" and _clean_text(row.get("platform"))
        ],
        "",
    )
    platform_scope_sentence = (
        f"有效回答来自{platform_names}。"
        if platform_names != "平台样本待补充"
        else "有效平台样本待补充。"
    )
    if failed_platform_names:
        platform_scope_sentence += (
            f"{failed_platform_names}本轮抓取失败，已进入平台状态记录，"
            "不计入有效平台。"
        )
    total_answer_count = int(platform_source_summary.get("total_answer_count") or 0)
    failed_answer_count = int(platform_source_summary.get("failed_answer_count") or 0)
    empty_answer_count = int(platform_source_summary.get("empty_answer_count") or 0)

    def finding_for_terms(terms: list[str]) -> dict[str, Any]:
        term_set = set(terms)
        return next(
            (
                finding
                for finding in evidence_findings
                if _clean_text(finding.get("node_term")) in term_set
            ),
            {},
        )

    def facts_from_finding(finding: dict[str, Any]) -> list[str]:
        facts = finding.get("supporting_facts")
        if isinstance(facts, list):
            return [_clean_text(fact) for fact in facts if _clean_text(fact)]
        return []

    def refs_from_finding(finding: dict[str, Any]) -> list[str]:
        refs = finding.get("evidence_refs")
        if isinstance(refs, list):
            return [_clean_text(ref) for ref in refs if _clean_text(ref)]
        return []

    strong_finding = finding_for_terms(strong_terms)
    growth_finding = finding_for_terms(growth_terms)
    risk_finding = finding_for_terms(risk_terms)
    first_finding = evidence_findings[0] if evidence_findings else {}

    sections = [
        {
            "section_id": "executive_read",
            "role": "executive_summary",
            "title": f"{center_term}现在被怎样记住",
            "reader_question": "先用一句话说清楚：AI回答目前把品牌放在什么位置？",
            "takeaway": (
                f"{center_term}这一轮的默认入口是{_join_report_terms(strong_terms, '尚未稳定')}，"
                "品牌应先守住已被回答反复带出的资产，再处理风险旧认知。"
            ),
            "claims": [
                f"平台回答解析出 {len(nodes)} 个外围联想节点，且外围节点只来自回答原文。",
                f"风险关系单独计入 {risk_count} 个节点，不与正向机会混在同一判断里。",
            ],
            "so_what": (
                "这意味着报告先判断平台如何记住品牌，再决定品牌该补什么证据；"
                "战略愿望需要先被回答证据接住，才会进入图谱判断。"
            ),
            "paragraphs": [
                (
                    f"这一轮先看见的是{_join_report_terms(strong_terms, '尚未稳定的第一反应')}。"
                    f"{current_identity_sentence}"
                    f"本轮从 {answer_count} 条有效回答里解析出 {len(nodes)} 个联想节点，"
                    f"其中 {risk_count} 个会把{center_term}带向信任、销售方式或争议解释。"
                    if answer_count
                    else current_identity_sentence
                ),
                (
                    f"图谱记录平台回答已经怎样组织{center_term}，按回答证据呈现品牌联想。"
                    "稳定回到品牌的词代表回答会主动带回品牌；已有路径的词代表线索存在但证据还需要继续加固；"
                    "风险词单独展开，避免把负面旧认知和增长机会画在同一条轨道上。"
                ),
                (
                    f"阅读顺序是：先确认题目和平台样本，再看{center_term}的稳定资产，"
                    "随后看机会是否被拉近，最后回到原文证据和下一轮复测动作。"
                ),
            ],
            "supporting_facts": facts_from_finding(first_finding)
            or [f"解析节点 {len(nodes)} 个；风险节点 {risk_count} 个。"],
            "evidence_refs": refs_from_finding(first_finding),
            "next_probe": "下一轮沿用同一批核心问题，观察稳定资产是否继续被平台带回品牌、机会词是否靠近、风险词是否下降。",
        },
        {
            "section_id": "question_definition",
            "role": "input_definition",
            "title": "这轮问题在问什么",
            "reader_question": "这轮题目把哪些人群、场景和机会点带进观察范围？",
            "takeaway": (
                f"这轮问题把{audience_text}、{probe_text}和{opportunity_text}放进同一个观察边界。"
            ),
            "claims": [
                f"题库记录 {question_definition.get('question_count', 0)} 个问题。",
                "题目元数据决定后续抓取和解析口径，报告阶段沿用题库口径。",
            ],
            "so_what": (
                "如果题目边界不清楚，图谱就无法解释为什么某些词靠近或远离品牌。"
            ),
            "paragraphs": [
                (
                    f"本轮以{center_term}为中心，题库记录 "
                    f"{question_definition.get('question_count', 0)} 个问题。"
                    f"题目同时覆盖{audience_text}，使用{probe_text}，并把{opportunity_text}放进观察范围。"
                ),
                (
                    "这一步先限定观察边界。平台回答会在健康、产品、事业、社群和人生阶段之间移动，"
                    f"圈层只承认回答里真实出现、并且能被带回{center_term}的词。"
                ),
            ],
            "supporting_facts": [
                _clean_text(question_definition.get("definition_sentence")),
                "题库来源："
                + _format_report_distribution(
                    question_definition.get("question_sources"),
                    "来源待补充",
                )
                + "。",
            ],
            "evidence_refs": [],
            "next_probe": "下一轮如果要比较变化，应保留同一批核心题目，再补充新的机会探针。",
        },
        {
            "section_id": "platform_sources",
            "role": "source_scope",
            "title": "样本从哪些平台来",
            "reader_question": "哪些平台给出了回答，哪些回答失败或没有形成可读样本？",
            "takeaway": (
                f"本轮读到 {answer_count} 条有效回答，覆盖 {platform_count} 个有效平台；"
                "失败和空回答也进入样本口径。"
            ),
            "claims": [
                f"总回答请求 {total_answer_count} 条，失败 {failed_answer_count} 条，空回答 {empty_answer_count} 条。",
                f"尝试平台包括{requested_platform_names}。",
                platform_scope_sentence,
            ],
            "so_what": (
                "平台样本决定这张图能代表什么；样本不足时先记录不足，再等待下一轮补样验证。"
            ),
            "paragraphs": [
                (
                    f"本轮共请求 {total_answer_count} 条平台回答，读到 {answer_count} 条有效回答，"
                    f"有效平台 {platform_count} 个。{platform_scope_sentence}"
                ),
                (
                    f"抓取失败 {failed_answer_count} 条，空回答 {empty_answer_count} 条。"
                    "这些状态会保留在口径里，避免把样本不足误读成品牌缺席。"
                ),
            ],
            "supporting_facts": [
                (
                    f"有效回答 {answer_count} 条；总回答请求 {total_answer_count} 条；"
                    f"失败 {failed_answer_count} 条；空回答 {empty_answer_count} 条。"
                ),
                f"尝试平台：{requested_platform_names}。",
                platform_scope_sentence,
            ],
            "evidence_refs": [],
            "next_probe": "样本不足的平台应在下一轮保留失败记录，并继续抓取同一批问题。",
        },
        {
            "section_id": "circle_reading",
            "role": "method_reading",
            "title": "图谱怎么读",
            "reader_question": "平台回答为什么把这些词放进不同圈层？",
            "takeaway": (
                "图谱要把回答里的稳定绑定、连接路径、机会方向和风险关系拆开看，避免停留在关键词罗列。"
            ),
            "claims": [
                    "稳定回到品牌的词代表回答会主动把用户带回品牌。",
                "已有路径的词代表连接已经出现，但仍需要更多回答和平台共识。",
                "风险词用单独关系图查看，不放在普通机会轨道上。",
            ],
            "so_what": (
                "品牌团队读图时应先问这个词为什么在这里，再决定是放大、补证据还是单独澄清。"
            ),
            "paragraphs": [
                (
                    f"把 {answer_count} 条有效回答合在一起看，先确认哪些词会被平台主动带回{center_term}。"
                    f"{current_identity_sentence}"
                    if answer_count
                    else current_identity_sentence
                ),
                (
                    f"外围节点只从回答原文解析。预设战略词可以帮助解释方向，进入{center_term}圈层仍以回答证据为准。"
                ),
                (
                    "读图时先看哪些词已经稳定回到品牌，再看连接路径和待观察机会是否可以被拉近。"
                    "风险旧认知单独拆开，避免把负向问题误当成增长机会。"
                ),
            ],
            "supporting_facts": facts_from_finding(first_finding)
            or [f"解析出 {len(nodes)} 个联想节点，风险节点 {risk_count} 个。"],
            "evidence_refs": refs_from_finding(first_finding),
            "next_probe": "先锁定近端身份，再看新增内容是否能让待观察机会更稳定地回到品牌。",
        },
        {
            "section_id": "stable_assets",
            "role": "asset_finding",
            "title": "已经站稳的资产",
            "reader_question": "哪些联想已经被回答稳定带回品牌？",
            "takeaway": (
                f"{_join_report_terms(strong_terms, '近端资产')}是这一轮最先值得守住的品牌资产。"
                if strong_terms
                else f"{center_term}暂时还没有足够稳定的第一反应。"
            ),
            "claims": [
                f"近端资产：{_join_report_terms(strong_terms, '暂未形成')}。",
                "这些资产需要继续用产品事实、场景证据和权威背书巩固。",
            ],
            "so_what": (
                "稳定资产要看平台是否已经会引用；品牌内容应优先服务这些入口。"
            ),
            "paragraphs": [
                (
                    f"{_join_report_terms(strong_terms, '近端资产')}目前离{center_term}最近。"
                    "这些词在回答中和品牌反复同框，用户从这里进入健康、产品、社群或生活方式语境。"
                    if strong_terms
                    else f"{center_term}这一轮还没有形成非常稳定的第一反应。"
                    "品牌需要更多可引用的公开证据，让平台回答有更可靠的抓手。"
                ),
                (
                    "近端资产可以先进入内容资产管理。保留平台已经采用的表达，再补产品来源、使用场景和权威背书，"
                    "下一轮复测时看它们是否继续被平台带回品牌。"
                    if strong_terms
                    else "当前更适合先补基础证据，再谈新概念。回答需要稳定抓手，品牌叙事才会被模型接住。"
                ),
            ],
            "supporting_facts": facts_from_finding(strong_finding)
            or [f"近端资产：{_join_report_terms(strong_terms, '暂未形成')}。"],
            "evidence_refs": refs_from_finding(strong_finding),
            "next_probe": "围绕近端资产追加产品事实题、场景题和品牌锚定题，观察它们是否仍被平台主动引用。",
        },
        {
            "section_id": "growth_opportunities",
            "role": "opportunity_finding",
            "title": "正在靠近的机会",
            "reader_question": "哪些词已经能连到品牌，但还需要更多证据才能站稳？",
            "takeaway": (
                f"{_join_report_terms(growth_terms + story_terms, '机会词')}可以作为下一轮拉近对象。"
                if growth_terms or story_terms
                else "新的需求场景尚未形成稳定机会词。"
            ),
            "claims": [
                f"可拉近机会：{_join_report_terms(growth_terms, '暂未形成')}。",
                f"长期观察词：{_join_report_terms(story_terms, '暂未形成')}。",
            ],
            "so_what": (
                "机会词需要通过问题、内容和回答证据反复带回中心品牌。"
            ),
            "paragraphs": [
                (
                    f"{_join_report_terms(growth_terms, '机会词')}已经能通向{center_term}，"
                    "只是出现频率和平台一致性还不够稳。下一轮要看它们能否进入更稳定的品牌资产区。"
                    if growth_terms
                    else "机会区暂时还不够集中，新的需求场景尚未被平台回答稳定带回品牌。"
                ),
                (
                    f"{_join_report_terms(story_terms, '观察词')}更适合作为观察词。"
                    "它们尚未成为成熟资产，但可能接到长寿、陪伴、人生阶段和美好生活这些长期议题。"
                    if story_terms
                    else "如果要建立新的品牌联想，下一轮问题和内容应更多覆盖人群、生活场景和真实使用理由。"
                ),
            ],
            "supporting_facts": facts_from_finding(growth_finding)
            or [f"机会词：{_join_report_terms(growth_terms + story_terms, '暂未形成')}。"],
            "evidence_refs": refs_from_finding(growth_finding),
            "next_probe": "把机会词拆成自然提问、路径提问和品牌锚定提问，分别看平台是否会主动连回品牌。",
        },
        {
            "section_id": "risk_relationship",
            "role": "risk_finding",
            "title": "需要拆开的风险关系",
            "reader_question": "哪些旧认知会把回答带向信任、合规或销售关系问题？",
            "takeaway": (
                f"{_join_report_terms(risk_terms, '风险词')}应作为风险关系单独追踪。"
                if risk_terms
                else "风险认知这一轮没有被明显放大，但仍需作为基线留存。"
            ),
            "claims": [
                f"风险节点数量：{risk_count}。",
                "风险判断只看回答中真实出现的信任、合规、销售方式或争议表达。",
            ],
            "so_what": (
                "风险单独成类；需要在风险视图里看出现频率、平台来源和替代证据。"
            ),
            "paragraphs": [
                (
                    f"{_join_report_terms(risk_terms, '风险词')}会把回答从产品和健康带到信任、"
                    "争议或销售方式。它们归入风险关系，单独追踪。"
                    if risk_terms
                    else "这一轮风险认知没有被明显放大。这个结果可以保留为基线，下轮继续观察具体问题或特定平台里的变化。"
                ),
                "风险图只看三件事：是否反复出现，在哪些平台出现，能否被新的正向证据替代。",
            ],
            "supporting_facts": facts_from_finding(risk_finding)
            or [f"风险节点：{len(risk_terms)} 个。"],
            "evidence_refs": refs_from_finding(risk_finding),
            "next_probe": "风险词下一轮不和正向资产混看，单独追踪出现频率、平台来源和可替代证据。",
        },
        {
            "section_id": "platform_entry",
            "role": "platform_finding",
            "title": "平台偏好暴露了内容入口",
            "reader_question": "不同平台会优先接住哪类品牌语境？",
            "takeaway": (
                f"{platform_name}这一轮更容易从“{platform_preference}”进入{center_term}。"
                if first_platform
                else "平台偏好样本还不足，暂不形成稳定判断。"
            ),
            "claims": [
                (
                    f"{platform_name}有效回答 {int(first_platform.get('valid_answer_count') or 0)} 条。"
                    if first_platform
                    else "平台有效样本不足。"
                ),
                (
                    f"代表节点：{_join_report_terms(first_platform.get('preferred_nodes') or [], '待观察')}。"
                    if first_platform
                    else "代表节点待观察。"
                ),
            ],
            "so_what": (
                "同一品牌在不同平台会被不同入口接住；内容建设应按平台补证据，避免用一套话术覆盖所有平台。"
            ),
            "paragraphs": [
                (
                    f"{platform_name}这一轮偏向“{platform_preference}”。同一个中心品牌，"
                    "在不同平台会先进入不同入口：产品、健康、社群，或风险解释。"
                    if first_platform
                    else "平台样本还不足时，先保留为观察项。样本更完整后，这部分会成为内容分发和证据建设的依据。"
                ),
                (
                    f"内容准备要跟着平台入口走。{_clean_text(first_platform.get('recommendation'))}"
                    if _clean_text(first_platform.get("recommendation"))
                    else "内容准备要跟着平台入口走，每个平台优先补它最容易采用的证据。"
                ),
            ],
            "supporting_facts": [
                (
                    f"{platform_name}有效回答 "
                    f"{int(first_platform.get('valid_answer_count') or 0)} 条，"
                    f"代表节点：{_join_report_terms(first_platform.get('preferred_nodes') or [], '待观察')}。"
                )
                if first_platform
                else "平台样本不足，暂不形成平台偏好判断。",
            ],
            "evidence_refs": [],
            "next_probe": "下一轮按平台分别补材料，比较它们是否仍沿同一入口组织回答。",
        },
        {
            "section_id": "evidence_action",
            "role": "action_finding",
            "title": "下一轮该验证什么",
            "reader_question": "哪些内容证据、澄清动作和复测问题应该先执行？",
            "takeaway": (
                f"下一轮先围绕“{action_title}”补证据并复测。"
                if action_title
                else "下一轮应沿用同一问题口径，复测资产、机会和风险是否移动。"
            ),
            "claims": [
                (
                    f"证据样本来自 {evidence_platform}，节点为“{evidence_term}”。"
                    if first_evidence
                    else "当前暂未形成可引用证据样本。"
                ),
                "行动需要能追溯到节点、问题和原文摘录。",
            ],
            "so_what": (
                "报告的价值还在于把下一轮要补的内容、要问的问题和要追踪的变化固定下来。"
            ),
            "paragraphs": [
                (
                    f"可以先看一条原文证据：{evidence_platform}在回答“{evidence_question}”时，"
                    f"把“{evidence_term}”带了出来。原文能看见平台组织答案的方式，也能看见品牌应该补哪类材料。"
                    if evidence_question
                    else "下一步仍然要保留原始回答。没有原文，圈层只是一张图；有了原文，品牌才能知道该补哪条证据。"
                ),
                (
                    f"本轮先处理一个节点：{action_title}。目标很具体，"
                    "让下一轮回答看见更清楚、更可信的品牌证据。"
                    if action_title
                    else "下一轮围绕机会词补内容，围绕风险词补澄清，并用同一组问题复测变化。"
                ),
            ],
            "supporting_facts": [
                (
                    f"证据样本：{_clean_text(first_evidence.get('evidence_id'))}；"
                    f"节点：{evidence_term}；平台：{evidence_platform}。"
                )
                if first_evidence
                else "暂未形成可引用证据样本。",
            ],
            "evidence_refs": [
                _clean_text(first_evidence.get("evidence_id"))
            ]
            if first_evidence
            else [],
            "next_probe": (
                _clean_text(first_action.get("next_question_suggestion"))
                if first_action
                else "用同一组问题复测，再看近端资产、机会词和风险关系是否移动。"
            ),
        },
    ]
    return sections


def _render_narrative_markdown(
    title: str,
    narrative_sections: list[dict[str, Any]],
) -> list[str]:
    lines = [f"# {title}", ""]
    for section in narrative_sections:
        lines.extend([f"## {section.get('title')}", ""])
        reader_question = _clean_text(section.get("reader_question"))
        if reader_question:
            lines.extend([f"> {reader_question}", ""])
        takeaway = _clean_text(section.get("takeaway"))
        if takeaway:
            lines.extend([f"**{takeaway}**", ""])
        claims = [
            _clean_text(claim)
            for claim in section.get("claims") or []
            if _clean_text(claim)
        ]
        if claims:
            lines.extend(["要看见的事实：", ""])
            for claim in claims[:4]:
                lines.append(f"- {claim}")
            lines.append("")
        for paragraph in section.get("paragraphs") or []:
            text = _clean_text(paragraph)
            if text:
                lines.extend([text, ""])
        so_what = _clean_text(section.get("so_what"))
        if so_what:
            lines.extend([so_what, ""])
        facts = [
            _clean_text(fact)
            for fact in section.get("supporting_facts") or []
            if _clean_text(fact)
        ]
        if facts:
            for fact in facts[:3]:
                if fact.startswith(("平台原文", "AI 原文", "平台原文样本")):
                    lines.append(f"> {fact}")
                else:
                    lines.append(f"- {fact}")
            lines.append("")
        next_probe = _clean_text(section.get("next_probe"))
        if next_probe:
            lines.extend([next_probe, ""])
    return lines


def _build_report_quality_checks(
    *,
    narrative_sections: list[dict[str, Any]],
    question_definition: dict[str, Any],
    platform_source_summary: dict[str, Any],
    evidence_findings: list[dict[str, Any]],
    association_actions: list[dict[str, Any]],
    source_appendix: list[dict[str, Any]],
) -> dict[str, Any]:
    narrative_text = "\n".join(
        [
            _clean_text(section.get("title"))
            + "\n"
            + "\n".join(
                _clean_text(paragraph)
                for paragraph in section.get("paragraphs") or []
                if _clean_text(paragraph)
            )
            for section in narrative_sections
        ]
    )
    forbidden_hits = [
        phrase for phrase in REPORT_COPY_FORBIDDEN_PHRASES if phrase in narrative_text
    ]
    forbidden_pattern_hits = [
        pattern
        for pattern in REPORT_COPY_FORBIDDEN_PATTERNS
        if re.search(pattern, narrative_text)
    ]
    evidence_bound_roles = {
        "executive_summary",
        "asset_finding",
        "opportunity_finding",
        "risk_finding",
        "action_finding",
    }
    section_evidence_gaps = []
    section_takeaway_gaps = []
    section_contract_gaps = []

    def section_field_missing(section: dict[str, Any], field_name: str) -> bool:
        value = section.get(field_name)
        if isinstance(value, list):
            return not any(_clean_text(item) for item in value)
        return not bool(_clean_text(value))

    for section in narrative_sections:
        missing_fields = [
            field_name
            for field_name in REPORT_NARRATIVE_SECTION_REQUIRED_FIELDS
            if section_field_missing(section, field_name)
        ]
        if missing_fields:
            section_contract_gaps.append(
                {
                    "section_id": section.get("section_id"),
                    "title": section.get("title"),
                    "missing_fields": missing_fields,
                }
            )
        if not _clean_text(section.get("takeaway")):
            section_takeaway_gaps.append(
                {
                    "section_id": section.get("section_id"),
                    "title": section.get("title"),
                }
            )
        if str(section.get("role") or "") not in evidence_bound_roles:
            continue
        has_fact = bool(section.get("supporting_facts"))
        has_refs = bool(section.get("evidence_refs"))
        if not (has_fact or has_refs):
            section_evidence_gaps.append(
                {
                    "section_id": section.get("section_id"),
                    "title": section.get("title"),
                }
            )
    source_platforms = {
        _clean_text(item.get("platform") or item.get("source_platform"))
        for item in source_appendix
        if isinstance(item, dict)
        and _clean_text(item.get("platform") or item.get("source_platform"))
    }
    source_questions = {
        _clean_text(item.get("question_id"))
        for item in source_appendix
        if isinstance(item, dict) and _clean_text(item.get("question_id"))
    }
    expected_platforms = int(platform_source_summary.get("valid_platform_count") or 0)
    if not expected_platforms:
        expected_platforms = int(platform_source_summary.get("platform_count") or 0)
    available_questions = int(question_definition.get("question_count") or 0)
    if not available_questions:
        available_questions = len(question_definition.get("sample_questions") or [])
    minimum_platforms = min(max(expected_platforms, 1), 2)
    minimum_questions = min(max(available_questions, 1), 2) if len(source_appendix) >= 6 else 1
    required_checks = [
        {
            "key": "question_definition",
            "label": "题目定义",
            "passed": bool(
                question_definition.get("definition_sentence")
                and question_definition.get("sample_questions")
            ),
        },
        {
            "key": "platform_source_summary",
            "label": "平台来源",
            "passed": bool(
                platform_source_summary.get("platform_count")
                and platform_source_summary.get("platforms")
            ),
        },
        {
            "key": "evidence_findings",
            "label": "证据链",
            "passed": bool(
                evidence_findings
                and all(
                    finding.get("supporting_facts") and finding.get("evidence_refs")
                    for finding in evidence_findings[:3]
                )
            ),
        },
        {
            "key": "action_review",
            "label": "行动复测",
            "passed": bool(
                association_actions
                and any(action.get("evidence_refs") for action in association_actions)
            ),
        },
        {
            "key": "source_appendix",
            "label": "来源附录",
            "passed": bool(source_appendix),
        },
        {
            "key": "source_appendix_diversity",
            "label": "来源多样性",
            "passed": (
                bool(source_appendix)
                and len(source_platforms) >= minimum_platforms
                and len(source_questions) >= minimum_questions
            ),
            "platform_count": len(source_platforms),
            "question_count": len(source_questions),
            "minimum_platforms": minimum_platforms,
            "minimum_questions": minimum_questions,
        },
        {
            "key": "section_evidence_binding",
            "label": "章节证据绑定",
            "passed": not section_evidence_gaps,
            "gaps": section_evidence_gaps,
        },
        {
            "key": "section_takeaway",
            "label": "章节核心判断",
            "passed": not section_takeaway_gaps,
            "gaps": section_takeaway_gaps,
        },
        {
            "key": "section_contract",
            "label": "章节叙事契约",
            "passed": not section_contract_gaps,
            "gaps": section_contract_gaps,
        },
    ]
    return {
        "version": REPORT_COPY_CONSTRAINT_VERSION,
        "required_spine": list(REPORT_REQUIRED_EVIDENCE_SPINE),
        "passed": not forbidden_hits
        and not forbidden_pattern_hits
        and all(bool(item.get("passed")) for item in required_checks),
        "forbidden_hits": forbidden_hits,
        "forbidden_pattern_hits": forbidden_pattern_hits,
        "required_checks": required_checks,
    }


def _build_report_markdown(
    title: str,
    sample_scope: dict[str, Any],
    executive_summary: dict[str, Any],
    nodes: list[dict[str, Any]],
    platform_comparison: list[dict[str, Any]],
    evidence_samples: list[dict[str, Any]],
    association_actions: list[dict[str, Any]],
    narrative_sections: list[dict[str, Any]],
    question_definition: dict[str, Any],
    platform_source_summary: dict[str, Any],
    evidence_findings: list[dict[str, Any]],
    report_outline: list[dict[str, Any]],
    analysis_tool_trace: list[dict[str, Any]],
    source_appendix: list[dict[str, Any]],
) -> str:
    orbit_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        orbit_groups[str(node.get("orbit") or "weak")].append(node)
    lines = _render_narrative_markdown(title, narrative_sections)
    lines.extend(
        [
            "## 这轮问题在问什么",
            "",
            _clean_text(question_definition.get("definition_sentence")),
            "",
            "### 题目覆盖",
            "",
            (
                f"- 人群：{_join_report_terms(question_definition.get('audience_segments') or [], '待补充')}\n"
                f"- 探针：{_join_report_terms(question_definition.get('probe_types') or [], '待补充')}\n"
                f"- 机会点：{_join_report_terms(question_definition.get('opportunity_points') or [], '待补充')}\n"
                f"- 生活场景：{_join_report_terms(question_definition.get('life_scenes') or [], '待补充')}"
            ),
            "",
            "### 代表问题",
            "",
        ]
    )
    for item in question_definition.get("sample_questions") or []:
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("text"))
        if not text:
            continue
        lines.append(
            f"- {text}（{_clean_text(item.get('audience_segment')) or '未标注人群'} / "
            f"{_clean_text(item.get('probe_type')) or '未标注探针'}）"
        )
    lines.extend(
        [
            "",
            "## 样本从哪些平台来",
            "",
            (
                f"本轮向 {platform_source_summary.get('platform_count', 0)} 个平台请求回答，"
                f"共记录 {platform_source_summary.get('total_answer_count', 0)} 条返回；"
                f"其中有效回答 {platform_source_summary.get('valid_answer_count', 0)} 条，"
                f"失败 {platform_source_summary.get('failed_answer_count', 0)} 条，"
                f"空回答 {platform_source_summary.get('empty_answer_count', 0)} 条。"
            ),
            "",
            "| 平台 | 有效回答 | 失败 | 空回答 | 回答偏好 | 代表节点 |",
            "| --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in platform_source_summary.get("platforms") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _clean_text(row.get("platform")),
                    str(int(row.get("valid_answer_count") or 0)),
                    str(int(row.get("failed_answer_count") or 0)),
                    str(int(row.get("empty_answer_count") or 0)),
                    _clean_text(row.get("answer_preference")) or "待观察",
                    "、".join(row.get("preferred_nodes") or []) or "暂无",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 关键判断从哪些回答来",
            "",
        ]
    )
    for finding in evidence_findings[:10]:
        lines.extend(
            [
                f"### {finding.get('node_term')}",
                "",
                _clean_text(finding.get("claim")),
                "",
            ]
        )
        for fact in finding.get("supporting_facts") or []:
            text = _clean_text(fact)
            if text:
                lines.append(f"- {text}")
        if finding.get("sample_excerpt"):
            lines.extend(
                [
                    "",
                    (
                        f"> {_clean_text(finding.get('sample_platform'))} / "
                        f"{_clean_text(finding.get('sample_question'))}: "
                        f"{_clean_text(finding.get('sample_excerpt'))}"
                    ),
                ]
            )
        lines.append("")
    lines.extend(
        [
            "## 分析依据轨迹",
            "",
        ]
    )
    for trace in analysis_tool_trace:
        lines.extend([f"### {trace.get('title')}", "", _clean_text(trace.get("summary")), ""])
        outputs = trace.get("outputs")
        if isinstance(outputs, list):
            for output in outputs[:8]:
                text = _clean_text(output)
                if text:
                    lines.append(f"- {text}")
            lines.append("")
    if report_outline:
        lines.extend(["## 报告章节任务", ""])
        for chapter in report_outline:
            lines.append(
                f"- **{chapter.get('title')}**：{chapter.get('reader_question')}"
            )
        lines.append("")
    lines.extend(
        [
            "## 数据附录",
            "",
            "### 样本口径",
            "",
            (
                f"本次样本包含 {sample_scope.get('question_count', 0)} 个问题、"
                f"{sample_scope.get('valid_answer_count', 0)} 条有效回答、"
                f"{sample_scope.get('failed_answer_count', 0)} 条失败回答、"
                f"{sample_scope.get('empty_answer_count', 0)} 条空回答、"
                f"{sample_scope.get('platform_count', 0)} 个平台，解析出 "
                f"{sample_scope.get('normalized_node_count', 0)} 个联想节点。"
            ),
            "",
            (
                "图谱位置由出现频率、回答位置、关系类型、场景覆盖和跨平台一致性加权生成；"
                "证据缺口表示这个词还需要多少内容、问题或原文证据才能稳定回到品牌。"
            ),
            "",
            "### 节点清单",
            "",
        ]
    )
    for orbit, label in (
        ("core_near", "核心稳定"),
        ("strong", "已绑定资产"),
        ("near_opportunity", "近端机会"),
        ("far_opportunity", "远端机会"),
        ("weak", "待观察"),
        ("blank", "远端待验证"),
        (RISK_ORBIT, "风险关系"),
    ):
        orbit_nodes = orbit_groups.get(orbit, [])
        if not orbit_nodes:
            continue
        lines.extend([f"### {label}", ""])
        for node in orbit_nodes[:6]:
            lines.append(
                f"- **{node.get('term')}**：图谱贴近值 {node.get('gravity_score')}，"
                f"距离值 {node.get('distance_score')}，{node.get('business_tag')}。"
                f"读数来源：回答频率 {node.get('frequency_score')} / 回答位置 {node.get('position_score')} / "
                f"品牌关系 {node.get('relation_type_score')} / 场景覆盖 {node.get('scene_coverage_score')} / "
                f"平台一致性 {node.get('model_consistency_score')}。"
                f"{node.get('orbit_reason')}"
            )
        lines.append("")
    lines.extend(["## 平台差异", ""])
    for item in platform_comparison:
        lines.append(
            f"- **{item.get('platform')}**：{item.get('answer_preference')}；"
            f"代表节点：{'、'.join(item.get('preferred_nodes') or []) or '暂无'}；"
            f"建议：{item.get('recommendation')}"
        )
    lines.extend(["", "## 人群触发路径", ""])
    for node in nodes[:8]:
        audience = (
            "、".join(node.get("primary_audience_segments") or []) or "未标注人群"
        )
        opportunity = (
            "、".join(node.get("primary_opportunity_points") or []) or "未标注机会点"
        )
        lines.append(
            f"- **{node.get('term')}**：主要由 {audience} / {opportunity} 触发。"
        )
    lines.extend(["", "## 证据样本", ""])
    for evidence in evidence_samples[:8]:
        lines.append(
            f"- **{evidence.get('node_term')} / {evidence.get('platform')}**："
            f"{evidence.get('question')} -> {evidence.get('answer_excerpt')}"
        )
    if source_appendix:
        lines.extend(["", "## 来源附录", ""])
        for item in source_appendix[:12]:
            lines.append(
                f"- {item.get('evidence_id')} / {item.get('platform')} / "
                f"{item.get('node_term')}：{item.get('question')}"
            )
    lines.extend(["", "## 行动清单", ""])
    if association_actions:
        for action in association_actions[:6]:
            lines.append(
                f"- **{action.get('action_label')}**：{action.get('title')}。"
                f"{action.get('expected_impact')}"
            )
    else:
        lines.extend(
            [
                "- 优先放大核心稳定和已绑定资产中的正向健康资产。",
                "- 对风险关系中的旧认知进行转译，先补澄清证据。",
                "- 对弱信号和远端待验证方向补充问题和内容证据，进入下一轮复测。",
            ]
        )
    return "\n".join(line for line in lines if line is not None).strip()


def _question_set_version_from_simulated(value: Any) -> str | None:
    questions: list[Any] = []
    if isinstance(value, dict):
        normalized_payload = value.get("normalized_payload")
        normalized_payload = (
            normalized_payload if isinstance(normalized_payload, dict) else {}
        )
        raw = (
            value.get("simulated_questions")
            or value.get("questions")
            or normalized_payload.get("questions")
        )
        if isinstance(raw, list):
            questions = raw
    elif isinstance(value, list):
        questions = value
    for question in questions:
        if not isinstance(question, dict):
            continue
        version = _clean_text(question.get("question_set_version"))
        if version:
            return version
    return None


def _iter_question_payloads(value: Any) -> list[Any]:
    if isinstance(value, dict):
        normalized_payload = value.get("normalized_payload")
        normalized_payload = (
            normalized_payload if isinstance(normalized_payload, dict) else {}
        )
        raw = (
            value.get("simulated_questions")
            or value.get("questions")
            or normalized_payload.get("questions")
        )
        return raw if isinstance(raw, list) else []
    return value if isinstance(value, list) else []


def _question_text_from_payload(value: Any, index: int) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if not isinstance(value, dict):
        return ""
    return (
        _clean_text(value.get("text"))
        or _clean_text(value.get("core_question"))
        or _clean_text(value.get("question"))
        or _clean_text(value.get("question_text"))
        or _clean_text(value.get("query"))
        or f"问题 {index}"
    )


def _question_id_from_payload(value: Any, index: int) -> str:
    if not isinstance(value, dict):
        return f"q_{index:03d}"
    return (
        _clean_text(value.get("id"))
        or _clean_text(value.get("question_id"))
        or _clean_text(value.get("question_key"))
        or f"q_{index:03d}"
    )


def _normalize_question_bank_item(value: Any, index: int) -> dict[str, Any] | None:
    text = _question_text_from_payload(value, index)
    if not text:
        return None
    item: dict[str, Any] = {
        "id": _question_id_from_payload(value, index),
        "text": text,
        "source": "question_bank",
    }
    if isinstance(value, dict):
        for key in QUESTION_BANK_METADATA_KEYS:
            raw = value.get(key)
            if raw is None or raw == "":
                continue
            if key == "center_terms" and isinstance(raw, list):
                item[key] = [_clean_text(term) for term in raw if _clean_text(term)]
            else:
                item[key] = raw
        source = _clean_text(value.get("source"))
        if source:
            item["source"] = source
    missing = [
        key for key in QUESTION_BANK_REQUIRED_METADATA_KEYS if not _clean_text(item.get(key))
    ]
    if "metadata_status" not in item:
        item["metadata_status"] = "ready" if not missing else "inferred_needs_review"
    if missing:
        item["metadata_missing_fields"] = missing
    return item


def _question_bank_from_fetch_results(fetch_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for index, row in enumerate(fetch_results or [], start=1):
        if not isinstance(row, dict):
            continue
        item = _normalize_question_bank_item(
            {
                "id": _clean_text(row.get("question_id")) or f"q_{index:03d}",
                "text": _question_from_fetch_row(row, index),
                "audience_segment": row.get("audience_segment"),
                "core_anxiety": row.get("core_anxiety") or row.get("linked_pain_point"),
                "life_scene": row.get("life_scene")
                or row.get("linked_scenario")
                or row.get("category"),
                "opportunity_point": row.get("opportunity_point")
                or row.get("monitoring_purpose")
                or row.get("mother_theme")
                or row.get("opportunity"),
                "probe_type": row.get("probe_type")
                or row.get("question_type")
                or row.get("intent"),
                "mother_theme": row.get("mother_theme") or row.get("category"),
                "question_type": row.get("question_type") or row.get("probe_type"),
                "mentions_amway": row.get("mentions_amway"),
                "life_stage": row.get("life_stage") or row.get("audience_segment"),
                "four_have": row.get("four_have"),
                "touchpoint": row.get("touchpoint") or row.get("life_scene"),
                "monitoring_purpose": row.get("monitoring_purpose")
                or row.get("opportunity_point"),
                "source": "fetch_result",
            },
            index,
        )
        if item:
            questions.append(item)
    return questions


def _build_question_bank(
    simulated_questions: list[dict[str, Any]] | dict[str, Any] | None,
    fetch_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []

    def add_item(item: dict[str, Any] | None) -> None:
        if not item:
            return
        key = _clean_text(item.get("id")) or _clean_text(item.get("text"))
        if not key:
            return
        if key not in by_key:
            ordered_keys.append(key)
            by_key[key] = item
            return
        merged = {**by_key[key], **{k: v for k, v in item.items() if v not in (None, "", [])}}
        by_key[key] = merged

    for index, value in enumerate(_iter_question_payloads(simulated_questions), start=1):
        add_item(_normalize_question_bank_item(value, index))

    for item in _question_bank_from_fetch_results(fetch_results):
        add_item(item)

    return [by_key[key] for key in ordered_keys]


def _extract_calibrated_report_input(
    entity_calibration_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(entity_calibration_result, dict):
        return None
    report_input = entity_calibration_result.get("report_input")
    if isinstance(report_input, dict):
        return report_input
    if isinstance(entity_calibration_result.get("association_map"), dict):
        return {
            "question_scope": entity_calibration_result.get("question_scope") or {},
            "platform_scope": entity_calibration_result.get("platform_summary") or {},
            "association_map": entity_calibration_result.get("association_map") or {},
            "strategy_validation": (
                entity_calibration_result.get("strategy_validation") or []
            ),
            "strategy_storyline": entity_calibration_result.get("strategy_storyline")
            or {},
            "risk_summary": entity_calibration_result.get("risk_map") or {},
            "evidence_findings": entity_calibration_result.get("evidence_findings")
            or [],
            "source_appendix": entity_calibration_result.get("source_appendix") or [],
            "association_actions": entity_calibration_result.get(
                "association_actions"
            )
            or [],
            "tracking_projection": entity_calibration_result.get(
                "tracking_projection"
            )
            or {},
        }
    return None


def _build_calibrated_executive_summary(
    *,
    center_terms: list[str],
    sample_scope: dict[str, Any],
    nodes: list[dict[str, Any]],
    strategy_validation: list[dict[str, Any]],
    risk_summary: dict[str, Any],
) -> dict[str, Any]:
    center_term = _first_center_term(center_terms)
    strong_terms = [
        _clean_text(node.get("term"))
        for node in nodes
        if _is_strong_report_node(node)
    ][:3]
    growth_terms = [
        _clean_text(node.get("term"))
        for node in nodes
        if _is_growth_report_node(node)
    ][:3]
    far_terms = _top_far_terms_for_report(nodes, limit=3)
    competition_terms = _top_competition_terms_for_report(nodes, limit=3)
    validated_strategies = [
        _clean_text(item.get("strategy_term"))
        for item in strategy_validation
        if item.get("status") == "validated"
    ][:3]
    partial_strategies = [
        _clean_text(item.get("strategy_term"))
        for item in strategy_validation
        if item.get("status") == "partial"
    ][:3]
    risk_count = int(risk_summary.get("risk_count") or 0)
    competition_count = int(risk_summary.get("competition_count") or 0)
    valid_answers = int(sample_scope.get("valid_answer_count") or 0)
    platform_count = int(sample_scope.get("platform_count") or 0)
    missing_strategy_count = sum(
        1 for item in strategy_validation if item.get("status") == "missing"
    )
    validated_count = sum(
        1 for item in strategy_validation if item.get("status") == "validated"
    )
    partial_count = sum(
        1 for item in strategy_validation if item.get("status") == "partial"
    )
    overall_status = _overall_strategy_status_label(
        validated_count=validated_count,
        partial_count=partial_count,
        missing_count=missing_strategy_count,
        risk_count=risk_count,
    )
    one_line = (
        f"{center_term}本轮近端资产集中在"
        f"{_join_report_terms(strong_terms, '待形成稳定第一反应')}；"
        f"可拉近机会集中在{_join_report_terms(growth_terms, '待继续采样')}；"
        f"远端观察词包括{_join_report_terms(far_terms, '待继续观察')}；"
        f"总体判断为{overall_status}，竞品和风险关系 {risk_count} 个，其中竞品参照 {competition_count} 个。"
    )
    return {
        "one_line_judgment": one_line,
        "current_default_identity": _join_report_terms(strong_terms, "暂无稳定外围联想"),
        "primary_opportunity": _join_report_terms(
            growth_terms or partial_strategies,
            "继续补战略证据",
        ),
        "primary_risk": (
            f"风险关系 {risk_count} 个，竞品参照 {competition_count} 个，需要单独追踪。"
            if risk_count
            else "本轮风险认知未明显放大。"
        ),
        "far_terms": far_terms,
        "competition_terms": competition_terms,
        "validated_strategies": validated_strategies,
        "partial_strategies": partial_strategies,
        "missing_strategy_count": missing_strategy_count,
        "validated_strategy_count": validated_count,
        "partial_strategy_count": partial_count,
        "overall_strategy_status": overall_status,
        "sample_sentence": (
            f"本轮读取 {valid_answers} 条有效回答，覆盖 {platform_count} 个平台。"
        ),
    }


def _overall_strategy_status_label(
    *,
    validated_count: int,
    partial_count: int,
    missing_count: int,
    risk_count: int,
) -> str:
    if risk_count >= max(validated_count + partial_count, 1) and risk_count >= 3:
        return "被风险遮蔽"
    if validated_count >= max(partial_count + missing_count, 1):
        return "回答接住较多"
    if validated_count or partial_count:
        return "部分验证"
    return "尚未验证"


def _strategy_section_rows(
    strategy_validation: list[dict[str, Any]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in strategy_validation
        if row.get("status") in {"validated", "partial", "risk"}
        or int(row.get("question_count") or 0) > 0
    ]
    if not rows:
        rows = strategy_validation[:limit]
    return rows[:limit]


def _platform_strategy_sentence(row: dict[str, Any]) -> str:
    distribution = row.get("platform_distribution")
    if not isinstance(distribution, dict) or not distribution:
        return "平台暂未形成稳定提及。"
    parts = [
        f"{platform}{count}"
        for platform, count in sorted(distribution.items(), key=lambda item: str(item[0]))
        if int(count or 0) > 0
    ]
    return "平台提及：" + "、".join(parts[:6]) + "。" if parts else "平台暂未形成稳定提及。"


def _strategy_platform_comparison_lines(
    strategy_validation: list[dict[str, Any]],
    limit: int = 6,
) -> list[str]:
    lines: list[str] = []
    for row in strategy_validation:
        term = _clean_text(row.get("strategy_term"))
        if not term:
            continue
        outcomes = [
            item
            for item in row.get("platform_outcomes") or []
            if isinstance(item, dict) and _clean_text(item.get("platform"))
        ]
        platform_parts: list[str] = []
        for item in outcomes[:4]:
            platform = _clean_text(item.get("platform"))
            count = int(item.get("answer_count") or 0)
            sample = _clean_text(item.get("sample_excerpt"))
            if not platform:
                continue
            if count <= 0:
                platform_parts.append(f"{platform}未提及")
            elif sample:
                platform_parts.append(f"{platform}提及 {count} 次，样本指向“{sample[:40]}”")
            else:
                platform_parts.append(f"{platform}提及 {count} 次")
        if not platform_parts:
            distribution = row.get("platform_distribution")
            if isinstance(distribution, dict):
                platform_parts = [
                    f"{platform}提及 {int(count or 0)} 次"
                    for platform, count in sorted(
                        distribution.items(),
                        key=lambda item: str(item[0]),
                    )
                    if int(count or 0) > 0
                ][:4]
        if platform_parts:
            lines.append(
                f"{term}：{_strategy_row_status_label(row)}，"
                + "；".join(platform_parts)
                + "。"
            )
        if len(lines) >= limit:
            break
    return lines


def _risk_scene_lines_for_report(
    risk_summary: dict[str, Any],
    key: str,
    *,
    limit: int = 4,
) -> list[str]:
    rows = risk_summary.get(key)
    if not isinstance(rows, list):
        return []
    lines: list[str] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        term = _clean_text(row.get("node_term"))
        scenes = _join_report_terms(row.get("scenes") or [], "未标注场景")
        distribution = row.get("platform_distribution")
        platform_text = _platform_distribution_sentence(distribution)
        sample = _clean_text(row.get("sample_excerpt"))
        sample_text = f"样本原文指向“{sample[:72]}”。" if sample else ""
        if term:
            lines.append(
                f"{term}主要出现在{scenes}，{platform_text}{sample_text}"
            )
    return lines


def _platform_distribution_sentence(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "平台分布待继续观察。"
    parts = [
        f"{platform}{int(count or 0)}次"
        for platform, count in sorted(value.items(), key=lambda item: str(item[0]))
        if _clean_text(platform) and int(count or 0) > 0
    ]
    if not parts:
        return "平台分布待继续观察。"
    return "平台分布为" + "、".join(parts[:5]) + "。"


def _strategy_status_label(status: Any) -> str:
    return {
        "validated": "已被回答接住",
        "partial": "部分验证",
        "missing": "尚未验证",
        "risk": "风险遮蔽",
    }.get(str(status or ""), "待观察")


def _strategy_row_status_label(row: dict[str, Any]) -> str:
    return _clean_text(row.get("validation_label")) or _strategy_status_label(
        row.get("status")
    )


def _platform_stance_label(stance: Any) -> str:
    value = str(stance or "")
    if value == "supportive":
        return "正向提及"
    if value == "skeptical":
        return "质疑提及"
    if value == "risk":
        return "风险提醒"
    if value == "competitive":
        return "竞品替代"
    if value == "neutral":
        return "中性提及"
    return "提到"


def _strategy_intent_sentence(term: Any) -> str:
    text = _clean_text(term)
    if any(keyword in text for keyword in ("健康", "抗衰", "长寿", "百岁")):
        return "让品牌从单一产品认知进入长期健康管理和人生周期支持。"
    if any(keyword in text for keyword in ("陪伴", "关系", "一起", "社群")):
        return "让品牌承担关系连接、社群支持和持续陪伴的心智角色。"
    if any(keyword in text for keyword in ("人生", "价值", "再出发", "安利人")):
        return "让品牌连接个人成长、角色转换和重新被需要的生活叙事。"
    if any(keyword in text for keyword in ("科技", "产品", "美好生活")):
        return "让品牌把产品证据、生活方式和体验场景合成可被复述的品牌资产。"
    return "让该词成为平台回答可以自然带回品牌的目标心智。"


def _strategy_question_sentence(row: dict[str, Any]) -> str:
    question_count = int(row.get("question_count") or 0)
    question_samples = [
        item
        for item in row.get("question_samples") or []
        if isinstance(item, dict) and _clean_text(item.get("question"))
    ][:3]
    if question_samples:
        sample_text = "；".join(
            f"{_clean_text(item.get('question_id')) or '问题'}：{_clean_text(item.get('question'))[:72]}"
            for item in question_samples
        )
        return f"本轮有 {question_count} 个问题直接或间接测试该战略词。样题包括：{sample_text}。"
    refs = [
        _clean_text(item)
        for item in row.get("question_refs") or []
        if _clean_text(item)
    ][:6]
    if not question_count:
        return "题库里尚未形成明确测试题，需要下一轮补题。"
    suffix = f"；题号：{'、'.join(refs)}" if refs else ""
    return f"本轮有 {question_count} 个问题直接或间接测试该战略词{suffix}。"


def _strategy_platform_detail(row: dict[str, Any]) -> str:
    outcomes = [
        item for item in row.get("platform_outcomes") or [] if isinstance(item, dict)
    ]
    if outcomes:
        parts = []
        for item in outcomes[:5]:
            platform = _clean_text(item.get("platform"))
            answer_count = int(item.get("answer_count") or 0)
            excerpt = _clean_text(item.get("sample_excerpt"))
            stance_label = _platform_stance_label(item.get("stance"))
            if not platform:
                continue
            if answer_count <= 0:
                parts.append(f"{platform}未提及。")
            elif excerpt:
                parts.append(
                    f"{platform}{stance_label} {answer_count} 次，样本为“{excerpt[:72]}”。"
                )
            else:
                parts.append(f"{platform}{stance_label} {answer_count} 次。")
        if parts:
            return " ".join(parts)
    distribution = row.get("platform_distribution")
    if isinstance(distribution, dict) and distribution:
        parts = [
            f"{platform}{count}次"
            for platform, count in sorted(
                distribution.items(),
                key=lambda item: str(item[0]),
            )
            if int(count or 0) > 0
        ]
        if parts:
            return "平台提及分布：" + "、".join(parts[:6]) + "。"
    return "各个平台本轮没有形成可复述的稳定提及。"


def _strategy_platform_count_detail(row: dict[str, Any]) -> str:
    outcomes = [
        item for item in row.get("platform_outcomes") or [] if isinstance(item, dict)
    ]
    if outcomes:
        parts: list[str] = []
        for item in outcomes[:5]:
            platform = _clean_text(item.get("platform"))
            answer_count = int(item.get("answer_count") or 0)
            if not platform:
                continue
            if answer_count <= 0:
                parts.append(f"{platform}未提及")
            else:
                parts.append(
                    f"{platform}{_platform_stance_label(item.get('stance'))}{answer_count}次"
                )
        if parts:
            return "平台统计：" + "、".join(parts) + "。"
    distribution = row.get("platform_distribution")
    if isinstance(distribution, dict) and distribution:
        parts = [
            f"{platform}{int(count or 0)}次"
            for platform, count in sorted(
                distribution.items(),
                key=lambda item: str(item[0]),
            )
            if int(count or 0) > 0
        ]
        if parts:
            return "平台统计：" + "、".join(parts[:6]) + "。"
    return "平台统计待继续观察。"


def _strategy_graph_sentence(
    row: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> str:
    node_ids = [
        _clean_text(item)
        for item in row.get("related_node_ids") or []
        if _clean_text(item)
    ]
    nodes = [nodes_by_id[item] for item in node_ids if item in nodes_by_id]
    if not nodes:
        return "图谱上还没有形成可独立展示的节点，当前回答证据不足。"
    parts = []
    for node in nodes[:3]:
        distance = int(node.get("distance_score") or 0)
        evidence_count = int(node.get("evidence_count") or node.get("answer_count") or 0)
        platform_count = int(node.get("platform_count") or 0)
        parts.append(
            f"{node.get('term')}位于{node.get('orbit_label') or node.get('orbit')}，"
            f"距离值 {distance}，证据 {evidence_count} 条，覆盖 {platform_count} 个平台"
        )
    return "；".join(parts) + "。"


def _strategy_brand_meaning(row: dict[str, Any]) -> str:
    term = _clean_text(row.get("strategy_term"))
    status = str(row.get("status") or "")
    tier = _clean_text(row.get("decision_tier"))
    stance = row.get("stance_summary") if isinstance(row.get("stance_summary"), dict) else {}
    supportive = int(stance.get("supportive") or 0)
    skeptical = int(stance.get("skeptical") or 0)
    risk_like = int(stance.get("risk") or 0) + int(stance.get("competitive") or 0)
    answer_mentions = int(row.get("answer_mention_count") or 0)
    platform_count = int(row.get("platform_count") or 0)
    lane = _strategy_lane_for_report(term)
    if tier == "amplify" or (status == "validated" and supportive >= 30):
        focus = {
            "relationship": "关系陪伴已经被平台理解，下一步要补充社群边界和真实陪伴案例",
            "career": "事业与价值感已经被平台带回品牌，下一步要补收入边界和合规路径",
            "green": "绿色生活已经有回答线索，下一步要用家庭环境健康和产品证据承接",
            "health": "健康资产已经较清晰，下一步要沉淀科学依据、产品组合和人群场景",
        }.get(lane, "这个战略词已经具备放大基础，下一步要沉淀稳定表达")
        return (
            f"{term}有 {supportive or answer_mentions} 条正向支撑，覆盖 {platform_count} 个平台。"
            f"{focus}。"
        )
    if tier == "risk_first" or status == "risk":
        focus = {
            "relationship": "风险多来自熟人压力和销售边界，需要先解释社群支持机制",
            "career": "风险多来自收益预期和参与成本，需要先写清合规边界",
            "green": "风险多来自口号化表达，需要先补具体产品和场景证据",
            "health": "风险多来自功效和信任问题，需要先补科学依据和适用边界",
        }.get(lane, "需要先处理质疑来源，再判断能否进入正向资产")
        return (
            f"{term}被提及时伴随 {risk_like or answer_mentions} 条风险或竞品替代语境，"
            f"{focus}。"
        )
    if tier == "evidence_building" or status == "partial":
        focus = {
            "relationship": "关系词已经有入口，但需要更多退休、朋友网络和社群陪伴问题",
            "career": "成长或事业词已有入口，但需要拆清价值感、投入和收益边界",
            "green": "绿色词还要落到家庭环境健康、净水、空气净化和清洁场景",
            "health": "健康词需要更多具体方案、产品组合和长期管理证据",
        }.get(lane, "这个词已有入口，但仍需补问题和证据")
        return (
            f"{term}已有 {answer_mentions} 条回答线索，"
            f"其中质疑或风险语境 {skeptical + risk_like} 条；{focus}。"
        )
    return f"{term}在本轮回答里的可用证据不足，下一轮先补题和补品牌锚定证据。"


def _strategy_lane_for_report(term: str) -> str:
    if any(cue in term for cue in ("财务", "保障", "事业", "安利人", "价值", "再出发", "成长")):
        return "career"
    if any(cue in term for cue in ("关系", "陪伴", "社群", "一起")):
        return "relationship"
    if any(cue in term for cue in ("绿色", "和谐", "环境")):
        return "green"
    if any(cue in term for cue in ("健康", "抗衰", "长寿", "活力", "营养", "身体", "情绪", "大健康")):
        return "health"
    return "general"


def _association_action_lines_for_report(
    association_actions: list[dict[str, Any]],
    *,
    limit: int,
) -> list[str]:
    lines: list[str] = []
    for action in association_actions[:limit]:
        title = _clean_text(action.get("title") or action.get("node_term"))
        target_scene = _clean_text(action.get("target_scene"))
        platforms = _join_report_terms(
            [
                _clean_text(platform)
                for platform in action.get("target_platforms") or []
                if _clean_text(platform)
            ],
            "本轮有效平台",
        )
        goal = _clean_text(action.get("goal_metric"))
        if not title:
            continue
        detail_parts = []
        if target_scene:
            detail_parts.append(f"场景：{target_scene}")
        detail_parts.append(f"平台：{platforms}")
        if goal:
            detail_parts.append(f"目标：{goal}")
        lines.append(f"{title}：" + "；".join(detail_parts) + "。")
    return lines


def _build_four_have_report_narrative_sections(
    *,
    center_terms: list[str],
    sample_scope: dict[str, Any],
    executive_summary: dict[str, Any],
    nodes: list[dict[str, Any]],
    strategy_validation: list[dict[str, Any]],
    risk_summary: dict[str, Any],
    platform_source_summary: dict[str, Any],
    evidence_findings: list[dict[str, Any]],
    association_actions: list[dict[str, Any]],
    tracking_projection: dict[str, Any] | None,
    strategy_storyline: dict[str, Any],
) -> list[dict[str, Any]]:
    center_term = _first_center_term(center_terms)
    tracking_projection = tracking_projection or {}
    verdict = (
        strategy_storyline.get("verdict")
        if isinstance(strategy_storyline.get("verdict"), dict)
        else {}
    )
    pillars = {
        _clean_text(item.get("key")): item
        for item in strategy_storyline.get("pillars", [])
        if isinstance(item, dict) and _clean_text(item.get("key"))
    }
    health = pillars.get("have_health", {})
    companionship = pillars.get("have_companionship", {})
    security = pillars.get("have_security", {})
    value = pillars.get("have_value", {})
    companionship_has_risk = bool(companionship.get("risk_terms")) or _clean_text(
        companionship.get("status")
    ) == "emerging_hijacked"
    weekly_actions = [
        item
        for item in strategy_storyline.get("weekly_actions", [])
        if isinstance(item, dict)
    ]
    strong_terms = _top_terms_for_report(nodes, _is_strong_report_node, 5)
    growth_terms = _top_terms_for_report(nodes, _is_growth_report_node, 5)
    far_terms = _top_far_terms_for_report(nodes, limit=5)
    risk_terms = [
        _clean_text(node.get("term"))
        for node in risk_summary.get("risk_nodes", [])
        if isinstance(node, dict) and _clean_text(node.get("term"))
    ][:5]
    competition_terms = [
        _clean_text(node.get("term"))
        for node in risk_summary.get("competition_nodes", [])
        if isinstance(node, dict) and _clean_text(node.get("term"))
    ][:5]
    valid_answers = int(sample_scope.get("valid_answer_count") or 0)
    question_count = int(sample_scope.get("question_count") or 0)
    platform_count = int(sample_scope.get("platform_count") or 0)
    tracking_label = _clean_text(
        tracking_projection.get("status_label")
        or sample_scope.get("tracking_status_label")
    ) or "首期基线"
    platforms = _join_report_terms(
        platform_source_summary.get("platform_names") or [],
        "平台样本待补",
    )
    sample_sentence = _clean_text(verdict.get("sample_sentence")) or (
        f"本轮围绕 {question_count} 个问题，读取 {valid_answers} 条有效回答，"
        f"覆盖 {platform_count} 个有效平台。"
    )
    first_finding = evidence_findings[0] if evidence_findings else {}
    health_refs = _storyline_refs(health, first_finding)
    companionship_refs = _storyline_refs(companionship, first_finding)
    security_refs = _storyline_refs(security, first_finding)
    action_lines = [
        f"{item.get('title')}：{item.get('action')} 验证口径：{item.get('validation')}"
        for item in weekly_actions
        if _clean_text(item.get("title")) and _clean_text(item.get("action"))
    ]
    if not action_lines:
        action_lines = _association_action_lines_for_report(association_actions, limit=3)
    rendered_source_quote_lines: set[str] = set()

    def source_quote_lines(*pillar_items: dict[str, Any], limit: int = 2) -> list[str]:
        lines: list[str] = []
        for line in _combined_pillar_source_quote_lines(*pillar_items, limit=limit):
            if line in rendered_source_quote_lines:
                continue
            rendered_source_quote_lines.add(line)
            lines.append(line)
        return lines

    return [
        {
            "section_id": "brand_verdict",
            "render_strategy_rows": False,
            "role": "executive_summary",
            "title": "品牌联想裁决",
            "reader_question": "四有战略在 AI 回答里被接住了吗？",
            "takeaway": _clean_text(verdict.get("headline"))
            or "四有在 AI 叙事中呈现不均衡：有健康最先被接住，有陪伴已有萌芽，有保障受风险遮蔽，有价值仍缺少稳定入口。",
            "claims": [
                f"样本边界：{sample_sentence}",
                f"有健康：{_clean_text(health.get('status_label')) or '待观察'}。",
                f"有陪伴：{_clean_text(companionship.get('status_label')) or '待观察'}。",
                f"有保障：{_clean_text(security.get('status_label')) or '待观察'}。",
                f"有价值：{_clean_text(value.get('status_label')) or '待观察'}。",
            ],
            "paragraphs": [
                f"{sample_sentence} 报告状态为{tracking_label}，有效平台为{platforms}。",
                (
                    f"按安利四有战略读图，{center_term}本轮最容易被 AI 接住的是有健康。"
                    f"图谱近端资产集中在{_join_report_terms(strong_terms, '待形成稳定资产')}，"
                    f"机会轨出现{_join_report_terms(growth_terms, '待形成机会词')}，"
                    f"观察轨保留{_join_report_terms(far_terms, '待继续观察')}。"
                ),
                (
                    _four_have_companionship_verdict_sentence(
                        companionship=companionship,
                        risk_terms=risk_terms,
                    )
                    + " "
                    "有保障受到信任、合规和销售方式影响；有价值需要先穿过保障问题，再进入人生阶段叙事。"
                ),
                (
                    f"竞品参照集中在{_join_report_terms(competition_terms, '本轮未形成明显竞品参照')}。"
                    "这些参照主要服务有健康升级，帮助判断安利从产品优势走向方案优势还缺哪些证据。"
                ),
            ],
            "so_what": "品牌团队先按四有判断战略承接，再把风险和竞品放回对应战略路径处理。",
            "supporting_facts": [
                f"解析节点 {len(nodes)} 个；风险关系 {risk_summary.get('risk_count', 0)} 个；竞品参照 {risk_summary.get('competition_count', 0)} 个。",
                f"有效回答 {valid_answers} 条；有效平台 {platform_count} 个。",
            ],
            "evidence_refs": first_finding.get("evidence_refs") or [],
            "next_probe": "下一轮固定同一批问题，观察四有的承接顺序和风险遮蔽是否发生变化。",
        },
        {
            "section_id": "have_health",
            "render_strategy_rows": False,
            "role": "asset_finding",
            "title": "有健康｜唯一被接住的有",
            "reader_question": "有健康为什么成立，又卡在哪里？",
            "takeaway": (
                f"有健康已被接住，但当前证据主要停在{_story_terms(health, 'node_terms', '产品和品类')}，"
                "需要升级到科技抗衰和长期健康管理方案。"
            ),
            "claims": [
                f"节点：{_story_terms(health, 'node_terms', '健康相关节点待补')}。",
                f"战略词：{_story_terms(health, 'strategy_terms', '有健康')}。",
                f"竞品参照：{_story_terms(health, 'competition_terms', '本轮不明显')}。",
                f"年度抓手：{_clean_text(health.get('annual_handle')) or '科技抗衰'}。",
            ],
            "paragraphs": [
                (
                    f"有健康是本轮最稳定的入口。回答里反复出现{_story_terms(health, 'node_terms', '健康、营养和产品证据')}，"
                    f"图谱上也更接近{center_term}。"
                ),
                (
                    "当前短板在表达层级。平台容易说产品、成分、营养和管理，却没有稳定复述成一套长期健康管理方案。"
                    f"年度抓手应落到{_clean_text(health.get('annual_handle')) or '科技抗衰'}，把营养、抗衰、体重管理和科学证据连成方案。"
                ),
                (
                    f"竞品参照为{_story_terms(health, 'competition_terms', '本轮不明显')}。"
                    "这组参照先放在健康方案表达里，用来观察哪些证据被别人抢先占位。"
                ),
            ],
            "so_what": "有健康可以先做内容资产沉淀，但必须从单点产品证据升级为方案证据。",
            "supporting_facts": [
                _pillar_fact_line(health),
                f"近端资产：{_join_report_terms(strong_terms, '待形成稳定资产')}。",
                *source_quote_lines(health),
            ],
            "evidence_refs": health_refs,
            "next_probe": "下一轮用科技抗衰、长期健康管理和人群方案题复测，看平台是否主动把方案带回安利。",
        },
        {
            "section_id": "have_companionship",
            "render_strategy_rows": False,
            "role": "opportunity_finding",
            "title": (
                "有陪伴｜萌芽被旧认知牵制"
                if companionship_has_risk
                else "有陪伴｜有萌芽，仍需外显"
            ),
            "reader_question": "社群和陪伴是否已经变成安利资产？",
            "takeaway": _four_have_companionship_takeaway(companionship),
            "claims": [
                f"节点：{_story_terms(companionship, 'node_terms', '陪伴节点待补')}。",
                f"风险牵制：{_story_terms(companionship, 'risk_terms', '本轮不明显')}。",
                f"年度抓手：{_clean_text(companionship.get('annual_handle')) or '安利社群外显'}。",
            ],
            "paragraphs": [
                (
                    f"有陪伴已经有入口。问题里关于退休、朋友、圈子和价值感的场景，会把回答带到"
                    f"{_story_terms(companionship, 'node_terms', '社群陪伴')}。"
                ),
                _four_have_companionship_gap_sentence(companionship),
                (
                    f"年度抓手应落到{_clean_text(companionship.get('annual_handle')) or '安利社群外显'}："
                    "把真实社群场景、参与边界和陪伴故事做成可引用证据。"
                ),
            ],
            "so_what": "有陪伴不能只写成口号，需要用真实社群边界和陪伴证据对冲旧认知。",
            "supporting_facts": [
                _pillar_fact_line(companionship),
                *source_quote_lines(companionship),
            ],
            "evidence_refs": companionship_refs,
            "next_probe": (
                "下一轮补退休、长期陪伴、朋友网络和非销售社群场景题，看风险伴随是否下降。"
                if companionship_has_risk
                else "下一轮补退休、长期陪伴、朋友网络和非销售社群场景题，看这个入口能否跨平台稳定出现。"
            ),
        },
        {
            "section_id": "have_security_value",
            "render_strategy_rows": False,
            "role": "risk_finding",
            "title": "有保障 + 有价值｜先修复信任，再谈人生再出发",
            "reader_question": "保障感和价值感为什么没有自然长出来？",
            "takeaway": (
                f"有保障受到{_story_terms(security, 'risk_terms', '信任和合规风险')}遮蔽；"
                "有价值需要在保障感修复后继续铺证据。"
            ),
            "claims": [
                f"有保障：{_clean_text(security.get('status_label')) or '待观察'}。",
                f"有价值：{_clean_text(value.get('status_label')) or '待观察'}。",
                f"风险入口：{_story_terms(security, 'risk_terms', '本轮不明显')}。",
                f"价值线索：{_story_terms(value, 'node_terms', '尚未稳定出现')}。",
            ],
            "paragraphs": [
                (
                    f"有保障当前先被{_story_terms(security, 'risk_terms', '信任、合规和销售方式问题')}挡住。"
                    "当回答先进入直销、收入、拉人和监管语境，平台很难继续自然展开保障感。"
                ),
                (
                    f"有价值依赖有保障。{_story_terms(value, 'node_terms', '人生再出发和价值感')}如果缺少清晰参与边界，"
                    "就容易停在理想叙事，无法成为稳定品牌联想。"
                ),
                (
                    "修复路径要串行推进：先把事业参与机制、收入边界、合规依据讲清楚，再把价值感、人生成长和被需要写成可验证故事。"
                ),
            ],
            "so_what": "品牌防守先处理保障感，价值感随后才有机会被平台稳定带回安利。",
            "supporting_facts": [
                _pillar_fact_line(security),
                _pillar_fact_line(value),
                *source_quote_lines(security, value),
            ],
            "evidence_refs": security_refs,
            "next_probe": (
                f"下一轮先复测{_story_terms(security, 'risk_terms', '直销、收入边界和合规')}题，"
                "再观察有价值类节点是否获得正向证据。"
            ),
        },
        {
            "section_id": "weekly_three_actions",
            "render_strategy_rows": False,
            "role": "action_finding",
            "title": "本周 3 件事",
            "reader_question": "品牌团队这周先做什么？",
            "takeaway": "行动直接对齐三条年度抓手：科技抗衰、安利社群外显、透明事业边界与人生再出发。",
            "claims": action_lines[:3] or ["本周先补健康方案、社群证据和事业边界三类材料。"],
            "paragraphs": [
                "这周先收拢概念，补可以进入 AI 回答的证据。",
                *action_lines[:3],
                (
                    "下一轮报告只看三件事是否改变图谱：有健康是否从产品层进入方案层；"
                    "有陪伴是否减少销售旧认知伴随；有保障修复后，有价值是否开始出现。"
                ),
            ],
            "so_what": "行动要服务下一轮复测，让图谱位置和报告判断都能被同一组问题检验。",
            "supporting_facts": [
                f"本轮战略词 {len(strategy_validation)} 个。",
                f"有效回答 {valid_answers} 条；有效平台 {platform_count} 个。",
            ],
            "evidence_refs": first_finding.get("evidence_refs") or [],
            "next_probe": "下一轮用同一题库复测四有，并新增三类年度抓手题。",
        },
    ]


def _story_terms(pillar: dict[str, Any], key: str, fallback: str) -> str:
    values = [
        _clean_text(item)
        for item in pillar.get(key, [])
        if _clean_text(item)
    ]
    return _join_report_terms(values[:5], fallback)


def _pillar_source_quote_lines(
    pillar: dict[str, Any],
    *,
    limit: int = 2,
) -> list[str]:
    return _combined_pillar_source_quote_lines(pillar, limit=limit)


def _combined_pillar_source_quote_lines(
    *pillars: dict[str, Any],
    limit: int = 2,
) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for pillar in pillars:
        for sample in pillar.get("source_samples", []):
            if not isinstance(sample, dict):
                continue
            platform = _clean_text(sample.get("platform")) or "未知平台"
            question = _clean_text(sample.get("question"))
            excerpt = _clean_text(
                sample.get("answer_excerpt") or sample.get("center_context_excerpt")
            )
            if not excerpt:
                continue
            signature = f"{platform}:{question}:{excerpt}"
            if signature in seen:
                continue
            seen.add(signature)
            question_part = f"问题：{question}；" if question else ""
            lines.append(f"平台原文样本：{platform}；{question_part}回答摘录：{excerpt}")
            if len(lines) >= limit:
                return lines
    return lines


def _four_have_companionship_verdict_sentence(
    *,
    companionship: dict[str, Any],
    risk_terms: list[str],
) -> str:
    if companionship.get("risk_terms"):
        return (
            "有陪伴已经出现社群和关系线索，"
            f"但{_story_terms(companionship, 'risk_terms', '风险词')}会牵制这条线。"
        )
    if risk_terms:
        return (
            "有陪伴已经出现社群和关系线索，本轮风险主要压在保障感上，"
            "陪伴线仍需单独复测。"
        )
    return "有陪伴已经出现社群和关系线索，本轮还没有抓到稳定的质疑语境。"


def _four_have_companionship_takeaway(companionship: dict[str, Any]) -> str:
    node_terms = _story_terms(companionship, "node_terms", "社群和关系线索")
    if companionship.get("risk_terms"):
        risk_terms = _story_terms(companionship, "risk_terms", "销售方式旧认知")
        return f"有陪伴已有{node_terms}，但{risk_terms}会削弱它。"
    return f"有陪伴已有{node_terms}，但当前证据集中，需要更多平台和真实场景把它托住。"


def _four_have_companionship_gap_sentence(companionship: dict[str, Any]) -> str:
    if companionship.get("risk_terms"):
        return (
            f"牵制来自{_story_terms(companionship, 'risk_terms', '销售方式旧认知')}。"
            "用户想要的是陪伴和关系支持，平台却可能把社群理解成卖货、熟人压力或参与成本。"
        )
    return (
        "本轮还没有抓到稳定的质疑语境。差距在证据厚度：回答能进入社群和陪伴，"
        "但平台覆盖还薄，真实场景和参与边界需要补进下一轮问题。"
    )


def _storyline_refs(
    pillar: dict[str, Any],
    fallback_finding: dict[str, Any],
) -> list[str]:
    refs = [
        _clean_text(item)
        for item in pillar.get("evidence_refs", [])
        if _clean_text(item)
    ]
    if refs:
        return refs[:8]
    return fallback_finding.get("evidence_refs") or []


def _pillar_fact_line(pillar: dict[str, Any]) -> str:
    label = _clean_text(pillar.get("label")) or "四有维度"
    answer_count = int(pillar.get("answer_mention_count") or 0)
    platform_count = int(pillar.get("platform_count") or 0)
    status = _clean_text(pillar.get("status_label")) or "待观察"
    terms = _story_terms(pillar, "node_terms", "暂无稳定节点")
    return (
        f"{label}：{status}；回答提及 {answer_count} 条，"
        f"覆盖 {platform_count} 个平台；代表节点为{terms}。"
    )


def _report_mentions_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    normalized = _clean_text(text)
    if not normalized:
        return False
    return any(_contains_alias(normalized, _clean_text(term)) for term in terms if _clean_text(term))


def _report_center_terms(center_terms: list[str]) -> list[str]:
    values: list[str] = []
    for term in [*center_terms, "安利", "安利中国", "纽崔莱", "Amway", "Nutrilite"]:
        text = _clean_text(term)
        if text and text not in values:
            values.append(text)
    return values


def _report_risk_terms_in(text: str) -> list[str]:
    value = _clean_text(text)
    return [term for term in REPORT_RISK_CONTEXT_TERMS if term in value]


def _clip_report_text(text: Any, limit: int = 160) -> str:
    value = _clean_text(text)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _build_story_answer_records(
    *,
    fetch_results: list[dict[str, Any]],
    center_terms: list[str],
) -> list[dict[str, Any]]:
    center_aliases = _report_center_terms(center_terms)
    records: list[dict[str, Any]] = []
    for observation in _iter_observations(fetch_results):
        risk_terms = _report_risk_terms_in(observation.answer_text)
        records.append(
            {
                "question_id": observation.question_id,
                "question": observation.question,
                "platform": observation.platform,
                "text": observation.answer_text,
                "question_has_center": _report_mentions_any(
                    observation.question,
                    center_aliases,
                ),
                "answer_has_center": _report_mentions_any(
                    observation.answer_text,
                    center_aliases,
                ),
                "risk_terms": risk_terms,
                "has_negative_risk_context": bool(risk_terms),
                "has_transformation_context": _report_mentions_any(
                    observation.answer_text,
                    REPORT_TRANSFORMATION_TERMS,
                ),
            }
        )
    return records


def _build_story_answer_records_from_source_appendix(
    *,
    source_appendix: list[dict[str, Any]],
    center_terms: list[str],
) -> list[dict[str, Any]]:
    center_aliases = _report_center_terms(center_terms)
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in source_appendix:
        if not isinstance(item, dict):
            continue
        platform = _clean_text(item.get("platform"))
        question = _clean_text(item.get("question"))
        text = _clean_text(
            item.get("answer_excerpt")
            or item.get("answer_text")
            or item.get("excerpt")
        )
        if not (platform and question and text):
            continue
        key = (platform, question, text)
        if key in seen:
            continue
        seen.add(key)
        risk_terms = _report_risk_terms_in(text)
        records.append(
            {
                "question_id": _clean_text(item.get("question_id")),
                "question": question,
                "platform": platform,
                "text": text,
                "question_has_center": _report_mentions_any(
                    question,
                    center_aliases,
                ),
                "answer_has_center": _report_mentions_any(
                    text,
                    center_aliases,
                ),
                "risk_terms": risk_terms,
                "has_negative_risk_context": bool(risk_terms),
                "has_transformation_context": _report_mentions_any(
                    text,
                    REPORT_TRANSFORMATION_TERMS,
                ),
            }
        )
    return records


def _build_story_sample_profile(
    *,
    records: list[dict[str, Any]],
    sample_scope: dict[str, Any],
) -> dict[str, Any]:
    answer_count = len(records) or int(sample_scope.get("valid_answer_count") or 0)
    platform_counts = Counter(
        _clean_text(record.get("platform")) for record in records if _clean_text(record.get("platform"))
    )
    question_ids = {
        _clean_text(record.get("question_id") or record.get("question"))
        for record in records
        if _clean_text(record.get("question_id") or record.get("question"))
    }
    brand_named = [record for record in records if record.get("question_has_center")]
    open_records = [record for record in records if not record.get("question_has_center")]
    brand_mentions = [record for record in records if record.get("answer_has_center")]
    open_mentions = [record for record in open_records if record.get("answer_has_center")]
    risk_records = [
        record
        for record in records
        if record.get("answer_has_center") and record.get("has_negative_risk_context")
    ]
    return {
        "answer_count": answer_count,
        "question_count": len(question_ids) or int(sample_scope.get("question_count") or 0),
        "platform_count": len(platform_counts) or int(sample_scope.get("platform_count") or 0),
        "platform_distribution": [
            {"platform": platform, "count": count}
            for platform, count in platform_counts.most_common()
        ],
        "brand_mention_count": len(brand_mentions),
        "brand_mention_rate": round(len(brand_mentions) / len(records), 4) if records else 0.0,
        "brand_named_answer_count": len(brand_named),
        "open_answer_count": len(open_records),
        "open_brand_mention_count": len(open_mentions),
        "active_mention_rate": round(len(open_mentions) / len(open_records), 4) if open_records else 0.0,
        "risk_context_count": len(risk_records),
        "risk_context_rate": round(len(risk_records) / len(brand_mentions), 4) if brand_mentions else 0.0,
    }


def _story_entity_ranking(nodes: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    rows = [
        {
            "term": _clean_text(node.get("term")),
            "business_tag": _clean_text(node.get("business_tag")),
            "orbit_label": _clean_text(node.get("orbit_label")),
            "answer_count": int(node.get("answer_count") or 0),
            "platform_count": int(node.get("platform_count") or 0),
            "gravity_score": int(node.get("gravity_score") or node.get("association_score") or 0),
            "risk_context_count": int(node.get("risk_evidence_count") or 0),
        }
        for node in nodes
        if _clean_text(node.get("term"))
    ]
    rows.sort(
        key=lambda item: (
            -int(item["answer_count"]),
            -int(item["platform_count"]),
            -int(item["gravity_score"]),
            str(item["term"]),
        )
    )
    return rows[:limit]


def _story_platform_profiles(
    *,
    records: list[dict[str, Any]],
    platform_source_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if records:
        for platform, count in Counter(_clean_text(record.get("platform")) for record in records).most_common():
            platform_records = [
                record
                for record in records
                if _clean_text(record.get("platform")) == platform
            ]
            if not platform_records:
                continue
            risk_count = sum(1 for record in platform_records if record.get("has_negative_risk_context"))
            active_mentions = sum(
                1
                for record in platform_records
                if not record.get("question_has_center") and record.get("answer_has_center")
            )
            transformation_count = sum(
                1 for record in platform_records if record.get("has_transformation_context")
            )
            risk_rate = risk_count / len(platform_records)
            if risk_rate >= 0.45:
                profile = "风险提醒密集"
            elif transformation_count >= max(1, len(platform_records) // 3):
                profile = "转型叙事更完整"
            elif active_mentions:
                profile = "开放问题更容易带出品牌"
            else:
                profile = "样本口吻待继续观察"
            centered_records = [record for record in platform_records if record.get("answer_has_center")]
            if centered_records:
                quote_record = max(centered_records, key=lambda r: len(str(r.get("text") or "")))
            else:
                quote_record = max(platform_records, key=lambda r: len(str(r.get("text") or ""))) if platform_records else {}
            rows.append(
                {
                    "platform": platform,
                    "answer_count": len(platform_records),
                    "risk_context_count": risk_count,
                    "active_mentions": active_mentions,
                    "transformation_mentions": transformation_count,
                    "profile": profile,
                    "quote": {
                        "platform": platform,
                        "question": quote_record.get("question"),
                        "excerpt": _preserve_answer_text(quote_record.get("text")) or "",
                    },
                }
            )
        return rows

    for row in platform_source_summary.get("platforms") or []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "platform": _clean_text(row.get("platform")),
                "answer_count": int(row.get("valid_answer_count") or 0),
                "risk_context_count": len(row.get("risk_nodes") or []),
                "active_mentions": 0,
                "transformation_mentions": len(row.get("preferred_nodes") or []),
                "profile": _clean_text(row.get("answer_preference")) or "样本口吻待继续观察",
                "quote": None,
            }
        )
    return rows


def _story_blind_spot(
    *,
    center_term: str,
    records: list[dict[str, Any]],
    sample_profile: dict[str, Any],
) -> dict[str, Any]:
    active_rate = float(sample_profile.get("active_mention_rate") or 0)
    if active_rate < 0.05:
        diagnosis = f"{center_term}尚未进入开放问题的默认推荐列表。"
    elif active_rate < 0.1:
        diagnosis = f"{center_term}只有少量开放场景会被平台主动带出。"
    else:
        diagnosis = f"{center_term}已经在部分开放场景里出现主动提及。"
    missed_examples = [
        {
            "platform": _clean_text(record.get("platform")),
            "question": _clean_text(record.get("question")),
            "excerpt": _preserve_answer_text(record.get("text")) or "",
        }
        for record in records
        if not record.get("question_has_center") and not record.get("answer_has_center")
    ][:3]
    return {
        "diagnosis": diagnosis,
        "active_mention_rate": active_rate,
        "open_answer_count": int(sample_profile.get("open_answer_count") or 0),
        "open_brand_mention_count": int(sample_profile.get("open_brand_mention_count") or 0),
        "brand_named_answer_count": int(sample_profile.get("brand_named_answer_count") or 0),
        "missed_examples": missed_examples,
    }


def _build_storyline_report_analysis(
    *,
    center_terms: list[str],
    sample_scope: dict[str, Any],
    nodes: list[dict[str, Any]],
    platform_source_summary: dict[str, Any],
    fetch_results: list[dict[str, Any]],
    source_appendix: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    center_term = _first_center_term(center_terms)
    records = _build_story_answer_records(
        fetch_results=fetch_results,
        center_terms=center_terms,
    )
    if not records and source_appendix:
        records = _build_story_answer_records_from_source_appendix(
            source_appendix=source_appendix,
            center_terms=center_terms,
        )
    sample_profile = _build_story_sample_profile(
        records=records,
        sample_scope=sample_scope,
    )
    return {
        "records": records,
        "sample_profile": sample_profile,
        "entity_ranking": _story_entity_ranking(nodes),
        "platform_profiles": _story_platform_profiles(
            records=records,
            platform_source_summary=platform_source_summary,
        ),
        "blind_spot": _story_blind_spot(
            center_term=center_term,
            records=records,
            sample_profile=sample_profile,
        ),
    }


def _story_platform_distribution_line(sample_profile: dict[str, Any]) -> str:
    rows = sample_profile.get("platform_distribution") or []
    if not rows:
        return "平台分布待补。"
    return "平台分布：" + "、".join(
        f"{row.get('platform')} {row.get('count')}"
        for row in rows[:4]
        if row.get("platform")
    ) + "。"


def _story_entity_line(rows: list[dict[str, Any]], *, limit: int = 5) -> str:
    values = [
        f"{row.get('term')}（{row.get('answer_count')}条）"
        for row in rows[:limit]
        if row.get("term")
    ]
    return "、".join(values) if values else "本轮尚未形成稳定实体排行"


def _story_quote_lines_from_samples(
    samples: list[dict[str, Any]],
    *,
    limit: int = 3,
    records: list[dict[str, Any]] | None = None,
) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    record_index: dict[str, str] = {}
    if records:
        for record in records:
            q = _clean_text(record.get("question"))[:40]
            plat = _normalize_platform(record.get("platform"))
            if q and plat:
                record_index[f"{q}|{plat}"] = record.get("text") or ""
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        platform = _clean_text(sample.get("platform")) or "未知平台"
        question = _clean_text(sample.get("question"))
        q = question[:40]
        plat = _normalize_platform(sample.get("platform"))
        full_text = record_index.get(f"{q}|{plat}") if q and plat else ""
        excerpt = _preserve_answer_text(full_text) if full_text else _preserve_answer_text(sample.get("answer_excerpt") or sample.get("excerpt"))
        if not excerpt:
            continue
        key = f"{platform}:{question}:{excerpt[:80]}"
        if key in seen:
            continue
        seen.add(key)
        question_part = f"｜{question}" if question else ""
        lines.append(f"平台原文：{platform}{question_part}｜{excerpt}")
        if len(lines) >= limit:
            break
    return lines


def _story_quote_lines_from_profiles(
    platform_profiles: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[str]:
    lines: list[str] = []
    for profile in platform_profiles:
        quote = profile.get("quote")
        if not isinstance(quote, dict):
            continue
        platform = _clean_text(quote.get("platform") or profile.get("platform"))
        question = _clean_text(quote.get("question"))
        excerpt = _preserve_answer_text(quote.get("excerpt"))
        if not excerpt:
            continue
        question_part = f"｜{question}" if question else ""
        lines.append(f"平台原文：{platform}{question_part}｜{excerpt}")
        if len(lines) >= limit:
            break
    return lines


def _story_gap_label(pillar_key: str, pillar: dict[str, Any]) -> str:
    status = _clean_text(pillar.get("status"))
    if pillar_key == "have_health":
        return "叙事层级差距"
    if pillar_key == "have_companionship":
        return "叙事被劫持" if pillar.get("risk_terms") or "hijacked" in status else "弱信号待确认"
    if pillar_key == "have_security":
        return "叙事被反转"
    if pillar_key == "have_value":
        return "叙事缺位" if int(pillar.get("answer_mention_count") or 0) <= 1 else "弱信号待确认"
    return "待判断"


def _story_pillar_line(pillar: dict[str, Any], key: str) -> str:
    label = _clean_text(pillar.get("label")) or "四有维度"
    status = _clean_text(pillar.get("status_label")) or "待观察"
    gap = _story_gap_label(key, pillar)
    terms = _story_terms(pillar, "node_terms", "代表节点待补")
    answer_count = int(pillar.get("answer_mention_count") or 0)
    platform_count = int(pillar.get("platform_count") or 0)
    return (
        f"{label}：{status}；差距类型为{gap}；"
        f"相关回答 {answer_count} 条，覆盖 {platform_count} 个平台；代表节点为{terms}。"
    )


def _story_metric_phrase(value: int, total: int) -> str:
    if total <= 0:
        return f"{value} 条"
    if value > total:
        return f"累计命中 {value} 次，样本回答 {total} 条"
    return f"{value} 条，占 {round(value / total * 100, 1)}%"


def _strip_report_sentence_end(text: str) -> str:
    return re.sub(r"[。；;.\s]+$", "", _clean_text(text))


def _dedupe_report_lines(lines: list[str], *, limit: int = 5) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = _clean_text(line)
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
        if len(values) >= limit:
            break
    return values


def _story_entities_by_tag(
    rows: list[dict[str, Any]],
    *,
    include_tags: tuple[str, ...] = (),
    exclude_tags: tuple[str, ...] = (),
    limit: int = 5,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in rows:
        tag = _clean_text(row.get("business_tag"))
        if include_tags and tag not in include_tags:
            continue
        if exclude_tags and tag in exclude_tags:
            continue
        if not _clean_text(row.get("term")):
            continue
        values.append(row)
        if len(values) >= limit:
            break
    return values


def _story_platform_persona(profile: dict[str, Any]) -> str:
    answer_count = int(profile.get("answer_count") or 0)
    risk_count = int(profile.get("risk_context_count") or 0)
    active_mentions = int(profile.get("active_mentions") or 0)
    transformation_mentions = int(profile.get("transformation_mentions") or 0)
    risk_rate = risk_count / answer_count if answer_count else 0
    if risk_rate >= 0.45:
        return "风险提示派"
    if active_mentions:
        return "主动推荐派"
    if transformation_mentions >= max(1, answer_count // 3):
        return "转型叙事派"
    if answer_count:
        return "中性档案派"
    return "样本待补"


def _story_platform_persona_description(profile: dict[str, Any]) -> str:
    answer_count = int(profile.get("answer_count") or 0)
    risk_count = int(profile.get("risk_context_count") or 0)
    active_mentions = int(profile.get("active_mentions") or 0)
    transformation_mentions = int(profile.get("transformation_mentions") or 0)
    risk_rate = risk_count / answer_count if answer_count else 0
    if risk_rate >= 0.45:
        return "几乎每条回答都带风险提醒，先讲品牌再讲争议。"
    if active_mentions:
        return "唯一在开放问题里主动带出品牌的平台。"
    if transformation_mentions >= max(1, answer_count // 3):
        return "最爱铺开品牌转型故事，提到投资、农场、系统等细节。"
    if answer_count:
        return "中立档案，正反数据都摆出来，不太做判断。"
    return "样本待补。"


def _story_platform_sentence(profile: dict[str, Any]) -> str:
    platform = _clean_text(profile.get("platform")) or "未知平台"
    persona = _story_platform_persona(profile)
    desc = _story_platform_persona_description(profile)
    answer_count = int(profile.get("answer_count") or 0)
    risk_count = int(profile.get("risk_context_count") or 0)
    active_mentions = int(profile.get("active_mentions") or 0)
    transformation_mentions = int(profile.get("transformation_mentions") or 0)
    return (
        f"{platform}｜{persona}。{desc}"
        f"（回答 {answer_count} 条，风险语境 {risk_count} 条，"
        f"转型叙事 {transformation_mentions} 条，主动带出品牌 {active_mentions} 条）"
    )


def _story_clean_action_lines(
    weekly_actions: list[dict[str, Any]],
    association_actions: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    titles: list[str] = []
    paragraphs: list[str] = []
    seen_titles: set[str] = set()
    for item in weekly_actions:
        title = _clean_text(item.get("title"))
        action = _clean_text(item.get("action"))
        validation = _clean_text(item.get("validation"))
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        titles.append(title)
        text_parts = [_strip_report_sentence_end(title)]
        if action:
            text_parts.append(_strip_report_sentence_end(action))
        paragraphs.append("；".join(text_parts) + "。")
    if titles:
        return titles[:3], paragraphs[:3]
    fallback_lines = _association_action_lines_for_report(association_actions, limit=3)
    return fallback_lines[:3], fallback_lines[:3]


def _build_storyline_report_sections(
    *,
    center_term: str,
    sample_scope: dict[str, Any],
    nodes: list[dict[str, Any]],
    risk_summary: dict[str, Any],
    platform_source_summary: dict[str, Any],
    association_actions: list[dict[str, Any]],
    strategy_storyline: dict[str, Any],
    storyline_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    sample_profile = storyline_analysis.get("sample_profile") or {}
    entity_ranking = storyline_analysis.get("entity_ranking") or []
    platform_profiles = storyline_analysis.get("platform_profiles") or []
    blind_spot = storyline_analysis.get("blind_spot") or {}
    pillars = {
        _clean_text(item.get("key")): item
        for item in strategy_storyline.get("pillars", [])
        if isinstance(item, dict) and _clean_text(item.get("key"))
    }
    health = pillars.get("have_health", {})
    companionship = pillars.get("have_companionship", {})
    security = pillars.get("have_security", {})
    value = pillars.get("have_value", {})
    weekly_actions = [
        item for item in strategy_storyline.get("weekly_actions", []) if isinstance(item, dict)
    ]
    valid_answers = int(sample_profile.get("answer_count") or sample_scope.get("valid_answer_count") or 0)
    question_count = int(sample_profile.get("question_count") or sample_scope.get("question_count") or 0)
    platform_count = int(sample_profile.get("platform_count") or sample_scope.get("platform_count") or 0)
    active_rate = float(blind_spot.get("active_mention_rate") or 0)
    risk_rate = float(sample_profile.get("risk_context_rate") or 0)
    asset_rows = _story_entities_by_tag(
        entity_ranking,
        exclude_tags=("风险认知", "竞争关系"),
        limit=8,
    )
    risk_rows = _story_entities_by_tag(
        entity_ranking,
        include_tags=("风险认知", "竞争关系"),
        limit=8,
    )
    top_entities = _story_entity_line(asset_rows or entity_ranking, limit=4)
    risk_terms = [
        _clean_text(node.get("term"))
        for node in risk_summary.get("risk_nodes", [])
        if isinstance(node, dict) and _clean_text(node.get("term"))
    ][:4] or [
        _clean_text(row.get("term")) for row in risk_rows[:4] if row.get("term")
    ]
    competition_terms = [
        _clean_text(node.get("term"))
        for node in risk_summary.get("competition_nodes", [])
        if isinstance(node, dict) and _clean_text(node.get("term"))
    ][:4]
    story_records = storyline_analysis.get("records") or []
    health_quotes = _story_quote_lines_from_samples(health.get("source_samples") or [], limit=3, records=story_records)
    companionship_quotes = _story_quote_lines_from_samples(
        companionship.get("source_samples") or [],
        limit=2,
        records=story_records,
    )
    security_quotes = _story_quote_lines_from_samples(
        security.get("source_samples") or [],
        limit=2,
        records=story_records,
    )
    platform_quotes = _story_quote_lines_from_profiles(platform_profiles, limit=3)
    action_titles, action_paragraphs = _story_clean_action_lines(
        weekly_actions,
        association_actions,
    )
    platform_claims = [
        _story_platform_sentence(profile)
        for profile in platform_profiles[:4]
        if profile.get("platform")
    ]
    entity_fact_lines = [
        f"{row.get('term')}：提及 {row.get('answer_count')} 条，覆盖 {row.get('platform_count')} 个平台，图谱位置为{row.get('orbit_label') or row.get('business_tag')}。"
        for row in (asset_rows or entity_ranking)[:5]
        if row.get("term")
    ]
    blind_examples = [
        f"{item.get('platform')}｜{item.get('question')}｜回答未主动提及{center_term}"
        for item in blind_spot.get("missed_examples") or []
        if item.get("question")
    ]
    health_count = int(health.get("answer_mention_count") or 0)
    companionship_count = int(companionship.get("answer_mention_count") or 0)
    security_count = int(security.get("answer_mention_count") or 0)
    value_count = int(value.get("answer_mention_count") or 0)
    health_gap = _story_gap_label("have_health", health)
    companionship_gap = _story_gap_label("have_companionship", companionship)
    security_gap = _story_gap_label("have_security", security)
    value_gap = _story_gap_label("have_value", value)
    companionship_summary = (
        "高可见低可信" if companionship_gap == "叙事被劫持" else "仍需外显证据"
    )
    value_summary = "叙事缺位" if value_gap == "叙事缺位" else "仍缺少稳定入口"
    platform_focus = _join_report_terms(
        [profile.get("platform") for profile in platform_profiles[:4] if profile.get("platform")],
        "平台样本待补",
    )
    risk_terms_text = _join_report_terms(risk_terms, "风险语境待继续确认")
    competition_terms_text = _join_report_terms(competition_terms, "竞品参照待继续确认")
    return [
        {
            "section_id": "core_verdict",
            "render_strategy_rows": False,
            "role": "executive_summary",
            "title": "核心判断",
            "reader_question": "这一轮 AI 到底怎样理解安利？",
            "takeaway": (
                f"最致命发现：开放问题主动提及率只有 {round(active_rate * 100, 1)}%。"
                f"{center_term}不会在健康、社群、退休这些话题里被自然联想到。"
                f"{center_term}是一个被问才答的品牌，不是一个被主动推荐的品牌。"
            ),
            "claims": [
                f"样本：{question_count} 个问题，{valid_answers} 条有效回答，覆盖 {platform_count} 个平台。",
                f"开放问题主动提及：{blind_spot.get('open_brand_mention_count', 0)} / {blind_spot.get('open_answer_count', 0)}。",
                f"品牌相关回答中的风险语境占比约 {round(risk_rate * 100, 1)}%。",
                "四种差距：有健康停在产品层；有陪伴高可见低可信；有保障被风险牵制；有价值仍在场外。",
            ],
            "paragraphs": [
                (
                    f"AI 对{center_term}的认知集中在三个层级。"
                    f"这一判断来自 {question_count} 个问题、{valid_answers} 条有效回答、{platform_count} 个平台的抓取。"
                ),
                (
                    f"第一层，{center_term}＝{top_entities}。"
                    "AI 记住了安利的产品和品类，但还没进到长期健康管理方案和生活方式。"
                ),
                (
                    f"第二层，{center_term}＝直销＋社群。"
                    f"AI 知道安利有社群和事业机会，但紧跟的不是陪伴和保障，而是{risk_terms_text}。"
                ),
                (
                    f"第三层，{center_term}＝争议品牌。"
                    f"品牌相关回答里，风险语境占比约 {round(risk_rate * 100, 1)}%，正向信息和风险提醒同时出现。"
                ),
            ],
            "so_what": "品牌团队先修正 AI 档案的第一层标签，再处理开放问题缺席和风险语境牵制。",
            "supporting_facts": [
                _story_platform_distribution_line(sample_profile),
                *entity_fact_lines[:2],
                *platform_quotes[:1],
            ],
            "evidence_refs": [],
            "next_probe": "下一轮沿用同一题库，看开放问题主动提及率、风险语境占比和核心实体排行是否变化。",
        },
        {
            "section_id": "ai_archive",
            "render_strategy_rows": False,
            "role": "asset_finding",
            "title": f"{center_term}的 AI 档案里写了什么",
            "reader_question": "平台给安利贴上的默认标签是什么？",
            "takeaway": (
                f"AI 记住了{center_term}卖什么，没记住{center_term}想成为什么。"
                f"档案里是{top_entities}，不是健康方案和美好生活。"
            ),
            "claims": platform_claims[:4] or [f"解析节点 {len(nodes)} 个。"],
            "paragraphs": [
                (
                    f"AI 档案里最前排的正向词是{top_entities}。"
                    f"这些词决定 AI 解释{center_term}时的第一反应。"
                ),
                (
                    "健康资产已经有基础，但社群和事业机会经常跟模式、收入、风险一起出现。"
                    "四有战略要先处理这张既有档案。"
                ),
                (
                    f"{platform_focus}给出的口吻不同。"
                    f"谁在帮{center_term}讲转型，谁在持续附带风险提醒，"
                    "要看平台画像。"
                ),
            ],
            "so_what": "AI 档案决定品牌进入回答后的第一解释路径，后续内容要先修正这张档案。",
            "supporting_facts": [
                *entity_fact_lines[:3],
                *platform_quotes[:2],
            ],
            "evidence_refs": [],
            "next_probe": "下一轮看高频实体是否从产品和模式标签，转向方案、社群边界和认证证据。",
        },
        {
            "section_id": "value_pillars",
            "render_strategy_rows": False,
            "role": "opportunity_finding",
            "title": "四个价值支柱，在 AI 叙事里是什么状态",
            "reader_question": "四有分别被接住、牵制、反转还是缺席？",
            "takeaway": (
                f"四有里只有有健康进了 AI 档案，"
                f"有陪伴、有保障、有价值都还卡在档案外面。"
            ),
            "claims": [
                f"有健康：差距类型为{health_gap}；{_story_metric_phrase(health_count, valid_answers)}；代表节点为{_story_terms(health, 'node_terms', '健康相关节点')}。",
                f"有陪伴：差距类型为{companionship_gap}；{_story_metric_phrase(companionship_count, valid_answers)}；代表节点为{_story_terms(companionship, 'node_terms', '社群和关系线索')}。",
                f"有保障：差距类型为{security_gap}；{_story_metric_phrase(security_count, valid_answers)}；风险入口为{_story_terms(security, 'risk_terms', risk_terms_text)}。",
                f"有价值：差距类型为{value_gap}；{_story_metric_phrase(value_count, valid_answers)}；线索为{_story_terms(value, 'node_terms', '价值感线索')}。",
            ],
            "paragraphs": [
                (
                    f"**有健康 — 站稳了，但停在产品层**。"
                    f"代表节点是{_story_terms(health, 'node_terms', '健康相关节点')}。"
                    "平台说产品、成分、营养组合，没说长期健康管理方案、生活方式、持续服务。"
                ),
                (
                    f"**有陪伴 — 高可见，低可信**。"
                    f"出现了{_story_terms(companionship, 'node_terms', '社群和关系线索')}。"
                    "平台认得出社群，看不到真实陪伴场景、参与边界、非销售案例。"
                ),
                (
                    f"**有保障 — 被风险语境笼罩**。"
                    f"被{_story_terms(security, 'risk_terms', '信任、合规和销售方式问题')}牵制。"
                    "回答一进入销售方式、收入边界、合规提醒，保障感就展不开。"
                ),
                (
                    f"**有价值 — 叙事缺位**。"
                    f"目前依赖{_story_terms(value, 'node_terms', '人生再出发和价值感线索')}。"
                    "要等保障感松动，再用真实人物故事和社会价值逐步建立。"
                ),
            ],
            "so_what": "四有要按差距类型处理：升级健康叙事，外显陪伴场景，先修复保障，再铺价值。",
            "supporting_facts": [
                *_dedupe_report_lines(
                    [
                        *health_quotes,
                        *companionship_quotes,
                        *security_quotes,
                    ],
                    limit=5,
                ),
            ],
            "evidence_refs": [
                *_storyline_refs(health, {}),
                *_storyline_refs(companionship, {}),
                *_storyline_refs(security, {}),
                *_storyline_refs(value, {}),
            ][:10],
            "next_probe": "下一轮看有健康是否进入方案层，有陪伴是否减少销售旧认知伴随，有保障风险语境是否下降。",
        },
        {
            "section_id": "ai_blind_spot",
            "render_strategy_rows": False,
            "role": "risk_finding",
            "title": f"{center_term}的 AI 盲区：不问就不说",
            "reader_question": "不点名安利时，平台会主动想到它吗？",
            "takeaway": (
                f"{center_term}在 AI 的默认推荐列表里不存在。"
                f"用户不问{center_term}时，平台不会主动推荐。"
                f"开放问题主动提及率只有 {round(active_rate * 100, 1)}%。"
            ),
            "claims": [
                f"含品牌名问题回答：{blind_spot.get('brand_named_answer_count', 0)} 条。",
                f"开放问题回答：{blind_spot.get('open_answer_count', 0)} 条。",
                f"开放问题主动提及：{blind_spot.get('open_brand_mention_count', 0)} 条。",
                f"主动提及率：{round(active_rate * 100, 1)}%。",
            ],
            "paragraphs": [
                (
                    f"用户直接问{center_term}时平台会答。"
                    f"用户只问健康、社群、退休、长期管理时，平台会不会主动带出{center_term}，"
                    "才是更关键的可见度。"
                ),
                (
                    f"本轮开放问题主动提及率 {round(active_rate * 100, 1)}%。"
                    "这个数字长期偏低，品牌就会停在被点名才出现的状态。"
                ),
                (
                    f"能带出{center_term}的入口通常来自已站稳的相关话题。"
                    f"健康生活社群、长期健康管理、抗衰方案这类题，"
                    f"是最值得观察的入口。"
                ),
            ],
            "so_what": "盲区需要靠开放场景内容解决，把安利嵌进用户原本会问的健康、社群和人生阶段问题。",
            "supporting_facts": blind_examples[:3] or [
                f"开放问题主动提及 {blind_spot.get('open_brand_mention_count', 0)} 条。"
            ],
            "evidence_refs": [],
            "next_probe": "下一轮保留开放问题组，目标是主动提及率超过 10%，并记录触发提及的具体场景。",
        },
        {
            "section_id": "platform_difference",
            "render_strategy_rows": False,
            "role": "asset_finding",
            "title": "平台差异",
            "reader_question": "哪个平台更容易给安利完整叙事，哪个平台风险更重？",
            "takeaway": f"同一个{center_term}，三个平台讲三个版本的故事——谁讲转型，谁讲风险，谁讲数据。",
            "claims": platform_claims[:4] or ["平台样本待补。"],
            "paragraphs": [
                (
                    "平台差异决定内容往哪投。"
                    "风险提醒密的平台，先补澄清材料；"
                    "转型叙事完整的平台，先验证方案级表达。"
                ),
                (
                    "同一个问题跨平台口吻不同时，要留原文对照。"
                    f"品牌团队得看清平台是在替{center_term}辩护、保持中立，"
                    "还是把话题带回旧认知。"
                ),
                (
                    f"本轮有效平台是{_join_report_terms(platform_source_summary.get('platform_names') or [], '平台样本待补')}。"
                    "平台组合固定后，平台缺口才不会被读成品牌变化。"
                ),
            ],
            "so_what": "平台画像帮助品牌把内容任务拆开：哪些平台先修风险，哪些平台先推方案，哪些平台继续观察。",
            "supporting_facts": [
                *platform_claims[:2],
                *platform_quotes[:2],
            ],
            "evidence_refs": [],
            "next_probe": "下一轮按平台比较风险语境、转型叙事和主动提及，判断哪类内容真正改变回答口吻。",
        },
        {
            "section_id": "data_to_action",
            "render_strategy_rows": False,
            "role": "action_finding",
            "title": "从数据到行动",
            "reader_question": "品牌团队这周先做哪三件事？",
            "takeaway": "先修档案，再开盲区，最后解死结——本周只做这三件事。",
            "claims": [
                "问题一：高可见度 ≠ 高认可度。健康、社群、抗衰被提及很多，但 AI 提到时总带\"但是\"。",
                f"问题二：{center_term}不在 AI 的默认推荐列表里。开放问题主动提及率只有 {round(active_rate * 100, 1)}%。",
                f"问题三：品牌故事被拆成碎片。三个平台讲三个版本的{center_term}。",
            ],
            "paragraphs": [
                "行动不按词逐项补材料。这周只按三个问题排优先级。",
                *action_paragraphs[:3],
                (
                    "做完这三件事后，只看图谱有没有变：方案词有没有向内移，"
                    "开放问题主动提及有没有上升，风险语境有没有下降。"
                ),
            ],
            "so_what": "报告行动要压缩成少数可复测动作，并在图谱和原文里验证。",
            "supporting_facts": [
                f"主动提及率 {round(active_rate * 100, 1)}%。",
                f"风险语境占比 {round(risk_rate * 100, 1)}%。",
                f"优先行动：{_join_report_terms(action_titles, '本周行动待补')}。",
                f"风险节点 {risk_summary.get('risk_count', 0)} 个，竞品参照 {risk_summary.get('competition_count', 0)} 个。",
            ],
            "evidence_refs": [],
            "next_probe": "下一轮固定同一题库，新增三类年度抓手题，并比较图谱位置、主动提及率和风险语境。",
        },
    ]


def _strategy_rows_for_story_section(
    strategy_validation: list[dict[str, Any]],
    section_id: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    cues = FOUR_HAVE_SECTION_STRATEGY_CUES.get(section_id, ())
    if not cues:
        return []
    rows = [
        row
        for row in strategy_validation
        if any(
            cue
            and (
                cue in _clean_text(row.get("strategy_term"))
                or _clean_text(row.get("strategy_term")) in cue
            )
            for cue in cues
        )
    ]
    rows.sort(
        key=lambda row: (
            {"validated": 0, "risk": 1, "partial": 2, "missing": 3}.get(
                str(row.get("status")),
                9,
            ),
            -int(row.get("answer_mention_count") or 0),
            _clean_text(row.get("strategy_term")),
        )
    )
    return rows[:limit]


def _build_calibrated_report_narrative_sections(
    *,
    center_terms: list[str],
    sample_scope: dict[str, Any],
    executive_summary: dict[str, Any],
    nodes: list[dict[str, Any]],
    strategy_validation: list[dict[str, Any]],
    risk_summary: dict[str, Any],
    platform_source_summary: dict[str, Any],
    evidence_findings: list[dict[str, Any]],
    association_actions: list[dict[str, Any]],
    tracking_projection: dict[str, Any] | None = None,
    strategy_storyline: dict[str, Any] | None = None,
    storyline_analysis: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(strategy_storyline, dict) and strategy_storyline.get("pillars"):
        if isinstance(storyline_analysis, dict) and storyline_analysis:
            return _build_storyline_report_sections(
                center_term=_first_center_term(center_terms),
                sample_scope=sample_scope,
                nodes=nodes,
                risk_summary=risk_summary,
                platform_source_summary=platform_source_summary,
                association_actions=association_actions,
                strategy_storyline=strategy_storyline,
                storyline_analysis=storyline_analysis,
            )
        return _build_four_have_report_narrative_sections(
            center_terms=center_terms,
            sample_scope=sample_scope,
            executive_summary=executive_summary,
            nodes=nodes,
            strategy_validation=strategy_validation,
            risk_summary=risk_summary,
            platform_source_summary=platform_source_summary,
            evidence_findings=evidence_findings,
            association_actions=association_actions,
            tracking_projection=tracking_projection,
            strategy_storyline=strategy_storyline,
        )
    center_term = _first_center_term(center_terms)
    tracking_projection = tracking_projection or {}
    tracking_label = _clean_text(
        tracking_projection.get("status_label")
        or sample_scope.get("tracking_status_label")
    ) or "首期基线"
    strong_terms = _top_terms_for_report(nodes, _is_strong_report_node, 4)
    growth_terms = _top_terms_for_report(nodes, _is_growth_report_node, 4)
    far_terms = _top_far_terms_for_report(nodes, limit=4)
    competition_terms = _top_competition_terms_for_report(nodes, limit=4)
    competition_count = int(risk_summary.get("competition_count") or 0)
    risk_terms = [
        _clean_text(node.get("term"))
        for node in risk_summary.get("nodes", [])
        if _clean_text(node.get("term"))
    ][:4]
    platforms = _join_report_terms(
        platform_source_summary.get("platform_names") or [],
        "平台样本待补",
    )
    requested_platforms = _join_report_terms(
        platform_source_summary.get("requested_platform_names")
        or platform_source_summary.get("platform_names")
        or [],
        "平台样本待补",
    )
    failed_platforms = _join_report_terms(
        [
            _clean_text(row.get("platform"))
            for row in platform_source_summary.get("platforms", [])
            if row.get("status") == "failed" and _clean_text(row.get("platform"))
        ],
        "",
    )
    platform_scope_sentence = (
        f"有效回答来自{platforms}。"
        if platforms != "平台样本待补"
        else "有效平台样本待补。"
    )
    if failed_platforms:
        platform_scope_sentence += (
            f"{failed_platforms}本轮抓取失败，已进入平台状态记录，"
            "不计入有效平台。"
        )
    platform_next_probe = (
        "下一轮先恢复失败平台的抓取，再按战略词比较各平台的提及方式、原文摘录和图谱位置。"
        if failed_platforms
        else "下一轮沿用同一批题库，按战略词比较各平台的提及方式、原文摘录和图谱位置。"
    )
    strategy_rows = _strategy_section_rows(strategy_validation)
    strategy_lines = [
        (
            f"{row.get('strategy_term')}：{row.get('interpretation')} "
            f"{_platform_strategy_sentence(row)}"
        )
        for row in strategy_rows[:5]
    ]
    strategy_platform_lines = _strategy_platform_comparison_lines(
        strategy_validation,
        limit=6,
    )
    risk_scene_lines = _risk_scene_lines_for_report(
        risk_summary,
        "risk_nodes",
        limit=4,
    )
    competition_scene_lines = _risk_scene_lines_for_report(
        risk_summary,
        "competition_nodes",
        limit=4,
    )
    first_finding = evidence_findings[0] if evidence_findings else {}
    valid_answers = int(sample_scope.get("valid_answer_count") or 0)
    question_count = int(sample_scope.get("question_count") or 0)
    platform_count = int(sample_scope.get("platform_count") or 0)
    market_context_count = int(sample_scope.get("market_context_signal_count") or 0)
    center_linked_count = int(sample_scope.get("center_linked_signal_count") or 0)
    validated_terms = [
        _clean_text(row.get("strategy_term"))
        for row in strategy_validation
        if row.get("status") == "validated" and _clean_text(row.get("strategy_term"))
    ][:5]
    partial_terms = [
        _clean_text(row.get("strategy_term"))
        for row in strategy_validation
        if row.get("status") == "partial" and _clean_text(row.get("strategy_term"))
    ][:5]
    missing_terms = [
        _clean_text(row.get("strategy_term"))
        for row in strategy_validation
        if row.get("status") == "missing" and _clean_text(row.get("strategy_term"))
    ][:5]
    overall_status = _clean_text(
        executive_summary.get("overall_strategy_status")
    ) or "部分验证"
    action_lines = _association_action_lines_for_report(association_actions, limit=4)
    return [
        {
            "section_id": "executive_summary",
            "role": "executive_summary",
            "title": "核心判断",
            "reader_question": "这一轮 AI 到底怎样理解安利？",
            "takeaway": executive_summary.get("one_line_judgment"),
            "claims": [
                f"本轮状态：{tracking_label}。",
                f"本轮 {question_count} 个问题获得 {valid_answers} 条有效回答，有效平台 {platform_count} 个。",
                f"回答最容易带回品牌的联想：{_join_report_terms(strong_terms, '待形成稳定第一反应')}。",
                f"需要拉近：{_join_report_terms(growth_terms + far_terms, '外圈机会还需要继续采样')}。",
                f"需要防守：{_join_report_terms(risk_terms, '本轮风险认知未明显放大')}。",
                f"总体判断：{overall_status}。",
            ],
            "paragraphs": [
                (
                    f"本轮报告是{tracking_label}，以 {question_count} 个问题和 {valid_answers} 条有效回答为边界。{platform_scope_sentence}"
                    f"中心相关信号 {center_linked_count} 条，市场背景信号 {market_context_count} 条。"
                    f"{center_term}本轮最容易被回答带回的联想集中在{_join_report_terms(strong_terms, '待形成稳定资产')}，这些词已经具备被平台反复提及的基础。"
                ),
                (
                    f"主要优势来自{_join_report_terms(validated_terms or strong_terms, '已被回答接住的资产')}。"
                    "这些联想已经具备多平台主动带回的基础，适合沉淀成可复述的问题回答素材。"
                ),
                (
                    f"短板集中在{_join_report_terms(missing_terms or partial_terms, '战略词稳定证据不足')}。"
                    f"它们已经进入题目或外圈语境，但还需要产品证据、生活场景和平台可引用材料继续拉近。"
                ),
                (
                    f"最大风险来自{_join_report_terms(risk_terms, '本轮未明显放大')}。"
                    f"竞品参照包括{_join_report_terms(competition_terms, '本轮未形成明显竞品参照')}。"
                    "这类关系要回到具体问题场景，单独处理信任、合规、销售方式和替代选择。"
                ),
            ],
            "so_what": "品牌团队可以先放大已站稳资产，再把外圈机会补成回答可引用证据，同时按场景处理风险和竞品。",
            "supporting_facts": [
                executive_summary.get("sample_sentence"),
                f"解析节点 {len(nodes)} 个；风险关系 {risk_summary.get('risk_count', 0)} 个；竞品参照 {competition_count} 个。",
                f"中心相关信号 {center_linked_count} 条；市场背景信号 {market_context_count} 条。",
            ],
            "evidence_refs": first_finding.get("evidence_refs") or [],
            "next_probe": "保留本轮核心问题，继续追踪正向资产、部分验证战略词和风险词的位置变化。",
        },
        {
            "section_id": "map_reading",
            "role": "asset_finding",
            "title": "安利的 AI 档案里写了什么",
            "reader_question": "平台给安利贴上的默认标签是什么？",
            "takeaway": f"近端看{_join_report_terms(strong_terms, '稳定资产')}，外侧看{_join_report_terms(growth_terms + far_terms, '待验证机会')}。",
            "claims": [
                "内圈读稳定资产。",
                "中圈读近端机会。",
                "外圈读远端机会和待观察。",
                "风险采用独立关系层，不进入远近轨道。",
            ],
            "paragraphs": [
                (
                    f"内圈代表 AI 回答已经稳定把相关词和{center_term}放在一起。"
                    f"本轮内圈主要看{_join_report_terms(strong_terms, '待形成稳定资产')}。"
                ),
                (
                    f"中圈代表关系已经出现，但还需要通过产品、健康、社群、事业等路径连接。"
                    f"本轮中圈主要看{_join_report_terms(growth_terms, '可拉近机会')}。"
                ),
                (
                    f"外圈代表战略机会已经被触达，但图谱距离和证据仍弱。"
                    f"本轮外圈主要看{_join_report_terms(far_terms, '远端观察词')}。"
                ),
                (
                    f"越靠近中心，代表 AI 回答越容易自然地把该词带回{center_term}。"
                    "风险采用独立关系层，处理的是信任、合规、销售方式和竞品替代问题。"
                ),
            ],
            "so_what": "图谱用于判断品牌联想的成熟度：近端词先放大，中圈词补证据，外圈词进入复测题库，风险词单独治理。",
            "supporting_facts": [
                f"解析节点 {len(nodes)} 个。",
                f"近端资产 {len(strong_terms)} 个，可拉近机会 {len(growth_terms)} 个，远端观察 {len(far_terms)} 个。",
            ],
            "evidence_refs": first_finding.get("evidence_refs") or [],
            "next_probe": "下一轮按近端、机会、远端三组词分别复测，观察位置变化。",
        },
        {
            "section_id": "strategy_validation",
            "role": "asset_finding",
            "title": "四个价值支柱，在 AI 叙事里是什么状态",
            "reader_question": "四有分别被接住、牵制、反转还是缺席？",
            "takeaway": "这一章按价值支柱写，节点只是证据；每个判断都要回到题目、平台、原文摘录和图谱位置。",
            "claims": strategy_lines[:4] or ["本轮战略词还缺少可读证据。"],
            "paragraphs": [
                (
                    "这一章按价值支柱展开。先看本轮哪些题在验证，再看各个平台如何提及，随后回到图谱位置和证据摘录。"
                ),
                *strategy_lines[:5],
            ],
            "so_what": "战略词进入品牌传播前，需要先通过题目和回答证据检验成熟度。",
            "supporting_facts": [
                f"纳入验证的战略词 {len(strategy_validation)} 个。",
                f"回答接住 {sum(1 for row in strategy_validation if row.get('status') == 'validated')} 个；部分接住 {sum(1 for row in strategy_validation if row.get('status') == 'partial')} 个。",
            ],
            "evidence_refs": [
                ref
                for row in strategy_rows
                for ref in row.get("evidence_refs", [])[:2]
            ][:8],
            "next_probe": "对部分验证和缺少证据的战略词，补充人群、场景、产品证据和品牌锚定问题。",
        },
        {
            "section_id": "platform_difference",
            "role": "source_scope",
            "title": "平台差异",
            "reader_question": "不同平台怎样验证同一个战略词？",
            "takeaway": f"平台差异必须绑定战略词来看。{platform_scope_sentence}",
            "claims": strategy_platform_lines[:4]
            or [
                _clean_text(row.get("answer_preference"))
                for row in platform_source_summary.get("platforms", [])[:4]
                if _clean_text(row.get("answer_preference"))
            ]
            or ["平台偏好还需要继续观察。"],
            "paragraphs": [
                (
                    f"本轮尝试平台包括{requested_platforms}。{platform_scope_sentence}"
                    "平台差异先绑定战略词，再看回答数量、代表节点、竞品参照、风险暴露，以及它们连接产品、健康、社群和事业机会的方式。"
                ),
                *strategy_platform_lines[:6],
                *[
                    (
                        f"{row.get('platform')}：{row.get('answer_preference')} "
                        f"代表节点：{_join_report_terms(row.get('preferred_nodes') or [], '待观察')}；"
                        f"竞品参照：{_join_report_terms(row.get('competition_nodes') or [], '未明显出现')}。"
                    )
                    for row in platform_source_summary.get("platforms", [])[:5]
                ],
            ],
            "so_what": "后续内容投放和问答素材应按平台偏好分层，分别处理每个平台的回答机制。",
            "supporting_facts": [
                f"有效平台 {platform_count} 个，有效回答 {valid_answers} 条。",
                f"尝试平台：{requested_platforms}。",
                platform_scope_sentence,
            ],
            "evidence_refs": [],
            "next_probe": platform_next_probe,
        },
        {
            "section_id": "risk_competition",
            "role": "risk_finding",
            "title": "风险语境与竞品参照",
            "reader_question": "哪些场景会把回答带离安利？",
            "takeaway": (
                f"风险关系 {risk_summary.get('risk_count', 0)} 个，"
                f"竞品参照 {competition_count} 个；这部分必须回到问题场景和平台原文判断。"
            ),
            "claims": (
                risk_scene_lines[:2]
                + competition_scene_lines[:2]
                or ["本轮风险语境和竞品参照较弱，仍应保留为首期基线。"]
            ),
            "paragraphs": [
                (
                    "风险与竞品不放进普通机会轨道。它们回答的是另一件事："
                    "当用户提问涉及信任、销售方式、合规、价格或替代选择时，"
                    f"AI 会不会把回答从{center_term}带到旧认知或竞品选择。"
                ),
                *risk_scene_lines,
                *competition_scene_lines,
            ],
            "so_what": "品牌防守动作要按场景拆开：信任问题补澄清，销售方式问题补合规与服务边界，竞品替代问题补产品证据和适用人群。",
            "supporting_facts": [
                f"风险节点 {len(risk_summary.get('risk_nodes') or [])} 个。",
                f"竞品节点 {len(risk_summary.get('competition_nodes') or [])} 个。",
                f"风险关系总数 {risk_summary.get('risk_count', 0)}，竞品参照 {competition_count}。",
            ],
            "evidence_refs": [
                ref
                for row in (risk_summary.get("risk_nodes") or [])
                + (risk_summary.get("competition_nodes") or [])
                if isinstance(row, dict)
                for ref in row.get("evidence_refs", [])[:2]
            ][:8],
            "next_probe": "下一轮保留触发风险和竞品的题目，观察这些词是否减少、转弱，或被新的品牌证据替代。",
        },
        {
            "section_id": "overall_strategy",
            "role": "action_finding",
            "title": "从数据到行动",
            "reader_question": "品牌团队这周先做哪三件事？",
            "takeaway": f"总体判断为{overall_status}。先守住近端资产，再把机会词补成可被回答引用的证据链，同时按场景处理竞品和风险。",
            "claims": [
                f"已经站稳的战略资产：{_join_report_terms(strong_terms or validated_terms, '待形成')}。",
                f"正在形成的机会：{_join_report_terms(growth_terms or partial_terms, '待继续发现')}。",
                f"尚未验证的战略词：{_join_report_terms(missing_terms, '本轮未形成明显缺口')}。",
                f"风险防守方向：{_join_report_terms(risk_terms, '本轮风险关系较弱')}。",
            ],
            "paragraphs": [
                (
                    f"{center_term}当前可以马上放大的资产是{_join_report_terms(strong_terms or validated_terms, '已被回答接住的资产')}。"
                    "这些资产已经具备进入内容资产和复测基线的条件。"
                ),
                (
                    f"正在形成的机会是{_join_report_terms(growth_terms or partial_terms, '部分验证战略词')}。"
                    "它们需要补内容、补证据、补场景，暂时不宜直接作为唯一传播主轴。"
                ),
                (
                    f"尚未验证的战略词包括{_join_report_terms(missing_terms, '本轮未形成明显缺口')}。"
                    "这些词应先补题和补证据，再进入主传播表达。"
                ),
                (
                    f"风险关系{_join_report_terms(risk_terms, '当前较弱')}需要独立追踪。"
                    "处理风险时先看原文语境，再设计澄清和替代表达。"
                ),
            ],
            "so_what": "品牌策略应从心智愿望回到回答证据，用复测判断战略词是否真的移动。",
            "supporting_facts": first_finding.get("supporting_facts") or [],
            "evidence_refs": first_finding.get("evidence_refs") or [],
            "next_probe": "下一轮用同一题库复测核心资产、战略机会、未验证战略词和风险关系四类对象。",
        },
        {
            "section_id": "next_tracking",
            "role": "action_finding",
            "title": "附录：样本、平台与原文证据",
            "reader_question": "这轮判断的样本边界是什么？",
            "takeaway": f"本轮先作为{tracking_label}保存；下一轮固定题库口径，分别追踪战略词、风险词和机会词的轨道变化。",
            "claims": [
                f"继续追踪战略词：{_join_report_terms(partial_terms or validated_terms, '部分验证战略词')}。",
                "保留本轮能区分内圈、中圈、外圈和风险关系的问题。",
                f"新增问题聚焦：{_join_report_terms(missing_terms or far_terms, '缺少证据的战略词')}。",
                f"风险复测对象：{_join_report_terms(risk_terms, '本轮风险基线')}。",
                *(action_lines[:2] if action_lines else []),
            ],
            "paragraphs": [
                (
                    f"继续追踪{_join_report_terms(partial_terms or validated_terms, '已进入验证范围的战略词')}。"
                    "重点看它们是否从外圈进入中圈，或从中圈进入内圈。"
                ),
                (
                    "保留本轮能稳定触发近端资产、机会词和风险关系的问题，保证下一轮可以比较位置变化。"
                ),
                (
                    f"新增问题应围绕{_join_report_terms(missing_terms or far_terms, '证据不足方向')}，"
                    "补充人群、生活场景、产品证据和品牌锚定探针。"
                ),
                (
                    f"风险词要看{_join_report_terms(risk_terms, '本轮风险基线')}是否下降，"
                    f"机会词要看{_join_report_terms(growth_terms + far_terms, '本轮机会词')}是否向中心移动。"
                ),
                *action_lines,
            ],
            "so_what": "下一轮追踪要服务决策：哪些词可以放大，哪些词继续补证据，哪些风险需要先澄清。",
            "supporting_facts": [
                f"本轮战略词 {len(strategy_validation)} 个。",
                f"有效回答 {valid_answers} 条，平台 {platform_count} 个。",
            ],
            "evidence_refs": first_finding.get("evidence_refs") or [],
            "next_probe": "下轮报告应输出同一批战略词的位置变化、平台提及变化和风险词变化。",
        },
    ]


def _build_calibrated_report_markdown(
    *,
    title: str,
    narrative_sections: list[dict[str, Any]],
    strategy_validation: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    platform_source_summary: dict[str, Any],
    source_appendix: list[dict[str, Any]],
) -> str:
    lines = [f"# {title}", ""]
    for section in narrative_sections:
        lines.extend([f"## {section.get('title')}", ""])
        takeaway = _clean_text(section.get("takeaway"))
        if takeaway:
            lines.extend([f"**{takeaway}**", ""])
        claims = [
            _clean_text(item)
            for item in section.get("claims") or []
            if _clean_text(item)
        ]
        if claims:
            lines.extend(["要看见的事实：", ""])
            for claim in claims[:6]:
                lines.append(f"- {claim}")
            lines.append("")
        for paragraph in section.get("paragraphs") or []:
            text = _clean_text(paragraph)
            if text:
                lines.extend([text, ""])
        facts = [
            _clean_text(item)
            for item in section.get("supporting_facts") or []
            if _clean_text(item)
        ]
        if facts:
            for fact in facts[:5]:
                if fact.startswith(("平台原文", "AI 原文", "平台原文样本")):
                    lines.append(f"> {fact}")
                else:
                    lines.append(f"- {fact}")
            lines.append("")
        next_probe = _clean_text(section.get("next_probe"))
        if next_probe:
            lines.extend([next_probe, ""])
    lines.extend(["## 附录：平台样本", ""])
    for row in platform_source_summary.get("platforms", [])[:8]:
        lines.append(
            f"- {row.get('platform')}：有效回答 {row.get('valid_answer_count', 0)} 条；"
            f"{row.get('answer_preference', '')}"
        )
    lines.extend(["", "## 附录：问题与原文摘录", ""])
    appendix_rows: dict[tuple[str, str, str], set[str]] = {}
    for item in source_appendix:
        platform = _clean_text(item.get("platform"))
        question = _clean_text(item.get("question"))
        excerpt = _clean_text(item.get("answer_excerpt"))
        if not (platform and question and excerpt):
            continue
        key = (platform, question, excerpt)
        appendix_rows.setdefault(key, set()).add(_clean_text(item.get("node_term")))
        if len(appendix_rows) >= 20:
            break
    for (platform, question, excerpt), terms in appendix_rows.items():
        term_values = sorted(term for term in terms if term)
        if len(term_values) > 8:
            linked_terms = "、".join(term_values[:8]) + f"等 {len(term_values)} 个节点"
        else:
            linked_terms = "、".join(term_values) or "相关节点"
        lines.append(
            f"- [{platform}] {question} => {linked_terms}：{excerpt}"
        )
    return "\n".join(lines).strip() + "\n"


def _ensure_report_strategy_storyline(
    *,
    center_terms: list[str],
    sample_scope: dict[str, Any],
    nodes: list[dict[str, Any]],
    strategy_validation: list[dict[str, Any]],
    risk_summary: dict[str, Any],
    platform_source_summary: dict[str, Any],
    source_appendix: list[dict[str, Any]],
    strategy_storyline: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(strategy_storyline, dict) and strategy_storyline.get("pillars"):
        return strategy_storyline

    from app.services.amway_entity_calibration_service import (
        _build_four_have_strategy_storyline,
    )

    generated = _build_four_have_strategy_storyline(
        center_terms=center_terms,
        sample_scope=sample_scope,
        nodes=nodes,
        strategy_validation=strategy_validation,
        risk_map=risk_summary,
        platform_summary=platform_source_summary,
        source_appendix=source_appendix,
    )
    return generated if isinstance(generated, dict) else {}


def _build_report_from_calibrated_input(
    *,
    session_id: str,
    entity_id: str | None,
    brand_profile: dict[str, Any],
    fetch_results: list[dict[str, Any]],
    simulated_questions: list[dict[str, Any]] | dict[str, Any] | None,
    center_terms: list[str] | None,
    entity_calibration_result: dict[str, Any],
) -> dict[str, Any]:
    report_input = _extract_calibrated_report_input(entity_calibration_result) or {}
    association_map = (
        report_input.get("association_map")
        if isinstance(report_input.get("association_map"), dict)
        else {}
    )
    projection = (
        entity_calibration_result.get("association_circle_projection")
        if isinstance(entity_calibration_result.get("association_circle_projection"), dict)
        else {}
    )
    nodes = (
        association_map.get("nodes")
        if isinstance(association_map.get("nodes"), list)
        else projection.get("nodes") if isinstance(projection.get("nodes"), list) else []
    )
    evidence_samples = (
        association_map.get("evidence_samples")
        if isinstance(association_map.get("evidence_samples"), list)
        else projection.get("evidence_samples")
        if isinstance(projection.get("evidence_samples"), list)
        else []
    )
    resolved_center_terms = _normalize_center_terms(
        brand_profile,
        center_terms
        or association_map.get("center_terms")
        or projection.get("center_terms"),
    )
    question_bank = (
        projection.get("question_bank")
        if isinstance(projection.get("question_bank"), list)
        else _build_question_bank(simulated_questions, fetch_results)
    )
    sample_scope = (
        entity_calibration_result.get("sample_scope")
        if isinstance(entity_calibration_result.get("sample_scope"), dict)
        else projection.get("sample_scope")
        if isinstance(projection.get("sample_scope"), dict)
        else {
            "question_count": len(fetch_results or []),
            "valid_answer_count": 0,
            "normalized_node_count": len(nodes),
        }
    )
    sample_scope = {**sample_scope, "normalized_node_count": len(nodes)}
    platform_source_summary = (
        report_input.get("platform_scope")
        if isinstance(report_input.get("platform_scope"), dict)
        else projection.get("platform_source_summary")
        if isinstance(projection.get("platform_source_summary"), dict)
        else {}
    )
    platform_comparison = (
        platform_source_summary.get("platforms")
        if isinstance(platform_source_summary.get("platforms"), list)
        else projection.get("platform_comparison")
        if isinstance(projection.get("platform_comparison"), list)
        else []
    )
    strategy_validation = (
        report_input.get("strategy_validation")
        if isinstance(report_input.get("strategy_validation"), list)
        else projection.get("strategy_validation")
        if isinstance(projection.get("strategy_validation"), list)
        else []
    )
    strategy_storyline = (
        report_input.get("strategy_storyline")
        if isinstance(report_input.get("strategy_storyline"), dict)
        else projection.get("strategy_storyline")
        if isinstance(projection.get("strategy_storyline"), dict)
        else {}
    )
    risk_summary = (
        report_input.get("risk_summary")
        if isinstance(report_input.get("risk_summary"), dict)
        else projection.get("risk_map")
        if isinstance(projection.get("risk_map"), dict)
        else {}
    )
    evidence_findings = (
        report_input.get("evidence_findings")
        if isinstance(report_input.get("evidence_findings"), list)
        else projection.get("evidence_findings")
        if isinstance(projection.get("evidence_findings"), list)
        else []
    )
    source_appendix = (
        report_input.get("source_appendix")
        if isinstance(report_input.get("source_appendix"), list)
        else projection.get("source_appendix")
        if isinstance(projection.get("source_appendix"), list)
        else []
    )
    association_actions = (
        report_input.get("association_actions")
        if isinstance(report_input.get("association_actions"), list)
        else projection.get("association_actions")
        if isinstance(projection.get("association_actions"), list)
        else _build_association_actions(nodes)
    )
    tracking_projection = (
        report_input.get("tracking_projection")
        if isinstance(report_input.get("tracking_projection"), dict)
        else projection.get("tracking_projection")
        if isinstance(projection.get("tracking_projection"), dict)
        else {}
    )
    if tracking_projection:
        sample_scope = {
            **sample_scope,
            "tracking_status": tracking_projection.get("status"),
            "tracking_status_label": tracking_projection.get("status_label"),
            "tracking_round_label": tracking_projection.get("round_label"),
        }
    question_definition = (
        report_input.get("question_scope")
        if isinstance(report_input.get("question_scope"), dict)
        else projection.get("question_definition")
        if isinstance(projection.get("question_definition"), dict)
        else _build_question_definition(
            center_terms=resolved_center_terms,
            question_bank=question_bank,
            sample_scope=sample_scope,
        )
    )
    strategy_storyline = _ensure_report_strategy_storyline(
        center_terms=resolved_center_terms,
        sample_scope=sample_scope,
        nodes=nodes,
        strategy_validation=strategy_validation,
        risk_summary=risk_summary,
        platform_source_summary=platform_source_summary,
        source_appendix=source_appendix,
        strategy_storyline=strategy_storyline,
    )
    executive_summary = _build_calibrated_executive_summary(
        center_terms=resolved_center_terms,
        sample_scope=sample_scope,
        nodes=nodes,
        strategy_validation=strategy_validation,
        risk_summary=risk_summary,
    )
    storyline_analysis = _build_storyline_report_analysis(
        center_terms=resolved_center_terms,
        sample_scope=sample_scope,
        nodes=nodes,
        platform_source_summary=platform_source_summary,
        fetch_results=fetch_results,
        source_appendix=source_appendix,
    )
    title = f"{_first_center_term(resolved_center_terms)}品牌 AI 认知图景"
    report_outline = _build_report_outline(resolved_center_terms)
    narrative_sections = _build_calibrated_report_narrative_sections(
        center_terms=resolved_center_terms,
        sample_scope=sample_scope,
        executive_summary=executive_summary,
        nodes=nodes,
        strategy_validation=strategy_validation,
        risk_summary=risk_summary,
        platform_source_summary=platform_source_summary,
        evidence_findings=evidence_findings,
        association_actions=association_actions,
        tracking_projection=tracking_projection,
        strategy_storyline=strategy_storyline,
        storyline_analysis=storyline_analysis,
    )
    analysis_tool_trace = _build_analysis_tool_trace(
        question_definition=question_definition,
        platform_source_summary=platform_source_summary,
        evidence_findings=evidence_findings,
        association_actions=association_actions,
    )
    quality_checks = _build_report_quality_checks(
        narrative_sections=narrative_sections,
        question_definition=question_definition,
        platform_source_summary=platform_source_summary,
        evidence_findings=evidence_findings,
        association_actions=association_actions,
        source_appendix=source_appendix,
    )
    full_markdown = _build_calibrated_report_markdown(
        title=title,
        narrative_sections=narrative_sections,
        strategy_validation=strategy_validation,
        nodes=nodes,
        platform_source_summary=platform_source_summary,
        source_appendix=source_appendix,
    )
    summary_metrics = [
        ["问题样本", str(sample_scope.get("question_count", 0)), "进入本轮的问题数"],
        ["有效回答", str(sample_scope.get("valid_answer_count", 0)), "用于解析的回答"],
        ["解析节点", str(len(nodes)), "经实体校准后进入图谱的节点"],
        ["战略词", str(len(strategy_validation)), "纳入逐项验证的战略词"],
        ["风险关系", str(risk_summary.get("risk_count", 0)), "单独追踪的风险节点"],
    ]
    report_sections = [
        {
            "section_name": "narrative",
            "title": "品牌圈层解读",
            "markdown": "\n\n".join(
                f"### {section.get('title')}\n\n"
                + "\n\n".join(
                    _clean_text(paragraph)
                    for paragraph in section.get("paragraphs") or []
                    if _clean_text(paragraph)
                )
                for section in narrative_sections
            ),
            "data": {"items": narrative_sections},
        },
        {
            "section_name": "strategy_validation",
            "title": "战略词底层数据",
            "markdown": "供图谱、筛选和附录追溯使用，正文不再逐词套用模板。",
            "data": {"items": strategy_validation},
        },
        {
            "section_name": "platform_comparison",
            "title": "平台差异",
            "markdown": "比较不同平台对安利品牌联想的偏好。",
            "data": {"items": platform_comparison},
        },
        {
            "section_name": "evidence_findings",
            "title": "原文证据",
            "markdown": "每个判断绑定节点、问题、平台和回答摘录。",
            "data": {"items": evidence_findings},
        },
        {
            "section_name": "association_actions",
            "title": "行动建议底层数据",
            "markdown": "行动建议绑定节点、回答证据和下一轮验证问题。",
            "data": {"items": association_actions},
        },
        {
            "section_name": "source_appendix",
            "title": "附录",
            "markdown": "问题与回答摘录。",
            "data": {"items": source_appendix},
        },
    ]
    projection_payload = {
        **projection,
        "center_terms": resolved_center_terms,
        "nodes": nodes,
        "evidence_samples": evidence_samples[:120],
        "question_bank": question_bank[:200],
        "platform_comparison": platform_comparison,
        "association_actions": association_actions,
        "report_narrative_sections": narrative_sections,
        "question_definition": question_definition,
        "platform_source_summary": platform_source_summary,
        "evidence_findings": evidence_findings[:80],
        "report_outline": report_outline,
        "analysis_tool_trace": analysis_tool_trace,
        "source_appendix": source_appendix[:80],
        "strategy_validation": strategy_validation,
        "strategy_storyline": strategy_storyline,
        "storyline_analysis": storyline_analysis,
        "risk_map": risk_summary,
        "tracking_projection": tracking_projection,
        "report_quality_checks": quality_checks,
        "copy_constraints": {
            "version": REPORT_COPY_CONSTRAINT_VERSION,
            "forbidden_phrases": list(REPORT_COPY_FORBIDDEN_PHRASES),
            "forbidden_patterns": list(REPORT_COPY_FORBIDDEN_PATTERNS),
            "required_spine": list(REPORT_REQUIRED_EVIDENCE_SPINE),
            "required_section_fields": list(
                REPORT_NARRATIVE_SECTION_REQUIRED_FIELDS
            ),
        },
        "generated_from": "entity_calibration",
    }
    return {
        "artifact_kind": ARTIFACT_KIND,
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "headline": title,
        "subtitle": executive_summary["one_line_judgment"],
        "brand_name": _clean_text(brand_profile.get("brand_name")) or "安利中国",
        "session_id": session_id,
        "entity_id": entity_id,
        "center_terms": resolved_center_terms,
        "sample_scope": sample_scope,
        "question_bank": question_bank,
        "question_definition": question_definition,
        "platform_source_summary": platform_source_summary,
        "evidence_findings": evidence_findings,
        "report_outline": report_outline,
        "analysis_tool_trace": analysis_tool_trace,
        "source_appendix": source_appendix,
        "strategy_validation": strategy_validation,
        "strategy_storyline": strategy_storyline,
        "storyline_analysis": storyline_analysis,
        "risk_summary": risk_summary,
        "tracking_projection": tracking_projection,
        "executive_summary": executive_summary,
        "report_narrative_sections": narrative_sections,
        "report_quality_checks": quality_checks,
        "copy_constraints": projection_payload["copy_constraints"],
        "summary_metrics": summary_metrics,
        "report_sections": report_sections,
        "sections": report_sections,
        "association_circle": {
            "nodes": nodes,
            "evidence_samples": evidence_samples,
            "question_bank": question_bank,
            "evidence_findings": evidence_findings,
            "source_appendix": source_appendix,
        },
        "platform_comparison": platform_comparison,
        "association_actions": association_actions,
        "dashboard_projection": {
            "brief_card": {
                "title": "母品牌联想圈层",
                "status": "样本不足"
                if int(sample_scope.get("valid_answer_count") or 0) < 4
                else "已生成",
            },
            "brand_world_view_mode": "association_circle",
            "association_circle_views": ["flat", "spatial"],
            "association_circle_projection": projection_payload,
        },
        "full_markdown": full_markdown,
        "report_markdown": full_markdown,
        "report_input": report_input,
        "entity_calibration_result": {
            "schema_version": entity_calibration_result.get("schema_version"),
            "ontology_version": entity_calibration_result.get("ontology_version"),
            "generated_at": entity_calibration_result.get("generated_at"),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_missing_calibration_artifact(
    *,
    session_id: str,
    entity_id: str | None,
    brand_profile: dict[str, Any],
    simulated_questions: list[dict[str, Any]] | dict[str, Any] | None,
    center_terms: list[str] | None,
) -> dict[str, Any]:
    resolved_center_terms = _normalize_center_terms(brand_profile, center_terms)
    question_bank = _build_question_bank(simulated_questions, [])
    generated_at = datetime.now(timezone.utc).isoformat()
    projection_payload = {
        "status": "needs_entity_calibration",
        "generated_from": "missing_entity_calibration",
        "center_terms": resolved_center_terms,
        "nodes": [],
        "evidence_samples": [],
        "question_bank": question_bank[:200],
        "question_definition": {
            "center_term": resolved_center_terms[0] if resolved_center_terms else "",
            "question_count": len(question_bank),
            "sample_questions": question_bank[:8],
        },
        "sample_scope": {
            "question_count": len(question_bank),
            "total_answer_count": 0,
            "valid_answer_count": 0,
            "failed_answer_count": 0,
            "empty_answer_count": 0,
            "platform_count": 0,
        },
        "platform_comparison": [],
        "association_actions": [],
        "strategy_validation": [],
        "risk_map": {"risk_count": 0, "nodes": []},
        "report_narrative_sections": [],
        "report_quality_checks": {
            "passed": False,
            "reason": "missing_entity_calibration",
            "required_checks": [
                {
                    "key": "calibrated_report_input",
                    "passed": False,
                    "detail": "A5 requires Entity Calibration report_input.",
                }
            ],
        },
        "copy_constraints": {
            "version": REPORT_COPY_CONSTRAINT_VERSION,
            "required_spine": list(REPORT_REQUIRED_EVIDENCE_SPINE),
            "required_section_fields": list(
                REPORT_NARRATIVE_SECTION_REQUIRED_FIELDS
            ),
        },
    }
    report_markdown = (
        "# 品牌联想圈层报告\n\n"
        "## 状态\n\n"
        "缺少 Entity Calibration 产出的 report_input。A5 已停止生成正式圈层解读；"
        "请先完成 A4 抓取、实体抽取和校准汇总。\n"
    )
    report_sections = [
        {
            "section_name": "missing_entity_calibration",
            "title": "等待校准输入",
            "content": (
                "缺少 Entity Calibration 产出的 report_input。"
                "A5 当前只生成报告，不生成图谱节点。"
            ),
        }
    ]
    return {
        "kind": ARTIFACT_KIND,
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "status": "needs_entity_calibration",
        "session_id": session_id,
        "entity_id": entity_id,
        "center_terms": resolved_center_terms,
        "sample_scope": projection_payload["sample_scope"],
        "question_bank": question_bank,
        "question_definition": projection_payload["question_definition"],
        "platform_source_summary": {"platforms": []},
        "evidence_findings": [],
        "report_outline": [],
        "analysis_tool_trace": [
            {
                "step": "A5",
                "operation": "report_generation_guard",
                "input": "entity_calibration_result.report_input",
                "output": "needs_entity_calibration",
            }
        ],
        "source_appendix": [],
        "strategy_validation": [],
        "risk_summary": projection_payload["risk_map"],
        "executive_summary": "",
        "report_narrative_sections": [],
        "report_quality_checks": projection_payload["report_quality_checks"],
        "copy_constraints": projection_payload["copy_constraints"],
        "summary_metrics": [],
        "report_sections": report_sections,
        "sections": report_sections,
        "association_circle": {
            "nodes": [],
            "evidence_samples": [],
            "question_bank": question_bank,
            "evidence_findings": [],
            "source_appendix": [],
        },
        "platform_comparison": [],
        "association_actions": [],
        "dashboard_projection": {
            "brief_card": {
                "title": "母品牌联想圈层",
                "status": "等待校准输入",
            },
            "brand_world_view_mode": "association_circle",
            "association_circle_views": ["flat", "spatial"],
            "association_circle_projection": projection_payload,
        },
        "full_markdown": report_markdown,
        "report_markdown": report_markdown,
        "report_input": {},
        "entity_calibration_result": {},
        "updated_at": generated_at,
    }


def build_brand_association_circle_report_artifact(
    *,
    session_id: str,
    entity_id: str | None,
    brand_profile: dict[str, Any],
    fetch_results: list[dict[str, Any]],
    simulated_questions: list[dict[str, Any]] | dict[str, Any] | None = None,
    center_terms: list[str] | None = None,
    entity_calibration_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _extract_calibrated_report_input(entity_calibration_result):
        return _build_report_from_calibrated_input(
            session_id=session_id,
            entity_id=entity_id,
            brand_profile=brand_profile,
            fetch_results=fetch_results,
            simulated_questions=simulated_questions,
            center_terms=center_terms,
            entity_calibration_result=entity_calibration_result or {},
        )

    return _build_missing_calibration_artifact(
        session_id=session_id,
        entity_id=entity_id,
        brand_profile=brand_profile,
        simulated_questions=simulated_questions,
        center_terms=center_terms,
    )

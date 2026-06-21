"""Internal question-generation primitives used by the A3 workflow stage."""

from __future__ import annotations

from textwrap import dedent
from typing import Any

from app.core.constants import PlatformConstants

_VALID_PERSONA_CATEGORIES = (
    "画像痛点场景",
    "品牌直接问题",
    "品类选购对比",
    "行业趋势认知",
)
_PERSONA_CATEGORY_ALIAS_MAP = {
    "痛点场景": "画像痛点场景",
    "用户痛点场景": "画像痛点场景",
    "品牌问题": "品牌直接问题",
    "品牌相关问题": "品牌直接问题",
    "品类对比": "品类选购对比",
    "选购对比": "品类选购对比",
    "行业趋势": "行业趋势认知",
}
_PANORAMA_COMPARE_CUES = (
    "谁家",
    "谁更",
    "哪家",
    "哪个牌子",
    "哪个品牌",
    "更好",
    "更强",
    "更厉害",
    "谁更强",
    "性价比更高",
    "值不值得",
    "排名",
    "vs",
    "VS",
)
ASSOCIATION_CIRCLE_CENTER_TERMS = (
    "安利",
    "安利中国",
    "纽崔莱",
    "Amway China",
    "Nutrilite",
)
ASSOCIATION_CIRCLE_METADATA_KEYS = (
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
    "metadata_missing_fields",
)
ASSOCIATION_CIRCLE_REQUIRED_METADATA_KEYS = (
    "audience_segment",
    "core_anxiety",
    "life_scene",
    "opportunity_point",
    "probe_type",
)


def _association_metadata_from_question(question: dict) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ASSOCIATION_CIRCLE_METADATA_KEYS:
        value = question.get(key)
        if value is None or value == "":
            continue
        metadata[key] = value
    return metadata


def infer_association_question_metadata(
    question_text: str,
    *,
    center_terms: Any = None,
) -> dict[str, Any]:
    """Infer first-pass Amway association metadata for uploaded questions."""

    text = str(question_text or "")
    normalized = text.lower()
    metadata: dict[str, Any] = {
        "center_terms": normalize_association_center_terms(center_terms),
        "question_set_version": "uploaded_association_circle_v1",
    }

    if any(keyword in text for keyword in ("退休后", "银发", "老年", "孤独", "长寿")):
        metadata.update(
            {
                "audience_segment": "活力银发",
                "core_anxiety": "慢病预防、孤独感、被需要感、生活质量",
                "life_scene": "退休后健康维护与社交关系重建",
            }
        )
    elif any(
        keyword in text for keyword in ("50", "退休", "第二事业", "再出发", "转型")
    ):
        metadata.update(
            {
                "audience_segment": "50-65 人生转换期",
                "core_anxiety": "退休准备、收入安全感、关系变化、价值感",
                "life_scene": "职业后半程和家庭角色变化",
            }
        )
    elif any(keyword in text for keyword in ("中年", "40", "35", "抗衰", "家庭责任")):
        metadata.update(
            {
                "audience_segment": "35-50 初老期",
                "core_anxiety": "抗衰焦虑、家庭责任、长期健康掌控感",
                "life_scene": "身体状态变化和家庭责任叠加",
            }
        )
    else:
        metadata.update(
            {
                "audience_segment": "25-35 健康预防期",
                "core_anxiety": "精力不足、饮食不规律、早期健康管理",
                "life_scene": "工作压力和轻健康习惯建立",
            }
        )

    if any(keyword in text for keyword in ("安利人", "abo", "koc")):
        metadata["opportunity_point"] = "安利人品牌表达"
    elif any(
        keyword in text for keyword in ("第二事业", "事业", "副业", "收入", "再出发")
    ):
        metadata["opportunity_point"] = "事业机会作为多段人生再出发平台"
    elif any(keyword in text for keyword in ("社群", "陪伴", "孤独", "关系")):
        metadata["opportunity_point"] = "安利社群外显"
    elif any(keyword in text for keyword in ("科技", "抗衰", "营养科学")):
        metadata["opportunity_point"] = "科技安利"
    elif any(keyword in text for keyword in ("长寿", "银发", "退休后")):
        metadata["opportunity_point"] = "长寿时代"
    else:
        metadata["opportunity_point"] = "健康习惯"

    if any(keyword in text for keyword in ("安利", "纽崔莱", "amway", "nutrilite")):
        metadata["probe_type"] = "品牌锚定探针"
    elif any(
        keyword in text for keyword in ("如何", "怎样", "怎么", "关系", "路径", "连接")
    ):
        metadata["probe_type"] = "路径探针"
    elif any(keyword in text for keyword in ("需要", "能不能", "机会", "应该")):
        metadata["probe_type"] = "机会探针"
    elif any(keyword in normalized for keyword in ("why", "how", "amway", "nutrilite")):
        metadata["probe_type"] = "路径探针"
    else:
        metadata["probe_type"] = "无品牌自然探针"

    return metadata


def complete_association_question_metadata(
    question: dict[str, Any],
    *,
    center_terms: Any = None,
) -> dict[str, Any]:
    """Preserve uploaded tags and infer missing association-circle metadata."""

    metadata = _association_metadata_from_question(question)
    inferred = infer_association_question_metadata(
        str(
            question.get("text")
            or question.get("core_question")
            or question.get("question")
            or ""
        ),
        center_terms=metadata.get("center_terms") or center_terms,
    )
    inferred_keys: list[str] = []
    for key in ASSOCIATION_CIRCLE_REQUIRED_METADATA_KEYS:
        if metadata.get(key):
            continue
        inferred_value = inferred.get(key)
        if inferred_value:
            metadata[key] = inferred_value
            inferred_keys.append(key)
    if not metadata.get("center_terms"):
        metadata["center_terms"] = inferred.get("center_terms")
        inferred_keys.append("center_terms")
    if not metadata.get("question_set_version"):
        metadata["question_set_version"] = inferred.get("question_set_version")
        inferred_keys.append("question_set_version")

    missing_fields = [
        key
        for key in ASSOCIATION_CIRCLE_REQUIRED_METADATA_KEYS
        if not metadata.get(key)
    ]
    if missing_fields:
        metadata["metadata_status"] = "needs_review"
        metadata["metadata_missing_fields"] = missing_fields
    elif inferred_keys:
        metadata["metadata_status"] = "inferred_needs_review"
        metadata["metadata_missing_fields"] = []
    else:
        metadata["metadata_status"] = "complete"
        metadata["metadata_missing_fields"] = []
    return metadata


def normalize_uploaded_question_payload(
    questions: list[dict],
    *,
    start_index: int = 1,
    association_mode: bool = False,
    center_terms: Any = None,
) -> tuple[list[dict], list[dict]]:
    simulated_questions = []
    flattened_questions = []

    for offset, question in enumerate(questions, start=start_index):
        question_id = (
            question.get("id")
            or question.get("question_id")
            or f"upload_q_{offset:03d}"
        )
        category = question.get("category") or "上传问题"
        core_question = question.get("text") or question.get("core_question") or ""
        if not core_question:
            continue
        intent = question.get("intent") or question.get("user_intent") or ""
        stage = question.get("stage") or question.get("decision_stage") or ""
        association_metadata = (
            complete_association_question_metadata(question, center_terms=center_terms)
            if association_mode
            else _association_metadata_from_question(question)
        )

        simulated_questions.append(
            {
                "question_id": question_id,
                "category": category,
                "core_question": core_question,
                "user_intent": intent,
                "decision_stage": stage,
                "source": "uploaded_table",
                **association_metadata,
            }
        )
        flattened_questions.append(
            {
                "id": question_id,
                "text": core_question,
                "category": category,
                "intent": intent,
                "stage": stage,
                "source": "uploaded_table",
                **association_metadata,
            }
        )

    return simulated_questions, flattened_questions


def merge_uploaded_questions(
    existing_questions: list[dict],
    incoming_questions: list[dict],
) -> list[dict]:
    merged_questions: list[dict] = []
    seen_texts: set[str] = set()

    for question in [*existing_questions, *incoming_questions]:
        text = str(question.get("text") or question.get("core_question") or "").strip()
        if not text:
            continue
        normalized_text = " ".join(text.lower().split())
        if normalized_text in seen_texts:
            continue
        seen_texts.add(normalized_text)
        merged_questions.append(question)

    return merged_questions


def normalize_association_center_terms(value: Any = None) -> list[str]:
    raw_values: list[Any] = []
    if isinstance(value, str):
        raw_values = re_split_keywords(value)
    elif isinstance(value, (list, tuple)):
        raw_values = list(value)
    elif value:
        raw_values = [value]

    terms: list[str] = []
    for item in [*raw_values, *ASSOCIATION_CIRCLE_CENTER_TERMS]:
        text = " ".join(str(item or "").strip().split())
        if text and text not in terms:
            terms.append(text)
    return terms


def build_association_circle_question_matrix(
    *,
    center_terms: list[str] | tuple[str, ...] | str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Build the first deterministic Amway association-circle question matrix."""

    resolved_center_terms = normalize_association_center_terms(center_terms)
    brand_label = resolved_center_terms[0]
    rows = [
        {
            "audience_segment": "25-35 健康预防期",
            "core_anxiety": "精力不足、饮食不规律、早期健康管理",
            "life_scene": "工作压力和轻健康习惯建立",
            "opportunity_point": "健康习惯",
            "questions": {
                "无品牌自然探针": "年轻上班族想改善精力和饮食不规律，通常会想到哪些营养或生活方式方案？",
                "路径探针": "从营养补充到长期健康习惯，中间最关键的支持是什么？",
                "品牌锚定探针": f"提到{brand_label}和年轻人的健康管理，你会想到哪些产品或服务？",
                "机会探针": {
                    "text": "年轻人为什么会需要一个能陪伴建立健康习惯的生活方式社群？",
                    "opportunity_point": "安利社群外显",
                },
            },
        },
        {
            "audience_segment": "35-50 初老期",
            "core_anxiety": "抗衰焦虑、家庭责任、长期健康掌控感",
            "life_scene": "身体状态变化和家庭责任叠加",
            "opportunity_point": "科技抗衰",
            "questions": {
                "无品牌自然探针": "中年人开始关注抗衰和长期健康管理时，通常会先想到哪些方案？",
                "路径探针": "中年抗衰除了产品，还需要哪些营养、运动和生活方式支持？",
                "品牌锚定探针": f"如果把{brand_label}、纽崔莱和抗衰管理放在一起，你会如何理解它们的关系？",
                "机会探针": {
                    "text": "科技抗衰怎样才能从单个产品变成持续健康管理方案？",
                    "opportunity_point": "科技安利",
                },
            },
        },
        {
            "audience_segment": "50-65 人生转换期",
            "core_anxiety": "退休准备、收入安全感、关系变化、价值感",
            "life_scene": "职业后半程和家庭角色变化",
            "opportunity_point": "人生再出发",
            "questions": {
                "无品牌自然探针": "50 岁以后想重新规划人生和健康，通常会寻找哪些支持？",
                "路径探针": {
                    "text": "健康产品、社群关系和第二事业之间，怎样可能形成互相支持？",
                    "opportunity_point": "事业机会作为多段人生再出发平台",
                },
                "品牌锚定探针": {
                    "text": f"提到{brand_label}和安利人，它们和中年人的第二事业或人生再出发有什么关系？",
                    "opportunity_point": "安利人品牌表达",
                },
                "机会探针": "人生再出发需要什么样的社群、能力和长期陪伴？",
            },
        },
        {
            "audience_segment": "活力银发",
            "core_anxiety": "慢病预防、孤独感、被需要感、生活质量",
            "life_scene": "退休后健康维护与社交关系重建",
            "opportunity_point": "长寿时代",
            "questions": {
                "无品牌自然探针": "长寿时代下，退休人群最需要哪些健康、陪伴和价值支持？",
                "路径探针": "营养健康、关系陪伴和美好生活社群如何帮助银发人群提升生活质量？",
                "品牌锚定探针": f"如果从长寿时代看{brand_label}和纽崔莱，它们能提供什么支持？",
                "机会探针": "一个面向长寿时代的美好生活社群，应该解决哪些真实问题？",
            },
        },
    ]

    questions: list[dict[str, Any]] = []
    sequence = 1
    for row in rows:
        for probe_type, question_spec in row["questions"].items():
            if isinstance(question_spec, dict):
                question = str(question_spec.get("text") or "")
                opportunity_point = str(
                    question_spec.get("opportunity_point") or row["opportunity_point"]
                )
            else:
                question = str(question_spec)
                opportunity_point = str(row["opportunity_point"])
            questions.append(
                {
                    "question_id": f"ac_{sequence:03d}",
                    "category": "品牌联想圈层",
                    "core_question": question,
                    "user_intent": "识别 AI 回答中的品牌联想距离和连接路径",
                    "decision_stage": "认知",
                    "audience_segment": row["audience_segment"],
                    "core_anxiety": row["core_anxiety"],
                    "life_scene": row["life_scene"],
                    "opportunity_point": opportunity_point,
                    "probe_type": probe_type,
                    "center_terms": resolved_center_terms,
                    "source": "association_circle_matrix",
                }
            )
            sequence += 1

    if limit is not None:
        return questions[: max(0, int(limit))]
    return questions


def extract_brand_name(
    brand_profile: dict, fallback_state: dict[str, Any] | None = None
) -> str:
    brand_name = brand_profile.get("brand_name", "") or brand_profile.get("name", "")
    if not brand_name and fallback_state:
        brand_name = str(fallback_state.get("brand_name") or "")
    return brand_name or "品牌"


def _normalize_persona_category(raw: str) -> str:
    raw = str(raw or "").strip()
    if raw in _VALID_PERSONA_CATEGORIES:
        return raw
    if raw in _PERSONA_CATEGORY_ALIAS_MAP:
        return _PERSONA_CATEGORY_ALIAS_MAP[raw]
    for valid in _VALID_PERSONA_CATEGORIES:
        if valid in raw or raw in valid:
            return valid
    return "画像痛点场景"


def fix_persona_categories(
    questions: list[dict],
    brand_name: str,
    *,
    min_brand_ratio: float = 0.25,
) -> list[dict]:
    if not questions or not brand_name:
        return questions

    brand_lower = brand_name.lower()

    for question in questions:
        question["category"] = _normalize_persona_category(question.get("category", ""))

    total = len(questions)
    brand_count = sum(
        1 for question in questions if question["category"] == "品牌直接问题"
    )
    target_count = max(1, int(total * min_brand_ratio + 0.5))

    if brand_count < target_count:
        for question in questions:
            if brand_count >= target_count:
                break
            core = str(
                question.get("core_question", question.get("question", ""))
            ).lower()
            if brand_lower in core and question["category"] != "品牌直接问题":
                question["category"] = "品牌直接问题"
                brand_count += 1

    return questions


def build_question_generation_messages(
    *,
    mode: str,
    brand_profile: dict,
    competitors: list | None = None,
    selected_personas: list | None = None,
    platforms: list[str] | tuple[str, ...],
    identity: str | None = None,
    topic_keywords: list[str] | tuple[str, ...] | str | None = None,
    topic_description: str | None = None,
) -> tuple[str, str]:
    normalized_identity = _normalize_identity_override(identity)
    normalized_topic_keywords = normalize_topic_keywords(topic_keywords)
    normalized_topic_description = _normalize_topic_description(topic_description)
    if mode == "persona_focused":
        system_prompt, user_content = (
            _build_persona_system_prompt(platforms),
            _build_persona_user_content(brand_profile, selected_personas or []),
        )
    else:
        system_prompt, user_content = (
            _build_baseline_system_prompt(platforms),
            _build_baseline_user_content(
                brand_profile,
                competitors or [],
                topic_keywords=normalized_topic_keywords,
                topic_description=normalized_topic_description,
            ),
        )
    if normalized_identity:
        user_content = _append_identity_context(user_content, normalized_identity)
    return system_prompt, user_content


def normalize_topic_keywords(
    value: list[str] | tuple[str, ...] | str | None,
) -> list[str]:
    """Normalize user-supplied topic keywords for topic-driven panorama questions."""

    raw_items: list[str] = []
    if isinstance(value, str):
        raw_items = re_split_keywords(value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                raw_items.extend(re_split_keywords(item))
            elif item is not None:
                raw_items.extend(re_split_keywords(str(item)))

    keywords: list[str] = []
    for item in raw_items:
        keyword = " ".join(str(item or "").strip().split())
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return keywords[:12]


def re_split_keywords(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    for separator in ("，", "、", ";", "；", "|", "\n", "\t"):
        text = text.replace(separator, ",")
    return [part.strip() for part in text.split(",") if part.strip()]


def _normalize_identity_override(identity: str | None) -> str | None:
    text = str(identity or "").strip()
    return text or None


def _normalize_topic_description(topic_description: str | None) -> str | None:
    text = str(topic_description or "").strip()
    return text or None


def _append_identity_context(user_content: str, identity: str) -> str:
    return (
        user_content
        + "\n\n"
        + dedent(
            f"""
            ## 指定身份视角
            - 本次指定身份：{identity}
            - 用户已明确要求以该身份生成问题。
            - 若与默认消费者视角冲突，以该身份视角为准。
            """
        ).strip()
    )


def _build_persona_system_prompt(platforms: list[str] | tuple[str, ...]) -> str:
    platform_list = "、".join(
        PlatformConstants.PLATFORM_DISPLAY_NAMES.get(platform, platform)
        for platform in platforms
    )
    return f"""你是一个资深的 AI 平台用户行为分析专家。你的任务是根据品牌信息和用户画像，生成这些用户可能在 AI 平台（如{platform_list}）中提出的真实问题。

## 输出格式
请严格输出以下 JSON 格式，不要有其他文字：

{{
  "questions": [
    {{
      "question_id": "pq_001",
      "core_question": "用户会在 AI 平台中问的完整问题",
      "category": "必须从以下4个值中选择：画像痛点场景 | 品牌直接问题 | 品类选购对比 | 行业趋势认知",
      "user_intent": "用户提问的潜在意图",
      "decision_stage": "认知/兴趣/评估/决策/验证",
      "source_persona": "对应画像名称"
    }}
  ]
}}

## 问题分类比例（严格遵守，这是最高优先级的规则）
生成问题时，必须按以下数量分配（以12个问题为例）：
- 品牌直接问题：至少 3-4 个（约30%）— 必须在问题中直接提及品牌名称
- 画像痛点场景：约 4 个（约35%）— 基于画像痛点，不包含品牌名
- 品类选购对比：约 2-3 个（约20%）— 品类层面选购/对比
- 行业趋势认知：约 1-2 个（约15%）— 行业宏观趋势

⚠ 请先生成品牌直接问题，确保数量达标，再生成其他类型。

## 分类定义
- 品牌直接问题：用户已经知道目标品牌，直接询问品牌、产品、口碑、适用场景或购买建议；问题必须出现品牌名。
- 画像痛点场景：从用户身份、生活场景、痛点或任务出发提问，不直接出现品牌名。
- 品类选购对比：围绕品类、功能、成分、预算、替代方案进行比较，不把多个品牌写成互撕式排序。
- 行业趋势认知：询问行业趋势、新技术、新概念、消费变化或品类发展方向。

## 分类示例
- 品牌直接问题："【目标品牌】适合敏感肌长期使用吗？和我现在的护理习惯冲突吗？"
- 画像痛点场景："经常熬夜、皮肤状态不稳定的人，日常护理最该先解决什么问题？"
- 品类选购对比："预算 300 元以内，入门级修护类产品应该优先看哪些成分和功效？"
- 行业趋势认知："现在这个品类为什么都在强调科学验证和成分透明？"

## 生成规则
1. 每个画像生成 10-15 个问题
2. 问题必须覆盖决策全路径：认知 → 兴趣 → 评估 → 决策 → 验证
3. 不需要指定平台，系统会自动在 {platform_list} 之间轮转分配
4. 问题要贴合该画像人群的真实表达方式和关注点
5. 避免重复或过于笼统的问题
6. 总问题数不超过 40 个
7. 最高优先级：品牌直接问题必须占总数的 30%。生成完毕后请自检各分类数量。category 字段只能使用上述4个固定值。"""


def _build_persona_user_content(
    brand_profile: dict,
    selected_personas: list,
) -> str:
    brand_name = brand_profile.get("brand_name", "")
    industry = brand_profile.get("industry", "")
    description = brand_profile.get("description", "")
    products = ", ".join(brand_profile.get("core_products", []))

    persona_blocks = []
    for persona in selected_personas:
        name = persona.get("persona_name", persona.get("name", ""))
        desc = persona.get("persona_description", persona.get("description", ""))
        key_qs = persona.get("key_questions", [])
        scenarios = persona.get("usage_scenarios", [])

        demographics = persona.get("demographics")
        demo_text = ""
        if demographics and isinstance(demographics, dict):
            demo_parts = []
            if demographics.get("age_range"):
                demo_parts.append(f"年龄: {demographics['age_range']}")
            if demographics.get("gender"):
                demo_parts.append(f"性别: {demographics['gender']}")
            if demographics.get("city_tier"):
                demo_parts.append(f"城市: {demographics['city_tier']}")
            if demographics.get("income"):
                demo_parts.append(f"收入: {demographics['income']}")
            if demographics.get("occupation"):
                demo_parts.append(f"职业: {demographics['occupation']}")
            if demo_parts:
                demo_text = f"- 人口统计: {', '.join(demo_parts)}"

        psychographics = persona.get("psychographics")
        psycho_text = ""
        if psychographics and isinstance(psychographics, dict):
            psycho_parts = []
            if psychographics.get("lifestyle"):
                psycho_parts.append(f"生活方式: {psychographics['lifestyle']}")
            if psychographics.get("values"):
                psycho_parts.append(f"价值观: {psychographics['values']}")
            pain_points = psychographics.get("pain_points", [])
            if pain_points:
                psycho_parts.append(f"痛点: {', '.join(pain_points)}")
            if psycho_parts:
                psycho_text = f"- 心理画像: {'; '.join(psycho_parts)}"

        scenario_text = ""
        if scenarios:
            scenario_lines = []
            for scenario in scenarios:
                if isinstance(scenario, dict):
                    line = (
                        f"  - {scenario.get('scenario_name', '')}: "
                        f"{scenario.get('scenario_description', '')}"
                    )
                    intents = scenario.get(
                        "brand_interaction_intents",
                        scenario.get("likely_search_intents", []),
                    )
                    if intents:
                        line += f" (搜索意图: {', '.join(intents[:3])})"
                    scenario_lines.append(line)
                else:
                    scenario_lines.append(f"  - {scenario}")
            scenario_text = "\n".join(scenario_lines)

        persona_blocks.append(
            f"""### 画像：{name}
- 描述: {desc}
{demo_text}
{psycho_text}
- 典型问题: {", ".join(key_qs[:5]) if key_qs else "无"}
- 使用场景:
{scenario_text if scenario_text else "  - 无"}
"""
        )

    persona_text = "\n".join(persona_blocks)

    return f"""请基于以下品牌信息和用户画像生成用户会在 AI 平台中提出的问题。

## 品牌信息
- 品牌名称: {brand_name}
- 行业: {industry}
- 品牌描述: {description}
- 核心产品: {products}

## 用户画像
{persona_text}

请直接输出 JSON，不要有其他文字。"""


def _build_baseline_system_prompt(platforms: list[str] | tuple[str, ...]) -> str:
    platform_list = "、".join(
        PlatformConstants.PLATFORM_DISPLAY_NAMES.get(platform, platform)
        for platform in platforms
    )
    return f"""你是一个消费者行为研究专家。请基于以下品牌信息和竞品列表，生成模拟用户在 AI 平台（如 {platform_list}）中会提问的行业全景问题。

## 核心规则
1. 问题必须是用户视角，模拟真实消费者的搜索行为
2. 绝对禁止在问题中直接提及目标品牌名称
3. 问题必须覆盖品牌的主要产品领域
4. 包含预算、场景、用途等真实决策因素
5. 问题要口语化，像真实用户会在 AI 平台中输入的
6. 优先生成产品形态、成分、功能、使用场景、价格带等品类层面的比较问题，避免直接列出多个品牌做“谁更好、谁更强、谁更值得买”的比较

## 分类定义
- 品类需求咨询：用户还在理解需求、功效、成分、产品形态或适用人群。
- 场景化选购：用户带着明确生活场景、预算、使用对象或约束条件做选择。
- 品类对比排名：用户比较产品类型、功能路线、成分方案、价位段或购买渠道；不得直接写多个品牌互相 PK。
- 行业趋势探索：用户询问品类趋势、技术变化、消费观念或行业发展。

## 示例
- 品类需求咨询："牙龈容易出血的人，日常口腔护理应该重点看哪些产品功能？"
- 场景化选购："经常出差的人想带便携漱口水，应该优先考虑容量、刺激性还是留香时间？"
- 品类对比排名："含氟牙膏和草本牙膏分别适合什么情况？怎么判断自己该选哪种？"
- 行业趋势探索："为什么现在口腔护理产品越来越强调益生菌、抗糖和修护牙釉质？"
- 反例："舒客、高露洁、云南白药谁更值得买？" 这是品牌互撕式问题，不能用于全景问题。

## 问题分类比例
- 品类需求咨询 (30%)
- 场景化选购 (25%)
- 品类对比排名 (20%)
- 行业趋势探索 (25%)

## 输出格式 (JSON)
请严格输出以下 JSON 格式，不要有其他文字：

{{
  "questions": [
    {{
      "question_id": "bl_001",
      "core_question": "问题文本",
      "category": "品类需求咨询|场景化选购|品类对比排名|行业趋势探索",
      "user_intent": "用户意图",
      "decision_stage": "认知|兴趣|评估|决策",
      "covers_product": "对应的产品线(可选)"
    }}
  ]
}}

## 生成规则
1. 总问题数：10-15 个
2. 不需要指定平台，系统会自动在 {platform_list} 之间轮转分配
3. 问题要覆盖品牌的核心产品线
4. 避免重复或过于笼统的问题
5. 竞品名称最多只作为行业背景提示，不要把多个品牌直接拼成“孰优孰劣式”的题目
6. 目标品牌名称不能出现在任何问题中"""


def _build_baseline_user_content(
    brand_profile: dict,
    competitors: list,
    *,
    topic_keywords: list[str] | None = None,
    topic_description: str | None = None,
) -> str:
    brand_name = brand_profile.get("brand_name", "") or brand_profile.get("name", "")
    industry = brand_profile.get("industry", "")
    description = brand_profile.get("description", "")
    products = ", ".join(brand_profile.get("core_products", []))

    competitor_text = "无"
    if competitors:
        competitor_names = []
        for competitor in competitors:
            if isinstance(competitor, dict):
                competitor_names.append(
                    competitor.get(
                        "name", competitor.get("brand_name", str(competitor))
                    )
                )
            else:
                competitor_names.append(str(competitor))
        competitor_text = ", ".join(competitor_names)

    topic_keywords = topic_keywords or []
    if topic_keywords:
        keyword_text = "、".join(topic_keywords)
        topic_line = (
            f"- 用户原始需求: {topic_description}\n" if topic_description else ""
        )
        brand_constraint = (
            f"- 【强制约束】任何问题都不要直接出现「{brand_name}」这个品牌名\n"
            if brand_name
            else "- 未提供明确目标品牌时，不要编造目标品牌，不要把关键词当作品牌名\n"
        )
        industry_constraint = (
            f"- 已知行业: {industry}\n"
            if industry
            else "- 可以基于关键词推断相关品类/行业，但不要编造具体品牌事实\n"
        )
        product_constraint = (
            f"- 覆盖核心产品线: {products}\n"
            if products
            else "- 覆盖关键词自然延展出的核心需求、技术路线、风险顾虑、使用场景和选购标准\n"
        )
        return f"""请围绕用户给出的主题关键词生成新的全景问题。

## 主题输入
- 主题关键词: {keyword_text}
{topic_line}{industry_constraint}- 已知品牌名称: {brand_name or "无明确品牌"}
- 品牌描述: {description or "无"}
- 核心产品: {products or "无"}

## 竞品列表
{competitor_text}

## 要求
- 生成 10-15 个主题/行业全景问题
- 所有问题必须严格围绕「{keyword_text}」及其自然延展的用户决策场景
{brand_constraint}- 问题要覆盖用户真实关心的功效、原理、安全性、适用人群、预算、效果验证、风险顾虑和趋势判断
{product_constraint}- 问题要口语化，像真实用户会搜索的
- 竞品名称最多只作为行业背景提示，避免把多个品牌直接写成“谁更好、谁更强、谁更值得买”的比较题

请直接输出 JSON，不要有其他文字。"""

    return f"""请为以下品牌生成行业全景问题。

## 品牌信息
- 品牌名称: {brand_name}
- 行业: {industry}
- 品牌描述: {description}
- 核心产品: {products}

## 竞品列表
{competitor_text}

## 要求
- 生成 10-15 个行业全景问题
- 强制约束：所有问题必须严格围绕「{industry}」行业，禁止生成其他行业的问题
- 【强制约束】任何问题都不要直接出现「{brand_name}」这个品牌名
- 覆盖核心产品线: {products}
- 问题要口语化，像真实用户会搜索的
- 竞品名称最多只作为行业背景提示，避免把多个品牌直接写成“谁更好、谁更强、谁更值得买”的比较题
- 优先生成产品形态、成分、功能、使用场景、价格带等品类问题，而不是品牌孰优孰劣题

请直接输出 JSON，不要有其他文字。"""


def validate_baseline_questions(questions: list[dict], brand_name: str) -> None:
    if not questions:
        return
    normalized_brand_name = str(brand_name or "").strip()
    if not normalized_brand_name:
        return

    total = len(questions)
    brand_direct_count = sum(
        1
        for question in questions
        if normalized_brand_name.lower()
        in str(question.get("core_question", "")).lower()
        or question.get("category", "") == "品牌直接问题"
    )
    if brand_direct_count > 0:
        raise ValueError(f"基线问题出现目标品牌直问: {brand_direct_count}/{total}")


def _normalize_brand_term(term: str) -> str:
    return " ".join(str(term or "").strip().lower().split())


def _collect_panorama_brand_terms(brand_name: str, competitors: list[Any]) -> list[str]:
    brand_terms: list[str] = []

    def add_term(raw: str) -> None:
        normalized = _normalize_brand_term(raw)
        if normalized and normalized not in brand_terms:
            brand_terms.append(normalized)

    add_term(brand_name)
    for competitor in competitors:
        if isinstance(competitor, dict):
            add_term(
                str(
                    competitor.get("name")
                    or competitor.get("brand_name")
                    or competitor.get("label")
                    or ""
                )
            )
        else:
            add_term(str(competitor))

    return brand_terms


def _find_panorama_brand_mentions(text: str, brand_terms: list[str]) -> list[str]:
    normalized_text = _normalize_brand_term(text)
    if not normalized_text:
        return []
    return [term for term in brand_terms if term and term in normalized_text]


def sanitize_panorama_questions(
    questions: list[dict],
    brand_name: str,
    competitors: list[Any],
) -> list[dict]:
    if not questions:
        return questions

    brand_terms = _collect_panorama_brand_terms(brand_name, competitors)
    if len(brand_terms) < 2:
        return questions

    filtered_questions: list[dict] = []
    for question in questions:
        question_text = str(
            question.get("core_question") or question.get("question") or ""
        )
        category = str(question.get("category") or "")
        mentions = _find_panorama_brand_mentions(question_text, brand_terms)
        compare_like = category == "品类对比排名" or any(
            cue in question_text for cue in _PANORAMA_COMPARE_CUES
        )
        if compare_like and len(mentions) >= 2:
            continue
        filtered_questions.append(question)

    return filtered_questions or questions


# Backward-compatible alias for callers that want to treat generation as a tool.
QuestionGenerationTool = build_question_generation_messages

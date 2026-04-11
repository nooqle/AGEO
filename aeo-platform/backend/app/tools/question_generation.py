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


def normalize_uploaded_question_payload(
    questions: list[dict],
    *,
    start_index: int = 1,
) -> tuple[list[dict], list[dict]]:
    simulated_questions = []
    flattened_questions = []

    for offset, question in enumerate(questions, start=start_index):
        question_id = question.get("id") or question.get("question_id") or f"upload_q_{offset:03d}"
        category = question.get("category") or "上传问题"
        core_question = question.get("text") or question.get("core_question") or ""
        if not core_question:
            continue
        intent = question.get("intent") or question.get("user_intent") or ""
        stage = question.get("stage") or question.get("decision_stage") or ""

        simulated_questions.append(
            {
                "question_id": question_id,
                "category": category,
                "core_question": core_question,
                "user_intent": intent,
                "decision_stage": stage,
                "source": "uploaded_table",
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


def extract_brand_name(brand_profile: dict, fallback_state: dict[str, Any] | None = None) -> str:
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
    brand_count = sum(1 for question in questions if question["category"] == "品牌直接问题")
    target_count = max(1, int(total * min_brand_ratio + 0.5))

    if brand_count < target_count:
        for question in questions:
            if brand_count >= target_count:
                break
            core = str(question.get("core_question", question.get("question", ""))).lower()
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
) -> tuple[str, str]:
    normalized_identity = _normalize_identity_override(identity)
    if mode == "persona_focused":
        system_prompt, user_content = (
            _build_persona_system_prompt(platforms),
            _build_persona_user_content(brand_profile, selected_personas or []),
        )
    else:
        system_prompt, user_content = (
            _build_baseline_system_prompt(platforms),
            _build_baseline_user_content(brand_profile, competitors or []),
        )
    if normalized_identity:
        system_prompt = _append_identity_override(system_prompt, normalized_identity)
        user_content = _append_identity_context(user_content, normalized_identity)
    return system_prompt, user_content


def _normalize_identity_override(identity: str | None) -> str | None:
    text = str(identity or "").strip()
    return text or None


def _append_identity_override(system_prompt: str, identity: str) -> str:
    return (
        system_prompt
        + "\n\n"
        + dedent(
            f"""
            ## 身份视角覆盖（最高优先级）
            - 本次不要默认按普通消费者视角生成问题。
            - 请明确代入“{identity}”的身份/角色来提问。
            - 问题要体现该身份在真实工作中的职责、关注点、判断标准和约束。
            - 如果该身份与普通消费者口吻冲突，以“{identity}”视角为准。
            """
        ).strip()
    )


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
    return f"""你是一个消费者行为研究专家。请基于以下品牌信息和竞品列表，生成模拟用户在 AI 平台（如 {platform_list}）中会提问的行业基线全景问题。

## 核心规则
1. 问题必须是用户视角，模拟真实消费者的搜索行为
2. 绝对禁止在问题中直接提及目标品牌名称
3. 问题必须覆盖品牌的主要产品领域
4. 包含预算、场景、用途等真实决策因素
5. 问题要口语化，像真实用户会在 AI 平台中输入的
6. 可以出现竞品名称用于对比，但不能出现目标品牌名称

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
5. 竞品名称可以出现在对比类问题中，但目标品牌名称不能出现在任何问题中"""


def _build_baseline_user_content(
    brand_profile: dict,
    competitors: list,
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
                    competitor.get("name", competitor.get("brand_name", str(competitor)))
                )
            else:
                competitor_names.append(str(competitor))
        competitor_text = ", ".join(competitor_names)

    return f"""请为以下品牌生成行业全景基线问题。

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
- 允许出现竞品名称做对比，但不要把目标品牌名写进问题

请直接输出 JSON，不要有其他文字。"""


def validate_baseline_questions(questions: list[dict], brand_name: str) -> None:
    if not questions:
        return

    total = len(questions)
    brand_direct_count = sum(
        1
        for question in questions
        if brand_name.lower() in str(question.get("core_question", "")).lower()
        or question.get("category", "") == "品牌直接问题"
    )
    if brand_direct_count > 0:
        raise ValueError(
            f"基线问题出现目标品牌直问: {brand_direct_count}/{total}"
        )


# Backward-compatible alias for callers that want to treat generation as a tool.
QuestionGenerationTool = build_question_generation_messages

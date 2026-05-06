"""Internal persona-generation primitives used by the A2 workflow stage."""

from __future__ import annotations


def build_persona_generation_messages(
    brand_profile: dict,
    competitors: list,
) -> tuple[str, str]:
    return _get_a2_system_prompt(), _build_a2_user_content(brand_profile, competitors)


def build_persona_retry_messages(
    brand_profile: dict,
    competitors: list,
) -> tuple[str, str]:
    return _get_a2_retry_prompt(), _build_a2_user_content(brand_profile, competitors)


def normalize_persona_payload(data: dict) -> dict:
    normalized = dict(data or {})

    if "userPersonas" in normalized and "user_personas" not in normalized:
        normalized["user_personas"] = normalized["userPersonas"]
    if "marketingScenarios" in normalized and "marketing_scenarios" not in normalized:
        normalized["marketing_scenarios"] = normalized["marketingScenarios"]

    personas = normalized.get("user_personas", [])
    if not isinstance(personas, list):
        normalized["user_personas"] = []
        return normalized

    for persona in personas:
        if not isinstance(persona, dict):
            continue
        if "name" in persona and "persona_name" not in persona:
            persona["persona_name"] = persona["name"]
        if "description" in persona and "persona_description" not in persona:
            persona["persona_description"] = persona["description"]
        if "priority" in persona and "persona_priority" not in persona:
            persona["persona_priority"] = persona["priority"]

    return normalized


def validate_persona_payload(data: dict) -> bool:
    personas = (data or {}).get("user_personas")
    return isinstance(personas, list) and len(personas) > 0


def build_persona_pipeline_data(personas: list[dict]) -> dict:
    """Build 3-column pipeline data from A2 persona output.

    Columns: User Profile -> Usage Scenario -> Brand Interaction Intent
    """
    empty: dict = {
        "columns": [
            {"key": "profile", "label": "用户画像", "color": "purple", "nodes": []},
            {"key": "scenario", "label": "使用场景", "color": "blue", "nodes": []},
            {"key": "intent", "label": "互动意图", "color": "orange", "nodes": []},
        ],
        "edges": [],
    }
    if not personas or not isinstance(personas, list):
        return empty

    profiles = []
    scenarios = []
    intents = []
    edges = []
    intent_dedup: dict[str, str] = {}
    scenario_dedup: dict[str, str] = {}

    for persona_index, persona in enumerate(personas):
        if not isinstance(persona, dict):
            continue
        persona_name = persona.get(
            "persona_name", persona.get("name", f"画像{persona_index + 1}")
        )
        persona_id = f"profile_{persona_index}"

        pain_points = []
        psychographics = persona.get("psychographics", {})
        if isinstance(psychographics, dict):
            pain_points = psychographics.get("pain_points", [])
            if isinstance(pain_points, str):
                pain_points = [pain_points]
            elif not isinstance(pain_points, list):
                pain_points = []

        values_text = (
            psychographics.get("values", "") if isinstance(psychographics, dict) else ""
        )
        demographics = persona.get("demographics", {})
        occupation = (
            demographics.get("occupation", "") if isinstance(demographics, dict) else ""
        )

        profiles.append(
            {
                "id": persona_id,
                "label": persona_name,
                "subtitle": persona.get(
                    "persona_description",
                    persona.get("description", ""),
                ),
                "tags": {
                    "痛点": pain_points[:3] if pain_points else [],
                    "核心诉求": values_text,
                    "职业": occupation,
                },
                "priority": persona.get(
                    "persona_priority",
                    persona.get("priority", ""),
                ),
            }
        )

        usage_scenarios = persona.get("usage_scenarios") or []
        if isinstance(usage_scenarios, dict):
            usage_scenarios = [usage_scenarios]
        elif not isinstance(usage_scenarios, list):
            usage_scenarios = []

        for scenario_index, scenario in enumerate(usage_scenarios):
            if not isinstance(scenario, dict):
                continue
            scenario_name = scenario.get("scenario_name", f"场景{scenario_index + 1}")
            scenario_description = scenario.get("scenario_description", "")

            if scenario_name in scenario_dedup:
                scenario_id = scenario_dedup[scenario_name]
            else:
                scenario_id = f"scenario_{len(scenario_dedup)}"
                scenario_dedup[scenario_name] = scenario_id
                scenarios.append(
                    {
                        "id": scenario_id,
                        "label": scenario_name,
                        "tags": {
                            "任务目标": scenario_description,
                        },
                    }
                )

            edges.append({"source": persona_id, "target": scenario_id})

            interaction_intents = scenario.get(
                "brand_interaction_intents",
                scenario.get("likely_search_intents", []),
            )
            if isinstance(interaction_intents, str):
                interaction_intents = [interaction_intents]
            elif not isinstance(interaction_intents, list):
                interaction_intents = []

            for intent_text in interaction_intents:
                if not intent_text:
                    continue
                if intent_text not in intent_dedup:
                    intent_id = f"intent_{len(intent_dedup)}"
                    intent_dedup[intent_text] = intent_id
                    intents.append(
                        {
                            "id": intent_id,
                            "label": intent_text,
                        }
                    )
                edges.append(
                    {"source": scenario_id, "target": intent_dedup[intent_text]}
                )

    return {
        "columns": [
            {
                "key": "profile",
                "label": "用户画像",
                "color": "purple",
                "nodes": profiles,
            },
            {
                "key": "scenario",
                "label": "使用场景",
                "color": "blue",
                "nodes": scenarios,
            },
            {"key": "intent", "label": "互动意图", "color": "orange", "nodes": intents},
        ],
        "edges": edges,
    }


def _get_a2_system_prompt() -> str:
    return """你是一个资深的消费者洞察专家。根据品牌档案信息，生成 4 个差异化的用户画像。

## 输出格式
请严格按照以下 JSON 格式输出（不要添加任何额外字段）：

{
  "brand_summary": {
    "brand_name": "品牌名",
    "core_value": "品牌核心价值（一句话）",
    "category": "主要品类"
  },
  "user_personas": [
    {
      "name": "画像昵称（如：精致妈妈、职场新贵）",
      "description": "一句话概括该人群（30字以内）",
      "demographics": {
        "age_range": "25-35",
        "gender": "女性为主",
        "city_tier": "一二线城市",
        "income": "月入1.5-3万",
        "occupation": "互联网/金融从业者"
      },
      "psychographics": {
        "lifestyle": "注重品质生活，追求效率与美感",
        "values": "品质优先，愿意为好产品付溢价",
        "pain_points": ["选择困难", "信息过载", "品质参差不齐"]
      },
      "priority": "核心人群/增长人群/机会人群",
      "key_questions": ["这类用户可能在 AI 平台中问的问题1", "问题2", "问题3"],
      "usage_scenarios": [
        {
          "scenario_name": "场景名",
          "scenario_description": "该人群触发品牌需求的具体情境（30-50字）",
          "brand_interaction_intents": ["用户在此场景下与品牌互动的意图1（如：了解产品、比较方案、寻求建议、尝鲜体验、复购囤货）", "意图2"],
          "relevant_competitors": ["此场景下用户可能对比的竞品1", "竞品2"]
        }
      ]
    }
  ],
  "marketing_scenarios": [
    "场景1描述（包含人群、时间、地点、触发需求的情境，50-80字）",
    "场景2描述",
    "场景3描述"
  ]
}

## 画像要求
- 生成 4 个画像，覆盖：核心人群（2个）、增长人群（1个）、机会人群（1个）
- description 字段为一句话概括（30字以内），详细人口统计放在 demographics 中
- demographics 必须包含 age_range, gender, city_tier, income, occupation
- psychographics 必须包含 lifestyle, values, pain_points（数组）
- 每个画像的 key_questions 要贴合真实用户在 AI 平台中的提问习惯
- 每个画像的 priority 必须是 "核心人群"、"增长人群"、"机会人群" 之一
- 每个画像包含 2-3 个 usage_scenarios
- 每个 usage_scenario 必须包含 brand_interaction_intents（2-3个，描述用户与品牌/产品互动的意图，如咨询、比较、试用、购买、复购）和 relevant_competitors（1-3个）
- marketing_scenarios 生成 4-6 个场景

⚠️ 重要：直接以 { 开头输出 JSON，不要有任何解释或 Markdown 标记。"""


def _get_a2_retry_prompt() -> str:
    return """根据品牌信息，生成 4 个用户画像。直接输出以下 JSON 格式，不要有其他文字：

{
  "user_personas": [
    {"name": "画像名称", "description": "一句话概括（30字以内）", "demographics": {"age_range": "25-35", "gender": "女性为主", "city_tier": "一二线", "income": "月入1-2万", "occupation": "职业"}, "psychographics": {"lifestyle": "生活方式", "values": "价值观", "pain_points": ["痛点1"]}, "priority": "核心人群", "key_questions": ["问题1", "问题2"], "usage_scenarios": [{"scenario_name": "场景名", "scenario_description": "场景描述", "brand_interaction_intents": ["了解产品"], "relevant_competitors": ["竞品1"]}]},
    {"name": "画像名称", "description": "一句话概括", "demographics": {"age_range": "30-45", "gender": "男性为主", "city_tier": "一二线", "income": "月入2-5万", "occupation": "职业"}, "psychographics": {"lifestyle": "生活方式", "values": "价值观", "pain_points": ["痛点1"]}, "priority": "核心人群", "key_questions": ["问题1", "问题2"], "usage_scenarios": [{"scenario_name": "场景名", "scenario_description": "场景描述", "brand_interaction_intents": ["比较方案"], "relevant_competitors": ["竞品1"]}]},
    {"name": "画像名称", "description": "一句话概括", "demographics": {"age_range": "20-30", "gender": "不限", "city_tier": "二三线", "income": "月入0.5-1万", "occupation": "职业"}, "psychographics": {"lifestyle": "生活方式", "values": "价值观", "pain_points": ["痛点1"]}, "priority": "增长人群", "key_questions": ["问题1", "问题2"], "usage_scenarios": [{"scenario_name": "场景名", "scenario_description": "场景描述", "brand_interaction_intents": ["尝鲜体验"], "relevant_competitors": ["竞品1"]}]},
    {"name": "画像名称", "description": "一句话概括", "demographics": {"age_range": "35-50", "gender": "不限", "city_tier": "各线", "income": "月入1-3万", "occupation": "职业"}, "psychographics": {"lifestyle": "生活方式", "values": "价值观", "pain_points": ["痛点1"]}, "priority": "机会人群", "key_questions": ["问题1", "问题2"], "usage_scenarios": [{"scenario_name": "场景名", "scenario_description": "场景描述", "brand_interaction_intents": ["寻求建议"], "relevant_competitors": ["竞品1"]}]}
  ],
  "marketing_scenarios": ["场景1", "场景2", "场景3"]
}"""


def _coerce_text_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _coerce_competitor_list(competitors) -> list[dict]:
    if not isinstance(competitors, list):
        return []

    normalized: list[dict] = []
    for competitor in competitors:
        if not isinstance(competitor, dict):
            continue
        normalized.append(competitor)
    return normalized


def _build_a2_user_content(brand_profile: dict, competitors: list) -> str:
    if not isinstance(brand_profile, dict):
        brand_profile = {}

    competitors = _coerce_competitor_list(competitors)
    core_products = _coerce_text_list(brand_profile.get("core_products"))
    competitor_names = _coerce_text_list(
        [competitor.get("name", "") for competitor in competitors[:5]]
    )

    return f"""请基于以下品牌档案信息，生成 4 组【用户画像 + 使用场景 + 营销痛点】：

## 品牌档案
- 品牌中文名：{brand_profile.get('brand_name', '')}
- 品牌英文名：{brand_profile.get('brand_name_en', '')}
- 成立年份：{brand_profile.get('founded_year', '')}
- 核心领域：{brand_profile.get('industry', '')}
- 核心产品：{', '.join(core_products)}
- 品牌理念：{brand_profile.get('brand_positioning', '')}
- 品牌描述：{brand_profile.get('description', '')}
- 目标市场：{brand_profile.get('target_audience', '')}
- 价格定位：{brand_profile.get('price_positioning', '')}

## 竞争环境参考
- 主要竞品：{', '.join(competitor_names)}
- 市场竞争格局：{len(competitors)} 个主要竞品
"""


PersonaGenerationTool = build_persona_generation_messages

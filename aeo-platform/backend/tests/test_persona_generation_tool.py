from __future__ import annotations

from app.tools.persona_generation import (
    PersonaGenerationTool,
    build_persona_pipeline_data,
    build_persona_retry_messages,
    normalize_persona_payload,
    validate_persona_payload,
)


def test_persona_generation_tool_builds_prompt_and_user_content():
    system_prompt, user_content = PersonaGenerationTool(
        {
            "brand_name": "观夏",
            "industry": "香氛",
            "core_products": ["香薰", "香水"],
            "brand_positioning": "东方香氛品牌",
        },
        [{"name": "闻献"}, {"name": "野兽派"}],
    )
    retry_prompt, retry_user_content = build_persona_retry_messages(
        {"brand_name": "观夏", "industry": "香氛"},
        [{"name": "闻献"}],
    )

    assert "生成 4 个差异化的用户画像" in system_prompt
    assert "品牌中文名：观夏" in user_content
    assert "主要竞品：闻献, 野兽派" in user_content
    assert "直接输出以下 JSON 格式" in retry_prompt
    assert "品牌中文名：观夏" in retry_user_content


def test_normalize_persona_payload_adds_downstream_compatible_fields():
    payload = normalize_persona_payload(
        {
            "userPersonas": [
                {
                    "name": "精致妈妈",
                    "description": "关注家庭品质",
                    "priority": "核心人群",
                }
            ],
            "marketingScenarios": ["家庭囤货"],
        }
    )

    persona = payload["user_personas"][0]
    assert validate_persona_payload(payload)
    assert payload["marketing_scenarios"] == ["家庭囤货"]
    assert persona["persona_name"] == "精致妈妈"
    assert persona["persona_description"] == "关注家庭品质"
    assert persona["persona_priority"] == "核心人群"


def test_build_persona_pipeline_data_maps_profile_scenario_and_intent():
    pipeline = build_persona_pipeline_data(
        [
            {
                "persona_name": "精致妈妈",
                "persona_description": "关注家庭健康",
                "persona_priority": "核心人群",
                "demographics": {"occupation": "家庭决策者"},
                "psychographics": {
                    "values": "安全优先",
                    "pain_points": ["选择困难"],
                },
                "usage_scenarios": [
                    {
                        "scenario_name": "家庭囤货",
                        "scenario_description": "给全家选择长期用品",
                        "brand_interaction_intents": ["比较方案", "了解产品"],
                    }
                ],
            }
        ]
    )

    columns = {column["key"]: column for column in pipeline["columns"]}
    assert columns["profile"]["nodes"][0]["label"] == "精致妈妈"
    assert columns["scenario"]["nodes"][0]["label"] == "家庭囤货"
    assert {node["label"] for node in columns["intent"]["nodes"]} == {
        "比较方案",
        "了解产品",
    }
    assert pipeline["edges"] == [
        {"source": "profile_0", "target": "scenario_0"},
        {"source": "scenario_0", "target": "intent_0"},
        {"source": "scenario_0", "target": "intent_1"},
    ]

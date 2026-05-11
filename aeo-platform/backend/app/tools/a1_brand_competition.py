"""A1 Tool - Brand Competition Analysis.

Pure function implementation for brand profile and competitor analysis.
This replaces the old class-based Tool with stateless functions.
"""

from time import perf_counter
from typing import Any

from app.core.llm.task_routing import get_a1_llm_model
from app.core.utils import (
    extract_json_from_content,
    load_prompt_template,
    render_prompt,
)
from app.services.llm_usage_service import record_llm_usage_async
from app.tools.a1_evidence import (
    build_a1_web_search_tool,
    normalize_evidence_sources,
)


async def analyze_brand_competition(
    brand_name: str,
    official_website: str | None = None,
    industry_hint: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    step: str = "a1_tool",
    step_name: str = "品牌竞品分析",
) -> dict[str, Any]:
    """Analyze brand profile and identify competitors.

    Args:
        brand_name: Brand name to analyze
        official_website: Optional official website
        industry_hint: Optional industry hint

    Returns:
        Dictionary containing brand_profile, competitors, and competitive_landscape
    """
    # Load system prompt
    try:
        system_prompt = load_prompt_template("brand_competition_agent")
    except FileNotFoundError:
        system_prompt = _get_fallback_prompt()

    # Build user content
    user_content = render_prompt(
        "请分析以下品牌：\n\n"
        "品牌名称: {{brand_name}}\n"
        "{% if official_website %}官网: {{official_website}}\n{% endif %}"
        "{% if industry_hint %}行业提示: {{industry_hint}}\n{% endif %}\n"
        "任务: 请分析这个品牌，收集其档案信息，并识别8-12个主要竞品。",
        {
            "brand_name": brand_name,
            "official_website": official_website,
            "industry_hint": industry_hint,
        },
    )

    # Call LLM
    model = get_a1_llm_model()
    started_at = perf_counter()
    response = await model.async_call(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        tools=[build_a1_web_search_tool()],
    )
    latency_ms = response.latency_ms or max(int((perf_counter() - started_at) * 1000), 0)
    await record_llm_usage_async(
        session_id=session_id,
        task_id=task_id,
        skill_key=None,
        step=step,
        step_name=step_name,
        model=model,
        usage=response.usage,
        latency_ms=latency_ms,
        extra_metadata={
            "streaming": False,
            "message_count": 2,
            "tool_entrypoint": "a1_brand_competition",
        },
    )

    # Parse response
    content = response.content if hasattr(response, "content") else str(response)
    data = extract_json_from_content(content)

    if not data:
        raise ValueError("Failed to parse LLM response as JSON")

    # Validate required fields
    if "brand_profile" not in data or "competitors" not in data:
        raise ValueError(
            "Response missing required fields: brand_profile or competitors"
        )

    return {
        "brand_profile": data["brand_profile"],
        "competitors": data["competitors"],
        "competitive_landscape": data.get("competitive_landscape", {}),
        "evidence_sources": normalize_evidence_sources(
            data.get("evidence_sources")
        ),
    }


def _get_fallback_prompt() -> str:
    """Fallback system prompt for A1."""
    return """你是 Specta AI 平台的品牌竞品分析专家。你的任务是通过搜索和分析，为目标品牌建立完整的品牌档案，并识别出 8-12 个主要竞品。

## 核心职责

1. **品牌档案收集**：收集目标品牌的基础信息、核心产品、品牌定位等
2. **行业识别**：准确识别品牌所属行业和市场定位
3. **竞品识别**：找出 8-12 个相关竞品
4. **竞争格局分析**：分析整体市场竞争态势

## 输出格式

你必须以 JSON 格式输出分析结果：

{
  "brand_profile": {
    "brand_name": "品牌中文名",
    "brand_name_en": "品牌英文名",
    "official_website": "官网地址",
    "industry": "所属行业",
    "description": "品牌描述",
    "core_products": ["产品1", "产品2"],
    "brand_keywords": ["关键词1", "关键词2"],
    "brand_positioning": "品牌定位",
    "target_audience": "目标受众",
    "founded_year": "成立年份",
    "price_positioning": "价格定位"
  },
  "competitors": [
    {
      "name": "竞品名称",
      "name_en": "竞品英文名",
      "website": "竞品官网",
      "description": "竞品描述",
      "relevance_score": 8,
      "competition_type": "直接竞争/间接竞争/潜在竞争",
      "core_products": ["产品1"],
      "competitive_advantage": "核心优势"
    }
  ],
  "competitive_landscape": {
    "market_overview": "市场整体概况",
    "competition_intensity": "高/中/低",
    "key_battlegrounds": ["竞争维度1", "竞争维度2"]
  },
  "evidence_sources": [
    {
      "title": "来源标题",
      "link": "来源链接",
      "media": "媒体/站点名称",
      "publish_date": "发布日期",
      "refer": "引用编号",
      "usage": "用于核验官网/核心产品/竞品"
    }
  ]
}

⚠️ 重要：直接以 { 开头输出 JSON，不要有任何解释或 Markdown 标记。"""


# Backward compatibility alias
BrandCompetitionTool = analyze_brand_competition

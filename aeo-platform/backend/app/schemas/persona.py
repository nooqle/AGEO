"""Persona-related Pydantic schemas."""

from typing import List

from pydantic import BaseModel, Field

from app.schemas.brand import BrandProfile, Competitor


class WeaknessArea(BaseModel):
    """Weakness area from benchmark analysis.

    Used to prioritize persona generation.
    """

    area: str = Field(..., description="薄弱环节名称")
    description: str = Field(..., description="环节描述")
    severity: str = Field(..., description="严重程度：高/中/低")


class Demographics(BaseModel):
    """Demographic information for a persona."""

    age_range: str = Field(..., description="年龄区间，如 '25-35岁'")
    gender: str = Field(..., description="性别倾向，如 '女性为主'")
    city_tier: str = Field(..., description="城市层级，如 '一二线城市'")
    occupation: str = Field(..., description="典型职业")
    income_level: str = Field(..., description="收入水平")
    family_status: str = Field(..., description="家庭状态")


class Psychographics(BaseModel):
    """Psychographic information for a persona."""

    lifestyle: str = Field(..., description="生活方式描述")
    values: List[str] = Field(default_factory=list, description="核心价值观")
    interests: List[str] = Field(default_factory=list, description="兴趣爱好")
    media_habits: List[str] = Field(default_factory=list, description="常用媒体/平台")
    consumption_attitude: str = Field(..., description="消费态度描述")


class BrandRelationship(BaseModel):
    """Brand relationship information for a persona."""

    awareness_level: str = Field(
        ...,
        description="认知程度：陌生/听过/了解/使用过/忠实用户",
    )
    purchase_motivation: str = Field(..., description="购买动机")
    decision_factors: List[str] = Field(default_factory=list, description="决策因素")
    price_sensitivity: str = Field(..., description="价格敏感度：高/中/低")


class UsageScenario(BaseModel):
    """Usage scenario for a persona."""

    scenario_id: str = Field(..., description="场景ID，如 'S01'")
    scenario_name: str = Field(..., description="场景名称")
    scenario_description: str = Field(..., description="场景详细描述（50-80字）")
    time_context: str = Field(..., description="时间情境")
    space_context: str = Field(..., description="空间情境")
    emotional_state: str = Field(..., description="情绪状态")
    need_trigger: str = Field(..., description="需求触发点")
    product_role: str = Field(..., description="产品在场景中的角色")


class MarketingPainPoint(BaseModel):
    """Marketing pain point for a persona."""

    pain_point_id: str = Field(..., description="痛点ID，如 'PP01'")
    pain_point_category: str = Field(
        ...,
        description="痛点类别：认知层/信任层/决策层/行动层/体验层",
    )
    pain_point_description: str = Field(..., description="痛点详细描述")
    user_inner_voice: str = Field(..., description="用户内心OS（第一人称）")
    barrier_to_conversion: str = Field(..., description="转化障碍点")
    marketing_opportunity: str = Field(..., description="营销机会点")


class UserPersona(BaseModel):
    """User persona definition.

    Complete user persona with demographics, psychographics,
    scenarios, and pain points.
    """

    # Basic info
    persona_id: str = Field(..., description="画像ID，如 'P01'")
    persona_name: str = Field(..., description="画像昵称，如 '都市疗愈系白领'")
    emoji: str = Field(..., description="代表emoji，如 '🧘'")
    persona_description: str = Field(..., description="一句话描述")

    # Detailed info
    demographics: Demographics = Field(..., description="人口统计信息")
    psychographics: Psychographics = Field(..., description="心理特征信息")
    brand_relationship: BrandRelationship = Field(..., description="品牌关系")

    # Scenarios and pain points
    usage_scenarios: List[UsageScenario] = Field(
        ...,
        description="使用场景列表（至少2个）",
        min_length=2,
    )
    marketing_pain_points: List[MarketingPainPoint] = Field(
        ...,
        description="营销痛点列表（至少2个）",
        min_length=2,
    )

    # Priority and recommendation
    persona_priority: str = Field(
        ...,
        description="人群优先级：核心人群/重点人群/机会人群",
    )
    estimated_market_size: str = Field(..., description="预估市场规模描述")
    acquisition_difficulty: str = Field(..., description="获客难度：高/中/低")

    # Recommendation related
    recommendation_score: int = Field(
        ...,
        description="推荐优先级（1-5分）",
        ge=1,
        le=5,
    )
    related_weakness: str | None = Field(
        None,
        description="关联的薄弱环节",
    )
    recommendation_reason: str | None = Field(
        None,
        description="推荐理由",
    )


class CrossPersonaInsights(BaseModel):
    """Cross-persona insights."""

    common_scenarios: List[str] = Field(
        default_factory=list, description="跨人群共性场景"
    )
    common_pain_points: List[str] = Field(
        default_factory=list, description="跨人群共性痛点"
    )
    differentiation_opportunities: List[str] = Field(
        default_factory=list,
        description="差异化营销机会",
    )


class BrandSummary(BaseModel):
    """Brand summary for persona generation context."""

    brand_name: str = Field(..., description="品牌名")
    core_value_proposition: str = Field(..., description="核心价值主张")
    primary_category: str = Field(..., description="主要品类")
    price_tier: str = Field(..., description="价格带")


class PersonaGenerationOutput(BaseModel):
    """Output schema for Marketing Persona Agent.

    Complete output including brand summary, personas, and cross-persona insights.
    """

    brand_summary: BrandSummary = Field(..., description="品牌摘要")
    user_personas: List[UserPersona] = Field(
        ...,
        description="用户画像列表（6-8个）",
        min_length=6,
        max_length=8,
    )
    cross_persona_insights: CrossPersonaInsights = Field(
        ...,
        description="跨人群洞察",
    )
    generation_summary: str = Field(..., description="生成总结")


class PersonaGenerationInput(BaseModel):
    """Input schema for Marketing Persona Agent.

    Requires brand profile and competitors from previous agent.
    """

    brand_profile: BrandProfile = Field(..., description="品牌档案")
    competitors: List[Competitor] = Field(..., description="竞品列表")
    weakness_areas: List[WeaknessArea] = Field(
        default_factory=list,
        description="薄弱环节列表（可选，来自基准分析）",
    )


class PersonaGenerationResult(BaseModel):
    """Complete result including output and metadata."""

    success: bool = Field(..., description="是否成功")
    output: PersonaGenerationOutput | None = Field(None, description="生成输出")
    raw_content: str | None = Field(None, description="原始模型输出")
    error_message: str | None = Field(None, description="错误信息")
    session_id: str | None = Field(None, description="关联的会话ID")
    persona_set_id: str | None = Field(None, description="保存到数据库后的画像集ID")

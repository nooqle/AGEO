"""Brand-related Pydantic schemas."""

from typing import List

from pydantic import BaseModel, Field, field_validator


class BrandCompetitionInput(BaseModel):
    """Input schema for Brand Competition Agent.

    Attributes:
        brand_name: Brand name (required)
        official_website: Official website URL (optional)
        industry_hint: Industry hint to help identify the brand (optional)
    """

    brand_name: str = Field(
        ...,
        description="品牌名称",
        min_length=1,
        max_length=100,
    )
    official_website: str | None = Field(
        None,
        description="品牌官网地址（可选，Agent 可自行识别）",
    )
    industry_hint: str | None = Field(
        None,
        description="行业提示，帮助 Agent 识别品牌所属行业（可选）",
    )


class BrandProfile(BaseModel):
    """Brand profile information.

    Contains basic information about the brand.
    """

    brand_name: str = Field(..., description="品牌中文名")
    brand_name_en: str | None = Field(None, description="品牌英文名")
    official_website: str | None = Field(None, description="品牌官网")
    industry: str = Field(..., description="所属行业")
    description: str = Field(..., description="品牌描述（100-200字）")
    core_products: List[str] = Field(
        default_factory=list,
        description="核心产品列表",
    )
    brand_keywords: List[str] = Field(
        default_factory=list,
        description="品牌关键词",
    )
    brand_positioning: str = Field(..., description="品牌定位")
    target_audience: str = Field(..., description="目标受众")
    founded_year: str | int | None = Field(None, description="成立年份")
    price_positioning: str | None = Field(None, description="价格定位")

    @field_validator("founded_year", mode="before")
    @classmethod
    def convert_founded_year(cls, v):
        """Convert founded_year to string, handling both str and int inputs."""
        if v is None:
            return None
        return str(v)


class Competitor(BaseModel):
    """Competitor information.

    Contains information about a single competitor.
    """

    name: str = Field(..., description="竞品名称")
    name_en: str | None = Field(None, description="竞品英文名")
    website: str | None = Field(None, description="竞品官网")
    description: str = Field(..., description="竞品描述")
    relevance_score: int = Field(
        ...,
        description="相关度评分（1-10）",
        ge=1,
        le=10,
    )
    competition_type: str = Field(
        ...,
        description="竞争类型：直接竞争/间接竞争/潜在竞争",
    )
    core_products: List[str] = Field(
        default_factory=list,
        description="竞品核心产品",
    )
    competitive_advantage: str | None = Field(
        None,
        description="核心竞争优势",
    )


class CompetitiveLandscape(BaseModel):
    """Competitive landscape analysis.

    Contains overall market analysis.
    """

    market_overview: str = Field(..., description="市场整体概况（100字左右）")
    competition_intensity: str = Field(
        ...,
        description="竞争激烈程度：高/中/低",
    )
    key_battlegrounds: List[str] = Field(
        default_factory=list,
        description="主要竞争维度",
    )


class BrandCompetitionOutput(BaseModel):
    """Output schema for Brand Competition Agent.

    Complete output including brand profile, competitors, and analysis.
    """

    brand_profile: BrandProfile = Field(..., description="品牌档案")
    competitors: List[Competitor] = Field(
        ...,
        description="竞品列表（8-12个）",
        min_length=8,
        max_length=12,
    )
    competitive_landscape: CompetitiveLandscape = Field(
        ...,
        description="竞争格局分析",
    )
    analysis_summary: str = Field(..., description="分析总结")


class BrandCompetitionResult(BaseModel):
    """Complete result including output and metadata.

    This is the actual return type from the Agent.
    """

    success: bool = Field(..., description="是否成功")
    output: BrandCompetitionOutput | None = Field(
        None,
        description="分析输出",
    )
    raw_content: str | None = Field(
        None,
        description="原始模型输出",
    )
    error_message: str | None = Field(
        None,
        description="错误信息",
    )
    session_id: str | None = Field(
        None,
        description="关联的会话ID",
    )
    brand_profile_id: str | None = Field(
        None,
        description="保存到数据库后的品牌档案ID",
    )

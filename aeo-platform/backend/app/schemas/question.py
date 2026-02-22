"""Question simulation schemas."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.brand import BrandProfile, Competitor
from app.schemas.persona import UserPersona


class QuestionVariant(BaseModel):
    """A variant of a question with different tone/style."""

    variant_type: str = Field(..., description="变体类型：直接型/场景型/对比型/深入型")
    question_text: str = Field(..., description="问题文本")
    tone: str = Field(..., description="口吻特点")
    persona_fit: str | None = Field(
        None, description="如何体现画像特征（persona_focus模式）"
    )


class SimulatedQuestion(BaseModel):
    """A simulated user question.

    Represents a question that a real user might ask an AI search engine.
    """

    # Basic info
    question_id: str = Field(..., description="问题ID，如 'Q01'")
    question_text: str = Field(..., description="问题文本")
    category: str = Field(..., description="问题类别")
    subcategory: str | None = Field(None, description="子分类")
    intent: str = Field(..., description="用户意图")
    decision_stage: str = Field(..., description="决策阶段：认知/兴趣/决策/行动")

    # Keywords and SEO
    keywords: list[str] = Field(default_factory=list, description="关键词")
    seo_keywords: list[str] = Field(default_factory=list, description="SEO关键词")

    # Variants
    is_variant: bool = Field(False, description="是否为变体")
    variant_of: str | None = Field(None, description="原问题ID（如果是变体）")
    variants: list[QuestionVariant] = Field(
        default_factory=list, description="问题变体列表"
    )

    # Persona relation (for persona_focus mode)
    persona_id: str | None = Field(None, description="关联画像ID")
    linked_scenario: str | None = Field(None, description="关联场景")
    linked_pain_point: str | None = Field(None, description="关联痛点")
    user_inner_context: str | None = Field(None, description="用户内心背景/潜台词")

    # Brand info
    involves_brands: list[str] = Field(default_factory=list, description="涉及的品牌")

    # Answer guidance
    ideal_answer_should_mention: str | list[str] | None = Field(
        None, description="理想回答应提及的要点"
    )
    ideal_answer_should_address: str | list[str] | None = Field(
        None, description="理想回答应解决的问题"
    )


class QuestionStatistics(BaseModel):
    """Statistics for generated questions."""

    total_questions: int = Field(..., description="总问题数")
    by_category: dict[str, int] = Field(default_factory=dict, description="按类别统计")
    by_decision_stage: dict[str, int] = Field(
        default_factory=dict, description="按决策阶段统计"
    )
    by_persona: dict[str, int] | None = Field(
        None, description="按画像统计（persona_focus模式）"
    )
    variants_count: int = Field(..., description="变体数量")


class QuestionSimulationInput(BaseModel):
    """Input for question simulation.

    Supports two modes:
    - baseline: Generate questions covering 5 categories
    - persona_focus: Generate questions for specific personas
    """

    brand_profile: BrandProfile = Field(..., description="品牌档案")
    competitors: list[Competitor] = Field(..., description="竞品列表")
    mode: Literal["baseline", "persona_focus"] = Field(
        ...,
        description="生成模式：baseline 或 persona_focus",
    )
    personas: list[UserPersona] | None = Field(
        None,
        description="用户画像列表（persona_focus模式必填）",
    )
    selected_persona_ids: list[str] | None = Field(
        None,
        description="选中的画像ID列表（persona_focus模式）",
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "brand_profile": {"brand_name": "观夏", "industry": "香氛"},
                    "competitors": [],
                    "mode": "baseline",
                }
            ]
        }


class QuestionSimulationOutput(BaseModel):
    """Output from question simulation."""

    generation_mode: str = Field(..., description="生成模式")
    generation_context: dict[str, Any] = Field(
        default_factory=dict,
        description="生成上下文信息",
    )
    questions: list[SimulatedQuestion] = Field(..., description="模拟问题列表")
    statistics: QuestionStatistics = Field(..., description="统计信息")

    # Baseline mode specific
    brand_mention_analysis: dict[str, list[str]] | None = Field(
        None,
        description="品牌提及分析（baseline模式）",
    )

    # Persona focus mode specific
    persona_language_profile: dict[str, Any] | None = Field(
        None,
        description="画像语言特征（persona_focus模式）",
    )
    persona_insight_summary: dict[str, list[str]] | None = Field(
        None,
        description="画像洞察总结（persona_focus模式）",
    )


class QuestionSimulationResult(BaseModel):
    """Complete result including output and metadata."""

    success: bool = Field(..., description="是否成功")
    output: QuestionSimulationOutput | None = Field(None, description="生成输出")
    raw_content: str | None = Field(None, description="原始模型输出")
    error_message: str | None = Field(None, description="错误信息")
    session_id: str | None = Field(None, description="关联的会话ID")
    simulation_id: str | None = Field(None, description="保存到数据库后的模拟ID")

    # Mode specific metadata
    mode: Literal["baseline", "persona_focus"] | None = Field(
        None, description="使用的模式"
    )
    processed_persona_ids: list[str] | None = Field(
        None,
        description="处理的画像ID列表（persona_focus模式）",
    )

"""Analytics schemas for AEO data analysis."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.brand import BrandProfile, Competitor
from app.schemas.fetch import FetchResult
from app.schemas.persona import UserPersona


class ReportType(str, Enum):
    """Types of analysis reports."""

    BASELINE = "baseline"
    PRECISION = "precision"
    COMPARISON = "comparison"
    MONITORING = "monitoring"


class CategoryMetric(BaseModel):
    """Metrics for a specific question category."""

    category: str = Field(..., description="类别名称")
    mention_rate: float = Field(..., description="提及率 (%)")
    positive_rate: float = Field(..., description="正向情感率 (%)")
    question_count: int = Field(..., description="问题数量")
    weakness_flag: bool = Field(False, description="是否为薄弱环节")
    gap_vs_average: float = Field(0.0, description="与平均值的差距")


class PlatformMetric(BaseModel):
    """Metrics for a specific platform."""

    platform: str = Field(..., description="平台名称")
    bwvs_score: float = Field(..., description="BWVS 得分")
    bwvs_max: float = Field(7.5, description="BWVS 满分")
    bwvs_percentage: float = Field(..., description="BWVS 得分率 (%)")
    mention_rate: float = Field(..., description="提及率 (%)")
    positive_rate: float = Field(..., description="正向情感率 (%)")
    official_share: float = Field(..., description="官网引用率 (%)")
    rank: int = Field(..., description="排名")


class SentimentDistribution(BaseModel):
    """Sentiment distribution metrics."""

    positive: float = Field(..., description="正向占比 (%)")
    neutral: float = Field(..., description="中性占比 (%)")
    negative: float = Field(..., description="负向占比 (%)")
    net_sentiment_score: float = Field(..., description="净情感得分")


class CitationMetrics(BaseModel):
    """Citation-related metrics."""

    total_citations: int = Field(..., description="总引用数")
    unique_domains: int = Field(..., description="独立域名数")
    official_domain_share: float = Field(..., description="官网引用占比 (%)")
    authority_matrix_share: float = Field(..., description="权威矩阵占比 (%)")
    distribution: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="引用来源分布",
    )
    top_domains: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Top 引用域名",
    )


class CompetitiveBrandMetrics(BaseModel):
    """Metrics for a brand in competitive analysis."""

    rank: int = Field(..., description="排名")
    brand: str = Field(..., description="品牌名称")
    bwvs: float = Field(..., description="BWVS 得分")
    mention_rate: float = Field(..., description="提及率 (%)")
    positive_sentiment: float = Field(..., description="正向情感率 (%)")
    official_share: float = Field(..., description="官网引用率 (%)")


class HeadToHeadAnalysis(BaseModel):
    """Head-to-head comparison between two brands."""

    total_comparisons: int = Field(..., description="总对比次数")
    brand_a_wins: int = Field(..., description="品牌A胜场")
    brand_b_wins: int = Field(..., description="品牌B胜场")
    ties: int = Field(..., description="平局")
    brand_a_win_rate: float = Field(..., description="品牌A胜率 (%)")
    advantage_areas: list[str] = Field(default_factory=list, description="优势领域")
    disadvantage_areas: list[str] = Field(default_factory=list, description="劣势领域")


class AnalysisMetrics(BaseModel):
    """Complete analysis metrics."""

    # BWVS
    bwvs_total: float = Field(..., description="BWVS 总得分")
    bwvs_max: float = Field(30.0, description="BWVS 满分")
    bwvs_percentage: float = Field(..., description="BWVS 得分率 (%)")
    bwvs_by_platform: dict[str, PlatformMetric] = Field(
        default_factory=dict,
        description="各平台 BWVS",
    )
    bwvs_by_category: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="各类别 BWVS",
    )

    # Mention Rate
    mention_rate_overall: float = Field(..., description="整体提及率 (%)")
    mention_rate_by_platform: dict[str, float] = Field(
        default_factory=dict,
        description="各平台提及率",
    )
    mention_rate_by_category: dict[str, float] = Field(
        default_factory=dict,
        description="各类别提及率",
    )
    mention_rate_by_stage: dict[str, float] = Field(
        default_factory=dict,
        description="各决策阶段提及率",
    )

    # Sentiment
    sentiment_overall: SentimentDistribution = Field(
        ...,
        description="整体情感分布",
    )
    sentiment_by_platform: dict[str, SentimentDistribution] = Field(
        default_factory=dict,
        description="各平台情感分布",
    )

    # Accuracy
    accuracy_overall: float = Field(..., description="整体准确率 (%)")

    # Citations
    citation_metrics: CitationMetrics = Field(..., description="引用指标")

    # Category metrics
    category_metrics: dict[str, CategoryMetric] = Field(
        default_factory=dict,
        description="分类指标",
    )


class WeaknessArea(BaseModel):
    """Identified weakness area."""

    category: str = Field(..., description="薄弱环节类别")
    current_value: float = Field(..., description="当前值")
    benchmark_value: float = Field(..., description="基准值")
    gap: float = Field(..., description="差距")
    severity: Literal["high", "medium", "low"] = Field(..., description="严重程度")
    recommendation: str = Field(..., description="改进建议")


class KeyFinding(BaseModel):
    """Key finding from analysis."""

    finding_id: int = Field(..., description="发现ID")
    type: Literal["strength", "weakness", "opportunity"] = Field(
        ...,
        description="类型",
    )
    title: str = Field(..., description="标题")
    description: str = Field(..., description="描述")
    evidence: str = Field(..., description="证据")
    business_impact: str = Field(..., description="业务影响")
    root_cause: str | None = Field(None, description="根因分析")


class Recommendation(BaseModel):
    """Optimization recommendation."""

    priority: int = Field(..., description="优先级 (1-4)")
    category: str = Field(..., description="类别")
    title: str = Field(..., description="标题")
    rationale: str = Field(..., description="背景")
    actions: list[str] = Field(default_factory=list, description="具体行动")
    expected_impact: str = Field(..., description="预期效果")
    effort_level: Literal["high", "medium", "low"] = Field(
        ...,
        description="工作量",
    )
    timeline: str = Field(..., description="时间线")


class RiskAlert(BaseModel):
    """Risk alert."""

    risk_id: int = Field(..., description="风险ID")
    risk_level: Literal["high", "medium", "low"] = Field(..., description="风险等级")
    title: str = Field(..., description="标题")
    description: str = Field(..., description="描述")
    potential_impact: str = Field(..., description="潜在影响")
    mitigation: str = Field(..., description="应对建议")


class ExecutiveSummary(BaseModel):
    """Executive summary of analysis."""

    headline: str = Field(..., description="核心结论")
    overall_score: int = Field(..., description="综合得分")
    score_band: str = Field(..., description="评级")
    key_metrics_snapshot: dict[str, str] = Field(
        default_factory=dict,
        description="关键指标快照",
    )


class AnalysisInput(BaseModel):
    """Input for data analysis."""

    session_id: str = Field(..., description="会话ID")
    fetch_results: list[FetchResult] = Field(..., description="抓取结果")
    brand_profile: BrandProfile = Field(..., description="品牌档案")
    competitors: list[Competitor] = Field(..., description="竞品列表")
    report_type: ReportType = Field(..., description="报告类型")

    # Optional fields
    baseline_metrics: AnalysisMetrics | None = Field(
        None,
        description="基准指标（对比分析时）",
    )
    selected_personas: list[UserPersona] | None = Field(
        None,
        description="选中的画像（精准分析时）",
    )


class AnalysisOutput(BaseModel):
    """Output from data analysis."""

    analysis_id: str = Field(..., description="分析ID")
    analysis_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="分析时间",
    )

    # Brand context
    brand_context: dict[str, Any] = Field(
        default_factory=dict,
        description="品牌上下文",
    )

    # Metrics
    metrics: AnalysisMetrics = Field(..., description="分析指标")

    # Competitive analysis
    competitive_ranking: list[CompetitiveBrandMetrics] = Field(
        default_factory=list,
        description="竞品排名",
    )
    competitive_sov_index: dict[str, float] = Field(
        default_factory=dict,
        description="竞品声量份额",
    )
    head_to_head_analysis: dict[str, HeadToHeadAnalysis] = Field(
        default_factory=dict,
        description="一对一分析",
    )

    # Platform consistency
    platform_consistency_index: float = Field(
        ...,
        description="平台一致性指数",
    )

    # Weakness areas
    weakness_areas: list[WeaknessArea] = Field(
        default_factory=list,
        description="薄弱环节",
    )

    # Insights
    insights: list[KeyFinding] = Field(default_factory=list, description="关键洞察")
    recommendations: list[Recommendation] = Field(
        default_factory=list,
        description="优化建议",
    )
    risk_alerts: list[RiskAlert] = Field(default_factory=list, description="风险预警")

    # Executive summary
    executive_summary: ExecutiveSummary = Field(..., description="执行摘要")

    # Visualization configs
    visualization_configs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="图表配置",
    )

    # Next steps
    next_steps: dict[str, Any] = Field(default_factory=dict, description="下一步行动")


class AnalysisResult(BaseModel):
    """Complete analysis result with metadata."""

    success: bool = Field(..., description="是否成功")
    output: AnalysisOutput | None = Field(None, description="分析输出")
    error_message: str | None = Field(None, description="错误信息")
    raw_data: dict[str, Any] | None = Field(None, description="原始数据")

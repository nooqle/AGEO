"""Report schemas for AEO report generation."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportFormat(str, Enum):
    """Report output formats."""

    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"


class ReportType(str, Enum):
    """Types of reports."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    EXECUTIVE = "executive"
    SPECIAL = "special"


class DetailLevel(str, Enum):
    """Detail levels for reports."""

    EXECUTIVE = "executive"
    SUMMARY = "summary"
    DETAILED = "detailed"
    FULL = "full"


class ChartType(str, Enum):
    """Types of charts."""

    RADAR = "radar"
    BAR = "bar"
    BAR_GROUPED = "bar_grouped"
    PIE = "pie"
    FUNNEL = "funnel"
    HEATMAP = "heatmap"
    LINE = "line"
    LINE_MULTI = "line_multi"
    SCATTER_BUBBLE = "scatter_bubble"
    AREA_STACKED = "area_stacked"
    WATERFALL = "waterfall"


class ChartConfig(BaseModel):
    """Chart configuration."""

    chart_id: str = Field(..., description="图表ID")
    chart_type: ChartType = Field(..., description="图表类型")
    title: str = Field(..., description="标题")
    description: str = Field("", description="描述")
    data: dict[str, Any] = Field(default_factory=dict, description="图表数据")
    options: dict[str, Any] = Field(default_factory=dict, description="图表选项")


class ReportSection(BaseModel):
    """Report section."""

    section_id: str = Field(..., description="章节ID")
    title: str = Field(..., description="标题")
    content: str = Field("", description="内容")
    order: int = Field(0, description="顺序")
    include_charts: list[str] = Field(
        default_factory=list,
        description="包含的图表ID",
    )


class ReportConfig(BaseModel):
    """Report generation configuration."""

    report_type: ReportType = Field(..., description="报告类型")
    brand_name: str = Field(..., description="品牌名称")
    report_period_start: str = Field(..., description="报告周期开始")
    report_period_end: str = Field(..., description="报告周期结束")
    comparison_period_start: str | None = Field(
        None,
        description="对比周期开始",
    )
    comparison_period_end: str | None = Field(
        None,
        description="对比周期结束",
    )
    output_format: ReportFormat = Field(
        ReportFormat.MARKDOWN,
        description="输出格式",
    )
    language: str = Field("zh-CN", description="语言")
    detail_level: DetailLevel = Field(
        DetailLevel.DETAILED,
        description="详细程度",
    )
    include_charts: bool = Field(True, description="是否包含图表")
    include_appendix: bool = Field(True, description="是否包含附录")


class Report(BaseModel):
    """Generated report."""

    report_id: str = Field(..., description="报告ID")
    report_type: ReportType = Field(..., description="报告类型")
    brand_name: str = Field(..., description="品牌名称")
    title: str = Field(..., description="标题")
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="生成时间",
    )
    content: str = Field(..., description="报告内容")
    format: ReportFormat = Field(..., description="格式")
    word_count: int = Field(0, description="字数")
    sections: list[str] = Field(default_factory=list, description="章节列表")
    charts: list[ChartConfig] = Field(default_factory=list, description="图表配置")


class ReportTemplate(BaseModel):
    """Report template."""

    template_id: str = Field(..., description="模板ID")
    template_type: ReportType = Field(..., description="模板类型")
    name: str = Field(..., description="名称")
    description: str = Field("", description="描述")
    template_content: str = Field(..., description="模板内容")
    default_sections: list[str] = Field(
        default_factory=list,
        description="默认章节",
    )


class Insight(BaseModel):
    """Analysis insight."""

    insight_id: str = Field(..., description="洞察ID")
    type: Literal["strength", "weakness", "opportunity", "threat"] = Field(
        ...,
        description="类型",
    )
    title: str = Field(..., description="标题")
    description: str = Field(..., description="描述")
    evidence: str = Field(..., description="证据")
    business_impact: str = Field(..., description="业务影响")
    priority: int = Field(1, description="优先级")


class NextStep(BaseModel):
    """Next step action."""

    step_id: str = Field(..., description="步骤ID")
    action: str = Field(..., description="行动")
    owner: str | None = Field(None, description="负责人")
    due_date: str | None = Field(None, description="截止日期")
    priority: Literal["high", "medium", "low"] = Field(
        "medium",
        description="优先级",
    )


class ReportOutput(BaseModel):
    """Complete report output."""

    report: Report = Field(..., description="报告")
    insights: list[Insight] = Field(default_factory=list, description="洞察")
    next_steps: list[NextStep] = Field(default_factory=list, description="下一步")
    chart_files: dict[str, str] = Field(
        default_factory=dict,
        description="图表文件路径",
    )


class TemporalMetrics(BaseModel):
    """Temporal metrics for trend analysis."""

    metric_name: str = Field(..., description="指标名称")
    current: float = Field(..., description="当前值")
    previous: float = Field(..., description="上期值")
    change: float = Field(..., description="变化值")
    change_rate: float = Field(..., description="变化率 (%)")
    trend: str = Field(..., description="趋势")
    trend_icon: str = Field(..., description="趋势图标")
    historical_values: list[float] = Field(
        default_factory=list,
        description="历史值",
    )
    historical_labels: list[str] = Field(
        default_factory=list,
        description="历史标签",
    )


class TrendAnalysis(BaseModel):
    """Trend analysis results."""

    analysis_period: dict[str, Any] = Field(
        default_factory=dict,
        description="分析周期",
    )
    metrics_trend: dict[str, TemporalMetrics] = Field(
        default_factory=dict,
        description="指标趋势",
    )
    platform_trend: dict[str, Any] = Field(
        default_factory=dict,
        description="平台趋势",
    )
    competitive_trend: dict[str, Any] = Field(
        default_factory=dict,
        description="竞品趋势",
    )
    trend_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="趋势总结",
    )

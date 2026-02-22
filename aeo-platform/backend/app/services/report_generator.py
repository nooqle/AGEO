"""Report generation service for Specta AI analysis."""

from datetime import datetime, timezone

from app.schemas.analytics import (
    AnalysisOutput,
    KeyFinding,
    Recommendation,
    WeaknessArea,
)
from app.schemas.report import (
    ChartConfig,
    ChartType,
    Report,
    ReportConfig,
    ReportOutput,
    ReportType,
)


class ReportGenerator:
    """Generator for Specta AI analysis reports."""

    def __init__(self, config: ReportConfig):
        """Initialize report generator.

        Args:
            config: Report configuration
        """
        self.config = config

    def generate(self, analysis_output: AnalysisOutput) -> ReportOutput:
        """Generate complete report.

        Args:
            analysis_output: Analysis output from data analytics agent

        Returns:
            Report output with all formats
        """
        # Generate report title
        title = self._generate_title(analysis_output)

        # Generate content based on detail level
        content = self._generate_report_content(analysis_output)

        # Generate charts
        charts = self._generate_charts(analysis_output)

        # Create report object
        report = Report(
            report_id=f"report_{analysis_output.analysis_id}",
            report_type=self.config.report_type,
            brand_name=self.config.brand_name,
            title=title,
            content=content,
            format=self.config.output_format,
            word_count=len(content),
            charts=charts,
        )

        # Generate output in requested formats
        output = ReportOutput(report=report)

        return output

    def _generate_title(self, analysis_output: AnalysisOutput) -> str:
        """Generate report title.

        Args:
            analysis_output: Analysis output

        Returns:
            Report title
        """
        brand = self.config.brand_name
        period = f"{self.config.report_period_start} 至 {self.config.report_period_end}"

        type_names = {
            ReportType.EXECUTIVE: "执行摘要",
            ReportType.DAILY: "日报",
            ReportType.WEEKLY: "周报",
            ReportType.MONTHLY: "月报",
            ReportType.SPECIAL: "专项报告",
        }

        report_type_name = type_names.get(self.config.report_type, "分析报告")
        return f"{brand} Specta AI 品牌声量评估 {report_type_name} ({period})"

    def _generate_report_content(self, analysis_output: AnalysisOutput) -> str:
        """Generate report content.

        Args:
            analysis_output: Analysis output

        Returns:
            Report content in markdown format
        """
        sections = []

        # Executive Summary
        sections.append(self._generate_executive_summary(analysis_output))

        # Brand Performance
        sections.append(self._generate_brand_performance_section(analysis_output))

        # Competitive Analysis
        sections.append(self._generate_competitive_section(analysis_output))

        # Weakness Analysis
        sections.append(self._generate_weakness_section(analysis_output))

        # Key Findings
        sections.append(self._generate_findings_section(analysis_output))

        # Recommendations
        sections.append(self._generate_recommendations_section(analysis_output))

        return "\n\n---\n\n".join(sections)

    def _generate_executive_summary(self, analysis_output: AnalysisOutput) -> str:
        """Generate executive summary section.

        Args:
            analysis_output: Analysis output

        Returns:
            Executive summary content
        """
        brand_name = self.config.brand_name
        metrics = analysis_output.metrics
        exec_summary = analysis_output.executive_summary

        return f"""# 执行摘要

## {brand_name} 品牌声量评估概览

**评估周期**: {self.config.report_period_start} 至 {self.config.report_period_end}

**总体评分**: {exec_summary.overall_score}/100

**核心指标**:
- 品牌加权声量指数 (BWVS): {metrics.bwvs_total:.2f}
- 品牌提及率: {metrics.mention_rate_overall:.1%}
- 情感分布: 正向 {metrics.sentiment_overall.positive:.1%} / 中性 {metrics.sentiment_overall.neutral:.1%} / 负向 {metrics.sentiment_overall.negative:.1%}

**关键结论**:
{self._format_key_conclusions(analysis_output.insights)}

**核心建议**:
{self._format_top_recommendations(analysis_output.recommendations[:3])}
"""

    def _generate_brand_performance_section(
        self, analysis_output: AnalysisOutput
    ) -> str:
        """Generate brand performance section.

        Args:
            analysis_output: Analysis output

        Returns:
            Brand performance content
        """
        brand_name = self.config.brand_name
        metrics = analysis_output.metrics

        return f"""# 品牌表现分析

## {brand_name} 核心指标

### 声量指标
- **品牌加权声量指数 (BWVS)**: {metrics.bwvs_total:.2f}
- **品牌提及率**: {metrics.mention_rate_overall:.1%}

### 情感分析
- **正向占比**: {metrics.sentiment_overall.positive:.1%}
- **中性占比**: {metrics.sentiment_overall.neutral:.1%}
- **负向占比**: {metrics.sentiment_overall.negative:.1%}
- **净情感得分**: {metrics.sentiment_overall.net_sentiment_score:.2f}

### 平台表现
{self._format_platform_metrics(metrics.bwvs_by_platform)}

### 类别表现
{self._format_category_metrics(metrics.category_metrics)}
"""

    def _generate_competitive_section(self, analysis_output: AnalysisOutput) -> str:
        """Generate competitive analysis section.

        Args:
            analysis_output: Analysis output

        Returns:
            Competitive analysis content
        """
        brand_name = self.config.brand_name
        competitors = [c.brand for c in analysis_output.competitive_ranking if c.brand != brand_name]

        return f"""# 竞品对比分析

## 竞争格局概览

**分析品牌**: {brand_name}
**对比竞品**: {', '.join(competitors)}

### 核心指标对比

| 品牌 | BWVS | 提及率 | 正向情感 |
|------|------|--------|----------|
{self._format_competitive_table(analysis_output)}

### 竞争优势分析
{self._format_competitive_advantages(analysis_output)}

### 竞争差距分析
{self._format_competitive_gaps(analysis_output)}
"""

    def _generate_weakness_section(self, analysis_output: AnalysisOutput) -> str:
        """Generate weakness analysis section.

        Args:
            analysis_output: Analysis output

        Returns:
            Weakness analysis content
        """
        if not analysis_output.weakness_areas:
            return "# 薄弱环节分析\n\n未识别出明显的薄弱环节。"

        return f"""# 薄弱环节分析

## 识别的薄弱环节

{self._format_weakness_areas(analysis_output.weakness_areas)}

## 改进建议

{self._format_weakness_recommendations(analysis_output.weakness_areas)}
"""

    def _generate_findings_section(self, analysis_output: AnalysisOutput) -> str:
        """Generate key findings section.

        Args:
            analysis_output: Analysis output

        Returns:
            Key findings content
        """
        return f"""# 关键发现

## 重要洞察

{self._format_key_findings(analysis_output.insights)}

## 数据亮点

{self._format_data_highlights(analysis_output)}
"""

    def _generate_recommendations_section(self, analysis_output: AnalysisOutput) -> str:
        """Generate recommendations section.

        Args:
            analysis_output: Analysis output

        Returns:
            Recommendations content
        """
        recommendations_text = self._format_recommendations(
            analysis_output.recommendations
        )
        report_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"""# 行动建议

## 优先建议

{recommendations_text}

## 实施路线图

1. **短期行动** (1-2周)
   - 针对识别出的薄弱环节制定改进计划
   - 优化高频问题类别的回答策略

2. **中期优化** (1-3个月)
   - 加强竞品优势领域的品牌建设
   - 提升在关键平台的可见度

3. **长期战略** (3-6个月)
   - 建立品牌护城河

---

*报告生成时间: {report_timestamp}*
*Specta AI Platform v1.0*
"""

    def _generate_charts(self, analysis_output: AnalysisOutput) -> list[ChartConfig]:
        """Generate chart configurations.

        Args:
            analysis_output: Analysis output

        Returns:
            List of chart configurations
        """
        charts = []
        metrics = analysis_output.metrics

        # BWVS comparison chart
        competitive_brands = analysis_output.competitive_ranking
        charts.append(
            ChartConfig(
                chart_id="bwvs_comparison",
                chart_type=ChartType.BAR,
                title="BWVS 品牌对比",
                description="各品牌 BWVS 得分对比",
                data={
                    "labels": [c.brand for c in competitive_brands],
                    "values": [c.bwvs for c in competitive_brands],
                },
            )
        )

        # Sentiment distribution pie chart
        sentiment = metrics.sentiment_overall
        charts.append(
            ChartConfig(
                chart_id="sentiment_distribution",
                chart_type=ChartType.PIE,
                title="情感分布",
                description="品牌情感分布",
                data={
                    "labels": ["正向", "中性", "负向"],
                    "values": [
                        sentiment.positive,
                        sentiment.neutral,
                        sentiment.negative,
                    ],
                },
            )
        )

        # Platform performance radar chart
        platforms = metrics.bwvs_by_platform
        charts.append(
            ChartConfig(
                chart_id="platform_performance",
                chart_type=ChartType.RADAR,
                title="平台表现",
                description="各平台 BWVS 表现",
                data={
                    "labels": list(platforms.keys()),
                    "values": [p.bwvs_score for p in platforms.values()],
                },
            )
        )

        return charts

    def _to_markdown(self, report: Report) -> str:
        """Convert report to markdown format.

        Args:
            report: Report object

        Returns:
            Markdown formatted report
        """
        return f"""# {report.title}

{report.content}
"""

    def _to_html(self, report: Report) -> str:
        """Convert report to HTML format.

        Args:
            report: Report object

        Returns:
            HTML formatted report
        """
        # Simple markdown to HTML conversion
        # In production, use a proper markdown library
        content = report.content.replace("\n\n", "</p><p>")
        content = content.replace("\n", "<br>")

        return f"""<!DOCTYPE html>
<html>
<head>
    <title>{report.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>{report.title}</h1>
    <p>{content}</p>
</body>
</html>
"""

    def _to_pdf(self, report: Report) -> str:
        """Convert report to PDF format.

        Args:
            report: Report object

        Returns:
            URL to PDF file
        """
        # TODO: Implement PDF generation
        # For now, return placeholder
        return f"/reports/{report.report_id}.pdf"

    # Helper methods for formatting
    def _format_key_conclusions(self, findings: list[KeyFinding]) -> str:
        """Format key conclusions."""
        if not findings:
            return "暂无关键结论。"

        return "\n".join(
            f"{i+1}. **{f.title}**: {f.description}"
            for i, f in enumerate(findings[:5])
        )

    def _format_top_recommendations(self, recommendations: list[Recommendation]) -> str:
        """Format top recommendations."""
        if not recommendations:
            return "暂无建议。"

        return "\n".join(
            f"{i+1}. **{r.title}** (优先级: {r.priority}): {r.rationale}"
            for i, r in enumerate(recommendations)
        )

    def _format_platform_metrics(self, platforms: dict) -> str:
        """Format platform metrics."""
        return "\n".join(
            f"- **{name}**: BWVS {metrics.bwvs_score:.2f}, "
            f"提及率 {metrics.mention_rate:.1%}"
            for name, metrics in platforms.items()
        )

    def _format_category_metrics(self, categories: dict) -> str:
        """Format category metrics."""
        return "\n".join(
            f"- **{name}**: 提及率 {metrics.mention_rate:.1%}, "
            f"正向率 {metrics.positive_rate:.1%}"
            for name, metrics in categories.items()
        )

    def _format_competitive_table(self, analysis_output: AnalysisOutput) -> str:
        """Format competitive comparison table."""
        rows = []

        for competitor in analysis_output.competitive_ranking:
            rows.append(
                f"| {competitor.brand} | "
                f"{competitor.bwvs:.2f} | "
                f"{competitor.mention_rate:.1%} | "
                f"{competitor.positive_sentiment:.1%} |"
            )

        return "\n".join(rows)

    def _format_competitive_advantages(self, analysis_output: AnalysisOutput) -> str:
        """Format competitive advantages."""
        brand_name = self.config.brand_name
        advantages = []

        # Find our brand's metrics
        our_brand = next((c for c in analysis_output.competitive_ranking if c.brand == brand_name), None)
        if not our_brand:
            return "暂无数据。"

        for competitor in analysis_output.competitive_ranking:
            if competitor.brand != brand_name and our_brand.bwvs > competitor.bwvs:
                advantages.append(
                    f"- 在 BWVS 指数上领先 {competitor.brand} "
                    f"({our_brand.bwvs:.2f} vs {competitor.bwvs:.2f})"
                )

        return "\n".join(advantages) if advantages else "暂无显著优势。"

    def _format_competitive_gaps(self, analysis_output: AnalysisOutput) -> str:
        """Format competitive gaps."""
        brand_name = self.config.brand_name
        gaps = []

        # Find our brand's metrics
        our_brand = next((c for c in analysis_output.competitive_ranking if c.brand == brand_name), None)
        if not our_brand:
            return "暂无数据。"

        for competitor in analysis_output.competitive_ranking:
            if competitor.brand != brand_name and our_brand.bwvs < competitor.bwvs:
                gaps.append(
                    f"- 在 BWVS 指数上落后 {competitor.brand} "
                    f"({our_brand.bwvs:.2f} vs {competitor.bwvs:.2f})"
                )

        return "\n".join(gaps) if gaps else "暂无显著差距。"

    def _format_weakness_areas(self, weaknesses: list[WeaknessArea]) -> str:
        """Format weakness areas."""
        return "\n\n".join(
            f"### {w.category}\n"
            f"- **严重程度**: {w.severity}\n"
            f"- **当前值**: {w.current_value:.2f}\n"
            f"- **基准值**: {w.benchmark_value:.2f}\n"
            f"- **差距**: {w.gap:.2f}\n"
            f"- **建议**: {w.recommendation}"
            for w in weaknesses
        )

    def _format_weakness_recommendations(self, weaknesses: list[WeaknessArea]) -> str:
        """Format weakness recommendations."""
        return "\n".join(
            f"{i+1}. **{w.category}**: {w.recommendation}" for i, w in enumerate(weaknesses)
        )

    def _format_key_findings(self, findings: list[KeyFinding]) -> str:
        """Format key findings."""
        return "\n\n".join(
            f"### {f.title}\n"
            f"- **类型**: {f.type}\n"
            f"- **描述**: {f.description}\n"
            f"- **证据**: {f.evidence}\n"
            f"- **业务影响**: {f.business_impact}"
            for f in findings
        )

    def _format_data_highlights(self, analysis_output: AnalysisOutput) -> str:
        """Format data highlights."""
        metrics = analysis_output.metrics
        return f"""- 覆盖 {len(metrics.bwvs_by_platform)} 个主要平台
- 涉及 {len(metrics.category_metrics)} 个问题类别
- 竞品对比包含 {len(analysis_output.competitive_ranking)} 个品牌"""

    def _format_recommendations(self, recommendations: list[Recommendation]) -> str:
        """Format recommendations."""
        priority_order = {1: 0, 2: 1, 3: 2, 4: 3}
        sorted_recs = sorted(
            recommendations, key=lambda r: priority_order.get(r.priority, 4)
        )

        return "\n\n".join(
            f"### {i+1}. {r.title} (优先级: {r.priority})\n"
            f"**类别**: {r.category}\n\n"
            f"{r.rationale}\n\n"
            f"**具体行动**: {', '.join(r.actions)}\n\n"
            f"**预期影响**: {r.expected_impact}\n"
            f"**工作量**: {r.effort_level}\n"
            f"**时间线**: {r.timeline}"
            for i, r in enumerate(sorted_recs)
        )

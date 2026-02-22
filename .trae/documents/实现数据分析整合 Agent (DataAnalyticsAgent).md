## 执行计划

### Step 1: 创建输入输出 Schema
**文件**:
- `backend/app/schemas/analytics.py` - 分析相关 Schema
- `backend/app/schemas/report.py` - 报告相关 Schema

**analytics.py** 包含：
- `AnalysisMetrics` - 核心指标（BWVS、提及率、情感率等）
- `CategoryMetric` - 分类指标
- `CompetitiveAnalysis` - 竞品分析
- `PlatformConsistency` - 平台一致性
- `WeaknessArea` - 薄弱环节
- `AnalysisInput` / `AnalysisOutput` - 输入输出
- `ReportType` - 报告类型枚举

**report.py** 包含：
- `Report` - 报告基础结构
- `ReportConfig` - 报告配置
- `ChartConfig` - 图表配置
- `Insight` / `Recommendation` - 洞察和建议

### Step 2: 创建指标计算服务
**文件**: `backend/app/services/metrics_calculator.py`

实现核心指标计算：
- `calculate_bwvs()` - 品牌加权声量指数
- `calculate_mention_rate()` - 提及率
- `calculate_sentiment_distribution()` - 情感分布
- `calculate_citation_metrics()` - 引用指标
- `calculate_accuracy_score()` - 准确率
- `calculate_competitive_sov()` - 竞品声量份额
- `calculate_platform_consistency()` - 平台一致性

### Step 3: 创建报告生成服务
**文件**: `backend/app/services/report_generator.py`

实现报告生成：
- `generate_weekly_report()` - 周报
- `generate_daily_brief()` - 日报
- `generate_executive_summary()` - 管理层简报
- `generate_charts()` - 图表生成配置
- 支持 Markdown/HTML/PDF 输出

### Step 4: 实现 DataAnalyticsAgent
**文件**: `backend/app/agents/data_analytics.py`

实现 `DataAnalyticsAgent` 类：
- `agent_id = "A6"`
- `analyze()` - 主分析流程
- `_preprocess()` - 数据预处理
- `_analyze_mentions()` - 品牌提及分析
- `_analyze_sentiment()` - 情感分析
- `_analyze_citations()` - 引用分析
- `_calculate_metrics()` - 计算综合指标
- `_identify_weakness()` - 识别薄弱环节
- `_generate_report()` - 生成报告

### Step 5: 创建系统提示词
**文件**: `backend/prompts/data_analytics_agent.md`

包含：
- Agent 角色定义（AEO 数据分析师）
- 核心指标体系说明
- 分析维度框架
- 输出格式规范
- 可视化图表配置
- 报告生成模板

### 关键设计

**核心指标**：
- BWVS (Brand Weighted Visibility Score) - 品牌加权声量指数
- 提及率、情感分布、准确率、官网引用率
- 竞品声量份额、平台一致性

**报告类型**：
- BASELINE - 基准声量分析报告
- PRECISION - 精准画像分析报告
- COMPARISON - 对比分析报告
- MONITORING - 监控报告

**分析流程**：
1. 数据预处理
2. 品牌提及识别
3. 情感分析
4. 引用分析
5. 计算综合指标
6. 识别薄弱环节
7. 生成报告

请确认此计划后，我将开始执行具体的代码实现。
---
name: Post Analysis Package
description: Package guidance for drill-down and historical comparison tasks built on top of the post-analysis executor.
---

# Runtime Guidance

- Use this package only after the workflow already has analysis results, fetched answers, or snapshots to work from.
- Decide whether the user wants deeper interpretation or cross-run comparison.
- Reuse the existing evidence first; if the missing piece requires fresh data, hand the need back to the orchestrator so it can route to answer_fetch.

# Output Expectations

- Keep responses task-shaped: compare when asked to compare, zoom in when asked to drill down.
- Preserve continuity with prior findings instead of restating the full report.
- Make the next action obvious when evidence is incomplete, and explicitly say when new fetching would be more appropriate than more analysis.

# 读数与情绪判断

- 先判断有没有有效分母；没有有效分母时写“暂无足够数据支撑”，不要写 0.0%。
- 有有效分母但分子为 0 时，写“本轮样本未观察到该类信号”，不要扩展成长期结论。
- 品牌提及为 0 时，不判断品牌正向、负向、口碑或官网承接。
- 负向：只要文本中提及损害品牌声誉、指出产品硬伤、合规性失败或客观负面事件，均归类为负向。
- 正向：文本中强调产品的技术优势、权威认证、市场成功或积极社会影响，归类为正向。
- 中性：文本仅做机制说明、参数罗列或背景介绍，不对好坏进行评价或事件定性，归类为中性。
- 同一段同时包含正向和负向事实时，分别提取核心原文，不要用一个标签覆盖全部事实。

# 判断示例

- “不符合 GB/T 18801 标准、参数虚标” -> 负向。
- “隐私泄露、未经授权收集定位数据、监管罚款” -> 负向。
- “热失控风险、主动召回” -> 负向。
- “通过 ISO 27001 认证、红点设计大奖、标杆产品” -> 正向。
- “突破上下文窗口限制、提升准确率” -> 正向。
- “额定功率 800W、支持标准模式和节能模式” -> 中性。

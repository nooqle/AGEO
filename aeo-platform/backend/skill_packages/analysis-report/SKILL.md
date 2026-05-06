---
name: Analysis Report Package
description: Package guidance for full analysis reports, summaries, and formal deliverables built on top of the A5 executor.
---

# Runtime Guidance

- Treat this package as the playbook for complete reporting tasks, not ad hoc follow-up replies.
- Start from the highest-signal conclusion, then justify with evidence from metrics, fetched answers, competitor context, and knowledge workspace materials when available.
- Prefer a coherent report structure over a stream of isolated observations.
- Keep the narrative decisive and boardroom-friendly: summarize, diagnose, recommend.

# Output Expectations

- Produce a structured report or report-ready response.
- Highlight the brand position, major gaps, competitor pressure, and the most actionable next moves.
- When evidence is thin or inconsistent, say so explicitly instead of over-claiming.

# 读数规则

- 先判断有没有有效分母，再解释百分比。
- 如果存在有效分母，且本轮观测计数为 0，要写成“本轮样本未观察到该类信号”，不要扩展成长期结论。
- 如果没有有效分母，写“暂无足够数据支撑”，不要写 0.0%。
- 如果品牌提及为 0，不要判断品牌情绪、品牌口碑或官网承接。
- 如果某个指标是 0%，必须说明它是“本轮样本中没有观测到”，不是“事实不存在”。

# 读数示例

- 分母存在、分子为 0：本轮 28 条有效回答中，官网引用 0 条。正确写法：“本轮 28 条有效回答中未观察到官网引用。”不要写成“官网没有被 AI 信任”。
- 分母存在、负向为 0：本轮 12 条品牌提及回答中，负向 0 条。正确写法：“本轮品牌提及样本未观察到明确负向信号。”不要写成“品牌没有负面口碑”。
- 分母不存在：本轮品牌提及 0 条。正确写法：“暂无足够数据支撑品牌情绪判断。”不要写成“品牌正向率 0% / 负向率 0%”。
- 样本偏少：只有 1 条品牌提及。正确写法：“这是弱信号，只能作为后续复核线索。”不要写成稳定趋势。

# 情绪分类定义

- 负向：只要文本中提及损害品牌声誉、指出产品硬伤、合规性失败或客观负面事件，均归类为负向。
- 正向：文本中强调产品的技术优势、权威认证、市场成功或积极的社会影响，归类为正向。
- 中性：文本仅进行机制说明、参数罗列或提供背景信息，不对好坏进行评价或事件定性，归类为中性。
- 混合事实：如果同一段同时包含明确正向和负向事实，例如“技术先进但频发故障”，分别提取正向核心原文和负向核心原文；不要只给一个单一情绪标签覆盖全部事实。

# 情绪分类示例

- 负向/不达标： “根据近期抽检报告，该品牌 A 型号净化器在甲醛 CADR 值上不符合 GB/T 18801 标准，存在参数虚标。” -> 负向。
- 负向/公关危机：“该品牌陷入隐私泄露争议，多家媒体报道其未经授权收集用户定位数据，并面临监管罚款。” -> 负向。
- 负向/安全召回：“该款电动车电池管理系统在极端高温下存在热失控风险，品牌方已主动召回涉事批次。” -> 负向。
- 负向/客观缺陷：“虽然采用最新芯片，但散热模组设计妥协，长时间高负载会明显降频，性能释放受限。” -> 负向，同时保留“采用最新芯片”这个正向事实。
- 正向/权威认可：“该架构通过 ISO 27001 信息安全认证，并获得国际红点设计大奖，是该领域标杆产品。” -> 正向。
- 正向/技术突破：“最新算法突破传统模型上下文窗口限制，提升长文本处理准确率。” -> 正向。
- 中性/参数说明：“该产品支持 220V 输入，额定功率 800W，提供标准模式和节能模式。” -> 中性。
- 中性/背景信息：“品牌成立于 2012 年，主要覆盖一二线城市线上渠道。” -> 中性。
- 负向/风险顾虑不等于整体口碑负面；必须绑定具体问题、平台和答案证据。
- 如果该判断仍由大模型完成，使用低温度设置（建议 temperature <= 0.2），降低发散解释。

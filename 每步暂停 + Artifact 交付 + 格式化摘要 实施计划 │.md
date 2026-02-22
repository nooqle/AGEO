 每步暂停 + Artifact 交付 + 格式化摘要 实施计划                                                                             │
│                                                                                                                            │
│ 需求概述                                                                                                                   │
│                                                                                                                            │
│ 1. 每步暂停确认: A1→A5 每步完成后暂停，展示 Artifact，等用户确认后继续                                                     │
│ 2. Canvas Artifact 交付: 每步产出结构化的 Canvas 内容（图谱/文档/列表/表格/报告）                                          │
│ 3. 格式化摘要: TPAOR response 阶段显示人类可读摘要，不显示原始 JSON                                                        │
│ 4. Bug 修复: error_info Annotated reducer + A2 typo                                                                        │
│                                                                                                                            │
│ 架构变更                                                                                                                   │
│                                                                                                                            │
│ 新的工作流图                                                                                                               │
│                                                                                                                            │
│ START → A1 → a1_review → a2_decision → [A2 → a2_review | skip] → a3_decision → A3 → a3_review → A4 → a4_review → A5 →      │
│ a5_review → END                                                                                                            │
│                                                                                                                            │
│ 新增 4 个 review 节点: a1_review, a3_review, a4_review, a5_review                                                          │
│ A2 已有 a2_decision，在 A2 完成后增加 a2_review                                                                            │
│                                                                                                                            │
│ TPAOR 阶段重新定义                                                                                                         │
│                                                                                                                            │
│ - thought = LLM 思考推理（保持不变）                                                                                       │
│ - observation = LLM 原始输出/数据处理（原来的 response 改名）                                                              │
│ - response = 格式化的人类可读摘要（新增，由节点在解析后发送）                                                              │
│                                                                                                                            │
│ ---                                                                                                                        │
│ 实施步骤（按顺序）                                                                                                         │
│                                                                                                                            │
│ Step 1: Bug 修复                                                                                                           │
│                                                                                                                            │
│ aeo-platform/backend/app/workflow/state.py                                                                                 │
│                                                                                                                            │
│ - 在 AgentState 类之前添加 reducer 函数:                                                                                   │
│ def _merge_error_info(existing: dict | None, new: dict | None) -> dict | None:                                             │
│     return new if new is not None else existing                                                                            │
│ - 修改 L198: error_info: dict | None → error_info: Annotated[dict | None, _merge_error_info]                               │
│                                                                                                                            │
│ aeo-platform/backend/app/workflow/nodes.py                                                                                 │
│                                                                                                                            │
│ - 修改 L406: " step": "A2" → "step": "A2"                                                                                  │
│                                                                                                                            │
│ Step 2: 后端 - 摘要生成模块（新建）                                                                                        │
│                                                                                                                            │
│ 新建 aeo-platform/backend/app/workflow/summaries.py                                                                        │
│                                                                                                                            │
│ 5 个函数，每个 Agent 步骤一个:                                                                                             │
│ - generate_a1_summary(brand_profile, competitors, competitive_landscape) →                                                 │
│ "已完成品牌分析：识别品牌「蕉内」，发现12个竞品"                                                                           │
│ - generate_a2_summary(marketing_personas) → "已生成6个用户画像，覆盖18个使用场景"                                          │
│ - generate_a3_summary(simulated_questions, questions) → "已生成10组模拟问题，共30个问题变体"                               │
│ - generate_a4_summary(fetch_results) → "已完成4个平台的答案抓取，成功率85%"                                                │
│ - generate_a5_summary(metrics, report) → "分析报告已生成，BWVS指数: 72.5"                                                  │
│                                                                                                                            │
│ Step 3: 后端 - 增强事件模块                                                                                                │
│                                                                                                                            │
│ aeo-platform/backend/app/workflow/events.py                                                                                │
│                                                                                                                            │
│ 新增 send_step_complete_with_artifact() 函数，统一处理:                                                                    │
│ 1. 发送格式化 TPAOR response 摘要                                                                                          │
│ 2. 发送 output_ready 事件（Canvas Artifact）                                                                               │
│ 3. 发送 confirmation_request 事件（暂停等待确认）                                                                          │
│                                                                                                                            │
│ Step 4: 后端 - 流式输出阶段重命名                                                                                          │
│                                                                                                                            │
│ aeo-platform/backend/app/workflow/nodes_streaming.py                                                                       │
│                                                                                                                            │
│ 将 stream_llm_with_tpaor 中的 response 阶段改为 observation:                                                               │
│ - L81-86: phase="response" → phase="observation"（流式 chunk）                                                             │
│ - L111-116: phase="response" → phase="observation"（完成标记）                                                             │
│                                                                                                                            │
│ 这样 response 阶段专门留给节点发送格式化摘要。                                                                             │
│                                                                                                                            │
│ Step 5: 后端 - Review 决策节点（新建）                                                                                     │
│                                                                                                                            │
│ 新建 aeo-platform/backend/app/workflow/nodes_review.py                                                                     │
│                                                                                                                            │
│ 4 个 review 节点，复用 a2_decision_node 的状态机模式:                                                                      │
│                                                                                                                            │
│ a1_review_node: A1 完成后暂停                                                                                              │
│ - Canvas Artifact: workflow 类型（BrandCompetitionGraph + 品牌档案 + 竞品列表）                                            │
│ - 确认选项: "确认，继续下一步"                                                                                             │
│ - 确认后 goto: a2_decision                                                                                                 │
│                                                                                                                            │
│ a2_review_node: A2 完成后暂停（新增，在 a2_persona 之后）                                                                  │
│ - Canvas Artifact: workflow 类型（PersonaGraph + 画像卡片）                                                                │
│ - 确认选项: "确认，继续下一步"                                                                                             │
│ - 确认后 goto: a3_decision                                                                                                 │
│                                                                                                                            │
│ a3_review_node: A3 完成后暂停                                                                                              │
│ - Canvas Artifact: questionList 类型（新 Canvas 类型）                                                                     │
│ - 确认选项: "确认，开始抓取"                                                                                               │
│ - 确认后 goto: a4_fetch                                                                                                    │
│                                                                                                                            │
│ a4_review_node: A4 完成后暂停                                                                                              │
│ - Canvas Artifact: fetchResults 类型（新 Canvas 类型）                                                                     │
│ - 确认选项: "确认，生成报告"                                                                                               │
│ - 确认后 goto: a5_analytics                                                                                                │
│                                                                                                                            │
│ a5_review_node: A5 完成后展示最终报告                                                                                      │
│ - Canvas Artifact: report 类型                                                                                             │
│ - 确认选项: "完成分析"                                                                                                     │
│ - 确认后 goto: __end__，发送 execution_complete                                                                            │
│                                                                                                                            │
│ Step 6: 后端 - 更新图定义和现有节点                                                                                        │
│                                                                                                                            │
│ aeo-platform/backend/app/workflow/graph.py                                                                                 │
│                                                                                                                            │
│ 添加 5 个新节点，重新连接边:                                                                                               │
│ # 新节点                                                                                                                   │
│ workflow.add_node("a1_review", a1_review_node)                                                                             │
│ workflow.add_node("a2_review", a2_review_node)                                                                             │
│ workflow.add_node("a3_review", a3_review_node)                                                                             │
│ workflow.add_node("a4_review", a4_review_node)                                                                             │
│ workflow.add_node("a5_review", a5_review_node)                                                                             │
│                                                                                                                            │
│ # 新边                                                                                                                     │
│ a1_brand → a1_review (原: a1_brand → a2_decision)                                                                          │
│ a2_persona → a2_review (原: a2_persona → a3_decision)                                                                      │
│ a2_review → a3_decision (新)                                                                                               │
│ a3_question → a3_review (原: a3_question → a4_fetch)                                                                       │
│ a4_fetch → a4_review (原: a4_fetch → a5_analytics)                                                                         │
│ a5_analytics → a5_review (原: a5_analytics → END)                                                                          │
│                                                                                                                            │
│ 现有节点修改                                                                                                               │
│                                                                                                                            │
│ nodes.py - a1_brand_node:                                                                                                  │
│ - 删除 send_output_ready 调用（review 节点负责）                                                                           │
│ - 添加格式化摘要: await send_tpaor_event(session_id, "response", summary, is_complete=True)                                │
│ - goto 改为 "a1_review"                                                                                                    │
│                                                                                                                            │
│ nodes.py - a2_persona_node:                                                                                                │
│ - 删除 send_output_ready 调用                                                                                              │
│ - 添加格式化摘要                                                                                                           │
│ - goto 改为 "a2_review"（原: "a3_decision"）                                                                               │
│                                                                                                                            │
│ nodes_a3.py - a3_question_node:                                                                                            │
│ - 删除 send_output_ready 调用                                                                                              │
│ - 添加格式化摘要                                                                                                           │
│ - goto 改为 "a3_review"                                                                                                    │
│                                                                                                                            │
│ nodes_a4.py - a4_fetch_node:                                                                                               │
│ - 删除 send_output_ready 调用                                                                                              │
│ - 添加格式化摘要                                                                                                           │
│ - goto 改为 "a4_review"                                                                                                    │
│                                                                                                                            │
│ nodes_a5.py - a5_analytics_node:                                                                                           │
│ - 删除 send_output_ready 和 send_execution_complete 调用                                                                   │
│ - 添加格式化摘要                                                                                                           │
│ - goto 改为 "a5_review"                                                                                                    │
│                                                                                                                            │
│ Step 7: 前端 - Canvas 类型扩展                                                                                             │
│                                                                                                                            │
│ frontend/src/types/canvas.ts                                                                                               │
│                                                                                                                            │
│ - 添加类型: 'questionList' | 'fetchResults'                                                                                │
│                                                                                                                            │
│ 新建 frontend/src/components/canvas/contents/QuestionListContent.tsx                                                       │
│                                                                                                                            │
│ - 按分类分组展示问题                                                                                                       │
│ - 每组显示核心问题 + 3 个变体（直接型/场景型/对比型）                                                                      │
│ - 显示问题分布统计                                                                                                         │
│                                                                                                                            │
│ 新建 frontend/src/components/canvas/contents/FetchResultsContent.tsx                                                       │
│                                                                                                                            │
│ - 表格形式: 问题 × 平台                                                                                                    │
│ - 每个单元格显示成功/失败状态 + 答案摘要                                                                                   │
│ - 顶部显示汇总统计（成功率、平台分布）                                                                                     │
│                                                                                                                            │
│ frontend/src/components/canvas/CanvasPanel.tsx                                                                             │
│                                                                                                                            │
│ - 在 renderContent switch 中添加 questionList 和 fetchResults case                                                         │
│                                                                                                                            │
│ Step 8: 前端 - 增强 WorkflowContent（A1/A2 Artifact）                                                                      │
│                                                                                                                            │
│ frontend/src/components/canvas/contents/WorkflowContent.tsx                                                                │
│                                                                                                                            │
│ 当前只显示图谱。增强为 图谱 + 结构化文档:                                                                                  │
│                                                                                                                            │
│ A1 增强:                                                                                                                   │
│ - 品牌档案卡片（品牌名、行业、定位、核心产品、目标受众）                                                                   │
│ - 竞品列表（名称、相关度评分、竞争类型、核心优势）                                                                         │
│ - BrandCompetitionGraph（已有）                                                                                            │
│                                                                                                                            │
│ A2 增强:                                                                                                                   │
│ - 画像卡片列表（画像名、描述、优先级、人口统计、使用场景）                                                                 │
│ - PersonaGraph（已有）                                                                                                     │
│                                                                                                                            │
│ Step 9: 前端 - TPAOR observation 阶段处理                                                                                  │
│                                                                                                                            │
│ frontend/src/hooks/useWebSocket.ts                                                                                         │
│                                                                                                                            │
│ - tpaor_update 事件处理中，observation 阶段（原始 JSON）默认折叠                                                           │
│ - 前端 conversationStore.ts 的 updateTPAOR 需要支持 observation 阶段                                                       │
│                                                                                                                            │
│ frontend/src/stores/conversationStore.ts                                                                                   │
│                                                                                                                            │
│ - currentTPAOR 添加 observation 字段                                                                                       │
│ - TPAORPhaseEntry 的 phase 类型添加 'observation'                                                                          │
│                                                                                                                            │
│ frontend/src/components/chat/TPAORCard.tsx                                                                                 │
│                                                                                                                            │
│ - phaseConfig 添加 observation 配置（绿色，眼睛图标，默认折叠）                                                            │
│                                                                                                                            │
│ ---                                                                                                                        │
│ 修改文件清单                                                                                                               │
│ 文件: backend/app/workflow/state.py                                                                                        │
│ 操作: 修改                                                                                                                 │
│ 说明: error_info Annotated reducer                                                                                         │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/nodes.py                                                                                        │
│ 操作: 修改                                                                                                                 │
│ 说明: A2 typo + A1/A2 goto + 删除 output_ready + 添加摘要                                                                  │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/nodes_a3.py                                                                                     │
│ 操作: 修改                                                                                                                 │
│ 说明: A3 goto + 删除 output_ready + 添加摘要                                                                               │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/nodes_a4.py                                                                                     │
│ 操作: 修改                                                                                                                 │
│ 说明: A4 goto + 删除 output_ready + 添加摘要                                                                               │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/nodes_a5.py                                                                                     │
│ 操作: 修改                                                                                                                 │
│ 说明: A5 goto + 删除 output_ready/complete + 添加摘要                                                                      │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/nodes_streaming.py                                                                              │
│ 操作: 修改                                                                                                                 │
│ 说明: response→observation 阶段重命名                                                                                      │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/events.py                                                                                       │
│ 操作: 修改                                                                                                                 │
│ 说明: 新增 send_step_complete_with_artifact                                                                                │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/graph.py                                                                                        │
│ 操作: 修改                                                                                                                 │
│ 说明: 添加 5 个 review 节点 + 重连边                                                                                       │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/summaries.py                                                                                    │
│ 操作: 新建                                                                                                                 │
│ 说明: 5 个摘要生成函数                                                                                                     │
│ ────────────────────────────────────────                                                                                   │
│ 文件: backend/app/workflow/nodes_review.py                                                                                 │
│ 操作: 新建                                                                                                                 │
│ 说明: 5 个 review 决策节点                                                                                                 │
│ ────────────────────────────────────────                                                                                   │
│ 文件: frontend/src/types/canvas.ts                                                                                         │
│ 操作: 修改                                                                                                                 │
│ 说明: 添加 questionList, fetchResults 类型                                                                                 │
│ ────────────────────────────────────────                                                                                   │
│ 文件: frontend/src/components/canvas/CanvasPanel.tsx                                                                       │
│ 操作: 修改                                                                                                                 │
│ 说明: 添加新类型渲染                                                                                                       │
│ ────────────────────────────────────────                                                                                   │
│ 文件: frontend/src/components/canvas/contents/QuestionListContent.tsx                                                      │
│ 操作: 新建                                                                                                                 │
│ 说明: A3 问题列表 Canvas                                                                                                   │
│ ────────────────────────────────────────                                                                                   │
│ 文件: frontend/src/components/canvas/contents/FetchResultsContent.tsx                                                      │
│ 操作: 新建                                                                                                                 │
│ 说明: A4 抓取结果 Canvas                                                                                                   │
│ ────────────────────────────────────────                                                                                   │
│ 文件: frontend/src/components/canvas/contents/WorkflowContent.tsx                                                          │
│ 操作: 修改                                                                                                                 │
│ 说明: 增强 A1/A2 结构化文档                                                                                                │
│ ────────────────────────────────────────                                                                                   │
│ 文件: frontend/src/stores/conversationStore.ts                                                                             │
│ 操作: 修改                                                                                                                 │
│ 说明: 添加 observation 阶段支持                                                                                            │
│ ────────────────────────────────────────                                                                                   │
│ 文件: frontend/src/hooks/useWebSocket.ts                                                                                   │
│ 操作: 修改                                                                                                                 │
│ 说明: observation 阶段映射                                                                                                 │
│ ────────────────────────────────────────                                                                                   │
│ 文件: frontend/src/components/chat/TPAORCard.tsx                                                                           │
│ 操作: 修改                                                                                                                 │
│ 说明: 添加 observation phaseConfig                                                                                         │
│ 验证方式                                                                                                                   │
│                                                                                                                            │
│ 1. 启动后端 + 前端                                                                                                         │
│ 2. 输入品牌名开始分析                                                                                                      │
│ 3. 验证每步:                                                                                                               │
│   - A1 完成 → Canvas 显示品牌图谱+档案+竞品列表 → Chat 显示格式化摘要 → 暂停等确认                                         │
│   - 确认后 → A2 决策 → A2 完成 → Canvas 显示画像图谱+卡片 → 暂停等确认                                                     │
│   - 确认后 → A3 决策 → A3 完成 → Canvas 显示问题列表 → 暂停等确认                                                          │
│   - 确认后 → A4 完成 → Canvas 显示抓取结果表 → 暂停等确认                                                                  │
│   - 确认后 → A5 完成 → Canvas 显示分析报告 → 暂停等确认 → 完成                                                             │
│ 4. TPAOR 中不再显示原始 JSON，只显示思考过程和格式化摘要                                                                   │
│ 5. 浏览器控制台无报错                                            
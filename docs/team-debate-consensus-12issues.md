# 团队 Debate 最终共识报告

参与成员：Marty Cagan (PM) · James Bach (QA) · Don Norman (UX) · Martin Fowler (Architect)
日期：2026-02-22
状态：已更新（#7 根据产品 Owner 修正重新设计，2026-02-22）

---

## 优先级总表（共识版）

| # | 问题 | 优先级 | 类型 |
|---|------|--------|------|
| 3 | 画像完成后自动触发模拟问题 | P0 | 核心流程 Bug |
| 4 | 确认按钮不悬浮/不可见 | P0 | 核心流程阻塞 |
| 5 | 画像选中交互混乱 | P0 | 核心流程阻塞 |
| 7 | Kimi/DeepSeek 抓取永远失败 | P0 | 核心功能失效 |
| 1 | 交付物列 icon/文字太小 | P1 | 可见性 |
| 2 | 品牌分析交付物名称/icon 错误 | P1 | 数据映射 Bug |
| 6 | A3 后生成空营销图谱 | P1 | 多余推送 |
| 8 | 抓取结果 Canvas 展示太乱 | P1 | 信息架构 |
| 9 | 历史对话数据丢失 | P1 | 持久化 Bug |
| 10 | 报告时生成营销图谱 | P1 | 多余推送 |
| 11 | 报告内容为空/建议不实操 | P1 | 数据质量 |
| 12 | 缺少 Light 模式 | P2 | 功能缺失 |

---

## 逐条共识与解决方案

### #1 交付物列 icon/文字太小（P1）

共识：ArtifactNav.tsx compact 模式 icon 仅 16px、文字 9px，深色背景对比度 3.4:1 未达 WCAG AA 标准（4.5:1）。

解决方案：
- icon 增大到 20px，文字增大到 12px
- 非活跃态颜色从 #A3A3A3 提升到 #D4D4D4
- 每个 tab 补充对应 content type 的 icon

---

### #2 品牌分析交付物名称/icon 错误（P1）

共识：后端 output_ready 事件中 type 被错误映射为 workflow，导致显示"流程+人头"icon。

解决方案：
- 检查 A1 节点 save_and_send_artifact() 调用，确保 output_type="report"、title="品牌分析报告"
- 前端 CanvasHeader.tsx 的 icon mapping 补全 report 类型

---

### #3 画像完成后自动触发模拟问题（P0）

Debate 结论：PM 认为只改 prompt 够了，Architect 最终裁定：Prompt 改 + 代码保底，两者都要。

根因（Architect 代码证据）：
- orchestrator_node.py:398："执行完一个步骤后，直接建议或执行下一步" → LLM 被指示跳过确认
- orchestrator_node.py:445：A2 tool_result 中 "建议下一步" → LLM 解读为"调用下一工具"

解决方案：
1. Prompt 修改（主要）：line 398 改为"执行完一个步骤后，使用 ask_user 询问用户是否继续"；line 445 的 A2 tool_result 改为"请使用 ask_user 询问用户下一步操作"
2. 代码保底（防 LLM 概率性忽略）：`_handle_tool_call()` A2 完成分支加 `state["awaiting_user"] = True`（约 5 行）

---

### #4 画像确认按钮不悬浮（P0）

共识：按钮在滚动区内部，用户需滚到底才能发现，违反系统状态可见性原则。UX 指出这是比 #5 更上游的阻塞。

解决方案：SelectionContent.tsx 改为 flex 布局，画像列表区 `overflow-auto flex-1`，底部确认栏 `sticky bottom-0 flex-shrink-0`，提取到滚动容器外部。

---

### #5 画像选中交互混乱（P0）

Debate 结论：QA 将评级从 P2 升级到 P0（原评级失误，未考虑错选后整条 A3→A4→A5 管道代价）。三方达成 P0 共识。

根因（UX + QA 证据）：
- TouchpointMapContent.tsx:81-86：点击节点只高亮详情，handleCheckChange 是独立 checkbox 操作
- 错选后 A3→A4→A5 耗时数分钟，不可在当前流程内撤回

解决方案：
1. Pipeline 模式下，点击管道中任意节点 = 选中整个管道（修改 handleNodeSelect）
2. 取消单独 checkbox 逻辑，改为整管道高亮选中态
3. checkbox 改为方形（UX 强调：圆形=单选，方形=多选，这是所有主流 UI 框架约定）
4. 支持多管道多选

---

### #7 Kimi/DeepSeek 抓取永远失败（P0）

⚠️ **此条目已根据产品 Owner 修正更新（2026-02-22）**

**原团队方案（已废弃）**：超时 15→90s；长期考虑 API 策略。

**产品 Owner 修正**：
1. 90s 不够，实际测试需要 180s+
2. Kimi/DeepSeek 没有 WebSearch API，核心价值是 Playwright 抓取答案 + 引用链接，不存在 API 替代方案
3. 引用链接是核心功能，必须打开引用列表并抓取所有链接

**最终方案（架构师 Martin Fowler 重设计，John Carmack 已实施）**：

超时分层设计：
```
外层 asyncio.wait_for:   200s  ← 总预算（nodes_a4.py）
  L1 page.goto:           30s  ← domcontentloaded（非 networkidle，SPA 心跳永不触发）
  L2 wait_for_selector:   15s  ← 找输入框等元素
  L3 生成等待:            120s  ← AI 实际生成时间
  L4 引用展开:             10s
  ──────────────────────────
  内层合计:              ~175s  < 200s ✓ 层级约束满足
```

实施变更（5个文件）：
- `constants.py`：kimi/deepseek: `60s → 200s`
- `nodes_a4.py`：删除硬编码 15s，改为 `_get_browser_timeout(platform)` 从 constants 读取；`BROWSER_MAX_RETRIES: 0 → 1`
- `playwright_client.py`：`networkidle → domcontentloaded`；`wait_for_selector: 30s → 15s`
- `kimi_handler.py`：生成完成检测改为内容稳定检测（连续2次长度相同）；引用提取：5个选择器 fallback + URL 清洗 + 日志
- `deepseek_handler.py`：生成完成检测改为 Playwright 原生等待"停止生成"按钮消失；引用提取：6个选择器 fallback + URL 清洗 + 日志

引用抓取核心改进：
- 不再 silent fail，失败时记录 WARNING 日志
- Kimi 5个候选选择器，DeepSeek 6个候选选择器，逐个尝试直到成功
- URL 清洗：过滤 `javascript:`、`#` 开头的无效链接

---

### #6 A3 后生成空营销图谱（P1）

共识：nodes_a3.py:162, 406 调用 `_push_touchpoint_map()`，A3 阶段只有结构无指标，前端渲染为空。

解决方案：移除 nodes_a3.py 中所有 `_push_touchpoint_map()` 调用（约 5 行删除）。

---

### #8 抓取结果 Canvas 展示太乱（P1）

新发现（UX）：后端已在 nodes_a4.py:746,784,833 返回 citations 字段，但前端 FetchResultsContent.tsx 零处引用，引用链接被完全丢弃。这对 AEO 产品的核心价值（分析 AI 引用来源）是严重的数据管道断裂。

解决方案，重新设计信息架构：
- 以问题为一级单位
- 下方按平台 Tab 展示完整答案（取消 line-clamp-3 截断）
- 每个答案下展示引用链接列表（渲染 citations 字段）
- 统计卡片可折叠，核心内容优先展示
- 预留答案正确性标注字段（未来功能）

---

### #9 历史对话数据丢失（P1）

Debate 结论：QA 确认两个问题都是真实存在的独立问题。Architect 最终裁定：后端是主因，先修后端。

两个独立问题：

| | 后端 MemorySaver | 前端 canvasStore |
|--|--|--|
| 根因 | graph.py:90 硬编码 `MemorySaver()`，进程重启即丢 | conversationStore.ts `create()` 无 persist |
| 触发 | 服务器重启/部署 | 浏览器刷新 |
| 修复 | graph.py 用 `get_checkpointer()` 替代（已写好，~1行） | 加 zustand persist middleware |

修复顺序：
1. P1-HIGH：后端换 `get_checkpointer()`（已有实现，1行改动）
2. P1-MED：补全 `rebuild_state_from_db()` 的 A2 数据恢复（当前遗漏 marketing_personas）
3. P2：前端 canvasStore 加 persist

---

### #10 报告时生成营销图谱（P1）

共识：与 #6 同源，nodes_a5.py:377-404 推送了 touchpointMap。

解决方案：移除 nodes_a5.py 中 touchpointMap 推送（约 5 行删除）。与 #6 一起做，一次清干净。

---

### #11 报告内容为空/优化建议不实操（P1）

共识：#7 未修复时 #11 的数据质量先天不足；同时 A5 prompt 对各 section 的要求不够具体。

解决方案：
1. 先修 #7（数据来源问题）
2. A5 prompt 重写：
   - 行业洞察：必须基于实际 fetch_results 数据，引用具体平台回答中的关键词
   - 平台分析：必须包含各平台的具体指标数字
   - 竞品对比：必须有量化对照表
   - 优化建议：遵循 EEAT 原则，分别说明：①做得好的具备什么特征（继续保持）②需要增强的具体场景/内容/数据方向
3. A5 输出校验：各 section 为空时返回错误而非空对象

---

### #12 Light 模式 / Dark 切换（P2）

共识：PM 和 UX 定 P2，QA 说 P3，PM 最终拍板 P2。理由：Dark 版本信息获取费劲，影响日常使用效率。

解决方案（工作量约 300+ 处替换，3天）：
1. 补全 CSS 变量系统（部分已有 var(--bg-primary) 等但不完整）
2. 定义 Light theme 变量集
3. 添加 theme toggle 组件 + localStorage 持久化
4. WorkflowContent（37处）、FetchResultsContent（25+处）等硬编码色值全部替换

---

## 实施顺序建议

**第一批 P0（本轮必做）**：
- ✅ #7 → Browser 超时+引用抓取重设计（已完成，2026-02-22）
- ⏳ #3 → Prompt + 代码保底（0.5天）
- ⏳ #4/#5 → 画像选中交互重构（1.5天）

**第二批 P1（紧跟）**：
- ⏳ #6/#10 → 移除营销图谱推送（0.5天，合并做）
- ⏳ #9 → 后端 checkpointer 修复（0.5天）
- ⏳ #8 → 抓取结果展示重构 + citations 渲染（2天）
- ⏳ #11 → A5 prompt 重写 + 数据校验（1天）
- ⏳ #1/#2 → 交付物列 UI 修正（0.5天，合并做）

**第三批 P2**：
- ⏳ #12 → Light 主题系统（3天）

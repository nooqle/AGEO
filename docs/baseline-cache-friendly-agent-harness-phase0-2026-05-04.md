# AGEO 提示词复用友好型 Harness Phase 0 基线记录（2026-05-04）

> 状态：Baseline  
> 分支：`codex/prompt-cache-harness-design`  
> 目的：在 Phase 1-2 改动前记录当前 orchestrator 的提示词、工具面、观测和回归入口。

---

## 1. 当前调用链

当前 orchestrator LLM 调用的核心链路是：

1. `build_orchestrator_prompt_assembly(state)` 组装 `PromptAssembly`
2. `build_orchestrator_system_prompt(state)` 调用 `assembly.render()` 生成完整 system prompt
3. `build_orchestrator_messages(state)` 生成历史消息
4. `build_agent_tools(state)` 生成工具清单
5. `model.stream(...)` 发送 system prompt、messages 和 tools
6. `record_llm_usage_async(...)` 记录 token、成本和基础 metadata

Phase 0 之前，运行时上下文、最近证据、待处理决策、技能上下文都在 `assembly.render()` 中进入 system prompt。

---

## 2. 当前 system prompt 变化来源

当前 system prompt 会受以下状态影响：

1. 会话状态：品牌档案、竞品、问题、抓取结果、报告、指标
2. 实体上下文：品牌名、官网、行业、竞品
3. 当前技能上下文：当前 skill、允许工具、前置条件、产出要求
4. 待处理决策：是否等待用户确认、候选操作
5. 最近证据包：当前抓取、当前产物、上传输入、历史资料结果
6. 历史资料可用性：可用来源、总量、覆盖月份、可对比轮次
7. 过往资料规划提示：是否应刷新历史结果
8. 指令防守提醒：提示词泄露请求或证据注入风险
9. 当前回合工具面约束：本次追问应优先或禁止的工具路径

结论：

> 当前 system prompt 不只是固定规则，还包含大量每轮都会变化的运行时信息。

---

## 3. 当前工具清单变化来源

`build_agent_tools(state)` 当前会根据 `_get_contextual_hidden_tool_names(state)` 过滤工具。

主要变化来源：

1. `headless_mode=true` 时隐藏 `ask_user`
2. session 被召回时隐藏 `knowledge_*`
3. 当前问题命中本次结果追问时隐藏部分历史资料工具
4. 当前问题应直接进入 `drill_down_analysis` 时隐藏泛化后续分析入口
5. 动态 public skill 来自 skill registry 和 assignment scope

结论：

> 当前工具清单是状态相关的；这对路由有帮助，但会影响提示词复用观测。

---

## 4. 当前 usage 观测

`LLMUsageRecord` 已记录：

1. provider
2. model_name
3. prompt_tokens
4. completion_tokens
5. total_tokens
6. cached_prompt_tokens
7. billable_prompt_tokens
8. latency_ms
9. estimated_cost
10. estimated_cost_cache_aware
11. extra_metadata

Phase 0 之前，orchestrator metadata 主要记录：

1. `streaming`
2. `message_count`
3. `tool_count`

缺口：

1. 不知道固定提示词是否变化
2. 不知道工具清单是否变化
3. 不知道本轮动态上下文长度
4. 不知道模型身份的统一字符串
5. 复用率低时难以定位原因

---

## 5. 固定回归场景

后续 Phase 1-2 至少覆盖以下场景：

### 场景一：新品牌完整分析

目标：

1. 首次输入品牌名后，仍能进入品牌分析路径
2. 不编造品牌结果
3. 不因本轮提醒插入影响工具调用

### 场景二：A4 失败后补采

目标：

1. A4 有失败项时仍能要求用户选择补采或继续分析
2. 不自动重新生成问题
3. 待处理决策能进入本轮提醒

### 场景三：用户追问历史结果

目标：

1. 用户问上一轮失败统计时，仍优先刷新权威历史结果
2. 不直接复述旧对话数字
3. 历史资料规划提示能进入本轮提醒

---

## 6. 测试入口

后端目标测试：

```powershell
pytest aeo-platform\backend\tests\test_harness_refactor_foundations.py -q
pytest aeo-platform\backend\tests\test_llm_task_routing.py -q
pytest aeo-platform\backend\tests\test_routing_matrix.py -q
python scripts\validate_change.py
```

编码安全检查：

1. 不用 PowerShell inline 写中文源码
2. 使用 `apply_patch`
3. 变更后扫描问号污染标记

---

## 7. Phase 1-2 保护原则

1. flag 默认关闭，默认生产行为不变
2. 不新增数据库字段
3. 不记录 system prompt 原文
4. 不改 A1/A3/A4/A5/A7 业务逻辑
5. 保留 `PromptAssembly.render()` 兼容旧路径


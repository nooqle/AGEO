# 置信度分析独立入口与能力收口设计

> 日期：2026-03-28
> 状态：Implemented（保留最小兼容别名）
> 目标：把“置信度分析”从节点后续动作收敛为一个独立输入模式，并清理当前 legacy tool / public skill / internal node 并存造成的概念混乱。

---

## 1. 一句话结论

`置信度分析` 应该成为聊天输入区中的一个独立工具模式，由主 orchestrator LLM 负责判断何时直接执行、何时 ask_user 确认；后端只保留一条清晰链路：

`工具模式 / 用户输入 -> 主 LLM 决策 -> confidence analysis skill -> executor node -> artifact`

其中：

1. `skill` 是平台能力定义
2. `executor node` 是 skill 的内部执行器
3. `tool` 只是主 LLM 调用该 skill 的入口名

---

## 2. 当前问题

### 2.1 同一能力有三套概念并存

设计启动前，“置信度分析”同时以三种形式存在：

1. legacy tool：`citation_confidence_analysis`
2. public skill：`confidence_signal_skill`
3. internal node：`a7_confidence_signal`

这导致两个问题：

1. 主 orchestrator 可能同时看到旧 tool 和新 skill tool，能力边界不清
2. 用户心智被误导成“这是某个节点后的可选步骤”，而不是“可以主动发起的独立能力”

### 2.2 用户心智与系统内部阶段耦合过重

当前文案和路由中仍存在：

1. “通常在 A5 报告生成后调用”
2. “A7 置信度信号”
3. “在某个节点完成后再做一次置信度评估”

这些表述都属于系统内部实现视角，不应该继续暴露给用户，也不应该成为 orchestrator 的主心智。

### 2.3 输入前没有能力选择入口

当前发现路径分散在：

1. A5 之后的 follow-up 选项
2. dashboard skill action
3. confidence artifact 内部的 extra evaluate

缺少一个像 Gemini 一样前置在输入区的能力入口，导致“主动使用置信度分析”的 discoverability 很弱。

### 2.4 表格解析链路已经存在，但没有统一进“置信度分析模式”

当前系统已经具备：

1. 附件上传
2. `table_intake_skill`
3. 表格识别结果为 `link_list` 时先 ask_user 确认

但这套链路还没有和“置信度分析工具模式”打通，结果是：

1. 同一类任务入口不统一
2. 主 LLM 无法利用“用户已经明确选择置信度分析模式”这一事实做更稳定决策

---

## 3. 设计原则

### 原则 1：用户只看见一个能力名

用户侧统一使用：

- `置信度分析`

用户不需要看见：

- `A7`
- `confidence signal`
- `citation_confidence_analysis`

### 原则 2：主 LLM 负责决策，程序负责提供事实

应该由主 orchestrator LLM 决策的是：

1. 现在该直接调用置信度分析 skill
2. 还是先 ask_user 确认
3. 还是告诉用户当前材料不足

应该由程序先整理成 facts 再提供给主 LLM 的是：

1. 当前是否选择了 `置信度分析` 工具模式
2. 用户本轮是否上传了附件
3. 附件是否已被识别为表格
4. 表格理解结果是否为 `link_list`
5. 当前会话是否已有可复用的 citation / fetch_results

### 原则 3：保留 `skill -> executor node`，删除 legacy tool 直连

最终关系应为：

1. `skill` 定义能力
2. `executor node` 执行能力
3. orchestrator 通过唯一 tool 入口调用 skill

不再保留：

`legacy tool -> node`

这样的并行直连链路。

### 原则 4：输入模式不等于立即执行

当用户选中输入区 pill `置信度分析` 时，表示：

1. 当前输入框进入“置信度分析任务模式”
2. 主 LLM 应优先围绕置信度分析解释和决策
3. 但系统仍要先理解材料来源，再决定是否直接执行

也就是说：

`pill` 表示的是任务意图边界，不表示材料已经确定。

---

## 4. 目标模型

## 4.1 用户可见模型

输入区下方新增 `工具` 入口，点击后弹出菜单。

第一阶段菜单仅包含：

1. `置信度分析`

选中后显示 pill：

- `置信度分析 ×`

点击 `×`：

1. 立即退出该模式
2. 恢复普通对话

### 交互语义

选中 `置信度分析` 后，输入框中的内容不再被简单理解为普通聊天文本，而是被理解为：

- “用户希望用于置信度分析的说明、链接、材料或指令”

---

## 4.2 主 LLM 的统一决策任务

当 `置信度分析` 模式开启时，主 LLM 要基于当前事实判断：

1. 用户是不是直接给了一个或多个链接
2. 用户是不是要求分析“刚才抓取出来的引用来源”
3. 用户是不是上传了一个表格，需要先走 `table_intake_skill`
4. 如果表格被识别为 `link_list`，是否需要先 ask_user 确认
5. 是否已经有足够材料直接调用置信度分析 skill

### 允许的材料来源

主 LLM 在该模式下可选择的材料来源包括：

1. 用户直接输入的单个链接
2. 用户直接输入的多个链接
3. 用户直接输入的一段文本
4. 当前会话中已有的 citation / fetch_results
5. 用户上传表格后解析出来的链接清单

---

## 4.3 程序提供给主 LLM 的事实

建议通过结构化 state / system prompt facts 提供以下信息：

1. `selected_tool_mode = confidence_analysis | null`
2. `has_current_attachments = true | false`
3. `pending_table_intake = ...`
4. `table_intake_result.table_kind = question_list | brand_competitor_info | link_list | unknown`
5. `import_source_metadata.imported_link_list_count`
6. `has_reusable_fetch_results = true | false`

主 LLM 不需要自行猜测这些事实。

---

## 5. 命名收口

## 5.1 用户侧文案

统一保留：

1. `置信度分析`：工具模式 / 菜单项
2. `置信度报告`：结果标题

## 5.2 orchestrator 唯一入口名

主 LLM 只看到一个能力入口：

- `confidence_analysis`

## 5.3 内部能力命名

建议统一为：

1. `confidence_analysis_skill`
2. `confidence_analysis_executor`
3. `report_kind = confidence_analysis`
4. `artifact_kind = confidence_analysis`

当前代码中，以下旧命名仅作为兼容别名保留，不再作为主路径：

1. `citation_confidence_analysis`
2. `confidence_signal_skill`
3. `a7_confidence_signal`
4. `confidence_signal`

都应逐步退出对外契约。

---

## 6. 删除与保留

## 6.1 删除

应删除或停止对外暴露：

1. orchestrator 中的 legacy tool `citation_confidence_analysis`
2. 旧的 tool display / fallback / completion reply 对旧名的分支
3. “通常在 A5 后调用”这类绑定文案
4. 把 `A7` 作为用户可见能力名称的表达

## 6.2 保留

应保留：

1. 现有置信度打分与 artifact 生成逻辑
2. 现有 `table_intake_skill`
3. link list 识别后 ask_user 确认的表格处理机制
4. Canvas 中现有置信度报告渲染和 extra evaluate 逻辑

---

## 7. 输入模式下的决策流程

### 7.1 默认流程

当 `置信度分析` pill 激活时：

1. 若存在待理解表格附件：
   - 主 LLM 应优先调用 `table_intake_skill`
2. 若表格识别结果为 `link_list`：
   - 主 LLM 先解释“识别到这是一份链接清单”
   - 然后调用 `ask_user` 确认是否继续做置信度分析
3. 若用户直接输入链接 / 文本：
   - 主 LLM 可直接调用置信度分析 skill
4. 若用户表达“分析刚才那些引用/来源”：
   - 主 LLM 应优先使用当前会话已有 citation / fetch_results
5. 若材料不足：
   - 主 LLM 应要求用户补充链接、文本，或明确选择使用当前会话数据

### 7.2 表格解析的特殊约束

对于表格解析出的 `link_list`：

1. 不应自动静默进入其他分析流程
2. 不应默认解释为 A3 question_list 或 A1 brand info
3. 在 `置信度分析` 模式下，确认文案应优先围绕“是否对这些链接做置信度分析”组织

也就是说：

`link_list -> ask_user -> confidence_analysis skill`

应成为这一模式下的默认链路。

---

## 8. 实施顺序

### Phase 1：收口对外契约

1. 移除 orchestrator 对 legacy confidence tool 的公开暴露
2. 让 orchestrator 只保留 skill 入口
3. 保持内部 executor node 不变

### Phase 2：加入输入区工具模式

1. 输入区下方增加 `工具` 入口
2. 菜单内加入 `置信度分析`
3. 选中后显示 pill `置信度分析 ×`

### Phase 3：把工具模式接入主 LLM 决策

1. 前端 websocket payload 带上 `tool_mode`
2. 后端把 `tool_mode` 写入 state / prompt facts
3. 主 orchestrator 根据该事实决定 skill 或 ask_user

### Phase 4：命名统一

1. 把 `confidence_signal_*` 系列命名逐步迁移为 `confidence_analysis_*`
2. 同步前端 report kind / artifact kind / adapter
3. 更新测试与文档

---

## 9. 本阶段不做的事

本阶段不做：

1. 新开一级页面
2. 重写置信度打分算法
3. 重写 Canvas 报告 UI
4. 新增独立 Agent 身份

本阶段只做：

1. 入口前置
2. 概念收口
3. 主 LLM 决策权明确化

---

## 10. 最终结构

最终希望系统收敛为：

1. 用户入口：`工具 -> 置信度分析`
2. 用户输入模式：`置信度分析 pill`
3. 主编排：orchestrator LLM 决定 skill / ask_user
4. public capability：`confidence_analysis_skill`
5. internal execution：`confidence_analysis_executor`
6. result artifact：`置信度报告`

如果这个结构成立，后续再扩展更多输入区工具模式时，也可以沿用同一套模式，而不必重复制造“tool / skill / node 多重命名并存”的问题。

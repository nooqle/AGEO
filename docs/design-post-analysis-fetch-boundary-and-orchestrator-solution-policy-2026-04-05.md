# post_analysis_skill / answer_fetch 边界修正与 Orchestrator 解决方案化策略

## 背景

当前系统存在两类已经影响可用性的边界问题：

1. `post_analysis_skill` 混入了 `selective_refetch`，导致“分析已有结果”和“重新采集数据”混在一起。
2. orchestrator 在前置条件不满足或步骤失败时，过于倾向输出“无法完成”“不能做”，而不是主动给出可执行的解决路径。

这两个问题叠加后，会让系统表现得：

- 能力边界混乱
- 路由不稳定
- 用户感知上“很死”“很傻”
- follow-up、重跑、换模式采集的意图难以正确表达

本设计用于把这两类问题一起收口。

## 目标

本次修正只做三件事：

1. 明确 `post_analysis_skill` 是“对已有结果做分析、提取、解释、对比”的只读能力。
2. 明确 `answer_fetch` 是唯一的数据采集入口；局部重跑、全量重跑、模式切换都属于 `fetch` 参数，不再存在 `refetch` 这个独立能力概念。
3. 明确 orchestrator 在阻塞、失败、缺条件时，默认输出建设性方案，而不是机械拒绝。

## 为什么当前 workflow 会显得“太死”

当前用户感知上的“太死”，并不只是因为文案生硬，而是三类问题叠加：

1. 能力边界混乱  
   当 `post_analysis_skill` 同时承担分析和重抓时，orchestrator 很难稳定判断“这是读已有结果”还是“重新拿数据”。

2. 运行时 guard 只会拦，不会解  
   现在不少 guard 在发现前置条件缺失后，只告诉 orchestrator “不能做”，却没有统一要求它继续给出替代路径。

3. 用户可见解释仍偏系统口吻  
   即使路由是对的，如果回复停在“无法完成”“不能执行”，用户也会觉得系统只会挡路，不会解决问题。

因此，本次修正的目标不是放松所有 guard，而是把默认策略从“阻塞优先”改成“方案优先”：

- 继续保留 deterministic guard
- 但 guard 触发后，必须产出明确下一步
- 让 orchestrator 更像解决问题的顾问，而不是流程闸门

## 非目标

本次不做以下事情：

- 不引入新的 public skill
- 不重做 A4/AIO runtime
- 不做大规模 prompt 重写
- 不新增复杂的 fetch 策略 DSL

## 一、边界重定义

### 1. post_analysis_skill

`post_analysis_skill` 的正式定位：

- 对已有结果做深入分析
- 对已有结果做差异比较
- 对已有结果做结论解释、风险提取、证据归因

它只消费已有材料，例如：

- `fetch_results`
- `metrics`
- `report`
- `confidence_signal`
- `history comparison result`

它不重新采集任何外部数据。

### 2. answer_fetch

`answer_fetch` 的正式定位：

- 唯一的数据采集入口

它统一负责：

- 首次抓取
- 局部重跑
- 全量重跑
- `fast -> full`
- `API -> 浏览器`
- 复用当前问题集重跑
- 基于上传问题集重跑

### 3. refetch

`refetch` 不再作为以下任何东西存在：

- public skill
- public tool
- orchestrator 能力名
- follow-up mode

`refetch` 如果还需要存在，只允许作为内部实现或日志术语，例如：

- fetch 的局部重跑分支
- A4 内部 merge/replace 策略

但它不应再暴露到能力建模层。

## 二、能力路由规则

### 1. 用户是在“问已有结果”

路由到 `post_analysis_skill`。

典型表达：

- “详细解释一下这次结果”
- “为什么 DeepSeek 表现差”
- “对比最近两次变化”
- “哪些引用最危险”

### 2. 用户是在“要求重新拿数据”

统一路由到 `answer_fetch`。

典型表达：

- “重新抓一遍”
- “只重跑 Kimi”
- “这次换成浏览器”
- “上次是 fast，这次 full”
- “所有平台重新跑”

### 3. 局部 / 全量不是能力边界，而是 fetch 参数

例如：

- `answer_fetch(platforms=["kimi"], fetch_mode="fast")`
- `answer_fetch(platforms=["doubao","kimi","deepseek"], fetch_mode="full")`
- `answer_fetch(fetch_mode="full")`

如果系统要复用当前问题集，这是 `answer_fetch` 的既有行为，不需要新的 public capability 名称。

## 三、对现有实现的修正原则

### 1. post_analysis_skill 保留的分析模式

保留：

- `drill_down`
- `compare_snapshots`

移除：

- `selective_refetch`

### 2. skill registry / contract / alias

必须同步收口：

- `post_analysis_skill` 的描述中删除“重抓”
- skill contract 的 `allowed_tools` 删除 `selective_refetch`
- legacy alias 中删除 `selective_refetch -> post_analysis_skill`

### 3. follow-up executor

`post_analysis_executor` 不再路由到任何重抓分支。

如果用户请求的是“重新抓取数据”，应由 orchestrator 直接转到 `answer_fetch`。

### 4. A4 现有 selective merge 逻辑

如果 A4 内部仍需要局部替换 / merge，这是 A4 的内部执行细节，不影响本次边界修正。

也就是说：

- 可以保留 A4 内部“按平台重跑并合并”的实现
- 但不能继续通过 `selective_refetch` 这个能力名触发它

### 5. Orchestrator 的新默认心智

orchestrator 以后遇到阻塞时，优先做下面三件事：

1. 明确指出当前缺什么事实或前置条件  
2. 说明为什么这个缺口会影响当前动作  
3. 直接给出 1-3 个可执行方案

这意味着 workflow 仍然是有阶段约束的，但不再是“只会拒绝”的刚性流程。

## 四、Orchestrator 解决方案化策略

### 1. 当前问题

当前 orchestrator 的失败表达偏“流程阻塞式”：

- “无法完成”
- “不能执行”
- “做不了”

这类表达的问题不是事实错误，而是：

- 没有给用户下一步
- 没有把系统限制翻译成解决路径
- 会让用户感知系统在推脱

### 2. 新策略

以后 orchestrator 遇到缺条件、失败、阻塞时，默认采用：

`事实说明 + 造成原因 + 可执行方案`

而不是直接停在“无法完成”。

### 3. 统一输出原则

禁止只输出：

- “当前无法完成”
- “这个做不了”
- “不能执行”

必须补出至少一个建设性方案，优先级如下：

1. 自动可执行的下一步
2. 可选的替代路径
3. 用户需要补充的信息

### 4. 典型改写规则

#### A4 前置条件缺失

不要说：

- “无法执行 answer_fetch”

改成：

- “现在还不能开始抓取，因为当前还没有可用的问题集。下一步我可以先帮您生成基线问题，或者如果您已经有问题列表，也可以直接导入后开始抓取。”

#### A4 抓取失败

不要说：

- “抓取失败，无法继续”

改成：

- “这轮抓取没有拿到稳定结果，但问题集仍然可复用。下一步可以直接重试当前模式，也可以改成完整浏览器模式重跑；如果您只想先验证某个平台，也可以只跑该平台。”

#### post_analysis 输入不足

不要说：

- “无法做深入分析”

改成：

- “当前已有结果不足以支持这类深入分析。更合适的下一步是先补抓相关平台的数据，或先生成完整报告后再继续追问。”

## 五、中文输出策略

orchestrator 的对外输出必须统一使用中文。

包括：

- 对用户的自然语言回复
- 对用户可见的 thought / progress 文本
- Prompt section 标题
- 失败提示与恢复建议

系统内部允许保留英文代码标识，但不得直接把英文主导内容流式展示给用户。

## 六、实施范围

本次实现至少覆盖以下文件：

- `app/services/skill_contracts.py`
- `app/services/skill_registry_service.py`
- `app/services/skill_invocation_service.py`
- `app/workflow/nodes_followup.py`
- `app/workflow/orchestrator_node.py`
- `prompts/general_react_agent.md`
- 相关测试文件

## 七、验收标准

### 架构验收

- `post_analysis_skill` 不再包含任何“重抓/重跑”描述
- `selective_refetch` 不再作为 public capability 被引用
- 所有重跑请求统一通过 `answer_fetch`

### 行为验收

- 用户要求“只重跑某个平台”时，orchestrator 路由到 `answer_fetch`
- 用户要求“全部重新抓取并换浏览器模式”时，orchestrator 路由到 `answer_fetch`
- 用户要求“详细解释这次结果”时，orchestrator 路由到 `post_analysis_skill`

### 体验验收

- 阻塞/失败回复必须给出建设性下一步
- 用户可见输出不出现英文主导 thought

## 八、结论

本次修正的核心不是“把 selective_refetch 换个地方放”，而是：

- 删除 `refetch` 作为独立能力的错误建模
- 把“重新拿数据”统一还原为 `fetch`
- 把 orchestrator 从“流程守门员”拉回“解决方案提供者”

这两件事一起完成后，系统的能力边界和用户感知都会明显变稳。

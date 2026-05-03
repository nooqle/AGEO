# AGEO 提示词复用友好型 Harness 设计（2026-05-03）

> 状态：Draft  
> 目标读者：产品、架构、后端、前端都能看懂  
> 背景来源：Claude Code 文章《Lessons from building Claude Code: Prompt caching is everything》  
> 本文目标：把“提示词复用”这件事讲清楚，并给出 AGEO/Specta 可以落地的 5 项改进。

---

## 1. 先用人话说明这件事

大模型每次回答前，都要重新读一遍我们给它的内容：

1. 系统规则
2. 工具说明
3. 当前项目背景
4. 历史对话
5. 当前这一轮用户说了什么

如果前面很长一段内容每次都一模一样，模型服务商可以直接复用之前算过的结果。这样会更快，也更便宜。

可以把它理解成：

> 每次开会前，大家不需要从公司章程第一页重新读起。  
> 固定章程保持不变，只把“今天的新情况”补充到最后。

这里的“固定章程”就是稳定的系统规则和工具说明。  
“今天的新情况”就是当前会话状态、刚抓到的证据、用户刚做的选择。

如果我们每一轮都改“固定章程”，系统就没法复用之前的计算。结果是：

1. 调用更慢
2. 成本更高
3. 长链任务越跑越贵
4. 缓存命中率不稳定，问题也更难排查

---

## 2. 这对 AGEO 为什么重要

AGEO/Specta 不是普通聊天机器人。我们的任务通常很长：

1. A1 先识别品牌和竞品
2. A3 生成问题
3. A4 去多个 AI 平台抓回答
4. A5/A7 生成报告和置信度判断
5. 用户还会继续追问、补采、导出、对比历史

这类流程越长，越需要控制成本和速度。

现在项目已经有一些正确基础：

1. `PromptAssembly` 已经把提示词拆成几个区块
2. `orchestrator_context_packets.py` 已经把运行时上下文变成结构化对象
3. `LLMUsageRecord` 已经记录了缓存命中的 token 和缓存感知成本

但目前还有一个核心问题：

> 我们已经会“整理上下文”，但还没有完全按“可复用”来安排上下文。

通俗地说：

> 我们现在有一个很好的资料夹，但每次开会前还是会把资料夹前几页重写一遍。

---

## 3. 设计目标

本设计不追求重写整套 Agent 系统。

目标只有一个：

> 让 AGEO 的长链 Agent 运行更稳定、更便宜、更快，同时不牺牲现有 Agent-first 架构。

具体目标：

1. 固定内容尽量固定
2. 临时内容尽量放到后面
3. 工具清单尽量稳定
4. 同一任务尽量不换模型
5. 把提示词复用率纳入正式观测

---

## 4. 总体方案

一句话方案：

> 把“永远不怎么变的规则”放在最前面，把“当前这一轮才知道的信息”放在后面，并且不要在任务中途随便换工具和模型。

目标结构如下：

```text
稳定部分（尽量每轮一样）
  1. Specta 固定身份、语言、安全和流程原则
  2. 稳定工具清单
  3. 稳定技能入口说明

动态部分（每轮可以变化）
  4. 当前会话状态
  5. 当前品牌、当前报告、最近证据
  6. 待用户确认事项
  7. 本轮用户新消息
```

现在最关键的变化是：

> 动态部分不要继续塞进系统提示词前面，而是作为“本轮提醒”追加到消息末尾。

---

## 5. 五项改进设计

### 5.1 改进一：把提示词分成“固定规则”和“本轮信息”

#### 现在的问题

当前 orchestrator 会把很多运行时信息一起 render 到 system message 里，例如：

1. 当前会话状态
2. 当前实体上下文
3. 当前技能上下文
4. 最近证据包
5. 待处理决策

这些信息本来就会经常变化。  
如果它们每轮都在 system message 里变化，前面的内容就不稳定，复用效果会变差。

#### 设计方案

把 `PromptAssembly` 的输出拆成两类：

1. `固定系统提示词`
   - 角色
   - 语言要求
   - 安全规则
   - 高层流程规则
   - 稳定工具使用原则

2. `本轮运行提醒`
   - 当前完成了什么
   - 当前缺什么
   - 当前是否等待用户确认
   - 最近证据是什么
   - 当前建议优先走哪个动作

建议接口形态：

```python
class OrchestratorPromptBundle:
    static_system_prompt: str
    runtime_reminder_message: str
```

调用模型时变成：

```python
messages = [
    {"role": "system", "content": static_system_prompt},
    *history_messages,
    {"role": "user", "content": runtime_reminder_message},
    {"role": "user", "content": latest_user_message},
]
```

这里的 `runtime_reminder_message` 可以用类似标签包起来：

```text
<本轮系统提醒>
当前已有品牌分析结果；最近 A4 抓取仍有失败项；需要先让用户选择是否补采。
</本轮系统提醒>
```

这不是把系统规则交给用户，而是让模型在本轮末尾看到一段结构化提醒。  
真正的固定规则仍在 system message 里。

#### 落地改动

1. 保留现有 `PromptAssembly`
2. 新增 `render_static_system_prompt()`
3. 新增 `render_runtime_reminder_message()`
4. `build_orchestrator_system_prompt()` 先只返回固定规则
5. `build_orchestrator_messages()` 负责追加本轮提醒

#### 验收标准

1. 同一任务连续多轮时，固定系统提示词 hash 不变
2. 当前状态变化只影响本轮提醒，不影响固定系统提示词
3. 现有路由测试继续通过

---

### 5.2 改进二：不要按状态增删工具，改成“工具稳定 + 规则限制”

#### 现在的问题

现在系统会根据状态隐藏一些工具。比如：

1. headless 模式隐藏 `ask_user`
2. 当前追问命中本次结果时隐藏部分 `knowledge_*`
3. 特定场景下隐藏泛化后续分析入口

这个做法能减少模型误选工具，但会让工具清单经常变化。

工具清单一变，模型服务商就更难复用前面内容。

#### 设计方案

工具清单尽量保持稳定。  
不想让模型用某个工具时，不把工具删掉，而是在本轮提醒里说明：

```text
当前是 headless 定时任务，不能等待用户确认；不要调用 ask_user。
如果仍调用 ask_user，系统会返回 capability_blocked。
```

也就是说：

1. 工具一直在那里
2. 当前能不能用，由 harness 判断
3. 模型误调时，harness 返回明确错误，而不是让工具清单每轮变化

#### 推荐新增结果类型

```python
CapabilityBlockedResult(
    tool_name="ask_user",
    reason="当前任务是 headless 模式，不能等待用户确认",
    suggested_next_actions=["直接给出可执行方案", "选择自动恢复路径"],
)
```

#### 落地改动

1. `build_agent_tools()` 默认返回稳定工具清单
2. `_get_contextual_hidden_tool_names()` 逐步改名为 `_get_contextual_tool_constraints()`
3. 工具执行前增加统一 gate：`validate_tool_available_in_current_state()`
4. 被禁止时返回结构化 blocked result

#### 验收标准

1. 同一个 session 内工具数量和工具 schema 默认不变
2. 原来依赖“隐藏工具”避免误路由的场景，仍能被本轮提醒和 gate 拦住
3. 模型误调受限工具时，用户不会看到生硬报错，而是得到可执行解释

---

### 5.3 改进三：技能的动态策略不要写进工具说明

#### 现在的问题

当前 skill tool definition 会把一些动态内容拼进工具 description，例如：

1. package hint
2. prompt overlay
3. 当前策略补充
4. profile 列表

这些内容对模型有帮助，但如果它们进入工具说明，工具说明就会经常变化。

工具说明属于模型请求前部。它一变，提示词复用就受影响。

#### 设计方案

工具说明只放稳定入口：

```text
analysis_report_skill：生成分析报告。
```

动态策略放进“当前技能上下文”：

```text
当前技能：analysis_report_skill
当前策略：本次优先输出品牌全景报告，重点解释提及率、官网引用率和高风险场景。
可用 profile：标准报告、轻量报告、法务友好报告。
```

这样：

1. 工具入口稳定
2. 策略仍然能被模型看到
3. 未来不同客户、不同品牌的策略变化不会污染工具 schema

#### 落地改动

1. `build_skill_tool_definition()` 只输出稳定 description 和 parameters
2. `prompt_overlay`、profile 列表、package hint 移入 `ActiveSkillPacket`
3. `render_active_skill_packet()` 负责把这些动态内容放进本轮提醒

#### 验收标准

1. 修改 skill profile 后，工具 schema hash 不变
2. 模型仍能在本轮提醒里看到当前策略
3. 自定义 skill 不会导致工具列表频繁抖动

---

### 5.4 改进四：同一个任务尽量锁定同一个模型

#### 现在的问题

不同模型之间不能共享提示词复用结果。  
如果同一个长任务中途换模型，之前积累的复用优势会丢掉。

当前项目已经按任务类型做了模型路由，这是正确方向。  
但还需要进一步明确：

> 一个 task run 开始后，orchestrator 使用哪个模型，应尽量固定。

#### 设计方案

任务启动时记录本次使用的模型：

```text
task_run.orchestrator_provider = deepseek
task_run.orchestrator_model = deepseek-v4-pro
task_run.orchestrator_model_locked = true
```

后续同一 task run 继续调用 orchestrator 时，优先使用这个已锁定模型。

如果必须换模型，要把它视为一次明确事件：

1. 记录原因
2. 记录从哪个模型换到哪个模型
3. 重新计算成本和复用影响
4. 必要时让子任务承接，而不是让父 orchestrator 悄悄换

#### 允许换模型的情况

1. 原模型不可用
2. 当前任务明确进入另一个执行器，例如短 JSON 生成
3. 人工配置强制切换
4. 成本策略明确要求新建子任务处理

#### 落地改动

1. 在 task run 或 session runtime state 中记录模型锁定信息
2. `get_orchestrator_llm_model()` 支持接收 locked model
3. fallback 发生时写入 usage metadata
4. 控制面展示模型切换次数

#### 验收标准

1. 同一个 orchestrator run 默认不隐式切模型
2. fallback 有日志、有 usage metadata
3. 控制面能看到模型切换带来的成本和延迟变化

---

### 5.5 改进五：把提示词复用率变成正式监控指标

#### 现在的问题

项目已经记录：

1. `cached_prompt_tokens`
2. `billable_prompt_tokens`
3. `estimated_cost_cache_aware`

但这些还偏“记录”。  
我们还没有把它变成日常运维会关注的指标。

#### 设计方案

每次 LLM 调用都补充几个字段：

```text
static_prompt_hash：固定系统提示词指纹
tool_surface_hash：工具清单指纹
model_identity：模型身份
runtime_context_size：本轮动态上下文长度
cache_hit_ratio：提示词复用率
```

人话解释：

1. `static_prompt_hash`：固定规则有没有变
2. `tool_surface_hash`：工具清单有没有变
3. `model_identity`：是不是换模型了
4. `runtime_context_size`：本轮临时信息是不是太长
5. `cache_hit_ratio`：这轮到底复用了多少

#### 控制面建议展示

按以下维度展示：

1. 最近 24 小时总提示词复用率
2. 按模型拆分
3. 按步骤拆分：orchestrator、A1、A4、A5、A7
4. 按 skill 拆分
5. 最近 cache hit 明显下降的 session

#### 告警建议

先不用复杂告警，先做轻量规则：

1. orchestrator 连续 20 次调用复用率低于目标值
2. 工具清单指纹在同一 session 中变化超过 2 次
3. 固定系统提示词指纹在同一版本部署后频繁变化
4. runtime context 长度超过预算

#### 落地改动

1. `record_llm_usage_async()` 增加 metadata
2. `LLMUsageService.get_observability_snapshot()` 返回 hash 和复用率趋势
3. 控制面增加“提示词复用”模块
4. `scripts/validate_change.py` 可选检查固定 prompt hash 是否意外变化

#### 验收标准

1. 能按 session 解释为什么复用率低
2. 能区分是工具变了、系统提示词变了、模型变了，还是动态上下文太长
3. 复用率下降不再只能靠猜

---

## 6. 推荐实施顺序

### 第一阶段：先观测，不改行为

目标：不影响现有功能，先知道问题在哪里。

改动：

1. 增加 `static_prompt_hash`
2. 增加 `tool_surface_hash`
3. 增加 `runtime_context_size`
4. usage metadata 写入这些字段
5. 控制面或日志能查看

为什么先做这个：

> 先量出来，再决定哪里最值得改。

### 第二阶段：拆分固定提示词和本轮提醒

目标：最大程度稳定 system message。

改动：

1. `PromptAssembly` 增加固定/动态 render
2. runtime packets 改为本轮提醒
3. 补充 prompt assembly 测试

这是收益最大的阶段。

### 第三阶段：稳定工具清单

目标：减少工具面变化。

改动：

1. 工具默认不按状态隐藏
2. 上下文限制转为本轮提醒
3. 工具执行前增加 capability gate

### 第四阶段：稳定技能说明

目标：减少 skill 配置变化对工具 schema 的污染。

改动：

1. 工具 description 只保留稳定能力说明
2. 动态策略进入 ActiveSkillPacket
3. profile / prompt overlay 不再直接拼工具说明

### 第五阶段：模型锁定和告警

目标：让长任务模型选择更可解释。

改动：

1. task run 记录模型锁定信息
2. fallback 写入原因
3. 控制面展示切换次数和成本影响
4. 低复用率告警

---

## 7. 对现有架构的影响

### 对 Orchestrator 的影响

Orchestrator 的职责不变，仍然负责决定下一步。

变化是：

> Orchestrator 不再每轮背一大包动态状态，而是读取固定规则，再看本轮提醒。

### 对 Skill 的影响

Skill 仍然是能力合同。

变化是：

> Skill 的入口说明更稳定，动态策略从工具说明搬到技能上下文。

### 对 Tool 的影响

Tool 仍然是可调用动作。

变化是：

> Tool 清单更稳定，能不能用由执行前 gate 判断。

### 对 Harness 的影响

Harness 会变得更像真正的运行外壳：

1. 管理固定提示词
2. 管理本轮提醒
3. 管理工具可用性
4. 管理模型锁定
5. 管理提示词复用观测

这符合我们之前的 Agent-first 原则：  
业务判断交给 orchestrator，确定性治理交给 harness。

---

## 8. 风险和处理方式

### 风险一：工具不隐藏后，模型误调用更多

处理方式：

1. 本轮提醒写清楚当前不能用什么
2. 工具执行前加 gate
3. gate 返回可执行建议
4. 对误调用做测试覆盖

### 风险二：本轮提醒从 system message 移出去后，模型不重视

处理方式：

1. 固定 system prompt 明确说明“本轮系统提醒优先级高”
2. 本轮提醒使用固定标签
3. 对关键场景保留 deterministic guard，不只靠模型自觉

### 风险三：hash 和指标增加后，短期看起来更复杂

处理方式：

1. 第一版只进 metadata 和日志
2. 控制面只展示最关键 3 个数字
3. 等数据稳定后再做告警

### 风险四：模型锁定影响 fallback 灵活性

处理方式：

1. 不是禁止 fallback，而是禁止“无记录地悄悄 fallback”
2. fallback 仍可发生，但必须留下原因和影响

---

## 9. 不建议做的事

1. 不建议为了提示词复用，把所有动态状态都藏起来不给模型看
2. 不建议一次性重写 orchestrator
3. 不建议立刻删除 `_get_contextual_hidden_tool_names`
4. 不建议为了稳定工具清单而放弃工具前置条件
5. 不建议只看 token 成本，不看时延和路由正确率

---

## 10. 最小可执行方案

如果只做一个最小版本，建议这样做：

1. 新增提示词和工具清单 hash
2. 把 usage metadata 记录完整
3. 将 `PromptAssembly` 拆成固定规则和本轮提醒
4. 先只在 orchestrator 上试，不动 A1/A4/A5/A7
5. 用 3 类真实场景验证：
   - 新品牌完整分析
   - A4 失败后补采
   - 用户追问历史结果

最小验收：

1. 功能行为不退化
2. 固定系统提示词在同一部署版本内保持稳定
3. 工具清单变化能被观测到
4. 复用率下降时能定位原因

---

## 11. 术语表

### 提示词复用

英文常叫 prompt caching。  
意思是：前面一大段完全一样的输入，模型服务商可以复用之前算过的结果。

### 固定系统提示词

长期不怎么变的规则。  
比如：Specta 的角色、语言要求、安全要求、基本流程原则。

### 本轮提醒

这一轮才有的信息。  
比如：当前品牌是谁、刚抓取失败了几个平台、是否正在等待用户确认。

### 工具清单

模型可调用的动作列表。  
比如：品牌分析、问题生成、答案抓取、报告生成、知识查询。

### 工具清单指纹

把工具清单算成一个短标识。  
如果标识变了，说明工具清单变了。

### 固定提示词指纹

把固定系统提示词算成一个短标识。  
如果标识变了，说明固定规则变了。

### 复用率

本轮提示词里，有多少输入被成功复用了。  
复用率越高，通常越省钱、越快。

---

## 12. 最终结论

AGEO 现在已经有 Agent-first 的基础，也已经开始有上下文协议和成本观测。

下一步不是写更多提示词，而是让运行外壳更会“安排信息”：

1. 固定规则固定住
2. 临时状态放后面
3. 工具入口保持稳定
4. 技能策略从工具说明中搬出来
5. 模型选择和复用率都要可观测

如果这 5 点落地，AGEO 的长链分析任务会更适合规模化运行：  
更少无谓成本，更少缓存抖动，更容易解释为什么某次任务慢、贵或路由不稳定。


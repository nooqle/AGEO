# Orchestrator Context Protocol 设计（2026-04-04）

> 版本：v1.0
> 日期：2026-04-04
> 状态：Approved For Initial Implementation
> 范围：`codex/validation-retro-harness`

---

## 1. 背景

当前 AGEO 的 orchestrator 已经完成了 sectioned prompt assembly，但 runtime context 仍主要通过若干自然语言 summary builder 直接拼接到 prompt 中：

1. `_build_orchestrator_data_status`
2. `_build_orchestrator_entity_context`
3. `_build_context_summary`
4. `_build_recent_knowledge_context`
5. `_build_knowledge_planning_hint`

这种方式已经比单块 giant prompt 稳定，但仍存在三个问题：

1. context 的“采集”和“呈现”没有分层，builder 直接输出自然语言
2. 没被写进 summary 的事实，模型基本看不到
3. orchestrator context 还没有形成正式协议，后续 AIO / follow-up / history 继续扩展时容易回到散落 if/else 和 prompt patch

---

## 2. Claude Code 对照结论

Claude Code 的 context 设计不是“写更多 prompt”，而是把 context 做成协议层：

1. `systemPrompt`
2. `userContext`
3. `systemContext`
4. `message history`
5. `attachments / memory`
6. `compaction / cache`

其关键特点是：

1. 先区分上下文类型，再做注入
2. context 可以被缓存、压缩和按层拼装
3. message stream 是一等公民

AGEO 不适合直接照搬 `message-first`，因为系统本质是 workflow-heavy、state-heavy。  
但 AGEO 非常适合借鉴 Claude Code 的另一点：

`让 context 先成为协议对象，再成为 prompt 文本。`

---

## 3. 目标

本次改造目标不是重写 orchestrator，也不是把 context 全部 message 化。

目标是：

1. 保持 AGEO 的 `state-first` 架构
2. 把 orchestrator 的关键 context 从“直接自然语言摘要”升级成“结构化 context packets”
3. 保持现有 `PromptAssembly` 机制不变，只替换 section 的来源

---

## 4. 设计原则

### 4.1 保持 `state-first`

orchestrator 仍然优先消费：

1. workflow state
2. artifact / latest results
3. knowledge manifest
4. deterministic routing hint

不把 AGEO 改成纯 message-driven。

### 4.2 packet 先于 section

新的设计顺序应是：

`state -> context packet -> rendered prompt section`

而不是：

`state -> natural language summary`

### 4.3 model-visible 与 harness-only 分离

需要区分：

1. `model-visible context`
2. `harness-only metadata`

不是所有运行时信息都应该暴露给模型。

---

## 5. 建议的 Context Packet 分层

### 5.1 本次先落地的 packets

#### `SessionStatusPacket`

回答：

1. 当前会话已经完成了哪些关键步骤
2. 当前缺少哪些关键前置条件
3. 当前是否存在必须先处理的阻塞状态

#### `EntityContextPacket`

回答：

1. 当前分析的品牌是谁
2. 官方网站 / 行业等核心实体信息是什么

#### `HistoryAvailabilityPacket`

回答：

1. 当前有没有历史材料可复用
2. 历史材料来自哪些 source types
3. 历史窗口是否足够支持 compare/export

### 5.2 后续再扩展的 packets

本次不实现，但建议后续增加：

1. `RecentEvidencePacket`
2. `PendingDecisionPacket`
3. `ActiveSkillPacket`

---

## 6. 建议的数据结构

### 6.1 `SessionStatusPacket`

```python
SessionStatusPacket(
  current_step: str | None,
  completed_items: tuple[str, ...],
  blocked_items: tuple[str, ...],
)
```

### 6.2 `EntityContextPacket`

```python
EntityContextPacket(
  brand_name: str,
  official_website: str | None,
  industry_hint: str | None,
  top_competitors: tuple[str, ...],
)
```

### 6.3 `HistoryAvailabilityPacket`

```python
HistoryAvailabilityPacket(
  has_materials: bool,
  available_sources: tuple[str, ...],
  total_items: int,
  recent_months: tuple[str, ...],
  analysis_window_count: int,
)
```

### 6.4 聚合对象

```python
OrchestratorContextPackets(
  session_status: SessionStatusPacket,
  entity_context: EntityContextPacket,
  history_availability: HistoryAvailabilityPacket,
)
```

---

## 7. Prompt Assembly 对接方式

本次不改变 `PromptAssembly` 类型本身。

新的对接方式应为：

1. builder 负责产出 packet
2. render 函数负责把 packet 转成 section body
3. `build_orchestrator_prompt_assembly()` 只负责 section 组装

目标形态：

```python
packets = build_orchestrator_context_packets(state)

PromptAssembly(
  base_policy_sections=...,
  skill_sections=...,
  runtime_context_sections=(
    PromptSection(... render_session_status_packet(...)),
    PromptSection(... render_entity_context_packet(...)),
    PromptSection(... render_history_availability_packet(...)),
    ...
  ),
  runtime_reminder_sections=...,
)
```

---

## 8. 本次最小实现范围

### 本次要做

1. 新增 `orchestrator_context_packets.py`
2. 定义三个 packet dataclass 和一个聚合 builder
3. 让 orchestrator prompt assembly 改为消费这些 packet
4. 新增 `History Availability` section
5. 保持现有 routing / hint / summary 逻辑大体不变

### 本次不做

1. Recent evidence 全量 packet 化
2. Pending decision packet
3. Active skill packet
4. AIO / A4 blocker taxonomy 的 context packet 化
5. history tool routing 规则重写

---

## 9. 对现有 `_build_context_summary` 的处理

`_build_context_summary` 本次继续保留，因为：

1. 它承载了较多 session-level availability hint
2. 完全拆除范围过大

但本次建议把“历史材料总览”从 `_build_context_summary` 中逐步迁出，避免与新的 `HistoryAvailabilityPacket` 重复。

也就是说：

1. `_build_context_summary` 保留“当前会话数据 + 可用工具提示”
2. 历史材料概况改由独立 packet section 负责

---

## 10. 预期收益

完成本次最小改造后，收益主要有三点：

1. orchestrator context 开始具备正式协议，而不是继续只靠 summary 字符串
2. 后续接 `RecentEvidencePacket / PendingDecisionPacket` 有清晰扩展路径
3. AGEO 在保持 `state-first` 的同时，更接近 Claude Code 的“context protocolized assembly”

---

## 11. 最终结论

本次推荐路线不是把 AGEO 改成 Claude Code 的 `message-first`，而是：

`保持 state-first，但把 orchestrator context 升级成 packet-first。`

最小落地动作就是：

`先把 SessionStatus / EntityContext / HistoryAvailability 三类 packet 建起来，并接入 PromptAssembly。`

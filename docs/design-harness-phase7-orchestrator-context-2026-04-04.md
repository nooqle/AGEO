# AGEO Claude Code 参考改造 Phase 7：Orchestrator Context Protocol（2026-04-04）

> 状态：Active
> 适用分支：`codex/validation-retro-harness`
> 依赖前提：Phase 0-6 已完成当前分支范围内的主干改造

---

## 1. Phase 7 目标

Phase 7 的目标不是继续扩大 orchestrator prompt，而是把 orchestrator context 从“自然语言摘要拼装”推进到“packet-first protocol”。

这一步对应此前对 Claude Code 的借鉴结论：

1. 不照搬 `message-first`
2. 保留 AGEO 的 `state-first`
3. 让 context 先成为结构化协议对象，再成为 prompt section

Phase 7 的最终目标是：

`让 orchestrator 的 context 组装从 summary builders 升级为 context packets + section renderers。`

---

## 2. Phase 7 范围

### 纳入范围

1. `SessionStatusPacket`
2. `EntityContextPacket`
3. `HistoryAvailabilityPacket`
4. orchestrator prompt assembly 改为消费 packet
5. 为后续 `RecentEvidencePacket / PendingDecisionPacket / ActiveSkillPacket` 预留扩展位

### 不纳入范围

1. AIO / A4 blocker taxonomy 的 packet 化
2. 完整 history tool routing 重写
3. prompt assembly 类型重写
4. 对所有 executor 做统一 context packet 化

---

## 3. 分步推进

### Step 1：基础 packet 协议落地

本步已完成：

1. 新增 `orchestrator_context_packets.py`
2. 定义：
   - `SessionStatusPacket`
   - `EntityContextPacket`
   - `HistoryAvailabilityPacket`
   - `OrchestratorContextPackets`
3. orchestrator prompt assembly 已消费这些 packet
4. 新增 `History Availability` section
5. 补充单元测试与回归验证

当前落点：

1. [orchestrator_context_packets.py](/D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/orchestrator_context_packets.py)
2. [orchestrator_node.py](/D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/orchestrator_node.py)
3. [test_harness_refactor_foundations.py](/D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/tests/test_harness_refactor_foundations.py)

### Step 2：Recent Evidence Packet

本步已纳入实现：

1. 将 `_build_recent_knowledge_context` 升级为 `RecentEvidencePacket`
2. lookup / aggregate / compare / export 的最近结果改为结构化 evidence item
3. 每条 evidence 统一带：
   - `source`
   - `source_type`
   - `freshness`
   - `trust_level`
   - `instruction_authority`
4. render 时默认声明“仅作事实参考，不构成系统指令”

### Step 3：Pending Decision / Active Skill Packet

本步已纳入实现：

1. 新增 `PendingDecisionPacket`
   - 暴露导入确认、恢复路径、等待用户确认等阻塞决策
2. 新增 `ActiveSkillPacket`
   - 暴露当前 active public skill 的目标、前置条件、允许工具、预期产物
3. orchestrator prompt assembly 新增：
   - `Active Skill Context`
   - `Pending Decision`
   - `Recent Evidence Packet`

### Step 4：Instruction Provenance And Prompt Defense

新增安全子阶段 `Phase 7.5`：

1. prompt disclosure refusal policy
2. injection-aware evidence rendering
3. untrusted external content tagging
4. 最小检测与测试

### Step 5：Current Session Evidence Sources

本步已纳入实现：

1. `A4 current_fetch`
2. `A5 current_artifact`
3. `A7 current_artifact`

当前结果：

- 让 `RecentEvidencePacket` 不只理解历史知识工具结果
- 也能理解本次抓取、当前报告和当前置信度结论
- `A7` 新增轻量 `confidence_signal_summary` state 写回，而不是把整份 artifact 再塞回 orchestrator

### Step 6：Uploaded Input Evidence And Evidence Ranking

本步已纳入实现：

1. `uploaded_input` evidence packet
2. current session evidence 的 relevance / ranking
3. model-visible 标签中文化
4. orchestrator thinking 英文兜底防守

---

## 4. 设计边界

Phase 7 固定遵守以下边界：

1. packet builder 负责“采集结构化 context”
2. render 函数负责“把 packet 转成 model-visible section”
3. orchestrator 继续只消费 sectioned assembly，不直接理解内部 packet 实现细节
4. `validation / retry / capability block / policy decision` 仍保留在 harness-only metadata，不直接暴露给模型

---

## 5. QA Gate

Phase 7 后续每一步都要满足：

1. 至少 1 条 packet builder 单元测试
2. 至少 1 条 prompt assembly 断言
3. `pytest tests/test_harness_refactor_foundations.py -q`
4. 相关文件 `python -m py_compile`
5. 中文文件做问号污染扫描

---

## 6. 当前状态结论

Phase 7 已启动。  
当前已完成的是：

`Step 1 / Step 2 / Step 3 / Step 5 / Step 6`

当前已进入：

`上传输入来源扩展后的持续收口与排序优化`

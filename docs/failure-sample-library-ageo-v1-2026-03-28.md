# AGEO Failure Sample Library v1（2026-03-28）

## 文档定位

这份文档是 AGEO 的本地 failure sample 库。

分层方式如下：

1. 跨项目通用 failure sample：
   - [Global Failure Sample Library v1](/C:/Users/Administrator/.codex/skills/collaboration-harness/references/failure-sample-library.md)
2. AGEO 本地稳定样本：
   - 记录在本文档 `AGEO Local` 部分
3. 仍未稳定、尚需观察的样本：
   - 记录在本文档 `Watchlist` 部分

目标不是罗列所有错误，而是保存那些能提高验证收口质量、能指导 kill step、能沉淀回规则的样本。

---

## Global

以下模式已经上升到全局层，后续 AGEO 不再单独定义通用版本，只保留本地实例和映射：

1. 验证要求存在，但没有显式 closure 结构
2. failure 被识别了，但没有被保存成 failure sample
3. 探索扩张快于验证收口
4. 可复用协议被锁在单一 repo 或分支
5. narrative writeback 替代 durable writeback

---

## AGEO Local

### 1. 场景化硬编码替代 Agent-First 扩展

- `Signal`
  - 新功能更容易被实现成专用 sidechain、专用 if/else 或独立流程，而不是 skill / node / context 扩展。
- `Why it survived`
  - 单次交付时，专用实现往往看起来更快，局部也更容易“先跑起来”。
- `Kill step`
  - 在设计阶段先回答：这是不是现有体系的新输入源，而不是一条专用新流程。
- `Writeback`
  - `Agent First / Skill First / Artifact-Version First` 原则
- `Status`
  - written-back

### 2. 只改内部状态，不更新对应 Artifact / Version

- `Signal`
  - 系统表面表现像成功了，但正式步骤结果、版本记录或可回放 artifact 没有同步更新。
- `Why it survived`
  - 临时 state 修改比正式 artifact 落库更轻，容易被误当成“已经完成”。
- `Kill step`
  - 任何会影响正式结果的输入都必须先更新对应 artifact/version，再恢复后续链路。
- `Writeback`
  - artifact-first 规则和对应测试
- `Status`
  - written-back

### 3. 未确认就执行带副作用的正式更新

- `Signal`
  - 仅凭识别结果就直接覆盖 A1/A3/A7 等正式业务结果。
- `Why it survived`
  - 系统把“识别到了什么”误当成“已经知道用户要执行什么”。
- `Kill step`
  - 对有业务副作用的导入或覆盖动作，先 `ask_user`，确认后再执行。
- `Writeback`
  - confirmation strategy + negative cases
- `Status`
  - written-back

### 4. 用冗长 AI 腔文案掩盖真实系统状态

- `Signal`
  - 文案看起来很“智能”，但没有明确告诉用户系统识别了什么、下一步做什么、需要确认什么。
- `Why it survived`
  - 冗长解释容易制造一种“系统很懂”的错觉，掩盖真实状态并降低可验证性。
- `Kill step`
  - 文案只回答必要事实，不用自我叙述填充不确定性。
- `Writeback`
  - 短、准、可执行的 UX 文案规则
- `Status`
  - written-back

### 5. 用户入口心智被内部节点语义绑架

- `Signal`
  - 一个用户本来想“现在做置信度分析”的能力，在实现上却被理解成某个内部节点后的后续动作；对外同时混着 `tool / skill / node` 三套说法。
- `Why it survived`
  - 系统先有内部 workflow 结构，后有产品能力表达，结果用户入口、主 LLM 可见能力和内部执行节点没有被强制对齐。
- `Kill step`
  - 先定义用户心智下的单一能力入口，再反推：
    - 对外能力名
    - orchestrator 可见调用名
    - 内部 executor node
  - 不允许三者各自漂移命名。
- `Writeback`
  - `confidence_analysis` 统一命名
  - `skill -> executor node` 清晰分层
  - “主 LLM 决策，程序提供事实”边界
  - 参考案例：
    - [2026-03-28-confidence-analysis-tool-mode.md](/D:/AGEO-worktrees/confidence-analysis-mode/docs/session-logs/2026-03-28-confidence-analysis-tool-mode.md)
- `Status`
  - written-back

### 6. 残留导入状态覆盖显式生成模式

- `Signal`
  - persona-focused questionList 已经真实生成，但最终交付物又被旧的 `uploaded_list` 逻辑覆盖回去，看起来像“画像问题没生成”。
- `Why it survived`
  - 系统把“首次导入的问题列表”错误地当成会话级长期模式，而不是一次性输入动作；于是后续显式模式（persona / panorama / baseline dynamic）仍会被 stale import state 反向改写。
- `Kill step`
  - 任何导入态都必须明确它的生命周期：
    - 是一次性消费
    - 还是会话级长期模式
  - 如果后续显式生成逻辑已经给出新版本交付物，旧导入态不得再回写覆盖。
- `Writeback`
  - “上传只执行一次”规则
  - questionList 版本应沿同一交付物流转，而不是被导入态重新接管
  - 参考案例：
    - [2026-03-28-report-persona-flow-stabilization.md](/D:/AGEO-worktrees/question-list-upload-a4/docs/session-logs/2026-03-28-report-persona-flow-stabilization.md)
- `Status`
  - written-back

---

## Watchlist

以下样本已经出现信号，但还不适合直接升级为 AGEO 稳定规则或全局规则。

### 1. 验证收口项是否可以自动采集

- `Signal`
  - 当前 closure 仍主要依赖人工复盘整理。
- `Why it survived`
  - 自动采集边界还没清楚，容易采到噪声而不是有效闭环。
- `Kill step`
  - 先明确哪些 closure 项具备结构化数据来源，再决定自动化。
- `Writeback`
  - 后续可考虑 closure telemetry 或 retro helper
- `Status`
  - open

### 2. 哪些 AGEO failure sample 值得再升到全局

- `Signal`
  - 某些 AGEO 本地问题可能其实也是跨项目通病。
- `Why it survived`
  - 目前还缺少跨 repo 复用证据，过早升格会污染全局层。
- `Kill step`
  - 至少在多个任务或多个项目中重复出现后，再考虑提升。
- `Writeback`
  - promotion review
- `Status`
  - open

### 3. retro / session archive / memory / automation 的衔接方式

- `Signal`
  - 这些层都在记录经验，但还没有形成统一信息流。
- `Why it survived`
  - 各自先独立演化，当前还没形成稳定的端到端协议。
- `Kill step`
  - 先画清楚每一层各自负责什么，再决定同步关系。
- `Writeback`
  - integration protocol
- `Status`
  - open

---

## 当前使用方式

1. 写 retro 或 postmortem 时：
   - 先用 [validation-closure-retro](/C:/Users/Administrator/.codex/skills/validation-closure-retro/SKILL.md)
   - 再看本文档里是否有对应 failure sample 可以直接引用
2. 讨论什么该全局化、什么该本地化时：
   - 用 [collaboration-harness](/C:/Users/Administrator/.codex/skills/collaboration-harness/SKILL.md)
3. 当某个 AGEO 本地样本反复出现时：
   - 先从 `Watchlist` 移到 `AGEO Local`
   - 再判断是否值得提升到全局库

# AGEO Harness 协同落地映射（2026-03-28）

## 文档定位

这份文档不再承担“通用协同规范”的主定义。

从今天起，分层如下：

1. 跨项目通用协同范式，提升到全局 skill：
   - [collaboration-harness](/C:/Users/Administrator/.codex/skills/collaboration-harness/SKILL.md)
   - [validation-closure-retro](/C:/Users/Administrator/.codex/skills/validation-closure-retro/SKILL.md)
2. AGEO 仓库内只保留本项目的落地映射、局部约束和案例化 failure sample。

所以，这份文档现在的作用是：

- 把全局协同范式映射到 AGEO
- 说明 AGEO 哪些部分是项目特有
- 记录哪些内容还停留在任务或分支层，尚未提升为通用规范
- 指向 AGEO 本地 failure sample 库：
  - [failure-sample-library-ageo-v1-2026-03-28.md](/D:/AGEO-worktrees/validation-retro-harness/docs/failure-sample-library-ageo-v1-2026-03-28.md)

---

## 1. 适合放到全局 skill 的内容

以下内容已经不应再被锁定在 AGEO 分支里：

1. 人类负责 `prior pruning / quality bar / irreversible-action control`
2. Codex 负责 `candidate expansion / implementation / artifactization / evidence gathering`
3. 协同必须显式区分：
   - 已验证什么
   - 未验证什么
   - failure sample 是什么
   - 什么被写回成长期资产
4. retro 不应只写任务列表，而应优先写：
   - `Validation Closure`
   - `Failure Samples`
   - `Collaboration Evolution`
5. 任何重复出现的协同规则，都应先判断该写到：
   - 全局 skill
   - repo 规则
   - 任务级文档

## 2. 留在 AGEO 仓库内的内容

这些内容仍然是 AGEO 特有，不应直接升格为全局通用规范：

1. worktree / branch 协议
2. A1 / A3 / A4 / A5 / A7 这些节点语义
3. artifact / version / resume 的本项目实现方式
4. 当前 repo 的 daily retro section 约束
5. 本项目特有的反模式，例如：
   - 场景化硬编码替代 agent-first 扩展
   - 只改 state 不更新 artifact/version
   - 未确认就改正式业务结果
6. AGEO 本地 failure sample 库及其 watchlist

---

## 3. 仍应先停留在任务或分支层的内容

以下内容目前更适合继续在任务层讨论，不急着提升：

1. 哪些 failure sample 已经足够稳定，值得升格为全局规则
2. AGEO 中哪些验证收口项可以被自动化采集
3. retro、session archive、memory、automation 之间的最终衔接方式
4. 哪些协同指标能真正量化 Harness 的增强，而不是只做形式统计

---

## 4. AGEO 当前如何使用全局 skill

建议从现在开始这样使用：

1. 当我们讨论“应该怎么协同、什么该全局化、什么该本地化”时，优先调用：
   - [collaboration-harness](/C:/Users/Administrator/.codex/skills/collaboration-harness/SKILL.md)
2. 当我们写 retro、postmortem、阶段收口时，优先调用：
   - [validation-closure-retro](/C:/Users/Administrator/.codex/skills/validation-closure-retro/SKILL.md)
3. 当需要把一个 AGEO 个案继续上升为全局规范时：
   - 先在本分支或本 repo 中验证其复用价值
   - 再决定是否升级进全局 skill

---

## 5. 当前写回结论

今天真正新增的不是一份只能留在 AGEO 的协议文档，而是一种分层方式：

1. 通用协同范式进全局 skill
2. 项目特有规则留在 repo
3. 个案讨论先留在分支，再视情况上升

这才更符合 Harness 作为跨项目协同能力的定位。

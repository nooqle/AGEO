# PRD v0.5 / Handoff / Story 三文档联合评审

> 评审日期：2026-06-17
> 评审对象：
> - `docs/prd-brand-circle-board-redesign-v0.5-2026-06-17.md` (PRD v0.5, 645 行)
> - `docs/implementation-handoff-brand-circle-board-v0.5-2026-06-17.md` (Handoff, 596 行)
> - `docs/story-task-breakdown-brand-circle-board-v0.5-2026-06-17.md` (Story, 511 行)
> 评审依据：安利报告 10 个真实问题 + PRD v0.3 规则对照 + 原型 v0.4 评估 + 现有代码库架构
> 评审结论：**文档拆分方向正确，PRD 精炼到位，Handoff 类型扎实，Story 排序合理。但拆分过程中丢失了 v0.3 的 6 组核心算法规则，后端类型定义缺失，报告生成仍是黑盒。需要在 Milestone 0 之前补齐，否则实施无法启动。**

---

## 一、做对了什么

### 1. 文档拆分终于做到了

PRD v0.3 的问题是 Section 17 嵌了 300 行技术规格。评审建议拆为独立文档。v0.5 做了正确的拆分：

| 文档 | 职责 | 行数 |
|------|------|------|
| PRD v0.5 | 产品决策、概念定义、验收标准 | 645 |
| Handoff | 类型定义、API 合约、状态机、前后端边界 | 596 |
| Story | 里程碑、任务拆解、验收条件、Sprint 排序 | 511 |

PRD 只管"做什么"，Handoff 管"怎么接"，Story 管"按什么顺序做"。三者不重叠。

### 2. 10 个原始问题在 PRD 中全部有规则覆盖

| 问题 | PRD v0.5 对应章节 |
|------|------------------|
| P01 提及≠认可 | Section 10（情感一票否决）、Section 13.3（圈层标签与情感矛盾→BLOCK） |
| P02 分层无区分度 | Section 4.2（6 层圈层 + 待审阅浮层）、Section 8（Queue 分组） |
| P03 风险消失 | Section 12（风险检测源 + 渲染要求"默认可见"） |
| P04 竞品缺失 | Section 11（竞品检测证据要求 + confidence 阈值） |
| P05 判断模板化 | Section 13.3（结论相似度 > 0.8 → review） |
| P06 证据来源单一 | Section 13.3（80% 证据来自同一问题 → WARN/BLOCK） |
| P07 监管信息错分 | Section 10（负面情感多数不得进内圈/中圈 + 监管类实体不得靠 connection_strength 推入） |
| P08 无时间维度 | Section 3.2（Graph Update Timeline） |
| P09 内容三遍重复 | Section 13.2（报告结构定义，Summary 不重复 Detail） |
| P10 行动建议空洞 | Section 13.3（缺少平台和场景 → BLOCK） |

### 3. Handoff 的类型定义质量高

TypeScript 类型定义覆盖了核心数据模型：BoardRun、NodeRun、Artifact、GraphPatch、EvidenceRef、ReportGuardrailResult。特别是：

- `EvidenceRef` 包含 `polarity` 字段（positive/neutral/questioning/negative）——直接解决 P01
- `GraphPatch` 包含 `sentimentScore`、`confidence`、`evidenceRefs`——可直接驱动 Queue 展示
- `GuardrailSeverity` 三级（pass/warn/block）——直接解决原型评审中的"Guardrails 没有阻断力"问题
- 状态机定义清晰：BoardRun 7 种状态、GraphPatch 7 种状态、Report 4 种状态

### 4. Story 排序尊重依赖关系

Milestone 0（规格冻结）→ Milestone 1（只读 Shell）→ Milestone 2（Mock 运行时）→ Milestone 3（后端持久化）→ Milestone 4（真实 Graph Update）→ Milestone 5（审阅环）→ Milestone 6（Guardrails + Trace）→ Milestone 7/8（Assets + 迁移）。

关键决策：**先 Mock 后端跑通 UI，再接真实后端**。这避免了前后端耦合导致的早期阻塞。

### 5. 原型 v0.4 评估的问题被逐一回应

| 原型问题 | Handoff/Story 回应 |
|----------|-------------------|
| 并行平台机架无分组 | Story 2.2: PlatformRackNode + group progress + Run all |
| Queue 无 diff 预览 | PRD Section 8: Before/after diff; Story 1.2 验收条件 |
| Guardrails 无 BLOCK | PRD Section 13.3: BLOCK 定义; Handoff 类型; Story 1.3 验收 |
| Node Inspector Output 空壳 | PRD Section 7.3: 逐节点类型定义了 Output 内容 |
| Trace Chain 静态 | PRD Section 14: 完整链路; Story 6.3 验收 |
| 待审阅浮层无交互 | PRD Section 9; Story 5.2: accept/keep-review/reject |
| 两套 CSS 矛盾 | Handoff Section 11: Specta 视觉规则; Story 1.1 验收排除旧 AI 样式 |

---

## 二、6 个关键缺口

### 缺口 1：v0.3 的 connection_strength 评分公式丢失

PRD v0.3 Section 17.1 定义了 7 维度加权评分：

```
connection_strength =
  platform_coverage_score × 20% +
  mention_frequency_score × 15% +
  explicit_association_score × 20% +
  context_relevance_score × 15% +
  evidence_quality_score × 10% +
  sentiment_or_risk_score × 10% +
  stability_score × 10%
```

PRD v0.5 Section 10 只保留了情感一票否决规则和判定顺序，但**评分公式本身不见了**。没有公式，后端无法实现圈层分配——这是整个产品的核心算法。

**建议**：在 Handoff 或独立 spec 文档中补充 connection_strength 公式，包括每个维度的计算方式、分值范围、权重。

### 缺口 2：战略词结论分段规则丢失

PRD v0.3 Section 17.6 定义了战略词的分段结论规则：

| 稳定度 | 证据量 | 结论模板 |
|--------|--------|----------|
| ≥ 60 | ≥ 30 | 已站稳：可放大传播 |
| 50-59 | 15-29 | 有基础但需补强：建议定向投放 [平台] 的 [场景] |
| < 50 | < 15 | 尚在萌芽：先补证据 |
| 任意 | 负面情感占多数 | 伴随风险：需先澄清 [具体风险] |

PRD v0.5 Section 13.3 只说"结论相似度 > 0.8 → review"，但没有定义**什么才是正确的结论**。只有检测错误的规则，没有生成正确的规则。安利报告的 P05 问题（12 个词拿到相同结论）会在新架构中复发——Guardrails 能检测到结论太相似，但报告生成不知道应该输出什么。

**建议**：在 Handoff 或独立 spec 中补充战略词结论分段规则，作为报告生成的约束条件。

### 缺口 3：证据选择规则丢失

PRD v0.3 Section 17.6 定义了证据选择规则：

1. 每个战略词至少引用 2 个不同问题的证据
2. 优先级：精准命中 > 跨平台覆盖 > 长文本
3. 不允许同一问题的回答作为某个战略词的唯一证据来源
4. 证据引用应包含：问题原文、平台、摘录长度、情感倾向标记

PRD v0.5 Section 13.3 只有"80% 证据来自同一问题 → WARN/BLOCK"，这是**事后校验**而非**事前选择规则**。校验和选择是互补的，不能只靠校验。安利报告 P06 的根因是证据选择逻辑有问题，光靠 Guardrails 检测只能发现症状，不能修复病因。

**建议**：在 Handoff 中补充证据选择规则，作为 Report skeleton generation 的输入约束。

### 缺口 4：实体抽取流程缺失

PRD v0.3 Section 17.5 定义了完整的抽取流程：回答分句 → 实体识别 → 关系分类（含 risk_of/competes_with）→ 消歧 → 输出 EntityRelationSet。

PRD v0.5 有 Section 11（竞品检测）和 Section 12（风险检测），但**通用的实体抽取流程没有定义**。关键缺失：

- AI 回答如何被分句和标注？
- 实体识别用什么方法？词表匹配？LLM 抽取？混合？
- 关系分类的完整枚举是什么？PRD v0.5 只提到了 `competes_with` 和风险关系，但品牌实体之间的关系远不止这两种
- 消歧规则（同名实体合并、别名映射）在哪里定义？
- EntityRelationSet 的 schema 是什么？

这是 Board 执行的核心——一个 AI 回答如何变成结构化的实体关系数据。没有这个流程定义，后端无法实现 Story 4.1（Graph Patch Set Generation）。

**建议**：在 Handoff 或独立 spec 中补充实体抽取流程，至少包括：抽取步骤、关系类型枚举、消歧规则、EntityRelationSet schema。

### 缺口 5：报告生成仍是黑盒

三份文档定义了报告的**结构和校验**（PRD Section 13.2/13.3），但没有定义报告的**生成逻辑**。关键问题：

- 报告骨架从 Graph Update 生成，但用什么方法？模板填充？LLM 生成？混合？
- 如果用 LLM，prompt 的约束条件是什么？如何防止 LLM 幻觉（编造不存在的实体/关系）？
- 报告生成是否需要所有 Guardrails 都 PASS？还是可以先 draft 再校验？
- 报告的"推荐下一轮 Board"如何从 Graph Update 状态推导？

当前安利报告的问题（P01/P05/P06/P10）本质上都是报告生成逻辑的问题，不是报告结构的问题。Guardrails 能发现"结论太相似"和"证据太集中"，但如果生成逻辑本身不改善，Guardrails 只会反复 BLOCK 而无法产出合格报告。

**建议**：在 Handoff 中补充报告生成策略，至少包括：生成方法（模板/LLM/混合）、prompt 约束规则、防止幻觉机制、与 Guardrails 的迭代关系。

### 缺口 6：后端类型定义缺失

Handoff 的类型定义全部是 TypeScript。但后端是 Python/FastAPI/SQLAlchemy。后端工程师需要：

- SQLAlchemy Model 定义（对应 BoardRun、NodeRun、Artifact、GraphPatch 等表）
- Pydantic Schema 定义（对应 API request/response）
- 数据库迁移策略（如何从现有 session/task/output 模型迁移）
- Alembic migration 路径

Story 3.1 的任务是"Add BoardRun model/table"，但没有参考的 Model 定义。后端工程师需要从 TypeScript 类型反推 Python Model，这增加了出错风险。

**建议**：在 Handoff 中补充 Python 端的 Model/Schema 定义，或至少补充字段级别的 schema 约束（类型、可空、默认值、索引）。

---

## 三、3 个结构性问题

### 问题 1：Handoff 承担了过多职责

Handoff 目前同时包含：
- 组件设计（Section 3）
- 数据模型（Section 4）
- API 合约（Section 5）
- 事件合约（Section 6）
- 动效绑定（Section 7）
- 状态机（Section 8）
- 设计系统（Section 11）
- 验证计划（Section 12）
- 风险（Section 14）

596 行的 Handoff 实际上是一个**微型技术规格文档集**。评审 v0.2 时建议拆分的独立 spec（圈层算法、Patch 生命周期、Node I/O、实体抽取、报告生成）现在都被压缩进了 Handoff，但关键内容（评分公式、抽取流程、报告生成）反而丢失了。

**建议**：保持 Handoff 作为"接口合约"文档，将算法规则拆为独立 spec（如 `spec-circle-allocation.md`、`spec-entity-extraction.md`、`spec-report-generation.md`），Handoff 通过引用关联。

### 问题 2：API 合约过于草稿

当前 API 合约只有 HTTP 方法和 URL 路径，缺少：
- Request body schema
- Response body schema
- Error codes
- Pagination
- Authentication context
- Rate limiting

Story 3.1-3.3 的后端任务需要完整的 API 合约才能开始。不完整的合约会导致前后端反复对齐，浪费时间。

**建议**：在 Handoff 中至少补充核心 API（Board Run CRUD、Graph Patch Review、Report Validate/Publish）的 request/response schema。可以用 Handoff 中已有的 TypeScript 类型作为基础。

### 问题 3：Open Questions 中有阻塞性问题

PRD Section 19 列了 5 个 Open Questions，其中 Q5（"Which platform adapters are available for a real Phase 3 run?"）直接决定 Phase 3 是否可行。当前后端的 A4 Agent 有 4 个平台适配器（DeepSeek/Kimi/元宝/豆包），但 Handoff 的 Platform Rack 列的是 ChatGPT/DeepSeek/Kimi/Doubao。ChatGPT 在中国无法直接使用，且当前后端没有 ChatGPT 适配器。

这个不一致如果不解决，Story 2.2（PlatformRackNode）和 Story 4.1（Graph Patch Set Generation）的交付物会不匹配。

**建议**：在 Milestone 0 之前确认实际支持的平台列表，更新 Handoff 的 PlatformRackNode 定义。

---

## 四、Story Breakdown 评估

### 优点

- **Milestone 0（规格冻结）是关键设计**——先冻结再动手，避免返工
- **Mock-first 策略正确**——Milestone 1-2 用 Mock 数据跑通 UI，不依赖后端
- **每个 Story 有明确的验收条件**——不是模糊的"完成开发"
- **Cross-cutting Validation 清晰**——UI 变更和后端真理变更各有验证标准
- **First Engineering Ticket 建议实用**——Story 1.1 + 2.1 在隔离路由中起步

### 问题

1. **Story 缺少工作量估算**——6 个 Sprint 没有容量定义，无法判断是否可行
2. **Story 0.3（数据模型映射）是高风险项但缺少细节**——现有 A1-A6 Agent 体系的输出如何映射到新的 BoardRun/NodeRun/Artifact？这不是文档任务，是架构迁移
3. **Milestone 3 和 Milestone 4 之间的依赖关系过于紧密**——Milestone 3 的 Artifact Registry 和 Runtime Events 如果延期，Milestone 4 无法开始
4. **缺少回退策略**——如果 Milestone 4 的真实 Graph Update 不及预期，是否有 fallback 方案？是否需要继续支持旧报告流程？

---

## 五、10 个原始问题的最终覆盖评估

| 问题 | PRD v0.5 规则 | Handoff 实现 | 评估 |
|------|--------------|-------------|------|
| P01 提及≠认可 | ✅ 情感一票否决 + polarity 字段 | ✅ EvidenceRef.polarity | 可实施 |
| P02 分层无区分度 | ✅ 6 层 + 待审阅浮层 | ⚠️ 缺评分公式 | 公式缺失 |
| P03 风险消失 | ✅ 风险检测源 + 默认可见 | ✅ risk relation 类型 | 可实施 |
| P04 竞品缺失 | ✅ 竞品证据 + confidence 阈值 | ✅ competitor_relation + EvidenceRef | 可实施 |
| P05 判断模板化 | ⚠️ 只有相似度检测 | ❌ 缺分段结论规则 | 检测有，生成缺 |
| P06 证据来源单一 | ⚠️ 只有集中度检测 | ❌ 缺证据选择规则 | 检测有，生成缺 |
| P07 监管信息错分 | ✅ 情感否决 + 监管类排除 | ✅ sentiment 字段 | 可实施 |
| P08 无时间维度 | ✅ Timeline 定义 | ⚠️ 无具体交互规格 | 方向有，细节缺 |
| P09 内容三遍重复 | ✅ 报告结构定义 | ✅ Trace Chain 约束 | 可实施 |
| P10 行动建议空洞 | ✅ 缺平台/场景→BLOCK | ❌ 缺建议生成规则 | 检测有，生成缺 |

**结论：P01/P03/P04/P07/P09 可以实施。P02/P08 有方向但缺细节。P05/P06/P10 只有检测规则没有生成规则——Guardrails 能发现"错了"但不知道"什么是对的"。**

---

## 六、修订建议优先级

| 优先级 | 修订项 | 理由 |
|--------|--------|------|
| **P0** | 补充 connection_strength 评分公式 | 没有公式，圈层分配无法实现 |
| **P0** | 补充实体抽取流程（步骤、关系类型枚举、消歧规则） | 没有抽取流程，Story 4.1 无法开始 |
| **P0** | 补充报告生成策略（方法、prompt 约束、防幻觉机制） | 没有生成策略，Guardrails 只能反复 BLOCK |
| **P1** | 补充战略词结论分段规则 | P05 复发的预防 |
| **P1** | 补充证据选择规则 | P06 复发的预防 |
| **P1** | 补充 Python 端 Model/Schema 定义 | 后端实施的基础 |
| **P1** | 确认平台列表，更新 Handoff | ChatGPT vs 元宝/豆包 不一致 |
| **P2** | Handoff 拆分算法规则为独立 spec | 降低文档维护复杂度 |
| **P2** | 补充核心 API 的 request/response schema | 前后端对齐效率 |
| **P2** | Story 补充工作量估算和回退策略 | 项目管理基础 |

---

## 七、一句话评审

**v0.5 三文档在"架构怎么搭"和"接口怎么接"上做得很好，但在"算法怎么算"和"内容怎么生"上留了空。** 圈层评分公式、实体抽取流程、报告生成策略——这三样是产品从"方向文档"升级为"可实施规格"的最后一步。补齐后，Milestone 0 可以关闭，实施可以启动。

# Review: 蓝皮书 3b-1/3b-2 批次代码评审（0580b1d..1f119fb）

日期：2026-07-21
评审方式：4 角色并行（architect / backend / frontend / qa）+ Lead 抽查互证
角色报告：`.claude/outputs/{architect,backend,frontend,qa}_result.md`
对照基准：`docs/specta-agentic-infrastructure-blueprint-2026-07-21.md`

---

## 总体结论

**方向正确、纪律性强，骨架有几根筋没接上，且有 1 个真实 P0 安全漏洞和 1 个静默失败放大器。**

- ✅ 命根子基本守住：契约 schema 领域无关，唯一裂缝是端口类型 `circle`（安利味词汇进契约词表）
- ✅ 范围零实质越界：3c 三要素（chat-to-topology/图确认流/模板库）均未混入；M3 确认闸判定不越界
- ✅ 采集内核未动：A4 只加平台门，抽取/校准内核 verbatim 搬移，56 个 parser 测试零改动通过
- ✅ 安全面大体干净：新端点认证授权+租户隔离+feature flag 齐全，SQL 全参数化，system prompt 不外泄
- ❌ 但"约束即节点"的承诺在三个地方打折：一条断了没效果的边、一个可被 LLM 绕过的门、一个会把全套门控静默关掉的降级路径

---

## P0 阻塞项（修复前不应宣称 3b-1 完成）

### P0-1 分支 BFS 幽灵节点环 → 事件循环死锁 DoS【backend 发现，architect 互证】
- `topology_resolver.py:226-242`：BFS 只对 executor 节点做 `reached` 标记，"幽灵节点"（边指向不存在的 id）永远进不了 `reached` → 幽灵自环/双环造成**无 await 的无限循环，整个 uvicorn worker 事件循环饿死**；无环幽灵 DAG 也会队列指数膨胀
- 诱因：`PUT /flow-topology`（`amwaychina.py:726-760`）只校验节点数 ≤20，**完全不校验 customEdges 端点存在性/自环/环/数量上限**
- 攻击面：本租户 manage 用户即可（无需越权），一次 PUT + 一次 `flow-branch/run` 触发
- **修法**：① BFS 改单一 visited 集合覆盖所有出队节点；② PUT 侧校验边端点∈节点白名单、拒自环、做环检测、限边数

### P0-2 `load_flow_topology` 静默失败放大器【QA 实证发现】
- QA 实测：asyncpg 下 str 参数靠 `$1::UUID` cast **侥幸可用**；SQLite 下 100% 抛异常，且被 `topology_resolver.py:79-81` 的 broad except **静默吞掉** → 整套 3b-1 门控全部静默失效而测试全绿
- happy path（行存在 → 读出 removedEdgeIds）**全批次零测试**；现有降级测试无法区分"无行"与"查询爆炸"——两种情况产出完全相同
- 同仓库 `persist_custom_node_results` 知道要 `UUID(raw)` 转换，`load_flow_topology` 却不转——不一致本身就是气味
- **修法**：entity_id 统一 `UUID(raw)` 转换；补 happy path 测试；降级路径至少记 warning 日志

### P0-3 两条验收标准的证据链都在最后一跳断裂【QA】
- 验收①（断平台→实际跳过）：门控值传递已证（`build_request` 收到无 doubao 的 filter），但 **executor 真正不建 doubao client 无测试**——QA 纸面核对了短路顺序正确，但没有测试钉住
- 验收②（自定义节点产出 LLM 解读）：函数级证据真实（真 LLM mode=llm），但 **A5→amway_analysis 图内链入（`nodes_a5.py:1199-1249`）零测试**——这是整跑时验收成立的唯一入口

### P0-4 验证证据可信度分层混乱【QA】
- `m1-exit-check-evidence.json` **手工拼装，不可由脚本复现**（多出脚本不会写的字段；`pytest: "32 passed"` 在仓库内无产生者）
- `m1_exit_check.py:121-167` 的"画布 merge 契约"检查是 **Python 仿写 TS 逻辑的自证循环**，从未执行前端一行代码
- 前端根本没有测试运行器（package.json 无 test script），"frontend pure functions pass" 声称无基础设施支撑
- **修法**：evidence 只保留脚本可复现的字段；撤下或补上 vitest；seam smoke 脚本提交进仓库

---

## P1 应修项（8 条，按主题归并四方发现）

| # | 发现 | 出处 | 要点 |
|---|---|---|---|
| 1 | **拓扑门是"劝告式"** | backend | A4/extract 入口不校验入边，LLM function calling 可绕过画布断边直接 dispatch——断边期待零抓取的用户仍产生采集费用。executor 入口应自查输入边（防御纵深） |
| 2 | **断边早退缺终态** | backend | 全平台断连早退不写 `execution_status`/`orchestrator_reply`，非约束模式入口有 LLM 反复 dispatch→早退的空跑循环风险 |
| 3 | **拓扑文档读写竞态** | backend+frontend+architect 三方互证 | PUT 与 `persist_custom_node_results` 无乐观锁，运行中编辑丢数据；前端自定义节点运行也无并发互斥，先到结果可被后到响应覆盖；并发首写撞唯一索引 500 |
| 4 | **双端计划规则已分叉** | architect+frontend+QA 三方互证 | content 节点计划条件前后端不一致（`topology_resolver.py:409-413` vs `amwayFlowExecutionPlan.ts:393-395`）；同算法还有第三、第四份拷贝（前端 `runFlowAnalysis` vs 后端 `build_deterministic_analysis`）。蓝图"无第二处事实"正在被违反 |
| 5 | **`e-lexicon-extract` 边断了等于没断** | architect | 前端可断开但后端无任何 gate 消费，extract 照常加载词库——用户以为约束生效了。要么接门，要么暂时禁止断开该边 |
| 6 | **前端 updater 纯度违规回潮** | frontend | `togglePlatform`（`AmwayFlowCanvas.tsx:1027-1035`）在 setState updater 内写 localStorage——与当日刚修的 StrictMode 分叉事故同款模式，就在立了纯度规矩注释的同一个文件里。当前幂等属潜伏违规 |
| 7 | **确认闸交互死胡同 + 离线编辑静默丢** | frontend | 圈层视图发起运行后无跳转 CTA（确认按钮只在生产线视图）；拓扑 PUT 失败 fire-and-forget，下次挂载后端无条件覆盖本地编辑，无用户提示 |
| 8 | **注册表是"无人消费的规格说明书"** | architect | `node_contracts.py` 全部公共 API 仅测试引用，orchestrator 工具表仍硬编码。3c 开工前必须切换，否则按 YAGNI 这层契约就是死重 |

另：分支运行无总时限（最坏 ~30 分钟单请求且全程占 DB 连接，backend P1-5）——建议下沉后台任务或加 per-entity 并发锁+总时限。

---

## P2 建议项（归并后 12 条，择要）

1. 端口类型 `circle` 泛化为 `graph`/`entity_graph`（命根子唯一实质裂缝，趁 8 个契约改最便宜）
2. `fallback_reason` 存原始异常字符串入库回显 → 只存 `exc.__class__.__name__`（`amway_flow_custom_node_service.py:358,472`）
3. `nodes_amway.py:421-423` 恒真表达式使"未连 report 边就不喂 report"意图落空
4. 词库加载模板复制 3 份（`nodes_amway.py:81-97/238-254/506-521`）且同 run 内重复查询可能不一致
5. 死代码：`AMWAY_PLATFORM_IDS`、`embedded_in` 字段、`nodes_amway.py:535-537`、`api.getAmwayFlowPlan`、`CustomNodeDetail` 的 `void node`
6. `AmwayFlowCanvas.tsx` 2585 行 God component 拆分（useFlowTopology hook / Artifact 组件独立 / runFlowAnalysis 移 lib）
7. stage code 双轨制（`startsWith('A4')` 旧码 vs 新语义码并存，失败定位在新码下退化）
8. 引擎层中文案改 reason code（`topology_resolver.py:317-419` 与前端三处文案同源维护）
9. `input_scope` 非 AgentState 声明通道，需真实图集成测试验证（疑似死代码）
10. API 路径 content 上游取"第一个有 cards 的结果"不看连线，与 workflow 路径语义不一致
11. PUT 不校验 config/prompt 大小、node id 唯一性；`get_flow_plan` 无效平台参数回落全平台应 400
12. `test_port_types_match_frontend_canvas` 是手抄副本对账，前端改了不会红

---

## 给 3c 的三条架构提醒（architect）

1. 开工第一件事：orchestrator 工具表切到注册表驱动（P1-8），否则 chat-to-topology 在硬编码映射上再长一层硬编码
2. 图确认流复用 M3 确认闸（`brand_intelligence_run_service.py:794-888`），不要另造第二条确认路径
3. 拓扑 diff 生成结果必须过 P0-1②的服务端校验——蓝图"拓扑校验前置"就是为这一刻准备的

## QA 总评摘录

> 单测层质量高于平均（resolver/契约/wiring 断言具体、patch 点真实）。三个系统性问题：证据链在最关键一跳断裂；evidence 文件可信度分层混乱；`load_flow_topology` 降级设计+只测降级 = 典型静默失败放大器。PASS_WITH_RESIDUAL 声称本身诚实，但 residual 清单漏掉了"已声称完成但证据不足"的缺口。

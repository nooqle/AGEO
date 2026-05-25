# Specta AI 品牌情报 Ontology 基础设计（2026-05-16）

> 状态：Draft
> 目标：把 Specta 从“跑一次分析并生成报告”的流程系统，逐步升级为“持续维护品牌情报世界”的产品与代码架构。
> 第一阶段交付：方法论、对象/关系/动作清单、轻量注册中心，不迁移数据库，不改变现有 A1-A5 流程。

## 一句话结论

Specta 的下一阶段不应该只是继续增加 Agent 节点或报告类型，而应该建立一层“品牌情报世界”：

```text
品牌长期存在
  -> 问题、回答、引用、指标、报告、监测持续沉淀
  -> Agent 通过受控动作更新这些对象
  -> 用户围绕品牌主页查看、追溯、对比和监测
```

这层不是为了模仿 Palantir 的产品形态，而是借鉴其核心设计：把真实业务对象、关系、动作、函数、安全和应用放到同一套运行基础上。

## 官方依据

Palantir 官方文档给了几个关键判断：

1. Ontology 是组织的 operational layer，位于数据集、虚拟表和模型之上，并把它们连接到现实世界对象。见 [Ontology overview](https://www.palantir.com/docs/foundry/ontology/overview/)。
2. Ontology 的核心包含对象、字段、关系、动作、函数和对象视图；对象代表现实实体或事件，关系代表对象之间的连接，动作代表用户可一次性提交的一组修改。见 [Core concepts](https://www.palantir.com/docs/foundry/ontology/core-concepts/)。
3. 设计原则是“model reality, not systems”，也就是建模真实业务，而不是照着来源系统或部门表拆对象。见 [Best practices](https://www.palantir.com/docs/foundry/ontology/ontology-best-practices-and-anti-patterns/)。
4. Action 是一次受控交易，可以修改对象、字段和关系，并带规则、权限、通知等行为。见 [Action types](https://www.palantir.com/docs/foundry/action-types/overview/)。
5. Object Backend 负责对象查询、对象集合、动作写入和用户编辑编排。见 [Object Backend](https://www.palantir.com/docs/foundry/object-backend/overview/)。
6. Object Views 是围绕单个对象的信息和工作流中心。见 [Ontology-aware applications](https://www.palantir.com/docs/foundry/ontology/applications/)。

## Specta 当前位置

当前 Specta 已有很好的基础：

1. `Entity` 已经是品牌对象雏形：`aeo-platform/backend/app/models/entity.py`。
2. A1-A5 已经形成品牌分析主流程：`aeo-platform/backend/app/workflow/graph.py`。
3. `SkillContract` 已经开始描述能力输入、输出、允许工具和写回规则：`aeo-platform/backend/app/services/skill_contracts.py`。
4. `Message.output_data` 和 Canvas 已经承载报告、问题、抓取结果等产物。
5. Knowledge Workspace、Monitoring、Access Scope 已经具备长期化和组织化的雏形。

但当前中心仍然是：

```text
AgentState + Workflow Node + Artifact JSON
```

下一阶段的中心应该逐步变成：

```text
Brand Object + Evidence Objects + Controlled Actions + Object Views
```

## Gap 判断

### 1. 业务事实仍在流程状态里

`AgentState` 里的 `brand_profile`、`competitors`、`simulated_questions`、`fetch_results`、`metrics`、`report` 都是流程运行结果。它们很有价值，但还不是长期可查询、可授权、可链接、可审计的业务对象。

第一阶段不需要删除这些字段，而是要把它们映射成长期对象。

### 2. 证据链没有成为一等结构

Specta 的真实价值在于：

```text
问题 -> AI 平台回答 -> 引用来源 -> 指标 -> 报告结论
```

现在这条链主要藏在 JSON 结构中。未来需要显式关系：

```text
Question -> PlatformAnswer
PlatformAnswer -> Citation
EvidenceSet -> PlatformAnswer
Report -> EvidenceSet
```

### 3. 动作散落在流程代码里

确认问题、导入表格、重新抓取、生成报告、创建监测，都是业务动作。但现在它们分散在 workflow node、confirmation、WebSocket 和 service 中。

未来应统一成：

```text
ActionService.submit("confirm_question_set")
ActionService.submit("run_answer_fetch")
ActionService.submit("generate_report")
ActionService.submit("create_monitoring_plan")
```

### 4. 产物语义部分由前端判断

前端 `artifactIdentity.ts` 会根据 `report_kind`、`artifact_kind`、raw id 判断报告归类。短期可接受，但长期应该由后端对象和版本模型决定“这是什么、来自哪里、是哪一版、用了哪些证据”。

### 5. 缺少品牌主页

用户现在主要在 chat + canvas 中工作。企业级品牌情报系统应该有品牌对象主页：

```text
品牌画像
竞品
用户画像
问题库
AI 平台回答
引用来源
指标趋势
报告版本
监测计划
用户决策和 Agent 动作记录
```

## 第一版业务模型

第一版模型已沉淀在：

```text
aeo-platform/backend/app/ontology/specta_ontology.json
```

它定义了五类东西：

1. 对象：品牌、竞品、用户画像、使用场景、模拟问题、AI 平台回答、引用来源、指标快照、证据集合、报告、监测计划、用户决策、动作记录。
2. 关系：品牌拥有竞品、问题得到回答、回答引用来源、报告使用证据集合、监测计划跟踪问题等。
3. 动作：更新品牌画像、确认问题组、抓取 AI 回答、生成报告、创建监测计划、应用表格导入、对比指标快照、导出证据集合。
4. 函数：标准化品牌身份、计算品牌可见度、排序引用来源、比较指标快照、构建报告上下文、检索品牌证据。
5. 视图：品牌情报主页、报告证据视图、监测计划视图。

## 代码落地原则

### 原则 1：先注册，不迁移

第一阶段只建立注册中心：

```text
aeo-platform/backend/app/ontology/
  specta_ontology.json
  schemas.py
  registry.py
```

这层只读、可校验、可测试，不改变现有运行路径。

### 原则 2：先双写，再替换

后续对象化时，不要立刻移除现有 JSON：

```text
旧路径：AgentState / Message.output_data
新路径：Question / PlatformAnswer / Citation / EvidenceSet / ReportVersion
```

先让 A3/A4/A5 在写现有产物的同时，写入对象层。确认稳定后，再逐步让查询和 UI 消费对象层。

### 原则 3：先证据链，后主页

不要先做漂亮的品牌主页。先保证数据能回答：

1. 这份报告用了哪些问题？
2. 哪些平台回答支撑了这个结论？
3. 每个回答引用了哪些来源？
4. 哪些回答和指标相比上次发生了变化？

证据链稳定后，品牌主页才有真实内容。

### 原则 4：动作中心收口业务修改

任何会改变长期业务状态的能力，都应该逐步经过动作中心：

```text
确认问题
应用表格导入
生成报告
创建监测
重新抓取回答
更新品牌画像
```

动作中心必须记录：

1. 谁发起。
2. 作用在哪个品牌或对象。
3. 输入是什么。
4. 修改了哪些对象和关系。
5. 是否需要用户确认。
6. 成功或失败原因。
7. 产生了哪些报告、证据集合或监测计划。

### 用户操作发生在哪里

用户操作不能定义为“用户点了哪个按钮”，也不能定义为“Agent 在哪个节点写了数据”。这两种说法都会让系统重新散掉。

Specta 的边界应该是：

```text
界面发生入口：Chat / Canvas / 品牌主页 / API / 定时任务
业务提交点：ActionService.start_action
状态生效点：ActionService 调用对象写入、关系写入、artifact/version 写入后 commit
```

因此，用户的操作在产品上发生于某个界面入口，但在业务上发生于 `ActionRecord`。任何会改变长期品牌世界的行为，都必须能回答：

1. `actor_type`：是用户、Agent、系统任务，还是外部集成。
2. `origin_surface`：来自 Chat、Canvas、品牌主页、API、workflow node，还是 scheduler。
3. `origin_event_id`：来自哪次消息、按钮点击、请求、任务运行或节点执行。
4. `parent_action_record_id`：如果这是 Agent 或系统被用户操作触发的后续动作，要能追溯到上游动作。

这会形成两层清晰关系：

```text
用户在 Chat 点击“确认问题集”
  -> ActionRecord(confirm_question_set, actor_type=user, origin_surface=chat)
  -> Agent 执行抓取
     -> ActionRecord(run_answer_fetch, actor_type=agent, parent_action_record_id=上一步)
     -> 写入 Question -> PlatformAnswer -> Citation
```

前端按钮、Chat 消息、Canvas 操作只是入口；它们不直接代表业务事实。真正的业务事实是后端动作中心提交并成功应用的 `ActionRecord`。

这个判断会反过来改变界面设计：

1. 人类主要做两件事：观测对象、反馈判断。
2. Orchestrator 在另一个执行层面推进任务，不应该把每个内部步骤都变成用户主流程。
3. 当 Orchestrator 需要授权、确认、补充信息或纠偏时，再把一个明确的行动请求推到用户面前。
4. 用户主动想反馈时，也应该围绕品牌对象、问题、回答、引用、报告这些对象发起，而不是只在聊天流里寻找入口。

因此后续 UI 主体应该逐步从“聊天窗口 + 报告画布”升级为“品牌对象主页 + 对象关系视图 + 行动请求队列”。Chat 仍然存在，但它更像与 Orchestrator 交互的反馈通道，而不是唯一工作台。

## 分阶段路线

### P0：Ontology 设计文件和注册中心

本阶段完成：

1. 架构文档。
2. `specta_ontology.json`。
3. `OntologyRegistry`。
4. 注册中心单元测试。

验收标准：

1. 默认模型可加载。
2. 对象、关系、动作、函数、视图引用能被校验。
3. 不影响现有 workflow、API、前端。

### P1：证据对象双写

新增持久化对象或服务，优先处理：

```text
SimulatedQuestion
PlatformAnswer
CitationSource
EvidenceSet
ReportVersion
```

A3/A4/A5 继续写现有 artifact，同时写对象层。

当前分支已经先落地 P1 的承接层：

```text
aeo-platform/backend/app/models/brand_intelligence.py
aeo-platform/backend/app/services/brand_intelligence_projection_service.py
aeo-platform/backend/alembic/versions/020_add_brand_intelligence_objects.py
```

当前分支也已经把 A3/A4/A5 接入低风险双写：

1. A3 生成或导入问题后，写入 `brand_intelligence_questions`。
2. A4 抓取答案后，写入 `brand_platform_answers` 和 `brand_citation_sources`。
3. A5 生成报告后，创建 `brand_evidence_sets` 和 `brand_report_versions`。

这些写入失败时只记录 warning，不打断现有主流程；原有 `AgentState`、`Message.output_data`、Canvas artifact 仍然是当前用户路径的权威输出。

### P2：LinkService

建立最小关系服务：

```text
Question -> PlatformAnswer
PlatformAnswer -> Citation
EvidenceSet -> PlatformAnswer
Report -> EvidenceSet
MonitoringPlan -> Question
```

当前分支已先在 `BrandIntelligenceProjectionService` 内落地最小关系写入：

```text
simulated_question -> platform_answer
platform_answer -> citation_source
evidence_set -> platform_answer
report_artifact -> evidence_set
```

关系落在 `brand_object_links`，并通过唯一约束保证同一条关系重复投影时不会重复插入。第一版还没有把监测计划和动作记录写成关系边，这部分留到 P3/P4 与 ActionService、MonitoringPlan 双写一起处理。

### P3：ActionService 和 ActionLog

收拢：

```text
generate_question_set
confirm_question_set
run_answer_fetch
generate_report
create_monitoring_plan
apply_table_import
```

当前分支已开始落地 P3 的基础层：

```text
aeo-platform/backend/app/services/brand_action_service.py
aeo-platform/backend/app/services/brand_object_link_service.py
```

第一版 ActionService 负责：

1. 根据 `specta_ontology.json` 校验 action type。
2. 创建 `brand_action_records`，并记录 actor、origin surface、origin event 和 parent action。
3. 把 `action_record -> brand_entity` 写入 `brand_object_links`。
4. 为 A3/A4/A5 的双写链路记录 `generate_question_set`、`run_answer_fetch`、`generate_report`。

这一步仍然不改变用户确认协议，也不把业务修改强制收口到 ActionService；它先记录“已经发生的行动”和这些行动来自哪里。后续 P3b 才把确认、导入、监测创建这些会改变长期状态的入口真正改成 ActionService 提交。

P3b 已开始把用户反馈接入动作链路：

1. WebSocket inline confirmation 会记录用户动作，来源是 `chat_confirmation`。
2. 用户反馈不一定直接改对象；通用反馈先记录为 `record_user_feedback`。
3. 用户反馈已经从 action payload 升格为 `brand_user_decisions` 对象。
4. `BrandActionService` 会在用户动作或写入 `user_decision` 的动作发生时，自动创建用户决策对象，并写入 `user_decision -> action_record` 关系。
5. 确认问题集会记录为 `confirm_question_set`。
6. 表格导入的用户选择先记录为反馈，真正应用导入时由 workflow node 记录 `apply_table_import`。
7. API 侧的问题集确认、追加问题、创建监测计划也会写入动作记录。
8. 监测计划会写入 `monitoring_plan -> question_set -> simulated_question` 和 `monitoring_plan -> simulated_question` 关系。
9. 后续 Agent 动作可通过 `parent_action_record_id` 追溯到用户反馈。

P3c 继续补齐底层 Ontology 缺口：

1. `competitor_entity`、`audience_persona`、`usage_scenario`、`metric_snapshot` 不再只是字典概念，已经有对应持久表。
2. A1 竞品会投影成 `brand_competitor_entities`，并写入 `brand_entity -> competitor_entity`。
3. A2 用户画像和场景会投影成 `brand_audience_personas`、`brand_usage_scenarios`，并写入 `brand_entity -> audience_persona -> usage_scenario`。
4. A5 报告中的指标会投影成 `brand_metric_snapshots`，并写入 `metric_snapshot -> brand_entity`。
5. ActionService 会补齐动作输入中的 `brand_entity_id` / `actor_id`，校验权限域和必填输入；当前为了兼容旧流程默认记录 warning，后续高风险写操作可以打开 strict validation。
6. `BrandOntologyObjectService` 提供对象读取、关系读取和 Object View payload 组装，给后续品牌对象主页和 Orchestrator 读取对象世界使用。

这一步之后，底层不再只是“记录 workflow 产生的报告”，而是开始形成可查询的品牌对象图。

P3d 把对象图读取层接入正式 API：

1. `GET /api/v1/ontology/entities/{entity_id}/objects/{object_type}/{object_id}` 读取单个对象。
2. `GET /api/v1/ontology/entities/{entity_id}/objects/{object_type}/{object_id}/links` 读取对象关系。
3. `GET /api/v1/ontology/entities/{entity_id}/views/{view_key}/{object_type}/{object_id}` 读取对象视图 payload。
4. 所有入口先通过 `EntityService` 校验当前用户对品牌的访问权，避免对象图 API 绕过实体权限。
5. 这一步让后续 UI 和 Orchestrator 能读同一个对象世界，而不是继续从 workflow 临时状态各自拼装。

### P4：品牌情报主页

在前端增加品牌对象主页，让 chat 和 canvas 变成该主页中的工作方式之一，而不是唯一入口。

### P5：Agent 基于对象工作

Orchestrator 在执行前读取：

```text
当前品牌对象
问题集合
回答集合
证据集合
历史报告
监测状态
可执行动作
```

Agent 不再只依赖临时流程状态，而是操作持续积累的品牌世界。

P5a 已开始落地最小读取闭环：

1. `BrandOntologyWorldService` 会把品牌对象、对象集合、关系边、可走动作压缩成对象世界快照。
2. Orchestrator 在调用 LLM 前，会像读取 history manifest 一样读取 `ontology_world`。
3. `ontology_world` 只作为事实上下文进入 prompt，不允许 LLM 直接改对象。
4. 所有写入仍必须经过 `ActionService`，所有关系仍必须经过 `BrandObjectLinkService`。
5. 这一阶段不改变现有工具路由，也不改变前端入口；它先让 Agent 的判断建立在持久对象世界上。

P5b 把“读到对象世界”推进为“基于对象世界做行动判断”：

1. `BrandOntologyActionPlannerService` 会把对象世界快照转成确定性的阶段、缺口、动作就绪度和推荐动作。
2. 行动判断不依赖 LLM 自由推断，而是由后端根据对象数量、生命周期、必填输入、是否需要人确认来计算。
3. 每个动作会被标记为 `ready`、`ready_with_defaults`、`needs_input`、`needs_confirmation` 或 `blocked`。
4. `payload` 不完整时禁止调用 `ActionService`；需要确认的动作必须先让人确认。
5. Orchestrator prompt 现在同时包含 `品牌对象世界` 和 `对象行动判断`：前者说明事实，后者说明下一步能否行动。
6. 这一步仍然不直接改对象、不自动执行动作；它先把“Agent 应该怎么想下一步”沉淀成可测试的后端模块。

P5c 把 Orchestrator 上下文加工成缓存友好的分层结构：

1. 静态系统规则、静态技能索引、动态工具面、动态对象世界、动态行动判断、临时安全提醒被明确分层。
2. `PromptAssembly.cache_layer_manifest()` 会输出不含正文的分层清单，记录每段的 cache layer、来源、波动性、长度和指纹。
3. 当 runtime reminder 开启时，品牌名、对象世界、行动判断、待处理决策等动态信息不会进入静态 system prompt。
4. 对象世界和行动判断被标记为 `dynamic_object_world` 与 `dynamic_object_action_plan`，便于后续做缓存命中率和上下文预算观测。
5. 同一个 Skill 现在可以拥有静态层优先级和运行时层优先级：静态技能索引用于缓存稳定性，运行时技能索引可被压缩，不能挤掉对象世界、行动判断和人类待确认事项。
6. 这一步借鉴 Claude Code 的 cache prompt 思路：稳定规则尽量保持不变，动态上下文单独进入本轮提醒，避免每轮都破坏静态 prompt 缓存。

## 预期产品形态

最终 Specta 应该成为：

```text
企业品牌在 AI 世界里的情报系统
```

它不是简单的报告生成器，而是能长期维护：

1. 一个品牌的事实。
2. 一个品牌的问题库。
3. 一个品牌在各 AI 平台中的回答表现。
4. 一个品牌的引用来源和证据链。
5. 一个品牌的历史变化。
6. 一个品牌的监测计划。
7. 一个组织围绕这个品牌做过的决策。

这就是“AI 品牌情报”的核心：长期追踪、证据可查、动作可控、结论可复用、组织可协作。

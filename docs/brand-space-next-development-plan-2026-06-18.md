# Brand Space 后续开发规划

日期：2026-06-18
分支：`codex/brand-circle-board-prd`
当前基线：`af79dc2 fix(brand-space): harden graph update patch builder`

## 1. 目标

本文件用于承接 Brand Space / Brand Circle Board 的后续开发。当前已经完成画布底版、后端 Brand Space 基础模型、BoardRun 真实运行接入、真实运行同步节流和重复 resume dispatch 防护。下一阶段的目标不是继续扩展新概念，而是把 MVP 闭环真正收紧：

品牌实体关系库 → 画布运行 → Graph Update → 审阅 Graph Patch → 应用/保留/拒绝 → 基于 Graph Update 生成报告 → 可追溯查看资产与证据。

## 2. 当前状态

### 2.1 已完成

- Brand Space 并行入口已经存在，不替换旧 Dashboard。
- `/brand-space` 前端底版已包含 `Graph / Boards / Assets / Reports` 四个主 Section。
- Board 画布已支持节点、连线、并行平台抓取视觉、运行日志、节点 Inspector、动态效果和 reduced motion。
- 后端已新增 Brand Space Runtime 模型：
  - `board_runs`
  - `board_node_runs`
  - `board_artifacts`
  - `board_runtime_events`
  - `graph_updates`
  - `graph_patches`
  - `report_guardrail_results`
- 已接入真实 `BrandIntelligenceRun`：
  - `BoardRun.is_scaffold` 区分脚手架和真实运行。
  - `BoardRun.last_synced_at` 对真实运行同步做 30 秒 TTL。
  - `resume` 不再重复创建后台 dispatch。
  - 真实运行失败、缺失、阶段变化会映射到画布状态。
- 当前 Review 中的 real runtime connection 6 个问题已处理。
- Sprint A 第一轮已完成：
  - 新增品牌级 Review Items API。
  - GraphPatch decision 已具备终态幂等、审计字段和事件写入。
  - Graph 页已加入 Review Inbox、补丁详情、筛选和按钮 loading。
- Sprint A 第二轮已完成：
  - GraphSnapshot 已带上 `patchId / patchStatus / category / priority`，实体点击可精确定位补丁详情。
  - Patch decision 后会重算 GraphUpdate summary 和 graph_snapshot。
  - Rejected patch 不进入图谱快照，但仍保留在补丁队列中可审计。
  - 品牌级 Review Inbox 已补多 BoardRun 聚合测试。

### 2.2 仍是半成品的部分

- Graph Update 已脱离纯脚手架：真实 `BrandPlatformAnswer` 完成态可以生成确定性 GraphPatch，已接入实体词表 alias、产品线/战略词/风险词/竞品词和当前对象图谱投影输入。
- Review Loop 已接通并完成第二轮收口；真实 A4 答案进入 GraphPatchBuilder 的服务层回归已补，安利词表 fixture 已完成真实 BoardRun → GraphUpdate → Review Items 回测。
- Reports 第一轮已接入 GraphUpdate 解读：报告 payload 已从 GraphPatch / evidence refs 生成 `claims / trace_chains / platform_differences`，guardrail 会阻断越界 claim、缺证据竞品声明和缺平台行动建议；前端 Reports 已显示真实关键结论、平台差异和追溯链。
- Assets 第一轮闭环已完成：已有 artifact registry、详情预览、筛选、分页、报告反向入口和 trace links；真实对象存储下载/打开仍留作后续增强。
- Hardening 尾项已收口：Graph 正式版本写入/并发保护、报告 `publication_status` schema 下推、报告版本分配保护、旧数据 Assets 映射、50 节点画布压力入口、reduced motion 和键盘可达性补强均已完成；剩余工作转入真实对象存储下载/打开、生产态 E2E 和后续性能队列化。

### 2.3 开发进度记录

| 日期 | Sprint | 状态 | 已完成 | 仍需跟进 |
| --- | --- | --- | --- | --- |
| 2026-06-18 | Sprint A: Graph Review Loop | 第一轮完成 | `GET /brand-space/brands/{entity_id}/review-items`；GraphPatch decision 终态幂等；`graph_patch_accepted / graph_patch_rejected / graph_patch_kept_review / graph_update_applied` 事件；Graph 页 Review Inbox 与补丁详情 | 真实多 run Review Inbox 验证；图谱实体到 patch detail 的精确关联；GraphUpdate applied 后的正式图谱版本写入 |
| 2026-06-18 | Sprint A: Graph Review Loop | 第二轮完成 | 多 BoardRun Review Inbox 聚合测试；GraphSnapshot 追溯字段；实体点击到 patch detail；decision 后重算 summary/snapshot；rejected patch 从图谱快照移除 | 进入 Sprint B：从真实运行产物构建 GraphPatch，而不是继续依赖 `_default_patches` |
| 2026-06-18 | Sprint B: Real GraphPatchBuilder | 第一轮完成 | 新增确定性 `GraphPatchBuilderService`；真实 completed `BoardRun` 会从成功抓取回答生成 GraphUpdate；支持健康管理、风险顾虑、明确竞品比较三类 patch；写入 `graph_update_created` 事件和 artifact row count；补重复同步不生成第二个 GraphUpdate 测试；画布抓取组与异常审阅节点重叠已修正，浏览器复测 8 节点 / 8 连线 / 0 重叠 | 接入安利实体词表 fixture；补 sentiment=3/5、competitor confidence=0.7 边界；把实体词表和对象图谱投影纳入 builder 输入 |
| 2026-06-18 | Sprint B: Real GraphPatchBuilder | 完成 | `GraphPatchBuilderService` 已读取 `input_scope.entity_lexicon`；支持 alias 匹配、产品/子品牌 `supports`、战略/方案 `associated_with`、风险词 `risk_related`、竞品 `competes_with`；patch evidence refs 带 `matched_entity_*`；Graph projection 纳入 builder payload；安利 fixture 真实回测覆盖 GraphUpdate → Review Items；sentiment=3/5 和 competitor confidence=0.7 边界已测试 | 进入 Sprint C：报告必须从 GraphUpdate 生成结构化解读；正式图谱版本写入和并发版本检查放入 Hardening/版本化任务 |
| 2026-06-19 | Sprint B: Review Hardening | 完成 | `_ensure_real_graph_update` 从 polling read-path 拆出 pending/queued/background build；竞品 confidence 更保守；已接受竞品跨 run 转为 `update_strength`；中文 term 匹配增加否定/粘连保护；connection strength 改为对数衰减；补回归测试并提交 `af79dc2` | 完整 worker/任务表队列化、竞品候选和信号 pattern 配置化进入后续 hardening |
| 2026-06-19 | Sprint C: Report From GraphUpdate | 完成 | 报告 payload 已从 GraphUpdate patches 生成 `claims / trace_chains / platform_differences`；每个 trace chain 覆盖 Report claim → GraphPatch → EntityRelation → Answer → Question → Platform；guardrail 新增 `graph_update_scope`；前端 Reports 接真实关键结论、平台差异和追溯链；新增品牌级报告列表、报告版本详情和正式发布 API；旧报告标记为 `pre_graph_update` 且不能作为 GraphUpdate 报告发布；麦当劳餐饮品牌逻辑测试覆盖非营养健康品牌报告 | 后续进入 Sprint D：Assets detail、资产反向追溯、分页和完整浏览器 E2E |
| 2026-06-20 | Sprint C: Report Review Hardening | Review 修复完成 | 按 `review-brand-space-complete-graph-update-reports-2026-06-20.md` 收口：补齐报告辅助方法/常量；publish 时实时重算 guardrail 并刷新持久化结果；GraphPatchBuilder corpus helper 改为公开方法；报告 status 过滤改为分页扫描；真实 answers 分支补麦当劳品牌逻辑测试；Markdown 输出盲区示例；前端 `source_type` 类型收紧并说明 mock-only guardrail fallback；浏览器 smoke 验证 `/brand-space` 报告页中文、核心判断、AI 盲区、证据样本和报告校验正常渲染 | 后续进入 Sprint D：Assets detail、资产反向追溯、分页和完整浏览器 E2E；`publication_status` 下推到 schema/JSON 查询可作为后续性能 hardening |
| 2026-06-20 | Sprint D: Assets Detail And Trace Back | 完成 | 新增 artifact detail API；`board-runs/{run_id}/assets` 和 events 支持 limit/offset，assets 支持 artifact_type 筛选；artifact detail 返回安全 preview，不读取任意磁盘路径；trace links 覆盖 BoardRun、NodeRun、GraphUpdate、ReportVersion；报告生成后同步登记 `report` artifact，并绑定具体 `report_version_id`，避免多版本报告在 Assets 里串版本；前端 Assets 增加类型筛选、详情抽屉、JSON/JSONL/table/summary 预览、加载更多和追溯跳转；Reports 增加“查看相关资产”反向入口；补 API/service 测试覆盖分页、筛选、跨用户拦截和 GraphUpdate/Report trace；浏览器 smoke 覆盖 Assets、Reports → Assets 和旧 Dashboard 入口 | 后续进入 Hardening：真实对象存储下载/打开、50 节点性能、生产态 E2E 与可访问性细化 |
| 2026-06-20 | Sprint D: Review Fix | 完成 | 按 `review-brand-space-sprint-d-assets-trace-back-2026-06-20.md` 收口：`_latest_report_for_graph_update` 改为按确定性 `report_id` 查询，不再拉 200 条报告扫 payload；report artifact 缺 `report_version_id` 时不再 fallback 到 latest report；GraphUpdate 未生成时补丁/审阅资产显示明确空态；问题集无内联内容时改为 summary；Reports → Assets 找不到 report 资产时提示而不是打开第一个资产；补 preview 分支、events offset、report trace 降级测试；浏览器 smoke 复测 report 资产反向入口和旧 Dashboard 隔离 | 进入 Hardening 队列；`publication_status` 下推和报告版本并发分配仍作为后续 schema/队列化议题 |
| 2026-06-20 | Sprint E: Graph Versioning And Concurrency | 第一块完成 | GraphUpdate 创建时根据品牌最新已应用版本生成 `before_graph_version / after_graph_version`；GraphPatch 全部终态后先检查版本基线，不一致则标记 GraphUpdate `failed` 并写入 `graph_update_version_conflict` 事件；品牌 Graph 读取会跳过已失败的过期更新，避免 stale update 覆盖正式图谱；补服务层回归覆盖两个并发 GraphUpdate、第一条应用、第二条过期阻断、第三条递增到 `v0.2.0` | 继续 Sprint E：`publication_status` 下推到 schema/查询、报告版本并发分配保护、旧数据映射和 50 节点/可访问性回归 |
| 2026-06-20 | Sprint E: Report Schema And Version Hardening | 第一块完成 | `BrandReportVersion` 新增 `publication_status` 列和 `ix_brand_report_versions_entity_publication` 索引；新增迁移 `026_add_report_publication_status.py` 回填旧报告和 GraphUpdate 报告状态；GraphUpdate 报告生成/发布同步写 payload 与列，非 GraphUpdate 报告写 `pre_graph_update`；报告列表普通状态过滤优先走 SQL 条件并做 source type 安全过滤，`pre_graph_update` 仅对未迁移旧数据做有限 fallback；报告版本分配前锁定父 GraphUpdate，读取最新 version 时使用 `FOR UPDATE`；补麦当劳报告发布与分页过滤回归 | 继续 Sprint E：旧抓取答案进入 Assets 的数据映射、50 节点画布压力、reduced motion/键盘可达性和 `/dashboard` feature flag 回归 |
| 2026-06-20 | Sprint E: Review Fix | 完成 | 按 `review-brand-space-harden-trace-back-and-graph-version-2026-06-20.md` 收口：migration 026 改为解析 JSON 精确回填，避免 `LIKE` 误匹配；GraphUpdate apply 前锁品牌实体范围并锁 latest applied 行；report source type 增加 `report_id/artifact_id` 契约判断，payload 丢失 `graph_update_id` 时仍能识别 GraphUpdate 报告；`_reports_for_publication_status` 增加防御注释；Graph 页补 failed/version_conflict 提示；前端 runtime event severity 类型加入 `error`；补 migration helper 与 source type 回归测试 | 继续 Sprint E：旧抓取答案进入 Assets 的数据映射、50 节点画布压力、reduced motion/键盘可达性和 `/dashboard` feature flag 回归 |
| 2026-06-20 | Sprint E: Legacy Assets And Canvas Hardening | 完成 | 旧 `BrandPlatformAnswer` 可映射到 raw/parsed Assets，按 run session 或品牌最近成功回答只读取样并展示行数；旧答案资产 detail 返回安全 JSONL/table 预览，trace 仅保留 BoardRun/NodeRun，不伪造 GraphUpdate/Report；前端新增 `?canvasFixture=50-nodes` 压力底版，画布 stage 按节点数扩展并用扩展坐标计算连线端点；补主导航、画布工具条、节点、平台卡、Review 操作、Assets drawer、Reports 版本选择的可访问标签；reduced motion 下禁用扫光、流动包和脉冲视觉 | 后续增强：真实对象存储下载/打开、生产态长跑 E2E、WebSocket/SSE 或任务队列化性能优化 |
| 2026-06-20 | Sprint E: Legacy Assets Review Fix | 完成 | 按 `review-brand-space-legacy-assets-canvas-hardening-2026-06-20.md` 收口：移除 `get_assets/get_artifact_detail` 中 legacy answer artifact 的读端写入与 `commit()`；列表/详情改为只读 projection，不再每次读 COUNT；非法 `session_id` 在 scope 阶段降级为 `brand_recent_answers`，metadata 与查询行为一致；问题 lookup 抽到 `GraphPatchBuilderService.question_lookup_for_answers` 复用；补 `run_session_answers` 主路径和非法 session 回归测试；压力 fixture URL 支持 `N-nodes` 并给 24 节点阈值加注释 | 等待下一轮 review 或进入真实对象存储下载/打开增强 |
| 2026-06-21 | Sprint F: Performance And Object Storage | 完成 | `GET /events` 新增 `after_sequence` cursor 和 `sync=false` 默认轻量读，前端运行日志改为 2.5 秒增量事件轮询、15 秒全量 run 刷新；`get_assets/get_artifact_detail` 默认不触发真实运行同步；新增本地对象仓配置 `BRAND_SPACE_ASSET_STORAGE_ROOT`，artifact access/download API 只解析受控 `assets/...` object key；GraphUpdate 报告资产生成时物化 Markdown，可在 Assets drawer 下载；补危险 key、对象下载、event cursor 和轻量读不同步回归；验证通过 `validate_change.py`、targeted pytest、lint、build | 后续增强：生产态长跑 E2E、SSE/WebSocket 事件通道、对象仓云端 provider 抽象和真实大文件资产物化 |
| 2026-06-21 | Sprint F: Runtime Polling And Artifact Storage Review Fix | Review 修复完成 | 按 `review-brand-space-runtime-polling-artifact-storage-2026-06-21.md` 收口：增量事件页 `pagination.total` 改为 `null`，避免伪造总数；报告 artifact 改为异步文件写入且对象物化成功后才登记 DB；前端下载改走统一 response error helper；运行日志 240 条窗口改为显式折叠提示；artifact access 返回前防御性剥离 `_local_path`；`sequence=None` 保持 `null`；补写入失败、外部 URL、cursor total 和 sequence 空值回归；验证通过 `validate_change.py`、targeted pytest、lint、build | 后续确认是否进入生产态长跑 E2E、SSE/WebSocket 事件通道或云端对象仓 provider 抽象 |
| 2026-06-21 | Sprint F: QA/PM Pre-production Gate Fix | 验收修复完成 | QA Agent 未发现 blocking；PM Agent 发现两个上线前 blocking 并已收口：Brand Space 默认入口改为 Graph，首次读取不再自动创建 scaffold run；Graph 版本标签和更新时间线改为读取真实 `GraphUpdate` / context，不再展示硬编码假版本；后端全量空间 payload 改取最新 240 条 runtime events，避免 15 秒 full refresh 把运行日志倒回旧窗口；补 access/download 跨用户 404 测试和长日志窗口回归；验证通过 `validate_change.py`、targeted pytest、lint、build | 上生产前仍建议补一次真实后端浏览器 smoke：`/brand-space` Graph 首屏、手动启动运行、Graph Update 审阅、Report 生成/发布阻断、Assets 详情与下载、旧 `/dashboard` 隔离 |
| 2026-06-21 | Sprint F: Final QA/PM Real Runtime Gate | 验收修复完成 | 独立 QA/产品 Agent 做最终只读验收后发现 release gate 问题并已收口：报告页首屏新增“发布护栏阻断”摘要，block guardrail 不再藏在页面底部；品牌空间默认 run 改按 `created_at` 选择，避免读端同步 `updated_at` 把旧 scaffold run 顶到首屏；非 scaffold 的终态空运行不再回退展示 scaffold GraphUpdate/report；Review Inbox 和默认 Reports API 改为当前有效 GraphUpdate 范围，无当前 GraphUpdate 时不泄漏旧 scaffold patch/report；无 GraphUpdate 的 Reports 页面隐藏历史版本列表和报告正文模板，只显示“等待图谱更新”空态；补服务层回归测试。验证通过 `validate_change.py`、`npm run lint`、`npm run build` 和浏览器 smoke | 当前共享 DB 没有非 scaffold GraphUpdate；上生产前仍需用真实 A4 凭据保留一条非 scaffold 完整样本，覆盖真实抓取 → GraphUpdate → Review → Report → Assets 下载 |

## 3. 产品 Section 完成度

| Section | 当前状态 | 完成定义 |
| --- | --- | --- |
| Boards | 基本完成 | 能启动真实运行、恢复运行态、展示阶段进度、暂停/继续/停止不会重复 dispatch，节点和连线在桌面视口稳定。 |
| Graph | 版本化第一块完成 | 图谱能显示当前品牌实体关系库、Graph Update 差异、待审阅层；用户可以从图谱中处理补丁并看到版本变化；过期 GraphUpdate 不再覆盖正式图谱。 |
| Reports | 完成 | 报告只从某次 Graph Update 生成，guardrail 能阻断发布，关键结论能追溯到 patch / relation / answer / question / platform；支持报告版本列表、版本详情、正式发布状态和旧报告 `pre_graph_update` 隔离。 |
| Assets | 完成第一轮 | 用户能按 run/type 查看中间产物，安全预览 JSON/JSONL/table，能跳回对应 Graph Update 和 Report；真实对象存储下载/打开后续增强。 |

按产品主 Section 口径，`Boards / Graph / Reports / Assets` 已完成 MVP 闭环并进入稳定和回归阶段。后续重点不再是补主链路，而是对象存储下载/打开、生产态 E2E、队列化/事件流性能和更完整的可访问性审计。

## 4. 开发路线

### Phase 1: Graph Review Loop 收口

优先级：P0

目标：让 Graph Update 成为主交付物，而不是画布旁边的辅助列表。

#### 后端任务

1. 完成 GraphPatch 决策审计字段的使用规范。
   - 已完成：决策人、决策时间、决策理由、应用结果可查询。
   - 已完成：重复提交同一终态 patch decision 幂等。
   - 已完成：终态 patch 不允许反转，不制造新事件。

2. 增加品牌级待审阅聚合查询。
   - 已完成端点：`GET /api/v1/brand-space/brands/{entity_id}/review-items`
   - 已完成聚合来源：当前未处理的 `graph_patches`。
   - 已完成最小筛选：`risk / competitor / new_entity / conflict / low_confidence`。

3. 明确 GraphUpdate 状态机。
   - `needs_review`：仍有需要人工处理的 patch。
   - `partial`：存在未知或未来扩展状态。
   - `applied`：所有 patch 进入 terminal 状态。
   - `failed`：Graph Update 构建或应用失败。

4. 补充事件写入。
   - 已完成：`graph_patch_accepted`
   - 已完成：`graph_patch_rejected`
   - 已完成：`graph_patch_kept_review`
   - 已完成：`graph_update_applied`

#### 前端任务

1. 强化 `GraphHomeView`。
   - 待审阅实体在图谱中有明确视觉层级。
   - 点击实体可以打开 patch detail。
   - detail 里展示：变更类型、分数、证据数、风险/竞品原因、建议动作。

2. 强化 `GraphUpdateQueue`。
   - 已完成：按 `自动应用 / 待审阅 / 已接受 / 已拒绝 / 已阻断` 分组。
   - 已完成：操作后按钮进入 disabled/loading 状态。
   - 已完成：操作后保留用户可读的结果提示。

3. 增加 Review Inbox。
   - 已完成：作为 Graph 页右侧 panel，不新增主导航。
   - 已完成：支持按风险、竞品、新实体过滤。
   - 已完成：后端 API 已按品牌聚合，可跨 Board Run 返回待审阅项；仍需真实多 run 数据回测。

#### 验收

- 用户可以在 Graph 页处理所有待审阅 patch。
- 处理结果刷新后仍保持一致。
- 同一 patch 重复处理不会重复写事件或重复应用。
- 待审阅实体不会静默进入内圈或中圈。

### Phase 2: Real Graph Update 质量提升

优先级：P0

目标：减少 `_default_patches` 脚手架依赖，让 GraphPatchBuilder 真正从真实运行产物和实体关系库生成 Graph Update。

#### 后端任务

1. 新增或拆出 `GraphPatchBuilderService`。
   - 输入：`BoardRun`、`BrandIntelligenceRun`、问题集、抓取答案、实体词表、当前品牌图谱投影。
   - 输出：`GraphUpdate`、`GraphPatch[]`、`BoardArtifact[]`。
   - 已完成：从真实 `BrandPlatformAnswer` / `BrandIntelligenceQuestion` 生成 GraphPatch，并在真实 completed run 中落地 GraphUpdate。
   - 已完成：`input_scope.entity_lexicon` 和当前对象图谱投影已作为 builder 输入。

2. 落实实体匹配与关系构建。
   - 从答案中提取实体提及。
   - 匹配实体词表和已有品牌对象图谱。
   - 输出关系类型：`supports / associated_with / risk_related / competes_with`。
   - 已完成：词表 alias、产品/子品牌、战略/方案、风险词、竞品词进入确定性匹配。
   - 已完成：关系类型输出为 `supports / associated_with / risk_related / competes_with`。

3. 锁定圈层规则。
   - `sentiment_or_risk_score < 5` 不进内圈。
   - `3-5` 只能进入中圈候选或待审阅，需要连续两次正向证据后才能升级。
   - `< 3` 进入风险层或待审。
   - `competes_with` 必须有明确替代、推荐或对比信号。
   - 竞品置信度 `< 0.7` 只进待审阅，不自动入竞品圈。
   - 已复用现有 `allocate_graph_zone` 和 `detect_competitor_context`，真实 builder 不绕过这些规则。
   - 已完成边界测试：sentiment=3、sentiment=5、competitor confidence=0.7。

4. 版本写入。
   - GraphUpdate 必须有 `before_graph_version` 和 `after_graph_version`。
   - 自动应用 patch 更新投影，待审阅 patch 不改变正式图谱。
   - 需要处理并发更新，至少用 updated_at/version 检查防止覆盖。
   - 第一轮已完成：每个真实 BoardRun 只生成一次 GraphUpdate，重复同步不会重复创建。
   - Sprint B 收口说明：本 Sprint 完成 GraphUpdate 构建与 Review 输入，不把正式图谱版本写入和并发锁作为本轮阻塞项；它们进入后续版本化/Hardening。
   - Sprint E 第一块已完成：GraphUpdate 创建时按品牌最新已应用版本递增；apply 前检查 `before_graph_version` 是否仍等于当前正式版本，过期则标记 `failed` 并写入冲突事件，不发 `graph_update_applied`。

#### 前端任务

1. Graph 页显示真实 GraphUpdate 摘要。
2. Graph Update detail 显示 before/after 差异。
3. 图谱占位状态只在真实运行未完成时出现；完成后必须显示真实实体变化。

#### 验收

- 已完成：用安利实体词表 fixture 跑出真实 GraphPatch。
- 已完成：每个非阻断 patch 都有 evidence refs，且 evidence refs 带 `matched_entity_*`。
- 已完成：风险和竞品边界测试覆盖 sentiment=3、5 和 confidence=0.7。
- 已完成：真实 completed BoardRun 后可生成非空 GraphUpdate，并可查询 Review Items。

### Phase 3: Report Guardrails And Trace Chain

优先级：P1

目标：报告只作为 Graph Update 的解读层，不能成为另一个事实来源。

#### 后端任务

1. 从 GraphUpdate 生成报告骨架。
   - 核心变化摘要。
   - 圈层变化。
   - 风险和竞品候选。
   - 平台差异。
   - 下一步建议。
   - 第一轮已完成：从 GraphPatch / evidence refs 生成结构化 `claims / trace_chains / platform_differences / recommended_actions`。

2. 完成报告后处理校验。
   - 战略词结论相似度 `> 0.8` 阻断。
   - 声称发现竞品但缺 evidence span 阻断。
   - 80% 以上证据来自同一问题时警告或阻断。
   - 行动建议缺少具体平台名阻断。
   - 报告引用了 GraphUpdate 以外的实体时阻断。
   - 第一轮已完成：`graph_update_scope` guardrail 已阻断报告引用本次 GraphUpdate 之外的 patch；已有竞品证据、行动建议平台、证据集中度和战略词相似度校验继续生效。

3. 写入 `BrandReportVersion`。
   - 必须关联 `graph_update_id`。
   - 必须保存 guardrail result。
   - blocking guardrail 失败时状态为 `needs_review`，不能发布为正式报告。
   - 第一轮已完成：报告仍写入 `BrandReportVersion.payload`，并通过 `report_guardrail_results.report_version_id` 关联 guardrail；`payload.publication_status` 区分 `needs_review / draft / publishable`。
   - Sprint E 第一块已完成：`publication_status` 已下推为 `BrandReportVersion` 列并建立品牌级索引；payload 保留兼容字段，DTO 读取列优先，旧报告仍以 `pre_graph_update` 隔离。

#### 前端任务

1. `ReportReviewView` 改成真实 report + guardrail 数据驱动。
   - 第一轮已完成：关键结论、平台差异、报告校验和发布按钮均读取真实 report/guardrail payload。
2. 加 Trace Chain Viewer。
   - Report claim → GraphPatch → EntityRelation → Answer → Question → Platform。
   - 第一轮已完成：Reports 右侧展示真实 trace chain，未生成报告前不再使用 mock trace。
3. 发布按钮必须尊重 guardrail 状态。
   - 第一轮已完成：blocking guardrail 下禁用发布；无阻断时可请求生成 `publishable` 版本。

#### 验收

- 缺 evidence span 的竞品声明不能发布。
- 缺平台名的建议不能发布。
- 每个关键 claim 都能追溯到平台和问题。
- 报告刷新后版本和状态不丢失。

### Phase 4: Assets View 完整化

优先级：P1

目标：Assets 是中间产物文件夹，不抢 Graph 和 Report 的主视觉，但要能排查和追溯。

#### 后端任务

1. 完成 artifact listing 参数。
   - `run_id`
   - `artifact_type`
   - `limit`
   - `cursor` 或 `offset`

2. 增加 artifact detail。
   - 返回 metadata。
   - 对 JSON / JSONL / table-like 输出返回安全预览。
   - 大文件只返回摘要和下载/打开路径，不直接内联。

3. 建立反向关联。
   - artifact → node_run
   - artifact → graph_update
   - artifact → report_version

#### 前端任务

1. Assets 增加筛选条。
2. 点击资产打开详情抽屉。
3. 支持复制路径、查看预览、跳转 Graph Update / Report。

#### 验收

- 原始答案、标准化答案、GraphPatchSet、GraphUpdate、Report 都能在 Assets 找到。
- 大型资产不会卡住页面。
- 资产详情不会泄露不该给当前用户看的路径或内容。

### Phase 5: Hardening, Migration And Backtest

优先级：P1

目标：让 Brand Space 可以稳定作为并行 Dashboard v2 区域存在。

#### 后端任务

1. 增加分页和限流。
   - events 默认最新 100 条。
   - assets 默认分页。
   - review items 默认分页。

2. 补旧数据映射。
   - 旧报告进入 Reports 区域，但标记为 `pre_graph_update`。
   - 旧抓取答案尽可能进入 Assets。
   - 没有 trace chain 的旧报告不能伪装成 Graph Update 报告。

3. 回测 fixture。
   - 使用安利实体词表和记录化抓取答案。
   - 跑完整：BoardRun → GraphUpdate → Review → Report → Assets。

#### 前端任务

1. 50 节点画布压力验证。
2. reduced motion 验证。
3. 键盘可达性验证。
4. `/dashboard` 和 `/brand-space` 并行入口回归。

#### 验收

- `NEXT_PUBLIC_BRAND_SPACE_ENABLED=false` 时旧 Dashboard 不受影响。
- `/brand-space` 不再出现节点堆叠、连线漂浮、英文回退。
- 完整回测截图和命令结果可复现。

## 5. 推荐执行顺序

### Sprint A: Graph Review Loop

目标：把 Graph 页变成真正的图谱审阅工作区。

建议任务：

1. 后端 review items 聚合 API。
2. GraphPatch decision 幂等和事件补强。
3. Graph 页 pending review detail。
4. Review Inbox panel。
5. API + frontend DOM 验证。

交付结果：用户能在 Graph 页处理所有待审阅图谱变化。

### Sprint B: Real GraphPatchBuilder

目标：减少脚手架 patch，让真实运行产物进入 Graph Update。

建议任务：

1. 已完成：`GraphPatchBuilderService` 独立出来。
2. 已完成：从真实问题/答案/实体词表构建 patch。
3. 已完成：补 evidence refs，并带 `matched_entity_*`。
4. 已完成：补圈层边界和竞品边界测试。
5. 已完成：安利 fixture real BoardRun backtest。

交付结果：完成真实 BoardRun 后能生成可审阅的 GraphUpdate。

### Sprint C: Report From GraphUpdate

目标：报告成为 GraphUpdate 的可信解读。

建议任务：

1. 报告 skeleton builder。
   - 第一轮已完成。
2. guardrail blocking 状态写入。
   - 第一轮已完成。
3. Trace Chain Viewer。
   - 第一轮已完成。
4. 报告发布按钮和状态。
   - 第一轮已完成。
5. 报告相关 API 测试。
   - 已完成 service/API targeted 覆盖：报告生成、版本列表、详情读取、发布、旧报告 `pre_graph_update` 隔离，以及麦当劳餐饮品牌逻辑回归；后续仍需补浏览器 E2E。

交付结果：报告能生成、阻断、追溯、版本化。

### Sprint D: Assets And Hardening

目标：补齐中间产物和稳定性。

建议任务：

1. Assets detail API。
2. Assets 筛选和详情抽屉。
3. events/assets 分页。
4. 旧数据映射。
5. 全链路回测。

交付结果：Brand Space MVP 可作为并行区域进入更完整试用。

## 6. 非目标

本轮后续开发仍不做：

- 不替换旧 Dashboard。
- 不做自由低代码画布编排。
- 不做 WebSocket/SSE 事件流，继续使用 polling + TTL。
- 不默认每次 Graph Update 自动发布报告。
- 不把报告作为事实源，报告只能解释 GraphUpdate。

## 7. 风险和控制

| 风险 | 控制方式 |
| --- | --- |
| GraphPatch 继续脚手架化 | Sprint B 必须把 builder 从真实产物输入开始拆，不再扩大 `_default_patches`。 |
| Review Loop 视觉存在但事实未落库 | 所有前端 action 必须有 API 测试覆盖，刷新后状态必须一致。 |
| 报告生成重新变成泛泛 AI 总结 | 报告只能从 GraphUpdate skeleton 生成，guardrail 阻断无证据声明。 |
| Assets 暴露内部路径或跨用户数据 | 所有读取必须走当前用户访问控制，不允许 user-facing 路径使用 internal admin bypass。 |
| Polling 压力回升 | 保持 `last_synced_at` TTL，events/assets/review items 加分页。 |
| 旧 Dashboard 回归 | 每轮 UI 改动都验证 `/dashboard` 和 `/brand-space` 两个入口。 |

## 8. 必跑验证

每个后续 Sprint 至少运行：

```bash
python scripts/validate_change.py --pytest aeo-platform/backend/tests/test_brand_space_service.py --pytest aeo-platform/backend/tests/test_brand_space_api.py
```

后端行为变更还要加：

```bash
python -m pytest aeo-platform/backend/tests/test_brand_intelligence_run_service.py aeo-platform/backend/tests/test_intelligence_runs_api.py -q
python -m ruff check aeo-platform/backend/app/services/brand_space_service.py aeo-platform/backend/app/api/v1/brand_space.py aeo-platform/backend/tests/test_brand_space_service.py aeo-platform/backend/tests/test_brand_space_api.py
```

前端可见变更还要加：

```bash
npx tsc --noEmit
npm run lint
npm run build
```

UI 变更必须额外做：

- 浏览器验证 `/brand-space`。
- 浏览器验证旧 `/dashboard` 未受影响。
- 截图或 DOM 检查中文 UI、节点不堆叠、连线端点贴合节点。
- 扫描异常问号占位符，防止中文编码损坏。
- 扫描旧 AI 视觉关键词，防止引入不符合 Specta 视觉系统的调色和特效。

## 9. 下一步建议

当前建议继续 Sprint F 的 release gate 收口，不再回头扩展新概念。本轮已完成性能改造、对象存储基础能力和最终 QA/PM 发现的交互可信边界问题。剩余最大前置条件不是 UI 组件，而是生产态数据样本：当前共享 DB 没有非 scaffold 的 GraphUpdate，所以上生产前必须跑出并保留一条真实 A4 全链路样本。

下一张具体开发票：

标题：`Brand Space Production Runtime And Event Stream Hardening`

范围：

1. 补生产态长跑 E2E：真实 A4 凭据可用时跑一次完整 Brand Space run，从运行、GraphUpdate、Review、Report 到 Assets 下载，并确认样本 `BoardRun.is_scaffold=false`。
2. 评估 polling 到 SSE/WebSocket 的切换边界：事件流可先替代 logs，节点状态仍由周期性 run snapshot 保底。
3. 把对象仓 provider 抽象从 local 扩展为 cloud adapter，但保持当前 `objectKey/access/download` API 不变。
4. 补大文件资产物化策略：raw answers / parsed answers 优先写对象仓，列表只返回 metadata 与 bounded preview。
5. 对 50 节点压力底版做浏览器回归：确认增量事件轮询不会造成画布抖动、日志重复或 Inspector 过度刷新。

Sprint E 已完成部分：

- GraphUpdate 版本从最新已应用图谱递增。
- 过期 GraphUpdate 在 apply 时被阻断为 `failed`。
- 冲突事件写入 `graph_update_version_conflict`。
- 品牌 Graph 读取跳过已失败的 stale update。
- `publication_status` 已下推到 `BrandReportVersion` 列并建立品牌级索引。
- 报告生成/发布同步写 payload 与列。
- 报告版本分配前锁定父 GraphUpdate，并对最新 version 行使用 `FOR UPDATE`。
- Review Fix 已补：migration 精确回填、GraphUpdate apply 实体级锁、Graph failed 冲突提示。
- 旧答案 Assets 映射已补：raw/parsed 可从历史 `BrandPlatformAnswer` 回填安全预览和行数，但不伪造 GraphUpdate trace chain。
- 50 节点画布压力入口已补：`/brand-space?canvasFixture=50-nodes` 使用独立 fixture，stage 自动放大并重新计算连线端点。
- reduced motion 和键盘可达性第一轮已补：动态扫光/流动包/脉冲可降级，主导航、画布工具条、节点、Review 操作、Assets drawer 和 Reports 版本选择具备明确标签。
- Review Fix 已补：legacy answer assets 不再在 GET 读端点写库或提交事务；legacy 降级只读展示 bounded sample，run session 主路径继续使用精确 session 过滤。
- 性能与对象存储增强已补：events 支持 cursor 增量读取，前端 2.5 秒只拉新增事件、15 秒全量刷新；assets/detail 默认轻量读；报告资产可物化 Markdown 并通过受控 download API 下载。
- 已跑回归：`python scripts/validate_change.py --pytest "aeo-platform/backend/tests/test_brand_space_service.py aeo-platform/backend/tests/test_brand_space_api.py"` PASS；`npm run build` PASS；`npm run lint` PASS 但保留 3 个既有 warning。

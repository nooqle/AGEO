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
- Assets 还只是列表壳：已有 artifact registry，但缺少详情预览、筛选、打开和反向追溯。
- Hardening 未完成：需要 50 节点画布性能、旧 Dashboard 回归、旧数据映射、可访问性和完整回测。

### 2.3 开发进度记录

| 日期 | Sprint | 状态 | 已完成 | 仍需跟进 |
| --- | --- | --- | --- | --- |
| 2026-06-18 | Sprint A: Graph Review Loop | 第一轮完成 | `GET /brand-space/brands/{entity_id}/review-items`；GraphPatch decision 终态幂等；`graph_patch_accepted / graph_patch_rejected / graph_patch_kept_review / graph_update_applied` 事件；Graph 页 Review Inbox 与补丁详情 | 真实多 run Review Inbox 验证；图谱实体到 patch detail 的精确关联；GraphUpdate applied 后的正式图谱版本写入 |
| 2026-06-18 | Sprint A: Graph Review Loop | 第二轮完成 | 多 BoardRun Review Inbox 聚合测试；GraphSnapshot 追溯字段；实体点击到 patch detail；decision 后重算 summary/snapshot；rejected patch 从图谱快照移除 | 进入 Sprint B：从真实运行产物构建 GraphPatch，而不是继续依赖 `_default_patches` |
| 2026-06-18 | Sprint B: Real GraphPatchBuilder | 第一轮完成 | 新增确定性 `GraphPatchBuilderService`；真实 completed `BoardRun` 会从成功抓取回答生成 GraphUpdate；支持健康管理、风险顾虑、明确竞品比较三类 patch；写入 `graph_update_created` 事件和 artifact row count；补重复同步不生成第二个 GraphUpdate 测试；画布抓取组与异常审阅节点重叠已修正，浏览器复测 8 节点 / 8 连线 / 0 重叠 | 接入安利实体词表 fixture；补 sentiment=3/5、competitor confidence=0.7 边界；把实体词表和对象图谱投影纳入 builder 输入 |
| 2026-06-18 | Sprint B: Real GraphPatchBuilder | 完成 | `GraphPatchBuilderService` 已读取 `input_scope.entity_lexicon`；支持 alias 匹配、产品/子品牌 `supports`、战略/方案 `associated_with`、风险词 `risk_related`、竞品 `competes_with`；patch evidence refs 带 `matched_entity_*`；Graph projection 纳入 builder payload；安利 fixture 真实回测覆盖 GraphUpdate → Review Items；sentiment=3/5 和 competitor confidence=0.7 边界已测试 | 进入 Sprint C：报告必须从 GraphUpdate 生成结构化解读；正式图谱版本写入和并发版本检查放入 Hardening/版本化任务 |
| 2026-06-19 | Sprint B: Review Hardening | 完成 | `_ensure_real_graph_update` 从 polling read-path 拆出 pending/queued/background build；竞品 confidence 更保守；已接受竞品跨 run 转为 `update_strength`；中文 term 匹配增加否定/粘连保护；connection strength 改为对数衰减；补回归测试并提交 `af79dc2` | 完整 worker/任务表队列化、竞品候选和信号 pattern 配置化进入后续 hardening |
| 2026-06-19 | Sprint C: Report From GraphUpdate | 完成 | 报告 payload 已从 GraphUpdate patches 生成 `claims / trace_chains / platform_differences`；每个 trace chain 覆盖 Report claim → GraphPatch → EntityRelation → Answer → Question → Platform；guardrail 新增 `graph_update_scope`；前端 Reports 接真实关键结论、平台差异和追溯链；新增品牌级报告列表、报告版本详情和正式发布 API；旧报告标记为 `pre_graph_update` 且不能作为 GraphUpdate 报告发布；麦当劳餐饮品牌逻辑测试覆盖非营养健康品牌报告 | 后续进入 Sprint D：Assets detail、资产反向追溯、分页和完整浏览器 E2E |

## 3. 产品 Section 完成度

| Section | 当前状态 | 完成定义 |
| --- | --- | --- |
| Boards | 基本完成 | 能启动真实运行、恢复运行态、展示阶段进度、暂停/继续/停止不会重复 dispatch，节点和连线在桌面视口稳定。 |
| Graph | 第一轮闭环完成 | 图谱能显示当前品牌实体关系库、Graph Update 差异、待审阅层；用户可以从图谱中处理补丁并看到版本变化。 |
| Reports | 完成 | 报告只从某次 Graph Update 生成，guardrail 能阻断发布，关键结论能追溯到 patch / relation / answer / question / platform；支持报告版本列表、版本详情、正式发布状态和旧报告 `pre_graph_update` 隔离。 |
| Assets | 待完成 | 用户能按 run/type 查看中间产物，安全预览 JSON/JSONL/table，能跳回对应 Graph Update 和 Report。 |

按产品主 Section 口径，`Boards / Reports` 已进入稳定和回归阶段；还剩 `Graph` 的正式版本写入/并发保护，以及 `Assets` 的明细浏览和反向追溯。

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

Sprint C 第一轮已完成。下一次开发建议有两个可选方向：

已完成开发票：

标题：`Brand Space Reports Version List And Detail`

范围：

1. 新增品牌级报告列表 API，按 GraphUpdate / report_kind / publication_status 查询。
2. Reports Section 增加 report version 列表和 detail 切换。
3. 旧报告进入 Reports 时标记 `pre_graph_update`，不能伪装成 GraphUpdate 报告。
4. Report detail 展示 guardrail 历史和 trace chain。
5. 增加 service/API/frontend 回归测试。

完成状态：

- 已实现品牌级报告列表、版本详情、正式发布接口和前端版本切换。
- 旧报告以 `pre_graph_update` 进入 Reports，只可查阅，不能作为 GraphUpdate 报告发布。
- 报告 guardrail 返回统一 DTO，生成/详情/发布接口一致。
- `publication_status=pre_graph_update` 查询会命中派生旧报告状态。

验证结果（2026-06-19）：

- 后端 targeted：`python -m pytest tests/test_brand_space_service.py tests/test_brand_space_api.py -q`，19 passed；包含麦当劳餐饮品牌报告逻辑、旧报告隔离、发布状态和 API 回归。
- 后端静态：`python -m ruff check app/services/brand_space_service.py app/api/v1/brand_space.py tests/test_brand_space_service.py tests/test_brand_space_api.py`，通过。
- 前端静态：`npx tsc --noEmit` 通过；`npm run lint` 0 errors，3 个既有 warning 不在本次变更文件。
- 前端 build：`npm run build` 通过；保留既有 PDF export / Playwright helper 的 Turbopack trace warning，不属于 Brand Space 改动。
- 仓库验证：`python scripts/validate_change.py --pytest aeo-platform/backend/tests/test_brand_space_service.py --pytest aeo-platform/backend/tests/test_brand_space_api.py`，PASS。
- 浏览器 smoke：`/brand-space` 中文 UI、8 节点/8 连接、报告区、校验区、追溯链可渲染；旧 `/dashboard` 未登录状态正常跳转 `/auth?next=/dashboard`，没有被 Brand Space 替换。

第二张具体开发票：

标题：`Brand Space Assets Detail And Trace Back`

范围：

1. 增加 artifact detail API。
2. Assets 支持 run/type 筛选。
3. 点击资产打开详情抽屉，安全预览 JSON/JSONL/table。
4. artifact → node_run / graph_update / report_version 反向跳转。
5. 大文件只显示摘要，不内联全部内容。

建议先做 Reports Version List，再进入 Assets Detail；这样用户先能完整查看报告历史，再从报告追溯到中间产物。

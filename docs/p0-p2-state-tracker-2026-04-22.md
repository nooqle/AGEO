# P0-P2 问题状态追踪

## Scope

- 覆盖范围：
  - 用户提出的 14 个线上问题
  - DeepSeek 及多平台低成功率专项
  - 明确违反 Agent-First / TPAOR 设计原则的回撤项
- 当前工作树：
  - `D:\AGEO-worktrees\supplemental-fetch-recovery`
- 当前分支：
  - `codex/supplemental-fetch-recovery`
- 当前 main 基线：
  - `origin/main` / `D:\AGEO-main` 头部已知为 `6a093ef`

## State 定义

- `分析阶段`
  - 还在确认根因，证据未闭环
- `解决方案阶段`
  - 根因已基本明确，正在收敛修法和边界
- `代码修正阶段`
  - 已进入实现或回撤，但未完成完整验证
- `部署验证阶段`
  - 已有代码和本地验证，正在 demo / 线上回放
- `已闭环`
  - 根因、修法、验证、部署闭环都完成

## 设计原则回撤清单

| ID | 问题 | 当前状态 | 完成度 | 证据 | 处理方向 |
| --- | --- | --- | ---: | --- | --- |
| R1 | `orchestrator_node.py` 中 pre-LLM 强制历史查询与 pre-LLM authoritative refresh 越过 Orchestrator 正常 ReAct | 部署验证阶段 | 97% | 已回撤 `_route_precise_history_query_without_llm` 与 pre-LLM authoritative refresh block；`test_tpaor_ownership.py` 已写回新边界；demo 已部署 | 保持由 Orchestrator 先 observe / plan；后续只保留真正需要的 validation guard |
| R2 | `orchestrator_node.py` 中 pre-LLM 显式补采 `_route_explicit_supplemental_fetch_without_llm` 用确定性分支替代 LLM 规划 | 部署验证阶段 | 97% | 已移除该短路路径；本地 `py_compile` 通过；demo 已部署 | 只允许在真正的 `user_confirmation` continuation 下消费，不允许基于文本直接短路 |
| R3 | `runtime_policy_executor` 的 `authoritative_resume` 仍有替代业务分叉判断的风险 | 部署验证阶段 | 94% | `2026-04-22 18:22` 代码级复核再次确认：全仓没有任何 `authoritative_resume` 写入点；`next_required_action` 的有效写入仅位于 `websocket_langgraph.py:2398/2410/2427`，且 authority 全部为 `user_confirmation`；`orchestrator_node.py:3185` 消费前仍会通过 `parse_next_required_action()` 做 authority gate，未识别 authority 会直接忽略；`nodes_table_import_apply.py` 等其他节点仅显式清空 `next_required_action`，没有新增业务分叉写入 | 保留该 authority 作为受控能力，但继续禁止新增业务分叉写入点 |
| R4 | `knowledge_export` 完成后直接 `send_execution_complete + goto=END`，把 Response/收口权从 Orchestrator 抢走 | 部署验证阶段 | 92% | 已移除 `knowledge_export` 直接 `END` 分支；demo 已部署，待实际导出/历史查询回放 | 收权，让 artifact 生成只产生 observation，由 Orchestrator 统一回复与收口 |

## P0 问题主链

| Group | 对应问题 | 当前状态 | 完成度 | 根因状态 | 证据 | 计划 |
| --- | --- | --- | ---: | --- | --- | --- |
| P0-A | Issue 3 / 4 / 10 / 12：打开最新报告卡顿、快速导航失效、查看问题内容跳错、左侧导航污染 | 部署验证阶段 | 99% | 主根因已明确，当前剩余 open 已收敛成 panorama report 的 canonical hydrate 性能尾巴 | 前端 artifact identity 分裂：历史 hydrate 用 `artifact_id`，实时 `output_ready` 用 `output_id`；`ChatPanel` route sync gate 过严；`ArtifactNav` compact 模式只按类型渲染；此外，`hydrateArtifacts()` 会在较慢的 outputs 快照返回时，仅保留本次 API 返回的 artifact 集合，从而把刚通过 WebSocket `addContent()` 加进来的 preview artifact 覆盖掉，这正是 `Issue 10` “查看问题内容”会被旧历史 artifact 顶回去的直接根因；本地 `tsc` / `lint` / `build` 已通过，demo 已部署；`2026-04-22` live 点击已证明 Dashboard 可直接落到正确 report artifact，左侧导航可切到不同 artifact 且 URL 会同步变化；compact 左栏按钮文本已验证为 `资料表 / 元宝数据 / 数据表格`，不再是纯重复 `数据`；`ChatPanel` 已追加按 `output_id` 去重的 detail hydration，并把 route-scope reset 前移到 `useLayoutEffect`；最新一轮又补上 hydrate merge 保留现有 WebSocket artifact，避免 preview 被旧 hydrate 覆盖；`Issue 10` 已在 fresh session `16fd5f25-d97d-4cf5-9fff-8af2cbd7aa97` 完成完整用户动作级 live 回放：上传 `anli-upload-1.xlsx` -> 点击 `先查看问题内容` -> URL 落到 `artifact_id=16fd5f25-d97d-4cf5-9fff-8af2cbd7aa97_tableImportQuestionPreview&output_id=0d75e413-f51f-4261-a42d-b550d8ee5774`，右侧 canvas 文本命中 `生成模式: 上传问题预览 / 共 6 个问题 / 上传问题 (6) / • 安利纽崔莱有什么最新的官方合作新闻？`，且未回退成历史资料表；`2026-04-22 18:13` 本机 Playwright 再次 live 验证：`route≈0.083s / canvas≈2.884s / canonical≈10.981s`，loading stub 可见，坏 fallback 不再出现，`report/fetch` 切换正常，`PDF/MD` 都成功 | 继续压 canonical hydrate tail；若后续再无用户体感级阻塞，可把剩余性能尾巴降级为 residual risk |
| P0-B | Issue 6：历史消息出现 `???` | 部署验证阶段 | 96% | 主要根因已明确，当前已拿到更深历史回放证据 | 一部分是确认消息写库污染；另一部分与 artifact 错位 / 历史回放绑定错位耦合；`ChatPanel.tsx` 已补历史读取恢复逻辑，demo 已部署；`2026-04-22` live DOM 扫描 `???` 命中数为 `0`；`2026-04-22 18:13` 本机 Playwright 继续对 `session_id=51a51ea9-4f63-4d72-8292-ec8e22197d05` 连续上翻历史消息，`body_has_question_marks = false`，更深历史样本尾部也未出现 `???` | 再保留一轮不同 session 的抽样回放；若不再复现，可转闭环 |
| P0-C | Issue 1 / 5：A7 报告打开异常、PDF 导出失败、导出命名错误 | 部署验证阶段 | 98% | A7 route、标题、时间、PDF/MD 导出与命名都已拿到 live 证据；剩余只差最终 closure 判断 | A7 report schema 与通用 report 渲染链不一致；导出链路曾存在 print/export origin 错位和 artifact schema 不一致；本地前端 build 已通过，demo `/api/exports/pdf` smoke 返回 `200 application/pdf`；`2026-04-22 18:13` 本机 Playwright 直开 A7 route 再验证：`has_geo_title=false / has_a7_title=true / has_domain=true / has_timezone=false / pdf_downloaded=true / md_downloaded=true`，建议文件名已变为 `纽崔莱官网AI友好度分析报告_20260421-035341_v1.pdf|md`；同轮 panorama report 的 PDF/MD live 导出也通过，MD 文件名为 `纽崔莱品牌全景分析_20260420-130241_v1.md` | 维持当前命名规则，补一轮用户动作级 A7 入口回放后即可考虑闭环 |
| P0-D | 设计越权回撤：避免 P0 修复继续被错误编排污染 | 部署验证阶段 | 97% | 已完成 R1 / R2 / R4 首轮回撤，本地 `py_compile`、`test_tpaor_ownership.py` 已通过，demo 已部署；`2026-04-22 18:22` 再次复核 runtime policy 写入/消费链后，确认当前 demo 基线里没有新的 `authoritative_resume` 业务分叉写入，`next_required_action` 仍限定为 `user_confirmation` continuation | 若后续 P0 live 回放不再暴露编排越权症状，可把该项与 R3 一并转闭环 |

## P1 问题主链

| Group | 对应问题 | 当前状态 | 完成度 | 根因状态 | 证据 | 计划 |
| --- | --- | --- | ---: | --- | --- | --- |
| P1-A | Issue 8 / 9：导入问题列表为空、导入后 ask user 不可决策 | 解决方案阶段 | 55% | 主因已部分明确 | 导入结果没有成为 first-class、可 version 的官方 artifact；ask user 只报识别数量，没有结构化预览和决策面 | 将导入问题作为官方 artifact，给 Orchestrator 结构化 preview + confirmation |
| P1-B | Issue 11 / 14：查询导入表格内容时 scope 错误、返回维度混乱 | 分析阶段 | 45% | 部分明确 | 当前查询回退到全历史知识表；不同 record type 混表返回 | 增加 scoped query 优先级与 typed result projection |
| P1-C | Issue 2 / 7 / 13：Dashboard 指标文案错位、skill 名泄露、`hunyuan` 外露 | 解决方案阶段 | 60% | 根因基本明确 | display layer 规范化不统一，多个组件各自拼名称 | 收敛平台名 / skill 名 / 指标名的统一 display layer |

## P2 问题主链

| Group | 对应问题 | 当前状态 | 完成度 | 根因状态 | 证据 | 计划 |
| --- | --- | --- | ---: | --- | --- | --- |
| P2-A | DeepSeek 最近 7 天几乎未实际成功执行 | 分析阶段 | 70% | 高概率不是单纯网络问题 | 本地登录态 DeepSeek 正常；远端 failure evidence 出现页面失败态；近期账号侧几乎无新任务 | 建立 runtime / session / page-state / breaker 矩阵，查清远端浏览器运行时与失败态分类 |
| P2-B | Kimi / 豆包 / 元宝近期成功率也偏低 | 分析阶段 | 40% | 还在归因 | 已观察到 `429`、timeout、empty_answer、login timeout 等多种失败形态 | 做多平台统一测试矩阵，不再单点猜测 |
| P2-C | Validation 能力不足：生成后缺独立验收与修订闭环 | 分析阶段 | 35% | 架构缺口明确 | 当前大量问题属于“生成了但没验”；planner 与 validator 都不够强 | 单独立项做 MVP：结构化交付包 + 确定性校验 + failure report + 定向修订 |

## 14 个问题映射表

| Issue | 摘要 | Priority | 当前阶段 | 完成度 |
| --- | --- | --- | --- | ---: |
| 1 | 官网 AI 友好度报告展示 / 导出 / 命名异常 | P0 | 部署验证阶段 | 98% |
| 2 | Dashboard 指标文案错位 | P1 | 解决方案阶段 | 60% |
| 3 | 打开最新报告卡很久 | P0 | 部署验证阶段 | 99% |
| 4 | Chat 快速导航无响应 | P0 | 部署验证阶段 | 97% |
| 5 | PDF 导出异常 | P0 | 部署验证阶段 | 98% |
| 6 | 历史消息 `???` | P0 | 部署验证阶段 | 96% |
| 7 | 泄露 skill 名称 | P1 | 解决方案阶段 | 60% |
| 8 | 导入 6 个问题后 artifact 为空 | P1 | 代码修正阶段 | 90% |
| 9 | 导入后 ask user 不可决策 | P1 | 解决方案阶段 | 55% |
| 10 | “查看问题内容”跳到历史表 | P0 | 部署验证阶段 | 99% |
| 11 | 查询上传表格却扫全历史 | P1 | 分析阶段 | 45% |
| 12 | 数据查询 / 导航被全局污染 | P0 | 部署验证阶段 | 90% |
| 13 | `hunyuan` 外露而不是 `元宝` | P1 | 解决方案阶段 | 60% |
| 14 | 查询返回信息维度不统一 | P1 | 分析阶段 | 45% |

## 当前执行顺序

1. 回撤明确违反设计原则的越权改动（R1-R4）
2. 修 P0-A / P0-B / P0-C 主链
3. 完成 P0 的本地验证与 demo 回放
4. 再进入 P1 的导入/查询范围和 display 统一
5. 最后单独处理 P2 DeepSeek / 多平台成功率专项

## 最新部署证据

- demo 备份目录：
  - `/srv/ageo/.codex-backups/20260422-120414-p0-rollbacks-and-artifact-fix`
  - `/srv/ageo/.codex-backups/20260422-122831-chatpanel-dedupe`
  - `/srv/ageo/.codex-backups/20260422-123232-chatpanel-compact-dedupe`
  - `/srv/ageo/.codex-backups/20260422-123452-chatpanel-layouteffect-dedupe`
  - `/srv/ageo/.codex-backups/20260422-131859-issue10-hydrate-preserve`
- demo 本次部署时间：
  - backend: `2026-04-22 12:06:09 CST`
  - frontend: `2026-04-22 12:06:09 CST`
- 本地验证：
  - `python scripts/validate_change.py` 通过
  - `pytest tests/test_tpaor_ownership.py -q` 通过
  - `npx tsc --noEmit` 通过
  - `npm run lint` 通过，仅有既有 warning
  - `npm run build` 通过
- demo 健康检查：
  - `http://127.0.0.1:8000/docs` -> `200`
  - `http://127.0.0.1:3000` -> `200`
  - `https://demo.imspecta.com` -> `200`
- `2026-04-22 16:52 +08:00` 再次确认：
  - `https://demo.imspecta.com` -> `200`
  - `https://demo.imspecta.com/dashboard` -> `200`
- PDF 路由 smoke：
  - `POST https://demo.imspecta.com/api/exports/pdf` -> `200`
  - `content-type: application/pdf`

## 最新 live 回放证据（2026-04-22）

- 使用用户已登录的 `https://demo.imspecta.com/dashboard` 会话做真实点击，而不是只跑 API smoke。
- Dashboard 点击 `打开最新报告` 后，页面直接落到：
  - `artifact_id=51a51ea9-4f63-4d72-8292-ec8e22197d05_report_panorama`
  - `output_id=b16275b1-377c-49e1-9f58-9fc63d1f8c9c`
- Chat / Canvas 左侧导航已验证可切换真实 artifact：
  - `元宝数据表`
  - `只查询 2026-04-20 13:02 的数据表`
  - `品牌全景分析报告`
- 当前报告页右上角 `导出` 菜单已真实点开，并完成两条真实下载：
  - `纽崔莱_品牌全景分析_20260420-130241_v1.pdf`
  - `纽崔莱_品牌全景分析_20260420-130241_v1.md`
- 当前报告页可见 DOM 扫描 `???` 命中数为 `0`。
- compact 左侧栏的三个数据类入口已验证为：
  - `资料表`
  - `元宝数据`
  - `数据表格`
- 当前保留的 open 点变成：
  - `2026-04-22 12:28` 单文件重新部署 `ChatPanel.tsx` 后，Dashboard 点击 `打开最新报告` 到页面出现 `h1=纽崔莱｜品牌全景分析报告`，最新一次 live 实测约 `2.0s`。
  - 针对 `output_id=b16275b1-377c-49e1-9f58-9fc63d1f8c9c`，本次 `performance` 记录里只剩 `1` 条 detail fetch；此前同一 output detail 被重复 hydration 的问题已被压掉。
- `2026-04-22 12:34` 再次单文件部署 `ChatPanel.tsx` 后，`compact=true` 也已经从 `2` 条收敛到 `1` 条；同轮 live 回放 `Dashboard -> 打开最新报告` 实测约 `1.53s`。
- `2026-04-22` 继续回溯 `Issue 10` 时，已拿到一条直接根因：`ChatPanel.tsx` 中 `hydrateArtifacts()` 在 outputs 快照返回时只保留 `hydratedContents`，会把稍早通过 WebSocket `addContent()` 加进来的 preview artifact 覆盖掉；这能直接解释“点了先查看问题内容，右侧又被旧历史表顶回去”。本地 `npx tsc --noEmit` 与 `npm run lint` 已通过，等待 demo live 回放。
- `2026-04-22 13:19` 已将这条 `hydrateArtifacts()` 修补单文件部署到 demo，frontend build / restart / 健康检查通过；随后在 demo 服务器本机用 Patchright 直开：`/chat/59fbaddc-b8e8-4b69-b7a1-b5ffbadd3a79?artifact_id=59fbaddc-b8e8-4b69-b7a1-b5ffbadd3a79_tableImportQuestionPreview&output_id=0013f621-21b7-46ea-8859-878636e70c64`，右侧 canvas 文本已命中：
  - `生成模式: 上传问题预览`
  - `共 6 个问题`
  - `上传问题 (6)`
  - `安利纽崔莱有什么最新的官方合作新闻？`
  说明 preview artifact 当前能在 live 环境稳定落到上传问题预览，而不是历史资料表。
- `2026-04-22` 同一 session 的 A7 route 也已做服务器本机 Patchright 回放：`/chat/59fbaddc-b8e8-4b69-b7a1-b5ffbadd3a79?artifact_id=59fbaddc-b8e8-4b69-b7a1-b5ffbadd3a79_report_site_confidence_amway_com_cn&output_id=d7dc702c-e74e-4233-8d6e-b76d88ccb5fa`；右侧 canvas 文本命中：
  - `官网评估报告`
  - `官网 AI 友好度分析报告`
  - `amway.com.cn`
  - `最近更新 2026-04-21 11:53`
  且未出现：
  - `GEO 全景分析报告`
  - `canonical GEO 报告`
  - `fallback 渲染`
  说明 A7 当前 route 打开已不再掉回旧 GEO fallback 壳子。
- 当前 remaining open 点从“detail / compact 重复 hydration”收敛成“仍会并行出现一次 `workflow` output detail（`b169dee1-3a0b-4152-9837-97cc93a59edd`）”，以及单条 panorama detail 载荷仍约 `981KB / 8.6s`。
  - 当前最大单点开销已定位到：
    - `GET /api/v1/sessions/51a51ea9-4f63-4d72-8292-ec8e22197d05/outputs/b16275b1-377c-49e1-9f58-9fc63d1f8c9c`
    - `duration ≈ 8.61s`
    - `transferSize ≈ 981604 bytes`
- `2026-04-22 14:18` 使用 fresh session `16fd5f25-d97d-4cf5-9fff-8af2cbd7aa97`，在 demo 服务器本机用 Patchright 完成完整用户动作级回放：
  - 上传文件：`anli-upload-1.xlsx`
  - 聊天内点击：`先查看问题内容`
  - 最终 URL：`/chat/16fd5f25-d97d-4cf5-9fff-8af2cbd7aa97?artifact_id=16fd5f25-d97d-4cf5-9fff-8af2cbd7aa97_tableImportQuestionPreview&output_id=0d75e413-f51f-4261-a42d-b550d8ee5774`
  - 右侧 canvas 文本命中：
    - `生成模式: 上传问题预览`
    - `共 6 个问题`
    - `上传问题 (6)`
    - `• 安利纽崔莱有什么最新的官方合作新闻？`
  - 且 `canvas_has_history_table = false`
  - 说明 `Issue 10` 现在已经不再跳回历史资料表
- `2026-04-22 14:27` 对 `Dashboard -> 打开最新报告` 做新一轮 probe 时，又拿到一条新的直接反证：
  - UI 初始 canvas 文本出现：
    - `当前报告内容不完整，暂时无法正常展示。`
    - `请重新生成一次分析报告后再查看。`
  - 对应 session / output：
    - `session_id = 51a51ea9-4f63-4d72-8292-ec8e22197d05`
    - `output_id = b16275b1-377c-49e1-9f58-9fc63d1f8c9c`
  - 但同一 output 的 detail API 已确认返回 canonical report 数据：
    - `artifact_id = 51a51ea9-4f63-4d72-8292-ec8e22197d05_report_panorama`
    - `has_full_markdown = true`
    - `sections_len = 9`
  - 说明当前 open 点已经从“后端没生成报告”收敛成“前端 report hydrate / preview merge 错位”，不是后端产物缺失
- `2026-04-22 16:45` 继续沿同一条前端主链排查时，又拿到一条直接代码级事实：
  - `frontend/src/components/chat/ChatPanel.tsx` 中 route-target compact guard 的补丁是半截状态，`hasCanonicalRouteTarget` 被引用但未定义；
  - 本地 `npx tsc --noEmit` 已直接报错：`TS2304: Cannot find name 'hasCanonicalRouteTarget'`
  - 这说明上一轮 intended fix 实际没有形成可编译、可部署的完整前端版本
- `2026-04-22 16:49 ~ 16:51` 已补全这条 guard：
  - 在 `hydrateArtifacts()` 内基于当前 `state.contents` 显式计算 `hasCanonicalRouteTarget`
  - 本地 `npx tsc --noEmit --pretty false` 通过
  - 本地 `npm run lint -- --quiet` 通过
  - demo 机前端已重新 `build + restart` 成功
- `2026-04-22 17:00` 已修复本机 Playwright CLI 不可用问题：
  - 直接根因不是 CLI 命令缺失，而是本机缺少 Playwright browser runtime，报错为：
    - `Executable doesn't exist ... chrome-headless-shell.exe`
  - 已在本机 `frontend` 目录执行：
    - `npx playwright install chromium`
  - 安装完成后已完成最小回归：
    - `npx playwright screenshot https://example.com ..\\output\\playwright\\example-com.png --timeout 45000`
  - 输出文件已生成：
    - `D:\AGEO-worktrees\supplemental-fetch-recovery\output\playwright\example-com.png`
  - 结论：本机 Playwright CLI 现在可用；当前仍不可用的是桌面 MCP Playwright browser backend，而不是本机 Playwright runtime
- `2026-04-22 17:10 ~ 17:13` 已进一步打通**本机可脚本化 Playwright 验证链**：
  - 已安装 Python `playwright` 包，并直接复用本机刚安装的 Chromium：
    - `python -m pip install playwright`
    - executable path: `C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1217\chrome-win64\chrome.exe`
  - 使用真实 token 初始化 cookie + localStorage 后，本机 Playwright 已能：
    - 打开 `https://demo.imspecta.com/dashboard`
    - 真实点击 `打开最新报告`
    - 截图并抓取页面文本 / console / network
  - 相关本地产物：
    - `output/playwright/p0-dashboard-python.png`
    - `output/playwright/p0-open-report-python.png`
    - `output/playwright/p0-open-report-python.json`
    - `output/playwright/p0-direct-report-python.png`
    - `output/playwright/p0-direct-report-python.json`
- `2026-04-22 17:13` 用本机 Python Playwright 做真实 live 回放后，P0 当前 open 点进一步收敛：
  - `Dashboard -> 打开最新报告` 已真实跳到目标 URL：
    - `/chat/51a51ea9-4f63-4d72-8292-ec8e22197d05?artifact_id=51a51ea9-4f63-4d72-8292-ec8e22197d05_report_panorama&output_id=b16275b1-377c-49e1-9f58-9fc63d1f8c9c`
  - 但当前页面状态不是“后端没报告”，也不完全是“fallback 文案”，而是：
    - `hasCanvasRoot = 0`
    - `canvasDebug = null`
    - 右侧 canvas 在本机回放里根本没有挂出来
  - 同时，另一条本机 Playwright network+console 探针又证明：
    - 浏览器里确实发出了 detail 请求：`/outputs/b16275b1-377c-49e1-9f58-9fc63d1f8c9c` -> `200`
    - `ReportContent` 控制台仍打出：
      - `missing canonical markdown ... isHydrationStub: true ... sourceOutputId: b16275b1-377c-49e1-9f58-9fc63d1f8c9c`
  - 最关键的对照证据：
    - 在同一浏览器上下文里，用 `wait_for_response` 直接读取这条 detail 响应体，得到的是 canonical 数据：
      - `type = report`
      - `artifact_id = 51a51ea9-..._report_panorama`
      - `has_full_markdown = true`
      - `has_report_markdown = true`
      - `sections_len = 9`
  - 结论：
    - 后端 report detail 已确认正确
    - 当前 blocker 已进一步收敛成前端 route 初始化 / store 写回 / canvas 打开时机链，而不是后端产物或 PDF 导出链
- `2026-04-22 17:23` 已修复 `ChatPanel.tsx` 中一段把 TS 解析器打坏的临时 debug patch，并再次确认：
  - 本地 `npx tsc --noEmit --pretty false` 通过
  - 本地 `npm run lint -- --quiet` 通过
  - demo frontend 已重新 `build + restart` 成功
- `2026-04-22 17:30 ~ 17:40` 又完成了一轮新的本机 Python Playwright 真正用户动作级回放，并拿到当前最可信的 P0-A 指标：
  - `Dashboard -> 打开最新报告`：
    - `route 切换 ≈ 2.385s`
    - `右侧 canvas 首次可见 ≈ 5.696s`
    - `panorama canonical report 完全到位 ≈ 14.357s`
  - 这轮 probe 同时确认：
    - output detail 真实 payload 约 `981304 bytes`
    - 当前慢点不是“打不开”，而是 canonical report hydrate 的 tail 仍偏长
- `2026-04-22 17:40` 为了把用户侧体验从“无响应 / 错误 fallback”收回来，已补上两条纯前端 hydration UX 收口，并完成 demo 部署：
  - `ChatPanel.tsx`：route 命中 report artifact 时，先注册一个 placeholder report artifact，保证 split canvas 能立刻打开
  - `ReportContent.tsx`：对 `isHydrationStub` 且缺少 canonical markdown 的场景，显示 `报告加载中，请稍候...`，不再显示 `当前报告内容不完整，暂时无法正常展示。`
  - 本地新证据文件：
    - `output/playwright/p0-open-report-8s-post-placeholder.png`
    - `output/playwright/p0-open-report-25s-post-placeholder.png`
    - `output/playwright/p0-open-report-8s-post-placeholder.json`
    - `output/playwright/p0-open-report-25s-post-placeholder.json`
  - 当前实际用户侧效果：
    - `8s` 时右侧 canvas 已打开，并显示 loading 态
- `2026-04-22 18:24` 使用本机 Playwright 再跑一轮 bundled regression：
  - `output/playwright/p0-live-probe.json`
  - `output/playwright/p0-history-probe.json`
  - 结果：
    - `dashboard_ready_seconds = 6.769`
    - `route_seconds = 0.079`
    - `canvas_seconds = 2.879`
    - `canonical_seconds = 12.003`
    - `has_bad_fallback = false`
    - `has_question_marks = false`
    - `pdf_downloaded = true`
    - `md_downloaded = true`
  - `P0-B` 的深历史回放仍未发现 `???`
- `2026-04-22 18:27` 对 A7 route 做轻量复验（`domcontentloaded + canvas selector + settle`）：
  - 路由：
    - `/chat/59fbaddc-b8e8-4b69-b7a1-b5ffbadd3a79?artifact_id=59fbaddc-b8e8-4b69-b7a1-b5ffbadd3a79_report_site_confidence_amway_com_cn&output_id=d7dc702c-e74e-4233-8d6e-b76d88ccb5fa`
  - canvas 文本命中：
    - `官网 AI 友好度`
    - `官网评估报告`
    - `官网 AI 友好度分析报告`
    - `amway.com.cn`
    - `最近更新 2026-04-21 11:53`
  - 且未命中：
    - `GEO 全景分析报告`
    - `???`
  - 说明先前那次 `networkidle` 超时属于 probe 条件问题，不是 A7 页面功能回退
- `2026-04-22 18:43` 已将当前修复基线提交为：
  - `9f734dc fix(workflow): close p0 artifact and report routing`
  - 并已 `fast-forward merge` 到 `D:\AGEO-main` 的 `main`，随后推送 `origin/main`
- `2026-04-22 18:43 ~ 18:46` 已部署到 demo：
  - 远端目录：`/srv/ageo`
  - 备份目录：`/srv/ageo/.codex-backups/20260422-184307-main-sync`
  - 处理了一次前端构建权限漂移：先清理 `/srv/ageo/frontend/.next`，再执行 `npm run build`
  - 两个服务均已重启并恢复 `active`
  - 健康检查：
    - `http://127.0.0.1:3000 -> 200`
    - `https://demo.imspecta.com -> 200`
- `2026-04-22 18:46` 部署后再次执行本机 Playwright smoke：
  - `output/playwright/p0-live-probe.json`
  - `output/playwright/p0-history-probe.json`
  - 结果：
    - `dashboard_ready_seconds = 6.786`
    - `route_seconds = 0.073`
    - `canvas_seconds = 2.873`
    - `canonical_seconds = 12.053`
    - `has_question_marks = false`
    - `has_bad_fallback = false`
    - `pdf_downloaded = true`
    - `md_downloaded = true`
  - 但同时暴露一个残余 open：
    - 本轮 probe 最终 `chat_url` 落在 `artifact_id=..._fetchResults`
    - `report_tab_has_summary = false`
    - `md_suggested_filename = brand用户场景细分分析_20260422-184505_v1.md`
  - 说明这版主线和 demo 已完成提交/合并/推送/部署，但 `P0` 仍未正式闭环，当前残余问题已收敛成部署后的一条 artifact focus / export context 错位，不再是服务不可用或大面积回退
    - `25s` 时 canonical panorama report 已完整可见
- 当前仍保留的 open：
  - 桌面 MCP Playwright browser backend 仍不可用：`browserBackend.callTool: Target page, context or browser has been closed`
  - 但这已不再阻塞 P0 live 验证，因为本机 Python Playwright 链已替代它
  - `P0-A` 当前还未闭环，因为：
    - 真实点击已进目标 route
    - 右侧 canvas 已能稳定打开且不再显示错误 fallback
    - 但 panorama canonical report 的最终到位时间仍约 `14.36s`，仍有性能收口空间
- `2026-04-22 18:13` 用本机 Playwright 完成新一轮 `P0` live 回放，并把之前残留的几个 open 进一步压缩：
  - `Dashboard -> 打开最新报告`
    - `dashboard_ready_seconds ≈ 7.142s`
    - `route_seconds ≈ 0.083s`
    - `canvas_seconds ≈ 2.884s`
    - `canonical_seconds ≈ 10.981s`
    - `loading_stub_visible = true`
    - `has_bad_fallback = false`
  - 同轮切换 tab 后：
    - `report_tab_has_summary = true`
    - `report_tab_has_fetch_results = false`
    - 说明 report / fetch 切换不再串内容
  - panorama report 导出：
    - `pdf_downloaded = true`
    - `md_downloaded = true`
    - `md_suggested_filename = 纽崔莱品牌全景分析_20260420-130241_v1.md`
  - 深历史 `???` 回放：
    - 新证据文件：`output/playwright/p0-history-probe.json`
    - `body_has_question_marks = false`
    - 已在同一 session 内连续上翻历史消息，不再只看当前可见区
  - A7 route / 导出 / 命名：
    - 新证据文件：`output/playwright/a7-live-probe.json`
    - `has_geo_title = false`
    - `has_a7_title = true`
    - `has_domain = true`
    - `has_timezone = false`
    - `pdf_downloaded = true`
    - `md_downloaded = true`
    - `pdf_suggested_filename = 纽崔莱官网AI友好度分析报告_20260421-035341_v1.pdf`
    - `md_suggested_filename = 纽崔莱官网AI友好度分析报告_20260421-035341_v1.md`
  - 这轮说明：
    - `Issue 1 / 3 / 5 / 6 / 10` 都已经拿到新的本机用户动作级 live 证据
    - `P0` 当前剩下的主要 open 不再是功能错位，而是 `P0-A` 的 canonical hydrate 还有性能尾巴，以及 `P0-D` 设计边界还要做最后一轮 closure 复审

## 本轮完成标准

- 本文档持续更新，不再只依赖对话记忆
- 每个问题组都必须显式标记：
  - 当前阶段
  - 完成度
  - 证据
  - 下一步
- 没有经过 demo 回放验证的问题，不得标记为 `已闭环`

## 2026-04-22 19:04 导出弹窗 / PDF 样式子任务

- 范围：
  - 去掉导出弹窗里的文件名规则展示
  - 去掉导出成功 toast 里的完整文件名回显
  - 把 PDF 打印页从深色 canvas 主题收回到浅色文档主题
- 当前阶段：`部署验证阶段`
- 当前完成度：`88%`
- 已完成：
  - [frontend/src/components/canvas/CanvasHeader.tsx](../frontend/src/components/canvas/CanvasHeader.tsx)
    - 删除导出下拉中的“文件名：品牌名 + ...”提示
    - 导出成功提示改为通用格式：`PDF 已导出 / MD 已导出 / CSV 已导出`
  - [frontend/src/app/exports/print/[id]/page.tsx](../frontend/src/app/exports/print/[id]/page.tsx)
    - 打印页强制覆盖为浅色文档变量，不再继承深色主题
- 本地验证：
  - `npx tsc --noEmit` -> 通过
  - `npm run lint -- --quiet` -> 通过
  - `npm run build` -> 通过
- demo 部署：
  - 备份目录：`/srv/ageo/.codex-backups/20260422-194200-nav-export-fix`
  - 已替换：
    - `frontend/src/components/canvas/CanvasHeader.tsx`
    - `frontend/src/app/exports/print/[id]/page.tsx`
  - `frontend` 已重新 `build`
  - `ageo-frontend.service` / `ageo-backend.service` 已重启，均为 `active`
  - 健康检查：
    - `http://127.0.0.1:3000 -> 200`
    - `https://demo.imspecta.com -> 200`
- 当前 open：
  - 还未做本机用户动作级 PDF 预览验证
  - 还未做导出弹窗实际点击验证
- 下一步：
  - 用本机 Playwright 验证导出弹窗不再显示文件名，且 PDF 预览为浅色文档样式

## 2026-04-22 19:20 导航切换重载 / 高亮样式子任务

- 范围：
  - 导航点击切换时不应触发整页/对话重新加载
  - compact 导航不应整批错误点亮
  - 高亮边框应完整、稳定
- 当前阶段：`部署验证阶段`
- 当前完成度：`85%`
- 直接根因：
  - [frontend/src/components/chat/ChatPanel.tsx](../frontend/src/components/chat/ChatPanel.tsx)
    - artifact 切换后直接 `router.replace` 更新 `artifact_id/output_id`，导致 App Router 重新跑页面级 searchParams 链路，体感像整页重载
  - [frontend/src/components/layout/ArtifactNav.tsx](../frontend/src/components/layout/ArtifactNav.tsx)
    - `prevCountRef` 在新增 artifact 时没有及时更新，导致 `glow-border` 会把整批按钮反复当成“新项”
    - compact 导航在窄宽度里使用 glow 边框，视觉上容易出现不完整边缘
- 已完成修正：
  - artifact URL 同步改为 `window.history.replaceState(...)`，保留 URL 更新但不再触发 router 级导航
  - `ArtifactNav` 修正 `prevCountRef` 更新时机
  - compact 导航去掉破碎 glow 边缘，只保留清晰 active border
  - artifact 导航按钮补 `type=\"button\"`
- 本地验证：
  - `npx tsc --noEmit` -> 通过
  - `npm run lint -- --quiet` -> 通过
  - `npm run build` -> 通过
- demo 部署：
  - 已替换：
    - `frontend/src/components/layout/ArtifactNav.tsx`
    - `frontend/src/components/chat/ChatPanel.tsx`
  - 与上面同批次重建并重启
- 当前 open：
  - 还未做 demo live 点击验证
  - 还未最终确认“只亮当前项”与“切换不触发页面级重载”
- 下一步：
  - 本机 Playwright 验证：点击多个导航时不再出现页面级重载，且只有当前项点亮

## 2026-04-22 20:05 P1 Root-Cause Freeze（Issue 8 / 9 / 11 / 12 / 13 / 14，连带复核 2 / 7）

- 范围：
  - `Issue 8` 导入 6 个问题后，Artifacts 中问题为空/错内容
  - `Issue 9` 导入成功后 ask_user 不可决策，只说“识别到 6 个问题”
  - `Issue 11` 查询上传表格内容却扫全历史
  - `Issue 12` 查询结果/version/title 污染导航
  - `Issue 13` 结果里出现 `hunyuan` 而不是 `元宝`
  - `Issue 14` 查询回来的信息维度混乱
  - 连带复核：`Issue 2` Dashboard 指标文案错位，`Issue 7` skill 名泄露
- 当前阶段：`解决方案阶段`
- 当前完成度：`68%`
- 约束：
  - 这一阶段不改 repo-tracked 代码，只冻结根因
  - 每个问题必须落到具体模块，不允许停留在“可能是 orchestrator / skill”

### 问题矩阵

| 问题 | 直接根因 | 所属链路 | 影响范围 | 所属层 |
| --- | --- | --- | --- | --- |
| `Issue 8` 导入问题为空/错内容 | [aeo-platform/backend/app/services/table_intake_service.py](../aeo-platform/backend/app/services/table_intake_service.py) 的 `_deterministic_classify`（`186`）和 `_header_match_score`（`504`）仍可能把“编号/问题编号”列误判为问题列；`_merge_results`（`320`）在 LLM 覆盖 `detected_columns` 后又不会重建 `normalized_payload.questions`，导致列选择与最终问题 payload 漂移 | 表格导入解析 -> 预览 artifact/A3 | 导入问题列表、后续 ask_user、A3 问题来源 | `Skill / Artifact` |
| `Issue 9` ask_user 不可决策 | [aeo-platform/backend/app/workflow/orchestrator_node.py](../aeo-platform/backend/app/workflow/orchestrator_node.py) 的 `table_intake_skill` tool summary（`2162`）仍是“建议 ask_user”的自然语言；`_force_table_import_confirmation`（`2808`）只在无 tool call 的修复分支兜底，而不是正式的 post-table-intake 契约 | Orchestrator -> table_intake -> ask_user | 导入后无法稳定出现“查看问题内容 / 确认导入 / 暂不继续” | `Agent / Skill Contract` |
| `Issue 11` 查刚上传表格却扫全历史 | [aeo-platform/backend/app/workflow/orchestrator_context_packets.py](../aeo-platform/backend/app/workflow/orchestrator_context_packets.py) 只把上传表格摘要成 `uploaded_input` 证据（`555`、`691`），不是 first-class artifact scope；[aeo-platform/backend/app/workflow/orchestrator_node.py](../aeo-platform/backend/app/workflow/orchestrator_node.py) 的 `current_uploaded_table_query`（`1338`）只是单点 guard；一旦落入 [aeo-platform/backend/app/services/knowledge_workspace_service.py](../aeo-platform/backend/app/services/knowledge_workspace_service.py) 的 `export_table`，查询只按历史 `KnowledgeRecord` 范围导出 | 上传输入 -> 查询路由 -> knowledge_export | “查刚上传内容”变成“查品牌历史全量” | `Context / Artifact / Validation` |
| `Issue 12` 查询结果/version/title 污染导航 | [aeo-platform/backend/app/services/knowledge_workspace_service.py](../aeo-platform/backend/app/services/knowledge_workspace_service.py) 的 `_export_scope_label`（`345`）默认落到“过往资料表”；`_export_columns`（`1718`）/ `_serialize_export_row`（`1956`）把历史知识导出为通用 `dataTable`；由于上传内容不是 first-class scoped artifact，结果会生成一串泛化历史表 artifact | knowledge_export -> artifact/title/version | 左侧导航被“过往资料表 / 数据”污染 | `Artifact / Version` |
| `Issue 13` `hunyuan` 外露 | 后端有存储/公开平台名双轨：[knowledge_workspace_service.py](../aeo-platform/backend/app/services/knowledge_workspace_service.py) `_public_platform_id`（`270`）会把 `hunyuan -> yuanbao`，但查询导出仍通过通用 `_serialize_export_row`（`1956`）直序列化历史记录，说明公共显示层没有被所有结果路径一致消费；前端也仍是多处局部归一化而非单一公共契约 | 历史查询导出 -> 数据表/导航显示 | 平台名公开层不一致 | `Display Layer / Artifact Output` |
| `Issue 14` 结果维度混乱 | [knowledge_workspace_service.py](../aeo-platform/backend/app/services/knowledge_workspace_service.py) 的 `_export_columns`（`1718`）始终固定成单一扁平列 schema，`_serialize_export_row`（`1956`）把异构历史记录压成 `snippet`/`title`/`question_text` 等通用字段；[frontend/src/components/canvas/contents/DataTableContent.tsx](../frontend/src/components/canvas/contents/DataTableContent.tsx) 只是表格直渲染，不做 typed rows 校验，所以“回答内容 / 情感 / 摘要 / 标签”会被混成同一张表 | knowledge_export -> dataTable 渲染 | 查询结果维度不一致，难以解释/复用 | `Validation / Artifact Schema` |
| `Issue 2` 复核：Dashboard 指标文案错位 | [frontend/src/hooks/websocket/canvas.ts](../frontend/src/hooks/websocket/canvas.ts) 里 `normalizePreviewMetricLabel`（`19`）仍把 `官网 AI 友好度` 归一成 `官网转化率`，`PREVIEW_METRIC_PRIORITY`（`6`）也仍以 `官网转化率` 为预览指标 | 预览指标规范化 | Dashboard / 卡片预览 | `Display Layer` |
| `Issue 7` 复核：skill 名泄露 | [frontend/src/lib/workflowStageLabels.ts](../frontend/src/lib/workflowStageLabels.ts) 已有公共映射（`22`、`31`），但 [frontend/src/components/chat/process-timeline.tsx](../frontend/src/components/chat/process-timeline.tsx) 仍保留独立 `formatToolName`（`72`），说明公开名称层没有完全收拢到单一 display contract | timeline / tool label 渲染 | 用户可见流程名可能继续泄露内部 skill id | `Display Layer` |

### 根因冻结结论

- `P1-A` 导入问题正式化：
  - 当前根因已足够冻结，核心不是“前端空白”，而是“导入问题的解析结果与 artifact/version 契约不稳定”
  - 下一阶段应把上传问题列表提升为 first-class artifact，并让 ask_user 与后续流程都绑定这一 artifact
- `P1-B` 查询范围收口：
  - 当前根因已足够冻结，核心不是“某句 prompt 没写好”，而是“上传内容没有 authoritative scope，knowledge_export 只能回落到历史 KnowledgeRecord”
  - 下一阶段应先补 artifact scope，再做 scoped query 路由和 deterministic scope validator
- `P1-C` 结果类型与显示规范化：
  - 当前根因已足够冻结，核心不是某一张表的文案错误，而是“公共 display / typed result schema 还没有收敛成单一契约”
  - 下一阶段应统一 public display layer 与 typed export schema

### 当前不进入改码的原因

- `Issue 13 / 14` 已拿到直接根因，`Issue 2 / 7` 也已复核到具体模块
- 但本轮还没有把统一改码方案压成最小 shared-layer 变更面
- 按本轮协议，必须先完成根因冻结与问题矩阵写回，再进入统一改码

### 下一步

- 进入 `P1` 统一改码方案设计：
  - `1.` 导入问题升级为 first-class artifact/version
  - `2.` 重做 table_intake 后的 ask_user 契约
  - `3.` 为“刚上传/导入内容”建立 authoritative scoped query
  - `4.` 收拢公共 display layer 与 typed export schema
  - `5.` 增加最小 deterministic validation：scope / coverage / result typing / artifact binding

## 2026-04-22 20:18 P1 Unified Change Batch / Priority

- 当前阶段：`代码修正阶段（待开始）`
- 当前完成度：`0%`
- 设计目标：
  - 不再用单场景 `if/else` 修补导入与查询
  - 先补 authoritative artifact/version，再补 query scope，再补 display/validation
  - 保持 Orchestrator 负责理解与路由，代码负责 deterministic mechanics

### 改码批次与优先级

#### `P1-A` 导入问题升级为 first-class artifact/version（最高优先级）

- 目标：
  - 上传问题列表不再只是 preview 或 A3 衍生物，而是正式的导入 artifact/version
  - 后续“查看问题内容 / 确认导入 / 询问刚上传内容”都绑定这份 artifact
- 最小改动面：
  - `table_intake_service.py`
    - 修正问题列识别与 payload 重建，确保 `normalized_payload.questions` 与最终 `detected_columns` 一致
  - `confirmation.py`
    - table import preview / confirmation payload 携带稳定 artifact ref
  - `websocket_langgraph.py`
    - `view_questions` / `table_import_question_list*` 路径写入 authoritative import artifact ref
  - `orchestrator_context_packets.py`
    - 把上传问题列表从“摘要 evidence”升级为带 artifact/version 的 authoritative current input

#### `P1-B` 重做 table_intake 后的 ask_user 契约（高优先级）

- 目标：
  - 导入成功后，Orchestrator 必须给出可决策 ask_user，而不是“识别到 6 个问题”就结束
  - ask_user 选项至少稳定包含：
    - 查看问题内容
    - 确认按这些问题继续
    - 暂不继续
- 最小改动面：
  - `orchestrator_node.py`
    - 将 table intake 完成后的确认作为正式 continuation contract，而不是纯自然语言建议
  - `confirmation.py`
    - 统一解析 option -> artifact/action 绑定
  - `nodes_table_intake.py`
    - 把 import intent / artifact ref / downstream action 准备成结构化 state

#### `P1-C` 建立 authoritative scoped query（高优先级）

- 目标：
  - “刚上传/导入的表格内容”优先 scoped 到最新导入 artifact
  - 没有 current import artifact 或用户明确查历史时，才回退知识库
- 最小改动面：
  - `orchestrator_node.py`
    - 明确 current import scope precedence
  - `orchestrator_context_packets.py`
    - current import artifact 进入 current context，不再只是 `uploaded_input` 摘要
  - `nodes_knowledge.py` / `knowledge_workspace_service.py`
    - 增加 import-artifact scoped export/query path，避免直接落入全历史 `KnowledgeRecord`

#### `P1-D` 收拢 typed export schema + public display layer（中优先级）

- 目标：
  - 历史/导入查询结果不再混杂回答内容、情感、摘要、标签
  - `hunyuan -> 元宝`、skill 名、内部术语统一走单一公开显示层
  - Dashboard 预览指标不再把 `官网 AI 友好度` 归成 `官网转化率`
- 最小改动面：
  - `knowledge_workspace_service.py`
    - 输出 typed rows 和 typed columns，而不是单一扁平 `dataTable`
  - `frontend/src/components/canvas/contents/DataTableContent.tsx`
    - 只消费规范化 schema，不再对异构行做隐式容错
  - `frontend/src/hooks/websocket/canvas.ts`
    - 修正 preview metric 公共映射
  - `frontend/src/lib/workflowStageLabels.ts`
    - 成为唯一 stage/tool 公共映射来源
  - `frontend/src/components/chat/process-timeline.tsx`
    - 去掉本地私有 `formatToolName` 映射，统一走公共显示层

#### `P1-E` 最小 deterministic validation（中优先级）

- 目标：
  - 在交付导入/查询结果前，先做 deterministic 校验，不再只靠模型“理解”
- 最小改动面：
  - `table_intake_service.py`
    - artifact binding / payload consistency check
  - `orchestrator_node.py`
    - requirement coverage / scope binding gate
  - `knowledge_workspace_service.py`
    - result typing / source_scope 标注

### 执行顺序

- `1.` `P1-A`
- `2.` `P1-B`
- `3.` `P1-C`
- `4.` `P1-D`
- `5.` `P1-E`

### 本轮改码边界

- 不进入 `P2`，不顺手修 DeepSeek / 多平台成功率
- 不回头扩 `P0`，除非用户在 demo 最终验证时明确指出残余功能错误
- 不新增临时 side channel；所有后续动作都必须绑定 artifact/version 或 structured context

## 2026-04-22 20:46 P1 Unified Code Batch / Progress Writeback

- 当前阶段：`代码修正阶段（进行中）`
- 当前完成度：`72%`
- 本轮原则：
  - 先把 authoritative artifact / scope / typed schema / deterministic validation 四条主链补齐
  - 不中途部署，不把一次 smoke 冒充 closure

### 已完成

- `P1-A` first-class import artifact/version：
  - `table_intake_node` 现在会在 question_list 导入时直接写正式 `questionList` artifact
  - `confirmation.py` 统一生成稳定的 `current_import_artifact` 引用
  - `state.py` 已新增 `current_import_artifact`
  - `websocket_langgraph.py` 的 `view_questions` / `still_empty` 路径已改成复用 authoritative import artifact，而不是临时 preview key
  - `nodes_table_intake.py` 已新增 deterministic question-list gate：
    - 没识别出稳定问题列，或 `normalized_payload.questions` 为空时，不再允许生成空问题列表交付物
- `P1-B` ask_user 契约重做：
  - `build_table_import_confirmation_payload()` 现在稳定提供“先查看问题内容 / 确认导入问题列表 / 暂不导入”
  - `resolve_confirmation_selection()` 会把 option 解析成结构化 import action，而不是只回自然语言
- `P1-C` scoped query：
  - `orchestrator_node.py` 已新增 current-import deterministic route
  - 当用户询问“刚上传/导入的表格/问题内容”时，会优先走 `knowledge_export(source_scope=current_import_artifact)`
  - `nodes_knowledge.py` 已新增 current import export path，并优先复用 authoritative import artifact，而不是回退到全历史 `KnowledgeRecord`
- `P1-D` typed result schema + display layer：
  - `knowledge_workspace_service.py` 导出列已拆成 `source_scope / answer_content / sentiment / summary / tags`
  - `source_scope` 与 `source_type` 已解耦，历史导出统一标为 `历史资料库`
  - `frontend/src/hooks/websocket/canvas.ts` 已把 `官网 AI 友好度` 与 `官网转化率` 拆开
  - `frontend/src/components/chat/process-timeline.tsx` 已改成走公共 `workflowStageLabels`
- `P1-E` 最小 deterministic validation：
  - `nodes_knowledge.py` 已新增 `_validate_export_result()`
  - 当前会在交付前校验：
    - scope 是否正确
    - 列 schema 是否完整
    - row scope 是否正确
    - current import 结果是否绑定到正式 artifact/version
    - 历史导出是否仍残留 legacy `snippet` 维度
  - `orchestrator_node.py` 已补 current import export failure reply，不再错误回退成“过往资料表失败”

### 本轮本地验证

- backend:
  - `py_compile` 已通过：
    - `websocket_langgraph.py`
    - `knowledge_workspace_service.py`
    - `message_service.py`
    - `table_intake_service.py`
    - `confirmation.py`
    - `nodes_knowledge.py`
    - `nodes_table_intake.py`
    - `orchestrator_context_packets.py`
    - `orchestrator_node.py`
    - `state.py`
  - 现有 `pytest aeo-platform/backend/tests/test_nodes_knowledge.py -q` 已通过
  - 脚本级断言已通过：
    - current import export validation pass
    - 历史导出 row scope mismatch 会被 deterministic validator 拦住
    - current import completion reply 会明确声明“只来自本次上传表格”
    - table intake deterministic gate 会拦住空问题列表交付物
- frontend:
  - `npx tsc --noEmit` 已通过
  - `npm run lint -- --quiet` 已通过

### 仍然 open

- `P1-A/B` 还没做最终用户动作级闭环，因为本轮按协议还没部署
- `P1-D` 的 `DataTableContent.tsx` 尚未复核是否需要显式消费新的 typed schema；目前先依赖兼容渲染
- `Issue 2 / 7` 虽然已经落到公共显示层，但这轮还没做最终 demo 验证
- `P1` 统一改码批次还没正式进入 `部署验证阶段`

### 下一步

- 继续完成 `P1` 剩余收尾：
  - 复核 `DataTableContent` 是否需要最小适配
  - 扫一遍 current import / historical export close-out 文案
  - 确认没有遗漏的历史 fallback 路径
- 然后一次性进入：
  - 本地最终 build
  - 单次部署到 demo
  - 交给用户集中验证

## 2026-04-22 20:31 P1 Single Deploy Completed

- 当前阶段：`部署验证阶段`
- 当前完成度：`88%`
- 远端备份目录：
  - `/srv/ageo/.codex-backups/20260422-202633-p1-unified-batch`

### 已部署内容

- backend:
  - `websocket_langgraph.py`
  - `knowledge_workspace_service.py`
  - `message_service.py`
  - `table_intake_service.py`
  - `confirmation.py`
  - `nodes_knowledge.py`
  - `nodes_table_intake.py`
  - `orchestrator_context_packets.py`
  - `orchestrator_node.py`
  - `state.py`
- frontend:
  - `process-timeline.tsx`
  - `canvas.ts`

### 部署后基础健康检查

- `ageo-backend.service = active`
- `ageo-frontend.service = active`
- `http://127.0.0.1:8000/docs -> 200`
- `http://127.0.0.1:3000 -> 200`
- `https://demo.imspecta.com -> 200`

### 待用户集中验证的 P1 Checklist

- 导入问题后查看问题内容：
  - 应只打开当前导入 artifact，不再跳历史资料表
- 导入后确认继续：
  - ask_user 不再只是“识别到 6 个问题”，而是可决策的正式确认
- 询问刚上传/导入的表格内容：
  - 应优先 scoped 到当前导入 artifact，不扫全历史
- 查询结果导航/version/title：
  - 不应再因为当前导入查询生成新的泛化“过往资料表”污染导航
- 平台名/公共显示：
  - 不再出现 `hunyuan`、内部 skill 名
  - `官网 AI 友好度` 不应误映射成 `官网转化率`
- 查询结果维度：
  - 结果列应区分 `来源范围 / 来源类型 / 回答内容 / 回答情感 / 摘要 / 标签`
  - 不再把不同维度混在一列或一段里

### 当前仍未 closed 的原因

- 这轮按协议没有继续做中间 smoke 交互验收
- 当前等待用户在 demo 上按 checklist 做集中验证，再决定是否还有极小 `P1-fix`

## 2026-04-22 22:05 历史具体回答查询 skill loop 根因冻结 / 首轮修正已部署

- 当前阶段：`部署验证阶段`
- 当前完成度：`86%`
- 会话证据：
  - `session_id = 51a51ea9-4f63-4d72-8292-ec8e22197d05`
  - `task = ca6c37da-0132-437e-9aeb-dbfc4169f690`
  - `run = bbd358a1-a456-458c-93ed-03db9663f976`

### 直接根因

- `Root cause A`：
  - “查询之前带有负面信息的回答”这类请求没有被收成一个有边界的历史回答查询能力
  - Orchestrator 先后放出了多次 `knowledge_lookup`，然后继续漂到 `post_analysis_skill -> knowledge_aggregate -> knowledge_compare`
- `Root cause B`：
  - 第 3 次 `knowledge_lookup` 被 retry gate 拦住后，只是把 tool error 注回 history，然后又回到 orchestrator 继续自由规划
  - 结果不是停下来整理已有结果，而是继续漂移到别的 knowledge / post-analysis 技能
- `Root cause C`：
  - 每次 tool call 都会发完整的 `send_plan_event + send_action_log_event`，所以一次历史查询被拆成了 5~6 条“执行计划”
- `Root cause D`：
  - 在上述膨胀后的 history 上，下一次 GLM streaming 请求最终打出 `messages 参数非法`
  - 目前已补 payload role summary 日志，下一次若还复现，就能直接钉到具体 message shape

### 统一修法

- `orchestrator_node.py`
  - 新增 bounded route：
    - “历史/之前/过往 + 回答/答案/内容”这类请求，直接走一次 `knowledge_export(source_types=[fetch_answer])`
    - 不再让 LLM 自由串 `knowledge_lookup -> aggregate -> compare -> post_analysis`
  - 新增 bounded close-out：
    - 当这类请求的 `knowledge_export_result` 已命中后，直接 deterministic 收口，不再继续回到 LLM 漂移
  - 对这类 bounded 历史查询，抑制 `knowledge_* / post_analysis_skill` 的进度卡、action log 和 fallback 文案，避免一条问题刷出 5~6 条“执行计划”
  - 对 knowledge retry cap 的错误文案做了专门收口：
    - 到上限后不再鼓励继续调用更多 `knowledge_* / post_analysis_skill`
    - 改成要求直接基于已有结果整理回答，或只向用户要求更精确的范围
  - 在 orchestrator streaming 前和异常路径补了 payload role summary 日志，便于下一次定位 `messages 参数非法`

- `nodes_knowledge.py`
  - `knowledge_export_result` 现在显式带上 `query`
  - 供 bounded history route 的 deterministic close-out 校验“本次结果是否属于当前这条用户问题”

### 本地验证

- `py_compile`：
  - `orchestrator_node.py`
  - `nodes_knowledge.py`
  - 均已通过
- 脚本级断言（使用 `\\u` 逃逸，避免 Windows PowerShell 中文源码污染）：
  - “查询一下之前带有负面信息的回答” 已命中 bounded history answer query
  - fallback 现在会直接给出 `knowledge_export + fetch_answer`
  - “比较最近两次负面回答变化” 不会误判成这条 bounded query
- `pytest aeo-platform/backend/tests/test_nodes_knowledge.py -q`
  - 已通过

### 当前 still open

- 这批 backend 修正已部署到 demo：
  - 备份目录：`/srv/ageo/.codex-backups/20260422-2205-history-query-loop-fix`
  - `ageo-backend.service = active`
  - `http://127.0.0.1:8000/docs -> 200`
- 还没做最终 live 验证：
  - 是否从“五六条消息”收敛为“一次执行”
  - 是否不再漂到 `knowledge_compare / post_analysis_skill`
  - 是否不再打出 `messages 参数非法`

## 2026-04-22 22:31 历史具体回答查询 continuation：recall 后“需要看完整内容”仍退回自由 skill 串链

- 当前阶段：`部署验证阶段`
- 当前完成度：`93%`

### 会话证据

- `session_id = 51a51ea9-4f63-4d72-8292-ec8e22197d05`
- `task = 32930a51-282c-468e-a83a-ec74b1dbf468`
- `run = 24604a2e-8bc1-4aa5-bd78-666f55fbe3c2`
- 用户输入：`需要看完整内容。`

### 直接根因

- 上一版 bounded history answer route 只覆盖“当前用户输入本身就显式包含历史 + 回答内容”的问法
- 这次用户是在 `recall` 之后只说了 `需要看完整内容。`
- 当时 `session_recalled = True`
- `_is_bounded_history_answer_query_state()` 又把 recalled session 直接排除
- 结果：
  - 这条承接型 follow-up 没命中 bounded continuation
  - 又退回 LLM 自由规划
  - 日志里重新出现：
    - `knowledge_lookup`
    - `knowledge_export`
    - `knowledge_lookup`
    - 最后 `ask_user`

### 修法

- 在 `orchestrator_node.py` 增加 history-answer continuation 解析：
  - 识别 `完整内容 / 完整回答 / 原文 / 全文` 这类 follow-up
  - 从最近上下文里回溯上一条明确的历史回答查询
  - 将本轮 follow-up 绑定回同一条 bounded export，而不是重新自由规划
- `_is_bounded_history_answer_query_state()` 不再单纯因 `session_recalled` 而放弃这类 continuation
- `_route_history_answer_query_without_llm()` 现在会在 continuation 场景下直接走：
  - `knowledge_export(source_types=[fetch_answer])`
  - query 解析成如：`查询一下之前带有负面信息的回答 完整内容`
- `_infer_knowledge_fallback_tool()` 也同步改成基于 resolved continuation query，而不是只看最新一句字面文本

### 本地验证

- `py_compile orchestrator_node.py` 通过
- 使用共享 `.env.local` 做脚本级断言：
  - `session_recalled=True`
  - 上下文里前一条用户问“查询一下之前带有负面信息的回答”
  - 当前用户只说“需要看完整内容。”
  - 解析结果已稳定变成：
    - `查询一下之前带有负面信息的回答 完整内容`
- `pytest aeo-platform/backend/tests/test_nodes_knowledge.py -q` 通过

### 部署

- 已部署到 demo：
  - 备份目录：`/srv/ageo/.codex-backups/20260422-2231-history-answer-continuation`
  - `ageo-backend.service = active`
  - `http://127.0.0.1:8000/docs -> 200`

### 当前 still open

- 还没做最终用户侧 live 验证：
  - follow-up `需要看完整内容。` 是否收敛成 bounded export
  - 是否不再刷多条“执行计划”
  - 是否不再退回 `knowledge_lookup -> export -> lookup -> ask_user`

## 2026-04-22 22:18 P0 残余：Dashboard 进入后 Chat 导航 / Tab 点击无响应

- 当前阶段：`部署验证阶段`
- 当前完成度：`97%`

### 直接根因

- `frontend/src/components/chat/ChatPanel.tsx`
  - 存在一段 route-target 对齐 effect
  - 当从 Dashboard 带着 `artifact_id/output_id` 进入 Chat 时，这段 effect 会持续把 `activeContentIndex` 拉回初始 route target
  - 因为 `initialArtifactId/initialOutputId` 在当前会话里保持不变，所以用户后续点击左侧导航或顶部 Tab，虽然点击事件触发了 `setActiveContentById()`，但选中态立刻又被这段 effect 抢回，体感就是“点哪都没反应”

### 修法

- 这段 route-lock 只保留到“首轮 route artifact 成功落位并完成 URL sync ready”为止
- 一旦 `artifactUrlSyncReadyRef.current = true`，后续不再持续强制把用户切换拉回初始 report

### 本地验证

- `frontend: npx tsc --noEmit` 通过
- `frontend: npm run lint -- --quiet` 通过

### 当前 still open

- 修正已完成，本地静态校验已过，且已部署到 demo：
  - 备份目录：`/srv/ageo/.codex-backups/20260422-2218-p0-nav-click-fix`
  - `frontend build` 已成功
  - `ageo-frontend.service = active`
  - `http://127.0.0.1:3000 -> 200`
- 还没完成最终 demo live 点击验证：
  - Dashboard 打开报告后
  - 左侧导航应可正常切换
  - 顶部 Tab 应可正常切换

## 2026-04-22 22:32 P0 残余：Chat 返回首页需要多次点击

- 当前阶段：`部署验证阶段`
- 当前完成度：`91%`

### 直接根因

- `frontend/src/components/layout/HomeBrandLink.tsx`
  - Chat 侧栏里的“返回首页”入口用了 `requireConfirm`
  - 确认弹层直接渲染在侧栏组件树内部
- `frontend/src/components/layout/ChatLayout.tsx`
  - 侧栏容器是 `motion.div`
  - Framer Motion 会给祖先建立 transform 上下文
- 结果：
  - `HomeBrandLink` 里的 `fixed` 确认层会被 transform 祖先局部化
  - 第一次点击实际上可能已经打开了确认层，但确认层被限制在侧栏/局部区域内，体感就像“没反应”
  - 用户继续点多次后，才可能碰到真实可点区域或误打误撞完成跳转

### 修法

- 把 `HomeBrandLink` 的确认层改成 `createPortal(..., document.body)`
- 让确认层脱离侧栏和 `motion.div` 的 transform 上下文
- 顺手给入口按钮和关闭按钮补 `type=\"button\"`，避免默认按钮语义带来额外噪音

### 本地验证

- `frontend: npx tsc --noEmit` 通过
- `frontend: npm run lint -- --quiet` 通过

### 当前 still open

- 这批修正已部署到 demo：
  - 备份目录：`/srv/ageo/.codex-backups/20260422-221904-homebrandlink-fix`
  - `frontend build` 已成功
  - `ageo-frontend.service = active`
  - `http://127.0.0.1:3000 -> 200`
- 还没做最终 live 点击验证：
  - Chat 内点击“返回首页”
  - 应该一次点击就稳定出现全屏确认层
  - 点击确认后应直接跳转到 `/dashboard`

## 2026-04-22 22:45 P0 残余：compact 导航边框裁切 / 资料查询每次新增一个导航

- 当前阶段：`部署验证阶段`
- 当前完成度：`90%`

### 直接根因

- `frontend/src/components/layout/ArtifactNav.tsx`
  - compact 模式下外层容器宽度只有 48px，但内部按钮用了固定 `w-12` 再叠 `px-1.5`
  - 实际渲染宽度超过可用竖条宽度，导致选中态边框被裁切，看起来像“外框显示不全”
- `aeo-platform/backend/app/workflow/nodes_knowledge.py`
  - `knowledge_export` 为历史资料表生成 artifact key 时把 `query/start_date/end_date/platform/...` 全部纳入 digest
  - 结果每查一次资料都会生成一个新的 `artifact_id`
  - 前端自然只能把它们当成多个导航项，而不是同一份资料表的不同版本

### 修法

- `ArtifactNav.tsx`
  - compact 按钮改成 `w-full` 适配 48px 竖条
  - 去掉会放大裁切感的 active `boxShadow`
  - 外层 padding 收紧，保持边框完整可见
- `nodes_knowledge.py`
  - 对 `source_scope = knowledge_records` 的历史资料导出，统一收成一个稳定 artifact family：
    - `session_id + knowledge_export_history`
  - 这样后续资料查询会走同一个 artifact，通过版本累积，而不是每次长出一个新的“资料”导航

### 本地验证

- `backend: py_compile nodes_knowledge.py` 通过
- `frontend: npx tsc --noEmit` 通过
- `frontend: npm run lint -- --quiet` 通过

### 部署

- 已部署到 demo：
  - 备份目录：`/srv/ageo/.codex-backups/20260422-2245-nav-history-family`
  - `ageo-backend.service = active`
  - `ageo-frontend.service = active`
  - `http://127.0.0.1:8000/docs -> 200`
  - `http://127.0.0.1:3000 -> 200`

### 当前 still open

- 还没做最终页面级验证：
  - 资料查询后是否复用同一个导航项，仅通过版本更新
  - compact 导航选中外框是否已经完整显示

## 2026-04-22 23:05 P0 残余：刷新后旧“资料”导航不自动收拢

- 当前阶段：`部署验证阶段`
- 当前完成度：`96%`

### 直接根因

- 之前在 `aeo-platform/backend/app/workflow/nodes_knowledge.py` 里做的 stable artifact family，只会影响**后续新生成**的历史资料导出。
- 但当前旧会话里已经落库的多份历史资料表，本身就是多个不同 `artifact_id`。
- 刷新页面时，前端 hydrate 只是把这些旧 artifact 重新读出来，并不会自动把数据库里的旧 `artifact_id` 重写合并，所以“刷新以后没反应”是预期内现象。
- 也就是说：
  - backend 修的是“以后别再长新的重复资料导航”
  - 但对“旧会话里已经长出来的一串资料导航”，还缺一个前端 family 归并层。

### 修法

- 新增前端公共 artifact identity 逻辑：
  - `frontend/src/lib/artifactIdentity.ts`
- 对 `source_scope = knowledge_records` 的旧历史资料导出，在前端 hydrate / 历史 output card 恢复时统一映射到同一个 canonical artifact family：
  - `<session_id>_knowledge_export_history`
- 这样：
  - 旧会话刷新后也会被折叠成一个“资料”导航
  - 旧记录会通过 `versions` 机制累积，而不是继续并排显示多个“资料”
- 实时 websocket 路径不强行伪造 `session_id`，继续沿用后端当前稳定下来的 `artifact_id`，避免在 live 执行时引入新的 identity 漂移。

### 本地验证

- `frontend: npx tsc --noEmit` 通过
- `frontend: npm run lint -- --quiet` 通过

### 部署

- 已部署到 demo：
  - 备份目录：`/srv/ageo/.codex-backups/20260422-2318-history-nav-frontend-family`
  - 远端 `frontend build` 已重新跑过
  - `ageo-frontend.service = active`

### 当前 still open

- 还没做最终页面级验证：
  - 旧会话刷新后，多份历史“资料”是否折叠为一个导航项
  - 同一“资料”导航是否能通过 version 正常切换历史结果

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

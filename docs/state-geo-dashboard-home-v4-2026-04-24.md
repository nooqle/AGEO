# GEO Dashboard 首页改版开发 State

日期：2026-04-24

## 当前状态

当前阶段：S7 本地冒烟与 E2E 已完成

当前结论：

- 使用现有 worktree：`D:\AGEO-worktrees\geo-dashboard-product-proposal`
- 使用现有分支：`codex/geo-dashboard-product-proposal`
- 不在 `D:\AGEO-main` 直接开发。
- v4 原型和 PRD 已作为产品基线。
- 本次开发不重做品牌管理区，保留现有品牌卡片切换和管理能力。
- 本次开发重点是最近一轮分析模块、首页 API contract、A5 首页投影。
- 当前完成边界：本地代码、PRD、原型、开发拆分、State、静态验证和本地 E2E 均已闭合。
- 当前未完成边界：尚未提交、尚未创建 PR、尚未合并 main、尚未部署外部环境。

## 协同执行卡 State

### 1. Boundary

本线程解决：

- Dashboard 首页从“报告入口”改为“监测首页 + 最近一轮分析”。
- 保留多品牌监测切换、新建品牌、进入分析、设置监测等现有能力。
- 用 A5 / 首页 API 提供词云、平台诊断、风险、优势、提及率排行和信源结构。

本线程不解决：

- 线上部署。
- main 合并。
- Chat / Canvas / Monitoring 主流程重构。
- 行业级榜单、首位提及率、情绪趋势图。

完成声明只在以下边界内成立：

- 当前 feature worktree：`D:\AGEO-worktrees\geo-dashboard-product-proposal`
- 当前分支：`codex/geo-dashboard-product-proposal`
- 本地后端：`http://127.0.0.1:8001`
- 本地前端：`http://127.0.0.1:3000`

### 2. Four Calibration Questions

| 问题 | 当前答案 |
| --- | --- |
| What is this exactly? | Dashboard 首页改版，核心是信息架构、首页 contract、A5 首页投影和品牌管理入口保留。 |
| Who is the authority source? | 产品口径以 PRD 和 v4 原型为准；数据口径以 A5 canonical 和 `/analytics/v2/dashboard-home` 为准；运行证据以本地 E2E 为准。 |
| What is the state lifecycle? | A5 生成 `dashboard_projection.home_v4`，后端投影为首页 API，前端 adapter normalize，Dashboard 按当前 `selectedBrandId` 渲染。 |
| Where is "done" true? | 本地验证完成；提交、PR、合并、部署仍是后续边界。 |

### 3. State Split

| State | 当前状态 |
| --- | --- |
| Project State | 代码与文档均在当前 worktree，尚未提交；分支落后 `origin/main` 1 个提交，暂未合并。 |
| Conversation State | 用户已要求按协同执行卡推进；当前重点从“继续开发”转为“证据写回、收口、准备提交/PR”。 |
| Validation State | 静态验证、本地 API smoke、页面 E2E 已通过；IAB 自动化因本机 Node 版本不足未执行。 |

### 4. Failure Samples

| Signal | Why it survived | Kill step | Writeback |
| --- | --- | --- | --- |
| 页面可见连续问号串 | 源码扫描未命中，但共享测试数据里已有损坏字段，纯源码扫描发现不了。 | E2E 必须检查页面可见文本，不只扫源码。 | 品牌卡展示层兜底损坏问号串；保留 E2E 文案禁用项。 |
| `设置监测` 自动化点击无跳转 | 品牌卡外层 `role=button` 包住真实按钮，无障碍树里按钮范围歧义。 | E2E 对比 `role=button` 数量和真实 button 数量。 | 拆分品牌卡顶部切换区和底部动作按钮。 |
| 控制台大量资源失败 | 品牌头像直接请求外部 favicon，测试域名和部分真实域名会失败。 | E2E 把真实 console error / requestfailed 作为阻塞项。 | 品牌卡头像改为本地字母头像，避免外部请求拖慢首页。 |

### 5. Writeback Layer

| 层级 | 写回内容 |
| --- | --- |
| Global | 本轮继续验证了执行卡里的“可见文本 E2E”和“failure sample 立即保存”有效，但暂不修改全局 skill。 |
| Project-local | 保留 AGENTS.md 的 Windows 编码规则、runtime reuse、validation protocol，不新增仓库级规则。 |
| Task-local | 本文档记录本次改版边界、State、E2E 证据、failure samples 和剩余风险。 |

## 开发阶段 State

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| S0 开发设计与状态对齐 | 已完成 | 已完成代码边界梳理、开发拆分文档和状态文档 |
| S1 前端类型与适配层 | 已完成 | 已扩展 v4 首页类型和 `dashboardHome` normalize，旧字段保持兼容 |
| S2 前端最近一轮分析模块 | 已完成 | 已按 v4 顺序升级 `DashboardHomeBoards.tsx` |
| S3 首页 API 投影扩展 | 已完成 | 已扩展 `analytics_service.py` 的 v4 首页字段投影 |
| S4 A5 首页投影 | 已完成 | 已写出 `dashboard_projection.home_v4`，排行扩展到前 10 |
| S5 端到端验证 | 已完成 | 已用本地后端 8001、前端 3000 跑 API 与页面 E2E |
| S6 UI 与交互 Review | 已完成 | 已压缩首页文案、收口旧接口副标题、补充关键点击 loading、优化站内跳转 |
| S7 冒烟问题修正 | 已完成 | 已修复品牌卡嵌套交互控件、外部 favicon 请求、损坏问号串展示 |

## 已确认代码边界

### 前端

- `frontend/src/components/dashboard/DashboardPage.tsx`
  - 负责 Dashboard 首页总装。
  - 已包含 `selectedBrandId`、实体列表、首页数据拉取、打开报告。
- `frontend/src/components/dashboard/DashboardHomeBoards.tsx`
  - 当前最近一轮分析模块。
  - 需要升级为 v4 信息架构。
- `frontend/src/types/dashboard.ts`
  - 当前首页类型只有旧摘要、指标、引用分布、关联问题和兼容 board。
  - 需要补 v4 类型。
- `frontend/src/adapters/dashboardHome.ts`
  - 当前只 normalize 旧字段。
  - 需要补 v4 字段 normalize。

### 后端

- `aeo-platform/backend/app/api/v1/analytics.py`
  - `GET /analytics/v2/dashboard-home` 已存在。
  - 路由层暂不需要新增接口。
- `aeo-platform/backend/app/services/analytics_service.py`
  - `get_dashboard_home_v2` 是首页聚合入口。
  - `_build_dashboard_home_from_projection` 是新 A5 artifact 的优先投影入口。
- `aeo-platform/backend/app/workflow/a5/canonical.py`
  - `build_dashboard_projection` 是 A5 dashboard 投影入口。
  - `MetricBundle` 已有可用基础字段。

## 产品约束

- 多品牌监测切换必须保留在品牌列表/品牌卡片区。
- 最近一轮分析只展示当前选中品牌的报告，不承担品牌切换。
- 不展示英文 UI 文案。
- 不写解释性自说自话文案。
- 提及率排行展示前十。
- 不展示提及份额。
- 不做首位提及率。
- 正负词云必须有独立模块。
- 正负词云第一阶段基于稳定正向理由和负向主题聚合。

## 当前数据可用性

| 模块 | 当前可用字段 | 缺口 |
| --- | --- | --- |
| KPI | `brand_visibility`、`brand_rank`、`official_conversion_rate`、`negative_rate` | 已展示 4 个指标 |
| 正负词云 | `top_positive_reasons`、`top_negative_topics` | 已投影为 `wordCloud` |
| 平台诊断 | `platform_profile`、answer/platform rows | 已投影为 `platformDiagnosis` |
| 高风险问题 | `question_diagnostics.risk_rows`、`sentiment_risk` | 已投影为 `risks` |
| 优势场景 | question rows、positive mentions | 已投影为 `advantages` |
| 提及率排行 | `top_brand_ranking` | 已扩展前 10，并使用 mentionRate 口径 |
| 信源结构 | `source_summary` | 已投影为 `sourceStructure` |

## 下一步

1. 复核 diff，确认没有范围外变更。
2. 如要提交，按用户提交偏好只纳入功能代码与必要文档，不纳入临时日志、截图、测试脚本。
3. 提交前处理分支落后 `origin/main` 1 个提交的策略：先确认是否需要 rebase/merge main。

## 验证记录

已执行：

- 扫描 PRD、开发拆分文档、State 文档和 v4 原型，未发现异常问号占位符。
- `python scripts/validate_change.py`：通过。
- `frontend/src/types/dashboard.ts`：已加入 v4 首页字段类型。
- `frontend/src/adapters/dashboardHome.ts`：已加入 v4 字段 normalize，兼容 camelCase 与 snake_case。
- `npm ci`：已安装当前 worktree 前端依赖用于验证。
- `npm run lint`：通过，保留 5 个既有 warning，未出现 error。
- `python scripts/validate_change.py`：通过，改动文件未发现异常问号占位符。
- `frontend/src/components/dashboard/DashboardHomeBoards.tsx`：已升级为 v4 模块顺序，品牌管理区未改动。
- `npm run build`：通过。
- UI 文案 Review：新首页模块移除长解释文案，指标副标题收为空值，按钮文案统一为短动作。
- 交互 Review：品牌分析、设置监测、打开报告均已有按钮级 loading；设置监测改为站内路由跳转，避免整页刷新。
- `python scripts/validate_change.py`：通过，ruff、compileall、tsc、lint 均无 error。
- `npm run lint`：通过，仍有 5 个既有 warning。
- `npm run build`：通过。
- 本地后端：当前分支代码使用 `.codex-main-merge` 环境变量启动在 `http://127.0.0.1:8001`，`/health` 通过。
- 本地前端：当前分支代码启动在 `http://127.0.0.1:3000`，指向 `http://127.0.0.1:8001/api/v1`。
- E2E：通过后端健康、品牌列表 API、首页 v4 API contract、Dashboard 首屏、文案禁用项、最近一轮分析模块、按钮无障碍范围、设置监测 loading 与跳转。
- E2E 发现并修复：品牌卡外层 `role=button` 包含真实按钮导致交互选择器歧义；已拆为顶部切换区和底部动作按钮。
- E2E 发现并修复：品牌头像直接请求外部 favicon 导致控制台错误和性能噪音；已改为本地字母头像。
- E2E 发现并修复：共享测试数据里存在损坏问号串；品牌卡展示层已兜底为“未命名品牌”或“未设置行业”。
- `python scripts/validate_change.py`：通过，剩余 4 个既有 warning。
- `npm run lint`：通过，剩余 4 个既有 warning。
- `npm run build`：通过。

## 当前环境限制

- IAB 自动化未执行：本机 `node_repl` 解析到的 Node 版本为 22.19.0，低于 browser-use 需要的 22.22.0。
- 本轮浏览器 E2E 使用 Python Playwright 运行；跳转过程中出现的 `net::ERR_ABORTED` 为页面导航中断旧请求，已过滤为非真实错误。
- `aeo-platform/backend/app/services/analytics_service.py`：已输出 `wordCloud`、`platformDiagnosis`、`risks`、`advantages`、`mentionRanking`、`sourceStructure`。
- `python -m py_compile aeo-platform/backend/app/services/analytics_service.py`：通过。
- `python scripts/validate_change.py`：通过，ruff 通过，前端 lint 仍只有 5 个既有 warning。
- `aeo-platform/backend/app/workflow/a5/canonical.py`：已新增 `home_v4` 投影；`top_brand_ranking` 已从前 5 扩展到前 10。
- 已将报告正文中的排名口径从“提及份额”同步为“提及率”。
- 禁用口径扫描：未发现“首位提及”“提及份额”“mentionShare”“firstMention”。
- `python scripts/validate_change.py`：通过。
- `npm run build`：通过。

当前工作区：

- 未提交文件包括 PRD、v4 原型、开发拆分文档、State 文档。
- 已修改 `aeo-platform/backend/app/services/analytics_service.py`、`aeo-platform/backend/app/workflow/a5/canonical.py`、`frontend/src/types/dashboard.ts`、`frontend/src/adapters/dashboardHome.ts`、`frontend/src/components/dashboard/DashboardHomeBoards.tsx`。
- `node_modules` 仅用于本地验证，不纳入提交范围。
- 当前分支落后远端 1 个提交，暂未合并，避免在开发中引入额外变量。

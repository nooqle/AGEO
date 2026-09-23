# 千问作为第五个 AIO 采集平台：调研与开发准备

日期：2026-09-23。状态：第五平台代码已开发并通过聚焦单测；真实 API Key、登录态浏览器试采尚未验收。工作树：`D:\AGEO-worktrees\qwen-fifth-platform-20260923`，分支 `codex/qwen-fifth-platform-20260923`，基线 `c51be52f3164372dff6eee799a0a83428f4a32f0`（最近一次成功的 demo 部署 Action 所用 SHA；尚未用服务器当前链接独立复核）。`D:\AGEO-main` 的 `origin/main` 仍在 2026-06-25 的 `65ee2c2`，因此本任务从已部署代码建立隔离工作树，不能把旧 main 当成当前运行实现。未改线上配置、未部署、未发起千问 API 请求。

## 当前实现与未验收范围

已接入公开平台 `qwen`、逐平台 API/浏览器方式、旧拓扑默认关闭千问、Qwen3.7 Plus DashScope 多模态流式搜索、`[ref_数字]` 正文引用与检索候选分离、Qwen 专属 AIO context、登录后采集门闸，以及 A4/A5/Control 和画布的第五平台显示。浏览器初始化失败会产生可见失败行，避免报告漏掉计划中的千问；开始运行前会核对服务器权威拓扑与前端开关。独立审查已修复流式 401/429 异常、普通编号误判引用、五平台报告截断、零平台误回退等问题。

当前只完成模拟响应和本地静态/单元测试。浏览器自动化工具本次连续返回 `Unable to load browser request-header policy`，无法验证登录后 qwen.com 的 DOM 选择器；独立 Key 尚未完成真实单题调用。登录态、联网搜索开关、正文与来源抓取、供应商实际用量和 Control 投影仍须用真实环境验收。快速连续切换连线时，前端异步 PUT 仍可能发生低频先后顺序竞态；运行前 GET 校验可以阻止常见的单次未保存情形，不能替代服务端运行快照。以下“方案边界”和“验收门槛”仍是上线前要求，不等同于已验收事实。

## 结论与方案边界

千问可以作为第五个 **公开平台 ID `qwen`** 接入，每次运行仍由用户独立选择 `api` 或 `browser`。API 与 `qwen.com` 浏览器结果都归入同一个平台，但保存原始执行方式、真实模型 ID、搜索执行证据和引用来源；绝不把 API 和浏览器的回答当成同一条记录。先以一题一平台的受控试采证明两个入口能生成相同的 A4 结果契约，再开放五平台运行。

千问网页目前在未登录状态下允许提问。2026-09-23 对公开问题“安利纽崔莱是什么？”做了单次实测：`qwen.com` 显示 `Qwen3.7-千问`，自动检索 2 个关键词、参考 9 篇资料，回答正文与来源链接均可在页面读取；输入框为 `[contenteditable="true"][role="textbox"]`，发送按钮有 `aria-label="发送消息"`，正文含 `.qk-markdown-react`。**产品要求仍是登录后采集：匿名可回答不等于可用于 Specta 正式采集。** 点击“登录”后可见“用千问 APP 扫码登录”，并有手机号验证码、淘宝及支付宝入口；本次没有完成登录。这只证明当前匿名网页和登录入口的行为，不证明生产 AIO/CDP 会话、登录状态、限流、批量稳定性或 API 与网页模型等价。网页结构属于易变运行时选择器，必须有 DOM 稳定性和失败证据。

## 官方 API 事实

用户提供的[联网搜索文档](https://platform.qianwenai.com/docs/developer-guides/tool-calling/web-search)使用 `https://maas.qianwenaiapi.com/compatible-mode/v1`（OpenAI 兼容）和 `https://maas.qianwenaiapi.com/api/v1`（DashScope）。不能直接沿用其他阿里云地域或旧 DashScope endpoint 的 Key/计费假设。Responses API 用 `tools: [{"type":"web_search"}]`；响应的 `output` 有 `web_search_call.action.sources`，`usage.x_tools.web_search.count` 记录次数，但不支持自动插入引用角标。DashScope 调用可用 `enable_search`、`search_options.enable_source` 与 `enable_citation`，并在 `search_info.search_results` 返回来源。OpenAI 兼容 Chat Completions 只开 `enable_search` 时不能返回搜索来源，不宜作为需要可核查引用的正式采集路径。

Qwen3.8 Flash/Max、Qwen3.7 系列均列在官方搜索支持清单；Qwen3.8 在 Chat Completions/DashScope 下不支持 `search_strategy: agent`，但在 Responses API 下可用 `web_search` 多轮检索。是否真实搜索必须依据工具调用和来源，不能只看回答或 `enable_search=true`。官方说明搜索链路按账号限流 15 RPS，超限可能**跳过搜索但不报错**。模型 token 与搜索工具分开计费：目录价每千次 `turbo` 3 元、`max`/`agent` 4 元，Responses 搜索按 `agent` 计；搜索内容还会增加输入 token。单题可能发生多次搜索，不能把“请求数”当成“搜索次数”。实际模型价目和优惠以选定模型的模型市场为准，未选型前 Control 不写猜测单价。

实现选用 DashScope 多模态生成端点与 `qwen3.7-plus`，因为可同时要求联网搜索、来源与明确的引用角标。这个选择已通过模拟响应验证，仍须用真实 Key 核对供应商响应、完成率、时延与单题费用。`qwen.com` 页面上的 `Qwen3.7-千问` 不是某个公开 API 型号的映射证明。

## 当前代码接点与实现顺序

1. **冻结平台契约。** 后端 `app/core/constants.py`、`app/schemas/platform_fetch_methods.py`、`app/tools/a4_fetch_agent.py`、`app/workflow/topology_resolver.py` 与前端平台设置已增加 `qwen`，公共/执行 ID 相同，避免元宝 `yuanbao`/`hunyuan` 那种双 ID 分叉。旧四平台拓扑通过 v1→v2 读取投影默认断开千问，用户明确开启后才连通；新实体在灰度阶段也默认关闭千问。A4 已补齐平台失败行，A5 按本轮结果中的平台构造分母。独立的持久化计划快照及快速连线切换时的服务端冻结仍待完善。
2. **API 路径。** 新客户端在 `app/core/fetchers/api/`，接入 `app/workflow/nodes_a4.py` 的初始化、并发/重试/延迟、任务映射、结果规范化和 `app/tools/a4_fetch_agent.py` 的公开契约。只有收到可用最终回答且有真实搜索证据时才标记“联网搜索成功”；失败仍保留用量和原始错误，不将无搜索回答冒充成功。
3. **浏览器路径。** 在 `app/core/fetchers/browser/selectors.yaml` 配置千问选择器，新 handler 通过 `app/tools/a4_fetch_agent.py` 分发，复用 AIO/CDP、登录接管 UI、超时和引用提取的公共能力。正式采集必须取得千问专属的**正向登录证据**（需在真实登录试采中确定，例如已验证的账户身份/个人菜单）；输入框可用或登录按钮消失都不足以证明已登录。首次提交、人工接管恢复后及每题提交前都检查，证据未知即 fail closed/`login_required`，**不得把匿名回答记为正式成功**。若见扫码弹窗或短信登录框，立即发出 `login_required`。用户扫码/验证完成后仍需显式“我已完成”，随后由 handler 独立复核正向登录证据；不能把共用门闸的完成信号当作登录成功，因为 `BaseBrowserHandler._wait_for_user_action_completion` 当前在用户确认后不会执行传入的 `ready_check`。过期、取消及失败要留下可诊断状态。不要依赖内部私有接口或本次浏览器会话的临时 URL。验证输入、完成信号、来源展开、反机器人/登录弹窗、取消及迟到结果隔离。
4. **下游一致性。** `app/workflow/a5/canonical.py`、`postprocess.py:612`、`diagnosis.py`、`association_circle.py` 和前端采集结果/报告平台排序及拓扑意图增加千问。A5 的平台分母应以该次运行实际计划/有效平台为准。现有 `canonical.py:1564-1670,1896-1919` 会把输入来源逐条视为 citation；Responses 的 `action.sources` 只是检索来源，不能直接写入正文引用指标。若试采后仍选 Responses，应标记 `reference_scope=retrieved_search_results` 并让 A5 将其与实际正文引用分开；若需要现有引用指标口径，优先验证 DashScope 的 `enable_source` + `enable_citation`。
5. **Control 成本。** `app/services/llm_usage_service.py` 当前未见千问价目分支；`usage_billing_summary.py:52-79` 当前只识别已有提供商的搜索计数，并从调用时保存的 pricing 快照汇总。接入时按每次尝试分开保存模型输入/输出 token、缓存命中、`usage.x_tools.web_search.count` 和搜索工具费用，失败尝试的真实用量也要保留；未获真实计数/价目时显示“未知”，不能写 0。浏览器路径没有 API token 账单，不应套用 API 定价。

## AI Coding Router 记录

按 [AI Coding Router v3.0](C:/Users/Administrator/.codex/skills/ai-coding-router/ROUTER.md) 五项评分：范围 2、架构新颖度 2、可逆性 1、影响风险 2、可观测性 1，总计 **8 / R3**。如后续变更涉及真实账务结算或不可逆历史迁移，升级为 R4。已实际调用 `xiaomi/mimo-v2.6-flash` 作只读 Scout；GPT-6 Sol xhigh Architecture Gate 经两轮返工后对规格给出 PASS。实现阶段由 MiMo V2.6 Pro 完成千问 API 客户端与模拟测试，GPT-6 Sol Max 做独立代码复核；其指出的问题已逐项修补。Grok 仅在真实架构分歧或 MiMo 对同一根因两轮失败时触发，本次未触发。独立复核与模拟测试不代表真实 API、登录态浏览器或上线验收通过。

## 开发验收门槛

- 新运行选五平台时：每题最多产生五个平台结果；每个平台可以独立切换 API/浏览器，A4 持久化记录与 A5/页面可见的平台一致。
- 历史四平台运行与已保存拓扑的结果不被补造千问，历史报告分母不漂移；旧拓扑的千问节点默认断开，用户显式开启后才进入下一轮，新实体默认五平台；旧断边不被覆盖。
- API 试采同时验证回答、搜索工具真实调用、来源 URL、token/cache/tool 用量、无搜索/限流/401/429/超时及成本未知语义。浏览器试采验证回答正文和来源、匿名/登录两状态、取消与超时。
- 浏览器复用 `AioConnectedBrowserClient` 的每用户/每平台登录态存储、语言/时区/Accept-Language、按 Chrome 版本生成 UA 的配置代码，以及 AIO 人工接管和 480 秒登录等待参数；**仅新建隔离 context 才保证这些选项与保存态被应用**。当前客户端对已有 context 会仅凭同域页面复用，未核对用户/环境/平台身份。千问路径必须强制新建隔离 context 并加载其专属 state，或先实现可验证的 context 身份匹配后才允许复用；不得直接复用同域其他用户 context。`AIO_BROWSER_REUSE_DEFAULT_CONTEXT_PLATFORMS` 当前只包含 DeepSeek，不能为了千问放宽共享默认上下文。若保存态失效，再由人工登录并保存，不借用其他平台 Cookie。
- 定向测试覆盖平台 ID、方法校验、拓扑计划、五平台成功与单平台失败、A5 汇总及 Control 账务；执行 `python scripts/validate_change.py`，前端可见更改还需遵守仓库视觉检查与截图验收。
- 上线前确认服务器当前 SHA、配置 Key/额度、AIO CDP 运行、前后端健康及外部入口，先以单题灰度观察，之后才扩大到五平台整轮；部署不在本次调研范围。

资料：[联网搜索](https://platform.qianwenai.com/docs/developer-guides/tool-calling/web-search)、[可用模型](https://platform.qianwenai.com/docs/developer-guides/getting-started/vision-models)、[计费说明](https://platform.qianwenai.com/docs/developer-guides/getting-started/pricing)、[获取 API Key](https://platform.qianwenai.com/docs/api-reference/preparation/api-key)、[千问网页](https://www.qianwen.com/)。

## 门禁返工后的待冻结决定

- `planned_platforms` 是用户在本次运行实际启用的平台集合，`valid_platforms` 是至少拿到一条可分析回答的平台子集，二者在运行创建和完成时分别固化；历史运行无快照时使用版本化四平台集合，不以当前常量推断。`postprocess.py:1280` 的既有“跨平台覆盖率”原本以应采平台数作分母，扩展时继续用本轮 `planned_platforms` 数量以保持口径，但当题×平台采集不完整时标记该数值为观察值/下界，不能当作确定的无品牌覆盖。另分开报告平台触达率=`valid_platforms/planned_platforms`，以及采集完整度=`成功且可分析的题×平台对数/计划题×平台对数`；失败、取消、超时分别计数，不能用平台触达率掩盖大量失败。`canonical.py:1773` 空答案回退本轮计划集合而非全局常量。其他 A5 指标逐项列出分母并以版本化回归样本锁定，不在接入过程中顺手改业务口径。
- 旧拓扑采用读取时 v1→v2 投影：保留所有既有 `removedEdgeIds`，并将 `e-fetch-qwen` 视为断开。新实体只有在 API 与浏览器单题灰度过关、正式开放五平台后才默认接入千问；灰度阶段默认关闭。用户在设置中开启千问后，持久化 v2 和新的边状态。前端画布和后端执行读取同一版本判定，重复读取不会反复变更；不做批量数据库改写。历史采集运行快照始终保留原样。
- 来源分两个字段：`retrieved_sources` 为搜索工具返回的候选 URL，`cited_references` 为回答正文实际引用的来源。A5 现有 citation 指标只读取后者；Responses 若无法提供映射，则 citation 状态应为“不可判定”，不得把全部候选 URL 计入引用数，也不得伪造为 0。API 试采结果决定是否改用可产生角标的 DashScope 协议。
- Qwen API 每次尝试单独保存 token、缓存与搜索工具次数快照。`search_count` 来源必须是供应商返回的工具计数；缺失时为未知。Control 总成本只有模型价和搜索价均已确认时才给完整金额，否则分项展示已知金额与未知部分，不把未知合计当作 0。
- API 使用千问 AI 平台的独立通用 API Key，不复用 MiMo 编程 Token Plan 或其他提供商 Key。现有后端只有其他平台的 Key 配置，开发时新增仅服务端可见的 `QWEN_API_KEY`/Base URL 配置与 `.env.local.example` 占位说明；生产密钥放在 `/srv/ageo-deploy/shared/backend/.env.local` 或等效受控密钥注入位置，绝不写入前端、仓库、日志或本调研文档。创建 Key 后先做不回显密钥的存在性检查与一题有界真实试采，再扩容。

上述契约已通过 Sol 对“调研与开发准备”阶段的架构复核；代码已开始实现，仍不代替真实 API/浏览器试采和上线验收。

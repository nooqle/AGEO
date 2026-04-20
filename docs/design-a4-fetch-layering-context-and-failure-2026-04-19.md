# A4 抓取分层、上下文与失败责任设计（2026-04-19）

## 目的

本文档用于重新定义 A4 抓取阶段与 A5 分析阶段的边界，解决以下问题：

- A4 当前分层存在命名混乱，出问题时难以判断是哪一层失效
- A4 平台抓取失败后，谁负责自动恢复、谁负责人工接管、谁负责整轮交付，当前不清楚
- A4 用户可见输出存在重复真相源，artifact 与 chat 提示可能互相冲突
- A5 曾混入跨行业硬编码文案，违反了 skill 的通用能力边界
- 当前失败只有 `timeout` / `empty_answer` 之类的粗粒度字符串，缺少可诊断证据

本文档先冻结职责和信息边界，不先要求大规模代码重构。

## 关联文档

- `docs/design-geo-canonical-redesign-state-2026-04-17.md`
- `docs/report-writing-principles-2026-04-18.md`
- `docs/design-aio-browser-runtime-boundary-2026-04-09.md`
- `docs/design-browser-agent-state-unification-2026-04-14.md`

## 当前实现中的关键文件

- `aeo-platform/backend/app/workflow/nodes_a4.py`
- `aeo-platform/backend/app/tools/a4_fetch_agent.py`
- `aeo-platform/backend/app/services/fetch_run_platform_state_service.py`
- `aeo-platform/backend/app/core/fetchers/browser/`
- `aeo-platform/backend/app/workflow/a5/canonical.py`

## 范围

本文档覆盖：

- A4 抓取阶段的职责分层
- A4 各层之间传输什么信息
- A4 失败分类、自动恢复、人工接管与整轮交付决策
- A4 失败证据采集设计
- A4 用户可见输出真相源
- A5 防硬编码约束

本文档不覆盖：

- A1/A2/A3 生产逻辑重写
- 各平台 handler 的具体 selector 和 parser 改写
- 监测调度产品交互设计
- A5 指标公式重写

## 总体原则

### 1. A4 是抓取阶段，不是品牌分析阶段

A4 的职责是：

- 去平台问问题
- 抓回回答与引用
- 留存抓取结果和失败证据
- 判断结果是否足够进入 A5

A4 不负责：

- 品牌提及分析
- 官网引用归因
- 竞品挤压解释
- 行业语义归纳
- 报告文案生成

这些应交给 A5。

### 2. A4 默认尽量品牌无关

A4 抓取默认只依赖：

- 问题文本
- 平台
- 执行模式
- timeout / retry / handoff 策略

不默认依赖：

- 品牌别名
- 竞品名单
- 官网域名
- 品牌混淆词
- 品牌语义分析逻辑

如果某些后验识别需要品牌信息，应优先下沉到 A5，而不是前置进 A4 抓取执行。

### 3. 用户只应看到一份抓取真相

A4 的平台成功/失败、逐题结果和汇总统计，应以 fetch artifact 为唯一权威真相源。

不允许同时存在：

- artifact 一套平台统计
- chat 再发一套粗粒度平台状态卡

### 4. 失败必须可解释

失败不应只剩下：

- `timeout`
- `empty_answer`
- `failed`

系统必须尽量区分：

- 是页面接入问题
- 还是页面交互问题
- 还是平台返回问题
- 还是抽取问题
- 还是人工验证阻塞
- 还是编排预算问题

### 5. A5 skill 严禁跨行业硬编码

A5 只能从：

- 当前样本问题
- 当前样本回答
- 当前样本引用
- 通用分析模板

中生成用户可见结论。

禁止出现：

- 汽车/保健品/金融等行业专属写死模板
- 与当前输入无关的场景词
- 由历史项目遗留的行业标签翻译表

## 当前最小演进实现状态（2026-04-20）

本轮已经落地的部分：

- browser failure taxonomy 已进入抓取 contract
- terminal browser failure 已支持 evidence bundle：
  - screenshot
  - current URL
  - text snapshot
  - metadata
- evidence 默认落服务器本地目录，并支持 7 天清理
- fetch artifact 继续作为唯一用户可见抓取真相源
- shared post-submit browser executor 已经落地，四个平台 handler 已开始复用
- `PendingBrowserAction`、action inference、resume helper 已全部迁入 shared
  `browser_executor.py`
- `nodes_a4.py` 不再直接持有 `rate_limit / verify / modal` 恢复分支，而是
  统一委托给 executor 单入口
- `AioAnswerFetchRequest` 已去掉 `brand_profile`，A4 tool seam 收成
  question-only fetch contract

这意味着：

- A4 现在已经能更明确地区分 terminal browser failure
- 失败时能留下最小诊断证据
- handler 的 post-submit capture 逻辑不再四处复制
- A4 orchestrator 与 browser executor 的职责边界已经进一步变清楚
- A4 tool contract 不再把品牌语义当作抓取执行必要输入

但这轮还没有完全做完的部分也需要明确保留：

- API/browser 双路径虽然都已去掉 `has_brand_mention`，但 downstream 的
  knowledge writeback 仍然依赖 A4 结果进入后续品牌语义链
- `nodes_a4.py` 仍然持有少量 pending-action 生命周期编排，例如
  retry callback 与最终 terminal failure 汇总
- browser executor 还不是唯一的浏览器状态机中心，只是已经成为唯一恢复入口

## 当前 code review 结论（2026-04-20）

### 已修复的真实风险

- failure evidence 在 authoritative projection 中最初会把本地文件路径
  (`screenshot_path`, `metadata_path`) 直接带进用户可见 fetch artifact。
  这一点已经修复：projection 层只保留脱敏后的
  `evidence_id / storage_kind / captured_at / has_screenshot / has_text_snapshot`。

### 当前剩余的设计悖论

1. **A4 仍未完全品牌无关**
   - browser/API path 都已去除 `has_brand_mention`
   - 但 A4 完成后仍会通过 downstream writeback 进入品牌相关知识链
   - 这说明抓取执行边界已收窄，但 A4 与品牌语义后处理还未完全切开

2. **tool-facing contract 仍比目标边界更宽**
   - 这个问题已解决：`AioAnswerFetchRequest` 不再携带 `brand_profile`
   - A4 tool seam 现在已经收成“问题抓取合同”

3. **executor 责任已增强，但还未完全收口**
   - shared executor 现在已经覆盖 post-submit capture、action inference、
     resume helper、rate-limit/verify/modal recovery
   - `nodes_a4.py` 仍保留少量 pending-action 生命周期编排和 terminal failure 汇总
   - 这说明 handler 已明显变薄，但 executor/orchestrator 边界仍有最后一层残差

### 当前判断

- 这轮改动已经足够继续 Phase 3
- 但如果目标是彻底清晰的失败责任模型，后续还需要继续把：
  - retry
  - handoff decision
  - timeout classification
  - platform-specific recovery branching
  再进一步从 `nodes_a4.py` 收到统一 executor 里

## A4 分层模型

本方案将 A4 拆成四层：

1. `A4 orchestrator`
2. `browser executor`
3. `platform adapter (handler)`
4. `browser client`

调用链：

`A4 orchestrator -> browser executor -> platform adapter -> browser client`

结果再自下而上回传。

## 1. A4 orchestrator

### 职责

- 从 workflow state 中拿本轮抓取输入
- 决定抓哪些平台、走 API 还是 Browser
- 控制并发、单题 timeout、平台级 global timeout、熔断
- 聚合各平台结果
- 写入：
  - workflow state
  - fetch artifact
  - authoritative platform state
  - task progress / stage result
  - knowledge workspace
- 决定本轮结果是否足够进入 A5

### 输入

- `questions`
- `session_id`
- `task_id`
- `run_id`
- `fetch_mode`
- `platform_filter`
- `human_takeover_state`
- timeout / retry / breaker 配置

### 输出

- `fetch_results`
- A4 artifact
- authoritative platform state
- downstream state for A5

### 不负责

- 平台页面细节
- selector
- parser
- 用户报告文案
- 品牌语义解释

## 2. browser executor

### 职责

browser executor 是浏览器抓取的公共流程控制层。它负责：

- 组装本题浏览器执行上下文
- 统一控制：
  - 打开/复用页面
  - 提交
  - 等待
  - network intercept
  - DOM fallback
  - retry
  - timeout
  - handoff
- 输出统一的单题结果结构
- 统一失败分类
- 在 terminal failure 时采集失败证据

### 输入

- `question`
- `platform`
- `session_id`
- `run_id`
- timeout / retry / handoff policy
- 当前平台执行器

### 输出

- 单题标准结果 packet：
  - `success`
  - `status`
  - `answer`
  - `citations`
  - `duration_ms`
  - `failure_layer`
  - `failure_reason`
  - `retryable`
  - `needs_handoff`
  - `evidence_ref`

### 不负责

- 平台 selector 定义
- A4 整轮编排
- artifact 落库
- 品牌分析

## 3. platform adapter (handler)

### 职责

platform adapter 只处理平台差异。它负责描述并执行：

- 目标 URL
- 新对话入口
- 输入框和发送按钮
- 联网搜索开关
- 模型切换
- 回答区域定位
- 平台特有 parser
- 平台特有登录 / 验证 / 弹窗 / blocker 识别

### 输入

- 当前题目
- browser client
- 平台执行上下文

### 输出

- 平台语义化执行结果：
  - 是否提交成功
  - 是否拿到 network 数据
  - 是否拿到 DOM 数据
  - 平台特有错误类型
  - 页面阻塞状态

### 不负责

- 整轮交付决策
- A4 progress / artifact 写入
- 品牌识别
- 用户可见分析文案

## 4. browser client

### 职责

browser client 是最底层浏览器执行接口层。它负责：

- 打开页面
- 复用页面
- click / fill / press
- snapshot / evaluate
- network intercept
- screenshot / text snapshot

### 输入

- URL
- selector
- 输入文本
- 低层浏览器执行参数

### 输出

- 浏览器执行反馈
- snapshot
- network payload
- 当前页面 URL / DOM 状态

### 不负责

- 平台理解
- 失败分类
- 品牌分析
- 用户输出

## A4 各层信息传输规则

### 1. A4 orchestrator -> browser executor

传递：

- `question`
- `platform`
- `session_id`
- `run_id`
- timeout / retry / handoff 配置
- 当前题目在整轮中的位置

不传递：

- 品牌提及规则
- 官网域名
- 竞品名单

### 2. browser executor -> platform adapter

传递：

- 统一执行上下文
- question 文本
- browser client
- 当前策略（submit/wait/extract/handoff）

不传递：

- A4 整轮进度逻辑
- artifact 持久化逻辑

### 3. platform adapter -> browser client

传递：

- URL
- selector
- 页面动作
- network intercept 规则
- 平台特有页面探测逻辑

### 4. browser client -> platform adapter

返回：

- 页面是否打开成功
- selector 是否存在
- network payload
- snapshot / evaluate 结果

### 5. platform adapter -> browser executor

返回：

- 是否提交成功
- 是否拿到 network answer
- 是否拿到 DOM answer
- 平台特有 blocker 状态
- 平台级错误原因

### 6. browser executor -> A4 orchestrator

返回：

- 标准化单题结果
- 失败层和失败原因
- 是否可重试
- 是否需要人工接管
- 是否已采集失败证据

## 失败责任模型

### 1. platform adapter 负责“报事实”

platform adapter 不决定整轮策略，只负责准确描述：

- 当前失败发生在哪一层
- 当前失败原因是什么
- 是否已提交成功
- 是否拿到可抽取内容
- 当前页面是否处于登录 / 验证 / 弹窗阻塞状态

推荐 failure taxonomy：

- `navigation_failed`
- `submission_not_confirmed`
- `network_intercept_empty`
- `dom_extraction_empty`
- `parser_error`
- `question_timeout`
- `verify_required`
- `modal_blocked`

### 2. browser executor 负责“自动恢复”

browser executor 必须先尝试系统自动恢复，不直接把内部失败甩给用户。

自动恢复包括：

- reopen surface
- resubmit
- re-wait
- intercept fallback
- DOM fallback
- limited retry
- 重新检查页面 ready 状态

### 3. 只有这些情况允许 human handoff

- 登录
- 验证码
- 安全验证
- 账号选择
- modal / blocker 需要人工点击

### 4. 这些情况不应交给人类

- parser 失败
- selector 失效
- DOM 抽取为空
- intercept 为空
- 页面答了但没 parse 出来
- internal timeout

这些属于系统问题，应标记为工程修复对象。

### 5. A4 orchestrator 负责“整轮交付决策”

orchestrator 回答以下问题：

- 这轮结果是否足够进入 A5
- 是不是允许部分成功继续
- 是否应提示重新抓取
- 是否只保留 artifact 而不进入 A5

推荐策略：

- `0` 平台成功：A4 hard fail
- `>= 最小平台阈值`：允许进入 A5
- `>0 且 < 阈值`：保留 artifact，标记结果不足，不自动进入 A5 或进入低可信模式
- partial failure：artifact 为准，不再在 chat 里再发第二套统计

## 失败证据采集设计

### 目标

把 `timeout` / `empty_answer` 这类抽象错误，变成可判断的失败证据。

### 采集时机

只在关键失败态采集：

- `empty_answer`
- `question_timeout`
- `submission_not_confirmed`
- `verify_required`
- `modal_blocked`
- `takeover_required`

### 采集内容

失败证据包至少包含：

- screenshot
- 当前 URL
- platform
- question_id
- failure_type
- 当前阶段
- 时间戳
- 简短 text snapshot
- selector probe 结果（可选）

### 采集责任

- browser executor 决定何时采集
- browser client 负责实际 screenshot / snapshot
- A4 orchestrator 只消费 evidence metadata，不直接操作页面证据

### 存储建议

建议先走服务器本地目录：

- `/srv/ageo/runtime/failure-evidence/YYYY-MM-DD/...`

配套同名 metadata json。

### 生命周期

- 默认只保留失败证据
- 默认保留 7 天
- 每天定时 cleanup
- 同题同平台同失败类型最多保留最近 1-2 份

### 可见性

默认仅做内部诊断，不直接暴露给终端用户。

## A4 用户可见输出规则

### 1. artifact 是唯一抓取真相源

用户可见的：

- 平台成功率
- 平台失败率
- 逐题平台结果
- 抓取汇总统计

都应来自 fetch artifact。

### 2. chat 只保留流程性提示

chat 可以保留：

- 开始抓取
- 人工接管请求
- A4 完成，进入 A5

chat 不再生成第二套平台状态卡。

### 3. authoritative platform state 只服务系统和 artifact

`fetch_run_platform_states` 是系统权威状态，但用户最终只通过 artifact 消费，不直接看内部 row。

## A5 防硬编码规则

### 1. A5 只能使用当前样本事实和通用模板

A5 对用户可见的分析文本，只能基于：

- 当前样本问题
- 当前样本回答
- 当前样本引用
- 通用分析模板

### 2. 严禁跨行业硬编码

禁止：

- 汽车/保健品/金融等行业专属固定标签翻译表
- 与当前输入无关的场景词
- 历史项目遗留的行业术语

### 3. 若需领域语义，必须从样本归纳

允许：

- 从当前问题文本归纳“价格与成本问题”
- 从当前问题文本归纳“具体使用场景问题”

不允许：

- 写死“家庭场景选车问题”
- 写死“带娃出行和家庭使用”
- 写死“同价位车型对比”

### 4. 需要测试护栏

必须保留：

- banned phrase regression tests
- generic copy tests
- 报告正文中不得出现历史行业模板词的断言

## 推荐的最小演进顺序

### Phase 1：治理

- 清 A5 硬编码
- 去掉 A4 chat 平台统计卡
- partial failure 只看 artifact
- 补失败证据采集

### Phase 2：收 executor 职责

- 把自动恢复逻辑统一到 executor
- handler 只保留平台差异
- 统一 failure taxonomy

### Phase 3：收 A4 输入边界

- A4 尽量去品牌化
- 品牌分析回收 A5

### Phase 4：补 observability

- 逐题失败原因
- failure evidence
- per-platform failure summary

## 当前实现状态（2026-04-20）

基于本文档，当前最小实现已经落下了第一阶段的真相源治理和第二阶段
的失败可观测性基础设施。

已落地：

- A4 browser/fetch result contract 已新增：
  - `failure_layer`
  - `failure_reason`
  - `execution_stage`
  - `retryable`
  - `needs_handoff`
  - `evidence_ref`
- terminal browser failure 已支持采集：
  - screenshot
  - current URL
  - brief text snapshot
  - metadata json
- failure evidence 默认按日期目录存储，并支持短期 retention cleanup
- A4 authoritative platform-state projection 已透传结构化 failure 字段
- A4 chat 侧重复平台总结卡已保持下线，artifact 继续作为唯一用户可见
  真相源
- A5 generic-copy 回归护栏已保留，防止重新引入跨行业硬编码
- `browser executor` 已新增共享恢复 helper，`nodes_a4.py` 不再直接展开
  Doubao 的 `rate_limit / verify / modal` 长分支，而是通过 executor 统一
  编排恢复与 handoff
- `pending_action` 也开始从 `nodes_a4.py` 的隐式 dict 协议，收成
  executor 侧的共享 `PendingBrowserAction` dataclass，并把：
  - action inference
  - resume gate
  收到 `browser_executor.py`
- A4 API 路径已停止在 `_fetch_from_doubao / _fetch_from_hunyuan /
  _fetch_from_kimi` 中直接写入 `has_brand_mention`
- `AioAnswerFetchRequest.brand_profile` 已降为兼容可选字段，不再是 A4
  执行合同的必填输入
- `fetch_run_platform_states` 的 authoritative projection 已对 evidence
  metadata 做脱敏：
  - 用户可见 projection 只保留
    `evidence_id / storage_kind / captured_at / has_screenshot / has_text_snapshot`
  - 不再暴露服务器本地 `screenshot_path / metadata_path`
- Phase 3 的最小职责收口继续向前推进：
  - shared executor 已开始承接跨平台恢复逻辑
  - `nodes_a4.py` 不再直接展开 Doubao 的恢复流程
  - API path 与 browser path 在 failure taxonomy 上开始收口到同一套字段

尚未落地：

- `browser executor` / `platform adapter` 的职责还没有在代码里彻底重新切开；
  目前收口集中在 Doubao 恢复链，其他平台仍主要依赖现有 handler 差异
- A4 仍保留少量兼容时期的品牌相关输入/输出 seam：
  - `AioAnswerFetchRequest` 仍保留兼容 `brand_profile` 字段
  - `KnowledgeWorkspaceService.ingest_a4_facts(...)` 仍消费品牌上下文
- failure evidence 还没有进入产品 UI，只保留在内部诊断路径
- `nodes_a4.py` 仍保留 resume-gate / pending-action 层面的恢复编排，
  说明 executor 虽然已经增强，但还不是唯一的浏览器恢复中心；
  不过这层已从“隐式 dict + 本地 helper”进展到“共享 dataclass +
  executor helper”

当前状态应理解为：

- **Phase 1：已落地**
- **Phase 2：已落地**
- **Phase 3：已部分落地，仍需继续压薄 handler**
- **Phase 4：方向已冻结，代码未完全收口**

## 当前 review 结论（2026-04-20）

这轮 code review 没有再发现新的 blocking 安全问题。

已经修复的真实风险：

- failure evidence 的本地路径泄露问题已经被 authoritative projection
  脱敏修复，不再通过用户可见 artifact 暴露服务器文件系统路径

当前主要剩余的是设计悖论，而不是安全 blocker：

1. `browser executor` 的恢复责任已显著增强，但 `nodes_a4.py`
   仍保留一部分 resume/handoff 编排逻辑，职责切面还没有完全纯化
2. A4 已经停止在 API path 里直接计算 `has_brand_mention`，但工具合同上
   仍保留兼容 `brand_profile` seam，说明 A4 还没有完全收成“纯问题抓取”
3. A4 的品牌语义已经大幅收窄，但 downstream knowledge writeback
   仍然消费品牌上下文，说明 A4 与 A5 的边界已经更清晰，但尚未完全收死

共享验证结果：

- `compileall` 通过：
  - `browser_executor.py`
  - `failure_observability.py`
  - `a4_fetch_agent.py`
  - `nodes_a4.py`
- 定向测试通过：
  - `test_nodes_a4_timeouts.py`
  - `test_browser_executor.py`
  - `test_fetch_run_platform_state_service.py`
  - `test_browser_failure_evidence_service.py`
  - `test_a5_generic_report_copy.py`
- 当前合计：`31 passed`

## 当前冻结结论

本文档冻结以下判断：

- A4 是抓取阶段，不是品牌分析阶段
- A4 默认尽量品牌无关
- browser executor 是执行上下文、自动恢复和失败分类的最佳承载点
- platform adapter 只处理平台差异，不再承担“小 orchestrator”角色
- fetch artifact 是唯一用户可见抓取真相源
- human handoff 只处理人类可解决问题
- A5 skill 严禁跨行业硬编码

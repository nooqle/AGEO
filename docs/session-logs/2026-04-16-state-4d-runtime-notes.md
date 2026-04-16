## Context Scope

- 日期：`2026-04-16`
- 主题：围绕 `DeepSeek 空内容`、`knowledge_records 截断`、`WebSocket token 泄露`、`前端状态投影漂移` 的统一状态模型
- 目标：用一套状态坐标同时管理代码问题、运行问题和产品能力缺口

## State 四维

### 1. Authoritative State

- 定义：后端持久化、可回放、可复算的权威状态
- 典型载体：
  - `messages`
  - `analysis_tasks / task_runs`
  - `fetch_run_platform_states`
  - `knowledge_records`
- 本轮问题映射：
  - `knowledge_records.dedupe_key` 超长导致写库失败
  - 权威状态已经存在，但前端没有保真使用（如历史消息时间）

### 2. Runtime State

- 定义：单轮执行中即时变化、用于恢复与治理的运行时状态
- 典型载体：
  - `BrowserEvent.error_type`
  - platform breaker 状态
  - takeover / pending confirmation
  - submit / wait / extract 阶段信号
- 本轮问题映射：
  - `DeepSeek` 的真实问题是“提交未生效或未进入回答态”，不是简单平台不可用
  - `empty_answer` 之前只是文本消息，不是可治理的运行时类型

### 3. Projection State

- 定义：前端把权威状态和运行时状态投射成用户看到的界面状态
- 典型载体：
  - 顶部 badge
  - 输入框 placeholder
  - 等待确认横幅
  - 消息时间戳
- 本轮问题映射：
  - 历史消息在 hydrate 时丢失服务端时间，被本地 `new Date()` 污染
  - 旧确认横幅和旧 browser action state 没在新一轮开始时收口
  - placeholder 退回 brand-seed 文案，说明投影只看了“默认态”，没看当前会话态

### 4. Problem State

- 定义：问题本身的生命周期状态，用于跟踪“已发现 / 已定位 / 已修复 / 已验证 / 已上线”
- 典型载体：
  - `docs/session-logs/*.md`
  - 提交与部署记录
  - 线上验证样本
- 本轮问题映射：
  - 4 个问题不能只按“有没有报错”管理，而要区分：
    - 是否已拿到线上证据
    - 是否已定位根因
    - 是否已做共享层修复
    - 是否已被新样本验证

## 本轮 4 个问题的状态映射

### DeepSeek 提交后空内容

- Authoritative State：
  - `fetch_run_platform_states` 只看到了 `failed/skipped`
- Runtime State：
  - 真实链路是 `提交 -> 51s content_len=0 -> empty_answer`
  - 之前缺少显式 `empty_answer` 类型
- Projection State：
  - 报告层容易把抓取失败误写成品牌缺位
- Problem State：
  - 已定位到“提交确认缺失”这一层
  - 本轮已补：更稳的 submit 确认 + `empty_answer` 显式化
  - 仍需新样本验证

### knowledge_records varchar(255) 截断

- Authoritative State：
  - `dedupe_key` 是写库契约，原先允许被 URL 直接撑爆
- Runtime State：
  - A1/A4 都可能在 write-back 时失败
- Projection State：
  - 用户本轮报告可能成功，但后续“过往资料”能力变差
- Problem State：
  - 已定位并在 `_upsert_record()` 统一收口为稳定短 key

### WebSocket 日志 token 泄露

- Authoritative State：
  - token 不该进入日志，不该作为可回放状态
- Runtime State：
  - WebSocket 连接本身把鉴权 token 放在 query 中，Uvicorn 会记录
- Projection State：
  - 用户无感，但安全风险极高
- Problem State：
  - 已定位为“日志脱敏不够”+“鉴权载体错误”
  - 本轮已改为 `cookie 优先 + query 回退`

### 前端状态投影问题

- Authoritative State：
  - 历史消息有真实 `created_at`
  - task / run 也有真实阶段状态
- Runtime State：
  - 新一轮开始时，本应清掉旧 `pendingConfirmation / browserStates`
- Projection State：
  - 历史消息时间错乱
  - 旧确认横幅残留
  - placeholder 回退
- Problem State：
  - 本轮已修到共享层：
    - hydrate 保留服务端时间
    - `startExecution()` 清理旧等待态
    - placeholder 改由会话态驱动

## 功能 State 能力仍需健全的点

### 1. 缺少“提交已生效”状态

- 当前浏览器抓取只有 `SUBMITTING -> WAITING_RESPONSE`
- 中间少一个明确的 `submission_confirmed`
- 导致 DeepSeek 这类问题只能等 51 秒后才知道没提交成功

### 2. 缺少统一的软失败分类

- `empty_answer / extractor_miss / no_content`
- `rate_limit / verify / user_skipped`
- `platform_down`
- 这些应该是不同的 runtime state，不能继续靠 message 文本猜

### 3. 前端缺少单一投影源

- 现在 badge / placeholder / waiting banner 吃的状态源不完全一致
- 后续最好由统一 selector 从 `activeTask + latest_run + pendingConfirmation + browserStates` 计算 UI state

### 4. 安全状态没有独立建模

- token 是否出现在 query、cookie、日志里，本质上也是状态治理问题
- 这类问题以后不该靠“开发时注意”，而应该靠默认安全载体和脱敏日志策略

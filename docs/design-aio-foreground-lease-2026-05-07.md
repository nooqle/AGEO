# AIO 前台资源仲裁设计与实施说明

> 日期：2026-05-07
> 状态：Draft + Phase 1-4 最小实现
> 范围：A4 浏览器抓取、DeepSeek GUI actions、四平台 CDP 抓取、人工接管。

---

## 1. 先说结论

这次问题的核心不是“Playwright 要不要前台”。

真实情况是：

```text
AIO Runtime 里同时存在两类能力：

1. CDP / Playwright
   - 绑定具体 page 对象
   - 不依赖浏览器前台

2. GUI / VNC actions
   - 对远程桌面发送鼠标键盘
   - 依赖当前浏览器前台
```

目前四个平台的状态是：

| 平台 | 主要操作方式 | 是否应该抢前台 |
| --- | --- | --- |
| 豆包 | CDP / Playwright | 不应该 |
| 元宝 | CDP / Playwright | 不应该 |
| Kimi | CDP / Playwright | 不应该 |
| DeepSeek | 默认 `gui_actions` | 只有 GUI 动作期间需要 |

所以正确设计不是“四个平台排队抓取”，而是：

```text
只有需要远程桌面前台的动作排队。
```

---

## 2. 当前真实设计

## 2.1 AIO session 不是全局前台锁

当前 `AioSandboxSessionManager.acquire_session()` 会按平台传入：

```python
platforms=[self.platform]
```

因此 session scope 实际类似：

```text
workspace::aio-platform::deepseek
workspace::aio-platform::kimi
workspace::aio-platform::doubao
workspace::aio-platform::yuanbao
```

这说明现有 `human_takeover_lock` 是平台 session 维度，不是整个 AIO 浏览器桌面维度。

但真实远程浏览器前台只有一个。

所以不能把现有 `human_takeover_lock` 当成完整前台锁。

## 2.2 四个平台 browser pipeline 是并发的

A4 会把浏览器平台组成多个 pipeline 并发执行：

```text
DeepSeek pipeline
Kimi pipeline
豆包 pipeline
元宝 pipeline
```

每个平台内部按问题串行，但平台之间是并发的。

这意味着如果某个平台切前台，确实可能影响另一个正在做 GUI action 的平台。

## 2.3 只有 DeepSeek 直接调用 AIO GUI action

代码扫描后确认，直接调用 AIO `execute_action()` 的浏览器 handler 只有 DeepSeek。

DeepSeek 会发送：

```text
MOVE_TO
CLICK
HOTKEY
TYPING
PRESS
```

这些是远程桌面级动作，必须保护前台。

Kimi、豆包、元宝主要是：

```text
page.evaluate
locator.click
page.keyboard.press
page.keyboard.type
```

这些是 CDP/Playwright page 级操作，不应该因为自己执行而抢前台。

## 2.4 人工接管已有状态，但缺少前台仲裁

人工接管已有：

```text
create_takeover_access
open_takeover
heartbeat_takeover
resolve_takeover
cancel_takeover
expire_takeover
```

这些能表达用户接管生命周期，但之前没有和 DeepSeek GUI actions 共用同一个“前台资源”。

所以需要补一层：

```text
AIO foreground lease
```

---

## 3. 对原 Phase 1-4 的复核

## Phase 1：先观测

原方向正确，但需要补充真实观测对象。

应该观测的不是“哪个平台在抓取”，而是：

```text
谁在切前台
谁在执行 GUI action
谁在持有人类接管
谁因为前台被占用而等待
```

本轮已增加结构化日志：

```text
foreground_lease_acquired
foreground_lease_waiting
foreground_lease_timeout
foreground_lease_released
```

## Phase 2：收口前台切换

原方向正确，但不能简单删除所有 `bring_to_front`。

修正后规则：

```text
CDP-only 平台普通自动化不主动 bring_to_front
DeepSeek gui_actions 自动化可以 bring_to_front
人工接管准备/打开仍然可以 bring_to_front
```

本轮已将 AIO 自动化页面复用/打开路径改为：

```text
bring_to_front_for_automation()
```

只有平台确实需要 GUI foreground 时才执行，而且这类前台切换也必须先拿到短租约。

## Phase 3：DeepSeek GUI 与人工接管仲裁

原方向基本正确，但“DeepSeek 抓取全程占前台”是不对的。

修正后规则：

```text
DeepSeek 只在点击、输入、回车、联网搜索这些短 GUI 动作期间持有前台 lease。
DeepSeek 页面打开/复用时如果需要切前台，也走同一个短 GUI lease。
等待回答、提取正文、提取引用时不持有。
```

人工接管在 takeover bundle 发出时开始抢占前台 lease：

```text
弹出接管提示前：human_takeover lease 已预留
用户点击打开浏览器：继续刷新 human_takeover lease，并稳定目标页面
用户 heartbeat：刷新 human_takeover lease
用户完成/取消/超时：释放 human_takeover lease
```

这回答了“时机”问题：

```text
不是等用户点击打开浏览器才阻止 DeepSeek。
在后端确定需要人工接管、准备给用户弹提示时，就先预留前台。
```

## Phase 4：验证

原方向正确，但必须覆盖并发语义。

本轮已补：

1. human takeover 等待当前 GUI action 释放。
2. human takeover 持有前台时，DeepSeek GUI action 超时/阻塞。
3. Kimi CDP-only 页面复用不会主动切前台。
4. DeepSeek GUI 模式页面复用会请求前台。
5. 既有 DeepSeek GUI action 测试保持通过。

还未完成：

```text
线上真实 A4 并发 E2E
VNC 人工接管实测
```

这两项需要在部署或本地 AIO runtime 可用时验证。

---

## 4. 本轮实现边界

本轮是最小实现，不做数据库迁移。

新增：

```text
app/services/aio_foreground_lease.py
```

职责：

```text
按 AIO runtime 前台维度管理 lease
支持 gui_automation 和 human_takeover 两种模式
支持 TTL
支持等待、超时、释放
有 Redis 时可用 Redis；无 Redis 时退回进程内锁
```

修改：

```text
AioConnectedBrowserClient
  - 增加 foreground_key
  - 增加 should_request_automation_foreground()
  - 增加 bring_to_front_for_automation()

BaseBrowserHandler
  - AIO surface reuse 不再无条件切前台

DeepSeekHandler
  - GUI submit / search toggle 进入 foreground lease

browser_action_contract
  - AIO takeover bundle 发出时预留 human_takeover foreground lease
  - takeover 超时时释放 foreground lease

api/v1/aio
  - create/open/heartbeat/resolve/cancel takeover 同步 foreground lease
```

---

## 5. 现在这套机制如何工作

## 5.1 DeepSeek 正在 GUI 输入

```text
DeepSeek 请求 gui_automation lease
获得前台
bring_to_front 到 DeepSeek 页
执行 CLICK / TYPING / PRESS
释放前台
```

## 5.2 Kimi 普通 CDP 抓取同时运行

```text
Kimi 执行 page.evaluate / keyboard / locator
不请求 foreground lease
不 bring_to_front
不干扰 DeepSeek GUI
```

## 5.3 Kimi 需要人工接管

```text
Kimi 检测到登录/验证
后端创建 takeover bundle
请求 human_takeover lease
如果 DeepSeek 当前正在短 GUI action，等待它释放
human_takeover lease 获得后，再给用户发接管提示
DeepSeek 后续 GUI action 会等待或超时，不再抢前台
```

## 5.4 用户点击打开浏览器

```text
open_takeover
刷新 human_takeover lease
stabilize_browser_surface(exclusive=True)
把目标页面稳定到接管视图
```

## 5.5 用户完成接管

```text
resolve_takeover / cancel_takeover / timeout
释放 human_takeover lease
DeepSeek GUI action 后续可以重新申请
```

---

## 6. 风险与后续

## 6.1 Redis 风险

本轮 foreground lease 支持 Redis，也支持进程内 fallback。

如果生产是多 worker 且没有 Redis，跨 worker 的前台锁不能完全保证。

因此上线前需要确认：

```text
生产是否单 backend worker
或 REDIS_URL 是否可用
```

## 6.2 人工接管长时间占用风险

人工接管会阻止新的 DeepSeek GUI action。

这是符合优先级的，但如果用户长时间不处理，DeepSeek pipeline 可能等待到自己的 A4 超时。

这不是本轮新问题，而是人工接管和并发抓取本身的业务取舍。

后续可以把 DeepSeek GUI action 在 human takeover 存在时从“等待”改成“明确暂停并在接管完成后恢复”。

## 6.3 真实 E2E 仍必须做

单元测试证明了仲裁语义，但不能替代真实浏览器验证。

上线前或上线后需要跑：

```text
DeepSeek + Kimi 并发抓取
DeepSeek GUI + 豆包/元宝 CDP 并发抓取
人工接管触发后 DeepSeek 不抢前台
人工接管完成后 DeepSeek 可以继续
```

---

## 7. 当前结论

这次不是“又加一个锁”。

这次做的是把真实的共享资源明确出来：

```text
AIO 远程浏览器前台
```

然后让只有两类行为进入仲裁：

```text
DeepSeek GUI 自动动作
人工接管
```

CDP-only 平台不进入队列，也不再为普通自动化抢前台。

这样设计才和 AIO 的真实运行方式一致。

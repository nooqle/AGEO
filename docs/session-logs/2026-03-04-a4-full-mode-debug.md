# Session Log: A4 Full Mode Browser Fetch Failure

**Date**: 2026-03-04 (跨两个 session)
**Topic**: A4 节点 Full 模式下 4 平台浏览器采集全部失败 (0/52)

## Session Summary

调查 A4 Full 模式在 uvicorn 环境下 0% 成功率的问题。经过多轮错误方向的排查后，最终通过时间戳取证法定位到根因：`launch_persistent_context()` 失败，但 Kimi/Yuanbao handler 未检查 `open()` 返回值。

## Key Findings

### 根因链
1. `PlaywrightBrowserClient.open()` 内部 `launch_persistent_context()` 抛异常（具体异常类型待 `err_detail` 修复后确认）
2. `open()` 返回 `{"success": False, "error": "..."}`
3. **DeepSeek handler 检查了返回值** → 立即报错 "浏览器打开失败:" (0.0s)
4. **Kimi/Yuanbao handler 未检查返回值** → `self.client.page` 保持 None → 后续所有操作静默跳过 → 空等 60s → "未能提取到有效回答"
5. Doubao 需要登录 → 90s 超时（预期行为）

### 关键证据 (a4_debug.log)
```
# DeepSeek: 0.0s 失败
[11:10:45.034337] deepseek event: error (0.0s)
deepseek ERROR event: 浏览器打开失败:    ← 错误信息为空（err_detail 修复前）

# Kimi: 三个事件共享同一微秒时间戳 = page is None
[11:10:49.052430] kimi event: checking_login (4.0s)
[11:10:49.052430] kimi event: enabling_search (4.0s)   ← 同一微秒！
[11:10:49.052430] kimi event: submitting (4.0s)         ← 同一微秒！
[11:10:49.052927] kimi event: waiting_response (4.0s)   ← 仅差 0.5ms
```
如果 `_detect_login_needed()` 真正执行了 `await page.evaluate()`，时间戳不可能相同。

### 代码对比
```python
# DeepSeek (deepseek_handler.py:88-96) — 检查返回值 ✅
open_result = await self.client.open(self.URL, headed=False)
if not open_result.get("success"):
    yield error event; return

# Kimi (kimi_handler.py:155-157) — 未检查返回值 ❌
await self.client.open(self.URL, headed=self.headed)
await asyncio.sleep(4)
```

## Wrong Hypotheses (已排除)
1. ❌ 共享 patchright subprocess — 每个 client 独立 subprocess (已读源码确认)
2. ❌ async generator finally 调用 close() — handler 无 finally 块 (grep 确认)
3. ❌ zombie chrome 锁定 session 目录 — 独立测试在 22 zombie 下全部成功
4. ❌ atexit/signal handlers — 不存在
5. ❌ SPA 未加载完导致选择器失效 — 真实原因是 page 根本是 None

## Pending Fix
- [ ] Kimi/Yuanbao handler 加 `open()` 返回值检查（fail-fast）
- [ ] 排查 `launch_persistent_context()` 在 uvicorn 下失败的具体异常（需要 `err_detail` 日志）
- [ ] 清理 `playwright_client.py:close()` 中的 traceback 诊断代码
- [ ] 考虑 open() 失败时清理中间状态 + 重试机制

## Critical File References
- `nodes_a4.py:525-575` — handler 创建和 client 初始化
- `nodes_a4.py:703-773` — browser pipeline 执行
- `playwright_client.py:59-111` — open() 方法
- `kimi_handler.py:92-291` — fetch() 完整流程
- `deepseek_handler.py:64-213` — fetch() 完整流程（有返回值检查）
- `a4_debug.log` — 完整 130 行诊断日志

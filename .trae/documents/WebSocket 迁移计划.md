# WebSocket 迁移计划

## 目标
将 Socket.IO 迁移到 FastAPI 原生 WebSocket，解决生产环境部署问题。

## 实施步骤

### 步骤 1: 创建 WebSocket 后端模块 (4-6小时)
- 创建 `app/core/websocket_server.py`
- 复用 SocketIOManager 类管理连接
- 实现 3 个事件处理函数: user_message, confirmation, stop
- 保持所有 20+ 种事件的发送逻辑

### 步骤 2: 更新 FastAPI 主应用 (1小时)
- 修改 `app/main.py`
- 挂载 WebSocket 路由 `/ws/{session_id}`
- 移除 Socket.IO 相关代码

### 步骤 3: 更新前端 WebSocket Hook (3-4小时)
- 修改 `src/hooks/useWebSocket.ts`
- 将 socket.io-client 替换为原生 WebSocket
- 实现自动重连和心跳机制
- 保持所有事件监听逻辑不变

### 步骤 4: 测试验证 (2-3小时)
- 功能测试: 连接、消息、TPAOR、进度等
- 性能测试: 并发、吞吐量、内存

## 关键设计
- **事件格式**: `{"event": "event_name", "data": {...}}`
- **WebSocket URL**: `ws://localhost:8000/ws/{session_id}`
- **心跳间隔**: 30秒
- **重连策略**: 指数退避，最多5次

## 风险应对
- 消息丢失: 实现消息确认机制
- 重连风暴: 指数退避策略
- 内存泄漏: 定期清理断开连接
- 兼容性问题: 保持事件格式一致

## 回滚方案
如迁移失败，可快速回滚到 Socket.IO 版本。

## 时间安排
总计: 10-14 小时

---

**请确认后开始实施。**
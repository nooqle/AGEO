# WebSocket 迁移计划文档

## 项目概述
将 Socket.IO 迁移到 FastAPI 原生 WebSocket，解决生产环境部署问题。

---

## 一、现状分析

### 1.1 后端架构
- **框架**: FastAPI + Socket.IO (python-socketio 5.11.0)
- **问题**: Socket.IO 事件处理程序无法触发，调试困难
- **文件**: `app/core/socketio_server.py` (337 行)

### 1.2 前端架构
- **框架**: Next.js 16 + Socket.IO Client (4.8.3)
- **Hook**: `src/hooks/useWebSocket.ts` (377 行)
- **Store**: Zustand 管理状态

### 1.3 核心功能
- 用户消息处理 → GeneralReActAgent → 实时 TPAOR 推送
- 20+ 种 WebSocket 事件类型
- Session 管理和多连接支持

---

## 二、迁移目标

### 2.1 保持兼容
- ✅ 所有事件名称不变
- ✅ 数据格式不变
- ✅ 前端 API 不变
- ✅ 业务逻辑不变

### 2.2 提升稳定性
- ✅ 使用 FastAPI 原生 WebSocket
- ✅ 更好的生产环境支持
- ✅ 更简单的部署配置

---

## 三、详细实施计划

### 步骤 1: 创建 WebSocket 后端模块

**文件**: `app/core/websocket_server.py`

#### 3.1.1 复用 SocketIOManager
```python
class ConnectionManager:
    """管理 WebSocket 连接（复用现有逻辑）"""
    
    def __init__(self):
        # session_id -> Set[WebSocket]
        self.session_connections: dict[str, set[WebSocket]] = {}
        # WebSocket -> session_id
        self.ws_to_session: dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """注册连接"""
        await websocket.accept()
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        self.session_connections[session_id].add(websocket)
        self.ws_to_session[websocket] = session_id
    
    def disconnect(self, websocket: WebSocket):
        """注销连接"""
        session_id = self.ws_to_session.pop(websocket, None)
        if session_id and session_id in self.session_connections:
            self.session_connections[session_id].discard(websocket)
            if not self.session_connections[session_id]:
                del self.session_connections[session_id]
    
    async def emit_to_session(self, session_id: str, event: str, data: dict):
        """向 session 中的所有连接发送消息"""
        if session_id in self.session_connections:
            disconnected = []
            for ws in self.session_connections[session_id]:
                try:
                    await ws.send_json({"event": event, "data": data})
                except Exception:
                    disconnected.append(ws)
            # 清理断开的连接
            for ws in disconnected:
                self.disconnect(ws)
```

#### 3.1.2 WebSocket 路由处理
```python
@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 连接处理"""
    await manager.connect(websocket, session_id)
    
    try:
        while True:
            # 接收消息
            message = await websocket.receive_json()
            event = message.get("event")
            data = message.get("data", {})
            
            # 路由到对应处理函数
            if event == "user_message":
                await handle_user_message(websocket, session_id, data)
            elif event == "confirmation":
                await handle_confirmation(websocket, session_id, data)
            elif event == "stop":
                await handle_stop(websocket, session_id)
            elif event == "ping":
                await websocket.send_json({"event": "pong", "data": {}})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
```

#### 3.1.3 业务逻辑迁移
将 `socketio_server.py` 中的以下函数迁移：
- `user_message` → `handle_user_message()`
- `confirmation` → `handle_confirmation()`
- `stop` → `handle_stop()`

保持所有 `emit` 调用改为 `manager.emit_to_session()`

---

### 步骤 2: 更新 FastAPI 主应用

**文件**: `app/main.py`

#### 3.2.1 修改内容
```python
from fastapi import FastAPI
from app.core.websocket_server import router as ws_router

app = FastAPI(...)

# 挂载 WebSocket 路由
app.include_router(ws_router)

# 移除 Socket.IO 相关代码
# from app.core.socketio_server import sio
# socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
# app = socket_app
```

---

### 步骤 3: 更新前端 WebSocket Hook

**文件**: `src/hooks/useWebSocket.ts`

#### 3.3.1 替换 Socket.IO 为原生 WebSocket
```typescript
export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const maxReconnectAttempts = 5;
  
  useEffect(() => {
    if (!sessionId) return;
    
    const connect = () => {
      const ws = new WebSocket(`${WS_URL}/ws/${sessionId}`);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('[WebSocket] Connected');
        reconnectCountRef.current = 0;
      };
      
      ws.onmessage = (event) => {
        const { event: eventName, data } = JSON.parse(event.data);
        // 保持现有的事件处理逻辑
        handleEvent(eventName, data);
      };
      
      ws.onclose = () => {
        console.log('[WebSocket] Disconnected');
        // 自动重连
        if (reconnectCountRef.current < maxReconnectAttempts) {
          setTimeout(() => {
            reconnectCountRef.current++;
            connect();
          }, 1000 * reconnectCountRef.current);
        }
      };
      
      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
      };
    };
    
    connect();
    
    // 心跳
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ event: 'ping', data: {} }));
      }
    }, 30000);
    
    return () => {
      clearInterval(heartbeat);
      wsRef.current?.close();
    };
  }, [sessionId]);
  
  // 发送方法
  const sendMessage = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        event: 'user_message',
        data: { content }
      }));
    }
  }, []);
  
  // ... 其他发送方法
}
```

#### 3.3.2 保持事件处理不变
所有 `socket.on('event_name', handler)` 改为在 `handleEvent` 函数中处理：
```typescript
const handleEvent = (eventName: string, data: any) => {
  switch (eventName) {
    case 'agent_start':
      startExecution();
      break;
    case 'tpaor_update':
      updateTPAOR({...});
      break;
    // ... 其他 20+ 个事件
  }
};
```

---

### 步骤 4: 测试验证

#### 3.4.1 功能测试清单
- [ ] WebSocket 连接/断开
- [ ] 用户消息发送
- [ ] TPAOR 实时更新
- [ ] Agent 执行进度
- [ ] 执行计划显示
- [ ] Agent 调用事件
- [ ] 错误处理
- [ ] 自动重连
- [ ] 心跳机制

#### 3.4.2 性能测试
- [ ] 并发连接测试
- [ ] 消息吞吐量
- [ ] 内存泄漏检查

---

## 四、风险与应对

| 风险 | 可能性 | 影响 | 应对措施 |
|-----|-------|------|---------|
| 消息丢失 | 低 | 高 | 实现消息确认机制 |
| 重连风暴 | 中 | 中 | 指数退避重连策略 |
| 内存泄漏 | 低 | 高 | 定期清理断开的连接 |
| 兼容性问题 | 低 | 高 | 保持事件格式完全一致 |

---

## 五、时间安排

| 步骤 | 预计时间 | 依赖 |
|-----|---------|------|
| 步骤 1: 后端模块 | 4-6 小时 | 无 |
| 步骤 2: FastAPI 更新 | 1 小时 | 步骤 1 |
| 步骤 3: 前端更新 | 3-4 小时 | 步骤 2 |
| 步骤 4: 测试验证 | 2-3 小时 | 步骤 3 |
| **总计** | **10-14 小时** | - |

---

## 六、回滚计划

如果迁移失败，可以快速回滚：
1. 恢复 `app/main.py` 中的 Socket.IO 代码
2. 恢复前端 `useWebSocket.ts` 使用 Socket.IO
3. 重启服务

---

## 七、确认事项

实施前请确认：
- [ ] 计划内容符合预期
- [ ] 时间安排可接受
- [ ] 风险应对措施认可

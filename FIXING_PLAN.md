# Specta AI 问题修复行动计划

**创建日期**: 2026-02-04
**基于**: CODE_REVIEW_REPORT.md

---

## 修复优先级矩阵

| 优先级 | 问题数量 | 预估工作量 | 开始时间 |
|--------|----------|-----------|---------|
| P0 安全问题 | 5个 | 2-3天 | 立即 |
| P0 工作流问题 | 3个 | 1-2天 | 立即 |
| P1 功能问题 | 11个 | 3-5天 | 1周内 |
| P2 质量问题 | 多个 | 持续 | 2周内开始 |

---

## 第一阶段：P0 安全问题修复（立即执行）

### 任务 1.1: 实现认证授权机制

**问题编号**: 2.1
**优先级**: P0 - Critical
**预估时间**: 1.5天

**实施步骤**:

1. **创建用户模型和认证模块**
   ```bash
   # 创建文件
   touch aeo-platform/backend/app/models/user.py
   touch aeo-platform/backend/app/core/auth.py
   touch aeo-platform/backend/app/core/security.py
   ```

2. **实现 JWT token 验证**
   - 安装依赖: `pip install python-jose[cryptography] passlib[bcrypt]`
   - 实现 token 生成和验证函数
   - 创建认证依赖函数

3. **更新数据库模型**
   - 添加 User 模型
   - 在 Session 模型中添加 user_id 外键
   - 创建数据库迁移: `alembic revision --autogenerate -m "add user model"`

4. **更新所有 API 端点**
   - 添加 `current_user: str = Depends(get_current_user)` 依赖
   - 添加会话所有权验证逻辑

5. **测试**
   - 测试未认证访问被拒绝
   - 测试用户只能访问自己的会话
   - 测试 token 过期处理

**文件清单**:
- `app/models/user.py` (新建)
- `app/core/auth.py` (新建)
- `app/core/security.py` (新建)
- `app/api/v1/sessions.py` (修改)
- `app/api/v1/messages.py` (修改)
- `app/api/v1/outputs.py` (修改)
- `app/api/v1/websocket_langgraph.py` (修改)

---

### 任务 1.2: 修复 CORS 配置

**问题编号**: 2.2
**优先级**: P0 - Critical
**预估时间**: 0.5天

**实施步骤**:

1. **更新环境变量配置**
   ```bash
   # .env.local.example
   ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
   ```

2. **修改 main.py**
   ```python
   ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

   app.add_middleware(
       CORSMiddleware,
       allow_origins=ALLOWED_ORIGINS,
       allow_credentials=True,
       allow_methods=["GET", "POST", "PUT", "DELETE"],
       allow_headers=["*"],
   )
   ```

3. **测试**
   - 测试允许的来源可以访问
   - 测试不允许的来源被拒绝

**文件清单**:
- `app/main.py` (修改)
- `.env.local.example` (修改)

---

### 任务 1.3: 修复文件导出路径遍历漏洞

**问题编号**: 2.4
**优先级**: P0 - Critical
**预估时间**: 0.5天

**实施步骤**:

1. **添加输出类型白名单**
   ```python
   ALLOWED_OUTPUT_TYPES = {"report", "metrics", "questions", "answers"}
   ```

2. **实现路径验证**
   ```python
   from pathlib import Path

   def validate_output_path(session_id: str, output_type: str) -> Path:
       if output_type not in ALLOWED_OUTPUT_TYPES:
           raise HTTPException(status_code=400, detail="Invalid output type")

       base_dir = Path(settings.OUTPUT_DIR)
       file_path = (base_dir / session_id / f"{output_type}.json").resolve()

       if not str(file_path).startswith(str(base_dir.resolve())):
           raise HTTPException(status_code=400, detail="Invalid path")

       return file_path
   ```

3. **更新导出端点**
   - 使用验证函数
   - 添加文件存在性检查

4. **测试**
   - 测试正常导出
   - 测试路径遍历攻击被阻止

**文件清单**:
- `app/api/v1/outputs.py` (修改)
- `app/core/config.py` (添加 OUTPUT_DIR 配置)

---

### 任务 1.4: 添加 WebSocket 认证

**问题编号**: 2.5
**优先级**: P0 - Critical
**预估时间**: 0.5天

**实施步骤**:

1. **实现 WebSocket token 验证**
   ```python
   @router.websocket("/ws/{session_id}")
   async def websocket_endpoint(
       websocket: WebSocket,
       session_id: str,
       token: str = Query(...)
   ):
       # 验证 token
       user_id = verify_token(token)
       if not user_id:
           await websocket.close(code=1008, reason="Unauthorized")
           return

       # 验证会话所有权
       # ...
   ```

2. **更新前端 WebSocket 连接**
   ```typescript
   // 在连接 URL 中添加 token
   const token = getAuthToken();
   const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/${sessionId}?token=${token}`);
   ```

3. **测试**
   - 测试无 token 连接被拒绝
   - 测试无效 token 被拒绝
   - 测试用户只能连接自己的会话

**文件清单**:
- `app/api/v1/websocket_langgraph.py` (修改)
- `frontend/src/hooks/useWebSocket.ts` (修改)

---

### 任务 1.5: 前端 WebSocket 消息验证

**问题编号**: 3.1
**优先级**: P0 - Critical
**预估时间**: 0.5天

**实施步骤**:

1. **添加消息验证函数**
   ```typescript
   function validateMessage(message: unknown): message is WebSocketMessage {
     return (
       typeof message === 'object' &&
       message !== null &&
       'event' in message &&
       typeof (message as any).event === 'string' &&
       'data' in message
     );
   }
   ```

2. **更新消息处理逻辑**
   ```typescript
   ws.onmessage = (event) => {
     try {
       const message = JSON.parse(event.data);
       if (!validateMessage(message)) {
         console.error('[WebSocket] Invalid message format:', message);
         return;
       }
       handleEvent(message.event, message.data);
     } catch (error) {
       console.error('[WebSocket] Error parsing message:', error);
     }
   };
   ```

3. **测试**
   - 测试正常消息处理
   - 测试格式错误消息被拒绝
   - 测试应用不会因错误消息崩溃

**文件清单**:
- `frontend/src/hooks/useWebSocket.ts` (修改)
- `frontend/src/types/websocket.ts` (新建或修改)

---

## 第二阶段：P0 工作流问题修复（立即执行）

### 任务 2.1: 修复工作流节点名称不匹配

**问题编号**: 1.1
**优先级**: P0 - Critical
**预估时间**: 0.5天

**实施步骤**:

1. **统一节点名称**
   ```python
   # nodes.py 中修改所有 Command(goto=...)
   return Command(goto="a2_decision")  # 而非 "a2_decision_node"
   return Command(goto="a2_persona")   # 而非 "a2_persona_node"
   return Command(goto="a3_question")  # 而非 "a3_question_node"
   return Command(goto="a4_fetch")     # 而非 "a4_fetch_node"
   return Command(goto="a5_analytics") # 而非 "a5_analytics_node"
   ```

2. **验证所有节点引用**
   ```bash
   # 搜索所有 goto 引用
   grep -r "goto=" aeo-platform/backend/app/workflow/
   ```

3. **测试**
   - 测试完整工作流执行
   - 测试所有分支路径

**文件清单**:
- `app/workflow/nodes.py` (修改)
- `app/workflow/nodes_a3.py` (修改)
- `app/workflow/nodes_a4.py` (修改)
- `app/workflow/nodes_a5.py` (修改)

---

### 任务 2.2: 修复 A2 跳过逻辑

**问题编号**: 1.2
**优先级**: P0 - Critical
**预估时间**: 0.5天

**实施步骤**:

1. **实现条件路由函数**
   ```python
   # graph.py
   def route_a2_decision(state: AgentState) -> str:
       """Route after A2 decision: skip to A3 or continue to A2 persona"""
       user_decisions = state.get("user_decisions", {})
       if user_decisions.get("skip_a2"):
           return "a3_question"
       return "a2_persona"
   ```

2. **更新图定义**
   ```python
   # 移除固定边
   # workflow.add_edge("a2_decision", "a2_persona")

   # 添加条件边
   workflow.add_conditional_edges(
       "a2_decision",
       route_a2_decision,
       {
           "a2_persona": "a2_persona",
           "a3_question": "a3_question"
       }
   )
   ```

3. **测试**
   - 测试选择继续 A2 的路径
   - 测试选择跳过 A2 的路径

**文件清单**:
- `app/workflow/graph.py` (修改)

---

### 任务 2.3: 修复工作流状态管理

**问题编号**: 1.3
**优先级**: P0 - Critical
**预估时间**: 1天

**实施步骤**:

1. **实现单例模式**
   ```python
   # graph.py
   _compiled_workflow = None
   _workflow_lock = asyncio.Lock()

   async def get_compiled_workflow():
       global _compiled_workflow
       if _compiled_workflow is None:
           async with _workflow_lock:
               if _compiled_workflow is None:
                   workflow = build_workflow()
                   checkpointer = MemorySaver()
                   _compiled_workflow = workflow.compile(checkpointer=checkpointer)
       return _compiled_workflow
   ```

2. **更新 WebSocket 处理**
   ```python
   # websocket_langgraph.py
   workflow = await get_compiled_workflow()  # 使用 await
   ```

3. **考虑使用持久化 checkpointer**
   - 评估是否需要使用数据库存储检查点
   - 如果需要，实现 PostgresCheckpointer

4. **测试**
   - 测试 Human-in-Loop 暂停和恢复
   - 测试多个会话并发执行
   - 测试状态持久化

**文件清单**:
- `app/workflow/graph.py` (修改)
- `app/api/v1/websocket_langgraph.py` (修改)
- `app/workflow/checkpoint.py` (可能需要修改)

---

## 第三阶段：P1 功能问题修复（1周内）

### 任务 3.1: 修复 Agent 节点错误处理

**问题编号**: 1.4, 1.5
**优先级**: P1
**预估时间**: 1天

**实施步骤**:

1. **修复变量作用域问题**
   ```python
   # nodes_a4.py
   fetch_results = []
   try:
       # ... 现有代码
   except Exception as e:
       # fetch_results 始终可用
   ```

2. **添加错误日志和通知**
   ```python
   # nodes.py A2
   except Exception as e:
       logger.error(f"A2 persona generation error: {e}", exc_info=True)
       await send_error_event(session_id, "A2", str(e), recoverable=True)
       return Command(
           goto="a3_decision",
           update={"error_info": {"stage": "A2", "error": str(e)}}
       )
   ```

3. **测试**
   - 测试各节点的错误处理
   - 验证错误信息正确记录和显示

**文件清单**:
- `app/workflow/nodes.py` (修改)
- `app/workflow/nodes_a3.py` (修改)
- `app/workflow/nodes_a4.py` (修改)

---

### 任务 3.2: 添加 LLM 超时和重试机制

**问题编号**: 1.6
**优先级**: P1
**预估时间**: 1天

**实施步骤**:

1. **安装依赖**
   ```bash
   pip install tenacity
   ```

2. **实现重试装饰器**
   ```python
   # core/llm_utils.py (新建)
   import asyncio
   from tenacity import retry, stop_after_attempt, wait_exponential

   @retry(
       stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=2, max=10)
   )
   async def call_llm_with_retry(model, messages, timeout=60):
       return await asyncio.wait_for(
           asyncio.to_thread(model, messages=messages),
           timeout=timeout
       )
   ```

3. **更新所有 LLM 调用**
   ```python
   # 替换
   response = model(messages=[...])
   # 为
   response = await call_llm_with_retry(model, messages=[...])
   ```

4. **测试**
   - 测试正常调用
   - 测试超时处理
   - 测试重试机制

**文件清单**:
- `app/core/llm_utils.py` (新建)
- `app/workflow/nodes.py` (修改)
- `app/workflow/nodes_a3.py` (修改)
- `app/workflow/nodes_a5.py` (修改)

---

### 任务 3.3: 修复 Alembic 迁移调用

**问题编号**: 1.7
**优先级**: P1
**预估时间**: 0.5天

**实施步骤**:

1. **更新迁移函数**
   ```python
   # checkpoint.py
   async def setup_checkpoint_tables():
       import asyncio
       from alembic import command
       from alembic.config import Config

       def run_migration():
           alembic_cfg = Config(alembic_ini)
           command.upgrade(alembic_cfg, "head")  # 使用 "head"

       try:
           await asyncio.to_thread(run_migration)
           logger.info("Checkpoint tables setup completed")
       except Exception as e:
           logger.error(f"Migration failed: {e}")
           raise
   ```

2. **测试**
   - 测试迁移执行
   - 测试错误处理

**文件清单**:
- `app/workflow/checkpoint.py` (修改)

---

### 任务 3.4: 完善 WebSocket 事件处理

**问题编号**: 1.8
**优先级**: P1
**预估时间**: 0.5天

**实施步骤**:

1. **添加异常处理**
   ```python
   # events.py
   async def send_progress_event(...) -> None:
       try:
           await manager.emit_to_session(session_id, "execution_progress", {...})
       except Exception as e:
           logger.warning(f"Failed to send progress event to {session_id}: {e}")
           # 继续执行，不中断工作流
   ```

2. **应用到所有事件函数**

3. **测试**
   - 测试 WebSocket 断开时工作流继续执行

**文件清单**:
- `app/workflow/events.py` (修改)

---

### 任务 3.5: 改进 JSON 解析错误信息

**问题编号**: 1.9
**优先级**: P1
**预估时间**: 0.5天

**实施步骤**:

1. **更新错误信息**
   ```python
   if not data:
       raise ValueError(
           f"Failed to parse LLM response as JSON. "
           f"Raw content: {response.content[:500]}"
       )
   if "brand_profile" not in data:
       raise ValueError(
           f"Missing 'brand_profile' in LLM response. "
           f"Keys found: {list(data.keys())}"
       )
   ```

2. **应用到所有节点**

**文件清单**:
- `app/workflow/nodes.py` (修改)
- `app/workflow/nodes_a3.py` (修改)

---

### 任务 3.6: 实现或删除占位符服务

**问题编号**: 2.6
**优先级**: P1
**预估时间**: 1天

**实施步骤**:

1. **评估是否需要这些服务**
   - 如果需要，实现完整功能
   - 如果不需要，删除文件并直接在 API 层操作数据库

2. **如果删除**:
   ```bash
   rm aeo-platform/backend/app/services/session_service.py
   rm aeo-platform/backend/app/services/output_service.py
   ```

3. **更新 API 端点**
   - 直接使用数据库操作

**文件清单**:
- `app/services/session_service.py` (删除或实现)
- `app/services/output_service.py` (删除或实现)
- `app/api/v1/sessions.py` (可能需要修改)
- `app/api/v1/outputs.py` (可能需要修改)

---

### 任务 3.7: 完善 MessageService.rollback

**问题编号**: 2.7
**优先级**: P1
**预估时间**: 1天

**实施步骤**:

1. **实现完整回滚逻辑**
   ```python
   async def rollback(self, session_id: str, to_message_id: str):
       # 1. 删除消息
       # 2. 清理相关输出
       # 3. 回滚 Agent 状态
       # 4. 清理检查点
   ```

2. **测试**
   - 测试回滚功能
   - 验证状态一致性

**文件清单**:
- `app/services/message_service.py` (修改)

---

### 任务 3.8: 添加 WebSocket 清理机制

**问题编号**: 2.8
**优先级**: P1
**预估时间**: 1天

**实施步骤**:

1. **实现心跳检测**
   ```python
   # websocket_manager.py
   async def heartbeat_task(self):
       while True:
           await asyncio.sleep(30)
           # 检查所有连接
           # 清理断开的连接
   ```

2. **启动后台任务**

3. **测试**
   - 测试连接自动清理

**文件清单**:
- `app/services/websocket_manager.py` (修改)

---

### 任务 3.9: 清理废弃代码

**问题编号**: 2.9
**优先级**: P1
**预估时间**: 0.5天

**实施步骤**:

1. **删除废弃文件**
   ```bash
   rm aeo-platform/backend/app/api/v1/chat.py
   rm aeo-platform/backend/app/agents/orchestrator.py
   ```

2. **更新导入引用**

3. **测试**
   - 确保应用正常运行

**文件清单**:
- `app/api/v1/chat.py` (删除)
- `app/agents/orchestrator.py` (删除)

---

### 任务 3.10: 修复前端 WebSocket 重连逻辑

**问题编号**: 3.2
**优先级**: P1
**预估时间**: 0.5天

**实施步骤**:

1. **确保旧连接关闭**
   ```typescript
   const reconnect = () => {
     if (wsRef.current) {
       wsRef.current.close();
       wsRef.current = null;
     }
     // 重新连接
   };
   ```

2. **测试**
   - 测试重连不会创建多个连接

**文件清单**:
- `frontend/src/hooks/useWebSocket.ts` (修改)

---

### 任务 3.11: 实现乐观更新

**问题编号**: 3.3
**优先级**: P1
**预估时间**: 1天

**实施步骤**:

1. **实现乐观更新模式**
   ```typescript
   // stores/conversationStore.ts
   const sendMessage = async (message: string) => {
     // 1. 立即更新 UI
     const tempMessage = { id: 'temp', content: message, ... };
     addMessage(tempMessage);

     try {
       // 2. 发送到服务器
       const response = await api.sendMessage(message);
       // 3. 更新为真实数据
       updateMessage('temp', response);
     } catch (error) {
       // 4. 失败时回滚
       removeMessage('temp');
       showError(error);
     }
   };
   ```

2. **测试**
   - 测试成功场景
   - 测试失败回滚

**文件清单**:
- `frontend/src/stores/conversationStore.ts` (修改)

---

### 任务 3.12: 统一错误处理

**问题编号**: 3.4
**优先级**: P1
**预估时间**: 1天

**实施步骤**:

1. **创建全局错误处理**
   ```typescript
   // components/ErrorBoundary.tsx
   // hooks/useErrorHandler.ts
   ```

2. **统一错误显示**
   - 使用 toast 通知
   - 统一错误格式

3. **测试**
   - 测试各种错误场景

**文件清单**:
- `frontend/src/components/ErrorBoundary.tsx` (新建)
- `frontend/src/hooks/useErrorHandler.ts` (新建)

---

## 第四阶段：P2 质量问题改进（2周内开始）

### 任务 4.1: 性能优化

- 添加 React.memo
- 实现虚拟滚动
- 优化数据库查询
- 添加缓存

### 任务 4.2: 完善文档

- API 文档
- 架构文档
- 部署文档

### 任务 4.3: 改进用户体验

- 完善 loading 状态
- 改进错误提示
- 移动端适配
- 无障碍访问

### 任务 4.4: 代码质量

- 统一代码风格
- 添加单元测试
- 添加集成测试
- 提高测试覆盖率

---

## 验证清单

### 安全验证
- [ ] 未认证用户无法访问 API
- [ ] 用户只能访问自己的会话
- [ ] CORS 配置正确
- [ ] 文件导出路径遍历防护有效
- [ ] WebSocket 连接需要认证

### 功能验证
- [ ] 工作流正常执行（A1-A5）
- [ ] Human-in-Loop 确认和恢复正常
- [ ] A2 跳过功能正常
- [ ] 错误处理和重试机制有效
- [ ] WebSocket 实时通信正常

### 性能验证
- [ ] LLM 调用有超时限制
- [ ] WebSocket 连接自动清理
- [ ] 前端渲染性能良好
- [ ] 数据库查询优化

### 代码质量验证
- [ ] 运行 `black .` 和 `isort .`（后端）
- [ ] 运行 `ruff check .`（后端）
- [ ] 运行 `npm run lint`（前端）
- [ ] 运行测试套件

---

## 进度跟踪

| 阶段 | 任务数 | 已完成 | 进行中 | 待开始 | 完成率 |
|------|--------|--------|--------|--------|--------|
| 第一阶段 (P0 安全) | 5 | 0 | 0 | 5 | 0% |
| 第二阶段 (P0 工作流) | 3 | 0 | 0 | 3 | 0% |
| 第三阶段 (P1 功能) | 12 | 0 | 0 | 12 | 0% |
| 第四阶段 (P2 质量) | 4 | 0 | 0 | 4 | 0% |
| **总计** | **24** | **0** | **0** | **24** | **0%** |

---

## 下一步行动

1. **立即开始**: 第一阶段 P0 安全问题修复
2. **并行执行**: 第二阶段 P0 工作流问题修复
3. **计划安排**: 第三阶段 P1 功能问题修复
4. **持续改进**: 第四阶段 P2 质量问题改进

**建议**: 先完成所有 P0 问题修复，确保系统基本可用和安全，然后再处理 P1 和 P2 问题。

---

**创建日期**: 2026-02-04
**最后更新**: 2026-02-04
**状态**: 待开始
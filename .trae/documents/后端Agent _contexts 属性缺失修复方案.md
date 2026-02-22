## 问题分析

### 错误信息
```
GeneralReActAgent' object has no attribute '_contexts'
```

### 根本原因

1. **代码结构问题**：
   - `socketio_server.py` 第193行直接访问 `agent._contexts.get(session_id)`
   - 但旧版 `GeneralReActAgent` (general_react.py) 使用的是 `_session_states` 而非 `_contexts`
   - 新版 `GeneralReActAgent` (general_react_v2.py) 才使用 `_contexts`

2. **环境变量配置**：
   - `get_general_react_agent()` 函数根据 `USE_LLM_ORCHESTRATION` 环境变量决定使用哪个版本
   - 当前环境变量未设置或设置为 `false`，导致使用旧版 Agent
   - 旧版 Agent 没有 `_contexts` 属性

### 修复方案

#### 方案1：统一使用新版 Agent（推荐）

**修改文件**：`app/agents/general_react.py`

```python
def get_general_react_agent():
    """获取 GeneralReActAgent 实例。"""
    # 强制使用新版 LLM 编排
    from app.agents.general_react_v2 import GeneralReActAgent as AgentV2
    return AgentV2()
```

**影响评估**：
- ✅ 立即解决问题
- ✅ 使用 LLM 驱动的动态编排，更智能
- ⚠️ 需要确保 `general_react_v2.py` 的所有依赖都已正确配置
- ⚠️ 可能需要调整 LLM Orchestrator 的配置

#### 方案2：修改 socketio_server 兼容旧版

**修改文件**：`app/core/socketio_server.py` 第193行

```python
# 获取 context 时兼容新旧版本
try:
    context = agent._contexts.get(session_id)
except AttributeError:
    # 旧版 Agent 使用 _session_states
    context = None
```

**影响评估**：
- ✅ 向后兼容
- ⚠️ 旧版 Agent 的功能可能不完整
- ⚠️ 代码复杂度增加

#### 方案3：设置环境变量

**修改文件**：`.env` 或启动脚本

```bash
USE_LLM_ORCHESTRATION=true
```

**影响评估**：
- ✅ 无需修改代码
- ⚠️ 需要确保所有环境都正确配置
- ⚠️ 如果环境变量被覆盖，问题会复发

### 推荐实施方案

**采用方案1**，原因：
1. 新版 Agent 是项目的发展方向（LLM 驱动编排）
2. 前端已经按照新版 Agent 的事件格式开发
3. 旧版 Agent 的 `_session_states` 和 `_contexts` 数据结构不同，强行兼容会增加技术债务

### 修复步骤

1. 修改 `app/agents/general_react.py` 中的 `get_general_react_agent()` 函数
2. 重启后端服务
3. 重新测试端到端流程

### 风险评估

| 风险项 | 概率 | 影响 | 缓解措施 |
|--------|------|------|----------|
| LLM Orchestrator 依赖缺失 | 中 | 高 | 检查 `llm_orchestrator.py` 的依赖 |
| Agent Registry 未正确注册 | 低 | 中 | 确认 `register_all_agents()` 正常执行 |
| ExecutionContext Schema 不匹配 | 低 | 高 | 检查 `app/schemas/orchestration.py` |

请确认此方案，确认后我将立即执行修复。
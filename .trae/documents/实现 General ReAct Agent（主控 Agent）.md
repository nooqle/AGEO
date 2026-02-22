## 执行计划

### Step 1: 创建 Pipeline 状态 Schema
**文件**: `backend/app/schemas/pipeline.py`

定义 Pydantic Schema：
- `PipelinePhase` - Pipeline 阶段枚举
- `PipelineState` - Pipeline 执行状态
- `ExecutionPlan` - 执行计划
- `PlanStep` - 计划步骤
- `AgentEvent` - Agent 事件
- `PipelineContext` - Pipeline 上下文

### Step 2: 创建 Pipeline 服务
**文件**: `backend/app/services/pipeline_service.py`

实现 Pipeline 管理服务：
- `PipelineService` 类
- `create_pipeline()` - 创建 Pipeline
- `execute_step()` - 执行步骤
- `get_pipeline_status()` - 获取状态
- `update_pipeline_state()` - 更新状态
- Pipeline 模板（full_analysis, quick_analysis, incremental_update）

### Step 3: 实现 GeneralReActAgent
**文件**: `backend/app/agents/general_react.py`

实现主控 Agent：
- `GeneralReActAgent` 类，继承 `AEOAgentBase`
- `agent_id = "A0"`
- 注册功能 Agent 为工具：
  - `analyze_brand` → BrandCompetitionAgent (A1)
  - `generate_personas` → MarketingPersonaAgent (A2)
  - `simulate_questions` → QuestionSimulationAgent (A3)
  - `fetch_answers` → FetchAgent (A4+A5)
  - `analyze_data` → DataAnalyticsAgent (A6)
- `handle_user_message()` - 处理用户消息
- `execute_baseline_analysis()` - 执行基准分析 Pipeline
- `execute_persona_analysis()` - 执行画像分析 Pipeline
- TPAOR 框架实现

### Step 4: 创建系统提示词
**文件**: `backend/prompts/general_react_agent.md`

包含：
- Agent 角色定义（AEO 智能协调中枢）
- 核心职责说明
- TPAOR 执行框架详解
- 可调度的 Agent 清单
- Pipeline 模板库
- 意图识别与 Pipeline 选择逻辑
- 上下文管理规范
- 完整交互示例

### 关键设计

**Agent 注册为工具**：
```python
TOOLS = {
    "analyze_brand": BrandCompetitionAgent,      # A1
    "generate_personas": MarketingPersonaAgent,  # A2
    "simulate_questions": QuestionSimulationAgent,  # A3
    "fetch_answers": FetchAgent,                 # A4+A5 统一
    "analyze_data": DataAnalyticsAgent,          # A6
}
```

**Pipeline 类型**：
1. **Full Analysis** - 完整品牌 AEO 分析
2. **Quick Analysis** - 快速问题分析
3. **Incremental Update** - 增量数据更新
4. **Single Task** - 单项任务执行

**TPAOR 框架**：
- Thought - 思考用户意图和当前状态
- Plan - 制定执行计划
- Action - 调用 Agent 执行任务
- Observation - 观察执行结果
- Response - 向用户回复

请确认此计划后，我将开始执行具体的代码实现。
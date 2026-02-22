# LLM 驱动流程编排架构设计文档

> **版本**: v1.0
> **日期**: 2026-01-30
> **状态**: 设计评审中

---

## 1. 设计目标

### 1.1 核心目标

将 Specta AI 平台的流程编排从 **硬编码模式** 改为 **LLM 驱动的自主决策模式**，使 General ReAct Agent (A0) 能够：

1. **理解用户意图**: 通过 LLM 分析用户输入，识别真实需求
2. **动态规划流程**: 根据上下文自主决定执行哪些 Agent、以什么顺序执行
3. **灵活调整**: 根据执行结果和用户反馈动态调整后续计划
4. **智能确认**: 自主判断何时需要用户确认，而非固定确认点

### 1.2 设计原则

- **渐进式重构**: 保持向后兼容，逐步迁移
- **最小侵入**: 尽量复用现有代码，减少修改范围
- **可测试性**: 新架构易于单元测试和集成测试
- **可观测性**: 保持完整的执行日志和状态追踪

---

## 2. 当前架构问题分析

### 2.1 问题 1: 硬编码的执行阶段

```python
# 当前: general_react.py
class ExecutionPhase(Enum):
    IDLE = "idle"
    A1_BRAND_ANALYSIS = "a1_brand_analysis"
    A1_CONFIRMATION = "a1_confirmation"
    A2_PERSONA_GENERATION = "a2_persona_generation"
    # ... 固定的阶段枚举
```

**问题**: 阶段是预定义的，无法动态添加或跳过。

### 2.2 问题 2: 硬编码的动作处理

```python
# 当前: general_react.py
if action == "start_full_analysis":
    async for event in self._start_full_analysis(session_id, brand_name):
        yield event
elif action == "continue_from_a1":
    async for event in self._continue_to_a2(session_id):
        yield event
# ... 每个动作都有专门的处理方法
```

**问题**: 新增动作需要修改代码，LLM 只能选择预定义动作。

### 2.3 问题 3: 固定的确认点

```python
# 当前: A1 完成后固定要求确认
yield AgentEvent(
    output_type="confirmation",
    output_data={
        "options": [
            {"id": "continue", "label": "继续 - 生成用户画像"},
            {"id": "skip", "label": "跳过 - 直接生成问题"},
        ],
    },
)
```

**问题**: 确认点位置固定，无法根据上下文决定是否需要确认。

### 2.4 问题 4: PipelineService 与 GeneralReActAgent 职责重叠

| 职责 | PipelineService | GeneralReActAgent |
|------|-----------------|-------------------|
| 流程定义 | TEMPLATES 静态模板 | ExecutionPhase 枚举 |
| 状态管理 | PipelineContext | _session_states |
| 步骤执行 | get_next_executable_steps | _continue_to_a2/a3/a4/a5 |

**问题**: 两个组件都在做流程编排，逻辑分散。

---

## 3. 新架构设计

### 3.1 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户输入                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   GeneralReActAgent (A0)                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                  LLM Orchestration Engine                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │  │
│  │  │ Intent      │  │ Plan        │  │ Execution       │   │  │
│  │  │ Analyzer    │→ │ Generator   │→ │ Controller      │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Agent Registry                         │  │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                │  │
│  │  │ A1  │ │ A2  │ │ A3  │ │ A4  │ │ A5  │                │  │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                  Execution Context                        │  │
│  │  (状态管理、历史记录、中间结果)                            │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    WebSocket 实时推送                            │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 核心组件设计

#### 3.2.1 Agent Registry (Agent 注册表)

**职责**: 管理所有可用 Agent 的能力描述，供 LLM 决策使用。

```python
# 新增: app/agents/registry.py

from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class AgentCapability:
    """Agent 能力描述"""
    agent_id: str
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema
    output_schema: dict[str, Any]  # JSON Schema
    estimated_duration: str
    prerequisites: list[str]  # 依赖的数据字段
    produces: list[str]  # 产出的数据字段
    can_skip: bool  # 是否可跳过
    requires_confirmation: bool  # 默认是否需要确认


class AgentRegistry:
    """Agent 注册表"""

    _agents: dict[str, AgentCapability] = {}
    _instances: dict[str, Any] = {}

    @classmethod
    def register(cls, capability: AgentCapability, instance: Any):
        """注册 Agent"""
        cls._agents[capability.agent_id] = capability
        cls._instances[capability.agent_id] = instance

    @classmethod
    def get_capability(cls, agent_id: str) -> AgentCapability | None:
        """获取 Agent 能力描述"""
        return cls._agents.get(agent_id)

    @classmethod
    def get_instance(cls, agent_id: str) -> Any | None:
        """获取 Agent 实例"""
        return cls._instances.get(agent_id)

    @classmethod
    def get_all_capabilities(cls) -> list[AgentCapability]:
        """获取所有 Agent 能力描述"""
        return list(cls._agents.values())

    @classmethod
    def get_capabilities_for_llm(cls) -> str:
        """生成供 LLM 使用的能力描述文本"""
        lines = ["## 可用 Agent 列表\n"]
        for cap in cls._agents.values():
            lines.append(f"### {cap.agent_id}: {cap.name}")
            lines.append(f"- 描述: {cap.description}")
            lines.append(f"- 预估耗时: {cap.estimated_duration}")
            lines.append(f"- 前置条件: {', '.join(cap.prerequisites) or '无'}")
            lines.append(f"- 产出数据: {', '.join(cap.produces)}")
            lines.append(f"- 可跳过: {'是' if cap.can_skip else '否'}")
            lines.append("")
        return "\n".join(lines)
```

#### 3.2.2 Agent 能力描述示例

```python
# 在各 Agent 文件中注册能力

# A1: BrandCompetitionAgent
A1_CAPABILITY = AgentCapability(
    agent_id="A1",
    name="品牌竞品分析",
    description="收集品牌基础信息、核心产品、行业定位，并识别8-12个主要竞品",
    input_schema={
        "type": "object",
        "properties": {
            "brand_name": {"type": "string", "description": "品牌名称"},
            "official_website": {"type": "string", "description": "官网URL（可选）"},
            "industry_hint": {"type": "string", "description": "行业提示（可选）"},
        },
        "required": ["brand_name"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "brand_profile": {"type": "object"},
            "competitors": {"type": "array"},
        }
    },
    estimated_duration="30-45秒",
    prerequisites=[],  # 无前置条件
    produces=["brand_profile", "competitors"],
    can_skip=False,  # 必须执行
    requires_confirmation=True,  # 默认需要确认
)

# A2: MarketingPersonaAgent
A2_CAPABILITY = AgentCapability(
    agent_id="A2",
    name="用户画像生成",
    description="基于品牌和竞品信息生成6-8个差异化用户画像",
    input_schema={
        "type": "object",
        "properties": {
            "brand_profile": {"type": "object"},
            "competitors": {"type": "array"},
        },
        "required": ["brand_profile", "competitors"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "personas": {"type": "array"},
        }
    },
    estimated_duration="25-35秒",
    prerequisites=["brand_profile", "competitors"],
    produces=["personas"],
    can_skip=True,  # 可跳过
    requires_confirmation=False,  # 默认不需要确认
)

# A3: QuestionSimulationAgent
A3_CAPABILITY = AgentCapability(
    agent_id="A3",
    name="问题模拟生成",
    description="生成用户可能向AI助手询问的模拟问题",
    input_schema={
        "type": "object",
        "properties": {
            "brand_profile": {"type": "object"},
            "competitors": {"type": "array"},
            "personas": {"type": "array", "description": "可选，有则生成画像问题"},
            "mode": {"type": "string", "enum": ["baseline", "persona_focus"]},
        },
        "required": ["brand_profile", "competitors"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "questions": {"type": "array"},
        }
    },
    estimated_duration="20-30秒",
    prerequisites=["brand_profile", "competitors"],
    produces=["questions"],
    can_skip=False,
    requires_confirmation=True,  # 问题生成后需要确认
)

# A4: FetchAgent
A4_CAPABILITY = AgentCapability(
    agent_id="A4",
    name="AI答案抓取",
    description="将问题提交到豆包、混元、Kimi、DeepSeek等平台，收集AI回答",
    input_schema={
        "type": "object",
        "properties": {
            "questions": {"type": "array"},
            "platforms": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["questions"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "fetch_results": {"type": "array"},
        }
    },
    estimated_duration="3-8分钟",
    prerequisites=["questions"],
    produces=["fetch_results"],
    can_skip=False,
    requires_confirmation=True,  # 耗时长，需要确认
)

# A5: DataAnalyticsAgent
A5_CAPABILITY = AgentCapability(
    agent_id="A5",
    name="数据分析报告",
    description="计算BWVS、提及率、情感分布等指标，生成分析报告",
    input_schema={
        "type": "object",
        "properties": {
            "fetch_results": {"type": "array"},
            "brand_profile": {"type": "object"},
            "competitors": {"type": "array"},
        },
        "required": ["fetch_results", "brand_profile", "competitors"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "metrics": {"type": "object"},
            "report": {"type": "object"},
        }
    },
    estimated_duration="60-90秒",
    prerequisites=["fetch_results", "brand_profile", "competitors"],
    produces=["metrics", "report"],
    can_skip=False,
    requires_confirmation=False,  # 最后一步，不需要确认
)
```

#### 3.2.3 LLM 决策输出格式

**LLM 需要输出结构化的决策，包括下一步行动和执行计划。**

```python
# 新增: app/schemas/orchestration.py

from pydantic import BaseModel
from typing import Literal

class AgentCall(BaseModel):
    """单个 Agent 调用"""
    agent_id: str
    input_params: dict[str, Any]
    skip_confirmation: bool = False
    reason: str  # 为什么调用这个 Agent


class ExecutionPlanStep(BaseModel):
    """执行计划步骤"""
    step_number: int
    agent_id: str
    description: str
    depends_on: list[int] = []  # 依赖的步骤编号
    can_parallel: bool = False
    estimated_duration: str


class LLMDecision(BaseModel):
    """LLM 决策输出"""

    # 意图分析
    user_intent: str  # 用户意图描述
    intent_type: Literal[
        "start_analysis",      # 开始新分析
        "continue_execution",  # 继续执行
        "modify_plan",         # 修改计划
        "ask_question",        # 用户提问
        "provide_info",        # 用户提供信息
        "confirm_action",      # 用户确认
        "cancel_action",       # 用户取消
        "help_request",        # 请求帮助
        "unknown",             # 无法识别
    ]

    # 下一步行动
    next_action: Literal[
        "call_agent",          # 调用 Agent
        "ask_confirmation",    # 请求确认
        "respond_to_user",     # 回复用户
        "wait_for_input",      # 等待输入
        "complete",            # 完成
    ]

    # Agent 调用（如果 next_action == "call_agent"）
    agent_call: AgentCall | None = None

    # 执行计划（如果是新任务）
    execution_plan: list[ExecutionPlanStep] | None = None

    # 用户回复（如果 next_action == "respond_to_user"）
    response_message: str | None = None

    # 确认请求（如果 next_action == "ask_confirmation"）
    confirmation_request: dict | None = None

    # 决策理由
    reasoning: str
```

#### 3.2.4 LLM Orchestration Engine

**核心编排引擎，负责调用 LLM 进行决策并执行。**

```python
# 新增: app/agents/llm_orchestrator.py

class LLMOrchestrationEngine:
    """LLM 驱动的编排引擎"""

    def __init__(self, model):
        self.model = model
        self.registry = AgentRegistry

    async def decide_next_action(
        self,
        user_message: str,
        context: ExecutionContext,
    ) -> LLMDecision:
        """使用 LLM 决定下一步行动"""

        prompt = self._build_decision_prompt(user_message, context)

        response = self.model([
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": prompt}
        ])

        return self._parse_decision(response.content)

    def _get_system_prompt(self) -> str:
        """获取系统 prompt"""
        return f"""你是 Specta AI 的智能编排引擎，负责根据用户输入和当前状态决定下一步行动。

{self.registry.get_capabilities_for_llm()}

## 决策规则

1. **意图识别**: 首先分析用户的真实意图
2. **上下文感知**: 考虑当前执行状态和已有数据
3. **动态规划**: 根据意图生成或调整执行计划
4. **智能确认**: 只在必要时请求用户确认
   - 耗时较长的操作（如 A4 抓取）
   - 可能产生费用的操作
   - 用户明确要求确认时
5. **错误处理**: 遇到错误时提供替代方案

## 输出格式

请以 JSON 格式输出决策，包含以下字段：
- user_intent: 用户意图描述
- intent_type: 意图类型
- next_action: 下一步行动
- agent_call: Agent 调用信息（如果需要）
- execution_plan: 执行计划（如果是新任务）
- response_message: 回复消息（如果需要）
- confirmation_request: 确认请求（如果需要）
- reasoning: 决策理由
"""

    def _build_decision_prompt(
        self,
        user_message: str,
        context: ExecutionContext,
    ) -> str:
        """构建决策 prompt"""
        return f"""## 当前状态

- 会话ID: {context.session_id}
- 执行状态: {context.execution_status}
- 当前步骤: {context.current_step}
- 已完成步骤: {context.completed_steps}

## 已有数据

{self._format_available_data(context)}

## 对话历史

{self._format_conversation_history(context)}

## 用户输入

"{user_message}"

## 请决定下一步行动

请分析用户意图，并决定：
1. 是否需要调用 Agent？调用哪个？
2. 是否需要用户确认？
3. 如何回复用户？

请以 JSON 格式输出决策。"""

    async def execute_agent(
        self,
        agent_call: AgentCall,
        context: ExecutionContext,
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行 Agent 调用"""

        agent = self.registry.get_instance(agent_call.agent_id)
        capability = self.registry.get_capability(agent_call.agent_id)

        if not agent or not capability:
            yield AgentEvent(
                event_id="evt_error",
                tpaor_phase="观察",
                message=f"未找到 Agent: {agent_call.agent_id}",
                execution_status="failed",
            )
            return

        # 发送开始事件
        yield AgentEvent(
            event_id=f"evt_{agent_call.agent_id}_start",
            tpaor_phase="行动",
            message=f"正在执行 {capability.name}...",
            action_type="call_agent",
            target_agent=agent_call.agent_id,
        )

        try:
            # 执行 Agent
            result = await self._run_agent(agent, agent_call.input_params)

            # 更新上下文
            if result.get("success"):
                for key in capability.produces:
                    if key in result.get("output", {}):
                        context.data[key] = result["output"][key]

            # 发送完成事件
            yield AgentEvent(
                event_id=f"evt_{agent_call.agent_id}_complete",
                tpaor_phase="观察",
                message=f"{capability.name} 完成",
                execution_status="success" if result.get("success") else "failed",
            )

        except Exception as e:
            yield AgentEvent(
                event_id=f"evt_{agent_call.agent_id}_error",
                tpaor_phase="观察",
                message=f"{capability.name} 执行失败: {str(e)}",
                execution_status="failed",
            )
```

#### 3.2.5 Execution Context (执行上下文)

```python
# 修改: app/schemas/pipeline.py 或新增

class ExecutionContext(BaseModel):
    """执行上下文 - 统一的状态管理"""

    session_id: str

    # 执行状态
    execution_status: Literal["idle", "running", "paused", "completed", "failed"]
    current_step: int = 0
    completed_steps: list[str] = []

    # 数据存储 - 动态存储各 Agent 的输出
    data: dict[str, Any] = {}
    # 例如:
    # - brand_name: str
    # - brand_profile: dict
    # - competitors: list[dict]
    # - personas: list[dict]
    # - questions: list[dict]
    # - fetch_results: list[dict]
    # - metrics: dict
    # - report: dict

    # 执行计划
    execution_plan: list[ExecutionPlanStep] = []

    # 对话历史
    conversation_history: list[dict] = []

    # 用户配置
    user_preferences: dict[str, Any] = {}

    def has_data(self, key: str) -> bool:
        """检查是否有某项数据"""
        return key in self.data and self.data[key] is not None

    def get_available_data_keys(self) -> list[str]:
        """获取所有可用数据的键"""
        return [k for k, v in self.data.items() if v is not None]

    def can_execute_agent(self, capability: AgentCapability) -> bool:
        """检查是否满足执行某 Agent 的前置条件"""
        return all(self.has_data(prereq) for prereq in capability.prerequisites)
```

---

## 4. 重构后的 GeneralReActAgent

### 4.1 简化后的主入口

```python
# 重构: app/agents/general_react.py

class GeneralReActAgent(SpectaAgentBase):
    """General ReAct Agent - LLM 驱动的主控 Agent"""

    def __init__(self):
        super().__init__()
        self.orchestrator = LLMOrchestrationEngine(self.model)
        self._contexts: dict[str, ExecutionContext] = {}

    async def handle_user_message(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """处理用户消息 - 简化后的主入口"""

        if not session_id:
            session_id = "default"

        context = self._get_or_create_context(session_id)

        # 添加用户消息到历史
        context.conversation_history.append({
            "role": "user",
            "content": message,
        })

        # ========== 思考阶段 ==========
        yield AgentEvent(
            event_id="evt_thinking",
            tpaor_phase="思考",
            message="让我理解一下您的需求...",
            progress=0.1,
        )

        # 使用 LLM 决策
        decision = await self.orchestrator.decide_next_action(message, context)

        yield AgentEvent(
            event_id="evt_thinking_complete",
            tpaor_phase="思考",
            message=f"我理解了，您想要{decision.user_intent}。",
            progress=0.15,
        )

        # ========== 根据决策执行 ==========
        async for event in self._execute_decision(decision, context):
            yield event

    async def _execute_decision(
        self,
        decision: LLMDecision,
        context: ExecutionContext,
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行 LLM 决策"""

        if decision.next_action == "call_agent":
            # 调用 Agent
            if decision.agent_call:
                async for event in self.orchestrator.execute_agent(
                    decision.agent_call, context
                ):
                    yield event

                # Agent 执行完成后，继续决策下一步
                # （递归调用，直到不需要调用 Agent）
                next_decision = await self.orchestrator.decide_next_action(
                    "[Agent 执行完成，请决定下一步]", context
                )
                async for event in self._execute_decision(next_decision, context):
                    yield event

        elif decision.next_action == "ask_confirmation":
            # 请求用户确认
            yield AgentEvent(
                event_id="evt_confirmation",
                tpaor_phase="回复",
                message=decision.response_message or "请确认是否继续？",
                output_ready=True,
                output_type="confirmation",
                output_data=decision.confirmation_request,
            )

        elif decision.next_action == "respond_to_user":
            # 回复用户
            yield AgentEvent(
                event_id="evt_response",
                tpaor_phase="回复",
                message=decision.response_message or "",
                progress=1.0,
            )

        elif decision.next_action == "complete":
            # 完成
            yield AgentEvent(
                event_id="evt_complete",
                tpaor_phase="回复",
                message=decision.response_message or "任务已完成！",
                progress=1.0,
                output_ready=True,
                output_type="report",
                output_data=context.data.get("report"),
            )
```

### 4.2 对比：重构前 vs 重构后

| 方面 | 重构前 | 重构后 |
|------|--------|--------|
| 代码行数 | ~1100 行 | ~200 行 |
| 硬编码方法 | 10+ 个 (_start_full_analysis, _continue_to_a2, ...) | 2 个 (handle_user_message, _execute_decision) |
| 流程定义 | ExecutionPhase 枚举 | LLM 动态生成 |
| 动作处理 | if-elif 链 | 统一的 execute_agent |
| 确认点 | 固定位置 | LLM 动态决定 |
| 扩展性 | 需要修改代码 | 只需注册新 Agent |

---

## 5. 影响范围评估

### 5.1 需要修改的文件

#### 高优先级（核心重构）

| 文件 | 修改内容 | 工作量 | 风险 |
|------|---------|--------|------|
| `general_react.py` | 重写主逻辑，移除硬编码方法 | 高 | 中 |
| `prompts/general_react_agent.md` | 重写 prompt，添加动态编排指令 | 中 | 低 |

#### 中优先级（新增文件）

| 文件 | 内容 | 工作量 | 风险 |
|------|------|--------|------|
| `agents/registry.py` | Agent 注册表 | 中 | 低 |
| `agents/llm_orchestrator.py` | LLM 编排引擎 | 高 | 中 |
| `schemas/orchestration.py` | 新增 schema | 低 | 低 |

#### 低优先级（适配修改）

| 文件 | 修改内容 | 工作量 | 风险 |
|------|---------|--------|------|
| `socketio_server.py` | 适配新事件格式 | 低 | 低 |
| `agent_orchestrator.py` | 适配新编排逻辑 | 低 | 低 |
| `pipeline_service.py` | 简化为纯状态管理 | 中 | 低 |
| 各 Agent 文件 (A1-A5) | 添加能力描述注册 | 低 | 低 |

### 5.2 不需要修改的文件

- **所有 schema 文件**: 数据结构保持不变
- **专业 Agent 的核心逻辑**: A1-A5 的执行逻辑不变
- **utils.py**: 工具函数库保持不变
- **其他 prompt 文件**: A1-A5 的 prompt 保持不变
- **前端代码**: WebSocket 事件格式兼容

### 5.3 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| LLM 决策不稳定 | 中 | 高 | 添加 fallback 逻辑，保留硬编码路径 |
| 性能下降 | 低 | 中 | LLM 调用缓存，批量决策 |
| 回归问题 | 中 | 中 | 完善测试用例，渐进式迁移 |
| Prompt 调优困难 | 中 | 中 | 建立 prompt 版本管理，A/B 测试 |

---

## 6. 实施计划

### 6.1 阶段一：基础设施（1-2 天）

**目标**: 搭建新架构的基础组件

**任务**:
1. 创建 `agents/registry.py` - Agent 注册表
2. 创建 `schemas/orchestration.py` - 新增 schema
3. 为 A1-A5 添加能力描述

**验收标准**:
- Agent 注册表可以正确返回所有 Agent 的能力描述
- 能力描述格式正确，可供 LLM 使用

### 6.2 阶段二：编排引擎（2-3 天）

**目标**: 实现 LLM 编排引擎

**任务**:
1. 创建 `agents/llm_orchestrator.py`
2. 实现 `decide_next_action` 方法
3. 实现 `execute_agent` 方法
4. 编写单元测试

**验收标准**:
- LLM 能正确识别用户意图
- LLM 能生成合理的执行计划
- Agent 调用正常工作

### 6.3 阶段三：主控 Agent 重构（2-3 天）

**目标**: 重构 GeneralReActAgent

**任务**:
1. 简化 `handle_user_message` 方法
2. 移除硬编码的 `_continue_to_*` 方法
3. 保留旧逻辑作为 fallback
4. 编写集成测试

**验收标准**:
- 新逻辑能完成完整分析流程
- 用户确认正常工作
- 错误处理正常

### 6.4 阶段四：Prompt 优化（1-2 天）

**目标**: 优化 LLM prompt

**任务**:
1. 重写 `general_react_agent.md`
2. 添加更多示例
3. 调优决策准确性
4. A/B 测试

**验收标准**:
- 意图识别准确率 > 95%
- 执行计划合理性 > 90%
- 用户体验无明显下降

### 6.5 阶段五：清理和文档（1 天）

**目标**: 清理旧代码，完善文档

**任务**:
1. 移除不再使用的代码
2. 简化 `pipeline_service.py`
3. 更新 API 文档
4. 更新 CLAUDE.md

**验收标准**:
- 代码整洁，无冗余
- 文档完整准确

---

## 7. 测试策略

### 7.1 单元测试

```python
# tests/test_llm_orchestrator.py

class TestLLMOrchestrator:

    async def test_intent_recognition_start_analysis(self):
        """测试意图识别 - 开始分析"""
        engine = LLMOrchestrationEngine(mock_model)
        context = ExecutionContext(session_id="test")

        decision = await engine.decide_next_action(
            "帮我分析一下观夏这个品牌", context
        )

        assert decision.intent_type == "start_analysis"
        assert decision.next_action == "call_agent"
        assert decision.agent_call.agent_id == "A1"

    async def test_intent_recognition_continue(self):
        """测试意图识别 - 继续执行"""
        engine = LLMOrchestrationEngine(mock_model)
        context = ExecutionContext(
            session_id="test",
            data={"brand_profile": {...}, "competitors": [...]},
        )

        decision = await engine.decide_next_action("继续", context)

        assert decision.intent_type == "continue_execution"

    async def test_agent_prerequisite_check(self):
        """测试 Agent 前置条件检查"""
        context = ExecutionContext(session_id="test")

        # A2 需要 brand_profile 和 competitors
        assert not context.can_execute_agent(A2_CAPABILITY)

        context.data["brand_profile"] = {...}
        context.data["competitors"] = [...]

        assert context.can_execute_agent(A2_CAPABILITY)
```

### 7.2 集成测试

```python
# tests/test_general_react_integration.py

class TestGeneralReActIntegration:

    async def test_full_analysis_flow(self):
        """测试完整分析流程"""
        agent = GeneralReActAgent()
        events = []

        async for event in agent.handle_user_message(
            "分析一下小米", "test_session"
        ):
            events.append(event)

        # 验证事件序列
        phases = [e.tpaor_phase for e in events]
        assert "思考" in phases
        assert "规划" in phases
        assert "行动" in phases
        assert "观察" in phases
        assert "回复" in phases

    async def test_skip_persona_flow(self):
        """测试跳过画像流程"""
        agent = GeneralReActAgent()

        # 先执行 A1
        async for _ in agent.handle_user_message("分析观夏", "test"):
            pass

        # 跳过 A2
        events = []
        async for event in agent.handle_user_message("跳过画像", "test"):
            events.append(event)

        # 验证直接执行 A3
        agent_calls = [e for e in events if e.target_agent]
        assert any(e.target_agent == "A3" for e in agent_calls)
```

---

## 8. 回滚方案

如果新架构出现严重问题，可以快速回滚：

### 8.1 保留旧代码

```python
# general_react.py

class GeneralReActAgent:

    def __init__(self):
        self.use_llm_orchestration = os.getenv("USE_LLM_ORCHESTRATION", "true") == "true"
        if self.use_llm_orchestration:
            self.orchestrator = LLMOrchestrationEngine(self.model)

    async def handle_user_message(self, message, session_id):
        if self.use_llm_orchestration:
            # 新逻辑
            async for event in self._handle_with_llm(message, session_id):
                yield event
        else:
            # 旧逻辑（保留）
            async for event in self._handle_legacy(message, session_id):
                yield event
```

### 8.2 环境变量控制

```bash
# 启用新架构
USE_LLM_ORCHESTRATION=true

# 回滚到旧架构
USE_LLM_ORCHESTRATION=false
```

---

## 9. 总结

### 9.1 预期收益

1. **灵活性提升**: LLM 可以根据用户意图动态调整流程
2. **代码简化**: 移除大量硬编码逻辑，代码量减少 80%
3. **扩展性增强**: 新增 Agent 只需注册，无需修改编排逻辑
4. **用户体验优化**: 更自然的对话交互，智能确认点

### 9.2 工作量估算

| 阶段 | 工作量 |
|------|--------|
| 阶段一：基础设施 | 1-2 天 |
| 阶段二：编排引擎 | 2-3 天 |
| 阶段三：主控重构 | 2-3 天 |
| 阶段四：Prompt 优化 | 1-2 天 |
| 阶段五：清理文档 | 1 天 |
| **总计** | **7-11 天** |

### 9.3 文件变更清单

**新增文件** (3 个):
- `app/agents/registry.py`
- `app/agents/llm_orchestrator.py`
- `app/schemas/orchestration.py`

**修改文件** (7 个):
- `app/agents/general_react.py` - 核心重构
- `app/agents/brand_competition.py` - 添加能力注册
- `app/agents/marketing_persona.py` - 添加能力注册
- `app/agents/question_simulation.py` - 添加能力注册
- `app/agents/fetch_agent.py` - 添加能力注册
- `app/agents/data_analytics.py` - 添加能力注册
- `prompts/general_react_agent.md` - 重写 prompt

**可选修改** (3 个):
- `app/services/pipeline_service.py` - 简化
- `app/core/socketio_server.py` - 适配
- `app/services/agent_orchestrator.py` - 适配

---

## 10. 前端适配设计

### 10.1 适配概述

前端适配工作量：**低到中等**

| 类别 | 工作量 | 说明 |
|------|--------|------|
| 必须修改 | 1 天 | 类型定义扩展 |
| 可选增强 | 2-3 天 | 新增组件和事件处理 |
| 无需修改 | - | 大部分现有组件已支持新架构 |

**关键优势**：
- `ProgressIndicator` 和 `TPAORCard` 已支持动态内容
- Zustand store 易于扩展
- TypeScript 类型定义完整
- 新增字段不影响现有逻辑

### 10.2 需要新增的类型定义

**新增文件**: `frontend/src/types/orchestration.ts`

```typescript
/** LLM 决策输出 */
export interface LLMDecision {
  user_intent: string
  intent_type:
    | 'start_analysis'
    | 'continue_execution'
    | 'modify_plan'
    | 'ask_question'
    | 'provide_info'
    | 'confirm_action'
    | 'cancel_action'
    | 'help_request'
    | 'unknown'

  next_action:
    | 'call_agent'
    | 'ask_confirmation'
    | 'respond_to_user'
    | 'wait_for_input'
    | 'complete'

  agent_call?: AgentCall
  execution_plan?: ExecutionPlanStep[]
  response_message?: string
  confirmation_request?: any
  reasoning: string
}

/** Agent 调用信息 */
export interface AgentCall {
  agent_id: string
  agent_name?: string
  input_params: Record<string, any>
  skip_confirmation?: boolean
  reason: string
}

/** 执行计划步骤 */
export interface ExecutionPlanStep {
  step_number: number
  agent_id: string
  description: string
  depends_on?: number[]
  can_parallel?: boolean
  estimated_duration: string
  status?: 'pending' | 'running' | 'completed' | 'failed'
}

/** Agent 能力描述 */
export interface AgentCapability {
  agent_id: string
  name: string
  description: string
  estimated_duration: string
  prerequisites: string[]
  produces: string[]
  can_skip: boolean
  requires_confirmation: boolean
}
```

### 10.3 需要扩展的现有类型

**扩展 `Message` 类型** (`frontend/src/types/message.ts`):

```typescript
export interface Message {
  // ... 现有字段 ...

  // 🆕 新增字段（可选）
  execution_plan?: ExecutionPlanStep[]  // 执行计划
  llm_decision?: LLMDecision            // LLM 决策
  intent_type?: string                  // 用户意图类型
  reasoning?: string                    // 决策理由（调试用）
}
```

**扩展 `ExecutionProgress` 类型** (`frontend/src/types/agent.ts`):

```typescript
export interface ExecutionProgress {
  // ... 现有字段 ...

  // 🆕 新增字段（可选）
  execution_plan?: ExecutionPlanStep[]  // 完整执行计划
  current_agent?: AgentCall             // 当前执行的 Agent
  available_agents?: AgentCapability[]  // 可用 Agent 列表
}
```

### 10.4 状态管理扩展

**修改文件**: `frontend/src/stores/conversationStore.ts`

```typescript
interface ConversationState {
  // ... 现有状态 ...

  // 🆕 新增状态
  executionPlan: ExecutionPlanStep[] | null
  contextData: Record<string, any>  // 存储 brand_profile, competitors 等
  decisionHistory: LLMDecision[]    // 可选，调试用
  currentIntent: string | null
}

// 新增 actions
setExecutionPlan: (plan: ExecutionPlanStep[] | null) => void
updateContextData: (key: string, value: any) => void
addDecision: (decision: LLMDecision) => void
setCurrentIntent: (intent: string | null) => void
```

### 10.5 WebSocket 事件处理扩展

**修改文件**: `frontend/src/hooks/useWebSocket.ts`

**可能新增的事件**:

| 事件名称 | 用途 | 数据结构 |
|---------|------|---------|
| `llm_decision` | LLM 决策结果 | `LLMDecision` |
| `plan_updated` | 执行计划更新 | `{ plan: ExecutionPlanStep[], reason: string }` |
| `agent_call_start` | Agent 调用开始 | `AgentCall` |
| `agent_call_complete` | Agent 调用完成 | `{ agent_id, success, output, duration }` |
| `context_updated` | 上下文数据更新 | `{ data_keys: string[], available_agents: string[] }` |

**实现示例**:

```typescript
// 新增事件监听
socket.on('llm_decision', (data: LLMDecision) => {
  addDecision(data)
  setCurrentIntent(data.user_intent)
})

socket.on('plan_updated', (data) => {
  setExecutionPlan(data.plan)
})

socket.on('agent_call_start', (data: AgentCall) => {
  // 更新当前执行的 Agent
})

socket.on('agent_call_complete', (data) => {
  // 更新 Agent 执行结果
})
```

### 10.6 可选新增组件

#### 1. ExecutionPlanCard - 执行计划卡片

**文件**: `frontend/src/components/chat/ExecutionPlanCard.tsx`

**功能**:
- 显示 LLM 生成的执行计划
- 显示步骤依赖关系
- 显示预估总耗时
- 支持折叠/展开

```typescript
interface ExecutionPlanCardProps {
  plan: ExecutionPlanStep[]
  currentStep?: number
  onStepClick?: (stepNumber: number) => void
}

export function ExecutionPlanCard({ plan, currentStep, onStepClick }: ExecutionPlanCardProps) {
  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <h4 className="font-medium mb-3">📋 执行计划</h4>
      <div className="space-y-2">
        {plan.map((step, index) => (
          <div
            key={step.step_number}
            className={cn(
              "flex items-center gap-3 p-2 rounded",
              index === currentStep && "bg-blue-50 border border-blue-200",
              step.status === 'completed' && "text-green-600",
              step.status === 'failed' && "text-red-600",
            )}
          >
            <span className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-sm">
              {step.step_number}
            </span>
            <div className="flex-1">
              <div className="font-medium">{step.description}</div>
              <div className="text-xs text-gray-500">{step.estimated_duration}</div>
            </div>
            <StatusIcon status={step.status} />
          </div>
        ))}
      </div>
    </div>
  )
}
```

#### 2. IntentBadge - 意图标识

**文件**: `frontend/src/components/chat/IntentBadge.tsx`

```typescript
const INTENT_COLORS = {
  start_analysis: 'bg-blue-100 text-blue-800',
  continue_execution: 'bg-green-100 text-green-800',
  modify_plan: 'bg-yellow-100 text-yellow-800',
  help_request: 'bg-purple-100 text-purple-800',
  unknown: 'bg-gray-100 text-gray-800',
}

export function IntentBadge({ intent }: { intent: string }) {
  return (
    <span className={cn(
      "px-2 py-0.5 rounded-full text-xs font-medium",
      INTENT_COLORS[intent] || INTENT_COLORS.unknown
    )}>
      {intent}
    </span>
  )
}
```

### 10.7 无需修改的组件

以下组件**已支持新架构**，无需修改：

| 组件 | 原因 |
|------|------|
| `ChatPanel` | 主聊天面板，逻辑不变 |
| `MessageList` | 消息列表，逻辑不变 |
| `TPAORCard` | 已支持动态阶段 |
| `ProgressIndicator` | 已支持动态步骤 |
| `ConfirmationCard` | 确认卡片，逻辑不变 |
| `InputArea` | 输入区域，逻辑不变 |
| `canvasStore` | Canvas 状态管理，逻辑不变 |

### 10.8 前端适配文件清单

**必须修改** (高优先级):

| 文件 | 修改内容 | 工作量 |
|------|---------|--------|
| `types/orchestration.ts` | 新增类型定义 | 低 |
| `types/message.ts` | 扩展 Message 类型 | 低 |
| `types/agent.ts` | 扩展 ExecutionProgress 类型 | 低 |
| `stores/conversationStore.ts` | 新增状态字段 | 低 |

**可选增强** (中优先级):

| 文件 | 修改内容 | 工作量 |
|------|---------|--------|
| `hooks/useWebSocket.ts` | 新增事件处理 | 低 |
| `components/chat/ExecutionPlanCard.tsx` | 新增组件 | 中 |
| `components/chat/IntentBadge.tsx` | 新增组件 | 低 |
| `components/chat/Message/AgentMessage.tsx` | 增强显示 | 低 |

**无需修改**:
- `ChatPanel.tsx`
- `MessageList.tsx`
- `TPAORCard.tsx`
- `ProgressIndicator.tsx`
- `ConfirmationCard.tsx`
- `InputArea.tsx`
- `canvasStore.ts`

### 10.9 向后兼容策略

**原则**: 所有新增字段都是可选的

```typescript
// 如果后端未发送新字段，使用默认值
const executionPlan = message.execution_plan || null
const reasoning = message.reasoning || ''
const intentType = message.intent_type || 'unknown'
```

**降级处理**:

```typescript
// useWebSocket.ts
socket.on('agent_message', (data) => {
  const message: Message = {
    id: data.id,
    type: 'agent',
    content: data.content,
    timestamp: new Date(data.timestamp),
    tpaor: data.tpaor,
    // 新字段，向后兼容
    execution_plan: data.execution_plan,
    llm_decision: data.llm_decision,
    intent_type: data.intent_type,
    reasoning: data.reasoning,
  }
  addMessage(message)
})
```

---

## 11. 完整影响范围汇总

### 11.1 后端文件变更

**新增文件** (3 个):
- `app/agents/registry.py` - Agent 注册表
- `app/agents/llm_orchestrator.py` - LLM 编排引擎
- `app/schemas/orchestration.py` - 新增 schema

**修改文件** (7 个):
- `app/agents/general_react.py` - 核心重构
- `app/agents/brand_competition.py` - 添加能力注册
- `app/agents/marketing_persona.py` - 添加能力注册
- `app/agents/question_simulation.py` - 添加能力注册
- `app/agents/fetch_agent.py` - 添加能力注册
- `app/agents/data_analytics.py` - 添加能力注册
- `prompts/general_react_agent.md` - 重写 prompt

**可选修改** (3 个):
- `app/services/pipeline_service.py` - 简化
- `app/core/socketio_server.py` - 适配
- `app/services/agent_orchestrator.py` - 适配

### 11.2 前端文件变更

**新增文件** (3 个):
- `types/orchestration.ts` - 新增类型定义
- `components/chat/ExecutionPlanCard.tsx` - 执行计划卡片
- `components/chat/IntentBadge.tsx` - 意图标识

**修改文件** (4 个):
- `types/message.ts` - 扩展类型
- `types/agent.ts` - 扩展类型
- `stores/conversationStore.ts` - 新增状态
- `hooks/useWebSocket.ts` - 新增事件处理

**可选修改** (1 个):
- `components/chat/Message/AgentMessage.tsx` - 增强显示

### 11.3 总工作量估算

| 部分 | 工作量 |
|------|--------|
| 后端核心重构 | 7-11 天 |
| 前端必须适配 | 1 天 |
| 前端可选增强 | 2-3 天 |
| **总计** | **10-15 天** |

---

## 附录 A: LLM Prompt 示例

```markdown
# General ReAct Agent System Prompt

你是 Specta AI 的智能编排引擎，负责协调品牌分析流程。

## 可用 Agent

### A1: 品牌竞品分析
- 描述: 收集品牌基础信息和竞品数据
- 前置条件: 无
- 产出: brand_profile, competitors
- 耗时: 30-45秒

### A2: 用户画像生成
- 描述: 生成目标用户画像
- 前置条件: brand_profile, competitors
- 产出: personas
- 耗时: 25-35秒
- 可跳过: 是

### A3: 问题模拟生成
- 描述: 生成模拟用户问题
- 前置条件: brand_profile, competitors
- 产出: questions
- 耗时: 20-30秒

### A4: AI答案抓取
- 描述: 从AI平台抓取回答
- 前置条件: questions
- 产出: fetch_results
- 耗时: 3-8分钟
- 需要确认: 是（耗时较长）

### A5: 数据分析报告
- 描述: 计算指标并生成报告
- 前置条件: fetch_results, brand_profile, competitors
- 产出: metrics, report
- 耗时: 60-90秒

## 决策规则

1. 用户提供品牌名称 → 调用 A1
2. A1 完成后 → 询问是否生成画像（A2）或直接生成问题（A3）
3. A3 完成后 → 确认后调用 A4（因为耗时长）
4. A4 完成后 → 自动调用 A5
5. A5 完成后 → 展示报告

## 输出格式

```json
{
  "user_intent": "用户意图描述",
  "intent_type": "start_analysis|continue_execution|...",
  "next_action": "call_agent|ask_confirmation|respond_to_user|complete",
  "agent_call": {
    "agent_id": "A1",
    "input_params": {"brand_name": "观夏"},
    "reason": "用户要求分析观夏品牌"
  },
  "reasoning": "决策理由"
}
```
```

---

## 附录 B: 数据流图

```
用户: "帮我分析观夏"
        │
        ▼
┌───────────────────┐
│ LLM 意图识别      │
│ intent: start    │
│ brand: 观夏      │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 调用 A1          │
│ 品牌竞品分析      │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 存储结果          │
│ brand_profile ✓  │
│ competitors ✓    │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ LLM 决策          │
│ 询问: 生成画像?   │
└───────────────────┘
        │
用户: "跳过"
        │
        ▼
┌───────────────────┐
│ LLM 决策          │
│ 调用 A3          │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 调用 A3          │
│ 问题模拟生成      │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 存储结果          │
│ questions ✓      │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ LLM 决策          │
│ 确认: 开始抓取?   │
│ (因为 A4 耗时长)  │
└───────────────────┘
        │
用户: "开始"
        │
        ▼
┌───────────────────┐
│ 调用 A4          │
│ AI答案抓取        │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 存储结果          │
│ fetch_results ✓  │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ LLM 决策          │
│ 自动调用 A5      │
│ (无需确认)        │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 调用 A5          │
│ 数据分析报告      │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 存储结果          │
│ metrics ✓        │
│ report ✓         │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 完成              │
│ 展示报告          │
└───────────────────┘
```
```
```

## 方案修正 - 完全符合 Minimax Mini-Agent 架构

根据对 Minimax Mini-Agent 官方架构的深入研究，我发现了几个关键设计要点需要调整：

### Minimax Mini-Agent 核心架构特点

1. **Function Calling 格式**: Minimax 使用 OpenAI 兼容的 function calling 格式
2. **Tool 定义结构**:
```json
{
  "type": "function",
  "function": {
    "name": "tool_name",
    "description": "tool description",
    "parameters": {
      "type": "object",
      "properties": {...},
      "required": [...]
    }
  }
}
```

3. **ReAct 循环**: MiniMax-M2.1 原生支持 reasoning + acting 的 agentic 行为
4. **流式输出**: 支持 interleaved thinking（思考与回复交错输出）

### 修正后的架构设计

#### 1. Tool 定义层 (完全符合 Minimax Function Calling)

```python
# tools/definitions.py

A1_BRAND_COMPETITION_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_brand_competition",
        "description": "分析品牌档案并识别8-12个主要竞品。输入品牌名称，输出完整的品牌档案、竞品列表和竞争格局分析。",
        "parameters": {
            "type": "object",
            "properties": {
                "brand_name": {
                    "type": "string",
                    "description": "要分析的品牌名称"
                },
                "industry_hint": {
                    "type": "string",
                    "description": "行业提示（可选）"
                },
                "official_website": {
                    "type": "string",
                    "description": "品牌官网（可选）"
                }
            },
            "required": ["brand_name"]
        }
    }
}

A2_MARKETING_PERSONA_TOOL = {
    "type": "function", 
    "function": {
        "name": "generate_user_personas",
        "description": "基于品牌档案生成6-8组用户画像，包含场景、痛点和营销策略建议。",
        "parameters": {
            "type": "object",
            "properties": {
                "brand_profile": {
                    "type": "object",
                    "description": "品牌档案（来自A1的输出）"
                },
                "competitors": {
                    "type": "array",
                    "description": "竞品列表（来自A1的输出）"
                },
                "weakness_areas": {
                    "type": "array",
                    "description": "薄弱环节（可选，用于画像优先级）"
                }
            },
            "required": ["brand_profile", "competitors"]
        }
    }
}

A3_QUESTION_SIMULATION_TOOL = {
    "type": "function",
    "function": {
        "name": "simulate_user_questions",
        "description": "模拟用户提问。支持baseline模式（30个问题）或persona_focus模式（20个问题/画像）。",
        "parameters": {
            "type": "object",
            "properties": {
                "brand_profile": {"type": "object"},
                "competitors": {"type": "array"},
                "personas": {"type": "array", "description": "可选，用于persona_focus模式"},
                "mode": {
                    "type": "string",
                    "enum": ["baseline", "persona_focus"],
                    "description": "生成模式"
                }
            },
            "required": ["brand_profile", "competitors", "mode"]
        }
    }
}

A4_FETCH_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "fetch_ai_platform_answers",
        "description": "从公域大模型平台（豆包、混元、Kimi、DeepSeek）抓取答案。支持API和Browser两种方式。",
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "问题列表（来自A3的输出）"
                },
                "platforms": {
                    "type": "array",
                    "items": {"enum": ["doubao", "hunyuan", "kimi", "deepseek"]},
                    "description": "要抓取的平台列表"
                },
                "brand_info": {
                    "type": "object",
                    "description": "品牌信息，用于引用分析"
                }
            },
            "required": ["questions", "platforms", "brand_info"]
        }
    }
}

A5_DATA_ANALYTICS_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_data_and_generate_report",
        "description": "分析抓取结果，计算BWVS、提及率、情感分布等指标，生成分析报告。",
        "parameters": {
            "type": "object",
            "properties": {
                "fetch_results": {
                    "type": "array",
                    "description": "抓取结果（来自A4的输出）"
                },
                "brand_profile": {"type": "object"},
                "competitors": {"type": "array"},
                "baseline_metrics": {"type": "object", "description": "可选，用于对比分析"}
            },
            "required": ["fetch_results", "brand_profile", "competitors"]
        }
    }
}
```

#### 2. Tool 执行层 (保留完整 Prompts)

```python
# tools/executors.py

class ToolExecutor:
    """Tool 执行器 - 保留完整的 A1-A5 Prompts"""
    
    def __init__(self):
        self.minimax_client = MiniMaxClient()
    
    async def execute_analyze_brand_competition(self, params: dict) -> dict:
        """执行 A1 - 品牌竞品分析"""
        # 加载完整 Prompt
        system_prompt = load_prompt("brand_competition_agent.md")
        
        # 构建输入
        user_input = f"请分析品牌：{params['brand_name']}"
        if params.get('industry_hint'):
            user_input += f"\n行业提示：{params['industry_hint']}"
        
        # 调用 Minimax2.1 执行
        response = await self.minimax_client.chat.completions.create(
            model="MiniMax-Text-01",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            tools=[WEB_SEARCH_TOOL],  # 启用 web_search
            tool_choice="auto"
        )
        
        # 解析并返回标准输出格式
        return self._parse_brand_competition_output(response)
    
    async def execute_generate_user_personas(self, params: dict) -> dict:
        """执行 A2 - 营销画像生成"""
        system_prompt = load_prompt("marketing_persona_agent.md")
        
        user_input = json.dumps({
            "brand_profile": params["brand_profile"],
            "competitors": params["competitors"],
            "weakness_areas": params.get("weakness_areas", [])
        }, ensure_ascii=False)
        
        response = await self.minimax_client.chat.completions.create(
            model="MiniMax-Text-01",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        
        return self._parse_persona_output(response)
    
    # ... 类似实现 A3, A4, A5
```

#### 3. Orchestrator Agent (ReAct 循环)

```python
# agents/orchestrator.py

class SpectaOrchestratorAgent:
    """
    Specta AI 主控 Agent
    - 使用 Minimax2.1 作为基础模型
    - 实现 ReAct 循环 (Thought -> Plan -> Action -> Observation)
    - 流式输出所有中间过程
    """
    
    SYSTEM_PROMPT = load_prompt("general_react_agent.md")
    
    TOOLS = [
        A1_BRAND_COMPETITION_TOOL,
        A2_MARKETING_PERSONA_TOOL,
        A3_QUESTION_SIMULATION_TOOL,
        A4_FETCH_AGENT_TOOL,
        A5_DATA_ANALYTICS_TOOL
    ]
    
    async def run(self, user_input: str, session_id: str):
        """主执行循环"""
        
        # 初始化对话历史
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ]
        
        # ReAct 循环
        while True:
            # 1. Thought + Plan - LLM 决定下一步
            response = await self.minimax_client.chat.completions.create(
                model="MiniMax-Text-01",
                messages=messages,
                tools=self.TOOLS,
                tool_choice="auto",
                stream=True  # 流式输出
            )
            
            # 流式输出 Thought/Plan
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield {
                        "type": "thinking",
                        "content": chunk.choices[0].delta.content
                    }
                
                if chunk.choices[0].delta.tool_calls:
                    # 2. Action - 执行 Tool
                    tool_call = chunk.choices[0].delta.tool_calls[0]
                    yield {
                        "type": "action",
                        "tool": tool_call.function.name,
                        "params": tool_call.function.arguments
                    }
                    
                    # 执行 Tool
                    result = await self._execute_tool(
                        tool_call.function.name,
                        json.loads(tool_call.function.arguments)
                    )
                    
                    # 3. Observation - 返回结果
                    yield {
                        "type": "observation",
                        "tool": tool_call.function.name,
                        "result": result
                    }
                    
                    # 添加到对话历史
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tool_call.id,
                            "type": "function",
                            "function": tool_call.function
                        }]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
                    
                    break  # 继续下一轮 ReAct
            
            # 检查是否完成
            if not response.tool_calls:
                # 4. Response - 最终回复
                final_response = ""
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        final_response += chunk.choices[0].delta.content
                        yield {
                            "type": "response",
                            "content": chunk.choices[0].delta.content
                        }
                break
```

#### 4. 前端展示架构 (Manus.im 风格)

```typescript
// 消息层级结构
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;  // 主消息 - 始终可见
  type: 'main';     // 主消息标识
}

interface ProcessStep {
  id: string;
  type: 'thought' | 'plan' | 'action' | 'observation';
  content: string;
  toolName?: string;      // action 类型时有
  toolParams?: object;    // action 类型时有
  toolResult?: object;    // observation 类型时有
  isCollapsible: true;    // 可折叠
  isExpanded: boolean;    // 当前展开状态
}

// UI 组件层级
<ChatContainer>
  <UserMessage />           {/* 始终展开 */}
  <AssistantMessage>        {/* 始终展开 - 最终回复 */}
  
  <ProcessSection>          {/* 可折叠的过程区域 */}
    <Collapsible title="思考过程">
      <ThoughtStep />
      <PlanStep />
      <ActionStep />        {/* 显示 Tool 调用 */}
      <ObservationStep>     {/* 显示 Tool 结果 */}
        <JsonDetail />      {/* 可展开的 JSON */}
      </ObservationStep>
    </Collapsible>
  </ProcessSection>
</ChatContainer>
```

### 关键设计确认

1. **Tool 定义**: 完全符合 Minimax Function Calling 格式
2. **Prompt 保留**: A1-A5 的 Prompts 原封不动作为 system_prompt
3. **输出结构**: 完全复用现有的 Pydantic schemas
4. **ReAct 循环**: Thought -> Plan -> Action -> Observation
5. **流式输出**: 所有中间过程实时流式展示
6. **UI 层级**: 主消息始终可见，过程信息可折叠

### 实施步骤

#### Phase 1: Tool 定义与执行层
1. 创建 `app/tools/definitions.py` - 定义 5 个 Tool 的 JSON Schema
2. 创建 `app/tools/executors.py` - 实现 Tool 执行，保留完整 Prompts
3. 创建 `app/tools/registry.py` - Tool 注册与路由

#### Phase 2: Orchestrator Agent
1. 创建 `app/agents/orchestrator.py` - ReAct 循环实现
2. 集成 Minimax2.1 Function Calling
3. 实现流式输出 (SSE)

#### Phase 3: API 层
1. 创建 `app/api/chat.py` - 流式聊天 API
2. 替换现有的 minimax_chat.py

#### Phase 4: 前端重构
1. 重构消息展示组件
2. 实现可折叠的过程信息面板
3. 保持现有测试页面

请确认此方案是否符合 Minimax 架构要求，以及是否可以开始实施。
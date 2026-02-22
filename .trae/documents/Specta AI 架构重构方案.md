# Phase 1: LangGraph 架构迁移 - 实施计划

## 一、老代码设计分析总结

### 1.1 A1-A5 Tool 核心输出字段（必须兼容）

| Agent | 核心输出字段 | 数据类型 | 用途 |
|-------|-------------|---------|------|
| **A1** | `brand_profile` | dict | 品牌档案，包含 brand_name, industry, description, core_products 等 |
| **A1** | `competitors` | list | 竞品列表，每个包含 name, relevance_score, competition_type |
| **A1** | `competitive_landscape` | dict | 竞争格局分析 |
| **A2** | `personas` | list | 用户画像列表，每个包含 id, name, demographics, pain_points |
| **A3** | `questions` | list | 模拟问题列表，每个包含 id, text, category, intent |
| **A4** | `fetch_results` | list | 抓取结果，每个包含 question_id, platform_results |
| **A5** | `metrics` | dict | 核心指标：bwvs_index, mention_rate, sentiment_distribution |
| **A5** | `report` | dict | 分析报告：executive_summary, recommendations, action_plan |

### 1.2 需要修复的依赖问题

**已删除但Tool仍在引用的模块：**
- `app.tools.base` (Tool, ToolResult, ToolProgress)
- `app.agents.utils` (extract_json_from_content, load_prompt, render_prompt)

**解决方案：**
1. 创建 `app/core/utils.py` - 提取 JSON 的通用函数
2. 修改 Tool 类 - 移除继承，改为纯函数式调用
3. 使用 `jinja2` 直接渲染提示词模板

### 1.3 MiniMax 模型封装（已保留）

- `MiniMaxModel` 类 - 支持同步/异步调用、流式输出
- `MiniMaxConfig` 类 - 配置管理
- 支持 `reasoning_split` 获取思考过程

---

## 二、LangGraph State 设计（兼容老字段）

```python
# app/workflow/state.py
from typing import TypedDict, Annotated, Sequence
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """LangGraph 状态 - 完全兼容老代码输出字段"""
    
    # === 会话标识 ===
    session_id: str
    
    # === 消息历史（LangGraph标准）===
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # === A1 输出（兼容老字段）===
    brand_profile: dict | None          # A1: 品牌档案
    competitors: list | None            # A1: 竞品列表
    competitive_landscape: dict | None  # A1: 竞争格局
    
    # === A2 输出（兼容老字段）===
    personas: list | None               # A2: 用户画像列表
    
    # === A3 输出（兼容老字段）===
    questions: list | None              # A3: 模拟问题列表
    
    # === A4 输出（兼容老字段）===
    fetch_results: list | None          # A4: 抓取结果
    
    # === A5 输出（兼容老字段）===
    metrics: dict | None                # A5: 核心指标
    report: dict | None                 # A5: 分析报告
    
    # === 执行控制（新增）===
    current_step: str                   # 当前步骤: A1/A2/A3/A4/A5
    execution_status: str               # running/paused/completed/error
    
    # === Human-in-loop（新增）===
    pending_confirmation: dict | None   # 待确认的请求
    user_decisions: dict                # 用户在各步骤的选择 {step_id: decision}
    
    # === 错误处理（新增）===
    error_info: dict | None             # 错误信息
    
    # === 原始输入（保留）===
    brand_name: str | None              # 用户输入的品牌名
    official_website: str | None        # 用户输入的官网
    industry_hint: str | None           # 用户输入的行业提示
```

---

## 三、实施步骤

### Step 1: 创建基础工具函数（30分钟）

**文件：** `app/core/utils.py`
- `extract_json_from_content()` - 从LLM响应中提取JSON
- `load_prompt_template()` - 加载提示词模板
- `render_prompt()` - 渲染提示词

### Step 2: 修改 A1-A5 Tool（1小时）

**修改内容：**
1. 移除 `from app.tools.base import Tool, ToolResult, ToolProgress`
2. 移除 `from app.agents.utils import ...`
3. 改为纯函数式调用，返回 `dict` 而非 `ToolResult`
4. 保留所有业务逻辑和输出字段

**示例修改：**
```python
# 修改前
class BrandCompetitionTool(Tool):
    async def execute(...) -> ToolResult:
        ...
        return ToolResult(success=True, data={"brand_profile": ...})

# 修改后
async def analyze_brand_competition(
    brand_name: str,
    official_website: str | None = None,
    industry_hint: str | None = None
) -> dict:
    """A1 品牌竞品分析 - 纯函数"""
    ...
    return {
        "brand_profile": {...},
        "competitors": [...],
        "competitive_landscape": {...}
    }
```

### Step 3: 创建 LangGraph Workflow（2小时）

**文件结构：**
```
app/workflow/
├── __init__.py
├── state.py          # AgentState 定义
├── nodes.py          # A1-A5 节点封装
├── graph.py          # 工作流图构建
├── checkpoint.py     # Postgres 持久化配置
└── events.py         # WebSocket 事件发送
```

**核心实现：**
1. **state.py** - 状态定义（见上文）
2. **nodes.py** - 每个Agent封装为Node函数
3. **graph.py** - 构建工作流图，添加边和条件
4. **checkpoint.py** - PostgresCheckpointer 配置
5. **events.py** - 发送 WebSocket 事件

### Step 4: 集成 WebSocket（1小时）

**修改：** `app/core/websocket_server.py`
- 添加 `run_workflow()` 函数
- 将 LangGraph 事件转换为前端协议
- 处理 Human-in-loop 确认

### Step 5: 数据库迁移（30分钟）

**创建：** `alembic/versions/002_add_checkpoint_table.py`
- LangGraph checkpoint 表
- Checkpoint blobs 表

### Step 6: 更新依赖（15分钟）

**修改：** `requirements.txt`
```
langgraph>=0.2.0
langchain-core>=0.3.0
langchain-openai>=0.2.0
```

### Step 7: 测试验证（1小时）

**测试内容：**
1. A1 节点单独执行
2. A1→A3→A4→A5 完整流程
3. 服务重启后状态恢复
4. WebSocket 事件正常推送

---

## 四、关键设计决策

### 4.1 为什么保留 Tool 的业务逻辑？

- 提示词工程已经过调优，直接复用
- 输出字段格式已确定，保持兼容
- 减少重构风险，专注架构迁移

### 4.2 Human-in-loop 实现

使用 LangGraph 的 `interrupt()` 机制：
```python
async def a2_persona_node(state: AgentState):
    # 检查用户是否已决定跳过
    if state["user_decisions"].get("skip_a2"):
        return Command(goto="a3_question_node")
    
    # 请求用户确认
    result = interrupt({
        "type": "step_confirmation",
        "step_id": "A2",
        "options": [{"id": "continue", "label": "继续"}, {"id": "skip", "label": "跳过"}]
    })
    
    # 根据用户选择执行
    if result["selection"] == "skip":
        return Command(
            goto="a3_question_node",
            update={"user_decisions": {"skip_a2": True}}
        )
    
    # 执行 A2
    output = await analyze_brand_competition(...)
    return Command(goto="a3_question_node", update=output)
```

### 4.3 WebSocket 协议兼容

保持现有前端协议不变：
- `execution_progress` - 执行进度
- `tpaor_update` - TPAOR 阶段更新
- `confirmation_request` - 确认请求
- `output_ready` - 输出就绪
- `execution_complete` - 执行完成

---

## 五、文件创建/修改清单

### 新建文件（7个）
1. `app/core/utils.py` - 工具函数
2. `app/workflow/__init__.py`
3. `app/workflow/state.py` - 状态定义
4. `app/workflow/nodes.py` - 节点封装
5. `app/workflow/graph.py` - 工作流图
6. `app/workflow/checkpoint.py` - 持久化
7. `app/workflow/events.py` - 事件发送
8. `alembic/versions/002_add_checkpoint_table.py` - 迁移

### 修改文件（7个）
1. `app/tools/a1_brand_competition.py` - 改为纯函数
2. `app/tools/a2_marketing_persona.py` - 改为纯函数
3. `app/tools/a3_question_simulation.py` - 改为纯函数
4. `app/tools/a4_fetch_agent.py` - 改为纯函数
5. `app/tools/a5_data_analytics.py` - 改为纯函数
6. `app/core/websocket_server.py` - 集成LangGraph
7. `requirements.txt` - 添加依赖

### 删除文件（0个，已清理完成）

---

## 六、预计时间

| 步骤 | 预计时间 | 说明 |
|------|---------|------|
| Step 1: 基础工具 | 30分钟 | 提取JSON等通用函数 |
| Step 2: 修改Tool | 1小时 | 5个Tool改为纯函数 |
| Step 3: Workflow | 2小时 | LangGraph核心实现 |
| Step 4: WebSocket | 1小时 | 事件集成 |
| Step 5: 迁移 | 30分钟 | 数据库表 |
| Step 6: 依赖 | 15分钟 | requirements.txt |
| Step 7: 测试 | 1小时 | 验证工作流 |
| **总计** | **~6.5小时** | |

---

## 七、风险提示

1. **A4 抓取耗时** - 当前是同步执行，Phase 3 改为Celery
2. **MiniMax 兼容性** - LangGraph默认OpenAI接口，需适配
3. **状态大小** - A4结果可能很大，checkpoint存储需优化

---

请确认此计划后，我将开始实施 Step 1。
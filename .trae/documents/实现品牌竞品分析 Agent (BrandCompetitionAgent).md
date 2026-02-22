## 执行计划

### Step 1: 创建输入输出 Schema
**文件**: `backend/app/schemas/brand.py`

定义 Pydantic Schema：
- `BrandCompetitionInput` - 输入：brand_name, official_website, industry_hint
- `BrandProfile` - 品牌档案
- `Competitor` - 竞品信息
- `BrandCompetitionOutput` - 完整输出

### Step 2: 创建系统提示词
**文件**: `backend/prompts/brand_competition_agent.md`

基于设计文档创建提示词，包含：
- Agent 角色定义
- 任务说明
- 分析流程
- 输出格式（JSON Schema）
- 竞品筛选原则
- 工具使用说明（web_search）

### Step 3: 实现 BrandCompetitionAgent
**文件**: `backend/app/agents/brand_competition.py`

实现完整的 Agent：
- 继承 `AEOAgentBase`
- `agent_id = "A1"`
- `prompt_file = "brand_competition_agent"`
- 实现 `execute()` 方法
- 集成 `web_search` 工具
- 解析 JSON 输出
- 保存结果到数据库

**核心流程**：
1. 接收输入（品牌名、官网等）
2. 使用 web_search 搜索品牌信息
3. 使用 web_search 搜索竞品信息
4. 调用 MiniMax 分析整理
5. 解析 JSON 输出
6. 保存到 brand_profiles 表

### Step 4: 创建测试文件
**文件**: `backend/tests/test_agents/test_brand_competition.py`

测试内容：
- Agent 初始化测试
- 输入验证测试
- 工具调用测试（mock）
- JSON 解析测试
- 数据库集成测试

### 关键实现细节

**工具使用**：
```python
# 在 execute 中使用 run_with_tools 自动处理工具调用
result = self.run_with_tools(input_data, max_tool_rounds=3)
```

**数据库集成**：
```python
# 保存到 brand_profiles 表
from app.models.brand import BrandProfile
# 创建记录并关联到 session
```

**错误处理**：
- JSON 解析失败时返回原始内容
- 搜索失败时使用模型知识
- 数据库保存失败不影响返回结果

请确认此计划后，我将开始执行具体的代码实现。
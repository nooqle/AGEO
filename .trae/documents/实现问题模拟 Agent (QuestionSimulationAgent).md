## 执行计划

### Step 1: 创建输入输出 Schema
**文件**: `backend/app/schemas/question.py`

定义 Pydantic Schema：
- `QuestionVariant` - 问题变体（直接型、场景型、对比型）
- `SimulatedQuestion` - 模拟问题（id、问题文本、类别、意图等）
- `QuestionSimulationInput` - 输入：brand_profile, competitors, mode, personas
- `QuestionSimulationOutput` - 输出：questions, mode, statistics
- `QuestionSimulationResult` - 包含元数据的结果

### Step 2: 创建系统提示词
**文件**: `backend/prompts/question_simulation_agent.md`

基于设计文档创建提示词：
- Agent 角色定义（消费者行为研究专家）
- 两种模式说明：
  - Baseline 模式：品牌全景模式，5大类（品牌认知/产品咨询/购买决策/使用场景/行业探索）
  - Persona Focus 模式：画像聚焦模式，5大类（场景触发/痛点驱动/身份匹配/决策推进/延伸需求）
- 问题生成原则（口吻真实性、问法多样性、搜索意图分层）
- JSON 输出格式（两种模式不同格式）

### Step 3: 实现 QuestionSimulationAgent
**文件**: `backend/app/agents/question_simulation.py`

实现 `QuestionSimulationAgent` 类：
- 继承 `AEOAgentBase`
- `agent_id = "A3"`
- `prompt_file = "question_simulation_agent"`
- 实现 `execute()` 方法，支持两种模式
- JSON 解析和验证
- 统计信息生成

**核心流程**：
1. 接收输入（品牌档案、竞品、模式、画像等）
2. 根据模式构建不同的 prompt
3. 调用模型生成问题
4. 解析 JSON 输出
5. 生成统计信息

### Step 4: 创建测试文件
**文件**: `backend/tests/test_agents/test_question_simulation.py`

测试内容：
- Schema 验证测试
- Agent 初始化测试
- Baseline 模式测试
- Persona Focus 模式测试
- 统计信息生成测试

### 关键设计

**两种模式**：
- **Baseline 模式**：10个核心问题 × 3个变体 = 30个问题
- **Persona Focus 模式**：10个问题 × 2个变体 = 20个问题/画像

**问题变体类型**：
- 直接型：开门见山
- 场景型：带个人背景
- 对比型：涉及竞品对比

**决策阶段**：
- 认知阶段、兴趣阶段、决策阶段、行动阶段

请确认此计划后，我将开始执行具体的代码实现。
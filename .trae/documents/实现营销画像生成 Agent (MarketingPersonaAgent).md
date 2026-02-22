## 执行计划

### Step 1: 创建输入输出 Schema
**文件**: `backend/app/schemas/persona.py`

定义 Pydantic Schema：
- `WeaknessArea` - 薄弱环节（来自基准分析）
- `PersonaGenerationInput` - 输入：brand_profile, competitors, weakness_areas
- `UserPersona` - 用户画像（id, name, emoji, demographics, psychographics等）
- `UsageScenario` - 使用场景
- `MarketingPainPoint` - 营销痛点
- `PersonaGenerationOutput` - 完整输出（6-8个画像）
- `PersonaGenerationResult` - 包含元数据的结果

### Step 2: 创建系统提示词
**文件**: `backend/prompts/marketing_persona_agent.md`

基于设计文档创建提示词：
- Agent 角色定义（消费者洞察专家）
- 任务说明（生成6-8组画像）
- 人群细分维度
- 场景挖掘原则
- 痛点分析框架
- JSON 输出格式
- 画像差异化要求

### Step 3: 实现 MarketingPersonaAgent
**文件**: `backend/app/agents/marketing_persona.py`

实现 `MarketingPersonaAgent` 类：
- 继承 `AEOAgentBase`
- `agent_id = "A2"`
- `prompt_file = "marketing_persona_agent"`
- 实现 `execute()` 方法
- JSON 解析和验证
- 数据库保存功能

**核心流程**：
1. 接收品牌档案和竞品信息
2. 分析目标人群特征
3. 生成6-8组差异化画像
4. 为每个画像定义场景和痛点
5. 如果有薄弱环节，优先生成覆盖画像
6. 输出结构化结果

### Step 4: 创建测试文件
**文件**: `backend/tests/test_agents/test_marketing_persona.py`

测试内容：
- Schema 验证测试
- Agent 初始化测试
- JSON 提取测试
- 画像生成逻辑测试
- 薄弱环节关联测试

### 关键设计

**画像结构**：
- 基础信息：id, name, emoji, description
- 人口统计：age_range, gender, city_tier等
- 心理特征：lifestyle, values, interests
- 品牌关系：awareness_level, purchase_motivation
- 使用场景：2个差异化场景
- 营销痛点：2个核心痛点
- 推荐优先级：recommendation_score

**差异化要求**：
- 核心人群（2-3组）：品牌主力消费群体
- 增长人群（2-3组）：有潜力未充分开发的群体
- 机会人群（1-2组）：可拓展的新兴群体

请确认此计划后，我将开始执行具体的代码实现。
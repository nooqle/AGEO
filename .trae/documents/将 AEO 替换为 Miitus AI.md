## 执行计划

### 需要替换的文件

根据搜索结果，以下文件包含 "AEO" 相关内容需要替换：

#### 前端 (frontend)
1. `src/components/chat/MessageList.tsx` - 欢迎语 "欢迎使用 AEO 智能分析"

#### 后端 (aeo-platform/backend)
1. `app/config.py` - APP_NAME: "Miitus AEO Platform" → "Miitus AI Platform"
2. `app/agents/general_react.py` - 多处 AEO 相关描述
3. `app/services/report_generator.py` - 报告标题和页脚
4. `prompts/general_react_agent.md` - Agent 提示词
5. `prompts/data_analytics_agent.md` - Agent 提示词
6. `prompts/brand_competition_agent.md` - Agent 提示词
7. `scripts/test_llm.py` - 测试脚本标题
8. 其他文件中的注释和描述

#### 替换规则
- "AEO 智能分析" → "Miitus AI 智能分析"
- "AEO Platform" → "Miitus AI Platform"
- "AEO（AI Engine Optimization）" → "Miitus AI"
- 单独出现的 "AEO" 根据上下文替换为 "Miitus AI" 或删除

### 不需要替换的
- 代码中的变量名、属性名（如 aeo_keywords）
- 数据库迁移文件中的字段名
- 类型定义中的标识符

请确认此计划后，我将开始执行具体的替换工作。
## 修改计划

### 1. 重构意图识别（高优先级）
- 文件: `app/agents/general_react.py`
- 删除 `_detect_intent()` 中的正则匹配逻辑
- 使用 LLM 进行意图识别，返回结构化格式

### 2. 完善 TPAOR 框架（高优先级）
- 文件: `app/agents/general_react.py`
- 使用中文阶段名称：思考、规划、行动、观察、回复
- 严格按照设计文档的 TPAOR 输出格式

### 3. 修复 Schema 验证（中优先级）
- 文件: `app/schemas/brand.py`
- 修复 `founded_year` 字段类型验证问题

### 4. 测试验证
- 运行端到端测试，验证修改效果
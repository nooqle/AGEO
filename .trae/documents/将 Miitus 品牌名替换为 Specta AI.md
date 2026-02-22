## 任务概述
将系统中所有 "Miitus" / "miitus" 替换为 "Specta AI" / "specta"

## 需要修改的文件清单（22个文件）

### 1. 核心配置文件（3个文件）
- `app/config.py` - APP_NAME 和数据库 URL
- `app/core/config.py` - APP_NAME 和数据库 URL
- `alembic.ini` - 数据库配置

### 2. Agent 相关文件（8个文件）
- `app/agents/base.py` - 类名 MiitusAgentBase → SpectaAgentBase，docstring
- `app/agents/__init__.py` - 导出名称
- `app/agents/brand_competition.py` - docstring 中的 Miitus AI
- `app/agents/general_react.py` - 帮助消息中的平台名
- `app/agents/question_simulation.py` - docstring
- `app/agents/marketing_persona.py` - docstring
- `app/agents/data_analytics.py` - docstring
- `app/agents/fetch_agent.py` - docstring
- `app/agents/utils.py` - docstring

### 3. Prompt 文件（3个文件）
- `prompts/general_react_agent.md` - 多处平台名称
- `prompts/brand_competition_agent.md` - Miitus AI 平台
- `prompts/data_analytics_agent.md` - Miitus AI 平台

### 4. 服务层文件（3个文件）
- `app/services/report_generator.py` - 报告标题
- `app/services/pipeline_service.py` - 平台名称
- `app/services/metrics_calculator.py` - 平台名称

### 5. 其他文件（3个文件）
- `app/main.py` - FastAPI title 和 description
- `app/__init__.py` - 版本信息
- `scripts/test_llm.py` - 测试脚本
- `test_e2e.py` - 测试脚本

## 替换规则
- `Miitus` → `Specta`
- `Miitus AI` → `Specta AI`
- `miitus` → `specta`（小写，用于数据库名、变量名等）
- `MiitusAgentBase` → `SpectaAgentBase`（类名）

## 注意事项
1. 数据库 URL 中的 `miitus_db` 改为 `specta_db`
2. 类名 `MiitusAgentBase` 需要同步修改所有引用处
3. Prompt 文件中的示例和角色定义需要更新
4. 保持代码功能不变，仅替换品牌名称
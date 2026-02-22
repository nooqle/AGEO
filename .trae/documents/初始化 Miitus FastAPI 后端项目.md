## 执行计划

### 阶段 1: 创建项目基础结构
1. 创建 `aeo-platform/backend/` 目录及所有子目录
2. 创建 `requirements.txt` 依赖文件
3. 创建 `.env.example` 环境变量模板

### 阶段 2: 核心配置文件
4. 创建 `app/config.py` - 使用 Pydantic-Settings 管理配置
5. 创建 `app/core/database.py` - SQLAlchemy 2.0 异步数据库连接
6. 创建 `app/core/exceptions.py` - 自定义异常类

### 阶段 3: 数据库模型
7. 创建 `app/models/session.py` - Session 模型
8. 创建 `app/models/message.py` - Message 模型  
9. 创建 `app/models/brand.py` - BrandProfile 模型
10. 创建 `app/models/__init__.py` - 统一导出

### 阶段 4: Pydantic Schemas
11. 创建 `app/schemas/session.py` - Session 相关 schemas
12. 创建 `app/schemas/message.py` - Message 相关 schemas
13. 创建 `app/schemas/__init__.py` - 统一导出

### 阶段 5: API 路由
14. 创建 `app/api/deps.py` - 依赖注入 (数据库会话)
15. 创建 `app/api/v1/sessions.py` - 会话管理 API
16. 创建 `app/api/v1/messages.py` - 消息处理 API
17. 创建 `app/api/v1/__init__.py` - 路由聚合

### 阶段 6: 业务逻辑与入口
18. 创建 `app/services/session_service.py` - 会话服务层
19. 创建 `app/main.py` - FastAPI 应用入口
20. 创建 `app/__init__.py`

### 阶段 7: Alembic 迁移配置
21. 创建 `alembic.ini` 配置文件
22. 创建 `alembic/env.py` 环境配置
23. 创建 `alembic/versions/` 目录
24. 生成初始迁移脚本

### 技术栈
- Python 3.10+
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async) + asyncpg
- Pydantic 2.0 + Pydantic-Settings
- Alembic
- PostgreSQL

请确认此计划后，我将开始执行具体的文件创建和代码编写。
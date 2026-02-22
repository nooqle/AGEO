# 任务：配置本地开发环境（不依赖 Docker）

## 背景
配置纯本地开发环境，无需 Docker，方便快速开发和调试。

## 任务要求

### 1. 后端本地运行

#### 1.1 安装依赖
```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 agent-browser（浏览器抓取需要）
npm install -g agent-browser
agent-browser install
```


**使用本地 PostgreSQL（更接近生产）**
```bash
# macOS
npm install postgresql@16
npm services start postgresql@16

# 创建数据库
createdb aeo_dev

# .env.local
DATABASE_URL=postgresql+asyncpg://localhost/aeo_dev
```

#### 1.3 创建 .env.local
```bash
# backend/.env.local

# 数据库
DATABASE_URL=postgresql+asyncpg://localhost/aeo_dev

Redis（可选，不配置则跳过缓存功能）
REDIS_URL=redis://localhost:6379

# LLM API Keys（必须配置才能测试抓取功能）
MINIMAX_API_KEY=sk-api-5cJeRJuKbXPyAmE0DY8OFcQdT0rhWiaLr0LfTM76BrKOmpaRLW4P56lyxlKOv676iO2aVazmH-rocz2S-ZqTa-CAxOXrojPmodmLpshuvvsYNc6-BZL8_1Y
DOUBAO_API_KEY=6fe00e11-4897-4745-bb24-46b637031539
HUNYUAN_API_KEY=sk-hFKiSo2YnJEM4fNQjYXmKan8kfN9ba2mdjb37fK6YiFDIJOZ

# 开发模式
DEBUG=true
```

#### 1.4 数据库迁移
```bash
cd backend

# 生成迁移
alembic revision --autogenerate -m "initial"

# 执行迁移
alembic upgrade head
```

#### 1.5 启动后端
```bash
cd backend
source venv/bin/activate

# 开发模式启动（热重载）
uvicorn app.main:app --reload --port 8000

# 访问
# API: http://localhost:8000
# 文档: http://localhost:8000/docs
```

### 2. 前端本地运行

#### 2.1 安装依赖
```bash
cd frontend
npm install
```

#### 2.2 创建 .env.local
```bash
# frontend/.env.local

NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=http://localhost:8000
```

#### 2.3 启动前端
```bash
cd frontend
npm run dev

# 访问: http://localhost:3000
```

### 3. 同时启动前后端的便捷脚本
```bash
#!/bin/bash
# scripts/dev.sh

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}启动 AEO 开发环境...${NC}"

# 检查后端虚拟环境
if [ ! -d "backend/venv" ]; then
    echo -e "${YELLOW}创建后端虚拟环境...${NC}"
    cd backend
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
fi

# 检查前端依赖
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}安装前端依赖...${NC}"
    cd frontend
    npm install
    cd ..
fi

# 启动后端
echo -e "${GREEN}启动后端 (port 8000)...${NC}"
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
cd ..

# 等待后端启动
sleep 3

# 启动前端
echo -e "${GREEN}启动前端 (port 3000)...${NC}"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}开发环境已启动！${NC}"
echo -e "${GREEN}前端: http://localhost:3000${NC}"
echo -e "${GREEN}后端: http://localhost:8000${NC}"
echo -e "${GREEN}API 文档: http://localhost:8000/docs${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"

# 等待并处理退出
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
```

### 4. 本地测试各功能模块

#### 4.1 测试后端 API
```bash
# 健康检查
curl http://localhost:8000/health

# 创建会话
curl -X POST http://localhost:8000/api/v1/sessions

# 查看 API 文档
open http://localhost:8000/docs
```

#### 4.2 测试 Agent（单元测试）
```bash
cd backend

# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_agents/test_brand_competition.py -v

# 带覆盖率
pytest --cov=app --cov-report=html
```

#### 4.3 测试 LLM 连接
```python
# backend/scripts/test_llm.py
import asyncio
from app.core.minimax_model import MiniMaxChatModel
from app.core.config import settings

async def test_minimax():
    model = MiniMaxChatModel()
    response = await model.chat("你好，请简单介绍一下自己")
    print(f"Response: {response}")

if __name__ == "__main__":
    asyncio.run(test_minimax())
```
```bash
cd backend
python scripts/test_llm.py
```

#### 4.4 测试浏览器抓取
```bash
# 测试 agent-browser 是否正常
agent-browser open https://kimi.moonshot.cn
agent-browser snapshot -i
agent-browser close
```

### 5. 配置支持 SQLite 和 PostgreSQL 双模式
```python
# backend/app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 根据 URL 判断数据库类型
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# 创建引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    # SQLite 需要特殊配置
    connect_args={"check_same_thread": False} if is_sqlite else {},
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

### 6. 可选：Redis 降级处理
```python
# backend/app/core/cache.py
from typing import Optional
import json
from app.core.config import settings

class CacheService:
    def __init__(self):
        self.redis = None
        if settings.REDIS_URL:
            try:
                import redis.asyncio as redis
                self.redis = redis.from_url(settings.REDIS_URL)
            except Exception as e:
                print(f"Redis 连接失败，使用内存缓存: {e}")
        
        # 内存缓存作为降级方案
        self._memory_cache = {}
    
    async def get(self, key: str) -> Optional[str]:
        if self.redis:
            return await self.redis.get(key)
        return self._memory_cache.get(key)
    
    async def set(self, key: str, value: str, ttl: int = 3600):
        if self.redis:
            await self.redis.setex(key, ttl, value)
        else:
            self._memory_cache[key] = value
    
    async def delete(self, key: str):
        if self.redis:
            await self.redis.delete(key)
        else:
            self._memory_cache.pop(key, None)

cache = CacheService()
```

## 预期产出
1. `backend/.env.local.example`
2. `frontend/.env.local.example`
3. `backend/app/core/config.py`（支持多环境）
4. `backend/app/core/database.py`（支持 SQLite/PostgreSQL）
5. `backend/app/core/cache.py`（Redis 可选）
6. `scripts/dev.sh`（一键启动脚本）
7. `backend/scripts/test_llm.py`（LLM 连接测试）
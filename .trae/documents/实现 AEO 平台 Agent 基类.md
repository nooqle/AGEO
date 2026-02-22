## 执行计划

### 1. 创建工具函数模块
**文件**: `backend/app/agents/utils.py`

功能：
- `load_prompt(prompt_name: str) -> str` - 从 prompts 目录加载提示词文件
- `render_prompt(template: str, variables: dict) -> str` - 变量替换
- `format_tpaor_output(state: dict) -> str` - 格式化 TPAOR 输出
- `ProgressCallback` 类型定义
- `WebSocketMessage` 类型定义

### 2. 创建 Agent 基类
**文件**: `backend/app/agents/base.py`

实现 `AEOAgentBase` 类：

```python
class AEOAgentBase:
    """AEO 平台 Agent 基类"""
    
    # 类属性
    agent_id: str
    agent_name: str
    prompt_file: str
    
    def __init__(self, config: MiniMaxConfig | None = None):
        self.model = MiniMaxModel(config)
        self.system_prompt = self._load_system_prompt()
        self.tools: dict[str, Callable] = {}
        self.progress_callbacks: list[Callable] = []
        self.tpaor_state: dict = {}
        
    # 核心方法
    def _load_system_prompt(self) -> str
    def register_tool(self, func: Callable) -> Callable  # 装饰器
    def on_progress_update(self, callback: Callable)
    def get_tpaor_state(self) -> dict
    def _emit_progress(self, stage: str, progress: float, message: str)
    def _update_tpaor_state(self, stage: str, data: dict)
    def execute(self, input_data: dict) -> dict  # 主执行入口
    def chat(self, messages: list[dict]) -> MiniMaxResponse
```

### 3. 创建 Agent 包初始化文件
**文件**: `backend/app/agents/__init__.py`

导出：
- `AEOAgentBase`
- `load_prompt`, `render_prompt`
- `ProgressCallback`, `WebSocketMessage`

### 4. 创建示例 Agent 实现
**文件**: `backend/app/agents/brand_competition.py`

展示如何继承 `AEOAgentBase` 实现具体的 Brand Competition Agent。

### 5. 更新项目结构
```
backend/app/agents/
├── __init__.py
├── base.py           # Agent 基类
├── utils.py          # 工具函数
└── brand_competition.py  # 示例实现
```

### 关键特性

1. **MiniMax 模型集成**：自动加载配置，支持 reasoning_split
2. **TPAOR 状态管理**：跟踪每个阶段的状态
3. **进度回调**：支持 WebSocket 推送进度
4. **工具注册装饰器**：便捷的工具注册机制
5. **提示词管理**：从文件加载，支持变量替换
6. **Agent as Tool**：支持将其他 Agent 注册为工具

请确认此计划后，我将开始执行具体的代码实现。
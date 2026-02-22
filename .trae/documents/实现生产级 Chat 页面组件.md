## 执行计划

### Step 1: 创建类型定义
**文件**:
- `frontend/src/types/message.ts` - Message, TPAORContent, OutputCard, ConfirmationRequest 等类型
- `frontend/src/types/agent.ts` - TPAORPhase, ExecutionProgress, BrowserState, StopState 等类型

### Step 2: 创建工具函数
**文件**:
- `frontend/src/lib/cn.ts` - className 合并工具
- `frontend/src/lib/utils.ts` - 时间格式化、进度格式化、带圈数字等工具函数

### Step 3: 更新状态管理
**文件**: `frontend/src/stores/conversationStore.ts`
- 更新为更完整的 ConversationState
- 添加 TPAOR、执行进度、浏览器状态、停止状态等
- 完善 Actions

### Step 4: 创建 Message 组件
**目录**: `frontend/src/components/chat/Message/`
- `index.tsx` - 消息分发组件
- `UserMessage.tsx` - 用户消息
- `AgentMessage.tsx` - Agent 消息（含 TPAOR、卡片、确认）
- `SystemMessage.tsx` - 系统消息
- `TPAORBlock.tsx` - TPAOR 展示块（可折叠）
- `OutputCard.tsx` - 产出内容卡片
- `ConfirmationBlock.tsx` - 确认请求块

### Step 5: 创建 ChatPanel 主组件
**文件**: `frontend/src/components/chat/ChatPanel.tsx`
- 整合所有子组件
- 处理消息发送
- 模拟 Agent 响应（开发调试）
- 自动滚动

### Step 6: 创建其他 Chat 组件
**文件**:
- `MessageList.tsx` - 消息列表（含空状态）
- `InputArea.tsx` - 输入区域（含快捷确认）
- `ProgressIndicator.tsx` - 执行进度指示器
- `BrowserStateAlert.tsx` - 浏览器状态提示
- `StopExecutionStatus.tsx` - 停止执行状态
- `MessageActions.tsx` - 消息操作菜单

### Step 7: 创建统一导出
**文件**: `frontend/src/components/chat/index.ts`
- 统一导出所有组件

### Step 8: 更新对话页面
**文件**: `frontend/src/app/chat/[sessionId]/page.tsx`
- 使用新的 ChatPanel 组件

### 目录结构
```
frontend/src/
├── types/
│   ├── message.ts
│   └── agent.ts
├── lib/
│   ├── cn.ts
│   └── utils.ts
├── stores/
│   └── conversationStore.ts
└── components/chat/
    ├── index.ts
    ├── ChatPanel.tsx
    ├── MessageList.tsx
    ├── InputArea.tsx
    ├── ProgressIndicator.tsx
    ├── BrowserStateAlert.tsx
    ├── StopExecutionStatus.tsx
    ├── MessageActions.tsx
    └── Message/
        ├── index.tsx
        ├── UserMessage.tsx
        ├── AgentMessage.tsx
        ├── SystemMessage.tsx
        ├── TPAORBlock.tsx
        ├── OutputCard.tsx
        └── ConfirmationBlock.tsx
```

### 依赖安装
```bash
cd frontend
npm install clsx tailwind-merge
```

### 功能特性
1. **空状态** - 显示欢迎页面和品牌快捷按钮
2. **消息展示** - 用户/Agent/系统消息区分样式
3. **TPAOR 状态** - 可折叠的 Thought/Plan/Action/Observation 块
4. **执行进度** - 进度条、子任务、预计剩余时间
5. **产出卡片** - 报告/图表/数据表/选择确认卡片
6. **确认请求** - 选项按钮、快捷回复
7. **输入区域** - 自动调整高度、快捷键支持
8. **浏览器状态** - 登录提示、操作引导
9. **停止状态** - 已完成/未完成阶段展示、继续/重试/保存按钮
10. **消息操作** - 复制、编辑、回退、删除

请确认此计划后，我将开始执行具体的代码实现。
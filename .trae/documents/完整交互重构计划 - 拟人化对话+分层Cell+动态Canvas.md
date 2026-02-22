## 实现计划：Specta AI TPAOR 交互系统

基于 `Specta-AI-UI-Design-Specification.md` 设计规范，实现分层 Cell 式的 TPAOR 交互系统。

### Phase 1: 前端核心组件开发 (P0)

**1.1 TPAORCard 组件**
- 五阶段卡片：思考(紫) / 规划(蓝) / 行动(橙) / 观察(绿) / 回复(靛蓝)
- 左侧 3px 彩色边框标识
- 圆角 8px，背景 #1A1A1A
- 可折叠/展开，200ms ease-out 动画
- 流式文本输出支持

**1.2 ProgressIndicator 组件**
- 步骤列表展示（完成✓/进行中○/等待○）
- 状态颜色：绿色/橙色/灰色
- 支持子步骤嵌套展示

**1.3 ConfirmationCard 组件**
- 品牌色边框高亮 (rgba(99, 102, 241, 0.1) 背景)
- 主按钮 + 次要按钮样式
- 自动滚动到底部
- 支持键盘操作 (Enter/Esc)

**1.4 AgentCallIndicator 组件**
- 显示调用的 Agent 名称和状态
- 展示输入参数摘要
- 运行中旋转动画

### Phase 2: Chat 窗口重构

**2.1 消息流结构**
```
┌─────────────────────────────────────┐
│ 👤 用户消息                          │
├─────────────────────────────────────┤
│ 🤖 Agent 回复                        │
│   ┌─────────────────────────────┐   │
│   │ [TPAORCard-思考]            │   │
│   │ [TPAORCard-规划]            │   │
│   │ [AgentCallIndicator]        │   │
│   │ [ProgressIndicator]         │   │
│   │ [TPAORCard-观察]            │   │
│   │ [ConfirmationCard]          │   │
│   │ [TPAORCard-回复]            │   │
│   └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

**2.2 流式输出效果**
- 打字机效果逐字显示
- 支持 Markdown 渲染
- 代码块语法高亮

### Phase 3: Canvas 动态面板

**3.1 布局实现**
- 右侧固定 480px 宽度
- 默认折叠，点击卡片展开
- 展开/折叠动画 300ms

**3.2 内容视图**
- 报告视图：Markdown + 指标卡片
- 数据表格：平台对比数据
- 图表视图：Recharts 集成

### Phase 4: 后端 TPAOR 事件流

**4.1 GeneralReActAgent 改造**
- 输出结构化 TPAOR 事件
- 每个阶段 yield AgentEvent
- 用户确认点状态管理

**4.2 WebSocket 事件优化**
- `tpaor_update`: 阶段更新
- `execution_progress`: 执行进度
- `output_ready`: 输出就绪
- `confirmation_request`: 确认请求

### Phase 5: Prompt 优化

**5.1 GeneralReActAgent Prompt**
- 拟人化自然语言风格
- TPAOR 各阶段输出规范
- 用户确认文案模板

---

请确认此计划后，我将开始执行代码实现。
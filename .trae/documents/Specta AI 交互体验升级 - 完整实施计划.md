## 已完成工作

### Phase 1: 前端消息流重构 ✅
1. **新增消息类型定义** - 支持 `execution_step` 类型
2. **ExecutionStepMessage 组件** - 显示每个 Pipeline 步骤的状态、日志、结果
3. **重构 AgentMessage 组件** - Manus 风格 Cell 层级设计
   - 主回复内容（白色背景，突出显示）
   - 思考/规划/动作/观察 Cell（可折叠，层级弱于主回复）
4. **更新 ConfirmationBlock** - 支持步骤确认类型
5. **更新 conversationStore** - 添加执行步骤相关方法

---

## 待实施工作

### Phase 2: Pipeline 逐步执行改造

#### 后端改造

1. **新增 Step-by-Step 执行模式**
   - 修改 `AgentOrchestrator` 支持暂停/继续模式
   - 每步执行完成后发送 `step_completed` 事件
   - 等待用户确认后发送 `step_confirmation` 事件再继续

2. **新增 WebSocket 事件类型**
   - `step_started` - 步骤开始
   - `step_completed` - 步骤完成，附带结果
   - `step_failed` - 步骤失败
   - `step_waiting_confirmation` - 等待用户确认
   - `step_log` - 步骤执行日志（流式）

3. **修改 GeneralReActAgent**
   - 支持在每步之间检查是否需要暂停
   - 发送详细的步骤日志

#### 前端改造

1. **更新 useWebSocket hook**
   - 监听新的步骤相关事件
   - 调用 store 方法更新执行步骤状态

2. **更新 ChatPanel 组件**
   - 处理步骤确认回调
   - 发送继续/跳过/重试命令

### Phase 3: Canvas 动态交互增强

1. **三栏布局重构**
   - 左侧：项目/会话列表（可折叠）
   - 中间：Chat 区域
   - 右侧：Canvas 区域（动态展开）

2. **Canvas 触发机制**
   - 点击 Chat 中的输出卡片 → 右侧展开 Canvas
   - 支持多 Tab 切换
   - Canvas 头部添加操作按钮（复制、分享、下载）

3. **Canvas 内容类型增强**
   - 报告：Markdown 渲染 + 导出 PDF
   - 图表：交互式图表
   - 数据表：可排序、筛选的表格

### Phase 4: 视觉与动效升级

1. **流式输出效果**
   - Agent 回复逐字显示（打字机效果）
   - 思考过程实时流式展示

2. **Cell 展开/收起动画**
   - 使用 Framer Motion 实现平滑动画

3. **Canvas 滑入滑出动画**
   - 从右侧滑入效果

---

## 实施建议

由于这是一个较大的改造，建议按以下顺序实施：

1. **立即实施** - Phase 2 后端改造（支持逐步执行）
2. **并行实施** - Phase 2 前端改造 + Phase 3 Canvas 增强
3. **最后实施** - Phase 4 动效优化

**预计总时间：5-7 天**

---

## 需要确认

1. 是否现在开始 Phase 2 后端改造？
2. 是否需要我先出详细的设计文档或原型？
3. 后端 Pipeline 当前执行逻辑是否需要我详细分析后再改造？
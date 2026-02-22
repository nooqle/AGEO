## 当前状态回顾

Phase 1 和 Phase 2 已完成：
- ✅ 消息流重构 - ExecutionStepMessage、AgentMessage Cell 层级
- ✅ Pipeline 逐步执行 - StepByStepOrchestrator 后端改造

---

## Phase 3: Canvas 动态交互增强

### 3.1 三栏布局重构

**目标：** 参考 AnyGen，实现左侧项目栏 + 中间 Chat + 右侧 Canvas

**改造内容：**

1. **新增左侧项目栏组件 (ProjectSidebar)**
   - 显示会话/项目列表
   - 可折叠/展开
   - 新建项目按钮
   - 项目历史记录

2. **重构 AppLayout 组件**
   - 三栏布局：Sidebar (可折叠) + Chat + Canvas
   - 响应式适配：移动端 Sidebar 变为抽屉
   - 动画过渡效果

3. **更新 Canvas 触发机制**
   - 点击 OutputCard → 右侧 Canvas 滑入
   - 点击 Chat 中的结果区域 → 展开 Canvas
   - 支持多 Tab 切换

### 3.2 Canvas 操作按钮增强

**目标：** 添加复制、分享、下载功能

**改造内容：**

1. **更新 CanvasHeader 组件**
   - 添加复制按钮（复制内容到剪贴板）
   - 添加分享按钮（生成分享链接）
   - 优化下载按钮（PDF/Excel）

2. **新增 Canvas 工具栏**
   - 固定在 Canvas 底部
   - 快速操作按钮

### 3.3 Canvas 内容类型增强

**目标：** 支持更多内容展示

**改造内容：**

1. **新增 Markdown 渲染组件**
   - 支持代码高亮
   - 支持表格
   - 支持图片

2. **优化图表组件**
   - 交互式图表（hover 显示数值）
   - 图表类型切换

3. **优化数据表格组件**
   - 排序功能
   - 筛选功能
   - 分页功能

---

## Phase 4: 视觉与动效升级

### 4.1 流式输出效果

**目标：** Agent 回复逐字显示

**改造内容：**

1. **新增 useTypewriter hook**
   - 逐字显示文本
   - 可配置打字速度
   - 支持暂停/继续

2. **更新 AgentMessage 组件**
   - 主回复内容使用打字机效果
   - 支持跳过动画

### 4.2 Cell 展开/收起动画

**目标：** 平滑的展开/收起效果

**改造内容：**

1. **更新 TPAOR Cell 组件**
   - 使用 Framer Motion AnimatePresence
   - 高度动画过渡
   - 内容淡入淡出

### 4.3 Canvas 滑入滑出动画

**目标：** 从右侧滑入效果

**改造内容：**

1. **更新 CanvasPanel 组件**
   - 滑入动画
   - 滑出动画
   - 遮罩层动画

2. **更新 AppLayout 布局动画**
   - Chat 区域宽度变化动画
   - Canvas 区域宽度变化动画

---

## 实施计划

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| Phase 3.1 | 三栏布局重构 | 1-2 天 |
| Phase 3.2 | Canvas 操作按钮 | 0.5 天 |
| Phase 3.3 | Canvas 内容增强 | 1-2 天 |
| Phase 4.1 | 流式输出效果 | 0.5-1 天 |
| Phase 4.2 | Cell 动画 | 0.5 天 |
| Phase 4.3 | Canvas 动画 | 0.5 天 |

**总计：4-7 天**

---

## 建议实施顺序

1. **Phase 3.1** - 三栏布局（基础架构）
2. **Phase 3.3** - Canvas 内容增强（功能）
3. **Phase 3.2** - Canvas 操作按钮（细节）
4. **Phase 4** - 所有动效（体验优化）

这样可以先完成功能，再优化体验。
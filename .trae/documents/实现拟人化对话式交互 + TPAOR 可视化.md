## 目标

实现设计文档 v2.0 中描述的拟人化对话式交互，包括 TPAOR 可视化、流式输出、产出卡片和动态 Canvas。

## 一、前端组件修改

### 1. 布局架构调整

**文件**: `src/app/chat/[sessionId]/page.tsx`

* 实现三种布局状态：纯对话态(100%)、分栏态(50%+50%)、聚焦态(35%+65%)

* Canvas 按需展开/收起逻辑

* 响应式适配

### 2. 对话消息组件重构

**文件**: `src/components/chat/ChatMessage.tsx` (新建)

* **用户消息**: 右侧气泡，显示时间

* **Agent 普通回复**: 左侧头像，Markdown 渲染，反馈按钮

* **TPAOR 执行消息**: 可折叠的 思考/规划/行动/观察 面板

  * 思考：💭 折叠状态，可展开查看

  * 规划：📋 折叠状态，显示执行步骤

  * 行动：⚡ 默认展开，显示进度条和流式输出

  * 观察：✅ 显示执行结果

* **产出内容卡片**: 带 \[→] 按钮，点击展开 Canvas

* **确认消息**: 选项按钮，支持点击选择

### 3. 流式输出效果

**文件**: `src/components/chat/StreamingText.tsx` (新建)

* 逐字显示效果（类似打字机）

* 支持 Markdown 实时渲染

* 光标闪烁效果

### 4. Canvas 组件增强

**文件**: `src/components/canvas/CanvasPanel.tsx` (重构)

* 顶部标题栏：内容标题 + 操作按钮(下载/展开/关闭)

* 内容展示区：支持 Report/Chart/Table/Selection 类型

* 底部操作栏：确认/返回/跳过按钮

* 动画：从右侧滑入/滑出

### 5. 输入区域状态

**文件**: `src/components/chat/ChatInput.tsx`

* 默认状态：输入框 + 附件/语音/设置按钮

* 执行中状态：显示"Agent 正在执行..." + 停止按钮

## 二、后端 Prompt 优化

### 1. General ReAct Agent Prompt

**文件**: `src/prompts/general_react_agent.py`
优化 LLM 回复风格：

* **开始执行**: "收到！我来帮您\[任务]。首先让我思考一下..."

* **思考过程**: 自然语言描述分析思路

* **规划输出**: "我已经规划好了步骤：1... 2... 3..."

* **执行中**: "正在\[动作]，请稍等..."

* **成功完成**: "太好了！我已经完成了\[任务]。结果如下：\n\n\[Markdown格式]\n\n您可以\[点击卡片查看详情/继续下一步]"

* **执行失败**: "不好意思，\[任务]遇到了问题。\[原因]。我可以\[重试/跳过]，或者请您\[补充信息]"

* **建议下一步**: "基于当前结果，我建议您可以：\[选项A/B/C]。您希望怎么做？"

### 2. 各 Agent Prompt 统一

* **A1 (BrandCompetitionAgent)**: 流式输出分析过程

* **A2 (MarketingPersonaAgent)**: 流式输出生成过程

* **A3 (QuestionSimulationAgent)**: 流式输出问题生成

* **A4 (FetchAgent)**: 实时返回抓取进度

* **A5 (DataAnalyticsAgent)**: 流式输出分析结论

## 三、WebSocket 事件优化

### 事件类型设计

```typescript
// 流式文本事件
interface StreamingTextEvent {
  type: 'streaming_text';
  cellId: string;      // 所属 Cell ID
  text: string;        // 本次推送的文本片段
  isComplete: boolean; // 是否完成
}

// Cell 状态事件
interface CellStateEvent {
  type: 'cell_state';
  cellType: 'thinking' | 'planning' | 'action' | 'observation' | 'reply';
  status: 'pending' | 'streaming' | 'complete';
  content: string;
  metadata?: {
    progress?: number;
    agentId?: string;
    outputReady?: boolean;
  };
}

// 产出卡片事件
interface OutputCardEvent {
  type: 'output_card';
  title: string;
  summary: string;
  data: any;
  actions: Array<{ label: string; value: string }>;
}

// Canvas 展开事件
interface CanvasOpenEvent {
  type: 'canvas_open';
  contentType: 'report' | 'chart' | 'table' | 'selection';
  data: any;
}
```

## 四、实施步骤

### Phase 1: 基础组件 (2-3 小时)

1. 创建 StreamingText 组件
2. 重构 ChatMessage 组件支持 TPAOR
3. 创建 OutputCard 组件
4. 调整页面布局支持三种状态

### Phase 2: Canvas 重构 (2-3 小时)

1. 重构 CanvasPanel 组件
2. 实现滑入/滑出动画
3. 支持多种内容类型

### Phase 3: WebSocket 集成 (1-2 小时)

1. 前端集成新事件类型
2. 后端发送流式事件

### Phase 4: Prompt 优化 (1-2 小时)

1. 优化 General ReAct Agent Prompt
2. 统一各 Agent 输出风格

### Phase 5: 测试验证 (1 小时)

1. 测试完整流程：纽崔莱 → A1 → 确认 → A2 → ...
2. 验证流式输出效果
3. 验证 Canvas 展开/收起

## 五、预期效果

用户输入"纽崔莱"后：

1. Agent 回复："收到！我来帮您分析纽崔莱品牌..."
2. 显示 \[思考 Cell] 流式输出分析思路
3. 显示 \[规划 Cell] 展示执行步骤
4. 显示 \[行动 Cell] 调用 A1，流式输出执行过程
5. 显示 \[观察 Cell] 展示品牌信息摘要
6. Agent 回复："太好了！已完成品牌信息收集..." + 产出卡片
7. 用户点击卡片 → Canvas 展开显示详情
8. Agent 建议："接下来可以生成用户画像，是否继续？"

参考设计：

* Claude Artifacts 的对话+预览双栏布局

* Manus 的任务执行过程可视化

* 设计文档 v2.0 的完整规范


## 核心目标
实现真正的AI Native交互：LLM主导，界面辅助，让用户Wow出来。

## 当前严重问题确认

### 1. 色彩系统混乱（必须统一）
- ChatPanel第117行：`bg-white` - 整个聊天面板是白色！
- InputArea：输入框是`bg-white`、`bg-gray-50`
- TPAORBlock：使用`bg-purple-50`等浅色（不是设计规范的深色）
- 只有AppLayout第29行：`bg-[#0D0D0D]`是深色

**结果**：界面一半是深色一半是浅色，极其丑陋。

### 2. ProgressIndicator完全错误
当前：一个巨大的面板，占用大量空间，抢了LLM回复的风头。

您要的效果：
```
┌─────────────────────────────┐
│ ⟳ 正在分析... 2/5         ▶ │  ← 小小一行，低调
└─────────────────────────────┘
```

### 3. TPAOR没有时序逻辑
当前：所有阶段一次性全部渲染，只是静态列表。

您要的效果：
- 思考（展开1.5秒→自动折叠）→规划（展开1.5秒→自动折叠）→...
- 后台静默更新
- 用户随时可点击展开查看详情

### 4. 缺少中央状态机
Store层没有控制"阶段推进"和"自动折叠时序"的逻辑。

---

## 重构计划（每一步都精确匹配期望）

### Phase 1: 统一深色主题（1天）
**目标**：所有组件使用设计规范的CSS变量，彻底消除浅色元素。

**具体修改**：
1. **ChatPanel.tsx** 第117行
   - `bg-white` → `bg-[#0D0D0D]`
   - 连接状态指示器：`bg-amber-50` → 深色主题适配
   - 停止状态：`bg-amber-50` → 深色主题适配

2. **InputArea.tsx** 第90-122行
   - `bg-white` → `bg-[#1A1A1A]`
   - `bg-gray-50` → `bg-[#1A1A1A]`
   - `border-gray-200` → `border-[#333333]`
   - 聚焦状态：`focus-within:bg-white` → `focus-within:bg-[#262626]`

3. **TPAORBlock.tsx** 第16-71行
   - `bg-purple-50` → `bg-[#1A1A1A]` + 紫色边框
   - `bg-blue-50` → `bg-[#1A1A1A]` + 蓝色边框
   - 所有浅色背景全部替换为深色

4. **MessageList.tsx** EmptyState
   - `text-gray-900` → `text-[#FFFFFF]`
   - `text-gray-500` → `text-[#A3A3A3]`
   - 品牌按钮：`bg-white` → `bg-[#1A1A1A]`

**验收标准**：
- 截图整个界面，没有任何白色/灰色浅色元素
- 所有文字在深色背景上清晰可读

---

### Phase 2: 重写ProgressIndicator为迷你版本（1天）
**目标**：小巧、低调、可展开，不抢LLM风头。

**设计规格**：
```
┌────────────────────────────────────────┐
│ ⟳ 正在分析... 2/5                   ▶ │  ← 高度32px，一行
└────────────────────────────────────────┘

点击展开后：
┌────────────────────────────────────────┐
│ ✓ 分析完成 · 5/5                    ▼ │
├────────────────────────────────────────┤
│ ✓ 品牌信息采集                    完成 │
│ ✓ 竞品分析                        完成 │
│ ○ 用户画像生成                  进行中 │
│ ○ 问题模拟                        等待 │
└────────────────────────────────────────┘
```

**实现要点**：
1. 默认状态：单行，高度32px，文字`text-[#737373]`
2. 展开状态：显示详细步骤列表
3. 自动折叠：如果用户没有交互，保持折叠状态
4. 静默更新：后台执行时，数字自动更新（2/5 → 3/5）

**文件修改**：
- `ProgressIndicator.tsx` 完全重写
- `ChatPanel.tsx` 第139-145行：调整Progress位置到消息流中

**验收标准**：
- Progress只占一行，不占用大量空间
- 可以展开/折叠查看详情
- 执行时数字自动更新

---

### Phase 3: 实现TPAOR时序状态机（2天）
**目标**：真正的"思考→规划→行动→观察→回复"时序推进。

**状态机设计**：
```typescript
interface TPAORState {
  phase: 'idle' | 'thought' | 'plan' | 'action' | 'observation' | 'response';
  content: string;
  isExpanded: boolean;
  autoCollapseTimer: NodeJS.Timeout | null;
  history: {
    thought: { content: string; timestamp: number; isExpanded: boolean };
    plan: { content: string; timestamp: number; isExpanded: boolean };
    action: { content: string; timestamp: number; isExpanded: boolean };
    observation: { content: string; timestamp: number; isExpanded: boolean };
    response: { content: string; timestamp: number; isExpanded: boolean };
  };
}
```

**时序逻辑**：
1. 用户发送消息 → phase: 'thought', isExpanded: true
2. 1.5秒后 → autoCollapse thought, expand plan
3. 1.5秒后 → autoCollapse plan, expand action
4. action阶段 → 显示Agent调用和Progress（迷你版）
5. action完成 → expand observation
6. 1.5秒后 → autoCollapse observation, expand response
7. response阶段 → 流式输出LLM回复

**文件修改**：
1. `conversationStore.ts`
   - 重写CurrentTPAOR接口
   - 添加phase推进逻辑
   - 添加autoCollapse时序控制

2. `TPAORCard.tsx`
   - 接收phase状态
   - 根据isExpanded控制展开/折叠
   - 添加折叠动画

3. `AgentMessage.tsx`
   - 按phase顺序渲染TPAOR卡片
   - 当前phase展开，其他折叠

**验收标准**：
- 可以看到阶段自动推进（思考→规划→行动...）
- 每个阶段展开1.5秒后自动折叠
- 可以随时点击展开查看历史阶段
- response阶段流式输出回复

---

### Phase 4: 整合到消息流（1天）
**目标**：Progress和TPAOR成为消息的一部分，不是独立面板。

**交互流程**：
```
用户: 瑞幸咖啡

[Progress迷你行] ⟳ 正在分析... 1/5 ▶

Agent: 让我来分析一下瑞幸咖啡在各AI平台上的表现。
      （流式输出中...）

[点击Progress展开]
┌────────────────────────────────────────┐
│ ● 思考  ▼                              │
│   分析用户意图：了解瑞幸咖啡品牌声量...  │
│ ● 规划  ▼                              │
│   1. 品牌信息采集 2. 竞品分析...        │
│ ● 行动  ▼                              │
│   ⟳ A1 品牌竞品分析 Agent 运行中        │
└────────────────────────────────────────┘
```

**文件修改**：
- `AgentMessage.tsx`：整合Progress到消息中
- `MessageList.tsx`：调整消息间距

**验收标准**：
- Progress出现在Agent消息中，不是独立面板
- 展开后可以看到完整的TPAOR流程
- 界面简洁，重点在LLM回复

---

### Phase 5: 细节打磨（1天）
1. **动画优化**
   - 阶段切换：300ms ease-out
   - 展开/折叠：200ms ease-out
   - 流式文本：打字机效果

2. **色彩微调**
   - 当前phase边框高亮
   - 完成phase显示绿色✓
   - 进行中phase显示旋转图标

3. **交互细节**
   - 鼠标悬停显示展开按钮
   - 点击阶段标题展开/折叠
   - 快捷键支持（Enter确认、Esc取消）

---

## 验收清单

### 视觉验收
- [ ] 整个界面统一深色主题，无浅色元素
- [ ] 文字层级清晰（主文字白色，次要文字灰色）
- [ ] TPAOR阶段色彩正确（紫/蓝/橙/绿/靛蓝）

### 交互验收
- [ ] 用户发送消息后，TPAOR阶段自动推进
- [ ] 每个阶段展开1.5秒后自动折叠
- [ ] 可以随时点击展开查看详情
- [ ] Progress迷你行静默更新
- [ ] LLM回复流式输出，打字机效果

### 性能验收
- [ ] 动画流畅，无卡顿
- [ ] 阶段切换自然，不生硬
- [ ] 大量消息时滚动流畅

---

## 风险规避

1. **不再使用任何Tailwind浅色类**
   - 禁用：`bg-white`, `bg-gray-50`, `bg-gray-100`等
   - 只用：`bg-[#0D0D0D]`, `bg-[#1A1A1A]`, `bg-[#262626]`

2. **不再做大面板**
   - Progress必须是一行
   - TPAOR默认折叠，不占空间

3. **必须有自动时序**
   - 不能等用户操作才切换阶段
   - 自动推进，自动折叠

4. **每完成一个Phase必须验收**
   - 截图对比设计规范
   - 确认符合期望后再进入下一阶段

---

请确认这个计划，确认后我将严格按照此计划执行，每一步都先给您确认后再继续。
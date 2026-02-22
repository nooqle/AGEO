## 执行计划

### Step 1: 创建 Canvas 面板容器
**文件**: `frontend/src/components/canvas/CanvasPanel.tsx`
- 主容器组件
- 根据 content type 渲染不同内容（report/chart/dataTable/selection）
- 包含 CanvasHeader、CanvasTabs、内容区、CanvasActions

### Step 2: 创建 CanvasHeader
**文件**: `frontend/src/components/canvas/CanvasHeader.tsx`
- 标题显示
- 导出按钮（PDF/Excel）
- 展开/收起按钮（切换 split/focused 模式）
- 关闭按钮

### Step 3: 创建 CanvasTabs
**文件**: `frontend/src/components/canvas/CanvasTabs.tsx`
- 多内容时显示 Tab 切换
- 点击切换 active content

### Step 4: 创建内容组件

**ReportContent.tsx** - 报告内容展示
- Markdown 渲染
- 支持导出

**ChartContent.tsx** - 图表内容
- 使用 Recharts 渲染图表
- 支持交互

**DataTableContent.tsx** - 数据表
- 表格展示
- 支持排序、筛选

**SelectionContent.tsx** - 选择确认界面
- 画像选择卡片
- 星级推荐
- 关联薄弱点提示
- 选择/跳过按钮

### Step 5: 创建 CanvasActions
**文件**: `frontend/src/components/canvas/CanvasActions.tsx`
- 底部操作栏
- 确认选择按钮
- 跳过按钮

### Step 6: 创建 MobileCanvasSheet
**文件**: `frontend/src/components/canvas/MobileCanvasSheet.tsx`
- 移动端全屏弹出层
- 下拉关闭手势
- 遮罩层

### 组件结构
```
frontend/src/components/canvas/
├── CanvasPanel.tsx            # Canvas 面板容器
├── CanvasHeader.tsx           # 顶部栏
├── CanvasTabs.tsx             # Tab 切换
├── contents/
│   ├── ReportContent.tsx      # 报告类型
│   ├── ChartContent.tsx       # 图表类型
│   ├── DataTableContent.tsx   # 数据表类型
│   └── SelectionContent.tsx   # 选择确认类型
├── CanvasActions.tsx          # 底部操作栏
└── MobileCanvasSheet.tsx      # 移动端弹出层
```

### 依赖
- Framer Motion - 动画
- Lucide React - 图标
- Recharts - 图表
- Radix UI - 基础组件

请确认此计划后，我将开始执行具体的代码实现。
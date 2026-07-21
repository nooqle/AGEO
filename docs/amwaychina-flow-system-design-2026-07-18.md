# AmwayChina Flow 系统设计 v3：侧边栏 + 品牌生产线画布

日期：2026-07-18（v3，根据用户反馈修订）
状态：**Phase 1 + Phase 2 已实施完成**（2026-07-18）
范围：/amwaychina 控制台（作为全平台新范式的首个落地）

---

## 一、战略与形态

**放弃 Chat-First，Flow 成为系统核心。** 但首用户默认不接触画布——通过**侧边栏导航**实现渐进披露：

- 默认落地 **品牌圈层**（现有页面，交互设计保留不动）。
- 想看流程的人点第二个 tab 进入 **品牌生产线** 画布。
- 复杂度永远在那里，但从不挡路。

## 二、信息架构：控制台侧边栏

```
┌──────────┬────────────────────────────────────┐
│ ◉ 品牌圈层 │                                    │
│ ○ 品牌生产线│         （主内容区）                │
│ ○ 设置    │                                    │
└──────────┴────────────────────────────────────┘
```

| Tab | 内容 | 说明 |
|---|---|---|
| **品牌圈层**（默认） | 现有圈层图 + 报告页 | **完全保留现有交互**，含播放键、运行设置对话框、观察周期 |
| **品牌生产线** | Langflow/ComfyUI 式画布 | 本文档主体。命名逻辑：圈层是成果，生产线是过程——原料（问题集/词库）→ 加工（采集/抽取）→ 成品（图谱/报告） |
| **设置** | **占位入口，本期不建设** | 未来放真实系统设置：账号信息、登录信息、权限信息等。优先级低，先保留入口 |

路由：`/amwaychina`（圈层，默认）、`/amwaychina/flow`、`/amwaychina/settings`。侧边栏为控制台级布局，三个页面共享。

## 三、品牌生产线画布

### 3.1 画布能力（对标 Langflow/ComfyUI）

- 平移、缩放、框选、小地图（minimap）。
- **节点自由拖拽排布**：用户可随意移动节点调整布局，位置持久化（localStorage，按品牌实体记忆）；提供"重置布局"恢复默认排布。首期连线关系（拓扑）固定，不可改接。
- 节点有**输入口/输出口**，连线表示数据流向。
- 节点可点选 → 右侧配置面板；可**替换变体**（见 3.4）。
- **运行时动态效果**：节点状态灯 + 连线流动动画（见 3.5）。
- **产出物可点击查看**（见 3.6）。

### 3.2 节点图谱（首期固定拓扑）

```
┌──────────┐   ┌──────────┐
│ 问题集    │   │ 实体词库  │        （资产节点，品牌色描边）
└─────┬────┘   └─────┬────┘
      └───────┬──────┘
              ▼
        ┌──────────┐      ┌─ Kimi ─┐
        │ 答案采集  │ ──── ├─ DeepSeek ─┤   （通道子节点，各自独立成败）
        └─────┬────┘      ├─ 豆包 ─┤
              │           └─ 元宝 ─┘
              ▼ 产出: 答案原文
        ┌──────────┐
        │ 实体抽取  │ ── 产出: 抽取实体（回写词库）
        │ 与校准    │
        └─────┬────┘
              ▼
        ┌──────────┐
        │ 图谱构建  │ ── 产出: 圈层图（点击 → 跳转品牌圈层 tab）
        └─────┬────┘
              ▼
        ┌──────────┐
        │ 报告生成  │ ── 产出: 报告原文
        └──────────┘
```

### 3.3 节点类型学

| 类型 | 视觉 | 实例 | 可做的操作 |
|---|---|---|---|
| **资产节点** | 圆角方形，品牌色描边 | 问题集、实体词库 | 点击查看内容；替换变体（默认集 ↔ 上传 ↔ 历史集） |
| **执行节点** | 胶囊形，中性色 | 采集、抽取校准、图谱构建、报告生成 | 点击配置参数；查看运行统计 |
| **通道子节点** | 小圆点，挂在采集节点右侧 | Kimi / DeepSeek / 豆包 / 元宝 | 独立状态灯；点击看该平台答案原文 |
| **产出物** | 节点上的输出端口徽标 | 答案原文、抽取实体、圈层图、报告原文 | 点击 → 右侧抽屉查看原文/跳转 |

### 3.4 节点编辑与替换（首期范围）

**编辑**（右侧配置面板，替代并逐步收编现有"运行设置"对话框）：
- 问题集节点：选择 系统默认 / 上传文件 / 历史问题集；显示题数与预览。
- 采集节点：采集方式（浏览器/API）、平台勾选、平台并发说明。
- 实体词库节点：词库统计 + "去设置页编辑"链接（编辑本体留在设置 tab）。
- 报告节点：是否自动生成报告。

**替换**（变体替换，非自由增删）：
- 问题集节点可替换为另一份历史问题集（拓扑不变，换数据绑定）。
- 采集节点可替换采集通道组合（去掉某平台 = 断开该子节点连线，视觉上连线变虚线）。
- **首期不做**：自由拖拽增删节点、自定义拓扑、新节点类型。

### 3.5 运行动态效果

- **触发**：画布顶部有与圈层页一致的"开始运行"按钮（两处入口，同一 action）。
- **节点状态**：等待（灰）→ 运行中（品牌色脉冲 + 边框流光）→ 完成（品牌色填充 + ✓）/ 失败（错误色 + ✗）。
- **连线动画**：数据流经的连线做 dash 流动动画（ComfyUI 式）；当前激活段的连线加粗高亮。
- **通道子节点**：采集阶段 4 个平台圆点各自独立亮灯，谁先回谁先亮，失败单独变红——**这是比文字进度条本质的提升**。
- **数据源**：现有 WebSocket `activeTask.current_stage` + `stage_results_cache` + A4 per-platform 结果，做一层"阶段 → 节点 ID"映射即可，**零后端改动**。
- 运行结束后状态定格，成为"上一次运行的回放"；再次运行重置。

### 3.6 产出物查看

点击节点上的产出徽标，右侧抽屉打开：

| 产出 | 抽屉内容 | 数据源（已有） |
|---|---|---|
| 答案原文 | 按平台分组的问题-回答列表，可展开单条 | evidenceSamples / sourceAppendix |
| 抽取实体 | 本轮抽取的实体及计数，链接到词库 | projection nodes |
| 圈层图 | 不展开抽屉，直接跳转品牌圈层 tab | — |
| 报告原文 | 报告全文渲染（复用报告组件） | AssociationReportPanel |

## 四、技术方案

| 项 | 方案 | 说明 |
|---|---|---|
| 画布库 | **@xyflow/react**（React Flow v12） | 事实标准，支持 React 19，TS 友好，自带 minimap/controls/连线动画/节点拖拽 |
| 布局 | 默认排布 + 用户自由拖拽，位置持久化 localStorage（按实体记忆），可一键重置 | 后期可接 dagre 自动布局 |
| 状态 | 复用 ConsolePage 现有数据 hooks，Flow 页与圈层页共享同一份 projection/run 状态 | 提升到控制台布局层 |
| 侧边栏 | 控制台级 layout 组件，三个 tab 共享 | 动 `app/amwaychina/` 路由结构 |
| 后端 | **零改动**（Phase 1） | 全部数据已有 |

### 分阶段

- **Phase 1（已完成）**：侧边栏三 tab 骨架（设置仅占位）+ 品牌生产线画布（默认布局 + 自由拖拽 + 位置持久化、节点状态灯、连线流动动画、平台子节点、产出物抽屉、节点配置面板、画布运行按钮）。词库/题库保留在圈层页 tab 内不动。
- **Phase 2（本次）**：见下节"Phase 2 方案"。
- **Phase 3**：自由编排（增删节点、自定义拓扑）+ 新节点类型（内容创作、数据分析）——企业知识系统沉淀。

---

## 四之补、Phase 2 方案（2026-07-18，用户已确认）

四组：A 运行态易用性 / B 节点配置 / C 统一 header / D 质感打磨。

### A 组：运行态易用性

| # | 项 | 实现 |
|---|---|---|
| A1 | 运行中量化进度 | active 节点显示实时计数：采集"已采 N 条答案"、抽取"已识别 N 个实体"。数据已有（answerCount / liveSignalCount / projectionNodes） |
| A2 | minimap 状态着色 | `nodeColor` 按节点状态映射（灰/品牌色/成功/失败），minimap 成为全局状态总览 |
| A3 | 失败节点直接重试 | failed 节点详情面板显示"重新运行"按钮（复用 onQuickRun） |
| A4 | 抽屉打开画布让位 | 抽屉打开时画布视口平滑偏移（fitView padding / setCenter），右侧节点不被 560px 抽屉遮挡 |
| A5 | 首次进入一次性引导 | 轻提示条"节点可自由拖拽，点击产出徽章查看内容"，localStorage 记忆已读 |

### B 组：节点配置

| # | 项 | 方案 |
|---|---|---|
| B1 | 问题集节点：当前绑定展示 | 面板显示当前问题集（名称+题数+前 3 题预览）+ "更换"入口（跳圈层页自动打开运行设置，复用 openRunSettingsSignal） |
| B2 | 采集节点：采集方式展示 | 显示浏览器/API 采集 + 跳转修改（同上）。**不做内嵌编辑器**：运行设置状态在 Dashboard 内，内嵌需提升到 ConsolePage 层动 790 行核心逻辑，跳转体验等效 |
| B3 | 平台开关 | 平台子节点可勾选启停；停用节点变灰、连线变虚线；选择持久化（localStorage 按实体记忆）；运行时写入 `input_scope.platforms`。**零后端改动**（已核实：input_scope.platforms 已是运行参数，前端原写死 4 平台） |

### C 组：统一 Console header

**问题**：顶栏写在 Dashboard 组件内，切到生产线/设置视图顶栏消失。

**方案**：顶栏提升到 ConsolePage 层，三视图共享；视图头统一版式。

```
┌────────────────────────────────────────────────────┐
│ S Specta AI·安利品牌圈层 │ 视图名 │ ●状态 │ [报告] │  ← Console 级顶栏（三视图共享，sticky）
├────────────────────────────────────────────────────┤
│ 视图头（各视图同款版式：标题左 + 摘要 + 操作右）      │
│  · circle: 品牌联想图谱 + 数据摘要 + 设置并运行      │
│  · flow:   品牌生产线 + 配置摘要 + 重置布局/开始运行 │
│  · settings: 设置 + 副标题                           │
└────────────────────────────────────────────────────┘
```

- 新建 `AmwayConsoleHeader.tsx`：左 Specta AI 标识、中视图名、右运行状态徽章 + 报告按钮。
- 报告按钮在 flow/settings 视图点击 → 跳回 circle 视图 + `openReportSignal` 信号自动打开报告（复用 openRunSettingsSignal 模式）。
- Dashboard 删除自带顶栏；workspace tabs（图谱/词库/问题集）下移内容区顶部（语义上本就是圈层视图内部子导航）。
- Dashboard 接收 `openReportSignal` 触发 openReport。

### D 组：质感打磨

| 部位 | 项 |
|---|---|
| 节点卡片 | 左侧 3px 状态色条；hover 微抬升（translateY(-1px)+阴影加深）；active 边框流光增强；done 右上角小 ✓ |
| 连线 | hover 加粗高亮；节点 hover 时关联连线联动高亮 |
| 徽章 | hover 缩放 + 颜色过渡 |
| 抽屉 | 滑入动画 + 投影层级 |
| 平台开关 | 精致小 toggle（非原生 checkbox） |
| 全局 | 数字 tabular-nums；按钮 focus-visible 环；深浅主题全量检查 |

## 五、明确不做（本期）

- 不做连线改接、不做节点增删（拓扑固定，但节点位置自由）。
- 不动圈层页任何交互；词库/题库仍留在圈层页 tab。
- 设置 tab 只建占位页，不做真实内容。
- 不动后端流水线与数据逻辑。
- 不做多人协作、版本历史。

## 六、已确认的决策

1. **画布库**：@xyflow/react（React Flow v12）。
2. **设置 tab**：占位入口，未来放账号/登录/权限等系统设置。
3. **画布运行按钮**：保留，与圈层页同源 action。
4. **运行设置对话框**：首期保留（圈层页对话框 + 画布配置面板两处可改），画布稳定后再收编。

---

## 七、Phase 1 实施完成记录（2026-07-18）

### 交付文件

| 文件 | 变更 |
|---|---|
| `frontend/src/components/dashboard/AmwayFlowCanvas.tsx` | **新建 ~900 行**，品牌生产线画布主体 |
| `frontend/src/components/dashboard/AmwayAssociationCircleConsolePage.tsx` | 侧边栏三 tab 骨架（`?view=flow|settings` searchParams 单路由视图切换）+ 设置占位页 |
| `frontend/src/components/dashboard/AmwayAssociationCircleDashboard.tsx` | `mergeStageResults`/`buildLiveAssociationProjection` 改为 export；新增 `openRunSettingsSignal` 跨视图打开运行设置对话框 |
| `frontend/src/components/dashboard/AmwayConsoleAssetPanels.tsx` | P0 文案修复（实体词库描述、问题集空状态） |

### 实现要点

- **节点图谱**：问题集 / 实体词库（资产节点）→ 答案采集（+ 4 平台子节点）→ 实体抽取校准 → 图谱构建 → 报告生成，拓扑固定、位置自由。
- **布局持久化**：localStorage key `amway-flow-layout:{entityId}:{centerTerm}`，按品牌实体记忆；「重置布局」清除存储回默认。组件以 `key={flow:entityId:centerTerm}` 重挂载切换实体。
- **运行状态映射**：`activeTask.current_stage`/`activeRun.stage` → 节点状态机（idle/active/done/failed）；A4 → 采集节点 + 平台子节点，A5 → 抽取节点；失败定位到具体节点。
- **连线动画**：数据流经段（source active 或 source done + target active）animated dash 流动 + 品牌色加粗；平台连线固定虚线。
- **产出物抽屉**：右侧 560px 面板，答案原文（按平台分组 details/summary）、抽取实体（按 answer_count 排序表格）、问题列表、报告原文（复用 AssociationReportPanel）、词库说明 + 「前往管理」跳转圈层 tab。
- **派生状态模式**：positions（state）+ nodes（useMemo 派生），规避 react-hooks/set-state-in-effect；运行设置跨视图触发用 render-time 信号比较（非 effect）。

### 验证结果

- `tsc --noEmit` 0 错；`eslint` 0 错。
- Playwright 实测通过：画布完整渲染（节点/平台子节点/产出徽章/minimap）、节点详情面板、运行设置跳转后对话框自动打开、设置占位页、**节点拖拽 → localStorage 持久化 → 刷新保持 → 重置布局恢复默认**。
- 产出物抽屉在有真实运行数据时的展示未覆盖（当前测试账号无数据），待有数据后人工过一眼。

### 与设计文档的偏差

无功能性偏差。实现中平台子节点采用小卡片（图标 + 平台名 + 计数）而非设计稿的"小圆点"，信息量更高；视觉仍属通道子节点层级。

---

## 八、Phase 2 实施完成记录（2026-07-19）

### 交付文件

| 文件 | 变更 |
|---|---|
| `frontend/src/components/dashboard/AmwayConsoleHeader.tsx` | **新建 ~75 行**，三视图共享的全局顶栏（品牌标识 + 视图名 + 运行状态徽章 + 报告按钮三态） |
| `frontend/src/components/dashboard/AmwayAssociationCircleConsolePage.tsx` | 顶栏上提到 Console 层；报告按钮状态自行计算（`consoleProjection`/`periodView`）；`openReportSignal` 信号下传；`createRun` 的 `input_scope.platforms` 改读 `readEnabledFlowPlatforms(entityId)`；设置页改统一视图头 |
| `frontend/src/components/dashboard/AmwayAssociationCircleDashboard.tsx` | 删除自带 `<header>`（顶栏 + workspace tabs + 状态徽章 + 报告按钮）；workspace tabs 下移内容区顶部为 pill 组；`hasReportContent`/`reportQualityPassed` 改 export；新增 `openReportSignal` prop（useEffect + ref 模式触发 `handleReportAction`） |
| `frontend/src/components/dashboard/AmwayFlowCanvas.tsx` | A/B/D 三组全部落地（详见下） |

### 实现要点

**A 组 · 运行态易用性**
- A1 运行中量化副标题：采集节点 active 时显示 `progressMessage`（"已采 N 条答案"），idle 显示 `N/4 个平台`；抽取节点 active 显示 `已识别 N 个实体信号`。
- A2 MiniMap `nodeColor` 按节点状态映射（active→品牌色 / done→品牌描边 / failed→错误色 / idle→浅灰）。
- A3 失败节点详情面板显示"重新运行"主按钮（复用 `onQuickRun`）。
- A4 抽屉让位：`onInit` 存 `ReactFlowInstance` ref，抽屉开关时 `getNodesBounds` + `setCenter(duration: 280)` 平滑偏移视口（偏移量 280px/zoom）。
- A5 首次引导浮层：`<Panel position="top-left">`（必须在 `<ReactFlow>` 内部），localStorage `amway-flow-guide-seen` 记忆已读；lazy useState 初始化规避 `react-hooks/set-state-in-effect`。

**B 组 · 节点配置**
- B1 问题集节点"当前绑定"卡片：`questionSets`（`api.listAmwayQuestionHistory(entityId, 80)`）匹配 `input_scope.uploaded_question_set_id`，显示标题 + 题数 + 前 3 题预览；fallback 为 `uploaded_question_source` 或"系统默认问题集"。"更换问题集"按钮 → `onOpenRunSettings`（跳回 circle 视图 + `openRunSettingsSignal` 自动打开运行设置对话框）。
- B2 采集节点"采集配置"卡片：`fetchModeLabel`（浏览器采集/API 采集）+ `平台通道 N/4 启用` + 已停用名单。"调整采集方式"按钮同上跳转。**未做内嵌编辑器**（运行设置状态在 Dashboard 内，避免动 790 行核心逻辑）。
- B3 平台开关：平台子节点渲染精致小 toggle（`role="switch"`，h-4 w-7）；选择持久化 localStorage `amway-flow-platforms:{entityId}`；`readEnabledFlowPlatforms` 在 `createRun` 时写入 `input_scope.platforms`——**零后端改动**（input_scope.platforms 本已是运行参数，前端原写死 4 平台）。至少保留一个平台；运行中禁切。停用节点 `opacity-45`、连线 `opacity 0.18`。

**C 组 · 统一 Console header**
- 顶栏从 Dashboard 提升到 ConsolePage 层，三视图共享（sticky，视图切换顶栏不动）。
- 报告按钮三态：disabled（运行中/生成中/无数据）/ primary（"生成报告"）/ outline（"查看报告"/"查看待校验报告"）。在 flow/settings 视图点击 → 切回 circle + `openReportSignal++` 信号 → Dashboard useEffect 触发 `handleReportAction`。
- 各视图视图头统一版式：kicker 小标签 + H1 + 副标题 | 右侧操作按钮组（h-10 text-sm），卡片式 section。
- 信号机制两种模式沉淀：**纯 setState 用 render-time 比较**（openRunSettingsSignal），**有副作用的动作用 useEffect + ref 比较**（openReportSignal → handleReportAction 含 async/滚动/API）。

**D 组 · 质感打磨**
- 节点卡片：左侧 3px 状态色条；done 右上角 `CheckCircle2`；hover `-translate-y-px` + `shadow-md`；徽章 `hover:scale-105`；数字 `tabular-nums`。
- 连线：hover 加粗高亮（2.5px 品牌色）；节点 hover 时关联连线联动高亮（`hoveredEdgeId`/`hoveredNodeId`）；style transition。
- 抽屉：圆角卡片（`rounded-2xl border`）+ `amwayFlowDrawerIn` 滑入动画（translateX 28px→0，0.28s cubic-bezier(0.32,0.72,0,1)）。
- 画布卡片化：容器 `px-5 pb-5 pt-3`，ReactFlow `overflow-hidden rounded-2xl border`——修复 Controls/MiniMap 贴屏幕底边问题。
- **深浅主题**：`colorMode="light"` 写死导致深色下 Controls/MiniMap 白底刺眼 → 改 `colorMode={theme}`（复用项目 `useTheme` hook，useSyncExternalStore 响应式）；MiniMap `maskColor` 按主题适配（dark: rgba(0,0,0,0.45)）。

### 验证结果

- `tsc --noEmit` 0 错；`eslint` 0 错。
- Playwright 实测通过（截图归档 `.playwright-cli/phase2/`）：
  - 平台 toggle：点击豆包 → localStorage 写入 `["deepseek","kimi","hunyuan"]`、节点变灰、连线淡化、采集副标题变"3/4 个平台"；恢复后 4/4。
  - B1 问题集"当前绑定"卡片（系统默认问题集 + 更换问题集按钮）；B2 采集"采集配置"卡片（浏览器采集 + 平台通道 4/4 启用 + 调整采集方式按钮）。
  - 抽屉打开画布平滑让位（节点群左移不被遮挡）。
  - 三视图顶栏统一：circle/flow/settings 切换顶栏不动，视图名分别为"品牌圈层/品牌生产线/设置"。
  - 深色主题：修复后 Controls/MiniMap/节点/抽屉全部暗色适配。
- **未覆盖**：顶栏报告按钮的完整链路（当前测试账号无数据，按钮 disabled 不可点；逻辑与已验证的 `openRunSettingsSignal` 同构）；有真实运行数据时的量化进度副标题（A1）与失败重试按钮（A3），待有数据后人工过一眼。

### 与设计文档的偏差

无功能性偏差。B3 停用连线采用整体淡化（opacity 0.18）而非改虚线样式——平台连线本身已是虚线，淡化层次感更清晰。

---

## 九、真实采集实测与修复记录（2026-07-19）

### 采集实测（第一次真实运行）

- 运行：系统默认问题集（16 题）× 4 平台浏览器采集，约 60 分钟完成。
- 结果：21 条有效回答（DeepSeek + 豆包两平台产出；Kimi/元宝该轮 43 条失败）、75 个圈层节点、圈层已生成。
- 运行态设计实测生效：视图头量化进度（"DeepSeek 14/16 完成"）、节点状态灯、平台子节点独立状态、连线品牌色虚线流动、产出徽章实时计数（答案原文 17→21、抽取实体 59→75）、运行完成后"生成报告"按钮变可用。

### 修复 1：React Flow 受控模式 measured 丢失（运行翻转节点消失）

- **现象**：idle→running、running→done 两次状态翻转时画布节点全部 `visibility: hidden`，硬刷新可恢复。
- **根因**：受控模式下 `onNodesChange` 只处理 `position` change、丢弃 `dimensions` change → measured 从未回流 state → nodes 数组重建时丢失 measured → ResizeObserver 自愈链条被并发渲染打断。
- **修复**（`AmwayFlowCanvas.tsx`）：新增 `measuredSizes` state，`dimensions` change 回流，nodes 构造时传 `measured`——React Flow 受控模式标准做法，节点自持完整状态不依赖 RO 自愈时序。

### 修复 2：period view 实时聚合丢失 source_appendix / evidence_samples

- **现象**：徽章"21 条回答"但答案原文抽屉显示"采集完成后显示"（圈层页答案面板同样为空）。
- **根因**：`amway_circle_tracking_service.py` 的 `_period_projection_shell` 外壳不含这两个字段，`_aggregate_projection` 只聚合 nodes/question_bank/sample_scope——run 级 projection 数据完整（196 条证据），period 实时聚合路径丢弃。报告路径 `_build_period_report_artifact` 有完整聚合逻辑，实时路径漏了。
- **修复**：`_aggregate_projection` 复用 `_aggregate_period_items` 聚合两字段（含 evidence→appendix 合并去重，与报告路径语义一致）。
- **测试冲突与裁定**：`test_period_projection_shell_does_not_leak_single_run_derived_fields` 原将两字段列入"禁止残留"名单——该测试防的是单 run 派生字段（report_markdown 等）未经聚合直接残留，而证据字段属于可聚合原始数据，聚合后是新鲜数据。测试已更新：两字段移出残留名单，改为断言聚合结果（evidence_id 带 run_id 前缀 qualified）。
- **验证**：109 个相关测试通过；API 返回 source_appendix 196 条；抽屉按平台分组展示（deepseek 40 条 + doubao 40 条，截断上限 40/平台）。

### 报告生成链路实测

- 顶栏"生成报告"→ 自动跳回圈层视图（openReportSignal 信号链路）→ 真实 LLM 生成 → 按钮变"查看报告"→ 报告页完整渲染（核心判断、统计卡片、三层认知解读、导出报告）。
- 至此 Phase 2 遗留的两个"未覆盖"项（报告按钮链路、真实数据下的运行态）全部实测闭环。

### 截图资产

`.playwright-cli/phase3-run/`：run-check2.png、run-complete-canvas.png、drawer-answers.png（修复前）、drawer-answers-fixed.png（修复后）、report-view.png。

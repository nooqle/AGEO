# /amwaychina 页面体验改版 — 分析与方案

日期：2026-07-17
范围：仅 `/amwaychina` 页面（安利品牌圈层 Console）的前端展示与交互，不动任何数据生成逻辑、不动轨道图布局算法、不动后端。

涉及文件：
- `frontend/src/app/amwaychina/page.tsx`（权限门）
- `frontend/src/components/dashboard/AmwayAssociationCircleConsolePage.tsx`（数据容器，790 行）
- `frontend/src/components/dashboard/AmwayAssociationCircleDashboard.tsx`（页面骨架，1398 行）
- `frontend/src/components/dashboard/AmwayAssociationCircleDashboardViews.tsx`（图谱+报告，6749 行）
- `frontend/src/components/dashboard/AmwayConsoleAssetPanels.tsx`（词库/题库，938 行）

---

## 一、现状结构

```
Header (sticky)
├─ logo + "安利品牌圈层"
├─ workspace nav：品牌图谱 / 实体词库 / 问题集管理
└─ 状态 pill（回答数/节点数） + [生成报告] 实心主按钮

Hero 控制卡
├─ 左：eyebrow + H1"品牌联想图谱" + 5 个 InfoPill（问题/计划平台/有效平台/回答/节点）
├─ 右：分析对象 chips（安利/安利中国/纽崔莱，2 个禁用）
│      + 运行快照摘要 + [设置并运行] 实心主按钮
└─ 底部：观察周期选择（5 选项 + 自定义日期）

图谱卡
├─ header：H2 + 图例 6 pills + 实时进度条(6步) + 轨道筛选条 ｜ 模式切换 + 2 个 InfoPill
├─ 轨道图本体（中心品牌 + 3 轨道 + 节点 + 左下风险入口圆钮）
└─ "本周先看" 三列（风险先处理/竞品替代/机会先拉近）

报告区
└─ ReportGenerationGate 卡 → AssociationReportPanel（长文报告）
```

## 二、核心问题（按用户目标归类）

### A. 信息层级不清 — 用户不知道先看哪

1. **两个实心主按钮竞争**：Header 的"生成报告"与 Hero 的"设置并运行"同为品牌绿实心按钮，同屏争夺主行动。
2. **数据重复 3 次**：回答数/节点数出现在 Header 状态 pill、Hero 5 pills、图谱卡右上 2 pills。
3. **图谱卡 header 堆 5 组控件**：标题、图例（6 pills）、进度条、筛选条、模式切换 + InfoPills。其中**图例与筛选条视觉形态几乎相同**（都是灰底条+胶囊），"说明"与"可操作"混淆。
4. **三个风险入口竞争**：模式切换"风险与竞争"、地图左下红色圆钮、"本周先看"里的"查看风险关系"按钮。
5. **"本周先看"位置与角色矛盾**：承担"最重要结论"却放在地图下方，且用 `border-b`（516-591 行）像地图脚注。
6. **风险圆钮语义不清**：联想模式下左下 24px 红圆与中心 40px 绿圆造型雷同，像"另一个中心"。

### B. 质感平 — 层级靠 8% 透明度边框硬撑

7. **卡片配方单一**：全页面 20+ 处 `rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]`，无阴影梯度、无 hover 反馈。
8. **卡片比页面暗**：页面 `bg-secondary`、卡片 `bg-primary`（深色主题下 #171B18 vs #101311），卡片呈"凹陷"感，与常规"卡片浮于页面"相反。
9. **控件规范不统一**：按钮圆角 rounded-lg/xl/2xl 混用、高度 h-9/h-10/h-11 混用、每个组件手写样式；6 个"指标格"组件、4 种"左竖条卡"、3 种胶囊各自重复实现。
10. **硬编码颜色脱离变量体系**：live 浮层米色 `rgba(250,248,242,0.98)`（1512 行）、报告 takeaway 底色 `rgba(31,122,107,0.18)` 等（5231/5238/5245/5499 行）、平台色 hex（5111-5115 行），换肤/暗色下突兀。

### C. 交互反馈不足

11. **节点可点感弱**：44px 按钮内 10-29px 色点，hover 只有阴影微变，色点不放大不变色。
12. **选中态语义错位**：选中 ring 统一用品牌绿，机会轨（黄）节点选中时绿 ring 与轨道色不一致。
13. **筛选"预览"与"激活"难区分**：hover 预览与点击激活共用同一套颜色（827 行）。
14. **中心品牌大圆是按钮但无 affordance**：点击=取消选中，无 hover 提示，看起来是装饰。
15. **周期切换反馈弱**：只有一行小字"正在更新图谱..."，图谱区无 skeleton/过渡。
16. **确认模式不一致**：词库删除用原生 `window.confirm`（Panels 175 行），问题集删除用"再点一次"，运行设置用 Radix Dialog，三种并存。

### D. 结构合理性

17. **报告区与图谱区风格突变**：报告顶绿条 + 17px 大字号 + 另一套字体栈，从地图滚到报告无过渡锚点。
18. **死代码**：`AssociationTrackingPanel` / `QuestionBankPanel` / `EvidenceWorkbenchPanel` / `WeightRulePanel` 四个导出组件（约 600 行）全项目无引用；`viewMode='flat'` 硬编码使 spatial 3D 模式整段不可达。
19. **导出 HTML 平行调色板**：`downloadAssociationReportHtml` 内 60+ 个硬编码 hex 与页面 CSS 变量重复定义同一套品牌色，品牌色调整必然漂移。

### 保留的亮点（不动）

- 轨道图本体：键盘导航、hover label、选中画线动画、live 节点弹入动画、`prefers-reduced-motion` 支持
- 实时进度 6 步条（LiveExtractionStatusStrip）
- 节点详情面板的三层解读结构（认知/理知/感知）
- 报告的长文排版骨架（章节编号、takeaway 引用块）

---

## 三、改版方案

### 设计原则

1. **单一主行动**：每个视口只有一个实心主按钮，其余降为次级/幽灵按钮。
2. **三层表面**：页面（最暗）→ 卡片（提亮 + 细边框 + 轻阴影）→ 嵌套区（灰底 inset），卡片 hover 微提升。
3. **说明与操作分离**：图例收纳为可展开的"图例"按钮；筛选/模式切换用分段控件形态，与说明性胶囊视觉区分。
4. **信息只出现一次**：回答数/节点数等摘要只保留在 Hero 一行。
5. **选中语义一致**：节点选中色跟随轨道色。

### 分区改动

#### 1. Header（Dashboard 386-453 行）
- 状态 pill 精简为"状态点 + 状态文字"，移除回答/节点计数（与 Hero 重复）。
- "生成报告"按钮降为**次级描边按钮**（主行动让给 Hero 的"设置并运行"）；报告已生成时仍实心（此时主流程已推进到报告）。
- Header 加 `backdrop-blur` + 滚动时阴影，提升 sticky 质感。

#### 2. Hero 控制卡（Dashboard 499-583 行）
- 5 个 InfoPill 合并为 1 行紧凑数据摘要（回答 · 平台 · 节点，3 项）。
- 重组为两行：**第一行** = 标题 + 数据摘要 + [设置并运行] 主按钮；**第二行** = 分析对象 chips + 观察周期（两个控制组并排，周期从卡片底部移上）。
- "其他对象将在独立投影生成后开放"等说明文字收敛为 chips 旁的 `?` 提示。

#### 3. 图谱卡 header（Views 311-352 行）
- 图例 6 pills 收纳为"图例"按钮 + hover/点击展开浮层（默认收起，降噪）。
- 轨道筛选条改为**分段控件**形态（与图例明确区分），预览态（hover）用虚线描边、激活态用实色，解决预览/激活混淆。
- 移除右上 2 个 InfoPill（与 Hero 摘要重复）。
- 模式切换保留，但"风险与竞争"加红色语义点，与筛选条形态统一。

#### 4. 轨道图本体（Views 916-1369 行）
- 节点 hover：色点 `scale(1.15)` + 亮度提升，增强可点感。
- 选中 ring 颜色改为**跟随轨道色**（稳定=品牌绿、机会=黄、观察=灰、风险=红）。
- 中心品牌圆加 hover 态（光晕 + "点击取消选中"title 已有，加视觉反馈）。
- 左下风险入口圆钮改为**小型胶囊按钮**（"风险与竞争 N →"），与中心品牌造型区分，消除"第二个中心"感。
- 总览态"幽灵点"（opacity 0.2 非高亮节点）进一步降到 0.12 或缩小尺寸，降低噪音。
- live 浮层米色硬编码 → CSS 变量（`--bg-elevated` + 透明度）。

#### 5. "本周先看" strip（Views 516-591 行）
- `border-b` 改 `border-t`（修正贴底分隔）。
- 移除 strip 内"查看风险关系"按钮（与模式切换重复，三个风险入口减为两个）。
- 三列卡片加 hover 提升反馈。

#### 6. 报告区（Views 3617-3767、5172-5310 行）
- 报告 article 前加锚点分隔（"解读报告"区标题 + 与图谱区的间距/背景过渡带）。
- takeaway 引用块 3 处硬编码 rgba → CSS 变量（新增 `--report-takeaway-bg` 等）。
- `REPORT_SERIF_FONT` 15+ 处内联 → 收敛为 `.report-font` 工具类（改名 `REPORT_FONT`，值不变）。
- ReportGenerationGate 与报告本体宽度对齐（统一 max-w）。

#### 7. 表面与组件规范（全局，限本页面文件）
- 新增页面级工具类（globals.css 或组件内常量）：
  - `.amway-card`：卡片 = bg 提亮 + border-subtle + shadow-sm + hover:border-hover + hover:shadow-md + transition
  - `.amway-card-inset`：嵌套灰底区
  - `.amway-btn-primary / -secondary / -ghost`：统一高度（40/36px）、圆角（10px）、过渡
  - `.amway-chip`：统一胶囊
- 深色主题卡片背景从 `bg-primary` 调整为 `bg-secondary`（卡片比页面亮一档），浅色主题同步校验。
- 词库删除 `window.confirm` → 与问题集一致的"再点一次确认"模式（或 Radix 确认弹窗，取实现成本低的）。

#### 8. 清理（可选，需确认）
- 删除 4 个未挂载死组件（约 600 行）：`AssociationTrackingPanel` / `QuestionBankPanel` / `EvidenceWorkbenchPanel` / `WeightRulePanel`。
- 删除 spatial 3D 死路径（`viewMode` 相关不可达代码）。
- 导出 HTML 平行调色板：**本期不动**（独立文档，风险低收益低，后续单独处理）。

### 明确不做

- 不动任何数据获取/计算/轮询/WebSocket 逻辑（ConsolePage 全部、Dashboard 的数据 hooks）。
- 不动轨道图布局算法（orbit 定位、碰撞、半径计算）。
- 不动报告内容生成（`buildAssociationNarrativeReport` 等纯函数）。
- 不动导出 HTML 的样式体系。

---

## 四、影响面与风险

| 项 | 影响 |
|---|---|
| 改动文件 | 主要是 Dashboard.tsx + Views.tsx + AssetPanels.tsx + globals.css（新增少量工具类） |
| 数据逻辑 | 零改动，仅 className/style/结构重排 |
| 无障碍 | 保留全部 aria 属性与键盘导航；图例收纳后需保证键盘可展开 |
| 主题 | 深色/浅色双主题同步校验（globals.css 有两套变量） |
| 风险 | 卡片背景反转（页面/卡片亮度）是全局视觉变化，需双主题截图验证 |

## 五、验证方式

1. `npm run lint` + `npm run build` 零错误。
2. 启动前后端，Playwright 截图对比：图谱总览 / 选中节点 / 风险模式 / live 进度 / 报告区 / 词库 / 题库，深浅两主题。
3. 键盘走查：Tab 顺序、方向键节点导航、Esc 关闭面板、图例浮层键盘可操作。

---

## 实施完成记录（2026-07-17）

### 已交付
1. **globals.css**：`.amway-console` 深色表面反转（`:root:not([data-theme="light"])` 作用域）、`--report-takeaway-*` / `--report-blindspot-bg` 变量、`.report-font`、`.amway-card-interactive`
2. **Dashboard.tsx**：Header 精简（状态 pill 去掉冗余计数、报告按钮三态）、Hero 两行重组（H1 + 内联摘要 + 设置并运行 / 分析对象 chips + PeriodSelector）、报告区"解读报告"锚点分隔线
3. **Views.tsx**：图谱卡 header 重组（OrbitMapLegend popover 替代 2 个 InfoPill）、过滤器激活/预览态彩色描边、PriorityFocusStrip 改顶部 hairline、中心品牌/节点 hover 光晕、风险入口圆形改 pill、报告区 15+ 处 fontFamily 内联 → `.report-font`、硬编码 rgba → CSS 变量
4. **死代码清理**（约 600 行）：AssociationTrackingPanel / QuestionBankPanel / EvidenceWorkbenchPanel / WeightRulePanel + 辅助组件（EvidenceMetric/WeightCard/TrackingMetric/TrackingRule/MetricGrid/QuestionUploadButton/EvidenceScopeCard/scoreText）+ spatial 3D 死路径（viewMode/isSpatialMode/spatialDepthForEntry/AssociationMapViewMode）+ REPORT_SERIF_FONT 常量
5. **AssetPanels**：实体词删除 window.confirm → 两次点击确认（与题库删除一致）

### 验证
- `tsc --noEmit` 0 错误；`eslint` 0 错误（仅剩 3 个范围外历史警告）；`npm run build` 成功
- Playwright 双主题截图验证：浅色/深色均正常，图例 popover 展开/Esc 关闭正常，实体词两次点击确认正常
- 修复一处实施中发现的 bug：表面反转规则初版未限定深色作用域，导致浅色主题暗底暗字 → 改为 `:root:not([data-theme="light"]) .amway-console`

---

## 浅色主题专属增强（2026-07-18）

### 已交付
1. **globals.css**：`html[data-theme="light"] .amway-console` 作用域下新增
   - 页面顶部极淡品牌色径向纹理（`radial-gradient 880px 300px, 0.028` 透明度）
   - `--amway-card-shadow` 双层柔和投影 + `.amway-surface` 工具类（Hero / 图谱卡 / 加载面板 / 报告文章 / 6 个资产管理面板 / 报告门槛卡）
   - `.amway-cta-glow` 主按钮品牌色光晕（0.3 / hover 0.4，首版 0.45/0.55 过重已调低）
   - `--amway-track-band: 0.13` 轨道色带不透明度（经 SVG `style={{ strokeOpacity: 'var(...)' }}` 消费，attribute 不支持 var()）
2. **Hero 品牌点缀**：eyebrow 行加品牌色圆点 + `{品牌} 专属`

### 用户反馈修正（2026-07-18）
1. **光晕过重** → 页面纹理 1100px/0.07 → 880px/0.028；CTA 光晕 0.45/0.55 → 0.3/0.4
2. **"-" 占位符不友好** → Hero 摘要无数据时显示"尚未运行采集，从图谱中心开始"；报告门槛卡无数据时显示"运行图谱采集后，即可基于真实回答展开战略词验证、平台差异和下一轮建议。"
3. **图中心无意义文案** → 删除空状态"还没有外围节点…"提示文字
4. **操作路径 = 视觉焦点** → 空状态下圈层图中心变为"开始运行"播放按钮（`showStartCta = !isRiskMode && !isLivePreview && entries.length === 0 && onStartRun`），实心品牌色圆 + Play 图标 + 2.4s 脉冲动画，点击直接打开运行设置对话框；`onStartRun` 经 CommercialOrbitView → CommercialOrbitMap 透传

### 验证
- `tsc --noEmit` 0 错误；`eslint` 0 错误
- Playwright 浅色主题截图：空状态播放 CTA 居中显示正常，点击后运行设置对话框正常打开

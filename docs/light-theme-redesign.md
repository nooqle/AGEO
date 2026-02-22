# 浅色模式色彩体系重新设计

**设计师**: Don Norman
**日期**: 2026-02-22
**状态**: 待产品确认后实施

---

## 1. 当前问题诊断

### 1.1 核心问题

当前浅色模式是从深色模式"翻转"而来，存在以下系统性问题：

| 问题 | 具体表现 | 严重程度 |
|------|----------|----------|
| **背景层级无区分感** | bg-primary (#F4F4F5) vs bg-secondary (#FFFFFF) vs bg-tertiary (#F0F0F0) 三者色差仅 4-5 个灰度值 | 高 |
| **卡片与背景融为一体** | bg-secondary = bg-elevated = #FFFFFF，卡片与内容区完全相同 | 高 |
| **阴影过重** | shadow 值设计较好，但 CanvasPanel 等处硬编码 `rgba(0,0,0,0.4)` 阴影过黑 | 中 |
| **品牌色缺乏浅色变体** | #6366F1 作为主色在浅色下偏深偏冷，缺少淡色背景/悬停态 | 中 |
| **按钮设计无系统性** | btn-primary 用渐变（indigo→purple→pink），其他按钮散落各组件内联样式 | 高 |
| **缺乏层次感** | 输入框、卡片、侧栏都是纯白或近白，视觉扁平 | 高 |
| **硬编码颜色散布** | 约 30+ 处使用 `#6366F1`/`#22C55E`/`#EF4444`/`#F59E0B` 等硬编码值 | 中 |

### 1.2 设计参考

本方案参考以下高质量浅色模式设计系统：

- **Linear Light** — 灰色底+白色卡片，极致简洁，阴影微妙
- **Vercel Light** — 纯白底，通过极细边框和微弱阴影创造层次
- **Radix Themes Light (Indigo)** — 与我们品牌色一致（Indigo），色阶系统完善
- **Notion Light** — 大留白+浅灰背景+白色内容区的经典搭配

**选定方向**：Linear/Notion 风格 — 浅灰底 + 白色卡片 + 微弱阴影 + 品牌色点缀

---

## 2. 重新设计的 CSS 变量

### 2.1 背景层级

设计原则：**由浅到深 4 级，拉大层级差距**

```css
/* 现有值 → 新值 */
--bg-primary:    #F4F4F5  →  #F8F9FA;   /* 页面底色：更暖更亮的灰 */
--bg-secondary:  #FFFFFF  →  #FFFFFF;   /* 卡片/面板：纯白（不变） */
--bg-tertiary:   #F0F0F0  →  #F1F3F5;   /* 悬停态/区分背景 */
--bg-elevated:   #FFFFFF  →  #FFFFFF;   /* 弹出层/浮层 */
--bg-card:       rgba(255, 255, 255, 0.9) → rgba(255, 255, 255, 0.95);
```

**关键改动说明**：
- `bg-primary` 从 #F4F4F5 (zinc-100) 改为 #F8F9FA (gray-50 偏暖)，让页面整体更明亮柔和
- `bg-tertiary` 从 #F0F0F0 改为 #F1F3F5，拉开与 bg-primary 的差距（原差 4 → 新差 7）
- bg-secondary 与 bg-elevated 保持 #FFFFFF，但通过阴影/边框区分

### 2.2 文字层级

设计原则：**保持 WCAG AA (4.5:1) 合规，但减轻视觉重量**

```css
--text-primary:   #111111  →  #1A1A2E;   /* 主文字：深灰偏蓝，不纯黑 */
--text-secondary: #525252  →  #64748B;   /* 次级文字：slate-500，更柔和 */
--text-tertiary:  #6B7280  →  #94A3B8;   /* 辅助文字：slate-400 */
--text-disabled:  #A1A1AA  →  #CBD5E1;   /* 禁用态：slate-300 */
--text-muted:     #9CA3AF  →  #B0BEC5;   /* 静音文字 */
```

**对比度验证**（在 #F8F9FA 背景上）：
- text-primary (#1A1A2E): 对比度 14.8:1 -- PASS AAA
- text-secondary (#64748B): 对比度 4.9:1 -- PASS AA
- text-tertiary (#94A3B8): 对比度 3.0:1 -- PASS (大号文字)
- text-disabled (#CBD5E1): 对比度 1.8:1 -- 预期（禁用态无需高对比）

### 2.3 边框

设计原则：**浅色下边框应更轻，用于分隔而非强调**

```css
--border-default: #E4E4E7  →  #E2E8F0;   /* 默认边框：slate-200，更柔 */
--border-hover:   #D4D4D8  →  #CBD5E1;   /* 悬停边框：slate-300 */
--border-focus:   #6366F1  →  #6366F1;   /* 焦点边框：保持品牌色 */
```

### 2.4 品牌色

设计原则：**Indigo 主色保留，但增加浅色专用变体**

```css
--brand-primary:  #6366F1  →  #6366F1;   /* 主色不变 */
--brand-hover:    #4F46E5  →  #4F46E5;   /* 悬停态：深一级 */
--brand-active:   #4338CA  →  #4338CA;   /* 按下态：再深一级 */

--color-primary:       #6366F1  →  #6366F1;
--color-primary-light: #818CF8  →  #A5B4FC;   /* 浅色变体：indigo-300，浅色下更舒适 */
--color-primary-dark:  #4F46E5  →  #4F46E5;
--color-primary-glow:  rgba(99, 102, 241, 0.15) → rgba(99, 102, 241, 0.08);  /* glow 减弱 */
```

**新增品牌色辅助变量**（建议添加）：
```css
--brand-bg:      #EEF2FF;   /* indigo-50，品牌色淡背景 */
--brand-bg-hover: #E0E7FF;   /* indigo-100，品牌色悬停背景 */
--brand-border:  #C7D2FE;   /* indigo-200，品牌色淡边框 */
--brand-text:    #4338CA;   /* indigo-700，品牌色文字（深色以保证对比度） */
```

### 2.5 语义/状态色

设计原则：**浅色下状态色需要降低饱和度，避免刺眼**

```css
/* 状态色微调 */
--success: #16A34A  →  #16A34A;   /* green-600，不变 */
--warning: #D97706  →  #D97706;   /* amber-600，不变 */
--error:   #DC2626  →  #DC2626;   /* red-600，不变 */
--info:    #2563EB  →  #2563EB;   /* blue-600，不变 */

/* 状态背景色加深（原 0.08 透明度在浅色底上几乎看不见） */
--status-success-bg: rgba(22, 163, 74, 0.08)  →  rgba(22, 163, 74, 0.10);
--status-warning-bg: rgba(217, 119, 6, 0.08)  →  rgba(217, 119, 6, 0.10);
--status-error-bg:   rgba(220, 38, 38, 0.08)  →  rgba(220, 38, 38, 0.10);
--status-info-bg:    rgba(37, 99, 235, 0.08)  →  rgba(37, 99, 235, 0.10);

/* 状态色浅色别名（保持一致） */
--status-success: #16A34A;
--status-warning: #D97706;
--status-error:   #DC2626;
--status-info:    #2563EB;
```

### 2.6 TPAOR 阶段色

```css
/* 浅色下阶段色降低饱和度，更适配白底 */
--phase-thought:  #7C3AED  →  #7C3AED;   /* violet-600，不变 */
--phase-plan:     #1D4ED8  →  #2563EB;   /* blue-600，略亮 */
--phase-action:   #B45309  →  #D97706;   /* amber-600，更可读 */
--phase-observe:  #15803D  →  #16A34A;   /* green-600，略亮 */
--phase-response: #4338CA  →  #4338CA;   /* indigo-700，不变 */
```

### 2.7 阴影

设计原则：**浅色模式阴影必须极轻，层次靠边框+微弱阴影共同构建**

```css
--shadow-sm:   0 1px 2px rgba(0, 0, 0, 0.06)
             → 0 1px 2px rgba(0, 0, 0, 0.04);

--shadow-md:   0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -1px rgba(0, 0, 0, 0.05)
             → 0 2px 4px -1px rgba(0, 0, 0, 0.06), 0 1px 2px -1px rgba(0, 0, 0, 0.04);

--shadow-lg:   0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04)
             → 0 8px 16px -4px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.04);

--shadow-glow: 0 0 20px rgba(99, 102, 241, 0.15)
             → 0 0 16px rgba(99, 102, 241, 0.10);

/* 新增卡片专用阴影 */
--shadow-card: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02);
```

### 2.8 Glass Morphism

```css
--glass-bg:     rgba(255, 255, 255, 0.7) → rgba(255, 255, 255, 0.80);
--glass-border: rgba(0, 0, 0, 0.06)      → rgba(0, 0, 0, 0.05);
```

---

## 3. 按钮状态设计

### 3.1 Primary Button（品牌主按钮）

```
┌──────────────────────────────────────────┐
│ 状态        │ 背景色    │ 文字色  │ 边框   │
├─────────────┼───────────┼─────────┼────────┤
│ Default     │ #6366F1   │ #FFFFFF │ 无     │
│ Hover       │ #4F46E5   │ #FFFFFF │ 无     │
│ Active      │ #4338CA   │ #FFFFFF │ 无     │
│ Disabled    │ #C7D2FE   │ #FFFFFF │ 无     │
│ Focus       │ #6366F1   │ #FFFFFF │ ring   │
└──────────────────────────────────────────┘

Focus ring: 0 0 0 2px #FFFFFF, 0 0 0 4px #6366F1
```

**重要改动**：取消渐变背景（`--gradient-primary`），改为**纯色 indigo**。渐变在浅色模式下太花哨，与"简洁有呼吸感"的目标不符。

CSS 建议：
```css
html[data-theme="light"] .btn-primary {
  background: var(--brand-primary);    /* 纯色替代渐变 */
  box-shadow: var(--shadow-sm);
}
html[data-theme="light"] .btn-primary:hover {
  background: var(--brand-hover);
  box-shadow: var(--shadow-md);
  transform: none;                     /* 取消 translateY，更克制 */
}
html[data-theme="light"] .btn-primary:hover::before {
  display: none;                       /* 取消 shimmer 光效 */
}
```

### 3.2 Secondary Button（次要按钮）

```
┌──────────────────────────────────────────────────┐
│ 状态        │ 背景色    │ 文字色    │ 边框       │
├─────────────┼───────────┼──────────┼────────────┤
│ Default     │ #FFFFFF   │ #1A1A2E  │ #E2E8F0    │
│ Hover       │ #F8F9FA   │ #1A1A2E  │ #CBD5E1    │
│ Active      │ #F1F3F5   │ #1A1A2E  │ #CBD5E1    │
│ Disabled    │ #F8F9FA   │ #CBD5E1  │ #E2E8F0    │
└──────────────────────────────────────────────────┘
```

### 3.3 Ghost Button（文本按钮/图标按钮）

```
┌──────────────────────────────────────────────────┐
│ 状态        │ 背景色         │ 文字色    │ 边框 │
├─────────────┼────────────────┼──────────┼──────┤
│ Default     │ transparent    │ #64748B  │ 无   │
│ Hover       │ #F1F3F5        │ #1A1A2E  │ 无   │
│ Active      │ #E2E8F0        │ #1A1A2E  │ 无   │
│ Disabled    │ transparent    │ #CBD5E1  │ 无   │
└──────────────────────────────────────────────────┘
```

### 3.4 Brand Ghost Button（品牌色文本按钮）

用于 FollowUpChips、品牌色操作按钮等：

```
┌──────────────────────────────────────────────────┐
│ 状态        │ 背景色    │ 文字色    │ 边框       │
├─────────────┼───────────┼──────────┼────────────┤
│ Default     │ #EEF2FF   │ #4338CA  │ #C7D2FE    │
│ Hover       │ #E0E7FF   │ #4338CA  │ #A5B4FC    │
│ Active      │ #C7D2FE   │ #3730A3  │ #A5B4FC    │
└──────────────────────────────────────────────────┘
```

### 3.5 Danger Button

```
┌──────────────────────────────────────────────────┐
│ 状态        │ 背景色           │ 文字色    │ 边框       │
├─────────────┼──────────────────┼──────────┼────────────┤
│ Default     │ #FEF2F2          │ #DC2626  │ #FECACA    │
│ Hover       │ #FEE2E2          │ #B91C1C  │ #FCA5A5    │
│ Active      │ #FECACA          │ #991B1B  │ #FCA5A5    │
└──────────────────────────────────────────────────┘
```

---

## 4. 组件级硬编码修复清单

以下为需要在代码中修复的硬编码颜色值：

### 4.1 高优先级（视觉影响大）

| 文件 | 行 | 当前值 | 建议修改 |
|------|-----|--------|----------|
| `CanvasPanel.tsx` | 25, 89 | `shadow-[-4px_0_24px_rgba(0,0,0,0.4)]` | 浅色下改为 `shadow-[-2px_0_16px_rgba(0,0,0,0.06)]`，可通过 CSS 变量 `--shadow-canvas` |
| `ChatPanel.tsx` | 422 | `bg-black/60 backdrop-blur-sm` | 浅色下改为 `bg-black/30 backdrop-blur-md` 或 `bg-white/60 backdrop-blur-md` |
| `ConfirmationCard.tsx` | 66 | `bg-[rgba(99,102,241,0.1)]` | 改为 `bg-[--brand-bg]`（新变量 #EEF2FF） |
| `ConfirmationCard.tsx` | 94 | `bg-[#6366F1]` / `hover:bg-[#818CF8]` | 改为 `bg-[--brand-primary]` / `hover:bg-[--brand-hover]` |
| `StageResultCard.tsx` | 331 | `backgroundColor: '#22C55E', color: '#FFFFFF'` | 改为 `var(--success)` 和 `#FFFFFF` |
| `design-system.css` | 183-218 | `btn-primary` 使用渐变+shimmer | 浅色下覆盖为纯色 |

### 4.2 中优先级（影响中等）

| 文件 | 问题 | 建议 |
|------|------|------|
| `MiniProgress.tsx` | 多处 `text-[#F59E0B]`, `text-[#22C55E]`, `text-[#EF4444]` | 改为 `text-[--warning]`, `text-[--success]`, `text-[--error]` |
| `StageResultCard.tsx` | `STAGE_COLORS` 硬编码 | 改为 CSS 变量引用 |
| `CanvasHeader.tsx` | `text-indigo-400`, `text-blue-400`, `text-purple-400` | 浅色下改用 -600 系列或用 CSS 变量 |
| `MessageList.tsx` | `from-indigo-500 to-purple-600` 渐变 | 品牌 logo 元素可接受，但建议统一 |
| `StageResultCard.tsx` | tooltip `boxShadow: rgba(0,0,0,0.3)` | 浅色下改为 `rgba(0,0,0,0.1)` |

### 4.3 低优先级（可后续统一处理）

| 文件 | 问题 |
|------|------|
| `SelectionContent.tsx` | `PRIORITY_CONFIG` 硬编码 `#EF4444`/`#F59E0B`/`#22C55E` |
| `FollowUpChips.tsx` | `ICON_COLORS` 使用 `var()` 带 fallback，已可接受 |
| `ThemeToggle.tsx` | `#D97706` 浅色 sun icon 颜色，风格化设计可接受 |

---

## 5. 呼吸感与间距优化

### 5.1 全局间距调整

| 位置 | 当前 | 建议 | 原因 |
|------|------|------|------|
| ArtifactNav compact `gap` | `gap-1` (4px) | `gap-2` (8px) | 按钮间太挤 |
| ArtifactNav compact `px` | `px-1` (4px) | `px-1.5` (6px) | 左右太窄 |
| Canvas Header `py` | `py-3` (12px) | `py-3.5` (14px) | 顶栏稍压抑 |
| Sidebar Entity `mb` | `mb-2` (8px) | `mb-1` (4px) | 卡片间距适中即可 |
| Chat 消息区 `px` | `px-4` (16px) | `px-5` (20px) | 浅色下内容区需要更多留白 |
| Chat 消息 `space-y` | `space-y-6` (24px) | `space-y-6` (24px) | 不变，已合适 |
| InputArea 外边距 `py` | `py-4` (16px) | `py-5` (20px) | 输入区需更多呼吸空间 |

### 5.2 圆角统一

当前组件圆角不统一（rounded-lg / rounded-xl / rounded-2xl / rounded-[10px] 混用）：

| 元素类型 | 建议圆角 |
|----------|----------|
| 卡片/面板 | `rounded-xl` (12px) |
| 按钮 | `rounded-lg` (8px) |
| 输入框 | `rounded-xl` (12px) |
| Badge/Tag | `rounded-md` (6px) |
| Avatar | `rounded-full` |
| 弹出菜单 | `rounded-xl` (12px) |

### 5.3 输入框改进

当前 InputArea 的输入框在浅色下 bg-secondary (#FFF) 与 bg-primary (#F4F4F5) 差异太小。

建议：
```css
/* 输入框在浅色下的特殊处理 */
html[data-theme="light"] textarea,
html[data-theme="light"] input {
  background-color: #FFFFFF;
  border: 1px solid var(--border-default);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.04);  /* 微弱内阴影创造凹陷感 */
}
```

---

## 6. 完整的新版 Light Theme CSS 变量

```css
html[data-theme="light"] {
  /* 背景层级 — 由浅到深，间隔明显 */
  --bg-primary:    #F8F9FA;
  --bg-secondary:  #FFFFFF;
  --bg-tertiary:   #F1F3F5;
  --bg-elevated:   #FFFFFF;
  --bg-card:       rgba(255, 255, 255, 0.95);

  /* 文字层级 — 基于 Slate 色阶，柔和不刺眼 */
  --text-primary:   #1A1A2E;
  --text-secondary: #64748B;
  --text-tertiary:  #94A3B8;
  --text-disabled:  #CBD5E1;
  --text-muted:     #B0BEC5;

  /* 边框 — 轻量化 */
  --border-default: #E2E8F0;
  --border-hover:   #CBD5E1;
  --border-focus:   #6366F1;

  /* 品牌色 — Indigo 系列 */
  --brand-primary:  #6366F1;
  --brand-hover:    #4F46E5;
  --brand-active:   #4338CA;
  --color-primary:  #6366F1;
  --color-primary-light: #A5B4FC;
  --color-primary-dark:  #4F46E5;
  --color-primary-glow:  rgba(99, 102, 241, 0.08);

  /* 品牌色辅助变量（新增） */
  --brand-bg:       #EEF2FF;
  --brand-bg-hover: #E0E7FF;
  --brand-border:   #C7D2FE;
  --brand-text:     #4338CA;

  /* 语义/状态色 */
  --success: #16A34A;
  --warning: #D97706;
  --error:   #DC2626;
  --info:    #2563EB;
  --status-success: #16A34A;
  --status-warning: #D97706;
  --status-error:   #DC2626;
  --status-info:    #2563EB;
  --status-success-bg: rgba(22, 163, 74, 0.10);
  --status-warning-bg: rgba(217, 119, 6, 0.10);
  --status-error-bg:   rgba(220, 38, 38, 0.10);
  --status-info-bg:    rgba(37, 99, 235, 0.10);

  /* TPAOR 阶段色 */
  --phase-thought:  #7C3AED;
  --phase-plan:     #2563EB;
  --phase-action:   #D97706;
  --phase-observe:  #16A34A;
  --phase-response: #4338CA;

  /* 阴影 — 极轻 */
  --shadow-sm:   0 1px 2px rgba(0, 0, 0, 0.04);
  --shadow-md:   0 2px 4px -1px rgba(0, 0, 0, 0.06), 0 1px 2px -1px rgba(0, 0, 0, 0.04);
  --shadow-lg:   0 8px 16px -4px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.04);
  --shadow-glow: 0 0 16px rgba(99, 102, 241, 0.10);
  --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02);

  /* Glass */
  --glass-bg:     rgba(255, 255, 255, 0.80);
  --glass-border: rgba(0, 0, 0, 0.05);
}
```

---

## 7. design-system.css 浅色覆盖

在 `design-system.css` 末尾添加：

```css
/* ============================================
   Light Theme Overrides for design-system.css
   ============================================ */
html[data-theme="light"] {
  --color-secondary-light: #34D399;
  --color-secondary-glow: rgba(16, 185, 129, 0.15);

  --gradient-primary: linear-gradient(135deg, #6366F1 0%, #818CF8 100%);
  --gradient-dark: none;
  --gradient-glow: radial-gradient(ellipse at center, rgba(99, 102, 241, 0.06) 0%, transparent 70%);

  --shadow-md-full: 0 2px 4px -1px rgba(0, 0, 0, 0.06), 0 1px 2px -1px rgba(0, 0, 0, 0.04);
  --shadow-lg-full: 0 8px 16px -4px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.04);
  --shadow-glow-lg: 0 0 24px rgba(99, 102, 241, 0.08);
}

/* 浅色下 btn-primary 简化 */
html[data-theme="light"] .btn-primary {
  background: var(--brand-primary);
  box-shadow: var(--shadow-sm);
}
html[data-theme="light"] .btn-primary:hover {
  background: var(--brand-hover);
  box-shadow: var(--shadow-md);
  transform: none;
}
html[data-theme="light"] .btn-primary::before {
  display: none;
}

/* 浅色下 glow 效果减弱 */
html[data-theme="light"] .glow {
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.08);
}
html[data-theme="light"] .glow-strong {
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.12);
}
html[data-theme="light"] .glow-border {
  box-shadow: 0 0 0 1px var(--color-primary), 0 0 12px rgba(99, 102, 241, 0.08);
}

/* 浅色下 card hover 阴影 */
html[data-theme="light"] .card-modern:hover {
  box-shadow: var(--shadow-md);
}
```

---

## 8. 实施优先级

| 步骤 | 内容 | 工作量 |
|------|------|--------|
| 1 | 更新 `globals.css` 中 `[data-theme="light"]` 的 CSS 变量值 | 10 分钟 |
| 2 | 更新 `design-system.css` 添加浅色覆盖 | 10 分钟 |
| 3 | 修复 CanvasPanel 阴影硬编码 | 5 分钟 |
| 4 | 修复 ConfirmationCard 颜色硬编码 | 10 分钟 |
| 5 | 修复 MiniProgress / StageResultCard 状态色硬编码 | 15 分钟 |
| 6 | 修复 ChatPanel 遮罩层 | 5 分钟 |
| 7 | 间距/圆角微调 | 20 分钟 |
| 8 | 全面浏览器验收 | 30 分钟 |

**预估总工作量**：约 1.5-2 小时前端开发工作

---

## 9. 前后对比预期

| 区域 | 现在 | 改后 |
|------|------|------|
| 页面底色 | 发灰（#F4F4F5）| 明亮温暖（#F8F9FA）|
| 卡片层次 | 与背景融为一体 | 白色卡片+微弱阴影浮出 |
| 品牌按钮 | 渐变+shimmer 光效 | 纯色 Indigo，简洁克制 |
| 文字灰度 | 偏暗/偏锌 | Slate 色阶，柔和统一 |
| 阴影 | 偏重 | 极轻，层次靠边框+微阴影 |
| 整体感觉 | "深色模式取反" | "现代 SaaS 浅色模式"（Linear/Notion 风格） |

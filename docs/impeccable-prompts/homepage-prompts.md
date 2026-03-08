# Homepage Prompts

适用文件：

- `frontend/src/app/page.tsx`
- `frontend/src/components/landing/hero.tsx`
- `frontend/src/components/landing/features.tsx`
- `frontend/src/components/landing/how-it-works.tsx`
- `frontend/src/components/landing/cta-section.tsx`

## 1. 首页整体重设计

```text
使用 impeccable-frontend-design 重做 Specta AI 首页。

目标文件：
- frontend/src/app/page.tsx
- frontend/src/components/landing/hero.tsx
- frontend/src/components/landing/features.tsx
- frontend/src/components/landing/how-it-works.tsx
- frontend/src/components/landing/cta-section.tsx

业务目标：
- 让用户更快理解 Specta AI 是做什么的
- 强化 “品牌在 AI 搜索中的可见性分析” 这一定位
- 提高首页的专业感、可信度和首屏记忆点

约束：
- 保留现有核心信息结构：hero、能力说明、流程说明、CTA
- 不改后端接口和数据流
- 不做模板化 SaaS 首页，不要紫蓝渐变和通用卡片堆叠

设计方向：
- editorial + refined minimal
- 用更强的字体层级、留白节奏、非对称布局和少量高质量动效建立品牌感

执行要求：
- 直接修改代码
- 优先产出生产可用实现
- 最后说明关键设计决策，并做必要验证
```

## 2. 只优化 Hero 首屏

```text
使用 impeccable-bolder 强化首页 hero section 的视觉冲击力。

目标文件：
- frontend/src/components/landing/hero.tsx

当前问题：
- 首屏过于平，缺少品牌辨识度
- 价值主张不够聚焦
- 视觉重心不够明确

要求：
- 保留现有核心文案含义
- 强化主标题、支持文案、CTA 层级
- 可以调整版式、字体、背景、装饰元素和局部动效
- 不要做成噪音设计，也不要牺牲可读性

输出要求：
- 直接改代码
- 解释 hero 的主视觉逻辑和信息层级是如何调整的
```

## 3. 首页批判性审查

```text
使用 impeccable-critique 对 Specta AI 首页做设计点评，但先不要改代码。

范围：
- frontend/src/app/page.tsx
- frontend/src/components/landing/hero.tsx
- frontend/src/components/landing/features.tsx
- frontend/src/components/landing/how-it-works.tsx
- frontend/src/components/landing/cta-section.tsx

重点判断：
- 是否足够像一个可信的 B2B AI 产品首页
- 信息层级是否清楚
- 文案与视觉是否互相支撑
- 哪些部分最有 “AI 味” 或模板感

输出要求：
- 先列出最关键的 5 个问题
- 每个问题给出原因和建议方向
- 最后指出下一步最适合用哪个 impeccable skill
```

## 4. 首页移动端适配

```text
使用 impeccable-adapt 适配 Specta AI 首页到移动端和窄屏场景。

目标文件：
- frontend/src/app/page.tsx
- frontend/src/components/landing/hero.tsx
- frontend/src/components/landing/features.tsx
- frontend/src/components/landing/how-it-works.tsx
- frontend/src/components/landing/cta-section.tsx

要求：
- 不只是缩小布局，而是重新组织首屏与内容节奏
- 保留关键信息与 CTA
- 修复拥挤、换行难看、点击区域不足、视觉节奏断裂等问题

执行要求：
- 直接改代码
- 最后说明移动端做了哪些结构性调整
```

## 5. 平台首页定位与转化路径审查

```text
使用 impeccable-audit 审查 Specta AI 平台首页的完整首屏说服力和转化路径，但先不要改代码。

范围：
- frontend/src/app/page.tsx
- frontend/src/components/landing/hero.tsx
- frontend/src/components/landing/features.tsx
- frontend/src/components/landing/how-it-works.tsx
- frontend/src/components/landing/cta-section.tsx
- frontend/src/components/landing/footer.tsx

这不是普通 marketing 页面，而是用户第一次理解 Specta AI 是什么、适合谁、解决什么问题，以及是否值得继续进入产品的入口页面。
请从以下 4 个层面一起审查：

1. 定位表达层
- 用户是否能在几秒内理解产品是什么
- “品牌在 AI 搜索中的可见性分析” 是否被清楚表达

2. 信任建立层
- 首页是否足够像可信的 B2B AI 产品
- 论据、结构和视觉是否支撑专业感

3. 转化路径层
- 页面是否清楚引导用户继续了解、开始使用或进入下一步
- CTA 是否足够清楚且层级明确

4. 内容节奏层
- hero、能力说明、流程说明、CTA 是否形成自然递进
- 是否存在模板化堆砌、冗余重复或阅读节奏断裂

重点：
- 首页是否存在“看起来像 AI 产品，但说不清价值”的问题
- 是否有明显模板感或 AI 味
- 文案、版式和视觉是否共同服务转化
- 移动端首屏是否仍然成立

输出要求：
- 按严重程度排序
- 每个问题说明影响范围和修复建议
- 单独指出“定位问题”“信任问题”“转化路径问题”“内容节奏问题”
- 标注哪些问题更适合后续用 impeccable-bolder、impeccable-polish、impeccable-clarify 或 impeccable-frontend-design 处理
```

## 6. 平台首页品牌与说服力点评

```text
使用 impeccable-critique 对 Specta AI 平台首页的品牌感、说服力和首屏记忆点做设计点评，但先不要改代码。

范围：
- frontend/src/app/page.tsx
- frontend/src/components/landing/

请重点判断：
- 用户是否能迅速理解这是一个什么产品
- 首页是否有足够强的品牌感和独特性
- 首屏是否有明确记忆点
- 文案与视觉是否互相强化，而不是各说各话
- 页面是否能自然把用户带到下一步动作

输出要求：
- 先列最关键的 5 个问题
- 每个问题给出原因和建议方向
- 区分哪些是品牌表达问题，哪些是结构问题，哪些只是视觉打磨问题
- 最后指出下一步最适合调用哪个 impeccable skill
```

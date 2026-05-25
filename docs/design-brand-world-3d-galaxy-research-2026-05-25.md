# 品牌世界 3D 立体图谱调研与落地边界（2026-05-25）

## 结论

可以实现类似“星系图”的品牌世界：支持放大缩小、3D 旋转、点击节点、展开第二圈关系。技术上最合适的路线是 `react-force-graph-3d`，它基于 Three.js/WebGL，并且和我们现在的 React/Next 前端可以通过客户端动态加载集成。

但它不应该替代当前默认的品牌世界主视图。Specta 的商业价值不是让用户看一个好看的宇宙，而是让品牌团队快速看清：

1. 品牌在 AI 回答里的位置。
2. 指标背后的样本、平台、竞品和来源。
3. 哪些关系值得继续追问。
4. 下一步该补什么内容、监测什么变化。

因此，3D 图谱应作为 `品牌世界` 的二级探索模式，默认仍保留可读性更强的 2D 关系图。

## 调研依据

### 1. react-force-graph

地址：https://github.com/vasturiano/react-force-graph

关键信息：

- 提供 React 组件，覆盖 2D、3D、VR、AR force graph。
- 3D 版本使用 Three.js/WebGL。
- 支持 zoom/pan、节点拖拽、节点/关系 hover/click。
- 有点击聚焦、点击展开/收起、自动适配画布、节点高亮等示例。

适配判断：

- 适合我们做 `品牌世界` 的 3D 探索模式。
- 可以直接接收 `{ nodes, links }` 结构，和当前 `graph_projection.nodes/edges` 映射成本低。
- 需要客户端动态加载，避免 Next SSR 触碰 WebGL。

### 2. 3d-force-graph

地址：https://github.com/vasturiano/3d-force-graph

关键信息：

- Web component，用 Three.js/WebGL 在三维空间渲染 force-directed graph。
- 支持 trackball / orbit / fly 控制。
- 官方示例包括 orbit controls、点击聚焦节点、点击展开/收起节点、大图渲染、暂停/恢复动画。

适配判断：

- 如果不用 React 包，也可以直接使用底层 3D 组件。
- 但在我们当前 Next/React 项目里，优先用 React binding，减少手写生命周期和 renderer 管理。

### 3. cosmos.gl

地址：https://github.com/cosmosgl/graph

关键信息：

- GPU 加速的 WebGL force graph，强调大规模图谱性能。
- 支持高规模点/边、拖拽、点击、聚类和视图 fit。

适配判断：

- 适合几十万点级别的大图，但我们的品牌世界第一版不是超大图。
- 它更偏 2D 高性能网络探索，不是最直接的 3D 旋转星系图方案。
- 后续如果世界对象规模非常大，可以作为大图性能路线研究。

### 4. Neo4j Bloom / Graph Visualization

地址：

- https://neo4j.com/docs/bloom-user-guide/current/
- https://neo4j.com/docs/getting-started/graph-visualization/graph-visualization-tools/

关键信息：

- Bloom 是业务用户可交互的图谱探索界面。
- Neo4j 的图谱可视化强调搜索、探索、缩放、关系查看和业务视角，而不是只画对象。

适配判断：

- 它不是我们可直接嵌入的前端库，但产品方向对我们有参考价值。
- 重要启发：图谱必须有业务语义、搜索/过滤和详情面板。纯视觉图不够。

## 产品边界

### 不能做成默认首屏

3D 图谱天然有学习成本。企业用户打开品牌主页，第一眼需要看到的是：

1. AI 提及率。
2. 提及排名。
3. 官网引用率。
4. 语气性质。
5. 明确的下一步建议。

3D 图谱适合回答第二层问题：

1. 这个指标和哪些平台、问题、回答、来源有关？
2. 我为什么排在这个位置？
3. 哪些竞品和我在同一批问题里被提到？
4. 哪些来源推动了 AI 对品牌的理解？
5. 哪些建议对应哪些证据缺口？

### 用户可见名称

不建议叫“星系图”。这个词容易把产品带向装饰感。

推荐用户可见名称：

- `关系图`
- `立体图谱`

页面结构建议：

```text
品牌世界
  [关系图] [立体图谱]

关系图：默认，清晰阅读指标和证据关系。
立体图谱：探索模式，适合放大、旋转、展开第二圈关系。
```

### 视觉原则

星系感只能来自空间层次，不来自科幻视觉。

允许：

- 3D 深度。
- 节点远近。
- 中心品牌与第一圈/第二圈关系。
- 轻微运动和节点聚焦。

禁止：

- 深色宇宙背景。
- 紫蓝渐变。
- 霓虹发光和装饰性光效。
- 星云、粒子风暴、玻璃拟态。
- 把边做成炫酷光束。

Specta 的 3D 图谱应仍然是浅色、证据导向、克制 teal、清晰阅读。

## 图谱结构

### 中心

```text
理想汽车
```

### 第一圈

```text
AI 提及率
提及排名
官网引用率
语气性质
竞品
AI 平台
引用来源
优化建议
```

### 第二圈展开规则

点击第一圈节点后，只展开该主题下的第二圈，避免一次性过载。

| 第一圈节点 | 第二圈展开 |
| --- | --- |
| AI 提及率 | 各 AI 平台提及率、提及/未提及回答样本 |
| 提及排名 | 目标品牌与竞品排名、各竞品提及率 |
| 官网引用率 | 官网域名、外部来源域名、引用次数 |
| 语气性质 | 正向/中性/负向回答样本 |
| 竞品 | 丰田、小米、腾势、领克等竞品节点 |
| AI 平台 | 元宝、豆包、DeepSeek、Kimi 等平台节点 |
| 引用来源 | 高频来源域名、官方/外部来源分组 |
| 优化建议 | 内容投放建议、官网证据页建议、监测建议 |

## 技术落地方案

### 依赖建议

```bash
npm install react-force-graph-3d
```

视实际 peer dependency 决定是否显式安装：

```bash
npm install three
```

### Next 集成方式

3D 图谱必须仅客户端加载：

```tsx
const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), {
  ssr: false,
});
```

### 数据映射

当前后端已经有：

```ts
OntologyGraphProjection {
  nodes: OntologyGraphNode[];
  edges: OntologyGraphEdge[];
}
```

可映射为：

```ts
{
  nodes: graph.nodes.map(node => ({
    id: node.id,
    name: title,
    type: node.type,
    group: semanticGroup,
    val: node.weight,
    color: tokenColor,
  })),
  links: graph.edges.map(edge => ({
    source: edge.from,
    target: edge.to,
    label: edge.label,
    strength: edge.strength,
  })),
}
```

### 必须补的图谱字段

为了让 3D 不是随机乱飞，后端或前端映射层需要补语义分组：

```ts
group:
  | 'brand'
  | 'metric'
  | 'platform'
  | 'competitor'
  | 'source'
  | 'sentiment'
  | 'recommendation'
  | 'sample'

ring_level: 0 | 1 | 2

expand_group:
  | 'mention_rate'
  | 'ranking'
  | 'official_citation_rate'
  | 'sentiment_distribution'
  | 'competitors'
  | 'platforms'
  | 'sources'
  | 'recommendations'
```

### 布局约束

必须固定中心和语义圈层：

1. 当前品牌固定在中心。
2. 第一圈按业务语义分区，不完全交给随机力导向。
3. 第二圈只在点击后加入图谱。
4. 节点总量默认控制在 80 个以内。
5. 超过 80 个时聚合成平台、来源、竞品组，不直接展开样本墙。

### 交互

| 操作 | 行为 |
| --- | --- |
| 滚轮 / 触控板 | 放大缩小 |
| 拖拽画布 | 3D 旋转 |
| 点击节点 | 聚焦节点，右侧显示指标、证据和关系 |
| 双击 / 展开按钮 | 展开第二圈 |
| 点击关系 | 显示关系动词、样本数、证据 |
| 复位按钮 | 回到中心品牌 |
| 切回关系图 | 回到 2D 默认视图 |

### 降级策略

| 场景 | 降级 |
| --- | --- |
| 移动端 | 默认显示 2D 关系图，不自动进入 3D |
| WebGL 不可用 | 显示 2D 关系图 |
| `prefers-reduced-motion` | 禁用自动旋转和持续动画 |
| 节点超过上限 | 聚合后展示 |
| 3D 组件加载失败 | 不影响品牌世界默认页 |

## 风险

1. 3D 图谱可读性天然弱于 2D，需要严格限制默认节点数量。
2. WebGL 增加包体和运行时风险，必须懒加载。
3. 3D canvas 对无障碍不友好，必须保留文字详情、2D 关系图和可键盘访问的证据入口。
4. 如果节点布局随机，用户会觉得“酷但看不懂”。必须使用语义圈层和点击展开。
5. 不能把品牌主页变成视觉 demo；商业主线仍是指标、证据、建议。

## 推荐实施顺序

### P1：不改默认体验，先加技术 Spike

- 新增 `BrandWorldGalaxyPanel`，只在开发开关或页签切换后出现。
- 用理想汽车的 `graph_projection` 映射 3D nodes/links。
- 实现缩放、旋转、点击节点、右侧详情复用。
- 保证 3D 加载失败不影响现有品牌世界。

### P2：补语义圈层和展开规则

- 给节点增加 group / ring_level / expand_group。
- 第一圈固定。
- 第二圈按当前点击主题展开。
- 来源、回答样本、竞品超过阈值时聚合。

### P3：产品化

- 加 `关系图 / 立体图谱` 切换。
- 默认仍是 `关系图`。
- 桌面支持 3D，移动端默认 2D。
- 完成截图、E2E、无障碍和性能验证。

## 当前判断

这条路线可以提升品牌世界的“空间感”和探索感，尤其适合向用户解释“品牌、平台、竞品、来源、建议是一个持续更新的世界”。但它不能弥补数据语义不清的问题。只有当 `提及率、排名、官网引用率、语气性质、竞品、平台、来源、建议` 的节点和关系已经稳定，3D 才会变成产品能力，而不是视觉噱头。

本阶段建议继续收口默认 2D 图谱和证据详情，同时启动一个受控的 3D Spike，不进入默认首屏。

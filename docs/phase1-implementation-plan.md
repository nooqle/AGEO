# Specta AI Phase 1 实施规划

> **版本**：1.0
> **日期**：2026-02-28
> **定位**：Phase 1 实施的核心执行文档
> **依据**：战略蓝图 + 团队四方 Debate（产品/架构/QA/UX）
> **上游文件**：`docs/strategic-blueprint-aeo-2026.md`（战略蓝图）
> **时间范围**：现在 → Q2 2026（约 12 周）
> **基础设施约束**：2 台阿里云 ECS（4vCPU, 8GB），≈ ¥900/月

---

## Executive Summary

Phase 1 的核心目标是将 Specta AI 从"技术原型"升级为"可交付的产品 MVP"。四项关键改造：

1. **异步任务**：用户不再傻等 8-12 分钟，提交后可离开，完成后系统通知
2. **产品叙事转型**：从"排名"全面迁移到"可见度概率"，BWVS 2.0 五维指标
3. **AICE Agent**：新增网页 AI 友好度评估工具，从"诊断"到"处方"的闭环
4. **数据质量基线**：Browser-Browser 一致性实验，建立三通道偏差矩阵

---

## 一、功能清单（按优先级）

### P0：不做就无法交付（Week 1-4）

| # | 功能 | 说明 | 工期 |
|---|------|------|------|
| P0-1 | Patchright 替换 Playwright | 一行 import 改动，反检测能力，最高 ROI | 0.5 天 |
| P0-2 | Browser 采集稳定性修复 | Kimi `.new-chat-btn` 超时、`.mask` 遮罩、Doubao 崩溃 | 2 天 |
| P0-3 | P0 Bug 修复 | POLA/宝丽重复、空集 Jaccard=1.0、A5 假情感/竞品 | 1 天 |
| P0-4 | BWVS 2.0 指标升级 | 35/25/15/15/10 新权重 + position_score 新维度 | 2 天 |
| P0-5 | 产品语言更新 | "排名"→"可见度概率"，全站零"排名"文案 | 2 天 |
| P0-6 | **异步任务架构** | 任务执行脱离 WS 生命周期，`asyncio.create_task` | 5 天 |
| P0-7 | Selector 外部化 | CSS Selector 迁移到 YAML 配置，支持热更新 | 1 天 |

### P1：显著提升价值（Week 5-8）

| # | 功能 | 说明 | 工期 |
|---|------|------|------|
| P1-1 | **AICE Agent** | 9C 评分 + 改写建议，Orchestrator 新增 Function Tool | 5 天 |
| P1-2 | Dashboard 重构 | Hero 指标 + TaskActivityFeed + AICE 卡片 | 4 天 |
| P1-3 | 通知系统增强 | 任务完成/失败通知 + alertStore 扩展 | 2 天 |
| P1-4 | Chat 非阻塞输入 | 任务执行中用户可继续对话 | 2 天 |
| P1-5 | 双轨采集 UI | Fast Track（API）vs Deep Scan（Browser）选项 | 2 天 |

### P2：数据质量验证（**可提前启动，不依赖功能开发**）

> **注意**：Browser 基线实验是独立任务，只需现有脚本 + 现有 Browser Handler 即可执行。
> 建议 Week 1 就用 Kimi + DeepSeek 先跑起来，不必等到 Week 5。

| # | 功能 | 说明 | 工期 |
|---|------|------|------|
| P2-0 | **元宝 Browser Handler** | 新增 `yuanbao_handler.py`，继承 `BaseBrowserHandler`，补齐 4 平台 Browser 覆盖 | 2 天 |
| P2-1 | Browser-Browser 基线实验 | 5 题×5 次×3 平台（Kimi+DeepSeek+元宝），建立 intra-Browser Jaccard | 3 天 |
| P2-2 | 三通道偏差矩阵 | API-API / Browser-Browser / API-Browser 统一实验 | 4 天 |
| P2-3 | 品牌提取 LLM 升级 | 正则词典→LLM 提取，F1 目标 ≥ 0.80 | 3 天 |

### P3：打磨（Week 9-12）

| # | 功能 | 说明 | 工期 |
|---|------|------|------|
| P3-1 | Settings 通知偏好激活 | 站内/浏览器推送开关 | 1 天 |
| P3-2 | 多轮对话增强 | "深入分析 X 平台""和上次对比" | 3 天 |
| P3-3 | 首页文案重构 | Landing page 对齐新叙事 | 1 天 |
| P3-4 | 端到端 QA + 性能优化 | 自动化测试 + 优化 | 5 天 |

---

## 二、异步任务架构（团队共识方案）

### 2.1 技术选型

| 方案 | 评估 | 结论 |
|------|------|------|
| Celery + Redis | 进程隔离好，但引入 2 个新依赖 | **Phase 2 候选** |
| **asyncio.create_task** | 零新依赖，利用现有事件循环 | **Phase 1 采用** |
| ARQ (async Redis) | 轻量但仍需 Redis | Phase 2 候选 |

**采用 asyncio.create_task 的理由**：
- Phase 1 单 worker 部署，asyncio 完全足够
- AnalysisTask 模型已有完整生命周期（PENDING/RUNNING/COMPLETED/FAILED/CANCELLED）
- TaskService.recover_orphan_tasks() 已处理孤儿任务
- 不引入新基础设施依赖，控制在 ¥900/月预算

**升级信号**（何时迁移到 Celery）：日均分析 > 20 次、需 multi-worker 扩展、任务队列积压 > 10 个

### 2.2 核心改造：从同步阻塞到后台执行

**当前问题**：A4 执行期间（8-12 分钟），整个 astream 循环阻塞在 WS handler 中

**改造方案**：在 astream 循环中检测到 A4 开始时，将后续 pipeline 剥离到后台

```
用户确认采集
  → 创建 AnalysisTask (status=PENDING)
  → asyncio.create_task(_continue_pipeline_in_background(...))
  → WS 立即回复 "任务已提交，预计 8-12 分钟"
  → 用户可关闭页面

后台任务
  → A4 每完成一个平台: TaskService.update_progress()
  → A5 完成: TaskService.complete_task() + 生成通知
  → WS: task_completed (if connected)

用户回来
  → GET /tasks/{id} → stage_results_cache
  → 或 WS reconnect → replay cache
```

### 2.3 用户体验流程（UX 设计）

**场景 A - 用户在线等待**：保持现有实时流式体验 + 顶部 Banner "可以安全离开"

**场景 B - 用户离开后回来**：
1. Dashboard TaskActivityFeed 显示"已完成"卡片
2. NotificationBell 角标亮起
3. 点击任何入口→跳转到 Chat→Canvas 自动打开报告

**场景 C - 任务失败**：
- Toast 显示错误原因 + 一键重试按钮
- 部分完成（3/4 平台成功）也展示可用结果

### 2.4 新增 WS 事件

| 事件 | 触发时机 | 数据 |
|------|---------|------|
| `task_submitted` | 任务转入后台时 | `{task_id, estimated_minutes}` |
| `task_completed` | A5 完成时 | `{task_id, snapshot_id}` |
| `task_failed` | 任务失败时 | `{task_id, error, retry_available}` |

### 2.5 现有基础设施复用（~80% 已就位）

| 组件 | 状态 | 需要改动 |
|------|------|---------|
| AnalysisTask 模型 | 已有完整字段 | 无需改动 |
| TaskService CRUD | 已有全套生命周期 | 无需改动 |
| Task API 端点 | 已有 list/get/cancel | 无需改动 |
| TaskNotificationPoller | 已有，轮询弹 Toast | 改为同时写入 alertStore |
| NotificationBell | 已有，轮询 alertStore | 扩展通知类型 |
| ReconnectionBanner | 已有，断线重连重放 | 无需改动 |

**需要新建**：
- 后台任务执行函数（从 WS handler 剥离）
- Dashboard TaskActivityFeed 组件
- Chat "可以安全离开"提示卡片
- 侧栏进度百分比显示

---

## 三、AICE Agent 设计

### 3.1 产品定义

AICE（AI Content Evaluation）填补"诊断→处方"断层：用户通过 A1-A5 知道"可见度不高"，通过 AICE 知道"为什么"和"怎么改"。

**三个入口**（Chat-first 一致性）：
1. **Chat 自然语言**（主入口）：`"检查 https://example.com 的 AI 友好度"`
2. **A5 报告内行动建议**：引用质量分低时推荐 AICE
3. **Dashboard AICE 卡片**：快捷入口弹窗

**与 A1-A5 的关系**：独立 Agent，不嵌入流水线。使用时机不同（诊断 vs 处方）、输入不同（品牌名 vs URL）。但有数据联动——A5 引用质量分低时自动推荐 AICE。

### 3.2 竞品差异化

| 竞品 | 核心差异 |
|------|---------|
| HubSpot AEO Grader（免费） | 品牌级评估；我们是**页面级**内容评估 |
| Discovered Labs CITABLE（免费/付费） | CITABLE 框架；我们用 9C + **改写建议** |
| SEMAI Scoring Engine | 英文；我们支持**中文内容 + 中国 AI 平台实测验证** |
| AI Rank Lab（免费） | 覆盖 ChatGPT/Claude；我们覆盖 **Kimi/豆包/DeepSeek/混元** |

**核心差异化**：中国 AI 平台实测验证（改写后用 A4 实测效果）+ Chat-first 交互 + 闭环优化

### 3.3 技术架构

**集成方式**：Orchestrator 星型拓扑新增一个 Function Tool，不独立 Graph

```python
# orchestrator_node.py AGENT_REGISTRY 新增
{
    "name": "aice_analysis",
    "description": "分析指定网页的 AI 友好度（AICE 评分）...",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要分析的网页 URL"},
        },
        "required": ["url"],
    },
}
```

**URL 抓取**：httpx + BeautifulSoup 为主（覆盖 80%+ SSR 页面），Patchright 为 SPA fallback

**9C 评分**：单次 LLM 调用 + 结构化 JSON 输出（MiniMax M2.1 的 16K context 够用）

**报告输出**：Canvas 新增 `aiceReport` 内容类型
- 总分环形图 + 等级标签
- 9C 雷达图（Recharts RadarChart）
- Top 3 优化建议（按影响分排序）
- Before/After 改写对比（非 diff 视图，并排展示）
- 一键复制建议代码

### 3.4 9C 评分框架（升级版）

| 维度 | 权重 | 评估内容 | 满分 |
|------|------|---------|------|
| **C6: Coverage（覆盖度）** | 25% | 话题完整性、FAQ 覆盖、信息密度；技术可访问性（爬虫不可读=0） | 25 |
| **C8: Timeliness（时效性）** | 15% | 日期标记、更新频率、引用数据时效 | 15 |
| **C1: Credibility（信源可信度）** | 10% | 作者信息、机构背书、外部引用源质量 | 10 |
| **C4: Claim Balance（宣传平衡性）** | 10% | 多角度论述、避免绝对化宣称 | 10 |
| **C9a: Semantic Tagging（语义标签）** | 10% | H1-H6 层级、article/section/main 使用 | 10 |
| **C9b: Schema Usage（结构化数据）** | 10% | JSON-LD/Microdata Schema.org 标记 | 10 |
| **C2: Consistency（内容一致性）** | 5% | 页面内信息自洽、术语统一 | 5 |
| **C3: Checkability（可核查性）** | 5% | 数据有来源链接、声明可验证 | 5 |
| **C5: Clarity（结构清晰度）** | 5% | 语言简洁、可读性、术语有解释 | 5 |
| **C7: Intent Match（意图匹配）** | 5% | 内容回答目标用户实际搜索的问题 | 5 |

---

## 四、可见度指标体系（Phase 1 策略调整）

### 4.1 策略：Phase 1 展示原始指标，暂不做综合分

> **设计原则**：综合评分（BWVS 2.0）本身是算法加成，在没有足够历史数据和基线校准之前，
> 先让客户看到**每一个可理解、可行动的原始指标**，比一个"黑箱分数"更有价值。
> BWVS 综合分推迟到 Phase 2，届时有数据支撑再定权重。

**Phase 1 展示的原始指标**：

| 指标 | 含义 | 客户理解门槛 |
|------|------|-------------|
| 提及率 | "4 个平台中有 3 个提到了您" → 75% | 直觉的 |
| 提及位置 | "在回答的第 2 段首次被提及" | 直觉的 |
| 情感倾向 | "正面/中性/负面" + 关键词摘要 | 直觉的 |
| 平台覆盖率 | "4 个平台中覆盖了 3 个" | 直觉的 |
| **官网引用追踪** | "您的官网在 Kimi 上被引用了 3 次" | **客户最关心的** |

### 4.2 官网引用追踪（核心客户需求）

> **客户原话**："他们官网的内容到底在这个过程里被引用了多少，是他们比较看重的。"

**不是笼统的"引用了多少次"，而是完整的分平台引用明细：**

#### 数据模型

```python
# A5 输出新增字段：citation_tracking
{
  "citation_tracking": {
    "brand_domain": "example.com",           # A1 阶段用户提供
    "total_citations": 8,                     # 总引用次数
    "total_questions": 24,                    # 总提问次数
    "citation_rate": 0.333,                   # 引用率 = 8/24
    "by_platform": {
      "kimi": {
        "citations": 3,
        "questions_asked": 6,
        "citation_rate": 0.50,
        "cited_pages": [
          {
            "url": "https://example.com/products/x",
            "title": "产品 X 介绍",
            "cited_in_questions": ["什么是最好的 X 产品？", "X 品类有哪些推荐？"],
            "citation_context": "根据 example.com 的介绍，产品 X 具有..."   # AI 引用时的原文片段
          },
          {
            "url": "https://example.com/about",
            "title": "关于我们",
            "cited_in_questions": ["X 行业有哪些知名品牌？"],
            "citation_context": "example 公司成立于..."
          }
        ]
      },
      "deepseek": {
        "citations": 2,
        "questions_asked": 6,
        "citation_rate": 0.333,
        "cited_pages": [...]
      },
      "doubao": {
        "citations": 2,
        "questions_asked": 6,
        "citation_rate": 0.333,
        "cited_pages": [...]
      },
      "hunyuan": {
        "citations": 1,
        "questions_asked": 6,
        "citation_rate": 0.167,
        "cited_pages": [...]
      }
    }
  }
}
```

#### 数据来源

| 平台 | 引用数据来源 | 当前可用性 |
|------|------------|-----------|
| 混元 (API) | `search_references` 字段，包含 `url`、`title`、`snippet` | 已有 |
| Kimi (API) | 回答中的引用链接解析 | 已有 |
| DeepSeek (Browser) | 回答 HTML 中的引用链接提取 | 需新增解析 |
| 豆包 (API) | 回答中的引用链接解析 | 需确认 API 返回格式 |

#### 匹配逻辑

```
用户在 A1 阶段提供品牌官网域名（如 example.com）
→ A4 采集时保存每个回答的 search_references / 引用链接
→ A5 分析时：
   1. 遍历所有回答的引用来源
   2. URL 域名匹配 brand_domain（含子域名 *.example.com）
   3. 按平台分组统计
   4. 记录具体被引用的页面 URL + 对应的提问 + 引用上下文
```

#### 前端展示——引用追踪卡片

```
+--- 官网引用追踪 -----------------------------------------+
|                                                            |
|  您的官网 (example.com) 在 24 次提问中被引用了 8 次        |
|  总体引用率: 33.3%                                         |
|                                                            |
|  ┌── 按平台 ────────────────────────────────────────┐     |
|  │ Kimi      ████████████████░░░░  3/6 (50.0%)     │     |
|  │ DeepSeek  ██████████░░░░░░░░░░  2/6 (33.3%)     │     |
|  │ 豆包      ██████████░░░░░░░░░░  2/6 (33.3%)     │     |
|  │ 混元      █████░░░░░░░░░░░░░░░  1/6 (16.7%)     │     |
|  └──────────────────────────────────────────────────┘     |
|                                                            |
|  ┌── 被引用最多的页面 ──────────────────────────────┐     |
|  │ 1. /products/x (产品X介绍)     — 被引 3 次      │     |
|  │    Kimi×2, DeepSeek×1                            │     |
|  │    问题: "什么是最好的X产品？" "X品类推荐？"      │     |
|  │                                                   │     |
|  │ 2. /about (关于我们)            — 被引 2 次      │     |
|  │    Kimi×1, 混元×1                                │     |
|  │    问题: "X行业有哪些知名品牌？"                  │     |
|  │                                                   │     |
|  │ 3. /blog/guide (选购指南)       — 被引 1 次      │     |
|  │    豆包×1                                        │     |
|  │    问题: "如何选择X产品？"                        │     |
|  └──────────────────────────────────────────────────┘     |
|                                                            |
|  未被引用的重要页面: /case-studies, /pricing               |
|  💡 建议: 优化 /case-studies 页面的 AI 可引用性 → AICE 评估|
+------------------------------------------------------------+
```

### 4.3 提及位置分（原始指标之一）

| 位置类型 | 标签 | 判断标准 |
|---------|------|---------|
| 首位推荐 | "首位推荐" | 回答中第一个被提及的品牌 |
| 前 3 位 | "优先提及" | 第 2-3 个被提及 |
| 列举中 | "被列举" | 第 4-10 个 |
| 附带提及 | "附带提及" | 出现在次要段落/比较表格 |

### 4.4 产品语言对照表

| 旧表述 | 新表述 |
|--------|--------|
| "品牌在 AI 搜索中排名第 3" | "当消费者搜索时，品牌有 **67%** 的概率被提及" |
| "BWVS 指数 45.2" | 暂不展示综合分，展示各项原始指标 |
| "提及率 67%" | "在 100 次搜索中，约有 67 次品牌被提及" |
| "竞品 A 排名高于您" | "竞品 A 被提及概率（82%）高于您（67%）" |
| 无 | "您的官网在 Kimi 上被引用了 3 次，在 DeepSeek 上被引用了 2 次" |
| 无 | "以上数据基于 N 次采样的统计结果" |

### 4.5 Dashboard KPI 卡片升级

| 位置 | 旧 | 新 |
|------|-----|-----|
| 卡片 1 | 品牌可见度 (BWVS 指数) | **AI 出现概率** — "67% 的概率被提及" + "基于 N 个样本" |
| 卡片 2 | 提及率 % | **平台覆盖率** — "4 平台中覆盖 3 个" |
| 卡片 3 | 声量份额 % | **官网引用率** — "您的官网被引用了 8 次" |
| 卡片 4 | 品牌数量 | **AICE 评分**（内容 AI 友好度） |

### 4.6 BWVS 2.0 综合分（Phase 2 实施）

Phase 2 有了历史数据和基线校准后，再启用综合分：
```
BWVS = 35×提及率 + 25×提及位置分 + 15×情感得分 + 15×平台覆盖率 + 10×引用质量分
```
届时的触发条件：① 积累 ≥ 50 个品牌分析案例 ② 三通道基线实验完成 ③ 客户反馈确认权重合理性

---

## 五、数据质量基线（QA 方案）

### 5.1 前置条件——Browser 采集稳定性

| 平台 | 当前成功率 | 目标 | 主要问题 |
|------|-----------|------|---------|
| Kimi Browser | ~30% | ≥ 90% | `.new-chat-btn` viewport 外超时（占 80% 失败） |
| Doubao Browser | ~65% | ≥ 90% | 浏览器上下文崩溃、回答为空 |

**必须先修复稳定性，再做一致性实验。**

### 5.2 三通道基线矩阵实验

> **4 平台 Browser 覆盖**：当前只有 Kimi + DeepSeek 两个 Browser Handler，
> 需先新增 `yuanbao_handler.py`（元宝/混元网页版）后，方可完整覆盖 4 平台。
> 豆包 Browser Handler 优先级低于元宝（豆包已有 API 通道）。

| 平台 | API | Browser | 状态 |
|------|-----|---------|------|
| Kimi | `kimi_client.py` | `kimi_handler.py` | 已有 |
| DeepSeek | — | `deepseek_handler.py` | 已有 |
| 豆包 | `doubao_client.py` | — | Phase 2 补 |
| **混元/元宝** | `hunyuan_client.py` | **`yuanbao_handler.py`（新增）** | **P2-0** |

```
Phase A（可 Week 1 启动，用现有 Handler）:
  5 个问题 × 2 个平台 (Kimi+DeepSeek) × 5 轮
  每轮: Browser×1（间隔 60s）
  产出: 50 次 Browser 调用 → Browser-Browser Jaccard 初步数据
  预估时间: 2-3 小时

Phase B（元宝 Handler 就绪后）:
  5 个问题 × 3 个平台 (Kimi+DeepSeek+元宝) × 3 轮
  每轮: API×2 + Browser×1（间隔 60s）
  轮间隔: 10 分钟
  产出:
    - 90 次 API 调用 → API-API Jaccard
    - 45 次 Browser 调用 → Browser-Browser Jaccard
    - API-Browser 交叉对比
  预估时间: 4-5 小时
```

**统计方法**：
- H0：API-Browser 差异 = 天然随机性（无系统性通道差异）
- Mann-Whitney U 检验，alpha = 0.05
- 通道偏差系数 = (min(J_AA, J_BB) - J_AB) / min(J_AA, J_BB)
  - < 0.1：可忽略
  - 0.1-0.3：可校正
  - ≥ 0.3：不能混用数据

### 5.3 Phase 1 数据质量 KPI

| KPI | 目标 | 当前 |
|-----|------|------|
| 品牌提取 F1 | ≥ 0.80 | ~0.68 |
| 重复品牌 Bug | 0 个 | ≥ 2 个 |
| 95% CI 宽度 | ≤ 15 百分点 | ~40 百分点 |
| Browser 采集成功率 | ≥ 90% | 30-65% |
| 有效数据点 | ≥ 62 | ~40 |

---

## 六、UX 关键设计

### 6.1 异步任务——4 层状态反馈

| 层级 | 组件 | 信号 |
|------|------|------|
| Chat 内 | 阶段进度条（可折叠） | running 时显示各平台进度 |
| 侧栏 | ChatSidebar 圆点 | 橙色脉冲=运行中, 绿色闪烁=完成 |
| Dashboard | TaskActivityFeed | 任务卡片列表 + 状态 + 操作 |
| 通知 | NotificationBell + Toast | 跨页面持久通知 |

### 6.2 非阻塞输入（重要 UX 改进）

**当前**：任务执行中输入框被 `isAgentExecuting` 阻塞
**改造**：输入框始终可用

- 对话类问题走快速 LLM 响应，不影响后台任务
- 新任务请求提供"等待/并行"选项
- `ChatPanel.tsx` 第 357 行去掉 `isAgentExecuting` 阻塞

### 6.3 AICE 报告 Canvas 设计

```
+--- AICE 报告 Canvas ---+
| 总分: 72/100 [良好]     |
| (环形进度图)             |
|                          |
| 9C 雷达图 + 评分列表     |
| (左右并排)               |
|                          |
| Top 3 改进建议           |
| 按影响分排序             |
| 可展开 Before/After 对比  |
| [一键复制建议代码]        |
+--------------------------+
```

### 6.4 通知系统扩展

现有 `alertStore` 只管理 MonitoringAlert，扩展支持：
- `task_completed`：绿色左边框，跳转到 Canvas
- `task_failed`：红色左边框，重试按钮
- `task_partial`：黄色左边框，查看+重试
- 按时间分组（今天/昨天/更早）

**通知渠道规划**：
| 渠道 | Phase | 说明 |
|------|-------|------|
| 平台内通知（铃铛+Toast） | **Phase 1** | 基于现有 alertStore + NotificationBell |
| 浏览器推送（Web Push） | Phase 1 (P3-1) | Settings 中开关控制 |
| **邮件订阅** | **Phase 2** | 需用户登录体系（邮箱字段），接入阿里云/SendGrid |

> Phase 1 不做邮件通知，原因：当前无用户注册/登录体系，无邮箱字段。
> Phase 2 建设用户体系时，邮件通知自然接入（阿里云邮件推送 ¥2/1000封，成本可忽略）。

---

## 七、文件改动清单

### 后端

| 文件 | 改动类型 | 内容 | 优先级 |
|------|---------|------|--------|
| `backend/requirements.txt` | 修改 | `playwright` → `patchright` | P0-1 |
| `backend/app/core/fetchers/browser/playwright_client.py` | 修改 | import 替换 | P0-1 |
| `backend/app/core/playwright_installer.py` | 修改 | import + 安装命令替换 | P0-1 |
| `backend/scripts/install_playwright.bat/.sh` | 修改 | patchright 安装命令 | P0-1 |
| `backend/app/core/fetchers/browser/kimi_handler.py` | 修改 | `.new-chat-btn` 修复 + Selector 外部化 | P0-2 |
| `backend/app/core/fetchers/browser/deepseek_handler.py` | 修改 | Selector 外部化 | P0-7 |
| `backend/app/core/fetchers/browser/selectors.py` | **新建** | 统一 Selector 配置（支持 YAML 热更新） | P0-7 |
| `backend/selectors.yaml` | **新建** | 外部 Selector 配置文件 | P0-7 |
| `backend/scripts/api_vs_browser_test.py` | 修改 | POLA/宝丽修复 + 空集 Jaccard 修复 + patchright import | P0-3 |
| `backend/app/workflow/nodes_a5.py` | 修改 | BWVS 权重 35/25/15/15/10 + position_score + 情感修复 | P0-4 |
| `backend/prompts/a5_*.yaml` | 修改 | 报告模板文案→概率性叙事 | P0-5 |
| `backend/app/workflow/events.py` | 修改 | 新增 task_submitted/task_completed/task_failed 事件 | P0-6 |
| `backend/app/api/v1/websocket_langgraph.py` | 修改 | A4+A5 剥离到 asyncio.create_task | P0-6 |
| `backend/app/workflow/nodes_a4.py` | 修改 | 每平台完成后 TaskService.update_progress() | P0-6 |
| `backend/app/workflow/nodes_aice.py` | **新建** | AICE Agent 节点（URL fetch + 9C 评分 + 报告） | P1-1 |
| `backend/prompts/aice_system.md` | **新建** | 9C 评分 system prompt | P1-1 |
| `backend/app/workflow/orchestrator_node.py` | 修改 | AGENT_REGISTRY 新增 aice_analysis tool | P1-1 |
| `backend/app/workflow/graph.py` | 修改 | 新增 aice node + edge | P1-1 |
| `backend/app/workflow/state.py` | 修改 | 新增 aice_report 字段 | P1-1 |
| `backend/app/core/fetchers/url_fetcher.py` | **新建** | httpx + BeautifulSoup URL 内容提取 | P1-1 |
| `backend/app/core/fetchers/browser/yuanbao_handler.py` | **新建** | 元宝(混元)网页版 Browser Handler，继承 BaseBrowserHandler | P2-0 |
| `backend/app/core/fetchers/browser/__init__.py` | 修改 | 导出 YuanbaoHandler | P2-0 |
| `backend/app/workflow/nodes_a5.py` (引用追踪) | 修改 | 新增 `_build_citation_tracking()` 按平台统计官网引用明细 | P0-4 |
| `backend/app/workflow/nodes_a4.py` (引用保存) | 修改 | 保存每个回答的 `search_references` / 引用链接到 state | P0-4 |
| `backend/scripts/browser_consistency_test.py` | **新建** | Browser 自身重复一致性测试脚本 | P2-1 |

### 前端

| 文件 | 改动类型 | 内容 | 优先级 |
|------|---------|------|--------|
| `frontend/src/components/dashboard/KPICard.tsx` | 修改 | 文案更新 + sampleCount 属性 | P0-5 |
| `frontend/src/components/dashboard/DashboardPage.tsx` | 修改 | 插入 TaskActivityFeed + AICE 卡片 | P1-2 |
| `frontend/src/components/dashboard/HeroSection.tsx` | 修改 | 追加任务计数 | P1-2 |
| `frontend/src/components/dashboard/TaskActivityFeed.tsx` | **新建** | 任务状态列表 | P1-2 |
| `frontend/src/components/dashboard/TaskActivityItem.tsx` | **新建** | 单条任务状态卡片 | P1-2 |
| `frontend/src/components/dashboard/URLInputDialog.tsx` | **新建** | AICE 快捷入口弹窗 | P1-1 |
| `frontend/src/stores/conversationStore.ts` | 修改 | activeTaskId + 非阻塞模式 | P0-6 |
| `frontend/src/stores/alertStore.ts` | 修改 | 扩展通知类型 + action_url | P1-3 |
| `frontend/src/stores/canvasStore.ts` | 修改 | 增加 'aiceReport' 类型 | P1-1 |
| `frontend/src/stores/dashboardStore.ts` | 修改 | activeTasks[] + recentTasks[] | P1-2 |
| `frontend/src/services/websocket.ts` | 修改 | 监听 task_submitted/task_completed | P0-6 |
| `frontend/src/components/chat/ChatPanel.tsx` | 修改 | 非阻塞输入 + 进度折叠 + 安全离开提示 | P1-4 |
| `frontend/src/components/chat/TaskNotificationPoller.tsx` | 修改 | 写入 alertStore | P1-3 |
| `frontend/src/components/chat/CollapsibleProgress.tsx` | **新建** | 可折叠阶段进度 | P1-4 |
| `frontend/src/components/layout/ChatSidebar.tsx` | 修改 | 进度百分比 + 状态文字 | P1-4 |
| `frontend/src/components/notifications/NotificationPanel.tsx` | 修改 | 新通知类型 + 日期分组 | P1-3 |
| `frontend/src/components/notifications/AlertCard.tsx` | 修改 | task 通知样式 | P1-3 |
| `frontend/src/components/canvas/CanvasPanel.tsx` | 修改 | 增加 aiceReport 路由 | P1-1 |
| `frontend/src/components/canvas/contents/AICEReportContent.tsx` | **新建** | AICE 报告渲染 | P1-1 |
| `frontend/src/components/canvas/contents/AICERadarChart.tsx` | **新建** | 9C 雷达图 (Recharts) | P1-1 |
| `frontend/src/components/canvas/contents/AICERewriteSuggestion.tsx` | **新建** | Before/After 改写建议 | P1-1 |
| `frontend/src/components/canvas/contents/CitationTrackingCard.tsx` | **新建** | 官网引用追踪卡片（按平台柱状图 + 被引页面列表） | P0-4 |
| `frontend/src/components/canvas/contents/BwvsBreakdownSection.tsx` | 修改 | 展示原始指标（去掉综合分，改为各维度独立展示） | P0-4 |
| `frontend/src/components/landing/hero.tsx` | 修改 | 副标题文案更新 | P3-3 |
| `frontend/src/components/landing/features.tsx` | 修改 | 功能列表更新 | P3-3 |

---

## 八、执行时间线

```
Week 1-2（立即开始）
├── P0-1: Patchright 替换（0.5天）
├── P0-2: Browser 采集稳定性修复（2天）
├── P0-3: P0 Bug 修复（POLA/宝丽 + 空集 Jaccard + A5 假数据）（1天）
├── P0-4: BWVS 2.0 权重更新 + position_score（2天）
├── P0-5: 产品语言更新（2天）
└── P0-7: Selector 外部化（1天）

Week 3-4
├── P0-6: 异步任务核心改造
│   ├── 后端：任务执行脱离 WS 生命周期（3天）
│   ├── 前端：WS 事件监听 + conversationStore 改造（1天）
│   └── 前端：SafeToLeaveCard + 侧栏进度（1天）
└── Browser 稳定性验证：每平台 10 次单题，确认 ≥ 90%

Week 5-6
├── P1-1: AICE Agent 后端（nodes_aice.py + url_fetcher + prompt）（3天）
├── P1-1: AICE Agent 前端（Canvas 组件 + 报告渲染）（2天）
├── P2-1: Browser-Browser 基线实验执行（3天）
└── P1-5: 双轨采集 UI（2天）

Week 7-8
├── P1-2: Dashboard 重构（TaskActivityFeed + Hero + AICE 卡片）（4天）
├── P1-3: 通知系统增强（alertStore + NotificationPanel）（2天）
├── P1-4: Chat 非阻塞输入 + 进度折叠（2天）
├── P2-2: 三通道偏差矩阵实验（4天）
└── P2-3: 品牌提取 LLM 升级（3天）

Week 9-10
├── P3-1: Settings 通知偏好激活（1天）
├── P3-2: 多轮对话增强（3天）
├── P3-3: 首页文案重构（1天）
└── 集成测试 + 回归测试

Week 11-12（Q2 收尾）
├── 端到端 QA
├── 性能优化
├── Phase 1 数据质量报告编写
└── Phase 1 交付评审
```

---

## 九、Phase 1 成功标准

| 指标 | 当前 | Phase 1 目标 |
|------|------|-------------|
| 端到端分析成功率 | ~40% | ≥ 75% |
| BWVS 指标维度 | 4 维 | 5 维（+position） |
| 用户可离线等待 | 否 | 是 |
| 通知触达率 | 0% | ≥ 80% |
| AICE 评估能力 | 无 | 9C 评分 + 改写建议 |
| "排名"文案残留 | 多处 | 0 |
| Fast Track 耗时 | 5-10 分钟 | ≤ 2 分钟 |
| Browser 采集成功率 | 30-65% | ≥ 90% |
| 品牌提取 F1 | ~0.68 | ≥ 0.80 |

---

## 十、开放问题与未决分歧

| # | 问题 | 双方观点 | 建议决策时机 |
|---|------|---------|------------|
| 1 | "引用质量分"数据来源 | 产品：Phase 1 简化版（品牌官网是否被引用）；架构：需要外链分析 | P0-4 实施时 |
| 2 | 提及位置判断方法 | LLM 辅助判断 vs 基于文本位置的启发式规则 | P0-4 实施时 |
| 3 | AICE 评分是否存 DB | 架构：存入 AnalysisSnapshot 子文档 | P1-1 实施时 |
| 4 | 一致性分数需要多次采样 | QA：先 3 次/问题；产品：成本太高则推迟 Phase 2 | P2 实验后 |
| 5 | A2 Persona 优先级 | 产品：P0 修好；架构：推迟到 Phase 3 | Phase 1 结束时 |
| 6 | Browser 投入时机 | 产品/UX：方向比速度重要；架构/QA：先验证基线 | P2 实验后 |

---

## 十一、Patchright 迁移（最小改动，最先执行）

**仅需修改 4 个文件的 import**：

| 文件 | 行号 | 改动 |
|------|------|------|
| `playwright_client.py` | L12 | `from playwright.async_api` → `from patchright.async_api` |
| `playwright_installer.py` | L65, L157 | 同上 + 安装命令改为 `python -m patchright install chromium` |
| `scripts/api_vs_browser_test.py` | L304 | `from playwright.async_api` → `from patchright.async_api` |
| `scripts/browser_login.py` | L21 | 同上 |

**API 完全兼容**，Patchright 是 Playwright 的 drop-in replacement。仅支持 Chromium（我们当前只用 Chromium，无风险）。

**验证步骤**：
1. 冒烟测试：`pip install patchright && python -m patchright install chromium` + 运行 browser_login.py（30 分钟）
2. 回归测试：完整 A4 pipeline（2 小时）
3. 检测规避验证：https://bot.sannysoft.com/ 截图对比（1 小时）

---

## 十二、现有产品稳定性保障

> **核心原则**：增量式改造，不重写。现有已打磨好的交互和细节不能被破坏。

### 12.1 保护策略

| 策略 | 具体做法 |
|------|---------|
| **不动组件内部** | ChatPanel、Canvas、ProgressBar 等已打磨组件，**内部逻辑不碰**。异步改造只改"调用方"（workflow层），不改"展示方" |
| **新功能 = 新文件** | AICE Agent → `nodes_aice.py`（新建）；引用追踪 → `CitationTrackingCard.tsx`（新建）；不修改已有组件 |
| **前端加法不减法** | Dashboard 改版是**新增 tab/视图**，不删现有内容；通知面板扩展类型，不重构结构 |
| **功能开关** | 异步模式 feature flag 控制，默认关闭。开启后走异步路径，老路径完整保留 |
| **逐步替换** | Patchright 先在一个 handler 里换 import 测试，确认无问题再推广 |

### 12.2 具体保护措施

1. **变更前快照**：每个 P 级任务开始前 `git tag pre-<task-id>`，任何时候可回滚
2. **PR 范围最小化**：一个 PR 只做一件事（如"异步任务后端"和"异步任务前端"拆两个 PR）
3. **现有 E2E 测试守护**：6 个 E2E 测试用例（casual_chat, a1_brand, full_pipeline 等），每次改动后必须全通过
4. **前端视觉回归**：改 UI 前截图保存，改后对比。任何视觉差异必须解释原因
5. **团队交叉验收**：QA + UX 以真实用户视角验收，不是"测功能"而是"用产品"

### 12.3 每个 PR 的 Not-Doing 清单（强制执行）

每个 PR 描述中必须包含"本 PR 不做的事"，例如：
- 异步任务 PR：不改 ChatPanel 渲染逻辑，不改 Canvas 组件，不改 WebSocket 事件格式
- AICE Agent PR：不修改 A1-A5 任何 node，不改 orchestrator 路由逻辑（只新增 tool）
- Dashboard PR：不删除现有 KPI 卡片，只新增/替换内容

---

## 十三、云端浏览器方案调研——腾讯云 Agent 工具箱 & Agent 沙箱

### 13.1 两个产品概述

| 维度 | Agent 工具箱 | Agent 沙箱 |
|------|-------------|-----------|
| **定位** | 一站式 AI Agent 开发/部署环境 | 轻量级隔离运行环境 |
| **核心组件** | Agent 沙箱 + LangGraph + Langfuse + Qdrant | LLM Sandbox + Playwright MCP |
| **浏览器能力** | 有（内含 Agent 沙箱的 Playwright） | 有（Playwright MCP，端口 8931） |
| **额外能力** | 向量数据库(Qdrant) + 可观测性(Langfuse) + 工作流(LangGraph) | 仅代码执行 + 浏览器自动化 |
| **底层系统** | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| **最低配置** | 2GB 内存, 20GB 磁盘 | 1GB 内存, 20GB 磁盘 |
| **计费** | 轻量应用服务器套餐制（按月/年） | 轻量应用服务器套餐制（按月/年） |

**关系**：Agent 工具箱 **包含** Agent 沙箱（是超集）。Agent 沙箱是工具箱的子组件之一。

### 13.2 与我们的适配分析

**Agent 沙箱的 Playwright MCP 能力与我们的需求高度匹配：**

| 我们的需求 | Agent 沙箱能力 | 匹配度 |
|-----------|--------------|--------|
| 运行 Playwright/Patchright 爬取 AI 平台 | 内置 Playwright MCP（端口 8931） | ★★★★★ |
| Docker 隔离（多租户安全） | 基于 Docker 的 Runtime 隔离 | ★★★★★ |
| 代码执行沙箱 | LLM Sandbox（端口 8000） | ★★★★☆ |
| 持久化浏览器会话（Cookie 保活） | 需自行配置 volume mount | ★★★☆☆ |
| 并发多浏览器实例 | 需多实例或自行管理 | ★★★☆☆ |

### 13.3 未来使用场景规划

| 阶段 | 方案 | 说明 |
|------|------|------|
| **Phase 1**（现在） | 本地/单机 VPS + Patchright | 零额外成本，够用 |
| **Phase 2**（用户增长） | **腾讯云 Agent 沙箱** × N 实例 | 每个实例跑 Playwright，按需扩缩；轻量服务器套餐性价比高 |
| **Phase 3**（K8s） | 自建 Chromium Pod 池 或 Browserless | 完全自主控制，最大灵活性 |

### 13.4 Phase 2 迁移路径（概念设计）

```
当前架构:
  Backend (ECS) → PlaywrightBrowserClient → 本地 Chromium

Phase 2 架构:
  Backend (ECS) → BrowserPoolManager → 腾讯云 Agent 沙箱 ×N
                                        ├── 实例 1: Playwright MCP (Kimi 专用)
                                        ├── 实例 2: Playwright MCP (DeepSeek 专用)
                                        └── 实例 3: Playwright MCP (元宝 专用)

代码改动:
  PlaywrightBrowserClient.open() 方法:
    现在: self.playwright.chromium.launch_persistent_context(...)
    未来: self.playwright.chromium.connect_over_cdp(sandbox_ws_url)
    改动量: ~10 行（一个函数内的连接方式切换）
```

### 13.5 建议

- **现阶段不急于使用**腾讯云 Agent 工具箱/沙箱，Phase 1 本地 Patchright 完全够用
- **Phase 2 优先考虑 Agent 沙箱**（而非工具箱），因为我们只需要浏览器能力，不需要 Qdrant/Langfuse/LangGraph（我们已有自己的架构）
- Agent 沙箱的 **Playwright MCP + Docker 隔离** 天然适合我们的多平台爬取场景
- 轻量应用服务器**套餐计费**比按量计费更可预测，适合固定频率的采集任务
- 需关注：腾讯云 Playwright MCP 是否支持 **persistent context**（Cookie 保活），这对免登录至关重要

---

*本文件为 Specta AI Phase 1 实施的核心执行文档，所有开发工作应对照本文件执行。*
*上游依赖：`docs/strategic-blueprint-aeo-2026.md`（战略蓝图）*

# AICE 9C LLM 官网 AI 友好度改造设计

> 状态：Draft
> 日期：2026-05-08
> 适用范围：`site_confidence_assessment_skill` / 官网 AI 友好度报告

## 1. 背景

当前“官网 AI 友好度”报告已经接入到 Chat 和 Canvas，并能自动发现官网页面、抽取页面特征、生成报告 Artifact。

但当前实现有一个核心偏差：

- 原始设计中，AICE 是一个 9C 评分的 LLM 审核能力。
- 当前实现中，官网 AI 友好度主要由后端规则扫描和模板报告生成。
- 目前 C9a / C9b 只被部分规则模拟，完整 9C 分数、扣分理由、风险判断和建议并没有由 AICE LLM 审核产出。

这会带来三个问题：

1. 分数口径不符合 AICE 设计。
2. 建议更像规则模板，而不是基于页面内容的审核结论。
3. 用户看到“AI 友好度”报告时，会误以为它已经按 AICE Agent 完整审核。

本设计目标是把现有官网 AI 友好度能力改回 AICE 9C LLM 审核链路，同时保留现有 Skill、Executor、Artifact 和前端入口。

## 2. 关键设计依据

### 2.1 Skill 不是 Prompt，也不是单个节点

当前 Specta 后端的能力边界是：

```text
A0 Orchestrator
  + LangGraph Workflow
  + Executor Nodes
  + Skill Registry / Skill Contract
  + Tool / Adapter
  + Artifact / Memory
```

因此本次不新增一个平行 public Skill，也不把 AICE 规则塞进 orchestrator 大 prompt。

### 2.2 模型选择使用现有模型分层

当前后端已经有三类模型 profile：

```text
TEXT_REASONING_LLM_PROVIDER / TEXT_REASONING_MODEL_NAME
TEXT_LIGHT_LLM_PROVIDER / TEXT_LIGHT_MODEL_NAME
MULTIMODAL_LLM_PROVIDER / MULTIMODAL_MODEL_NAME
```

AICE 官网审核属于短文本、结构化 JSON、规则约束明显的审核任务，默认应该使用：

```python
get_text_light_llm_model(task_name="aice_web_evaluation")
```

这会走现有 `TEXT_LIGHT` profile，当前默认是 DeepSeek v4 Flash。不要新增 `AICE_MODEL_NAME`、`AICE_LLM_PROVIDER` 这类旁路配置。

### 2.3 原始 AICE 评分要求

AICE-Web 使用 9C 固定矩阵：

```text
C6 + C9a + C9b + C8 + C1 + C4 + C2 + C3 + C5 + C7 = 总分
```

核心硬规则：

- 页面不可读或正文无法抽取时，`C6 = 0`。
- 缺失 H1 或关键结构标签时，`C9a` 至少扣 5 分。
- 未发现 Schema.org 标记时，`C9b` 至少扣 5 分。
- 每个维度都必须有分数、原因、证据和 confidence。
- 总分必须等于各维度分数求和。

## 3. 本次决策

### 3.1 保留现有 public Skill

继续保留：

```text
site_confidence_assessment_skill = 官网 AI 友好度
```

原因：

- 用户入口是正确的。
- Dashboard / Chat / Canvas 已经围绕这个 Skill 工作。
- 问题在 executor 内部评估方式，不在 public Skill 命名或入口。

### 3.2 改造现有 executor

继续使用：

```text
site_confidence_assessment_executor
```

但内部链路改为：

```text
官网页面发现
-> 页面事实抽取
-> 后端规则预判与 payload 聚合
-> AICE 9C LLM 单次整站审核
-> 后端硬规则校验与页面结果回填
-> 报告 Artifact 写回
```

### 3.3 新增内部 AICE 评估服务

新增内部服务，不作为 public Skill 暴露：

```text
app/services/aice_evaluation_service.py
```

职责：

- 构建 AICE-Web LLM 请求。
- 调用 `get_text_light_llm_model(...)`。
- 要求严格 JSON 输出。
- 在一次请求中解析整站结果和 pages[].aice_evaluation。
- 对非法输出重试。
- 失败时返回可解释的降级结果。

### 3.4 新增 Prompt Contract

新增：

```text
app/services/aice_prompt_contract.py
```

职责：

- 定义 `AICE_WEB_PROMPT_VERSION`。
- 定义 AICE 9C 评分矩阵。
- 定义 JSON 输出 schema。
- 构建 cache-friendly system prompt。
- 构建动态 site_with_pages payload。

## 4. 目标与非目标

### 4.1 目标

1. 官网 AI 友好度报告回到 AICE 9C 评分口径。
2. 9C 分数、扣分原因、风险判断、优化建议由 LLM 审核生成。
3. 后端保留硬规则校验，避免 LLM 自由发挥。
4. 继续使用现有 Skill / Executor / Artifact 框架。
5. 使用现有 `TEXT_LIGHT` 模型 profile，默认 DeepSeek v4 Flash。
6. Prompt 分层明确，固定 system prompt 可 hash、可观测、可缓存。
7. 前端尽量不改，保持现有报告渲染和版本历史。

### 4.2 非目标

1. 不新增 public `content_evaluation_skill`。
2. 不新增 `AICE_MODEL_NAME` 或独立模型配置。
3. 不重做 Canvas 报告组件。
4. 不把任意 URL / 文本 / citation 的完整 AICE 能力一次性展开。
5. 不让 LLM 直接抓网页或代替页面事实抽取。
6. 不让 LLM 输出未经校验的最终分数。

## 5. 目标架构

```text
site_confidence_assessment_skill
  -> site_confidence_assessment_executor
    -> discover_site_pages
    -> fetch_page_features
    -> backend_rule_precheck
    -> AICEEvaluationService.evaluate_site
      -> get_text_light_llm_model(task_name="aice_web_evaluation")
      -> stable AICE system prompt
      -> one dynamic site_with_pages JSON payload
      -> JSON site evaluation + pages[].aice_evaluation
      -> AICE validator
    -> save_and_send_artifact
    -> validate_artifact_writeback
```

## 6. Prompt 分层设计

### 6.1 固定 System Prompt

System prompt 必须稳定，适合 provider prompt cache 和本地 hash 观测。

固定内容包括：

- AICE Agent 角色。
- AICE-Web 9C 评分矩阵。
- 每个维度的满分和评分边界。
- C6 / C9a / C9b 硬扣规则。
- JSON 输出格式。
- 不允许新增维度。
- 不允许跳过评分原因。
- 不允许输出 Markdown。
- 不允许输出用户不可见的内部实现名。

示意：

```text
你是 Specta AI 的 AICE-Web 内容审核 Agent。
你必须基于输入的页面事实，对页面执行 AICE 9C 审核。
你只能输出严格 JSON。
你不得新增、删除或重命名 9C 维度。
```

### 6.2 动态 User Payload

动态 payload 只放本次页面事实和任务上下文。

建议结构：

```json
{
  "task": "aice_web_page_evaluation",
  "prompt_version": "aice_web_v1",
  "brand": {
    "name": "纽崔莱",
    "root_domain": "amway.com.cn"
  },
  "page": {
    "url": "https://www.amway.com.cn/...",
    "page_type": "product",
    "title": "...",
    "h1": ["..."],
    "h2": ["..."],
    "has_main": true,
    "has_article": false,
    "schema_types": ["Product"],
    "published_at": null,
    "body_text_length": 1420,
    "body_text_excerpt": "...",
    "external_links_count": 3,
    "crawl_readable": true,
    "fetch_failure_reason": ""
  },
  "output_language": "zh-CN"
}
```

### 6.3 单次整站 Prompt

页面事实抽取完成后，后端先做规则预判，然后把所有页面事实整合成一个 `site_with_pages` JSON：

- 每个页面包含 URL、页面类型、标题、H1/H2、正文摘录、Schema、发布时间、抓取状态。
- 每个页面包含 `backend_rule_precheck`，明确 C6 / C9a / C9b 的硬规则边界。
- LLM 在一次请求里同时输出整站评分、整站报告和每个页面的 `aice_evaluation`。
- 后端不对页面逐个发 LLM 请求，避免多页面并发触发 DeepSeek 限流。
- 官网级报告不再依赖第二次 LLM 总结，结论和 P0/P1 建议在同一次推理中完成。

## 7. AICE JSON 输出契约

单次整站输出建议：

```json
{
  "evaluation_mode": "AICE-Web",
  "prompt_version": "aice_web_v1",
  "overall_score": 78,
  "score_band": "medium_high",
  "formula": {
    "items": [
      {"code": "C6", "score": 20, "max_score": 25},
      {"code": "C9a", "score": 5, "max_score": 10},
      {"code": "C9b", "score": 5, "max_score": 10}
    ],
    "expression": "20 + 5 + 5 + ... = 78"
  },
  "dimension_scores": [
    {
      "code": "C9b",
      "label": "Schema Usage",
      "score": 5,
      "max_score": 10,
      "confidence": 0.92,
      "finding": "页面只发现基础结构，缺少可明确表达产品身份的 Schema。",
      "evidence": ["schema_types 为空或缺少 Product"],
      "recommendation": {
        "issue": "结构化数据不足",
        "action": "补充 Product 或 Organization JSON-LD",
        "example": "在页面 head 中加入符合页面类型的 JSON-LD",
        "reason": "帮助 AI 和搜索系统识别页面主体身份"
      }
    }
  ],
  "trusted_reasons": [],
  "caution_reasons": [],
  "recommendations": [],
  "overall_confidence": 0.86,
  "pages": [
    {
      "url": "https://example.com/product",
      "aice_evaluation": {
        "evaluation_mode": "AICE-Web",
        "overall_score": 72,
        "dimension_scores": []
      }
    }
  ]
}
```

要求：

- 10 个维度必须完整。
- `overall_score` 必须等于 10 个维度分数之和。
- 每个低分维度必须能追溯到 evidence。
- recommendation 必须绑定维度，不允许只写泛泛建议。
- 顶层 `pages` 必须覆盖输入页面，每个页面都必须有 `aice_evaluation`。

## 8. 后端校验规则

AICE validator 必须在写入报告前执行。

### 8.1 结构校验

- 输出必须是 JSON object。
- 必须包含 `evaluation_mode`、`overall_score`、`formula`、`dimension_scores`。
- `dimension_scores` 必须包含全部 10 个 code。
- 不允许出现未知维度 code。

### 8.2 算式校验

- `sum(dimension_scores.score) == overall_score`。
- 每个维度分数不能超过该维度满分。
- 每个维度分数不能小于 0。

### 8.3 硬扣规则

- `crawl_readable = false` 时，`C6 = 0`。
- 缺 H1 或缺 `main/article` 时，`C9a <= 5`。
- 无 Schema 时，`C9b <= 5`。

如果 LLM 输出违反硬规则，后端有两种处理：

1. 第一次违规：带违规原因重试一次。
2. 仍违规：后端修正硬规则分数，并在 metadata 中记录 `validator_repaired = true`。

### 8.4 建议校验

- 低分维度必须至少有一个对应建议。
- 建议必须包含 `issue`、`action`、`reason`。
- 不允许只输出“优化内容”“提升结构”等空泛建议。

## 9. 缓存与成本控制

### 9.1 Prompt cache-friendly 设计

第一优先级是让请求形态稳定：

- System prompt 固定。
- System prompt 有 `AICE_WEB_PROMPT_VERSION`。
- User payload 是 JSON。
- 页面事实字段顺序稳定。
- 不把大段动态上下文混进 system prompt。

同时记录：

- `prompt_version`
- `static_prompt_hash`
- `model_profile = TEXT_LIGHT`
- `model_name`

### 9.2 结果缓存边界

第一版不做页面级 LLM 结果缓存，因为页面级结果不再单独请求。

不要缓存整站 LLM 报告，因为：

- 用户可能立刻重新抓取。
- 页面列表可能变化。
- 报告版本需要体现本次运行时间。

可以继续复用 `page_feature_service` 的页面特征缓存，减少重复抓取；LLM 审核保持每次 Artifact 一次请求。

## 10. 报告结构

继续保持现有官网 AI 友好度报告在 Canvas 中展示。

报告内容调整为：

1. 结论
   - 官网 AICE 平均分
   - 评分模式：AICE-Web
   - 最近更新
2. 为什么会得到这个判断
   - 9C 维度短板
   - 重复扣分项
   - 页面覆盖说明
3. 直接证据
   - 低分页
   - 每页分数
   - 低分维度
   - LLM 给出的证据和建议
4. P0 / P1 建议
   - 按影响面和可执行性排序
   - 绑定页面和维度
5. 附录
   - 本轮页面列表
   - 每页 AICE 分数
   - 重要 validator metadata

## 11. 数据结构影响

### 11.1 保持现有 Artifact 类型

继续使用：

```text
report_kind = site_confidence_report
artifact_kind = site_confidence_report
```

这样前端不需要重新识别新类型。

### 11.2 扩展 report data

建议新增字段：

```json
{
  "evaluation_mode": "AICE-Web",
  "aice_prompt_version": "aice_web_v1",
  "aice_model_profile": "TEXT_LIGHT",
  "aice_model_name": "deepseek-v4-flash",
  "aice_static_prompt_hash": "...",
  "page_evaluations": [],
  "dimension_summary": [],
  "validator_summary": {
    "repaired_count": 0,
    "retry_count": 0,
    "fallback_count": 0
  }
}
```

前端现有 Markdown 渲染可以继续使用，结构化字段先用于后续调试和可观测。

## 12. 实施计划

### Phase 1：文档和契约

1. 固定本文档。
2. 新增 AICE prompt contract。
3. 新增 JSON schema / validator 测试样例。

### Phase 2：单次 AICE 服务

1. 新增 `AICEEvaluationService`。
2. 接入 `get_text_light_llm_model(task_name="aice_web_evaluation")`。
3. 完成 `site_with_pages` 单次 LLM JSON 调用。
4. 完成 JSON parse、retry、fallback。
5. 完成 C6 / C9a / C9b 页面级 validator。

### Phase 3：接入官网评估 executor

1. 在 `site_confidence_assessment.py` 中保留页面发现和事实抽取。
2. 先生成页面规则预判，再统一交给一次 AICE LLM。
3. 用 LLM 返回的 `pages[].aice_evaluation` 回填页面兼容字段。
4. 保持 artifact key 和 report_kind 不变。
5. 保持 Chat 回复和 Canvas 打开行为不变。

### Phase 4：验收和回归

1. 后端单元测试覆盖 validator。
2. 使用 mock LLM 测试非法 JSON、硬扣违规、缺维度。
3. 用真实官网跑一次本地 AICE 评估。
4. 检查报告时间、样式、版本、导航聚合不回退。
5. 跑 `python scripts/validate_change.py`。

## 13. 测试计划

### 13.1 单元测试

需要覆盖：

- 完整 9C 输出通过。
- 缺一个维度失败。
- 总分不等于求和失败。
- 无 Schema 但 C9b > 5 时触发修正或重试。
- 缺 H1 但 C9a > 5 时触发修正或重试。
- 页面不可读但 C6 > 0 时触发修正或重试。
- LLM 输出 Markdown 包裹 JSON 时仍能解析。
- LLM 输出无法解析时走 fallback。
- `site_with_pages` 只调用一次 LLM，并且 payload 含 `backend_rule_precheck`。

### 13.2 集成测试

需要覆盖：

- `site_confidence_assessment_executor` 能完成 artifact 写回。
- `skill_result_recorded` 仍然发生。
- `site_confidence_report_persisted` gate 仍然通过。
- 报告内容包含 AICE-Web、9C 总分和维度摘要。

### 13.3 人工验收

需要检查：

- 报告建议是否来自页面内容，而不是模板套话。
- 低分维度是否能回到页面证据。
- C9a / C9b 的扣分是否符合原始规则。
- 页面刷新后 Artifact 仍按同类聚合为版本。
- 不出现内部英文错误文案。

## 14. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| LLM 输出不稳定 | 分数和报告不可控 | JSON schema、validator、重试、fallback |
| 成本上升 | 多页面评估变慢或变贵 | 单次整站请求、限制页面数、TEXT_LIGHT |
| Prompt 过长 | 缓慢或截断 | 固定 system prompt，动态 payload 控制长度 |
| 前端不兼容 | Canvas 展示异常 | 保持 report_kind 和 markdown 字段 |
| 分数与旧报告差异大 | 用户困惑 | 报告明确标注 AICE-Web 和最近更新 |
| LLM 违反硬扣规则 | 分数失真 | 后端强校验和修正 metadata |

## 15. 开放问题

1. 单次整站 prompt 的页面摘录长度是否需要按品牌规模动态压缩？
2. 页面过多时是否要先做确定性抽样，而不是直接使用最大 50 页？
3. 报告里是否暴露全部 9C 明细，还是只展示低分维度和附录？
4. 如果页面抓取失败占比很高，是否直接中止 AICE 审核，还是输出低置信度报告？

## 16. 建议的第一版实现取舍

第一版建议：

1. 后端先做事实抽取和规则预判。
2. AICE LLM 只调用一次，同时产出页面级评分和官网级报告。
3. 不做页面级 LLM 并发，也不做页面级 LLM 结果缓存。
4. 报告正文展示总分、短板维度、低分页和 P0 / P1 建议。
5. 结构化 9C 明细写入 artifact data，但前端先不新增复杂图表。

这样可以先修正最关键的评分口径，同时控制改动范围。

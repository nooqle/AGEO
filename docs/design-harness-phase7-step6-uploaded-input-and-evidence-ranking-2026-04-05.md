# AGEO Claude Code 参考改造 Phase 7：Step 6 Uploaded Input Evidence And Evidence Ranking（2026-04-05）

> 状态：Completed
> 适用分支：`codex/validation-retro-harness`
> 依赖前提：Phase 7 Step 1 / 2 / 3 / 5 与 Phase 7.5 最小防守已接入

---

## 1. 目标

Step 6 解决两个实际缺口：

1. orchestrator 还看不到上传输入的结构化证据
2. current session evidence 已接入，但仍缺轻量 relevance / ranking

本步还顺带处理一个明确问题：

3. orchestrator 的 model-visible context 和 thinking guard 里仍有英文标签，必须全部收回中文

---

## 2. 实现范围

### 2.1 Uploaded Input Evidence

优先覆盖以下来源：

1. `pending_table_intake`
   - 表示“有待理解附件”
2. `table_intake_result`
   - 表示“上传表格已被理解”
3. `import_source_metadata`
   - 表示“问题列表 / 链接清单已导入”
4. `simulated_questions.generation_mode == uploaded_list`
   - 表示“上传问题列表已形成 A3 交付物”

统一 provenance：

- `source = uploaded_input`
- `instruction_authority = false`

`source_type` 先收成：

1. `pending_upload`
2. `table_intake_summary`
3. `uploaded_question_list`
4. `uploaded_link_list`

### 2.2 Evidence Ranking

只做轻量排序，不做复杂召回：

1. 当前会话 evidence 默认高于历史 evidence
2. 若用户问题明显指向某类证据，按 query-aware 规则加权：
   - 平台 / 回答 -> `fetch_answer`
   - 引用 / 来源 / 证据 -> `fetch_citation` / `confidence_summary`
   - 报告 / 结论 / 风险 -> `report_summary`
   - 上传 / 表格 / 导入 / 问题列表 / 链接清单 -> `uploaded_input`
3. 每条 evidence 记录：
   - `relevance_score`
   - `relevance_reason`

### 2.3 中文化与思考防守

本步固定要求：

1. 所有 model-visible section title 改为中文
2. `RecentEvidencePacket / ActiveSkillPacket / PendingDecisionPacket` render 改为中文标签
3. `SkillContract` 的 summary section 改为中文键名
4. orchestrator 增加语言规则：
   - 所有回复、计划、思考、tool-call 前说明一律使用中文
5. 对 streamed thinking 增加最小 guard：
   - 若 block 明显是英文思考片段，则不要原样透出英文，改成中文占位说明

---

## 3. 非目标

1. 不做完整 semantic reranker
2. 不做上传原文全文回灌
3. 不做浏览器 / AIO evidence packet
4. 不做多语言翻译器

---

## 4. QA Gate

至少覆盖：

1. uploaded input evidence contract test
2. current session evidence ranking test
3. 中文 section title / 中文 render test
4. 英文 thinking guard test
5. `pytest aeo-platform/backend/tests/test_harness_refactor_foundations.py -q`
6. 相关文件 `python -m py_compile`
7. 问号污染扫描

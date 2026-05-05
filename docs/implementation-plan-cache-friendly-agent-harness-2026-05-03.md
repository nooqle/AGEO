# AGEO 提示词复用友好型 Harness 开发规划（2026-05-03）

> 状态：Draft
> 关联设计文档：`docs/design-cache-friendly-agent-harness-2026-05-03.md`
> 目标：把 5 项设计拆成可开发、可验收、可灰度的阶段计划。
> 基本原则：先观测，再改行为；先 orchestrator，再扩展到其他执行器；每个 Phase 都必须能单独回滚。

---

## 1. 总目标

这次改造不是为了让模型“更聪明”，而是让系统运行更稳：

1. 长任务成本更可控
2. 多轮任务响应更稳定
3. 工具和模型变化更可解释
4. 复用率下降时能定位原因
5. 后续客户、品牌、技能变多时，不让 orchestrator 越跑越乱

最终希望看到的变化：

1. 固定系统提示词在同一版本内保持稳定
2. 工具清单默认稳定，不再频繁按状态变化
3. 技能动态策略不再污染工具说明
4. 同一任务默认不悄悄切换 orchestrator 模型
5. 控制面可以解释“为什么这次贵、慢、复用率低”

---

## 2. 不做什么

为避免范围失控，本轮规划明确不做：

1. 不重写整套 workflow graph
2. 不改 A1/A3/A4/A5/A7 的业务逻辑
3. 不一次性删除现有 `_get_contextual_hidden_tool_names`
4. 不把所有动态上下文都藏起来
5. 不做复杂自动调参系统
6. 不把控制面做成完整 APM 平台

---

## 3. 总体 Phase 划分

```text
Phase 0：基线确认
Phase 1：先加观测，不改行为
Phase 2：拆分固定提示词与本轮提醒
Phase 3：稳定工具清单，加工具可用性 gate
Phase 4：稳定技能工具说明，把动态策略移到技能上下文
Phase 5：同一任务锁定 orchestrator 模型
Phase 6：控制面展示与轻量告警
Phase 7：灰度、回归、上线关闭
```

推荐顺序不能颠倒。
尤其不能先大改工具清单，再补观测。否则问题出现时无法判断原因。

---

## 4. Phase 0：基线确认

### 4.1 目标

在正式改代码前，先确认当前系统的行为和风险点。

这一步不改变产品行为。

### 4.2 开发内容

1. 梳理 orchestrator 当前调用链：
   - `build_orchestrator_system_prompt`
   - `build_orchestrator_messages`
   - `build_agent_tools`
   - `record_llm_usage_async`
2. 梳理现有测试覆盖：
   - `tests/test_harness_refactor_foundations.py`
   - `tests/test_llm_task_routing.py`
   - `tests/test_routing_matrix.py`
3. 确认控制面成本页现状：
   - `frontend/src/app/control-plane/costs/page.tsx`
4. 选出 3 个后续固定回归场景：
   - 新品牌完整分析
   - A4 失败后补采
   - 用户追问历史结果

### 4.3 产出物

1. 一份改造前基线记录
2. 现有测试清单
3. 3 个固定回归场景的输入和预期行为

### 4.4 验收标准

1. 明确当前 system prompt 会随哪些 state 变化
2. 明确当前工具清单会随哪些 state 变化
3. 明确 usage 记录当前已有和缺失字段
4. 不产生任何功能代码改动

### 4.5 推荐验证

```powershell
python scripts\validate_change.py
pytest aeo-platform\backend\tests\test_harness_refactor_foundations.py -q
pytest aeo-platform\backend\tests\test_llm_task_routing.py -q
```

---

## 5. Phase 1：先加观测，不改行为

### 5.1 目标

先让系统能回答一个问题：

> 这次复用率低，到底是固定提示词变了、工具清单变了、模型变了，还是本轮动态信息太长？

这一期只加记录，不改变模型看到的内容。

### 5.2 开发内容

#### 后端

1. 新增指纹计算工具，例如：
   - `app/workflow/prompt_fingerprint.py`
2. 计算并记录：
   - `static_prompt_hash`
   - `tool_surface_hash`
   - `message_count`
   - `tool_count`
   - `runtime_context_size`
   - `model_identity`
3. 将这些字段写入 `LLMUsageRecord.extra_metadata`
4. 在 `LLMUsageService.get_observability_snapshot()` 中透出摘要

#### 前端

这一期前端可以不改。
如果要做最小展示，只在控制面成本页展示最近调用的复用率和模型。

### 5.3 涉及文件

1. `aeo-platform/backend/app/workflow/orchestrator_node.py`
2. `aeo-platform/backend/app/services/llm_usage_service.py`
3. `aeo-platform/backend/app/models/llm_usage.py`
4. `aeo-platform/backend/tests/test_harness_refactor_foundations.py`

### 5.4 Milestone

**M1：每次 orchestrator LLM 调用都有可解释 metadata。**

### 5.5 验收标准

1. usage metadata 中能看到固定提示词指纹
2. usage metadata 中能看到工具清单指纹
3. usage metadata 中能看到模型身份
4. 不改变当前 prompt 内容和工具列表
5. 现有 orchestrator 路由测试不退化

### 5.6 测试计划

单元测试：

1. 相同 system prompt 生成相同 hash
2. 工具顺序稳定时生成相同 hash
3. 工具参数变化时 hash 会变化
4. metadata 能被正确写入 usage record

回归测试：

```powershell
pytest aeo-platform\backend\tests\test_harness_refactor_foundations.py -q
pytest aeo-platform\backend\tests\test_llm_task_routing.py -q
python scripts\validate_change.py
```

### 5.7 回滚方式

只停止写入新增 metadata。
不影响业务流程。

---

## 6. Phase 2：拆分固定提示词与本轮提醒

### 6.1 目标

让 system message 尽量稳定。

人话解释：

> 公司章程放前面，不每轮改；今天的新情况放后面。

### 6.2 开发内容

1. 新增提示词包对象：

```python
class OrchestratorPromptBundle:
    static_system_prompt: str
    runtime_reminder_message: str
```

2. 将 `PromptAssembly` 渲染拆成两类：
   - 固定规则
   - 本轮提醒
3. `base_policy_sections` 进入固定系统提示词
4. `runtime_context_sections` 和 `runtime_reminder_sections` 进入本轮提醒
5. `build_orchestrator_messages()` 追加本轮提醒 message
6. 保留 feature flag：
   - `ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED`

### 6.3 涉及文件

1. `aeo-platform/backend/app/workflow/prompt_assembly.py`
2. `aeo-platform/backend/app/workflow/orchestrator_node.py`
3. `aeo-platform/backend/app/workflow/orchestrator_context_packets.py`
4. `aeo-platform/backend/tests/test_harness_refactor_foundations.py`

### 6.4 Milestone

**M2：动态运行信息不再污染固定 system prompt。**

### 6.5 验收标准

1. 同一部署版本内，固定系统提示词 hash 在状态变化后不变
2. 当前品牌、当前报告、最近证据变化时，只影响本轮提醒
3. 本轮提醒能正确出现在模型消息中
4. A4 失败补采、表格导入确认、历史追问等关键场景不退化
5. feature flag 关闭后可回到旧行为

### 6.6 测试计划

单元测试：

1. 不同 state 下 `static_system_prompt` 一致
2. 不同 state 下 `runtime_reminder_message` 正确变化
3. 本轮提醒中包含 pending decision
4. 本轮提醒中包含 recent evidence
5. 本轮提醒不泄露内部提示词

集成回归：

```powershell
pytest aeo-platform\backend\tests\test_harness_refactor_foundations.py -q
pytest aeo-platform\backend\tests\test_routing_matrix.py -q
python scripts\validate_change.py
```

### 6.7 运行时验收

至少跑 3 个真实场景：

1. 新品牌完整分析能继续从 A1 推进
2. A4 失败后仍能要求用户选择补采或继续分析
3. 用户问上一轮失败统计时仍会走知识刷新，而不是复述旧数字

### 6.8 回滚方式

关闭 `ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED`。
回到旧的 system prompt 组装方式。

---

## 7. Phase 3：稳定工具清单，加工具可用性 gate

### 7.1 目标

减少工具清单按状态变化。

人话解释：

> 工具箱固定摆在那里；现在能不能用某个工具，由门禁判断。

### 7.2 开发内容

1. 将 `_get_contextual_hidden_tool_names()` 的职责拆成两层：
   - 工具隐藏：保留旧逻辑，作为兼容路径
   - 工具限制：新增新逻辑，作为目标路径
2. 新增工具限制结构：

```python
class ToolConstraint:
    tool_name: str
    blocked: bool
    reason: str
    suggested_next_actions: list[str]
```

3. 新增工具执行前 gate：

```python
validate_tool_available_in_current_state(tool_name, state)
```

4. 模型误调用受限工具时，返回结构化结果：

```python
CapabilityBlockedResult
```

5. 加 feature flag：
   - `ORCHESTRATOR_STABLE_TOOL_SURFACE_ENABLED`

### 7.3 涉及文件

1. `aeo-platform/backend/app/workflow/orchestrator_node.py`
2. `aeo-platform/backend/app/services/tool_capability_matrix.py`
3. `aeo-platform/backend/tests/test_harness_refactor_foundations.py`
4. `aeo-platform/backend/tests/test_routing_matrix.py`

### 7.4 Milestone

**M3：同一 session 内工具清单默认稳定，误调用由 gate 拦截。**

### 7.5 验收标准

1. 开启 flag 后，常规状态变化不再改变工具清单 hash
2. headless 模式下模型误调 `ask_user` 会被 gate 拦截
3. 当前结果追问场景下模型误调历史工具会被清晰拦截或引导
4. 用户看到的是可执行解释，不是内部错误
5. 关闭 flag 后可回到旧隐藏工具逻辑

### 7.6 测试计划

单元测试：

1. headless 禁用 `ask_user`
2. A4 补采决策阶段限制错误工具
3. 当前会话追问优先本次结果，不误走历史工具
4. blocked result 包含 reason 和 suggested_next_actions

集成回归：

```powershell
pytest aeo-platform\backend\tests\test_harness_refactor_foundations.py -q
pytest aeo-platform\backend\tests\test_routing_matrix.py -q
python scripts\validate_change.py
```

### 7.7 回滚方式

关闭 `ORCHESTRATOR_STABLE_TOOL_SURFACE_ENABLED`。
继续使用旧的工具隐藏策略。

---

## 8. Phase 4：稳定技能工具说明，把动态策略移到技能上下文

### 8.1 目标

让 skill 作为工具入口时保持稳定，不因 profile、prompt overlay、package hint 变化而改变工具说明。

人话解释：

> 门牌不要天天换；今天店里主推什么，写在公告栏。

### 8.2 开发内容

1. `build_skill_tool_definition()` 只输出稳定能力说明
2. 将以下动态内容移入 `ActiveSkillPacket` 或本轮提醒：
   - `prompt_overlay`
   - package hint
   - profile 列表
   - 当前策略补充
3. 增加 skill schema 指纹测试
4. 加 feature flag：
   - `STABLE_SKILL_TOOL_DESCRIPTION_ENABLED`

### 8.3 涉及文件

1. `aeo-platform/backend/app/services/skill_registry_service.py`
2. `aeo-platform/backend/app/workflow/orchestrator_context_packets.py`
3. `aeo-platform/backend/app/workflow/orchestrator_node.py`
4. `aeo-platform/backend/tests/test_harness_refactor_foundations.py`

### 8.4 Milestone

**M4：自定义 skill 或 profile 变化不再导致工具 schema 频繁变化。**

### 8.5 验收标准

1. 修改 `prompt_overlay` 后，工具 schema hash 不变
2. 模型仍能通过本轮提醒看到当前策略
3. profile 列表仍能被模型看到，但不进入工具 description
4. skill 调用参数不变
5. 控制面 skill 配置功能不退化

### 8.6 测试计划

单元测试：

1. 同一 skill 修改 overlay 前后，工具 schema hash 不变
2. `ActiveSkillPacket` 能 render overlay/profile/package 信息
3. skill tool definition 保持原参数结构

回归测试：

```powershell
pytest aeo-platform\backend\tests\test_harness_refactor_foundations.py -q
python scripts\validate_change.py
```

### 8.7 回滚方式

关闭 `STABLE_SKILL_TOOL_DESCRIPTION_ENABLED`。
恢复旧的工具 description 拼接方式。

---

## 9. Phase 5：模型使用与切换观测

### 9.1 目标

2026-05-04 修订：不实施“同一任务强制锁定模型”。

原因：

1. 当前主线已经有 A1 / A4 / skill 等分层模型路由设计
2. 部分节点需要更快或更适合结构化输出的模型
3. 强制锁定可能破坏已有性能和能力分工

本阶段目标改为：

> 不阻止系统按设计选择模型，但要记录每次用了哪个模型、为什么贵、是否出现异常切换。

人话解释：

> 不强行规定谁来主持，但每次谁在主持、花了多少钱、是否换过人，都要看得见。

### 9.2 开发内容

1. 在 usage metadata 或观测摘要中记录：
   - `orchestrator_provider`
   - `orchestrator_model`
   - `model_identity`
   - `model_fallback_reason`（如果发生）
2. 不改 `get_orchestrator_llm_model()` 的选择策略
3. fallback 发生时写入 usage metadata
4. 控制面展示模型维度成本、缓存命中和延迟
5. 控制面后续可展示模型切换次数

### 9.3 涉及文件

1. `aeo-platform/backend/app/core/llm/task_routing.py`
2. `aeo-platform/backend/app/workflow/orchestrator_node.py`
3. `aeo-platform/backend/app/services/llm_usage_service.py`
5. `aeo-platform/backend/tests/test_llm_task_routing.py`

### 9.4 数据库迁移

不新增字段。

先使用 `LLMUsageRecord.extra_metadata` 和现有 Control-plane 聚合。

### 9.5 Milestone

**M5：模型使用可追踪、可解释，不破坏既有分层路由。**

### 9.6 验收标准

1. 每次调用能看到 provider / model / model_identity
2. fallback 发生时有原因记录
3. 不影响 A1、A4、fast structured 等任务级模型路由
4. 控制面能按模型拆分成本、延迟和缓存命中

### 9.7 测试计划

单元测试：

1. 无 locked model 时走默认配置
2. 有 locked model 时优先使用 locked model
3. locked model 初始化失败时 fallback 并记录原因
4. 其他 task-level model 路由不受影响

回归测试：

```powershell
pytest aeo-platform\backend\tests\test_llm_task_routing.py -q
pytest aeo-platform\backend\tests\test_harness_refactor_foundations.py -q
python scripts\validate_change.py
```

### 9.8 回滚方式

关闭 `ORCHESTRATOR_MODEL_LOCK_ENABLED`。
如果已加数据库字段，字段保留但不参与运行逻辑。

---

## 10. Phase 6：控制面展示与轻量告警

### 10.1 目标

让成本、速度、复用率变成可读指标。

人话解释：

> 不是只知道贵了，而是知道为什么贵。

### 10.2 开发内容

#### 后端

1. 扩展 `LLMUsageService.get_observability_snapshot()`
2. 返回：
   - 总复用率
   - 按模型复用率
   - 按步骤复用率
   - 最近低复用调用
   - prompt/tool hash 变化次数
3. 增加轻量告警判定：
   - 同 session 工具指纹变化过多
   - 固定提示词指纹变化异常
   - orchestrator 复用率持续偏低

#### 前端

1. 在控制面成本页增加“提示词复用”模块
2. 展示 3 个核心指标：
   - 复用率
   - 缓存节省成本
   - 最近异常原因
3. 遵守 Specta 全局视觉系统，使用 Evidence Teal，不引入紫蓝渐变

### 10.3 涉及文件

1. `aeo-platform/backend/app/services/llm_usage_service.py`
2. `aeo-platform/backend/app/api/v1/control_plane.py`
3. `frontend/src/app/control-plane/costs/page.tsx`
4. `frontend/src/components/control-plane/*`

### 10.4 Milestone

**M6：控制面能解释提示词复用率和异常原因。**

### 10.5 验收标准

1. 控制面能看到总复用率
2. 控制面能看到按模型/步骤拆分
3. 控制面能看到最近异常原因
4. UI 符合 Specta 视觉系统
5. 不泄露 system prompt 内容，只展示 hash 和指标

### 10.6 测试计划

后端：

```powershell
pytest aeo-platform\backend\tests\test_harness_refactor_foundations.py -q
python scripts\validate_change.py
```

前端：

```powershell
cd frontend
npm run lint
npm run build
```

视觉验证：

1. 扫描禁用色彩和效果词
2. 本地浏览器截图验证控制面成本页
3. 移动端宽度检查文本不溢出

### 10.7 回滚方式

后端继续保留 metadata。
前端隐藏提示词复用模块即可。

---

## 11. Phase 7：灰度、回归、上线关闭

### 11.1 目标

将改造从开发可用推进到生产可信。

### 11.2 灰度策略

建议按 feature flag 分阶段开启：

1. 先只开启 Phase 1 观测
2. 再只对内部账号开启 Phase 2
3. 再开启稳定工具清单
4. 再开启稳定 skill description
5. 最后开启模型锁定和控制面告警

### 11.3 固定回归场景

每次开启新 flag 前，至少跑：

1. 新品牌完整分析
2. A4 失败后补采
3. 用户追问上一轮失败统计
4. 表格导入问题列表
5. 当前报告深入追问

### 11.4 Milestone

**M7：核心场景行为不退化，复用指标可解释，改造可默认开启。**

### 11.5 上线验收标准

1. 后端本地健康检查通过
2. 前端本地健康检查通过
3. 核心回归场景通过
4. 复用率指标有数据
5. 未发现新增问号污染标记
6. 未泄露 system prompt 内容
7. feature flag 可回滚

### 11.6 部署验收

如进入 demo 部署，必须满足项目部署协议：

1. 目标 commit 明确
2. backend service active
3. frontend service active
4. `http://127.0.0.1:8000/health` 正常
5. `http://127.0.0.1:3000` 正常
6. `https://demo.imspecta.com` 正常

---

## 12. 跨 Phase 统一验收清单

每个 Phase 完成前都必须检查：

1. 当前目录不是 `D:\AGEO-main`
2. 当前分支不是 `main`
3. `git status --short --branch` 可解释
4. 变更文件无新增问号污染标记
5. `python scripts\validate_change.py` 通过
6. 相关单元测试通过
7. 如果改 UI，必须跑前端 lint/build 和浏览器截图
8. 如果改 orchestrator 行为，必须跑固定回归场景
9. 如果改数据库，必须说明迁移和回滚方式
10. 如果改部署相关内容，必须走完整部署健康检查

---

## 13. 建议任务拆分

### Epic A：提示词复用观测

覆盖 Phase 1。

任务：

1. 新增 hash 工具
2. 写入 usage metadata
3. 后端快照返回新增字段
4. 单元测试

### Epic B：固定提示词与本轮提醒拆分

覆盖 Phase 2。

任务：

1. 新增 prompt bundle
2. 拆分 render
3. 修改 orchestrator message 组装
4. 回归关键路由

### Epic C：稳定工具面

覆盖 Phase 3。

任务：

1. 定义 tool constraint
2. 实现 capability gate
3. 迁移隐藏工具逻辑
4. 补 blocked result 测试

### Epic D：稳定技能说明

覆盖 Phase 4。

任务：

1. 精简 skill tool description
2. 动态策略进入 ActiveSkillPacket
3. 保持 profile 可见
4. 补 schema hash 测试

### Epic E：模型锁定

覆盖 Phase 5。

任务：

1. 设计 locked model state
2. 路由读取 locked model
3. fallback 记录
4. 补 task routing 测试

### Epic F：控制面与灰度

覆盖 Phase 6 和 Phase 7。

任务：

1. 成本页增加提示词复用模块
2. 后端增加异常摘要
3. 配置 feature flag 默认值
4. 灰度回归和上线验证

---

## 14. 推荐优先级

如果资源有限，建议先做：

1. Phase 1：观测
2. Phase 2：固定提示词与本轮提醒拆分
3. Phase 3：工具 gate

这三期做完，就已经能显著改善“成本解释”和“系统稳定性”。

Phase 4 和 Phase 5 是规模化前的必要收口。
Phase 6 和 Phase 7 是上线运营闭环。

---

## 15. 成功判定

这套改造成功，不是看代码写了多少，而是看系统能否回答下面 5 个问题：

1. 这次为什么贵？
2. 这次为什么慢？
3. 这次工具清单有没有变？
4. 这次模型有没有换？
5. 这次固定规则有没有被动态状态污染？

如果控制面和日志都能回答这些问题，并且核心分析流程没有退化，就说明这次改造达到目标。

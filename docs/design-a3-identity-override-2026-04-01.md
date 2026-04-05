# A3 身份视角覆盖设计（2026-04-01）

> 版本：v1.0
> 日期：2026-04-01
> 状态：Approved For Implementation
> 范围：`codex/validation-retro-harness`

---

## 1. 需求背景

当前 A3 的默认目标是：

`绝大部分时间按消费者 / 用户视角生成问题。`

这条默认策略不改变。

新增需求是：

`当用户明确说“请以 XX 身份 / 视角生成问题”时，A3 应显式代入该身份来生成问题，而不是继续退化成普通消费者视角。`

这里的“身份”示例包括：

1. 采购经理
2. 品牌经理
3. 渠道商 / 经销商
4. 医生 / 顾问 / 运营负责人

---

## 2. 设计目标

本次设计追求的是最小可用扩展，而不是重做 A3。

目标只有两条：

1. 默认情况下，A3 继续按当前消费者视角生成
2. 仅当用户明确提出某个身份时，才用该身份覆盖默认视角

因此本次不引入：

1. 新 public skill
2. 新 workflow stage
3. 新的 A3 大 mode
4. 新的 role library / role schema 系统

---

## 3. 核心设计

### 3.1 仍使用现有 `question_simulation`

不新增新的工具名，继续使用：

`question_simulation`

只新增一个可选参数：

```json
{
  "mode": "brand_panorama | persona_focused | baseline_dynamic | uploaded_list",
  "persona_id": "optional",
  "identity": "optional"
}
```

其中：

1. `identity` 缺省时，行为保持现状
2. `identity` 有值时，表示用户显式要求用该身份视角生成问题

---

### 3.2 `identity` 的语义

`identity` 不是新的 persona，也不是新的 role object。

它只是：

`对当前 question generation 的显式身份覆盖层`

也就是说：

1. `mode` 决定生成路径
2. `identity` 决定“谁在提问”

例如：

1. `baseline_dynamic + identity="采购经理"`
   - 仍然是行业基线问题
   - 但问题应从采购经理视角提出

2. `brand_panorama + identity="品牌经理"`
   - 仍然是品牌全景问题
   - 但问题应从品牌经理视角提出

3. `persona_focused + identity`  
   - V1 不作为主推路径
   - 若同时传入，`identity` 优先于默认消费者画像口吻

---

## 4. 行为规则

### 4.1 默认规则

如果用户没有明确提出身份要求：

1. 不传 `identity`
2. A3 保持现在的消费者 / 用户视角

### 4.2 覆盖规则

如果用户明确说：

1. “以采购经理身份生成问题”
2. “站在品牌经理视角生成问题”
3. “从渠道商角度模拟会问什么”

则 orchestrator 应调用：

```text
question_simulation(..., identity="采购经理")
```

### 4.3 冲突规则

如果 `identity` 与默认消费者视角冲突：

1. 以 `identity` 为准
2. 不再退回普通消费者问题口吻

---

## 5. Prompt 设计

本次不重写整个 question generation prompt，只在现有 prompt 上追加一段高优先级 override。

建议追加规则：

```text
本次不要默认按普通消费者视角生成问题。
请明确代入“{identity}”的身份/角色来提问。
问题要体现该身份在真实工作中的职责、关注点、判断标准和约束。
如果该身份与普通消费者口吻冲突，以“{identity}”视角为准。
```

这样做的原因是：

1. 改动最小
2. 不破坏现有 baseline / brand / persona 的生成主框架
3. 只改变“问题由谁提出”

---

## 6. Artifact / State 设计

本次不新增新的 state 大字段。

只在 A3 结果中补充轻量 metadata：

```json
{
  "generation_mode": "baseline_dynamic",
  "generation_context": {
    "identity": "采购经理",
    "perspective_source": "user_explicit"
  }
}
```

默认情况下：

```json
{
  "generation_context": {
    "identity": null,
    "perspective_source": "default_consumer"
  }
}
```

目的：

1. 后续 A4/A5 可知道这批问题是否来自显式身份视角
2. 不引入新的复杂 state contract

---

## 7. Orchestrator 设计

orchestrator 需要做两件事：

1. 在 `question_simulation` tool schema 中暴露 `identity`
2. 在 routing policy 中明确：
   - 用户明确要求某个身份时，调用 `question_simulation` 并传 `identity`
   - 用户未明确要求时，默认消费者视角，不要擅自补身份

这意味着：

1. 这不是新的 A3 模式
2. 只是现有 `question_simulation` 的显式参数扩展

---

## 8. 实现边界

### 本次要做

1. `question_simulation` tool schema 增加 `identity`
2. `question_generation.py` 增加 identity override
3. `nodes_a3.py` 在 brand / baseline / persona 路径中读取 identity
4. A3 artifact 补 `generation_context.identity`
5. 补测试

### 本次不做

1. 新增 `role_perspective` mode
2. 新增角色模板库
3. 角色 schema 持久化
4. A5 按身份生成独立报告
5. A2 persona 系统重构

---

## 9. 验收标准

1. 不传 `identity` 时，A3 行为与当前版本一致
2. 传 `identity="采购经理"` 时，prompt 中会明确要求按采购经理身份生成问题
3. 传 `identity="品牌经理"` 时，prompt 中会明确要求按品牌经理身份生成问题
4. `uploaded_list` 路径不受影响
5. 现有 `baseline_dynamic / brand_panorama / persona_focused` 不回归

---

## 10. 最终结论

本次需求最合适的方案不是新增一整套角色模式，而是：

`保留 A3 默认消费者视角，只在用户明确要求时，通过 identity 参数显式覆盖生成视角。`

这是最小、最稳、最符合当前系统边界的做法。

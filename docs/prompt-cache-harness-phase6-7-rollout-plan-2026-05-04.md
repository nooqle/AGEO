# 提示词复用 Harness Phase 6-7 灰度与验收计划

日期：2026-05-04

状态：实施配套文档

## 1. 目标

Phase 6-7 的目标不是继续改变模型路由，而是让运营和开发能看清楚：

1. 哪些调用贵
2. 哪些调用没有命中缓存
3. 低复用是固定提示词变了、工具清单变了、模型变了，还是动态上下文太长
4. 新 flag 打开后是否能快速回滚

## 2. 当前上线边界

已经可以进入灰度的内容：

1. usage 记录中的 DeepSeek 人民币计费
2. Control-plane 成本页 token / 缓存 / 费用展示
3. 提示词复用诊断摘要
4. 最近调用里的 prompt hash、tool hash、模型身份、动态上下文大小

不进入本轮的内容：

1. 不做同一任务强制锁定模型
2. 不改 A1 / A4 / skill 的模型路由
3. 不新增数据库字段
4. 不做自动告警推送，只做页面上的轻量诊断

## 3. Feature Flag 顺序

建议按以下顺序灰度：

1. 保持 `ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED=false`
   - 只观察旧路径 metadata 和成本展示是否稳定
2. 内部账号开启 `ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED=true`
   - 观察 static prompt hash 是否稳定
   - 观察 runtime context size 是否明显上升
3. 内部账号开启 `ORCHESTRATOR_STABLE_TOOL_SURFACE_ENABLED=true`
   - 观察 tool surface hash 是否稳定
   - 重点看 blocked tool result 是否可解释
4. 内部账号开启 `STABLE_SKILL_TOOL_DESCRIPTION_ENABLED=true`
   - 观察 skill 变化是否不再影响 tool hash
5. 扩大到 demo 环境
   - 只在上述指标稳定后再考虑默认开启

## 4. 每一步验收

每个 flag 开启前后都必须看同一组指标：

1. 总缓存命中率
2. 低复用调用比例
3. 固定提示词 hash 版本数
4. 工具清单 hash 版本数
5. 平均和最大动态上下文大小
6. DeepSeek 费用是否按人民币价格估算
7. 最近调用是否没有泄露 system prompt 原文

如果出现以下情况，停止扩大灰度：

1. 低复用比例明显升高
2. 固定提示词 hash 在同一版本内频繁变化
3. 工具清单 hash 在同一场景内频繁变化
4. 用户路径出现工具误调用但没有可读解释
5. Control-plane 费用与 DeepSeek 中文价格不一致

## 5. 固定回归场景

每次灰度前至少验证：

1. 新品牌完整分析
2. A4 失败后补采
3. 用户追问上一轮失败统计
4. 表格导入问题列表
5. 当前报告深入追问

验证重点：

1. 行为没有退化
2. usage metadata 仍被写入
3. Control-plane 能解释 token、费用和复用率
4. 没有新增问号污染

## 6. 回滚方式

如果出现运行时回归，按以下顺序回滚：

1. 关闭 `STABLE_SKILL_TOOL_DESCRIPTION_ENABLED`
2. 关闭 `ORCHESTRATOR_STABLE_TOOL_SURFACE_ENABLED`
3. 关闭 `ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED`
4. 保留 Control-plane 费用与诊断展示

说明：

1. Control-plane 展示只读取 usage 数据，不改变运行路径
2. 价格配置可以通过环境变量覆盖
3. 不需要数据库回滚

## 7. 部署验收

如果进入 demo 部署，必须完成：

1. 明确目标 commit
2. backend service active
3. frontend service active
4. `http://127.0.0.1:8000/health` 正常
5. `http://127.0.0.1:3000` 正常
6. `https://demo.imspecta.com` 正常

没有完成这些检查前，不应声称已部署完成。

## 目标

- 本 PR 解决的问题：
- 所属阶段：
- 影响层级：`Orchestrator / Agent(Executor) / Skill / Tool / Harness`

## 接口变化

- 新增 / 修改的 public contract：
- 是否涉及 `PromptAssembly / SkillContract / ToolCapabilityMatrix / HarnessDecision`：

## 测试证据

- 自动化测试：
- 主路径验证：
- 失败 / 恢复路径验证：

## 残余风险

- 已知未覆盖项：
- 是否存在分支范围限制：

## 边界回退检查

- [ ] `Skill` 没有重新退化成 prompt patch
- [ ] `Tool` 没有重新承载粗粒度业务语义
- [ ] `Harness` 没有重新只剩状态记录
- [ ] `Orchestrator` 没有重新膨胀成总说明书

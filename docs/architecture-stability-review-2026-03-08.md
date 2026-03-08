# 架构稳定性审查与收口记录（2026-03-08）

## 目标
把当前 Chat / WebSocket / Report V2 / Dashboard V2 / A5 / analytics v2 收口成更稳定的结构，减少重复映射、状态漂移和旧口径残留。

## 已识别问题
1. Report 头部仍可能漏出旧的 BWVS / 综合分文案。
2. Dashboard V2 在缺失场景级数据时，把缺数据展示成真实 0。
3. orchestrator / monitoring 仍在对外使用 BWVS 主叙事。
4. action log 完成态依赖前端补偿匹配，后端步骤标识不一致。
5. Chat 历史消息重建和实时消息装配是两套逻辑。
6. Report / Dashboard 的 V2 数据适配分散在多个文件中。
7. useWebSocket.ts 与 nodes_a5.py 文件职责过重。
8. 注释缺少边界说明，难以维护状态生命周期和 fallback 规则。

## 线程拆分
### 线程 A：正确性与口径修复
- Report 头部统一使用清洗后的 narrative 字段
- Dashboard V2 fallback 缺数据返回 null / 空态
- 清理 orchestrator / monitoring 的 BWVS 主叙事
- 对齐 action log 的前后端步骤标识

### 线程 B：前端适配层与状态架构重构
- 新增 `frontend/src/adapters/chatMessage.ts`
- 新增 `frontend/src/adapters/reportV2.ts`
- 新增 `frontend/src/adapters/dashboardV2.ts`
- Chat 历史重建与实时 output card 复用同一 adapter
- ReportContent 页面只保留布局，normalize / sanitize / format 抽离
- useWebSocket 的 action log 逻辑抽到子模块

### 线程 C：后端 A5 / orchestrator / analytics 收口
- analytics v2 fallback 规则改成 null-first
- orchestrator / monitoring 用户文案切换到提及率 / 官网引用率 / 风险场景
- A5 后续拆分方向：metrics / contract / prompt / sanitizer / persistence
- 逐步减少 nodes_a5.py 内聚合职责

## 当前实现进度
- 线程 A：进行中
- 线程 B：进行中
- 线程 C：进行中

## 验收重点
1. 用户主界面、聊天与监测说明不再以 BWVS 为主叙事。
2. 缺失场景数据展示为 `--` / `暂无数据`，而不是 0。
3. Chat 刷新前后消息结构一致。
4. action log 在完成 / 停止 / 中断后不再残留 spinner。
5. Report / Dashboard 组件不再直接承担原始契约归一化。

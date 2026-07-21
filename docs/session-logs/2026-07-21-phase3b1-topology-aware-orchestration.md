# Session Log: 3b-1 拓扑感知编排里程碑完成（1.1~1.4）

日期：2026-07-21
分支：codex/amwaychina-mainline
方向文件：`docs/specta-agentic-infrastructure-blueprint-2026-07-21.md`

## 里程碑状态

蓝皮书路径：3a ✅ → **3b-1（本次完成 1.1~1.4）** → 3b-2 计划可视化 → 3c chat-to-topology

| 子项 | 状态 | 交付物 |
|---|---|---|
| 3b-1.1 节点契约 + 注册表骨架 | ✅ | `app/workflow/node_contracts.py`：领域无关契约层（id/kind/inputs/outputs/config/executor），AmwayChina 8 节点注册 |
| 3b-1.2 节点输入输出显式化 | ✅ | extract/projection 从 `a4_fetch_node` 拆出为独立 LangGraph 节点（`app/workflow/nodes_amway.py`）；执行内核原样搬移，仅换编排外壳；AgentState 补 5 个 amway 字段 |
| 3b-1.3 拓扑感知编排 | ✅ | `app/workflow/topology_resolver.py`：平台门 + 四条链门（questions→fetch / fetch→extract / extract→projection / projection→report）；画布断线真实影响运行 |
| 3b-1.4 拓扑存储上后端 | ✅ | `flow_topologies` 表（alembic 038）+ GET/PUT API + 前端 localStorage/后端双写；E2E 全过 |
| 3b-1.5 自定义节点真执行 | ⬜ 下一项 | 分析节点接 LLM 二级解读；内容创作节点接词库+分析产草稿 |
| 3b-1.6 局部运行 | ⬜ | 只跑拓扑某分支 |

## 关键设计决策

1. **命根子约束**：契约层只允许领域无关概念；品牌/圈层/词库语义留在节点实现与 prompt 中。
2. **空拓扑语义 = 内置全连**：无拓扑记录/加载失败 → `FlowTopology()`，行为与硬编码时代逐字节一致。
3. **None 哨兵陷阱**：`normalize_public_platforms(None)` 意为全平台；平台全断开时必须早退，绝不下传空 filter。
4. **平台键空间**：画布 id == executor 键（deepseek/kimi/doubao/hunyuan）；public 空间 hunyuan→yuanbao。
5. **链路形态**：`a4_fetch → amway_extract → amway_projection → a5_analytics`，每跳由对应画布连线门控；断链只影响推进，不影响已产出物落 state。

## 本会话修复的重要 bug

**React 18 StrictMode updater 不纯导致画布 state 与后端 id 分叉**：dev 双跑 setState updater，`updateTopology` 内含 `Math.random()` 生成 id + localStorage/PUT 副作用 → 双跑产生两个 id。修复：updater 纯化 + dirty ref/useEffect 持久化 + id 移到事件处理器。已沉淀 memory：`react-setstate-updater-purity.md`。

## 测试基线（全绿）

- 拓扑/契约/节点/门接线/flow-topology API：56 passed
- 实体抽取校准 + 圈层报告 + 周期视图：109 passed（含 5 个从 `_build_amway_entity_pipeline_update` 迁移到新节点的测试）
- run-service：16 passed；parser（A4 核心资产）：56 passed
- `import app.workflow.graph` 装配 OK；black / ruff 通过

## 环境状态

- 后端进程 be5o07udb（port 8000，无 --reload）已加载全部新代码，`flow-topology` 端点已注册
- 待办：E2E 验证画布断线真实生效（需消耗一次真实采集，受 60 秒间隔约束，接线测试已证明门控值到达执行入口）

# Plan：生产线「配方」v0

日期：2026-07-21  
定案（用户）：

| 决策 | 内容 |
|---|---|
| 命名 | **配方**（用户语言）；工程 `flow_recipe` |
| 作用域 | **组织级共享** + **品牌/项目级**（entity），类似 skill 配置分层 |
| 切换 | **直接替换**当前生产线拓扑，无 diff 确认弹窗 |
| 运行 | **点运行即确认开跑**（`auto_dispatch=true`），不再停 M3 二次确认闸 |
| 记忆 | 配方 = 可见、可命名、可删的编排记忆；不做黑盒自动学习 |

## 非目标（v0）

- 意图自动匹配推荐  
- 静默自动沉淀  
- 跨组织市场配方  
- 配方内嵌词库/报告正文  

## 数据

`flow_topology_recipes`：

- `organization_id`（必填）  
- `entity_id`（可空 = 组织级）  
- `name`, `description`  
- `topology` JSON（与 flow_topologies 同构）  
- `created_by_user_id`, timestamps, `version`  

## API（`/amwaychina`）

- `GET .../flow-recipes?entity_id=` → 组织级 + 该品牌级  
- `POST .../flow-recipes` → 创建（可 `from_current=true` 从当前拓扑另存）  
- `PATCH/DELETE .../flow-recipes/{id}`  
- `POST .../entities/{id}/flow-recipes/{recipe_id}/apply` → 校验后写 `flow_topologies`（替换）  

## 前端

生产线顶栏「配方」：选用（替换）、另存当前、删除（管理精简）  

## 运行即确认

`AmwayAssociationCircleConsolePage` `createRun`：`auto_dispatch: true`；文案改为已开始执行。  
计划条仍可展示 flow_plan 快照（运行中），但不强制先确认。  

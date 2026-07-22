# Wave A 验收执行记录

日期：2026-07-22  
工作区：`D:\AGEO-worktrees\amwaychina-mainline`  
分支：`codex/amwaychina-mainline`  
首轮验收提交：`a00d3930e222cd5a34fff9c75676667809678e0e`
修复提交：`c4741f2252f296fbd14ec9a385603c979a790f2b`
验收标准：`docs/plans/2026-07-21-wave-a-acceptance.md`

## 1. 总结论

**PASS（2026-07-22 复验结案）。**

- 功能：F1–F8 全部通过（8/8）。
- 视觉 / 交互：V1–V5 通过（5/5）。
- 工程：E1–E7 通过（7/7）。
- 非目标：全部守住。

首轮验收因 F7 不可达判定 FAIL。修复提交 `c4741f2` 落地后，已按结案条件复验 F7、B3、B2，三项全部通过，因此 Wave A 改判 PASS。

## 2. 环境与前置条件

- 当前分支 HEAD 为 `a00d393`，本地相对远端 ahead 24。
- 验收前本地 PostgreSQL 的 Alembic revision 为 `038`，代码 head 为 `039`，尚无 `flow_topology_recipes` 表。
- 已先执行 `alembic upgrade head`，验收后确认 `039 (head)`。
- 当前分支后端运行于 `127.0.0.1:8000`，前端运行于 `127.0.0.1:3000`；`/health` 与 `/amwaychina` 均返回 200 后开始 Live 验收。

> 发布前置条件：目标环境必须先应用 migration 039；否则配方 API 无法工作。这不是 F1–F8 的实现回归，但属于上线阻断条件。

## 3. 功能验收证据

| ID | 结果 | 实测证据 |
|---|---|---|
| F1 | ✓ | 配方列表为空时显示“还没有配方”、用途说明、填写名称提示及“存为配方”按钮。 |
| F2 | ✓ | 分别保存品牌级 `WaveA验收-品牌-20260722` 与组织级 `WaveA验收-组织-20260722`；列表显示“品牌/组织”scope 标签。 |
| F3 | ✓ | 在四平台组织配方和三平台品牌配方之间直接切换，无二次确认；画布计划与数据库 topology 同步切换。 |
| F4 | ✓ | 删除三平台测试配方，经删除确认后列表立即消失并显示成功提示。 |
| F5 | ✓ | 点击“开始运行”后直接进入 `fetching_answers`；run `96648dbf-3867-4624-87db-19a3ab81d996` 的 `requires_user_action=false`、`user_action_type=null`，未进入 `waiting_scope_confirmation`。为避免继续消耗采集资源，随后取消该测试 run。 |
| F6 | ✓ | “跳过豆包”先显示编译预览；确认后计划从四平台变为 DeepSeek/Kimi/腾讯元宝，共 9 步，数据库 `removedEdgeIds=["e-fetch-doubao"]`。 |
| F7 | ✓ | 修复后在 0 个 active run、2 个历史 completed run 条件下刷新页面；完成权限加载后，“最近有已完成的运行……”提示与“存为配方”按钮均可见。 |
| F8 | ✓ | 切换后显示“当前：WaveA验收-组织-20260722”或对应品牌配方名。 |

## 4. 视觉 / 交互验收证据

| ID | 结果 | 实测证据 |
|---|---|---|
| V1 | ✓ | 源码扫描无旧紫色实现；浏览器观察分析节点使用石色/中性表现。唯一 `violet` 命中是“禁止 violet”的代码注释。 |
| V2 | ✓ | 配方、预设/自然语言编排集中在同一个“编排”面板，上下层级清楚。 |
| V3 | ✓ | “开始运行”、保存、查看报告等主行动均为 Evidence Teal；未见大面积 glow。 |
| V4 | ✓ | 分析节点保持石色/中性；内容节点保留克制橙，未与紫色并存。 |
| V5 | ✓ | 30 秒主路径可从配方/预设直接到“开始运行”，没有退化为设置项堆叠；计划说明已与直接执行行为一致。 |

浏览器验收期间 console warning/error 均为空。

## 5. 工程验收证据

| ID | 结果 | 证据 |
|---|---|---|
| E1 | ✓ | `python scripts/run_3b1_suite.py`：`81 passed in 5.30s`。 |
| E2 | ✓ | `frontend` 下 `npx tsc --noEmit` exit 0。 |
| E3 | ✓ | `AmwayFlowCanvas.tsx` 1506 行，小于 1600。 |
| E4 | ✓ | Canvas 只挂载 `AmwayFlowOrchestrationPanel`；配方与拓扑编排由该组件统一承载。 |
| E5 | ✓ | 相关源码无 violet/purple/旧 AI 紫色硬编码；仅有禁止旧紫色的注释。 |
| E6 | ✓ | 相关源码 `???` 扫描无命中；`python scripts/validate_change.py` 通过。 |
| E7 | ✓ | Wave A 与拆分 backlog / 总路线记录一致。 |

非目标核对：`orchestrator_node.py` 未开拆；未实现意图自动推荐配方；未静默修改默认拓扑。

## 6. 已关闭 Bug / 保留风险

### B1 — 已关闭：完成态“存为配方”入口在刷新后不可达

`AmwayFlowCanvas` 只在 `activeRun.status === 'completed'` 时传入完成态建议；但页面的 `selectedRun` 来自 active-run API，后端查询只返回 `BRAND_INTELLIGENCE_ACTIVE_RUN_STATUSES`，排除了 `completed`。因此一次运行结束后重新加载页面，F7 CTA 无法可靠出现。

修复与复验：新增 latest-run completed 查询；0 active、2 completed 条件下刷新后提示与 CTA 可见。

### B2 — 已关闭：执行计划仍显示旧的“确认闸”文案

界面同时出现“点运行即开跑”和“点击开始运行后进入确认闸，确认后才执行”。实际 F5 已是一键运行，旧文案与真实行为互相矛盾，演示时会误导用户。

修复与复验：页面显示“点击『开始运行』后按该计划直接执行（运行即确认）”；旧“进入确认闸”计划说明不存在。

### B3 — 已关闭：拓扑修改后“当前配方”提示不会失效

先切换组织配方后，界面显示“当前：组织配方”；再用“跳过豆包”修改并应用拓扑，提示仍保持该组织配方名，尽管当前拓扑已经与配方内容不一致。`activeRecipeName` 只在 apply/create/delete 时更新，没有拓扑 dirty/change 失效机制。

修复与复验：套用 `WaveA复验-B3-20260722` 后执行“跳过豆包”并确认，角标变为“基于：WaveA复验-B3-20260722 · 已修改”。

### R1 — 上线前置：migration 039 必须部署

现有数据库若停留在 038，配方表不存在，F1–F4 会直接失败。部署流程应在启动新代码前明确执行或人工确认 039。

## 7. 验收后清理

- 首轮删除 3 条验收配方；复验创建的 `WaveA复验-B3-20260722` 也已删除，最终无本次测试配方。
- 恢复安利 entity 的空拓扑：`customNodes=[]`、`customEdges=[]`、`removedEdgeIds=[]`；最终 topology version 为 16（版本保持单调递增）。
- 测试 run `96648dbf-3867-4624-87db-19a3ab81d996` 已取消，最终 status/stage 均为 `cancelled`。
- 浏览器确认四平台、10 步、无自定义分析节点、配方空态恢复；历史 completed run 提示仍正常显示。

## 8. 结案判定

F7、B3、B2 已完成 Live 复验，功能 F1–F8、视觉 V1–V5、工程 E1–E7 全部通过，非目标守住。**Wave A 最终判定 PASS。**

## 9. 修复回写（2026-07-22 续）

| Bug | 修复 |
|---|---|
| B1 F7 | 新增 `GET /intelligence-runs/entities/{id}/latest?status=completed`；编排面板用其驱动「存为配方」提示，不依赖 active-run |
| B2 文案 | 计划区改为「开始运行后按计划直接执行」；清理「进入确认闸」误导 |
| B3 配方名 | 非配方拓扑应用后标记 `基于：xxx · 已修改`；套用/另存配方时清除 dirty |

工程复验：`tsc --noEmit` exit 0；`run_3b1_suite` 81 passed；`validate_change.py` PASS。
Live 复验：F7、B3、B2 全过；浏览器 warning/error 为 0。测试配方已删除，拓扑恢复为四平台、无 removed edge / custom node。
部署前置不变：目标环境必须应用 migration 039。

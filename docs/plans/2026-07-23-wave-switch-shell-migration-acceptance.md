# Wave Switch — 壳切换 / M2（Dashboard+Chat 外壳退役 · Chat 降级）

日期：2026-07-23  
状态：**工程已落地 · 首轮手测 3 PASS / F4 FAIL（鉴权 OOM）已修 · 待复测**  
前置：M1 amwaychina 形态成立（Wave A–Q / 完善轨 PASS）  
对照：蓝图 §1.3 抛弃 Dashboard+Chat 外壳；引擎/工具保留  
**本波与蓝图强相关**：兑现「拓扑即计划 / Chat 即编译器 / 抛弃旧外壳」，不是旁路体验修补。

---

## 0. 双必达中的位置

| ID | 内容 | 本波 |
|---|---|---|
| **M1** | amwaychina OK | 守住；本波不回退能力 |
| **M2** | 全切新设计 | **本波交付目标** |

**Chat 定案：降级**

- **是：** 编译器 + 辅入口（改图/配方预览确认、可选开跑、证据/轻问答）  
- **否：** 隐式 plan 的黑盒主分析舞台；主分析话术默认进 agent 长跑  

---

## 1. 目标主路径（唯一对外叙事）

```
登录/选品牌 → /amwaychina 生产线
  →（可选）改图 / 套配方 / Chat 编译确认
  → 生产线「开始运行」
  → 看证据（圈层/词库/报告）
  →（可选）存配方
```

---

## 2. 已实现（工程）

| ID | 事项 | 实现要点 |
|---|---|---|
| **S1** | 默认落地 | 登录 fallback、`HomeAuthLink`、auth next、`RequireAuth` → `/amwaychina` |
| **S2** | 起跑叙事 | 产品默认壳=生产线；遗产 Dashboard 新建品牌也落 flow |
| **S3** | Chat 降级 | 主分析话术 → `line_guide` 卡（引导生产线）；逃生口「仍作为普通对话发送」 |
| **S4** | IA / 文案 | JOURNEY 降级文案；控制台/设置/导航「生产线」用语 |
| **S5** | 旧路由 | `/dashboard` **默认 redirect** 到 `/amwaychina`；`?legacy=1` 临时逃生 + 顶栏警示 |
| **S6** | 资产入口 | settings / brand-space / chat 无 entity 失败回落 → 生产线 |

共享常量：`frontend/src/lib/productShell.ts`

---

## 3. Chat 降级细则

| ID | 项 | 工程 |
|---|---|---|
| C1 | 角色文案 | `chatRoleHint` / `chatLineGuide*` |
| C2 | 主分析话术 | `classify` → `line_guide`（原 null/agent） |
| C3 | 编排能力 | D/Q compile/recipe 保留 |
| C4 | 开跑 | Q 显式 CTA 保留 |
| C5 | Deep-link | 引导卡 CTA → `buildProductionLineHref` |

意图脚本：`node scripts/check_chat_topology_intent.mjs`（含 line_guide 用例）

---

## 4. 验收总表

| ID | 项 | 结果 |
|---|---|---|
| F1 | 登录后默认进生产线，不经旧 Dashboard 能开始工作 | **PASS**（首轮） |
| F2 | 直接访问 `/dashboard` 被带到 `/amwaychina` | **PASS**（首轮） |
| F3 | Chat「帮我分析品牌…生成报告」出现生产线引导卡，不直接进 agent 长跑 | **PASS**（首轮） |
| F4 | Chat「跳过豆包」等编排仍可用（compile） | ❌ 首轮 FAIL（Failed to fetch / 鉴权 MemoryError）→ **已修** · ⬜ 复测 |
| F5 | 逃生口「仍作为普通对话发送」可走 WS | 部分（WS/API 证据；浏览器手点未完成）· ⬜ 补手点 |
| F6 | 生产线起跑/M1 能力不回退 | 部分（API run→A4；按钮手点未完成）· ⬜ 补手点 |
| E1 | intent 脚本绿；中文无 `???` | ✓ 工程 |
| E2 | 无静默改图/auto-run 回潮 | ✓ 代码纪律 |
| E3 | 鉴权轻量加载单测 | ✓ `test_user_auth_lightweight_load` |

| **总裁决** | **暂不 PASS · F4 阻塞已修 · 请复测 F4 + 补 F5/F6 手点** |
|---|---|

### F4 根因与修复（2026-07-23）

| 项 | 内容 |
|---|---|
| 信号 | 前端 Failed to fetch；后端 asyncpg 解码 messages **MemoryError** |
| 根因 | `get_current_user` → User 关系 `selectin` 级联：org → entities → sessions → **全部 messages** |
| 修复 | User/Entity/Session/Organization 大集合改 `lazy=select`；`_lightweight_user_select` 对 sessions/owned_entities **noload**，org 下 users/entities **noload**；`require_amway_entity` 不再 selectin sessions |
| 旁证 | 重启后直打 compile 曾 200 + rule/skip_doubao（引擎本身正常） |

---

## 5. 非目标 / 后续

- 不删除 Chat/Dashboard 代码树（先产品路径切换）  
- 不拆 Orch 阶段 C / 第二垂直  
- 遗产 `?legacy=1` 可在稳定后收紧或删除  
- 圈层报告仍可 deep-link 到 Chat **查看证据**（辅入口，非主分析舞台）

---

## 6. 与蓝图完成度

| 口径 | Switch 后预期 |
|---|---|
| §1.3 抛弃外壳 | **主路径兑现** |
| Chat 即编译器 | **产品角色对齐** |
| 整本蓝图 | 抬产品命题分；不自动抬平台化 2.4 |

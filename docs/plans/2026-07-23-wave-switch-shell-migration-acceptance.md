# Wave Switch — 壳切换 / M2（Dashboard+Chat 外壳退役 · Chat 降级）

日期：2026-07-23  
状态：**PASS（2026-07-23 手测 + P1 复验三条全过）**  
前置：M1 amwaychina 形态成立（Wave A–Q / 完善轨 PASS）  
对照：蓝图 §1.3 抛弃 Dashboard+Chat 外壳；引擎/工具保留  
**本波与蓝图强相关**：兑现「拓扑即计划 / Chat 即编译器 / 抛弃旧外壳」，不是旁路体验修补。

关键提交：

| 提交 | 内容 |
|---|---|
| `6468b47` | 默认 `/amwaychina`、Dashboard redirect、Chat 降级 |
| `22de6cf` | 鉴权 OOM（F4） |
| `50325ef` | 安利实体重复（P1 noload 污染） |
| `ef6c139` | 重复实体安全软删脚本（本机 dry-run 无候选） |

---

## 0. 双必达中的位置

| ID | 内容 | 本波 |
|---|---|---|
| **M1** | amwaychina OK | 守住；本波不回退 |
| **M2** | 全切新设计 | ✅ **PASS** |

**Chat 定案：降级（已兑现）**

- **是：** 编译器 + 辅入口（改图/配方预览确认、可选开跑、证据/轻问答）  
- **否：** 隐式 plan 的黑盒主分析舞台  

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
| **S2** | 起跑叙事 | 产品默认壳=生产线 |
| **S3** | Chat 降级 | 主分析话术 → `line_guide`；逃生口「仍作为普通对话发送」 |
| **S4** | IA / 文案 | JOURNEY 降级文案；「生产线」用语 |
| **S5** | 旧路由 | `/dashboard` 默认 redirect；`?legacy=1` 临时逃生 |
| **S6** | 资产入口 | 失败回落 → 生产线 |

共享常量：`frontend/src/lib/productShell.ts`

---

## 3. 验收总表

| ID | 项 | 结果 |
|---|---|---|
| F1 | 登录后默认进生产线 | **PASS** |
| F2 | `/dashboard` → `/amwaychina` | **PASS** |
| F3 | 主分析话术 → 生产线引导卡，不进 agent 长跑 | **PASS** |
| F4 | Chat「跳过豆包」compile 预览可用 | **PASS**（鉴权 OOM 修复后复测） |
| F5 | 「仍作为普通对话发送」进 WS | **PASS** |
| F6 | 生产线开始运行 → A4，未立刻 failed | **PASS** |
| E1 | intent 脚本 / 中文 | ✓ 工程 |
| E2 | 无静默改图/auto-run 回潮 | ✓ |
| E3 | 鉴权轻量加载单测 | ✓ |
| **P1** | 不重复创建安利；run 绑原 entity | **PASS**（复验三条全过） |

| **总裁决** | **PASS** |
|---|---|

### 阻塞修复摘要

| 问题 | 修复 |
|---|---|
| F4 MemoryError / Failed to fetch | 鉴权不灌 sessions/messages 图 |
| P1 重复创建安利 + run 错绑 | 去掉 org.entities noload 污染；entitlement 查 Entity 表 |

### P1 复验（用户 2026-07-23）

1. 并发两次 `/feature-entitlements/amwaychina` → 同 `entity_id`  
2. 组织实体数量不增  
3. 「开始运行」绑定原安利实体  

---

## 4. 非目标 / 后续

- 不删除 Chat/Dashboard 代码树（产品路径已切；遗产 `?legacy=1` 可后收）  
- Orch 阶段 C / 第二垂直 / 平台化 另立项  
- 黑盒自学仍排除  

---

## 5. 与蓝图完成度

| 口径 | Switch PASS 后 |
|---|---|
| §1.3 抛弃外壳 | **主路径已兑现** |
| Chat 即编译器 | **产品角色对齐** |
| 整本蓝图 | 抬产品命题；不自动抬 2.4 平台化 |

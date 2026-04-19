# GEO Canonical Cleanup Checklist

## Goal

本次 cleanup 的目标不是“迁移老数据”，而是：

- 清空旧品牌生成数据
- 让系统从 GEO canonical 新合同重新起步
- 只保留账号体系，不保留历史包袱

## Keep

- users
- organizations
- auth / identity

## Remove

- brand entities
- related sessions / messages
- analysis tasks / task runs
- snapshots
- knowledge records / knowledge segments
- monitoring schedules / baseline data
- 旧 report / dashboard derived artifacts

## Execution Order

1. 先做 `--dry-run`
2. 核对每类删除计数是否符合预期
3. 确认只作用于 brand-scoped data
4. 再做 confirm path
5. cleanup 完成后立即验证 first-run recreation

## Script

执行脚本：

- [D:\AGEO-worktrees\geo-a5-canonical-redesign\aeo-platform\backend\scripts\purge_brand_generated_data.py](D:/AGEO-worktrees/geo-a5-canonical-redesign/aeo-platform/backend/scripts/purge_brand_generated_data.py)

要求：

- 先 `--dry-run`
- 再 `--confirm`
- 不允许跳过 dry-run 直接执行 destructive cleanup

## First-Run Recreation

cleanup 后必须验证：

1. brand list 为空
2. 创建 brand entity
3. 创建 / 恢复该 entity 的 session
4. 跑首轮 `panorama`
5. 生成第一个 canonical `report`
6. dashboard 首页出现“最近一轮分析”
7. `打开最新报告` 能直接展开报告

## Acceptance

cleanup 成功的标准：

- 账号体系仍可登录
- brand-scoped 数据已清空
- 首轮 brand recreation 流程跑通
- 第一个新 canonical report 可正常进入 dashboard / chat

## Failure Handling

如果 cleanup 后失败：

- 不先追求恢复旧品牌数据
- 先确认 brand recreation 路径是否可重新创建 entity/session/report
- 如果账号体系受影响，立即停止并按账号侧问题处理

## Writeback

上线执行时，必须把以下信息写回 state：

- dry-run 计数
- confirm 实际执行结果
- cleanup 后首轮 brand recreation 是否成功
- 是否出现 session / artifact / dashboard 首页异常

# GEO Canonical Rollout Checklist

## Scope

本清单只覆盖当前已经闭环的主路径：

- `A5 canonical report`
- `Dashboard 首页最近一轮报告摘要`
- `Dashboard -> 打开最新报告 -> Chat 自动展开对应报告`

本清单**不**把以下页面当成这次主上线验收范围：

- 旧 `analytics all / overview / mentionBoard / sourceBoard / radarBoard` 组合页
- 旧 dashboard dialog 细分报告面板
- 非首页监测页里的所有历史兼容读路径

这些页面仍可继续存在，但不应作为本次 GEO canonical 上线的主真相源。

## Release Gate

上线前必须满足：

- `A1-A4` producer 协议未改坏
- `analysis_report_skill` 对外能力面未扩散
- `output_type=report` + `artifact_kind=geo_report` + `report_kind=panorama|scenario` 已稳定
- 首页只读最近一轮报告摘要，不再混旧三看板
- `打开最新报告` 能进入 chat 并自动展开正确 artifact
- `report-writing-principles-2026-04-18.md` 已作为默认写作约束执行

## Backend Checks

- `pytest aeo-platform/backend/tests/test_a5_canonical.py`
- `pytest aeo-platform/backend/tests/test_analytics_canonical_projection.py`
- `python -m compileall aeo-platform/backend/app/services/analytics_service.py`

通过标准：

- `test_a5_canonical.py` 全绿
- `test_analytics_canonical_projection.py` 全绿
- 无新的 report contract / dashboard-home contract 回归

注意：

- 测试 shell 必须显式提供非默认 `JWT_SECRET`
- 不要把环境缺失误判成代码回归

## Frontend Checks

- `npx tsc --noEmit`
- `npm run lint`
- `npm run build`

通过标准：

- TypeScript 无 error
- lint 允许当前 4 个已知旧 warning 存在，但不能新增 warning/error
- build 成功

## Browser Checks

用真实浏览器验证以下链路：

1. 打开 `/dashboard`
2. 确认首页看到：
   - `最近一轮分析`
   - `提及率`
   - `排名`
   - `官网 AI 友好度`
   - `提及品牌的引用链接分布`
   - `这轮关联问题`
3. 点击 `打开最新报告`
4. 确认进入正确 `chat/{sessionId}?artifact_id=...`
5. 确认右侧 canvas 自动展开
6. 确认报告正文可见，不只是 header

## Runtime Discipline

- 分支 backend / frontend 每次 rerun 前先确认进程不是 stale
- 如果浏览器结果异常，先检查：
  - backend 启动时间
  - frontend 启动时间
  - `.env.local` 是否指向分支 backend
- 不要把 stale process false sample 当成真实回归

## Known Non-Blocking Risks

- frontend 仍有 4 个历史 warning
- 非首页 analytics 页面仍保留 legacy 兼容读路径
- 上线后仍需严格按 cleanup / brand recreation 流程执行

## Go / No-Go Rule

可以上线：

- 主链全部通过
- 非阻塞项没有扩大
- cleanup 演练和 brand recreation 路径已确认

不得上线：

- 首页再次回落到旧三看板兼容模式
- `打开最新报告` 不能自动展开对应报告
- A5 report contract 或 report writing 质量明显回退

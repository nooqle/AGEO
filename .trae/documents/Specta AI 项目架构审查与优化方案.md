## Phase 1: 清理与标准化

执行以下操作：

1. **删除根目录 requirements.txt**
   - 文件: `d:\AGEO\requirements.txt`
   - 原因: 与 `aeo-platform/backend/requirements.txt` 重复

2. **删除所有 __pycache__ 目录和 .pyc 文件**
   - 清理约 60+ 个缓存文件
   - 这些不应提交到版本控制

3. **删除 backend/logs/ 下的所有日志文件**
   - 约 30+ 个运行时日志文件
   - 这些是临时文件，不应提交

4. **更新 .gitignore**
   - 添加 `__pycache__/`、`*.pyc`、`logs/` 等规则
   - 防止未来再次提交

请确认后执行。
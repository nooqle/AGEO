## 任务：将 `d:\AGEO\logo.png` 替换到前端项目

### 当前Logo使用情况
1. **主Logo文件**: `d:\AGEO\frontend\public\logo.png` (32x32px，用于Header组件)
2. **Favicon**: `d:\AGEO\frontend\src\app\favicon.ico`
3. **引用位置**: `Header.tsx` 第14行使用 `<Image src="/logo.png" alt="Specta AI" width={32} height={32} />`

### 执行步骤

#### 步骤1: 备份当前Logo
- 将现有 `d:\AGEO\frontend\public\logo.png` 备份为 `logo.png.backup`

#### 步骤2: 复制新Logo
- 将 `d:\AGEO\logo.png` 复制到 `d:\AGEO\frontend\public\logo.png`

#### 步骤3: 验证替换
- 检查新Logo文件是否存在
- 确认文件格式正确

#### 步骤4: 清理缓存并重启（如需要）
- 清理 `.next` 缓存目录
- 重新构建前端（如果开发服务器未运行）

### 注意事项
- 新Logo建议尺寸为 32x32px 或更大（Next.js Image 组件会自动处理）
- 支持 PNG 格式
- 替换后页面会自动热更新（开发模式下）

请确认此计划后，我将开始执行替换操作。
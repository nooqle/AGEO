# Playwright 浏览器安装指南

## 为什么需要安装浏览器？

Specta AI 的 Browser Agent (A6) 使用 Playwright 进行网页自动化，用于从 AI 搜索引擎（DeepSeek、Kimi 等）获取答案。Playwright 需要下载浏览器内核才能运行。

## 快速安装

### Windows

```bash
cd aeo-platform\backend
scripts\install_playwright.bat
```

### Linux / macOS

```bash
cd aeo-platform/backend
chmod +x scripts/install_playwright.sh
./scripts/install_playwright.sh
```

### 手动安装

```bash
# 确保已安装 playwright Python 包
pip install playwright==1.49.1

# 安装 Chromium 浏览器内核
python -m playwright install chromium

# Linux 系统还需要安装系统依赖
python -m playwright install-deps chromium
```

## 安装内容

- **Chromium**: 约 300MB，用于 Browser Agent 的网页自动化
- **系统依赖** (仅 Linux): 浏览器运行所需的系统库

## 验证安装

```bash
# 检查 Playwright 是否正确安装
python -c "from playwright.sync_api import sync_playwright; print('Playwright installed successfully')"

# 检查浏览器是否已安装
python -m playwright install --dry-run chromium
```

## 常见问题

### 1. 安装失败：权限不足

**Windows**: 以管理员身份运行命令提示符

**Linux/macOS**: 使用 `sudo` 或确保有写入权限

### 2. 网络问题导致下载失败

Playwright 会从官方 CDN 下载浏览器，如果网络不稳定：

```bash
# 设置代理（如果需要）
export HTTPS_PROXY=http://your-proxy:port

# 重试安装
python -m playwright install chromium
```

### 3. 磁盘空间不足

Chromium 需要约 300MB 空间，确保有足够的磁盘空间。

### 4. Linux 系统依赖缺失

如果运行时出现类似错误：
```
Error: Host system is missing dependencies
```

运行以下命令安装系统依赖：
```bash
python -m playwright install-deps chromium
```

## 浏览器存储位置

Playwright 浏览器默认安装在：

- **Windows**: `%USERPROFILE%\AppData\Local\ms-playwright`
- **Linux**: `~/.cache/ms-playwright`
- **macOS**: `~/Library/Caches/ms-playwright`

## 卸载浏览器

如果需要卸载 Playwright 浏览器：

```bash
# 删除所有浏览器
python -m playwright uninstall --all

# 或手动删除浏览器目录（见上方路径）
```

## 其他浏览器

项目默认使用 Chromium，如需安装其他浏览器：

```bash
# Firefox
python -m playwright install firefox

# WebKit (Safari)
python -m playwright install webkit

# 安装所有浏览器
python -m playwright install
```

## 相关文档

- [Playwright 官方文档](https://playwright.dev/python/)
- [Playwright 安装指南](https://playwright.dev/python/docs/intro)
- [Browser Agent 设计文档](../../Doc/Agent%20design/Browser%20Agent.md)

## 技术支持

如果遇到问题，请：

1. 检查 Python 版本（需要 3.10+）
2. 确保 playwright 包已正确安装
3. 查看错误日志
4. 参考 Playwright 官方文档

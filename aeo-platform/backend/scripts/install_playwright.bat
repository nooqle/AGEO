@echo off
REM Playwright 浏览器内核安装脚本 (Windows)

echo ==========================================
echo Playwright 浏览器内核安装
echo ==========================================
echo.

REM 检查 Python 是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到 Python
    echo 请确保 Python 已安装并添加到 PATH
    pause
    exit /b 1
)

echo 📦 安装 Playwright 浏览器内核...
echo.

REM 安装 Chromium (项目使用的浏览器)
python -m playwright install chromium

if errorlevel 1 (
    echo.
    echo ❌ 安装失败
    echo.
    echo 请尝试手动安装:
    echo   python -m playwright install chromium
    echo.
    pause
    exit /b 1
)

echo.
echo ✅ Playwright 浏览器内核安装成功！
echo.
echo 已安装的浏览器:
echo   - Chromium (用于 Browser Agent)
echo.
echo 如需安装其他浏览器:
echo   python -m playwright install firefox
echo   python -m playwright install webkit
echo.
echo ==========================================
echo 安装完成！
echo ==========================================
echo.
pause

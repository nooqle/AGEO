#!/bin/bash
# Playwright 浏览器内核安装脚本

echo "=========================================="
echo "Playwright 浏览器内核安装"
echo "=========================================="
echo ""

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  警告: 未检测到虚拟环境"
    echo "建议先激活虚拟环境: source venv/bin/activate"
    echo ""
    read -p "是否继续安装? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "📦 安装 Playwright 浏览器内核..."
echo ""

# 安装 Chromium (项目使用的浏览器)
python -m playwright install chromium

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Playwright 浏览器内核安装成功！"
    echo ""
    echo "已安装的浏览器:"
    echo "  - Chromium (用于 Browser Agent)"
    echo ""
    echo "如需安装其他浏览器:"
    echo "  python -m playwright install firefox"
    echo "  python -m playwright install webkit"
    echo ""
else
    echo ""
    echo "❌ 安装失败"
    echo ""
    echo "请尝试手动安装:"
    echo "  python -m playwright install chromium"
    echo ""
    exit 1
fi

# 在 Linux 上安装系统依赖
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "检测到 Linux 系统"
    read -p "是否安装系统依赖? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "安装系统依赖..."
        python -m playwright install-deps chromium
    fi
fi

echo "=========================================="
echo "安装完成！"
echo "=========================================="

"""Playwright 浏览器自动安装模块

在首次使用时自动检测并安装 Playwright 浏览器内核。
"""

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class PlaywrightInstaller:
    """Playwright 浏览器自动安装器"""

    _installation_checked = False
    _installation_lock = asyncio.Lock()

    @classmethod
    async def ensure_browser_installed(cls) -> bool:
        """确保 Playwright 浏览器已安装

        Returns:
            bool: 安装成功返回 True，失败返回 False
        """
        # 如果已经检查过，直接返回
        if cls._installation_checked:
            return True

        async with cls._installation_lock:
            # 双重检查
            if cls._installation_checked:
                return True

            try:
                # 检查浏览器是否已安装
                if await cls._check_browser_installed():
                    logger.info("[Playwright] 浏览器已安装")
                    cls._installation_checked = True
                    return True

                # 浏览器未安装，尝试自动安装
                logger.warning("[Playwright] 浏览器未安装，开始自动安装...")
                success = await cls._install_browser()

                if success:
                    logger.info("[Playwright] 浏览器安装成功")
                    cls._installation_checked = True
                    return True
                else:
                    logger.error("[Playwright] 浏览器安装失败")
                    return False

            except Exception as e:
                logger.error(f"[Playwright] 检查/安装浏览器时出错: {e}")
                return False

    @classmethod
    async def _check_browser_installed(cls) -> bool:
        """检查浏览器是否已安装"""
        try:
            # 尝试导入 playwright 并检查浏览器
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                # 尝试获取浏览器路径
                browser_type = p.chromium
                executable_path = browser_type.executable_path

                if executable_path and Path(executable_path).exists():
                    return True

            return False
        except Exception as e:
            logger.debug(f"[Playwright] 浏览器检查失败: {e}")
            return False

    @classmethod
    async def _install_browser(cls) -> bool:
        """安装 Playwright 浏览器"""
        try:
            # 运行 playwright install chromium
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "playwright",
                "install",
                "chromium",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info("[Playwright] Chromium 安装成功")
                return True
            else:
                logger.error(
                    f"[Playwright] 安装失败: {stderr.decode('utf-8', errors='ignore')}"
                )
                return False

        except Exception as e:
            logger.error(f"[Playwright] 安装过程出错: {e}")
            return False

    @classmethod
    def install_browser_sync(cls) -> bool:
        """同步方式安装浏览器（用于启动脚本）"""
        try:
            logger.info("[Playwright] 检查浏览器安装状态...")

            # 运行 playwright install chromium
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
            )

            if result.returncode == 0:
                logger.info("[Playwright] 浏览器安装/更新成功")
                return True
            else:
                logger.error(f"[Playwright] 安装失败: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("[Playwright] 安装超时")
            return False
        except Exception as e:
            logger.error(f"[Playwright] 安装出错: {e}")
            return False


# 便捷函数
async def ensure_playwright_ready() -> bool:
    """确保 Playwright 已准备就绪

    在使用 Playwright 之前调用此函数，确保浏览器已安装。

    Returns:
        bool: 准备就绪返回 True，否则返回 False

    Example:
        ```python
        from app.core.playwright_installer import ensure_playwright_ready

        async def my_function():
            if not await ensure_playwright_ready():
                raise RuntimeError("Playwright 浏览器未安装")

            # 使用 Playwright
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                # ...
        ```
    """
    return await PlaywrightInstaller.ensure_browser_installed()

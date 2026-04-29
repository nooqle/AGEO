"""Playwright 浏览器自动安装模块

在首次使用时自动检测并安装 Playwright 浏览器内核。
"""

import asyncio
import logging
import os
import platform
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
        """检查浏览器是否已安装。

        Uses file-system check instead of starting a playwright server,
        which can fail inside uvicorn's event loop.
        """
        try:
            # Method 1: Check the well-known install location directly.
            if cls._browser_executable_exists():
                return True

            # Method 2: Fallback to patchright's executable_path (sync, no server)
            try:
                from patchright.sync_api import sync_playwright
                with sync_playwright() as p:
                    exe = p.chromium.executable_path
                    if exe and Path(exe).exists():
                        return True
            except Exception as e2:
                logger.debug("[Playwright] sync_playwright fallback failed: %s", e2)

            return False
        except Exception as e:
            logger.debug(f"[Playwright] 浏览器检查失败: {e}")
            return False

    @classmethod
    def _browser_executable_exists(cls) -> bool:
        roots: list[Path] = []
        for env_name in ("PLAYWRIGHT_BROWSERS_PATH", "PATCHRIGHT_BROWSERS_PATH"):
            configured = os.getenv(env_name)
            if configured:
                roots.append(Path(configured).expanduser())

        if platform.system() == "Windows":
            roots.append(Path.home() / "AppData" / "Local" / "ms-playwright")
            executable_name = "chrome.exe"
        else:
            roots.append(Path.home() / ".cache" / "ms-playwright")
            executable_name = "chrome"

        seen: set[Path] = set()
        for root in roots:
            if root in seen:
                continue
            seen.add(root)
            if not root.exists():
                continue
            for directory in root.iterdir():
                if not directory.is_dir() or not directory.name.startswith("chromium"):
                    continue
                for exe in directory.rglob(executable_name):
                    if exe.is_file():
                        logger.debug("[Playwright] Found browser at %s", exe)
                        return True

        return False

    @classmethod
    async def _install_browser(cls) -> bool:
        """安装 Playwright 浏览器"""
        try:
            # 运行 playwright install chromium
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "patchright",
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

            if cls._browser_executable_exists():
                logger.info("[Playwright] 浏览器已安装，跳过安装")
                return True

            timeout_seconds = int(os.getenv("PLAYWRIGHT_INSTALL_TIMEOUT_SECONDS", "90"))

            # 运行 playwright install chromium
            result = subprocess.run(
                [sys.executable, "-m", "patchright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
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
            from patchright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                # ...
        ```
    """
    return await PlaywrightInstaller.ensure_browser_installed()

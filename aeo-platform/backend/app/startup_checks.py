"""应用启动前的检查和初始化

在 FastAPI 应用启动前执行必要的检查和初始化。
"""

import logging
import sys

from app.core.playwright_installer import PlaywrightInstaller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def startup_checks() -> bool:
    """执行启动前检查

    Returns:
        bool: 所有检查通过返回 True，否则返回 False
    """
    logger.info("=" * 60)
    logger.info("执行启动前检查...")
    logger.info("=" * 60)

    # 检查 1: Playwright 浏览器
    logger.info("\n[1/1] 检查 Playwright 浏览器...")
    try:
        if not PlaywrightInstaller.install_browser_sync():
            logger.error("❌ Playwright 浏览器安装失败")
            logger.error("请手动运行: python -m playwright install chromium")
            return False

        logger.info("✅ Playwright 浏览器已就绪")

    except Exception as e:
        logger.error(f"❌ Playwright 检查失败: {e}")
        return False

    # 可以在这里添加更多检查...
    # 例如: 数据库连接、环境变量、API 密钥等

    logger.info("\n" + "=" * 60)
    logger.info("✅ 所有启动检查通过")
    logger.info("=" * 60 + "\n")

    return True


if __name__ == "__main__":
    if not startup_checks():
        logger.error("启动检查失败，退出")
        sys.exit(1)

    logger.info("启动检查完成，可以启动应用")

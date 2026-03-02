"""应用启动前的检查和初始化

在 FastAPI 应用启动前执行必要的检查和初始化。
"""

import logging
import sys

from app.core.playwright_installer import PlaywrightInstaller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_WEAK_JWT_SECRET = "dev-secret-change-me"


def _check_security_config() -> None:
    """检查安全相关配置，对不安全的默认值打印明显警告。"""
    from app.core.config import settings

    if settings.JWT_SECRET == _WEAK_JWT_SECRET:
        logger.warning("=" * 60)
        logger.warning("⚠️  安全警告: JWT_SECRET 使用默认弱密钥！")
        logger.warning("   生产环境请在 .env.local 中设置强随机密钥:")
        logger.warning("   JWT_SECRET=<至少32位随机字符串>")
        logger.warning("=" * 60)

    if settings.DEV_MODE_ENABLED and not settings.DEBUG:
        logger.warning(
            "⚠️  DEV_MODE_ENABLED=True 但 DEBUG=False，开发绕过已被 DEBUG 门控关闭。"
        )


def startup_checks() -> bool:
    """执行启动前检查

    Returns:
        bool: 所有检查通过返回 True，否则返回 False
    """
    logger.info("=" * 60)
    logger.info("执行启动前检查...")
    logger.info("=" * 60)

    # 检查 0: 安全配置
    logger.info("\n[1/2] 检查安全配置...")
    _check_security_config()
    logger.info("✅ 安全配置检查完成（详见上方警告）")

    # 检查 1: Playwright 浏览器
    logger.info("\n[2/2] 检查 Playwright 浏览器...")
    try:
        if not PlaywrightInstaller.install_browser_sync():
            logger.error("❌ Playwright 浏览器安装失败")
            logger.error("请手动运行: python -m patchright install chromium")
            return False

        logger.info("✅ Playwright 浏览器已就绪")

    except Exception as e:
        logger.error(f"❌ Playwright 检查失败: {e}")
        return False

    logger.info("\n" + "=" * 60)
    logger.info("✅ 所有启动检查通过")
    logger.info("=" * 60 + "\n")

    return True


if __name__ == "__main__":
    if not startup_checks():
        logger.error("启动检查失败，退出")
        sys.exit(1)

    logger.info("启动检查完成，可以启动应用")

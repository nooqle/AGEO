from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.models.verification_challenge import VerificationChannel, VerificationPurpose

logger = logging.getLogger(__name__)


class VerificationDeliveryError(RuntimeError):
    """Raised when verification delivery cannot be completed."""


class BaseEmailVerificationProvider:
    async def send_code(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        raise NotImplementedError


class BaseSmsVerificationProvider:
    async def send_code(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        raise NotImplementedError


class ConsoleEmailVerificationProvider(BaseEmailVerificationProvider):
    async def send_code(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        logger.info(
            "[Verification][Email][Console] purpose=%s target=%s code=%s expires_in=%sm",
            purpose.value,
            target,
            code,
            expires_in_minutes,
        )


class SmtpEmailVerificationProvider(BaseEmailVerificationProvider):
    def _build_message(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> EmailMessage:
        from_address = settings.VERIFICATION_EMAIL_FROM_ADDRESS
        if not from_address:
            raise VerificationDeliveryError("未配置邮件发件地址")

        subject_map = {
            VerificationPurpose.REGISTRATION: "注册验证码",
            VerificationPurpose.LOGIN: "登录验证码",
            VerificationPurpose.BIND_EMAIL: "邮箱换绑验证码",
            VerificationPurpose.BIND_PHONE: "手机号换绑验证码",
        }
        action_map = {
            VerificationPurpose.REGISTRATION: "提交注册申请",
            VerificationPurpose.LOGIN: "登录 Specta AI",
            VerificationPurpose.BIND_EMAIL: "换绑邮箱",
            VerificationPurpose.BIND_PHONE: "换绑手机号",
        }
        subject = (
            f"{settings.VERIFICATION_EMAIL_SUBJECT_PREFIX}"
            f"{subject_map.get(purpose, '验证码')}"
        )
        body = "\n".join(
            [
                "你好，",
                "",
                f"你正在进行：{action_map.get(purpose, '账号验证')}",
                f"验证码：{code}",
                f"有效期：{expires_in_minutes} 分钟",
                "",
                "如果这不是你的操作，请忽略本邮件。",
                "",
                "Specta AI",
            ]
        )

        message = EmailMessage()
        display_name = settings.VERIFICATION_EMAIL_FROM_NAME.strip()
        if display_name:
            message["From"] = f"{display_name} <{from_address}>"
        else:
            message["From"] = from_address
        message["To"] = target
        message["Subject"] = subject
        message.set_content(body)
        return message

    def _send_sync(self, message: EmailMessage) -> None:
        host = settings.VERIFICATION_SMTP_HOST
        if not host:
            raise VerificationDeliveryError("未配置 SMTP 主机")
        port = settings.VERIFICATION_SMTP_PORT
        username = settings.VERIFICATION_SMTP_USERNAME
        password = settings.VERIFICATION_SMTP_PASSWORD
        use_ssl = settings.VERIFICATION_SMTP_USE_SSL
        use_tls = settings.VERIFICATION_SMTP_USE_TLS

        try:
            if use_ssl:
                server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=20)
            else:
                server = smtplib.SMTP(host, port, timeout=20)
            with server:
                if not use_ssl and use_tls:
                    server.starttls()
                if username:
                    server.login(username, password or "")
                server.send_message(message)
        except Exception as exc:  # pragma: no cover - network/provider errors
            raise VerificationDeliveryError(f"邮件发送失败: {exc}") from exc

    async def send_code(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        message = self._build_message(
            target=target,
            purpose=purpose,
            code=code,
            expires_in_minutes=expires_in_minutes,
        )
        await asyncio.to_thread(self._send_sync, message)


class ConsoleSmsVerificationProvider(BaseSmsVerificationProvider):
    async def send_code(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        logger.info(
            "[Verification][SMS][Console] purpose=%s target=%s code=%s expires_in=%sm",
            purpose.value,
            target,
            code,
            expires_in_minutes,
        )


class DisabledSmsVerificationProvider(BaseSmsVerificationProvider):
    async def send_code(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        raise VerificationDeliveryError(
            "当前环境未配置短信验证码服务，请先使用邮箱验证码或联系管理员"
        )


class VerificationDeliveryService:
    def __init__(self) -> None:
        email_provider = settings.VERIFICATION_EMAIL_PROVIDER.strip().lower()
        sms_provider = settings.VERIFICATION_SMS_PROVIDER.strip().lower()

        if email_provider == "smtp":
            self.email_provider: BaseEmailVerificationProvider = (
                SmtpEmailVerificationProvider()
            )
        else:
            self.email_provider = ConsoleEmailVerificationProvider()

        if sms_provider == "disabled":
            self.sms_provider: BaseSmsVerificationProvider = (
                DisabledSmsVerificationProvider()
            )
        else:
            self.sms_provider = ConsoleSmsVerificationProvider()

    async def send_code(
        self,
        *,
        channel: VerificationChannel,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        if channel == VerificationChannel.EMAIL:
            await self.email_provider.send_code(
                target=target,
                purpose=purpose,
                code=code,
                expires_in_minutes=expires_in_minutes,
            )
            return
        if channel == VerificationChannel.PHONE:
            await self.sms_provider.send_code(
                target=target,
                purpose=purpose,
                code=code,
                expires_in_minutes=expires_in_minutes,
            )
            return
        raise VerificationDeliveryError(f"不支持的验证码渠道: {channel}")

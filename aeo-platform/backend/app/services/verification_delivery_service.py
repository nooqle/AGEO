from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import time
from email.message import EmailMessage

from app.core.config import settings
from app.models.verification_challenge import VerificationChannel, VerificationPurpose

logger = logging.getLogger(__name__)


class VerificationDeliveryError(RuntimeError):
    """Raised when verification delivery cannot be completed."""


def _build_subject(purpose: VerificationPurpose) -> str:
    subject_map = {
        VerificationPurpose.REGISTRATION: "注册验证码",
        VerificationPurpose.LOGIN: "登录验证码",
        VerificationPurpose.INVITE_ACCESS: "邀请码",
        VerificationPurpose.BIND_EMAIL: "邮箱换绑验证码",
        VerificationPurpose.BIND_PHONE: "手机号换绑验证码",
    }
    return (
        f"{settings.VERIFICATION_EMAIL_SUBJECT_PREFIX}"
        f"{subject_map.get(purpose, '验证码')}"
    )


def _build_action(purpose: VerificationPurpose) -> str:
    action_map = {
        VerificationPurpose.REGISTRATION: "完成邮箱验证",
        VerificationPurpose.LOGIN: "登录 Specta AI",
        VerificationPurpose.INVITE_ACCESS: "完成邀请码验证并进入 Specta AI",
        VerificationPurpose.BIND_EMAIL: "换绑邮箱",
        VerificationPurpose.BIND_PHONE: "换绑手机号",
    }
    return action_map.get(purpose, "账号验证")


def _sanitize_optional_env(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized in {"...", "…", "可空", "... 可空"}:
        return None
    return normalized


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

        subject = _build_subject(purpose)
        body = "\n".join(
            [
                "你好，",
                "",
                f"你正在进行：{_build_action(purpose)}",
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
        username = settings.VERIFICATION_SMTP_USERNAME or settings.VERIFICATION_EMAIL_FROM_ADDRESS
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


class TencentSesApiEmailVerificationProvider(BaseEmailVerificationProvider):
    def __init__(self) -> None:
        self._template_status: dict[int, int] = {}
        self._template_status_checked_at: dict[int, float] = {}

    def _resolve_template_config(
        self,
        purpose: VerificationPurpose,
    ) -> tuple[int | None, str]:
        if purpose == VerificationPurpose.INVITE_ACCESS:
            return (
                settings.TENCENT_SES_INVITE_CODE_TEMPLATE_ID,
                settings.TENCENT_SES_INVITE_CODE_TEMPLATE_VARIABLES,
            )
        return (
            settings.TENCENT_SES_TEMPLATE_ID,
            settings.TENCENT_SES_TEMPLATE_VARIABLES,
        )

    def _build_template_data(
        self,
        *,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
        template_variables: str,
    ) -> str:
        variables = [
            item.strip() for item in template_variables.split(",") if item.strip()
        ]
        if not variables:
            variables = ["code"]

        data: dict[str, str] = {}
        for key in variables:
            if key == "code":
                data[key] = code
            elif key == "expire_minutes":
                data[key] = str(expires_in_minutes)
            elif key == "action":
                data[key] = _build_action(purpose)
            elif key == "login_url":
                data[key] = settings.APP_LOGIN_URL
            else:
                raise VerificationDeliveryError(
                    f"腾讯云 SES 模板变量 {key} 当前未实现映射"
                )
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _build_client():
        secret_id = _sanitize_optional_env(settings.TENCENT_SES_SECRET_ID)
        secret_key = _sanitize_optional_env(settings.TENCENT_SES_SECRET_KEY)
        if not secret_id or not secret_key:
            raise VerificationDeliveryError("未配置腾讯云 SES SecretId / SecretKey")

        try:
            from tencentcloud.common import credential
            from tencentcloud.ses.v20201002 import ses_client
        except Exception as exc:
            raise VerificationDeliveryError(
                "缺少腾讯云 SDK，请先安装 tencentcloud-sdk-python"
            ) from exc

        cred = credential.Credential(secret_id, secret_key)
        return ses_client.SesClient(cred, settings.TENCENT_SES_REGION)

    def _fetch_template_status_sync(self, client, template_id: int) -> int | None:
        try:
            from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
                TencentCloudSDKException,
            )
            from tencentcloud.ses.v20201002 import models
        except Exception:
            return None

        try:
            request = models.GetEmailTemplateRequest()
            request.TemplateID = template_id
            response = client.GetEmailTemplate(request)
            status = getattr(response, "TemplateStatus", None)
            if isinstance(status, int):
                return status
        except TencentCloudSDKException:
            return None
        except Exception:
            return None
        return None

    def _ensure_template_ready_sync(self, client, template_id: int) -> None:
        now = time.time()
        cached_status = self._template_status.get(template_id)
        ttl_seconds = 300 if cached_status == 0 else 30
        if (
            template_id in self._template_status
            and now - self._template_status_checked_at.get(template_id, 0) < ttl_seconds
        ):
            status = cached_status
        else:
            status = self._fetch_template_status_sync(client, template_id)
            if status is not None:
                self._template_status[template_id] = status
                self._template_status_checked_at[template_id] = now

        if status == 1:
            raise VerificationDeliveryError("腾讯云 SES 模板仍在审核中，暂不可发送验证码邮件")
        if status == 2:
            raise VerificationDeliveryError("腾讯云 SES 模板审核未通过，请先修正模板后重试")

    def _send_sync(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        secret_id = _sanitize_optional_env(settings.TENCENT_SES_SECRET_ID)
        secret_key = _sanitize_optional_env(settings.TENCENT_SES_SECRET_KEY)
        from_email = _sanitize_optional_env(settings.TENCENT_SES_FROM_EMAIL_ADDRESS)
        template_id, template_variables = self._resolve_template_config(purpose)

        if not secret_id or not secret_key:
            raise VerificationDeliveryError("未配置腾讯云 SES SecretId / SecretKey")
        if not from_email:
            raise VerificationDeliveryError("未配置腾讯云 SES 发件地址")
        if not template_id:
            if purpose == VerificationPurpose.INVITE_ACCESS:
                raise VerificationDeliveryError("未配置腾讯云 SES 邀请码模板 ID")
            raise VerificationDeliveryError("未配置腾讯云 SES TemplateID")

        try:
            from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
                TencentCloudSDKException,
            )
            from tencentcloud.ses.v20201002 import models

            client = self._build_client()
            self._ensure_template_ready_sync(client, template_id)
            request = models.SendEmailRequest()
            request.FromEmailAddress = from_email
            request.Subject = _build_subject(purpose)
            request.Destination = [target]

            reply_to = _sanitize_optional_env(settings.TENCENT_SES_REPLY_TO_ADDRESS)
            if reply_to:
                request.ReplyToAddresses = reply_to

            template = models.Template()
            template.TemplateID = template_id
            template.TemplateData = self._build_template_data(
                purpose=purpose,
                code=code,
                expires_in_minutes=expires_in_minutes,
                template_variables=template_variables,
            )
            request.Template = template
            request.TriggerType = 1

            client.SendEmail(request)
        except TencentCloudSDKException as exc:
            template_status = self._fetch_template_status_sync(client, template_id)
            if template_status == 1:
                raise VerificationDeliveryError(
                    "腾讯云 SES 模板仍在审核中，暂不可发送验证码邮件"
                ) from exc
            if template_status == 2:
                raise VerificationDeliveryError(
                    "腾讯云 SES 模板审核未通过，请先修正模板后重试"
                ) from exc
            raise VerificationDeliveryError(f"腾讯云 SES 发送失败: {exc}") from exc
        except VerificationDeliveryError:
            raise
        except Exception as exc:
            raise VerificationDeliveryError(f"腾讯云 SES 调用失败: {exc}") from exc

    async def send_code(
        self,
        *,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        expires_in_minutes: int,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._send_sync,
                target=target,
                purpose=purpose,
                code=code,
                expires_in_minutes=expires_in_minutes,
            )
        except VerificationDeliveryError as exc:
            if purpose == VerificationPurpose.INVITE_ACCESS and (
                settings.DEBUG or settings.DEV_MODE_ENABLED
            ):
                logger.warning(
                    "[Verification][Email][Fallback] invite_access target=%s code=%s reason=%s",
                    target,
                    code,
                    exc,
                )
                return
            raise


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
        elif email_provider == "tencent_ses_api":
            self.email_provider = TencentSesApiEmailVerificationProvider()
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

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import time
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


class AccountNotificationError(RuntimeError):
    """Raised when account notification delivery cannot be completed."""


def _sanitize_optional_env(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized in {"...", "…", "可空", "... 可空"}:
        return None
    return normalized


def _build_approval_subject() -> str:
    return f"{settings.ACCOUNT_APPROVAL_EMAIL_SUBJECT_PREFIX}账号已开通"


def _build_approval_body(*, email: str, organization_name: str | None) -> str:
    lines = [
        "你好，",
        "",
        "你的 Specta AI 体验账号已审核通过，可以重新登录平台开始使用。",
    ]
    if organization_name:
        lines.append(f"归属组织：{organization_name}")
    lines.extend(
        [
            f"登录入口：{settings.APP_LOGIN_URL}",
            "",
            f"登录邮箱：{email}",
            "",
            "如果这不是你的申请，请忽略本邮件。",
            "",
            "Specta AI",
        ]
    )
    return "\n".join(lines)


class _ConsoleAccountNotificationProvider:
    async def send_approval_email(
        self,
        *,
        email: str,
        organization_name: str | None,
    ) -> None:
        logger.info(
            "[AccountNotification][Console] email=%s organization=%s login_url=%s",
            email,
            organization_name or "",
            settings.APP_LOGIN_URL,
        )


class _SmtpAccountNotificationProvider:
    def _build_message(
        self,
        *,
        email: str,
        organization_name: str | None,
    ) -> EmailMessage:
        from_address = settings.VERIFICATION_EMAIL_FROM_ADDRESS
        if not from_address:
            raise AccountNotificationError("未配置邮件发件地址")

        message = EmailMessage()
        display_name = settings.VERIFICATION_EMAIL_FROM_NAME.strip()
        if display_name:
            message["From"] = f"{display_name} <{from_address}>"
        else:
            message["From"] = from_address
        message["To"] = email
        message["Subject"] = _build_approval_subject()
        message.set_content(
            _build_approval_body(
                email=email,
                organization_name=organization_name,
            )
        )
        return message

    def _send_sync(self, message: EmailMessage) -> None:
        host = settings.VERIFICATION_SMTP_HOST
        if not host:
            raise AccountNotificationError("未配置 SMTP 主机")
        port = settings.VERIFICATION_SMTP_PORT
        username = (
            settings.VERIFICATION_SMTP_USERNAME
            or settings.VERIFICATION_EMAIL_FROM_ADDRESS
        )
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
        except Exception as exc:  # pragma: no cover - provider/network error
            raise AccountNotificationError(f"邮件发送失败: {exc}") from exc

    async def send_approval_email(
        self,
        *,
        email: str,
        organization_name: str | None,
    ) -> None:
        message = self._build_message(
            email=email,
            organization_name=organization_name,
        )
        await asyncio.to_thread(self._send_sync, message)


class _TencentSesAccountNotificationProvider:
    def __init__(self) -> None:
        self._template_status: int | None = None
        self._template_status_checked_at: float = 0.0

    def _build_template_data(
        self,
        *,
        email: str,
        organization_name: str | None,
    ) -> str:
        variables = [
            item.strip()
            for item in settings.TENCENT_SES_ACCOUNT_APPROVAL_TEMPLATE_VARIABLES.split(
                ","
            )
            if item.strip()
        ]
        if not variables:
            variables = ["email", "organization_name", "login_url"]

        data: dict[str, str] = {}
        for key in variables:
            if key == "email":
                data[key] = email
            elif key == "organization_name":
                data[key] = organization_name or ""
            elif key == "login_url":
                data[key] = settings.APP_LOGIN_URL
            else:
                raise AccountNotificationError(
                    f"腾讯云 SES 开通通知模板变量 {key} 当前未实现映射"
                )
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _build_client():
        secret_id = _sanitize_optional_env(settings.TENCENT_SES_SECRET_ID)
        secret_key = _sanitize_optional_env(settings.TENCENT_SES_SECRET_KEY)
        if not secret_id or not secret_key:
            raise AccountNotificationError("未配置腾讯云 SES SecretId / SecretKey")

        try:
            from tencentcloud.common import credential
            from tencentcloud.ses.v20201002 import ses_client
        except Exception as exc:  # pragma: no cover - dependency error
            raise AccountNotificationError(
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
        ttl_seconds = 300 if self._template_status == 0 else 30
        if (
            self._template_status is not None
            and now - self._template_status_checked_at < ttl_seconds
        ):
            status = self._template_status
        else:
            status = self._fetch_template_status_sync(client, template_id)
            if status is not None:
                self._template_status = status
                self._template_status_checked_at = now

        if status == 1:
            raise AccountNotificationError(
                "腾讯云 SES 开通通知模板仍在审核中，暂不可发送通知邮件"
            )
        if status == 2:
            raise AccountNotificationError(
                "腾讯云 SES 开通通知模板审核未通过，请先修正模板后重试"
            )

    def _send_sync(
        self,
        *,
        email: str,
        organization_name: str | None,
    ) -> None:
        from_email = _sanitize_optional_env(settings.TENCENT_SES_FROM_EMAIL_ADDRESS)
        template_id = settings.TENCENT_SES_ACCOUNT_APPROVAL_TEMPLATE_ID

        if not from_email:
            raise AccountNotificationError("未配置腾讯云 SES 发件地址")
        if not template_id:
            raise AccountNotificationError("未配置腾讯云 SES 开通通知模板 ID")

        try:
            from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
                TencentCloudSDKException,
            )
            from tencentcloud.ses.v20201002 import models

            client = self._build_client()
            self._ensure_template_ready_sync(client, template_id)

            request = models.SendEmailRequest()
            request.FromEmailAddress = from_email
            request.Subject = _build_approval_subject()
            request.Destination = [email]

            reply_to = _sanitize_optional_env(settings.TENCENT_SES_REPLY_TO_ADDRESS)
            if reply_to:
                request.ReplyToAddresses = reply_to

            template = models.Template()
            template.TemplateID = template_id
            template.TemplateData = self._build_template_data(
                email=email,
                organization_name=organization_name,
            )
            request.Template = template
            request.TriggerType = 1
            client.SendEmail(request)
        except TencentCloudSDKException as exc:
            raise AccountNotificationError(f"腾讯云 SES 发送失败: {exc}") from exc
        except AccountNotificationError:
            raise
        except Exception as exc:
            raise AccountNotificationError(f"腾讯云 SES 调用失败: {exc}") from exc

    async def send_approval_email(
        self,
        *,
        email: str,
        organization_name: str | None,
    ) -> None:
        await asyncio.to_thread(
            self._send_sync,
            email=email,
            organization_name=organization_name,
        )


class AccountNotificationService:
    def __init__(self) -> None:
        provider_name = settings.VERIFICATION_EMAIL_PROVIDER.strip().lower()
        if provider_name == "smtp":
            self.email_provider = _SmtpAccountNotificationProvider()
        elif provider_name == "tencent_ses_api":
            self.email_provider = _TencentSesAccountNotificationProvider()
        else:
            self.email_provider = _ConsoleAccountNotificationProvider()

    async def send_approval_email(
        self,
        *,
        email: str,
        organization_name: str | None,
    ) -> None:
        await self.email_provider.send_approval_email(
            email=email,
            organization_name=organization_name,
        )

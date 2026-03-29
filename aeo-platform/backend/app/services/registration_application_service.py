from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.registration_application import (
    RegistrationApplication,
    RegistrationApplicationStatus,
)
from app.models.user import User, UserRole, UserStatus
from app.models.verification_challenge import VerificationChannel, VerificationPurpose
from app.services.account_notification_service import (
    AccountNotificationError,
    AccountNotificationService,
)
from app.services.identity_normalization_service import normalize_email, normalize_phone
from app.services.user_service import UserService
from app.services.verification_service import VerificationService

WAITLIST_PLACEHOLDER_ORGANIZATION = "待分配组织"
WAITLIST_PLACEHOLDER_JOB_TITLE = "待补充"
logger = logging.getLogger(__name__)


class RegistrationApplicationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.verification = VerificationService(db)
        self.users = UserService(db)
        self.notifications = AccountNotificationService()

    async def create_application(
        self,
        *,
        email: str | None,
        phone: str | None,
        verification_channel: VerificationChannel,
        verification_target: str,
        verification_code: str,
        organization_name: str,
        job_title: str,
        applicant_name: str | None = None,
        company_size: str | None = None,
        is_agency: bool = False,
    ) -> RegistrationApplication:
        normalized_email = normalize_email(email)
        normalized_phone = normalize_phone(phone)
        purpose = VerificationPurpose.REGISTRATION
        verified = await self.verification.verify_code(
            channel=verification_channel,
            target=verification_target,
            purpose=purpose,
            code=verification_code,
            consume=True,
        )
        if verified is None:
            raise ValueError("验证码无效或已过期")

        if normalized_email:
            existing = await self.users.get_user_by_email(normalized_email)
            if existing is not None:
                raise ValueError("该邮箱已注册")
        if normalized_phone:
            existing = await self.users.get_user_by_phone(normalized_phone)
            if existing is not None:
                raise ValueError("该手机号已注册")
        existing_application = await self.get_latest_application_by_identity(
            channel=verification_channel,
            target=verification_target,
        )
        if (
            existing_application is not None
            and existing_application.status == RegistrationApplicationStatus.APPROVED
        ):
            raise ValueError("该邮箱已开通，可直接登录")

        if existing_application is not None:
            application = existing_application
            application.status = RegistrationApplicationStatus.PENDING_REVIEW
            application.review_note = None
            application.reviewed_at = None
            application.reviewed_by_user_id = None
            application.approved_user_id = None
            application.invite_code_sent_at = None
            application.invite_code_issued_by_user_id = None
            application.invite_redeemed_at = None
            application.assigned_organization_id = None
        else:
            application = RegistrationApplication(
                email=normalized_email,
                phone=normalized_phone,
                organization_name=organization_name.strip(),
                job_title=job_title.strip(),
                applicant_name=applicant_name.strip() if applicant_name else None,
            )
            self.db.add(application)

        application.email = normalized_email
        application.phone = normalized_phone
        application.organization_name = organization_name.strip()
        application.job_title = job_title.strip()
        application.applicant_name = (
            applicant_name.strip() if applicant_name else None
        )
        application.company_size = company_size.strip() if company_size else None
        application.is_agency = is_agency
        await self.db.commit()
        await self.db.refresh(application)
        return application

    async def create_waitlist_application(
        self,
        *,
        channel: VerificationChannel,
        target: str,
    ) -> RegistrationApplication:
        normalized_email = (
            normalize_email(target) if channel == VerificationChannel.EMAIL else None
        )
        normalized_phone = (
            normalize_phone(target) if channel == VerificationChannel.PHONE else None
        )
        if not normalized_email and not normalized_phone:
            raise ValueError("缺少可用的注册身份")

        if normalized_email:
            existing = await self.users.get_user_by_email(normalized_email)
            if existing is not None:
                raise ValueError("该邮箱已注册")
        if normalized_phone:
            existing = await self.users.get_user_by_phone(normalized_phone)
            if existing is not None:
                raise ValueError("该手机号已注册")

        existing_pending = await self.get_pending_application(
            email=normalized_email,
            phone=normalized_phone,
        )
        if existing_pending is not None:
            return existing_pending

        application = RegistrationApplication(
            email=normalized_email,
            phone=normalized_phone,
            organization_name=WAITLIST_PLACEHOLDER_ORGANIZATION,
            job_title=WAITLIST_PLACEHOLDER_JOB_TITLE,
            applicant_name=None,
        )
        self.db.add(application)
        await self.db.commit()
        await self.db.refresh(application)
        return application

    async def get_pending_application(
        self,
        *,
        email: str | None = None,
        phone: str | None = None,
    ) -> RegistrationApplication | None:
        email = normalize_email(email)
        phone = normalize_phone(phone)
        filters = []
        if email:
            filters.append(RegistrationApplication.email == email)
        if phone:
            filters.append(RegistrationApplication.phone == phone)
        if not filters:
            return None

        result = await self.db.execute(
            select(RegistrationApplication)
            .where(
                RegistrationApplication.status
                == RegistrationApplicationStatus.PENDING_REVIEW,
                or_(*filters),
            )
            .order_by(RegistrationApplication.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_application_by_identity(
        self,
        *,
        channel: VerificationChannel,
        target: str,
    ) -> RegistrationApplication | None:
        target = (
            normalize_email(target)
            if channel == VerificationChannel.EMAIL
            else normalize_phone(target)
        )
        if not target:
            return None
        condition = (
            RegistrationApplication.email == target
            if channel == VerificationChannel.EMAIL
            else RegistrationApplication.phone == target
        )
        result = await self.db.execute(
            select(RegistrationApplication)
            .where(condition)
            .order_by(RegistrationApplication.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_applications(self) -> list[RegistrationApplication]:
        result = await self.db.execute(
            select(RegistrationApplication).order_by(
                RegistrationApplication.created_at.desc()
            )
        )
        return list(result.scalars().all())

    async def get_application(
        self, application_id: UUID
    ) -> RegistrationApplication | None:
        result = await self.db.execute(
            select(RegistrationApplication).where(
                RegistrationApplication.id == application_id
            )
        )
        return result.scalar_one_or_none()

    async def approve_application(
        self,
        *,
        application_id: UUID,
        reviewer_user_id: UUID,
        organization_id: UUID | None = None,
    ) -> RegistrationApplication:
        application = await self.get_application(application_id)
        if application is None:
            raise ValueError("申请不存在")
        if application.status != RegistrationApplicationStatus.PENDING_REVIEW:
            raise ValueError("申请已处理")

        if application.email:
            existing = await self.users.get_user_by_email(application.email)
            if existing is not None:
                raise ValueError("该邮箱已被其他账号占用")
        if application.phone:
            existing = await self.users.get_user_by_phone(application.phone)
            if existing is not None:
                raise ValueError("该手机号已被其他账号占用")

        organization = await self._resolve_organization_for_approval(
            organization_id=organization_id,
            legal_name=application.organization_name,
            fallback_legal_name=self._build_waitlist_organization_name(application),
        )
        user = User(
            email=application.email,
            phone=application.phone,
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
            job_title=application.job_title,
            organization_id=organization.id,
        )
        self.db.add(user)
        await self.db.flush()

        application.status = RegistrationApplicationStatus.APPROVED
        application.organization_name = organization.legal_name
        application.reviewed_by_user_id = reviewer_user_id
        application.approved_user_id = user.id
        application.reviewed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(application)
        if application.email:
            try:
                await self.notifications.send_approval_email(
                    email=application.email,
                    organization_name=organization.legal_name,
                )
            except AccountNotificationError as exc:
                logger.warning("发送账号开通通知失败: %s", exc)
        return application

    async def issue_invite_code(
        self,
        *,
        application_id: UUID,
        reviewer_user_id: UUID,
        organization_id: UUID | None = None,
    ) -> RegistrationApplication:
        application = await self.get_application(application_id)
        if application is None:
            raise ValueError("申请不存在")
        if application.status != RegistrationApplicationStatus.PENDING_REVIEW:
            raise ValueError("该申请已不可再次发放邀请码")
        if not application.email:
            raise ValueError("当前申请缺少邮箱，无法发放邀请码")

        assigned_organization = await self._resolve_assigned_organization_for_invite(
            organization_id=organization_id,
            legal_name=application.organization_name,
        )

        await self.verification.send_code(
            channel=VerificationChannel.EMAIL,
            target=application.email,
            purpose=VerificationPurpose.INVITE_ACCESS,
        )

        now = datetime.now(timezone.utc)
        application.assigned_organization_id = (
            assigned_organization.id if assigned_organization else None
        )
        application.invite_code_sent_at = now
        application.invite_code_issued_by_user_id = reviewer_user_id
        application.reviewed_by_user_id = reviewer_user_id
        application.reviewed_at = now
        await self.db.commit()
        await self.db.refresh(application)
        return application

    async def redeem_invite_code(
        self,
        *,
        email: str,
        invite_code: str,
    ) -> tuple[RegistrationApplication, User]:
        normalized_email = normalize_email(email)
        if not normalized_email:
            raise ValueError("请输入有效的邮箱地址")

        application = await self.get_latest_application_by_identity(
            channel=VerificationChannel.EMAIL,
            target=normalized_email,
        )
        if application is None:
            raise ValueError("未找到对应的登记信息，请先完成公司信息登记")
        if application.status == RegistrationApplicationStatus.REJECTED:
            raise ValueError("该登记已被停用，请联系管理员")
        if application.invite_code_sent_at is None:
            raise ValueError("该邮箱尚未获得邀请码，请等待邮件通知")

        verified = await self.verification.verify_code(
            channel=VerificationChannel.EMAIL,
            target=normalized_email,
            purpose=VerificationPurpose.INVITE_ACCESS,
            code=invite_code.strip(),
            consume=True,
        )
        if verified is None:
            raise ValueError("邀请码无效或已过期")

        existing_user = await self.users.get_user_by_email(normalized_email)
        if existing_user is not None:
            if existing_user.is_active and existing_user.status == UserStatus.ACTIVE:
                raise ValueError("账号已开通，请直接使用邮箱验证码登录")
            raise ValueError("当前账号状态异常，请联系管理员")

        organization = await self._resolve_organization_for_invite_redeem(application)
        user = User(
            email=application.email,
            phone=application.phone,
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
            job_title=application.job_title,
            organization_id=organization.id,
        )
        self.db.add(user)
        await self.db.flush()

        now = datetime.now(timezone.utc)
        application.status = RegistrationApplicationStatus.APPROVED
        application.organization_name = organization.legal_name
        application.approved_user_id = user.id
        application.invite_redeemed_at = now
        application.reviewed_at = now

        await self.db.commit()
        await self.db.refresh(application)
        await self.db.refresh(user)
        return application, user

    async def reject_application(
        self,
        *,
        application_id: UUID,
        reviewer_user_id: UUID,
        review_note: str | None = None,
    ) -> RegistrationApplication:
        application = await self.get_application(application_id)
        if application is None:
            raise ValueError("申请不存在")
        if application.status != RegistrationApplicationStatus.PENDING_REVIEW:
            raise ValueError("申请已处理")

        application.status = RegistrationApplicationStatus.REJECTED
        application.reviewed_by_user_id = reviewer_user_id
        application.reviewed_at = datetime.now(timezone.utc)
        application.review_note = review_note.strip() if review_note else None
        await self.db.commit()
        await self.db.refresh(application)
        return application

    async def _resolve_organization_for_approval(
        self,
        *,
        organization_id: UUID | None,
        legal_name: str,
        fallback_legal_name: str | None = None,
    ) -> Organization:
        resolved_legal_name = legal_name.strip()
        if (
            organization_id is None
            and resolved_legal_name == WAITLIST_PLACEHOLDER_ORGANIZATION
        ):
            resolved_legal_name = (
                fallback_legal_name or WAITLIST_PLACEHOLDER_ORGANIZATION
            ).strip()
        if organization_id is not None:
            result = await self.db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
            organization = result.scalar_one_or_none()
            if organization is None:
                raise ValueError("指定的组织不存在")
            return organization

        result = await self.db.execute(
            select(Organization).where(Organization.legal_name == resolved_legal_name)
        )
        organization = result.scalar_one_or_none()
        if organization is not None:
            raise ValueError("已存在同名组织，请在后台明确选择归属组织后再开通")

        organization = Organization(legal_name=resolved_legal_name)
        self.db.add(organization)
        await self.db.flush()
        return organization

    async def _resolve_assigned_organization_for_invite(
        self,
        *,
        organization_id: UUID | None,
        legal_name: str,
    ) -> Organization | None:
        if organization_id is not None:
            result = await self.db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
            organization = result.scalar_one_or_none()
            if organization is None:
                raise ValueError("指定的组织不存在")
            return organization

        resolved_legal_name = legal_name.strip()
        if not resolved_legal_name or resolved_legal_name == WAITLIST_PLACEHOLDER_ORGANIZATION:
            return None

        result = await self.db.execute(
            select(Organization).where(Organization.legal_name == resolved_legal_name)
        )
        organization = result.scalar_one_or_none()
        if organization is not None:
            return organization

        organization = Organization(legal_name=resolved_legal_name)
        self.db.add(organization)
        await self.db.flush()
        return organization

    async def _resolve_organization_for_invite_redeem(
        self,
        application: RegistrationApplication,
    ) -> Organization:
        if application.assigned_organization_id is not None:
            result = await self.db.execute(
                select(Organization).where(
                    Organization.id == application.assigned_organization_id
                )
            )
            organization = result.scalar_one_or_none()
            if organization is not None:
                return organization

        resolved_legal_name = application.organization_name.strip()
        result = await self.db.execute(
            select(Organization).where(Organization.legal_name == resolved_legal_name)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        organization = Organization(legal_name=resolved_legal_name)
        self.db.add(organization)
        await self.db.flush()
        return organization

    @staticmethod
    def _build_waitlist_organization_name(
        application: RegistrationApplication,
    ) -> str | None:
        if application.email:
            local_part = application.email.split("@", 1)[0].strip()
            if local_part:
                return f"{local_part} 的工作区"
        if application.phone:
            suffix = application.phone[-4:]
            return f"手机号尾号 {suffix} 工作区"
        return None

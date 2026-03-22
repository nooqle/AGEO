from __future__ import annotations

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
from app.services.user_service import UserService
from app.services.verification_service import VerificationService


class RegistrationApplicationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.verification = VerificationService(db)
        self.users = UserService(db)

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
    ) -> RegistrationApplication:
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

        if email:
            existing = await self.users.get_user_by_email(email)
            if existing is not None:
                raise ValueError("该邮箱已注册")
        if phone:
            existing = await self.users.get_user_by_phone(phone)
            if existing is not None:
                raise ValueError("该手机号已注册")
        duplicate_application = await self.get_pending_application(
            email=email,
            phone=phone,
        )
        if duplicate_application is not None:
            raise ValueError("已存在待审核申请，请勿重复提交")

        application = RegistrationApplication(
            email=email,
            phone=phone,
            organization_name=organization_name.strip(),
            job_title=job_title.strip(),
            applicant_name=applicant_name.strip() if applicant_name else None,
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
            target.strip().lower()
            if channel == VerificationChannel.EMAIL
            else target.strip()
        )
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
        application.reviewed_by_user_id = reviewer_user_id
        application.approved_user_id = user.id
        application.reviewed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(application)
        return application

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
    ) -> Organization:
        if organization_id is not None:
            result = await self.db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
            organization = result.scalar_one_or_none()
            if organization is None:
                raise ValueError("指定的组织不存在")
            return organization

        result = await self.db.execute(
            select(Organization).where(Organization.legal_name == legal_name)
        )
        organization = result.scalar_one_or_none()
        if organization is not None:
            raise ValueError("已存在同名组织，请在后台明确选择归属组织后再开通")

        organization = Organization(legal_name=legal_name)
        self.db.add(organization)
        await self.db.flush()
        return organization

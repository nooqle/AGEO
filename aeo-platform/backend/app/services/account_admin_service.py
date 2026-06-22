from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.organization import Organization, OrganizationStatus
from app.models.registration_application import (
    RegistrationApplication,
    RegistrationApplicationStatus,
)
from app.models.user import User, UserRole, UserStatus
from app.models.verification_challenge import VerificationChannel, VerificationPurpose
from app.services.identity_normalization_service import normalize_email, normalize_phone
from app.services.organization_feature_service import (
    FEATURE_AMWAYCHINA_CONSOLE,
    ensure_amwaychina_console_entity,
    normalize_organization_feature_flags,
    normalize_user_feature_flags,
    organization_feature_enabled,
    user_feature_enabled,
)
from app.services.verification_service import VerificationService


class AccountAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_users(self) -> list[User]:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.organization))
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_user(self, user_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.organization))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_user(
        self,
        *,
        user_id: UUID,
        changes: dict[str, object | None],
    ) -> User:
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError("用户不存在")

        if "email" in changes:
            normalized_email = normalize_email(
                str(changes["email"]) if changes["email"] is not None else None
            )
            if normalized_email:
                result = await self.db.execute(
                    select(User).where(
                        User.email == normalized_email,
                        User.id != user.id,
                    )
                )
                if result.scalar_one_or_none() is not None:
                    raise ValueError("该邮箱已被其他账号占用")
            user.email = normalized_email

        if "phone" in changes:
            normalized_phone = normalize_phone(
                str(changes["phone"]) if changes["phone"] is not None else None
            )
            if normalized_phone:
                result = await self.db.execute(
                    select(User).where(
                        User.phone == normalized_phone,
                        User.id != user.id,
                    )
                )
                if result.scalar_one_or_none() is not None:
                    raise ValueError("该手机号已被其他账号占用")
            user.phone = normalized_phone

        if (
            ("email" in changes or "phone" in changes)
            and not user.email
            and not user.phone
        ):
            raise ValueError("邮箱和手机号至少保留一项，账号才可登录")

        if "job_title" in changes:
            job_title = changes["job_title"]
            user.job_title = str(job_title).strip() if job_title else None

        if "organization_id" in changes:
            organization_id = changes["organization_id"]
            if organization_id:
                organization = await self.get_organization(UUID(str(organization_id)))
                if organization is None:
                    raise ValueError("组织不存在")
                user.organization_id = organization.id
            else:
                user.organization_id = None

        if "status" in changes:
            raw_status = changes["status"]
            if isinstance(raw_status, UserStatus):
                user.status = raw_status
            else:
                user.status = UserStatus(str(raw_status))
            if user.status == UserStatus.ACTIVE:
                user.is_active = True
            else:
                user.is_active = False

        if "is_active" in changes:
            is_active = bool(changes["is_active"])
            user.is_active = is_active
            if not is_active and user.status == UserStatus.ACTIVE:
                user.status = UserStatus.DISABLED
            if is_active and user.status != UserStatus.ACTIVE:
                user.status = UserStatus.ACTIVE

        if "feature_flags" in changes:
            user.feature_flags = normalize_user_feature_flags(changes["feature_flags"])
            if (
                user.organization_id is not None
                and user_feature_enabled(
                    user.feature_flags,
                    FEATURE_AMWAYCHINA_CONSOLE,
                )
            ):
                organization = await self.get_organization(user.organization_id)
                if organization is not None:
                    await ensure_amwaychina_console_entity(self.db, organization)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def list_organizations(self) -> list[Organization]:
        result = await self.db.execute(
            select(Organization)
            .options(
                selectinload(Organization.users), selectinload(Organization.entities)
            )
            .order_by(Organization.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        result = await self.db.execute(
            select(Organization)
            .options(
                selectinload(Organization.users), selectinload(Organization.entities)
            )
            .where(Organization.id == organization_id)
        )
        return result.scalar_one_or_none()

    async def update_organization(
        self,
        *,
        organization_id: UUID,
        changes: dict[str, object | None],
    ) -> Organization:
        organization = await self.get_organization(organization_id)
        if organization is None:
            raise ValueError("组织不存在")

        if "legal_name" in changes:
            legal_name = changes["legal_name"]
            normalized_legal_name = str(legal_name).strip() if legal_name else None
            if not normalized_legal_name:
                raise ValueError("组织名称不能为空")
            existing = await self.db.execute(
                select(Organization).where(
                    Organization.legal_name == normalized_legal_name,
                    Organization.id != organization.id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError("已有同名组织，请先确认是否需要合并")
            organization.legal_name = normalized_legal_name

        if "status" in changes:
            raw_status = changes["status"]
            if isinstance(raw_status, OrganizationStatus):
                organization.status = raw_status
            else:
                organization.status = OrganizationStatus(str(raw_status))

        if "feature_flags" in changes:
            organization.feature_flags = normalize_organization_feature_flags(
                changes["feature_flags"]
            )
            if organization_feature_enabled(
                organization.feature_flags,
                FEATURE_AMWAYCHINA_CONSOLE,
            ):
                await ensure_amwaychina_console_entity(self.db, organization)

        await self.db.commit()
        await self.db.refresh(organization)
        return organization

    async def create_invitation(
        self,
        *,
        email: str,
        organization_id: UUID,
        reviewer_user_id: UUID,
        applicant_name: str | None = None,
        job_title: str | None = None,
        feature_flags: dict[str, bool] | None = None,
    ) -> dict[str, object]:
        normalized_email = normalize_email(email)
        if not normalized_email:
            raise ValueError("请输入有效的邮箱地址")

        organization = await self.get_organization(organization_id)
        if organization is None:
            raise ValueError("组织不存在")
        if organization.status != OrganizationStatus.ACTIVE:
            raise ValueError("只能向启用状态的组织发放邀请")

        normalized_flags = normalize_user_feature_flags(feature_flags)
        if user_feature_enabled(normalized_flags, FEATURE_AMWAYCHINA_CONSOLE):
            await ensure_amwaychina_console_entity(self.db, organization)

        existing_user = await self._get_user_by_email(normalized_email)
        if existing_user is not None:
            if existing_user.organization_id != organization.id:
                raise ValueError("该邮箱已属于其他组织，不能直接发放本组织权限")
            if not existing_user.is_active or existing_user.status != UserStatus.ACTIVE:
                raise ValueError("该邮箱账号当前未启用，请先处理账号状态")
            existing_user.feature_flags = self._merge_feature_flags(
                existing_user.feature_flags,
                normalized_flags,
            )
            await self.db.commit()
            await self.db.refresh(existing_user)
            return {
                "status": "existing_user_granted",
                "email": normalized_email,
                "feature_flags": normalize_user_feature_flags(
                    existing_user.feature_flags
                ),
                "user": existing_user,
                "application": None,
            }

        application = await self._get_latest_application_by_email(normalized_email)
        if application is None:
            application = RegistrationApplication(
                email=normalized_email,
                phone=None,
                organization_name=organization.legal_name,
                job_title=(job_title or "团队成员").strip(),
                applicant_name=applicant_name.strip() if applicant_name else None,
            )
            self.db.add(application)

        now = datetime.now(timezone.utc)
        application.email = normalized_email
        application.organization_name = organization.legal_name
        application.job_title = (job_title or application.job_title or "团队成员").strip()
        application.applicant_name = (
            applicant_name.strip() if applicant_name else application.applicant_name
        )
        application.status = RegistrationApplicationStatus.PENDING_REVIEW
        application.review_note = None
        application.reviewed_by_user_id = reviewer_user_id
        application.approved_user_id = None
        application.assigned_organization_id = organization.id
        application.invite_code_issued_by_user_id = reviewer_user_id
        application.invite_code_sent_at = now
        application.invite_redeemed_at = None
        application.reviewed_at = now
        application.feature_flags = normalized_flags

        verification = VerificationService(self.db)
        await verification.send_code(
            channel=VerificationChannel.EMAIL,
            target=normalized_email,
            purpose=VerificationPurpose.INVITE_ACCESS,
        )
        await self.db.refresh(application)
        return {
            "status": "invited",
            "email": normalized_email,
            "feature_flags": normalize_user_feature_flags(application.feature_flags),
            "user": None,
            "application": application,
        }

    async def _get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.organization))
            .where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def _get_latest_application_by_email(
        self,
        email: str,
    ) -> RegistrationApplication | None:
        result = await self.db.execute(
            select(RegistrationApplication)
            .where(RegistrationApplication.email == email)
            .order_by(RegistrationApplication.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _merge_feature_flags(existing: object, changes: object) -> dict[str, bool]:
        merged = normalize_user_feature_flags(existing)
        for key, enabled in normalize_user_feature_flags(changes).items():
            merged[key] = enabled
        return merged

    @staticmethod
    def build_organization_stats(
        organizations: list[Organization],
    ) -> dict[UUID, dict[str, object]]:
        stats: dict[UUID, dict[str, object]] = defaultdict(dict)
        for organization in organizations:
            primary_account = None
            if organization.users:
                ordered_users = sorted(
                    organization.users, key=lambda item: item.created_at
                )
                primary_user = ordered_users[0]
                primary_account = primary_user.email or primary_user.phone
            stats[organization.id] = {
                "member_count": len(organization.users),
                "entity_count": len(organization.entities),
                "primary_account": primary_account,
            }
        return stats

    @staticmethod
    def is_internal_admin(user: User) -> bool:
        return user.role == UserRole.INTERNAL_ADMIN

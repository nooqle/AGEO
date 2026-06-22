from __future__ import annotations

from collections import defaultdict
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entity import Entity, EntityStatus, EntityVisibilityScope
from app.models.organization import Organization, OrganizationStatus
from app.models.user import User, UserRole, UserStatus
from app.services.brand_association_circle_variant import is_amway_association_entity
from app.services.identity_normalization_service import normalize_email, normalize_phone
from app.services.organization_feature_service import (
    FEATURE_AMWAYCHINA_CONSOLE,
    normalize_organization_feature_flags,
    organization_feature_enabled,
)


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
                await self._ensure_amwaychina_console_entity(organization)

        await self.db.commit()
        await self.db.refresh(organization)
        return organization

    async def _ensure_amwaychina_console_entity(
        self,
        organization: Organization,
    ) -> Entity:
        for entity in organization.entities:
            aliases = []
            if entity.aliases:
                try:
                    aliases = json.loads(entity.aliases)
                except (TypeError, json.JSONDecodeError):
                    aliases = [entity.aliases]
            if is_amway_association_entity(
                name=entity.name,
                domain=entity.domain,
                aliases=aliases,
            ):
                if entity.status != EntityStatus.ACTIVE:
                    entity.status = EntityStatus.ACTIVE
                entity.visibility_scope = EntityVisibilityScope.ORGANIZATION
                entity.organization_id = organization.id
                entity.owner_user_id = None
                await self.db.flush()
                return entity

        entity = Entity(
            name="安利",
            aliases=json.dumps(
                ["安利", "安利中国", "纽崔莱", "Amway", "Amway China", "Nutrilite"],
                ensure_ascii=False,
            ),
            domain="https://www.amway.com.cn",
            industry="健康生活",
            description="安利中国专属品牌联想圈层 Console 中心品牌组",
            status=EntityStatus.ACTIVE,
            visibility_scope=EntityVisibilityScope.ORGANIZATION,
            owner_user_id=None,
            organization_id=organization.id,
        )
        self.db.add(entity)
        await self.db.flush()
        return entity

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

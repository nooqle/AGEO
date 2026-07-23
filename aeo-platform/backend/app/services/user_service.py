from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole, UserStatus
from app.services.identity_normalization_service import normalize_email, normalize_phone


def _lightweight_user_select():
    """Auth / identity lookup: never hydrate chat graphs or brand collections.

    Rules:
    - noload User.sessions / owned_entities (prevents message OOM on auth).
    - Do NOT load User.organization in this query. Callers that need org must
      ``select(Organization)`` by ``user.organization_id``.

    Why not ``selectinload(org).noload(entities)``:
    that marks Organization.entities empty in the identity map; a later
    ``selectinload(Organization.entities)`` in the same Session can still see
    the empty collection and skip real brands (duplicate 安利 create regression).
    """
    return select(User).options(
        noload(User.sessions),
        noload(User.owned_entities),
        noload(User.organization),
    )


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        normalized_email = normalize_email(email)
        if normalized_email is None:
            return None
        result = await self.db.execute(
            _lightweight_user_select().where(User.email == normalized_email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_phone(self, phone: str) -> User | None:
        normalized_phone = normalize_phone(phone)
        if normalized_phone is None:
            return None
        result = await self.db.execute(
            _lightweight_user_select().where(User.phone == normalized_phone)
        )
        return result.scalar_one_or_none()

    async def get_user_by_identity(self, *, channel: str, target: str) -> User | None:
        if channel == "email":
            return await self.get_user_by_email(target)
        if channel == "phone":
            return await self.get_user_by_phone(target)
        return None

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(_lightweight_user_select().where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, email: str, password: str) -> User:
        user = User(
            email=normalize_email(email),
            hashed_password=hash_password(password),
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate_user(self, email: str, password: str) -> User | None:
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        if not user.is_active or user.status != UserStatus.ACTIVE:
            return None
        return user

    async def get_or_create_dev_user(self, email: str, name: str) -> User:
        """Get or create a development test user.

        This is used in development mode to allow testing without authentication.

        Args:
            email: Email of the development user
            name: Name of the development user

        Returns:
            User object
        """
        user = await self.get_user_by_email(email)
        if not user:
            # Create dev user with a default password
            user = User(
                email=email,
                hashed_password=hash_password("dev-password"),
                is_active=True,
                status=UserStatus.ACTIVE,
                role=UserRole.INTERNAL_ADMIN,
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
        elif (
            not user.is_active
            or user.status != UserStatus.ACTIVE
            or user.role != UserRole.INTERNAL_ADMIN
        ):
            user.is_active = True
            user.status = UserStatus.ACTIVE
            user.role = UserRole.INTERNAL_ADMIN
            await self.db.commit()
            await self.db.refresh(user)
        return user

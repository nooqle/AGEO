from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole, UserStatus


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_phone(self, phone: str) -> User | None:
        result = await self.db.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    async def get_user_by_identity(self, *, channel: str, target: str) -> User | None:
        target = target.strip()
        if channel == "email":
            return await self.get_user_by_email(target)
        if channel == "phone":
            return await self.get_user_by_phone(target)
        return None

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, email: str, password: str) -> User:
        user = User(
            email=email,
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

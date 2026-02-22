"""API dependencies."""

from typing import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.services.user_service import UserService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session.

    Yields:
        Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    token = credentials.credentials
    user = await get_user_from_token(token, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return user


async def get_user_from_token(
    token: str,
    db: AsyncSession,
):
    try:
        if settings.DEBUG and settings.DEV_MODE_ENABLED and token == settings.DEV_TOKEN:
            service = UserService(db)
            return await service.get_or_create_dev_user(
                email=settings.DEV_USER_EMAIL,
                name=settings.DEV_USER_NAME,
            )
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        service = UserService(db)
        return await service.get_user_by_id(UUID(user_id))
    except Exception:
        return None

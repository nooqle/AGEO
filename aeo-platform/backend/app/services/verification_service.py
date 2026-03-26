from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.services.identity_normalization_service import normalize_email, normalize_phone
from app.services.verification_delivery_service import (
    VerificationDeliveryError,
    VerificationDeliveryService,
)
from app.models.verification_challenge import (
    VerificationChannel,
    VerificationChallenge,
    VerificationPurpose,
)

logger = logging.getLogger(__name__)


class VerificationThrottleError(ValueError):
    """Raised when verification code requests are sent too frequently."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"验证码发送过于频繁，请在 {retry_after_seconds} 秒后重试")


class VerificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.delivery = VerificationDeliveryService()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _normalize_target(self, channel: VerificationChannel, target: str) -> str:
        if channel == VerificationChannel.EMAIL:
            return normalize_email(target) or ""
        return normalize_phone(target) or ""

    def _is_expired(self, expires_at: datetime) -> bool:
        if expires_at.tzinfo is None:
            return expires_at <= datetime.utcnow()
        return expires_at <= self._now()

    def _generate_code(self) -> str:
        return f"{random.randint(0, 999999):06d}"

    def _get_expire_minutes(self, purpose: VerificationPurpose) -> int:
        if purpose == VerificationPurpose.INVITE_ACCESS:
            return settings.INVITE_CODE_EXPIRE_MINUTES
        return settings.VERIFICATION_CODE_EXPIRE_MINUTES

    async def _get_latest_active_challenge(
        self,
        *,
        channel: VerificationChannel,
        target: str,
        purpose: VerificationPurpose,
    ) -> VerificationChallenge | None:
        result = await self.db.execute(
            select(VerificationChallenge)
            .where(
                VerificationChallenge.channel == channel,
                VerificationChallenge.target == target,
                VerificationChallenge.purpose == purpose,
                VerificationChallenge.consumed_at.is_(None),
            )
            .order_by(VerificationChallenge.created_at.desc())
            .limit(1)
        )
        challenge = result.scalar_one_or_none()
        if challenge is None:
            return None
        if self._is_expired(challenge.expires_at):
            return None
        return challenge

    async def send_code(
        self,
        *,
        channel: VerificationChannel,
        target: str,
        purpose: VerificationPurpose,
    ) -> dict[str, object]:
        normalized_target = self._normalize_target(channel, target)
        active_challenge = await self._get_latest_active_challenge(
            channel=channel,
            target=normalized_target,
            purpose=purpose,
        )
        if active_challenge is not None:
            expire_minutes = self._get_expire_minutes(purpose)
            sent_at = active_challenge.expires_at - timedelta(
                minutes=expire_minutes
            )
            elapsed_seconds = int(
                max(
                    0,
                    (self._now() - sent_at).total_seconds(),
                )
            )
            cooldown = settings.VERIFICATION_SEND_COOLDOWN_SECONDS
            if elapsed_seconds < cooldown:
                raise VerificationThrottleError(cooldown - elapsed_seconds)
            active_challenge.consumed_at = self._now()

        code = self._generate_code()
        expire_minutes = self._get_expire_minutes(purpose)
        challenge = VerificationChallenge(
            channel=channel,
            purpose=purpose,
            target=normalized_target,
            code_hash=hash_password(code),
            expires_at=self._now() + timedelta(minutes=expire_minutes),
        )
        self.db.add(challenge)
        await self.db.flush()

        try:
            await self.delivery.send_code(
                channel=channel,
                target=normalized_target,
                purpose=purpose,
                code=code,
                expires_in_minutes=expire_minutes,
            )
        except VerificationDeliveryError:
            await self.db.rollback()
            raise

        await self.db.commit()
        await self.db.refresh(challenge)

        logger.info(
            "[Verification] Sent %s code for %s target=%s",
            purpose.value,
            channel.value,
            normalized_target,
        )
        if settings.DEBUG or settings.DEV_MODE_ENABLED:
            logger.warning(
                "[Verification] Development code for %s: %s",
                normalized_target,
                code,
            )

        return {
            "challenge_id": str(challenge.id),
            "expires_in_seconds": expire_minutes * 60,
            "debug_code": (
                code if (settings.DEBUG or settings.DEV_MODE_ENABLED) else None
            ),
        }

    async def verify_code(
        self,
        *,
        channel: VerificationChannel,
        target: str,
        purpose: VerificationPurpose,
        code: str,
        consume: bool = True,
    ) -> VerificationChallenge | None:
        normalized_target = self._normalize_target(channel, target)
        result = await self.db.execute(
            select(VerificationChallenge)
            .where(
                VerificationChallenge.channel == channel,
                VerificationChallenge.target == normalized_target,
                VerificationChallenge.purpose == purpose,
                VerificationChallenge.consumed_at.is_(None),
            )
            .order_by(VerificationChallenge.created_at.desc())
            .limit(1)
        )
        challenge = result.scalar_one_or_none()
        if challenge is None:
            return None
        if self._is_expired(challenge.expires_at):
            return None
        if challenge.attempts >= settings.VERIFICATION_MAX_ATTEMPTS:
            return None
        if not verify_password(code, challenge.code_hash):
            challenge.attempts += 1
            if challenge.attempts >= settings.VERIFICATION_MAX_ATTEMPTS:
                challenge.consumed_at = self._now()
            await self.db.commit()
            return None
        if consume:
            challenge.consumed_at = self._now()
            await self.db.commit()
        return challenge

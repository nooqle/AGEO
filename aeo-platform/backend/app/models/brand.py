"""Brand Profile model."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.session import Session


class IndustryType(str, PyEnum):
    """Industry type enum."""

    ECOMMERCE = "ecommerce"
    SAAS = "saas"
    FINTECH = "fintech"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    RETAIL = "retail"
    MANUFACTURING = "manufacturing"
    OTHER = "other"


class CompanyScale(str, PyEnum):
    """Company scale enum."""

    STARTUP = "startup"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    ENTERPRISE = "enterprise"


class BrandProfile(Base):
    """Brand Profile model for storing brand information."""

    __tablename__ = "brand_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Basic Information
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Industry & Scale
    industry: Mapped[IndustryType | None] = mapped_column(
        Enum(IndustryType),
        nullable=True,
    )
    company_scale: Mapped[CompanyScale | None] = mapped_column(
        Enum(CompanyScale),
        nullable=True,
    )

    # Target Audience
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_age_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Brand Positioning
    brand_positioning: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    unique_selling_points: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Products/Services
    main_products: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_range: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Marketing Info
    marketing_channels: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitors: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AEO Related
    aeo_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_visibility_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Metadata
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    extra_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    session: Mapped["Session | None"] = relationship("Session")

    def __repr__(self) -> str:
        return f"<BrandProfile(id={self.id}, name={self.name})>"

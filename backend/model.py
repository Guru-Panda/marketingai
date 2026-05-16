import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


class EmployeeCount(str, enum.Enum):
    small = "5-50"
    medium = "51-500"


class LeadStatus(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    rejected = "rejected"
    ignored = "ignored"
    do_not_contact = "do_not_contact"


class ChannelStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    inactive = "inactive"
    rejected = "rejected"
    watching = "watching"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_count: Mapped[EmployeeCount | None] = mapped_column(Enum(EmployeeCount), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    slack_webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    email_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    strategies: Mapped[list["BusinessStrategy"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    suggested_channels: Mapped[list["SuggestedChannel"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tracked_channels: Mapped[list["Channel"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    leads: Mapped[list["Lead"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class EmailOTP(Base):
    __tablename__ = "email_otps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    otp_code: Mapped[str] = mapped_column(String(6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BusinessStrategy(Base):
    __tablename__ = "business_strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    main_problem: Mapped[str] = mapped_column(Text, nullable=False)
    ideal_customer: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    buyer_phrases: Mapped[list] = mapped_column(JSON, default=list)
    business_type: Mapped[str] = mapped_column(String(20), default="mixed")
    intent_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_locations: Mapped[list] = mapped_column(JSON, default=list)
    exclude_keywords: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="strategies")
    suggested_channels: Mapped[list["SuggestedChannel"]] = relationship(back_populates="strategy")
    tracked_channels: Mapped[list["Channel"]] = relationship(back_populates="strategy")
    leads: Mapped[list["Lead"]] = relationship(back_populates="strategy")


class SuggestedChannel(Base):
    __tablename__ = "suggested_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("business_strategies.id"), nullable=True, index=True)
    platform_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[ChannelStatus] = mapped_column(Enum(ChannelStatus), default=ChannelStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="suggested_channels")
    strategy: Mapped["BusinessStrategy | None"] = relationship(back_populates="suggested_channels")


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("user_id", "platform_type", "external_id", name="uq_channel_user_platform_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("business_strategies.id"), nullable=True, index=True)
    platform_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    last_synced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    # Per-channel bot token (e.g. Telegram bot token, Discord bot token for private channels)
    access_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="tracked_channels")
    strategy: Mapped["BusinessStrategy | None"] = relationship(back_populates="tracked_channels")


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("user_id", "source_platform", "external_id", name="uq_lead_user_platform_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("business_strategies.id"), nullable=True, index=True)
    source_platform: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_summary: Mapped[str] = mapped_column(Text, nullable=False)
    intent_score: Mapped[float] = mapped_column(Float, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.new)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Author / contact details captured at scrape time
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    author_location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # AI-generated outreach message draft
    outreach_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    # User feedback: 1 = good lead, -1 = bad lead, None = no feedback yet
    feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship(back_populates="leads")
    strategy: Mapped["BusinessStrategy | None"] = relationship(back_populates="leads")

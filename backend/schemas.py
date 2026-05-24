from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, field_validator
from backend.model import ChannelStatus, EmployeeCount, LeadStatus


# ── Auth ─────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    company_name: str | None = None
    employee_count: EmployeeCount | None = None
    notes: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class SendOtpRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp_code: str


class VerifyOtpResponse(BaseModel):
    verified_token: str


class CompleteSignupRequest(BaseModel):
    verified_token: str
    password: str
    company_name: str | None = None
    employee_count: EmployeeCount | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# ── User ─────────────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    id: int
    email: EmailStr
    is_verified: bool
    company_name: str | None
    employee_count: EmployeeCount | None
    notes: str | None
    retention_days: int = 90
    created_at: datetime
    has_strategy: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user) -> "UserProfile":
        return cls(
            id=user.id,
            email=user.email,
            is_verified=user.is_verified,
            company_name=user.company_name,
            employee_count=user.employee_count,
            notes=user.notes,
            retention_days=user.retention_days,
            created_at=user.created_at,
            has_strategy=len(user.strategies) > 0,
        )


class UserUpdate(BaseModel):
    company_name: str | None = None
    employee_count: EmployeeCount | None = None
    notes: str | None = None
    retention_days: int | None = None


class NotificationSettings(BaseModel):
    notification_threshold: float = 0.8
    slack_webhook_url: str | None = None
    email_digest: bool = False

    model_config = {"from_attributes": True}


class NotificationUpdate(BaseModel):
    notification_threshold: float | None = None
    slack_webhook_url: str | None = None
    email_digest: bool | None = None


# ── BusinessStrategy ─────────────────────────────────────────────────────────

class StrategyCreate(BaseModel):
    title: str | None = None
    main_problem: str
    ideal_customer: str
    keywords: list[str] = []
    target_locations: list[str] = []


class StrategyPatch(BaseModel):
    title: str | None = None
    main_problem: str | None = None
    ideal_customer: str | None = None
    keywords: list[str] | None = None
    target_locations: list[str] | None = None
    buyer_phrases: list[str] | None = None
    intent_threshold: float | None = None
    exclude_keywords: list[str] | None = None


class StrategyResponse(BaseModel):
    id: int
    user_id: int
    title: str | None
    main_problem: str
    ideal_customer: str
    keywords: list[Any]
    buyer_phrases: list[Any] = []
    target_locations: list[Any]
    exclude_keywords: list[Any] = []
    intent_threshold: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class StrategyTitle(BaseModel):
    """Lightweight projection used to populate filter dropdowns."""
    id: int
    title: str | None

    model_config = {"from_attributes": True}


# ── AI Analysis ──────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    title: str | None = None
    user_text: str
    target_locations: list[str] = []


class AnalyzeResponse(BaseModel):
    strategy: "StrategyResponse"
    channels: list["ChannelResponse"]


# ── SuggestedChannel ─────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    platform_type: str
    name: str
    url: str | None = None
    status: ChannelStatus = ChannelStatus.pending


class ChannelUpdate(BaseModel):
    status: ChannelStatus | None = None
    sync_interval_hours: int | None = None
    url: str | None = None
    discord_channel_id: str | None = None


class ChannelResponse(BaseModel):
    id: int
    user_id: int
    strategy_id: int | None
    platform_type: str
    name: str
    url: str | None
    status: ChannelStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Tracked Channel ───────────────────────────────────────────────────────────

class TrackedChannelCreate(BaseModel):
    platform_type: str
    name: str
    external_id: str
    url: str | None = None
    sync_interval_hours: int | None = None


class TrackedChannelPatch(BaseModel):
    is_active: bool | None = None
    sync_interval_hours: int | None = None
    external_id: str | None = None


class PrivateChannelAccessPatch(BaseModel):
    """Submit a bot token / API key for a private channel so we can scrape it."""
    access_token: str
    # For Discord: the real snowflake channel ID(s) the bot can see (comma-separated)
    external_id: str | None = None


class TrackedChannelResponse(BaseModel):
    id: int
    user_id: int
    strategy_id: int | None
    platform_type: str
    name: str
    external_id: str
    url: str | None
    last_synced: datetime | None
    sync_interval_hours: int | None
    error_count: int
    is_active: bool
    is_private: bool = False
    # Never return the raw token to clients — just indicate whether one is set
    has_access_token: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_safe(cls, channel) -> "TrackedChannelResponse":
        data = {c.name: getattr(channel, c.name) for c in channel.__table__.columns}
        data["has_access_token"] = bool(data.pop("access_token", None))
        return cls(**data)


# ── Lead ──────────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    source_platform: str
    external_id: str
    content: str
    content_summary: str
    intent_score: float
    keywords: list[str] = []
    status: LeadStatus = LeadStatus.new
    strategy_id: int | None = None
    source_url: str | None = None
    author_name: str | None = None
    author_username: str | None = None
    author_url: str | None = None
    author_email: str | None = None
    author_phone: str | None = None
    author_location: str | None = None


class LeadStatusPatch(BaseModel):
    status: LeadStatus


class LeadFeedbackPatch(BaseModel):
    feedback: int  # 1 = good lead, -1 = bad lead


class OutreachRequest(BaseModel):
    extra_context: str | None = None  # optional extra info to personalise the draft
    tone: str | None = None  # casual | professional | direct | empathetic


class LeadResponse(BaseModel):
    id: int
    user_id: int
    strategy_id: int | None
    source_platform: str
    external_id: str
    content: str
    content_summary: str
    intent_score: float
    keywords: list[Any]
    status: LeadStatus
    created_at: datetime
    source_url: str | None = None
    author_name: str | None = None
    author_username: str | None = None
    author_url: str | None = None
    author_email: str | None = None
    author_phone: str | None = None
    author_location: str | None = None
    outreach_template: str | None = None
    feedback: int | None = None

    model_config = {"from_attributes": True}

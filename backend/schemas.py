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
    created_at: datetime
    has_strategy: bool = False

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    company_name: str | None = None
    employee_count: EmployeeCount | None = None
    notes: str | None = None


# ── BusinessStrategy ─────────────────────────────────────────────────────────

class StrategyCreate(BaseModel):
    title: str | None = None
    main_problem: str
    ideal_customer: str
    keywords: list[str] = []
    target_locations: list[str] = []


class StrategyResponse(BaseModel):
    id: int
    user_id: int
    title: str | None
    main_problem: str
    ideal_customer: str
    keywords: list[Any]
    target_locations: list[Any]
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
    created_at: datetime

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}

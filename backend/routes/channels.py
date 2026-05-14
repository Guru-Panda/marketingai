from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_verified_user
from backend.model import Channel, ChannelStatus, SuggestedChannel, User
from backend.monitor.channel_resolver import resolve_channel_url
from backend.schemas import (
    ChannelCreate, ChannelResponse, ChannelUpdate,
    TrackedChannelCreate, TrackedChannelPatch, TrackedChannelResponse,
)

# ── Helper ────────────────────────────────────────────────────────────────────

def get_active_channels(user_id: int, db: Session) -> list[Channel]:
    return (
        db.query(Channel)
        .filter(Channel.user_id == user_id, Channel.is_active.is_(True))
        .all()
    )


def ensure_channel_from_suggested(
    suggested: SuggestedChannel,
    db: Session,
    sync_interval_hours: int | None = None,
    discord_channel_id: str | None = None,
) -> Channel:
    """Create a Channel from a SuggestedChannel if one doesn't already exist."""
    # For Discord, use the real snowflake ID when provided; fall back to the
    # suggested channel's DB id (which won't be a valid snowflake but lets
    # the record exist until the user sets the real ID).
    external_id = (
        discord_channel_id
        if suggested.platform_type == "discord" and discord_channel_id
        else str(suggested.id)
    )

    existing = (
        db.query(Channel)
        .filter(
            Channel.user_id == suggested.user_id,
            Channel.platform_type == suggested.platform_type,
            Channel.external_id == str(suggested.id),
        )
        .first()
    )
    if existing:
        dirty = False
        if not existing.is_active:
            existing.is_active = True
            dirty = True
        if sync_interval_hours is not None:
            existing.sync_interval_hours = sync_interval_hours
            dirty = True
        if discord_channel_id and suggested.platform_type == "discord":
            existing.external_id = discord_channel_id
            dirty = True
        if dirty:
            db.commit()
            db.refresh(existing)
        return existing

    channel = Channel(
        user_id=suggested.user_id,
        strategy_id=suggested.strategy_id,
        platform_type=suggested.platform_type,
        name=suggested.name,
        external_id=external_id,
        url=suggested.url,
        is_active=True,
        sync_interval_hours=sync_interval_hours,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


# ── Tracked Channel routes  (/channels) ───────────────────────────────────────

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post("/", response_model=TrackedChannelResponse, status_code=status.HTTP_201_CREATED)
def create_tracked_channel(
    body: TrackedChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    existing = (
        db.query(Channel)
        .filter(
            Channel.user_id == current_user.id,
            Channel.platform_type == body.platform_type,
            Channel.external_id == body.external_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Channel already tracked")

    channel = Channel(user_id=current_user.id, is_active=True, **body.model_dump(exclude_none=True))
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.get("/", response_model=list[TrackedChannelResponse])
def list_tracked_channels(
    platform_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    strategy_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    limit = min(limit, 500)
    q = db.query(Channel).filter(Channel.user_id == current_user.id)
    if platform_type is not None:
        q = q.filter(Channel.platform_type == platform_type)
    if is_active is not None:
        q = q.filter(Channel.is_active.is_(is_active))
    if strategy_id is not None:
        q = q.filter(Channel.strategy_id == strategy_id)
    return q.order_by(Channel.created_at.desc()).offset(offset).limit(limit).all()


@router.patch("/{channel_id}", response_model=TrackedChannelResponse)
def toggle_tracked_channel(
    channel_id: int,
    body: TrackedChannelPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    channel = db.query(Channel).filter(
        Channel.id == channel_id,
        Channel.user_id == current_user.id,
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if body.is_active is not None:
        channel.is_active = body.is_active
    if body.sync_interval_hours is not None:
        channel.sync_interval_hours = body.sync_interval_hours
    if body.external_id is not None:
        channel.external_id = body.external_id
    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tracked_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    channel = db.query(Channel).filter(
        Channel.id == channel_id,
        Channel.user_id == current_user.id,
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete(channel)
    db.commit()


# ── SuggestedChannel routes  (/suggested-channels) ───────────────────────────

suggested_router = APIRouter(prefix="/suggested-channels", tags=["suggested-channels"])


@suggested_router.post("/", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
def create_suggested_channel(
    body: ChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    channel = SuggestedChannel(user_id=current_user.id, **body.model_dump())
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@suggested_router.get("/", response_model=list[ChannelResponse])
def list_suggested_channels(
    platform_type: Optional[str] = None,
    status: Optional[ChannelStatus] = None,
    strategy_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    limit = min(limit, 500)
    q = db.query(SuggestedChannel).filter(SuggestedChannel.user_id == current_user.id)
    if platform_type is not None:
        q = q.filter(SuggestedChannel.platform_type == platform_type)
    if status is not None:
        q = q.filter(SuggestedChannel.status == status)
    if strategy_id is not None:
        q = q.filter(SuggestedChannel.strategy_id == strategy_id)
    return q.order_by(SuggestedChannel.created_at.desc()).offset(offset).limit(limit).all()


@suggested_router.patch("/{channel_id}", response_model=ChannelResponse)
def update_suggested_channel_status(
    channel_id: int,
    body: ChannelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    channel = db.query(SuggestedChannel).filter(
        SuggestedChannel.id == channel_id,
        SuggestedChannel.user_id == current_user.id,
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Suggested channel not found")

    if body.status is not None:
        channel.status = body.status
    if body.url is not None:
        channel.url = body.url

    if channel.status == ChannelStatus.watching:
        ensure_channel_from_suggested(
            channel, db,
            sync_interval_hours=body.sync_interval_hours,
            discord_channel_id=body.discord_channel_id,
        )

    db.commit()
    db.refresh(channel)
    return channel


@suggested_router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suggested_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    channel = db.query(SuggestedChannel).filter(
        SuggestedChannel.id == channel_id,
        SuggestedChannel.user_id == current_user.id,
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Suggested channel not found")
    db.delete(channel)
    db.commit()


@suggested_router.post("/{channel_id}/resolve", response_model=ChannelResponse)
def resolve_suggested_channel_url(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Scrape the web to find a real joinable URL for a channel that has none."""
    channel = db.query(SuggestedChannel).filter(
        SuggestedChannel.id == channel_id,
        SuggestedChannel.user_id == current_user.id,
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Suggested channel not found")

    url = resolve_channel_url(channel.platform_type, channel.name)
    if not url:
        raise HTTPException(status_code=404, detail="Could not find a URL for this channel")

    channel.url = url
    db.commit()
    db.refresh(channel)
    return channel

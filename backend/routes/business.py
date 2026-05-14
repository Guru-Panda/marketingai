import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
from backend.database import get_db
from backend.dependencies import get_verified_user
from backend.model import BusinessStrategy, ChannelStatus, SuggestedChannel, User
from backend.schemas import (
    AnalyzeRequest, AnalyzeResponse,
    ChannelResponse, StrategyCreate, StrategyResponse, StrategyTitle,
)
from backend.business_analyzer import analyze_business, suggest_channels
from backend.monitor.channel_resolver import resolve_channel_url
from backend.routes.channels import ensure_channel_from_suggested, get_active_channels

router = APIRouter(prefix="/business", tags=["business"])

# ── AI-powered endpoint ───────────────────────────────────────────────────────

_PLATFORM_MAP = {
    "subreddits": "reddit",
    "telegram_channels": "telegram",
    "discord_servers": "discord",
    "linkedin_groups": "linkedin",
    "job_boards": "job_board",
    "quora_topics": "quora",
}


@router.post("/strategy", response_model=AnalyzeResponse, status_code=status.HTTP_201_CREATED)
def create_strategy_from_text(
    body: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    try:
        analysis = analyze_business(body.user_text)
    except Exception:
        log.exception("Business analysis failed for user %d", current_user.id)
        raise HTTPException(status_code=502, detail="Analysis failed. Please try again.")

    strategy = BusinessStrategy(
        user_id=current_user.id,
        title=body.title or None,
        main_problem=analysis.get("main_problem", ""),
        ideal_customer=analysis.get("ideal_customer", ""),
        keywords=analysis.get("keywords", []),
        buyer_phrases=analysis.get("buyer_phrases", []),
        target_locations=body.target_locations,
        business_type=analysis.get("business_type", "mixed"),
        intent_threshold=analysis.get("intent_threshold"),
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)

    try:
        channels_data = suggest_channels(analysis)
    except Exception:
        log.exception("Channel suggestion failed for user %d", current_user.id)
        raise HTTPException(status_code=502, detail="Channel suggestion failed. Please try again.")

    saved_channels: list[SuggestedChannel] = []
    for field, platform_type in _PLATFORM_MAP.items():
        for entry in channels_data.get(field, []):
            if isinstance(entry, dict):
                name = entry.get("name", "")
                url = entry.get("url") or None
            else:
                name = str(entry)
                url = None
            if not name:
                continue
            if not url:
                try:
                    url = resolve_channel_url(platform_type, name)
                except Exception:
                    pass
            channel = SuggestedChannel(
                user_id=current_user.id,
                strategy_id=strategy.id,
                platform_type=platform_type,
                name=name,
                url=url,
            )
            db.add(channel)
            saved_channels.append(channel)

    db.commit()
    for ch in saved_channels:
        db.refresh(ch)

    return AnalyzeResponse(
        strategy=StrategyResponse.model_validate(strategy),
        channels=[ChannelResponse.model_validate(ch) for ch in saved_channels],
    )


# ── Manual CRUD ───────────────────────────────────────────────────────────────

@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
def create_strategy(
    body: StrategyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    strategy = BusinessStrategy(user_id=current_user.id, **body.model_dump())
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


@router.get("/", response_model=list[StrategyResponse])
def list_strategies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    return db.query(BusinessStrategy).filter(BusinessStrategy.user_id == current_user.id).all()


@router.get("/titles", response_model=list[StrategyTitle])
def list_strategy_titles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Lightweight endpoint for populating filter dropdowns."""
    return db.query(BusinessStrategy).filter(BusinessStrategy.user_id == current_user.id).all()


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    strategy = db.query(BusinessStrategy).filter(
        BusinessStrategy.id == strategy_id,
        BusinessStrategy.user_id == current_user.id,
    ).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    strategy = db.query(BusinessStrategy).filter(
        BusinessStrategy.id == strategy_id,
        BusinessStrategy.user_id == current_user.id,
    ).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    db.delete(strategy)
    db.commit()

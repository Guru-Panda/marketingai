import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database import get_db, settings
from backend.model import Lead, User
from backend.rate_limit import check_rate_limit
from backend.schemas import UserProfile

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(request: Request, x_admin_key: str = Header(...)):
    check_rate_limit(f"admin:{request.client.host}", max_calls=20, window_seconds=60)
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/users", response_model=list[UserProfile], dependencies=[Depends(_require_admin)])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("/sync", dependencies=[Depends(_require_admin)])
def trigger_sync(background_tasks: BackgroundTasks):
    """Manually kick off a full channel sync without waiting for the scheduler."""
    from backend.monitor.sync import run_sync
    background_tasks.add_task(run_sync)
    return {"detail": "Sync started in background"}


@router.post("/refresh-channels", dependencies=[Depends(_require_admin)])
def trigger_channel_refresh(background_tasks: BackgroundTasks):
    """Drop pending suggestions and regenerate fresh verified ones for all strategies."""
    from backend.channel_refresh import refresh_suggested_channels
    background_tasks.add_task(refresh_suggested_channels)
    return {"detail": "Channel refresh started in background"}


@router.get("/leads-by-user", dependencies=[Depends(_require_admin)])
def leads_by_user(db: Session = Depends(get_db)):
    """Show lead counts per user — use this to diagnose why a user sees no leads."""
    rows = (
        db.query(User.id, User.email, func.count(Lead.id).label("total_leads"))
        .outerjoin(Lead, Lead.user_id == User.id)
        .group_by(User.id, User.email)
        .order_by(func.count(Lead.id).desc())
        .all()
    )
    return [{"user_id": r[0], "email": r[1], "total_leads": r[2]} for r in rows]


@router.get("/debug-scorer", dependencies=[Depends(_require_admin)])
def debug_scorer():
    """Show what LLM backend scorer.py is using."""
    import inspect
    import backend.monitor.scorer as scorer_mod
    src = inspect.getsource(scorer_mod.score_post)
    uses_llm_call = "llm_call" in src
    uses_anthropic = "_get_client" in src or "messages.create" in src
    return {
        "uses_llm_call": uses_llm_call,
        "uses_anthropic_directly": uses_anthropic,
        "first_200_chars": src[:200],
    }

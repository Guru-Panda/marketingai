import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
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
    users = db.query(User).options(selectinload(User.strategies)).order_by(User.created_at.desc()).all()
    return [UserProfile.from_user(u) for u in users]


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


@router.post("/seed-demo-leads/{user_id}", dependencies=[Depends(_require_admin)])
def seed_demo_leads(user_id: int, db: Session = Depends(get_db)):
    """Seed the built-in demo leads for a specific user so they see data immediately."""
    from backend.model import Lead, LeadStatus
    from backend.routes.leads import _DEMO_LEADS

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    created = []
    for i, demo in enumerate(_DEMO_LEADS):
        external_id = f"demo-{i+1}"
        # Skip if already exists for this user
        existing = db.query(Lead).filter(
            Lead.user_id == user_id,
            Lead.source_platform == demo["source_platform"],
            Lead.external_id == external_id,
        ).first()
        if existing:
            continue

        lead = Lead(
            user_id=user_id,
            source_platform=demo["source_platform"],
            external_id=external_id,
            content=demo["content"],
            content_summary=demo["content_summary"],
            intent_score=demo["intent_score"],
            keywords=demo.get("keywords", []),
            source_url=demo.get("source_url"),
            author_name=demo.get("author_name"),
            author_username=demo.get("author_username"),
            author_url=demo.get("author_url"),
            author_email=demo.get("author_email"),
            author_location=demo.get("author_location"),
            status=LeadStatus.new,
        )
        db.add(lead)
        created.append(demo["source_platform"])

    db.commit()
    return {"seeded": len(created), "platforms": created}


@router.post("/create-strategy/{user_id}", dependencies=[Depends(_require_admin)])
def create_strategy_for_user(user_id: int, db: Session = Depends(get_db)):
    """Create a default placeholder business strategy for a user so the sync starts finding real leads."""
    from backend.model import BusinessStrategy

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing = db.query(BusinessStrategy).filter(BusinessStrategy.user_id == user_id).first()
    if existing:
        return {"detail": "Strategy already exists", "strategy_id": existing.id}

    strategy = BusinessStrategy(
        user_id=user_id,
        title="Default Strategy",
        main_problem="Helping businesses find and convert high-intent leads faster",
        ideal_customer="Startups and SMBs actively looking for SaaS tools, CRM, sales automation, or marketing solutions",
        keywords=["CRM", "lead generation", "sales automation", "SaaS", "marketing tool", "B2B"],
        buyer_phrases=["looking for a tool", "need a solution", "any recommendations", "we are scaling", "replace spreadsheets"],
        business_type="b2b",
        intent_threshold=0.65,
        target_locations=[],
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return {"detail": "Strategy created", "strategy_id": strategy.id}

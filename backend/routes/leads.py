from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import nulls_last
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_verified_user
from backend.model import BusinessStrategy, Lead, LeadStatus, User
from backend.schemas import LeadCreate, LeadFeedbackPatch, LeadResponse, LeadStatusPatch, OutreachRequest

router = APIRouter(prefix="/leads", tags=["leads"])

_HIDDEN_STATUSES = {LeadStatus.ignored, LeadStatus.do_not_contact}

_DEMO_LEADS = [
    {
        "source_platform": "reddit",
        "content": "Hey everyone, our startup is scaling fast and we desperately need a reliable B2B SaaS CRM tool. Currently using spreadsheets but it's getting out of hand with 50+ leads. Budget is around $200/month. Any recommendations? We're a 15-person team in fintech.",
        "content_summary": "Fintech startup (15 people) actively seeking a B2B SaaS CRM to replace spreadsheets. Budget $200/mo, 50+ leads. High purchase intent.",
        "intent_score": 0.92,
        "keywords": ["CRM", "B2B SaaS", "fintech startup", "lead management", "scaling"],
        "source_url": "https://www.reddit.com/r/startups/comments/demo",
        "author_name": "Arjun Mehta",
        "author_username": "arjun_builds",
        "author_url": "https://www.reddit.com/user/arjun_builds",
        "author_location": "Bangalore, India",
    },
    {
        "source_platform": "linkedin",
        "content": "We're a Series A startup looking for outbound sales automation tools. Our SDR team is manually prospecting 200+ accounts a week and we need something that integrates with HubSpot. Would love recommendations from founders who've solved this.",
        "content_summary": "Series A startup SDR team needs outbound sales automation integrating with HubSpot. Actively evaluating tools.",
        "intent_score": 0.87,
        "keywords": ["outbound sales", "sales automation", "HubSpot integration", "SDR", "Series A"],
        "source_url": "https://www.linkedin.com/posts/demo",
        "author_name": "Priya Sharma",
        "author_username": "priya-sharma-founder",
        "author_url": "https://www.linkedin.com/in/priya-sharma-founder",
        "author_email": "priya@techstartup.in",
        "author_location": "Mumbai, India",
    },
    {
        "source_platform": "discord",
        "content": "Anyone using AI tools for lead generation in the SaaS space? We're trying to identify companies that are hiring sales roles (usually signals they need better tooling). Looking for something that can monitor job boards and social media automatically.",
        "content_summary": "SaaS founder looking for AI-powered lead gen tools that monitor job boards and social media for buying signals.",
        "intent_score": 0.78,
        "keywords": ["AI lead generation", "SaaS", "job board monitoring", "buying signals", "automated prospecting"],
        "source_url": "https://discord.com/channels/demo",
        "author_name": "Rohan Das",
        "author_username": "rohan_saas",
        "author_location": "Delhi, India",
    },
]


@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(
    body: LeadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    lead = Lead(user_id=current_user.id, **body.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead




@router.get("/", response_model=list[LeadResponse])
def list_leads(
    platform: Optional[str] = None,
    status: Optional[LeadStatus] = None,
    strategy_id: Optional[int] = None,
    min_intent_score: Optional[float] = None,
    max_intent_score: Optional[float] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    show_hidden: bool = False,
    has_email: Optional[bool] = None,
    has_contact: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    limit = min(limit, 500)
    q = db.query(Lead).filter(Lead.user_id == current_user.id)

    if not show_hidden and status is None:
        q = q.filter(Lead.status.notin_(_HIDDEN_STATUSES))

    if platform:
        q = q.filter(Lead.source_platform == platform)
    if status:
        q = q.filter(Lead.status == status)
    if strategy_id is not None:
        q = q.filter(Lead.strategy_id == strategy_id)
    if min_intent_score is not None:
        q = q.filter(Lead.intent_score >= min_intent_score)
    if max_intent_score is not None:
        q = q.filter(Lead.intent_score <= max_intent_score)
    if from_date:
        q = q.filter(Lead.created_at >= from_date)
    if to_date:
        q = q.filter(Lead.created_at <= to_date)
    if has_email is True:
        q = q.filter(Lead.author_email.isnot(None))
    elif has_email is False:
        q = q.filter(Lead.author_email.is_(None))
    if has_contact is True:
        q = q.filter(
            (Lead.author_email.isnot(None)) |
            (Lead.author_username.isnot(None)) |
            (Lead.author_url.isnot(None))
        )
    elif has_contact is False:
        q = q.filter(
            Lead.author_email.is_(None),
            Lead.author_username.is_(None),
            Lead.author_url.is_(None),
        )

    # Leads with email float to the top, then by intent score descending
    return (
        q.order_by(
            nulls_last(Lead.author_email.desc()),
            Lead.intent_score.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.patch("/{lead_id}/status", response_model=LeadResponse)
def update_lead_status(
    lead_id: int,
    body: LeadStatusPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.user_id == current_user.id,
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = body.status
    db.commit()
    db.refresh(lead)
    return lead


@router.patch("/{lead_id}/feedback", response_model=LeadResponse)
def submit_lead_feedback(
    lead_id: int,
    body: LeadFeedbackPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Thumbs up (1) or thumbs down (-1) on a lead.
    Feedback is stored and will be used to tune the intent scorer over time.
    """
    if body.feedback not in (1, -1):
        raise HTTPException(status_code=422, detail="feedback must be 1 or -1")
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.user_id == current_user.id,
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.feedback = body.feedback
    db.commit()
    db.refresh(lead)
    return lead


@router.post("/{lead_id}/outreach", response_model=LeadResponse)
def generate_lead_outreach(
    lead_id: int,
    body: OutreachRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """(Re-)generate an AI outreach message draft for a lead.
    Returns the updated lead with outreach_template populated.
    """
    from backend.monitor.scorer import generate_outreach

    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.user_id == current_user.id,
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Pull business context from the strategy if available
    biz: dict = {}
    if lead.strategy_id:
        s = db.query(BusinessStrategy).filter(BusinessStrategy.id == lead.strategy_id).first()
        if s:
            biz = {
                "main_problem": s.main_problem or "",
                "ideal_customer": s.ideal_customer or "",
            }

    try:
        template = generate_outreach(
            platform=lead.source_platform,
            post_content=lead.content,
            summary=lead.content_summary,
            business_context=biz,
            extra_context=body.extra_context or "",
            tone=body.tone or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Outreach generation failed: {exc}")

    lead.outreach_template = template
    db.commit()
    db.refresh(lead)
    return lead

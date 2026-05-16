from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_verified_user
from backend.model import Lead, LeadStatus, User
from backend.monitor.sync import get_sync_stats

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def get_analytics_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # Leads per day for the last 7 days
    leads_by_day = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end = day_start + timedelta(days=1)
        count = (
            db.query(func.count(Lead.id))
            .filter(
                Lead.user_id == current_user.id,
                Lead.created_at >= day_start,
                Lead.created_at < day_end,
            )
            .scalar()
            or 0
        )
        leads_by_day.append({"date": day_start.strftime("%b %d"), "count": count})

    # Platform breakdown
    platform_rows = (
        db.query(Lead.source_platform, func.count(Lead.id).label("count"))
        .filter(Lead.user_id == current_user.id)
        .group_by(Lead.source_platform)
        .order_by(func.count(Lead.id).desc())
        .all()
    )
    platform_breakdown = [
        {"platform": r.source_platform, "count": r.count} for r in platform_rows
    ]

    # Average intent score
    avg_intent = (
        db.query(func.avg(Lead.intent_score))
        .filter(Lead.user_id == current_user.id)
        .scalar()
        or 0.0
    )

    # Totals
    total_leads = (
        db.query(func.count(Lead.id))
        .filter(Lead.user_id == current_user.id)
        .scalar()
        or 0
    )
    contacted = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.user_id == current_user.id,
            Lead.status == LeadStatus.contacted,
        )
        .scalar()
        or 0
    )
    new_this_week = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.user_id == current_user.id,
            Lead.created_at >= seven_days_ago,
        )
        .scalar()
        or 0
    )

    sync_stats = get_sync_stats()

    return {
        "leads_by_day": leads_by_day,
        "platform_breakdown": platform_breakdown,
        "avg_intent_score": round(float(avg_intent), 2),
        "total_leads": total_leads,
        "contacted_leads": contacted,
        "new_this_week": new_this_week,
        "posts_scanned": sync_stats["posts_scanned"],
    }

import threading
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_verified_user
from backend.model import Lead, LeadStatus, User
from backend.monitor.sync import get_sync_stats, run_sync

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/status")
def get_monitor_status(
    current_user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """Return sync heartbeat — last run time, posts scanned, leads found.

    new_leads is the count of 'new'-status leads owned by the current user,
    sourced directly from the database.  This is always accurate regardless of
    how many sync runs have happened or whether other users share the deployment.
    """
    stats = get_sync_stats()
    # Replace the global in-memory counter with the real per-user figure so the
    # banner matches exactly what appears in the leads table.
    stats["new_leads"] = (
        db.query(Lead)
        .filter(Lead.user_id == current_user.id, Lead.status == LeadStatus.new)
        .count()
    )
    # Diagnostic: total leads in DB for this user across all statuses.
    # If new_leads > 0 but total_leads == 0, leads belong to a different user.
    # If total_leads > 0 but the table is empty, the list query has a bug.
    stats["total_leads"] = (
        db.query(Lead)
        .filter(Lead.user_id == current_user.id)
        .count()
    )
    return stats


@router.post("/sync", status_code=202)
def trigger_sync(current_user: User = Depends(get_verified_user)):
    """Manually kick off a full sync across all platforms immediately.
    Returns 202 immediately; poll GET /monitor/status to track progress.
    """
    stats = get_sync_stats()
    if stats.get("is_running"):
        return {"status": "already_running"}
    threading.Thread(target=run_sync, daemon=True).start()
    return {"status": "started"}

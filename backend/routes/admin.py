import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from backend.database import get_db, settings
from backend.model import User
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

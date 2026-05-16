from fastapi import APIRouter, Depends
from backend.dependencies import get_verified_user
from backend.model import User
from backend.monitor.sync import get_sync_stats

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/status")
def get_monitor_status(current_user: User = Depends(get_verified_user)):
    """Return sync heartbeat — last run time, posts scanned, leads found."""
    return get_sync_stats()

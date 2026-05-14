import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from backend.database import SessionLocal
from backend.model import Lead

log = logging.getLogger("data_retention")

LEAD_RETENTION_DAYS = int(os.getenv("LEAD_RETENTION_DAYS", "30"))


def delete_old_leads() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LEAD_RETENTION_DAYS)
    db = SessionLocal()
    try:
        result = db.execute(
            delete(Lead).where(Lead.created_at < cutoff)
        )
        db.commit()
        deleted = result.rowcount
        if deleted:
            log.info("Data retention: deleted %d lead(s) older than %d days", deleted, LEAD_RETENTION_DAYS)
        return deleted
    except Exception:
        db.rollback()
        log.exception("Data retention: failed to delete old leads")
        return 0
    finally:
        db.close()

"""
Verify that a suggested channel is actively posting before we save it.
Returns True if the channel had activity in the last 14 days, False otherwise.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketingMonitor/1.0)"}
_ACTIVE_WINDOW_DAYS = 14


def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def verify_reddit(subreddit: str) -> bool:
    slug = subreddit.lstrip("/").removeprefix("r/").strip()
    try:
        resp = httpx.get(
            f"https://www.reddit.com/r/{slug}/new.json",
            headers=_HEADERS,
            params={"limit": 5},
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            log.info("Reddit r/%s not found (status %d)", slug, resp.status_code)
            return False
        children = resp.json().get("data", {}).get("children", [])
        if not children:
            log.info("Reddit r/%s has no posts", slug)
            return False
        # Check if the newest post is within the active window
        newest_ts = children[0]["data"].get("created_utc", 0)
        newest = datetime.fromtimestamp(newest_ts, tz=timezone.utc)
        active = newest >= _days_ago(_ACTIVE_WINDOW_DAYS)
        if not active:
            log.info("Reddit r/%s last post was %s — inactive", slug, newest.date())
        return active
    except Exception as exc:
        log.warning("Reddit verify failed for r/%s: %s", slug, exc)
        return True  # fail open — don't discard on network error


def verify_telegram(handle: str) -> bool:
    """Best-effort check: fetch the public t.me preview page and look for post timestamps."""
    clean = handle.lstrip("@").replace("https://t.me/", "").strip()
    try:
        resp = httpx.get(
            f"https://t.me/s/{clean}",
            headers=_HEADERS,
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code == 404:
            log.info("Telegram @%s not found", clean)
            return False
        # If the page loads with any content, treat it as active
        active = resp.status_code == 200 and len(resp.text) > 2000
        if not active:
            log.info("Telegram @%s appears empty or private", clean)
        return active
    except Exception as exc:
        log.warning("Telegram verify failed for @%s: %s", clean, exc)
        return True  # fail open


def verify_channel(platform_type: str, name: str, url: str | None) -> bool:
    """Route to the right verifier. Returns True if the channel is active."""
    try:
        if platform_type == "reddit":
            return verify_reddit(name)
        if platform_type == "telegram":
            handle = (url or "").replace("https://t.me/", "") or name
            return verify_telegram(handle)
        # Discord, LinkedIn, Quora, job boards — no automated check, assume active
        return True
    except Exception as exc:
        log.warning("Channel verify error [%s / %s]: %s", platform_type, name, exc)
        return True  # fail open

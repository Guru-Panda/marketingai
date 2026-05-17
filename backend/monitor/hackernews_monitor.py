"""
Hacker News lead monitor.
Uses the Algolia HN search API — completely free, no auth, not blocked on cloud hosts.
Targets Ask HN, Show HN, and general stories matching buyer phrases / keywords.
"""
import hashlib
import logging

import httpx

log = logging.getLogger(__name__)

_ALGOLIA = "https://hn.algolia.com/api/v1"
_HEADERS = {"User-Agent": "MarketingMonitor/1.0"}


def _build_post(hit: dict) -> dict | None:
    obj_id = hit.get("objectID") or hit.get("story_id")
    if not obj_id:
        return None
    title = hit.get("title") or hit.get("story_title") or ""
    body = hit.get("comment_text") or hit.get("story_text") or ""
    content = f"{title}\n\n{body}".strip() if body else title
    if not content:
        return None
    author = hit.get("author") or ""
    return {
        "external_id": f"hn-{obj_id}",
        "content": content,
        "source_url": hit.get("url") or f"https://news.ycombinator.com/item?id={obj_id}",
        "author_name": author or None,
        "author_username": author or None,
        "author_url": f"https://news.ycombinator.com/user?id={author}" if author else None,
    }


def search_posts(query: str, limit: int = 20, search_by_date: bool = True) -> list[dict]:
    """Search HN via Algolia. search_by_date=True returns recent posts first."""
    endpoint = f"{_ALGOLIA}/search_by_date" if search_by_date else f"{_ALGOLIA}/search"
    try:
        resp = httpx.get(
            endpoint,
            params={
                "query": query,
                "tags": "ask_hn,story",
                "hitsPerPage": min(limit, 100),
            },
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        posts = []
        seen: set[str] = set()
        for hit in resp.json().get("hits", []):
            p = _build_post(hit)
            if p and p["external_id"] not in seen:
                seen.add(p["external_id"])
                posts.append(p)
        log.info("HN search '%s': %d results", query[:60], len(posts))
        return posts
    except Exception:
        log.exception("HN search failed for '%s'", query[:60])
        return []


def fetch_posts(channel_name: str, limit: int = 25) -> list[dict]:
    """Fetch recent Ask HN / Show HN posts matching a topic keyword (used for tracked channels)."""
    return search_posts(channel_name, limit=limit, search_by_date=True)

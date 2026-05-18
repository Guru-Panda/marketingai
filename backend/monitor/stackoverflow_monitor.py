"""
Stack Overflow / Stack Exchange lead monitor.
Uses the Stack Exchange API v2.3 — free, generous rate limits (300 req/day unauthenticated,
10 000/day with an API key stored in STACKOVERFLOW_KEY).
Targets questions tagged with relevant keywords where people are seeking solutions.
"""
import logging

import httpx

from backend.database import settings

log = logging.getLogger(__name__)

_BASE = "https://api.stackexchange.com/2.3"
_HEADERS = {"Accept-Encoding": "gzip"}


def _api_params(extra: dict) -> dict:
    p = {"site": "stackoverflow", "order": "desc", "sort": "creation", **extra}
    key = getattr(settings, "STACKOVERFLOW_KEY", "")
    if key:
        p["key"] = key
    return p


def _build_post(item: dict) -> dict:
    q_id = item.get("question_id", "")
    title = item.get("title", "")
    body = item.get("body_markdown") or item.get("body") or ""
    # Strip minimal HTML tags that may come through
    import re
    body = re.sub(r"<[^>]+>", " ", body)
    content = f"{title}\n\n{body}".strip() if body else title
    owner = item.get("owner", {})
    author = owner.get("display_name") or ""
    return {
        "external_id": f"so-{q_id}",
        "content": content[:3000],
        "source_url": item.get("link") or f"https://stackoverflow.com/q/{q_id}",
        "author_name": author or None,
        "author_username": owner.get("user_id") and str(owner["user_id"]) or None,
        "author_url": owner.get("link") or None,
    }


def search_posts(query: str, tags: list[str] | None = None, limit: int = 20) -> list[dict]:
    """Search Stack Overflow questions by query string and/or tags."""
    try:
        params = _api_params({
            "q": query,
            "pagesize": min(limit, 100),
            "filter": "withbody",
        })
        if tags:
            params["tagged"] = ";".join(tags[:5])

        resp = httpx.get(f"{_BASE}/search/advanced", params=params, headers=_HEADERS, timeout=15)
        if resp.status_code == 400:
            # Bad tag or quota; try without filter body
            params.pop("filter", None)
            resp = httpx.get(f"{_BASE}/search/advanced", params=params, headers=_HEADERS, timeout=15)
        resp.raise_for_status()

        posts = [_build_post(item) for item in resp.json().get("items", [])]
        log.info("SO search '%s': %d results", query[:60], len(posts))
        return posts
    except Exception as e:
        log.warning("SO search failed for '%s': %s", query[:60], e)
        return []


def fetch_posts(tag: str, limit: int = 25) -> list[dict]:
    """Fetch newest questions for a given tag (used for tracked channels)."""
    try:
        params = _api_params({"tagged": tag, "pagesize": min(limit, 50)})
        resp = httpx.get(f"{_BASE}/questions", params=params, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        posts = [_build_post(item) for item in resp.json().get("items", [])]
        log.info("SO tag '%s': %d results", tag, len(posts))
        return posts
    except Exception:
        log.exception("SO fetch failed for tag '%s'", tag)
        return []

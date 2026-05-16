"""
Dev.to lead monitor.
Uses the free, public dev.to REST API — no auth required, no IP blocking.
Good signal for developer tools, SaaS, APIs, and technical products.
"""
import logging

import httpx

log = logging.getLogger(__name__)

_BASE = "https://dev.to/api"
_HEADERS = {
    "User-Agent": "MarketingMonitor/1.0",
    "Accept": "application/vnd.forem.api-v1+json",
}


def _build_post(article: dict) -> dict:
    art_id = article.get("id", "")
    title = article.get("title", "")
    description = article.get("description") or ""
    content = f"{title}\n\n{description}".strip() if description else title
    user = article.get("user", {})
    author = user.get("name") or user.get("username") or ""
    username = user.get("username") or ""
    return {
        "external_id": f"devto-{art_id}",
        "content": content,
        "source_url": article.get("url") or f"https://dev.to/{username}/{article.get('slug', '')}",
        "author_name": author or None,
        "author_username": username or None,
        "author_url": f"https://dev.to/{username}" if username else None,
    }


def search_posts(query: str, limit: int = 20) -> list[dict]:
    """Search Dev.to articles by keyword tags.

    Dev.to's public API has no full-text search endpoint, so we query each
    significant word in the query as a tag (the tag endpoint is well-supported
    and returns fresh articles).  Results from all tags are deduplicated.
    """
    words = [w.strip().lower().replace(" ", "").replace("-", "") for w in query.split() if len(w.strip()) > 2]
    if not words:
        return []

    seen: set[str] = set()
    posts: list[dict] = []

    for tag in words[:5]:
        try:
            resp = httpx.get(
                f"{_BASE}/articles",
                params={"tag": tag, "per_page": min(limit, 30)},
                headers=_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            for article in resp.json():
                p = _build_post(article)
                if p["external_id"] not in seen:
                    seen.add(p["external_id"])
                    posts.append(p)
                if len(posts) >= limit:
                    log.info("Dev.to search '%s': %d results", query[:60], len(posts))
                    return posts
        except Exception:
            log.exception("Dev.to tag search failed for tag '%s'", tag)

    log.info("Dev.to search '%s': %d results", query[:60], len(posts))
    return posts


def fetch_posts(tag: str, limit: int = 25) -> list[dict]:
    """Fetch newest Dev.to articles by tag."""
    clean_tag = tag.lower().replace(" ", "").replace("-", "").replace("_", "")
    try:
        resp = httpx.get(
            f"{_BASE}/articles",
            params={"tag": clean_tag, "per_page": min(limit, 30)},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        posts = [_build_post(a) for a in resp.json()]
        log.info("Dev.to tag '%s': %d results", clean_tag, len(posts))
        return posts
    except Exception:
        log.exception("Dev.to fetch failed for tag '%s'", clean_tag)
        return []

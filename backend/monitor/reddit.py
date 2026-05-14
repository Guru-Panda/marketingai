import logging
import httpx

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketingMonitor/1.0)"}


def search_posts(query: str, limit: int = 25, sort: str = "new") -> list[dict]:
    """Search Reddit-wide for posts matching a query phrase.
    Returns posts from any subreddit — useful for proactive buyer hunting.
    """
    try:
        resp = httpx.get(
            "https://www.reddit.com/search.json",
            headers=_HEADERS,
            params={"q": query, "sort": sort, "limit": limit, "type": "link"},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []
        posts = []
        for child in resp.json().get("data", {}).get("children", []):
            p = child.get("data", {})
            body = p.get("title", "")
            if p.get("selftext"):
                body += f"\n\n{p['selftext']}"
            author = p.get("author") or ""
            posts.append({
                "external_id": f"search-{p['id']}",
                "content": body,
                "source_url": f"https://reddit.com{p.get('permalink', '')}" if p.get("permalink") else None,
                "author_name": author or None,
                "author_username": author or None,
                "author_url": f"https://reddit.com/u/{author}" if author and author != "[deleted]" else None,
                "subreddit": p.get("subreddit", ""),
            })
        log.info("Reddit search '%s': %d results", query[:50], len(posts))
        return posts
    except Exception:
        log.exception("Reddit search failed for '%s'", query[:50])
        return []


def fetch_posts(subreddit_name: str, limit: int = 25) -> list[dict]:
    """Fetch new posts from a public subreddit using Reddit's public JSON API.
    No credentials required. Fetches from any active subreddit regardless of size.
    """
    slug = subreddit_name.lstrip("/").removeprefix("r/").strip()
    if not slug:
        return []

    url = f"https://www.reddit.com/r/{slug}/new.json"
    try:
        resp = httpx.get(url, headers=_HEADERS, params={"limit": limit}, timeout=15, follow_redirects=True)
        if resp.status_code == 404:
            log.warning("Reddit r/%s not found or private", slug)
            return []
        resp.raise_for_status()

        posts = []
        for child in resp.json().get("data", {}).get("children", []):
            p = child.get("data", {})
            body = p.get("title", "")
            if p.get("selftext"):
                body += f"\n\n{p['selftext']}"
            author = p.get("author") or ""
            posts.append({
                "external_id": p["id"],
                "content": body,
                "source_url": f"https://reddit.com{p.get('permalink', '')}" if p.get("permalink") else None,
                "author_name": author or None,
                "author_username": author or None,
                "author_url": f"https://reddit.com/u/{author}" if author and author != "[deleted]" else None,
            })

        log.info("Reddit r/%s: fetched %d posts", slug, len(posts))
        return posts
    except Exception:
        log.exception("Reddit fetch failed for r/%s", slug)
        return []

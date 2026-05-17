import logging
import time
import httpx

from backend.database import settings

log = logging.getLogger(__name__)

_FALLBACK_HEADERS = {"User-Agent": "MarketingMonitor/1.0 by u/marketingmonitorbot"}

# --------------------------------------------------------------------------- #
# OAuth token cache
# --------------------------------------------------------------------------- #
_token_cache: dict = {"token": None, "expires_at": 0.0}


def _get_oauth_token() -> str | None:
    """Fetch (or return cached) a Reddit OAuth token using client credentials."""
    client_id = settings.REDDIT_CLIENT_ID
    client_secret = settings.REDDIT_CLIENT_SECRET
    if not client_id or not client_secret:
        return None

    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    try:
        resp = httpx.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": _FALLBACK_HEADERS["User-Agent"]},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + data.get("expires_in", 3600)
        log.info("Reddit OAuth token refreshed (expires in %ds)", data.get("expires_in", 3600))
        return _token_cache["token"]
    except Exception:
        log.exception("Reddit OAuth token fetch failed")
        return None


def _make_client() -> tuple[httpx.Client, str]:
    """Return (client, base_url). Uses OAuth if credentials are configured."""
    token = _get_oauth_token()
    if token:
        client = httpx.Client(
            headers={
                "User-Agent": _FALLBACK_HEADERS["User-Agent"],
                "Authorization": f"bearer {token}",
            }
        )
        return client, "https://oauth.reddit.com"
    # Fall back to public API (may 403 on some hosting providers)
    client = httpx.Client(headers=_FALLBACK_HEADERS)
    return client, "https://www.reddit.com"


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #

def search_posts(
    query: str,
    limit: int = 25,
    sort: str = "new",
    time_filter: str = "week",
    max_age_days: int | None = 3,
) -> list[dict]:
    """Search Reddit-wide for posts matching a query phrase.

    time_filter: Reddit time bucket passed to the API (hour/day/week/month/year/all).
    max_age_days: if set, client-side filter to posts no older than this many days.
                  Use this to e.g. cap to 3 days while still sending t=week to the API.
    """
    import time as _time
    client, base = _make_client()
    try:
        params: dict = {"q": query, "sort": sort, "limit": limit, "type": "link"}
        if time_filter:
            params["t"] = time_filter
        resp = client.get(
            f"{base}/search.json",
            params=params,
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code == 403:
            log.warning("Reddit search 403 — OAuth credentials may be missing or invalid")
            return []
        if resp.status_code != 200:
            log.warning("Reddit search returned %d for '%s'", resp.status_code, query[:50])
            return []
        cutoff = _time.time() - (max_age_days * 86400) if max_age_days else 0
        posts = []
        for child in resp.json().get("data", {}).get("children", []):
            p = child.get("data", {})
            created = float(p.get("created_utc", 0))
            if cutoff and created < cutoff:
                continue  # older than max_age_days — skip
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
                "created_utc": created,
            })
        log.info("Reddit search '%s' (t=%s, max_age=%sd): %d results", query[:50], time_filter, max_age_days, len(posts))
        return posts
    except Exception:
        log.exception("Reddit search failed for '%s'", query[:50])
        return []
    finally:
        client.close()


def fetch_posts(subreddit_name: str, limit: int = 25) -> list[dict]:
    """Fetch new posts from a subreddit. Uses OAuth API when credentials are set."""
    slug = subreddit_name.lstrip("/").removeprefix("r/").strip()
    if not slug:
        return []

    client, base = _make_client()
    try:
        resp = client.get(
            f"{base}/r/{slug}/new.json",
            params={"limit": limit},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code == 403:
            log.warning("Reddit r/%s 403 — OAuth credentials may be missing or invalid", slug)
            return []
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
    finally:
        client.close()

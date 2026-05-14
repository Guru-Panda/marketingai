"""
LinkedIn channel monitor.

Strategy:
  1. If the channel URL points to a public company page, scrape its posts feed.
  2. Fall back to a DuckDuckGo lite search scoped to linkedin.com so we surface
     public post excerpts without needing auth.

LinkedIn's content is heavily auth-gated, so expect a mix of real snippets and
"sign in to view" blanks. Posts that pass the intent threshold still get saved.
"""
import hashlib
import logging
import re

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_COMPANY_RE = re.compile(r"linkedin\.com/company/([\w%-]+)", re.I)
_GROUP_RE = re.compile(r"linkedin\.com/groups/(\d+)", re.I)


def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.md5(text.encode()).hexdigest()[:16]}"


def _scrape_company_posts(slug: str, limit: int) -> list[dict]:
    """Attempt to fetch public posts from a LinkedIn company page."""
    url = f"https://www.linkedin.com/company/{slug}/posts/"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code in (401, 403, 999):
            log.debug("LinkedIn company page auth-gated for %s", slug)
            return []
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        posts = []
        for el in soup.select("p, [data-test-id='main-feed-activity-card__commentary']"):
            text = el.get_text(separator=" ").strip()
            if len(text) < 40:
                continue
            posts.append({
                "external_id": _stable_id("li-co", text),
                "content": text,
                "source_url": url,
                "author_name": None,
                "author_username": None,
                "author_url": None,
            })
            if len(posts) >= limit:
                break

        log.info("LinkedIn company/%s: scraped %d posts", slug, len(posts))
        return posts
    except Exception:
        log.debug("LinkedIn company scrape failed for %s", slug)
        return []


def _search_ddg(query: str, limit: int) -> list[dict]:
    """Search DuckDuckGo lite for LinkedIn posts matching the query."""
    try:
        resp = httpx.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query},
            headers=_HEADERS,
            timeout=20,
            follow_redirects=True,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        posts = []

        # DDG lite result structure: alternating <tr> rows with snippet + URL
        for tr in soup.select("tr"):
            snippet_el = tr.select_one(".result-snippet")
            link_el = tr.select_one("a.result-link")
            if not snippet_el:
                continue
            text = snippet_el.get_text(separator=" ").strip()
            href = link_el.get("href", "") if link_el else ""
            if not text or len(text) < 30:
                continue

            posts.append({
                "external_id": _stable_id("li-ddg", text),
                "content": text,
                "source_url": href or None,
                "author_name": None,
                "author_username": None,
                "author_url": None,
            })
            if len(posts) >= limit:
                break

        log.info("LinkedIn DDG search [%s]: %d results", query[:60], len(posts))
        return posts
    except Exception:
        log.debug("LinkedIn DDG search failed for query: %s", query[:60])
        return []


def fetch_posts(
    channel_name: str,
    channel_url: str | None,
    keywords: list[str],
    limit: int = 20,
) -> list[dict]:
    """Return posts for a LinkedIn channel, trying company page then DDG search."""
    posts: list[dict] = []

    # Try company page scrape first if URL contains a company slug
    if channel_url:
        m = _COMPANY_RE.search(channel_url)
        if m:
            posts = _scrape_company_posts(m.group(1), limit)

    # Fall back to (or supplement with) a DuckDuckGo search
    if len(posts) < limit:
        kw_str = " ".join(keywords[:6]) if keywords else channel_name
        query = f'site:linkedin.com {kw_str}'
        ddg_posts = _search_ddg(query, limit - len(posts))
        seen = {p["external_id"] for p in posts}
        for p in ddg_posts:
            if p["external_id"] not in seen:
                posts.append(p)
                seen.add(p["external_id"])

    return posts[:limit]

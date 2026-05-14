"""
Quora lead monitor.
Searches DuckDuckGo for site:quora.com results matching buyer phrases/keywords.
Captures both question-askers (buying intent) and expert answerers (decision-makers).
"""
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
_DDG_URL = "https://lite.duckduckgo.com/lite/"


def _ddg_search(query: str, limit: int = 15) -> list[dict]:
    try:
        resp = httpx.post(
            _DDG_URL,
            data={"q": query},
            headers=_HEADERS,
            timeout=20,
            follow_redirects=True,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for tr in soup.select("tr"):
            snippet_el = tr.select_one(".result-snippet")
            link_el = tr.select_one("a.result-link")
            if not snippet_el:
                continue
            text = snippet_el.get_text(separator=" ").strip()
            href = link_el.get("href", "") if link_el else ""
            if not text or len(text) < 30:
                continue
            if "quora.com" not in href:
                continue
            uid = hashlib.md5((href or text).encode()).hexdigest()[:16]
            results.append({
                "external_id": f"quora-{uid}",
                "content": text,
                "source_url": href or None,
                "author_name": None,
                "author_username": None,
                "author_url": None,
            })
            if len(results) >= limit:
                break
        log.info("Quora DDG search [%s]: %d results", query[:60], len(results))
        return results
    except Exception:
        log.exception("Quora DDG search failed for: %s", query[:60])
        return []


def fetch_posts(
    keywords: list[str],
    buyer_phrases: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search Quora via DDG for buyer intent posts matching keywords/phrases."""
    phrases = list(buyer_phrases or [])[:3]  # max 3 phrase queries
    kw_query = " ".join(keywords[:5]) if keywords else ""

    queries = [f"site:quora.com {p}" for p in phrases]
    if kw_query:
        queries.append(f"site:quora.com {kw_query}")

    seen: set[str] = set()
    posts: list[dict] = []

    for q in queries[:4]:
        for post in _ddg_search(q, limit=15):
            if post["external_id"] not in seen:
                seen.add(post["external_id"])
                posts.append(post)
                if len(posts) >= limit:
                    return posts

    return posts

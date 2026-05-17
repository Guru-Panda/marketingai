"""
IndieHackers lead monitor.
Uses IndieHackers' public RSS feed — no DDG, no API key, works on Railway.

The feed surfaces recent community posts and articles. We filter them
client-side for keyword / buyer-phrase matches before scoring.
"""
import hashlib
import logging
import re
import xml.etree.ElementTree as ET

import httpx

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# IndieHackers public RSS / Atom feeds
_FEEDS = [
    "https://www.indiehackers.com/feed.xml",          # main community feed
    "https://www.indiehackers.com/posts/feed.xml",    # posts feed (alt URL)
]

# XML namespaces that may appear in Atom / RSS hybrid feeds
_NS = {
    "atom":    "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc":      "http://purl.org/dc/elements/1.1/",
}


def _stable_id(url: str, title: str) -> str:
    key = url or title
    return f"ih-{hashlib.md5(key.encode()).hexdigest()[:16]}"


def _text(el, *paths: str) -> str:
    """Try multiple child tag paths and return the first non-empty text."""
    for path in paths:
        child = el.find(path, _NS)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _fetch_feed(url: str) -> list[dict]:
    """Fetch one RSS/Atom feed and return a list of raw post dicts."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        log.warning("IH feed unavailable: %s", url)
        return []

    posts = []

    # ── RSS 2.0 ──────────────────────────────────────────────────────────────
    for item in root.findall(".//item"):
        title   = _text(item, "title")
        desc    = _text(item, "description", "content:encoded")
        link    = _text(item, "link")
        author  = _text(item, "author", "dc:creator")
        content = f"{title}\n\n{desc}".strip() if desc else title
        if not content:
            continue
        posts.append({
            "external_id": _stable_id(link, title),
            "content":     content[:3000],
            "source_url":  link or None,
            "author_name": author or None,
            "author_username": None,
            "author_url":  None,
        })

    # ── Atom ─────────────────────────────────────────────────────────────────
    for entry in root.findall("atom:entry", _NS):
        title  = _text(entry, "atom:title", "title")
        desc   = _text(entry, "atom:summary", "atom:content", "summary", "content")
        link_el = entry.find("atom:link", _NS) or entry.find("link")
        link   = (link_el.get("href") if link_el is not None else None) or ""
        author_el = entry.find("atom:author/atom:name", _NS) or entry.find("author/name")
        author = author_el.text.strip() if author_el is not None and author_el.text else None
        content = f"{title}\n\n{desc}".strip() if desc else title
        if not content:
            continue
        posts.append({
            "external_id": _stable_id(link, title),
            "content":     content[:3000],
            "source_url":  link or None,
            "author_name": author,
            "author_username": None,
            "author_url":  None,
        })

    log.info("IH feed %s: %d items", url, len(posts))
    return posts


def _keyword_match(text: str, keywords: list[str], phrases: list[str]) -> bool:
    """Return True if the text contains at least one keyword or buyer phrase."""
    lower = text.lower()
    for phrase in phrases:
        if phrase.lower() in lower:
            return True
    for kw in keywords:
        # whole-word match for short keywords to reduce noise
        pattern = r'\b' + re.escape(kw.lower()) + r'\b'
        if re.search(pattern, lower):
            return True
    return False


def fetch_posts(
    keywords: list[str],
    buyer_phrases: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Return IH posts that match at least one keyword or buyer phrase.

    Pulls from IndieHackers' public RSS feed — no external search engine needed.
    """
    phrases = list(buyer_phrases or [])
    if not keywords and not phrases:
        return []

    seen: set[str] = set()
    matched: list[dict] = []

    for feed_url in _FEEDS:
        for post in _fetch_feed(feed_url):
            ext_id = post["external_id"]
            if ext_id in seen:
                continue
            if not _keyword_match(post["content"], keywords, phrases):
                continue
            seen.add(ext_id)
            matched.append(post)
            if len(matched) >= limit:
                return matched
        if len(matched) >= limit:
            break

    log.info("IH keyword filter (%s): %d/%d posts matched",
             ", ".join(keywords[:3]), len(matched), limit)
    return matched

import hashlib
import logging
import re
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketingMonitor/1.0)"}
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
_MIN_SUBSCRIBERS = 1_000
_DDG_URL = "https://lite.duckduckgo.com/lite/"


def search_posts(query: str, limit: int = 15) -> list[dict]:
    """Search public Telegram content via DuckDuckGo site:t.me.

    Returns post-like dicts from Telegram channel snippets found in DDG results.
    No bot token required — surfaces public channel content indexed by search engines.
    """
    try:
        resp = httpx.post(
            _DDG_URL,
            data={"q": f"site:t.me {query}"},
            headers=_BROWSER_HEADERS,
            timeout=20,
            follow_redirects=True,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = []
        seen: set[str] = set()
        for tr in soup.select("tr"):
            snippet_el = tr.select_one(".result-snippet")
            link_el = tr.select_one("a.result-link")
            if not snippet_el:
                continue
            text = snippet_el.get_text(separator=" ").strip()
            href = link_el.get("href", "") if link_el else ""
            title = link_el.get_text(strip=True) if link_el else ""
            if not text or len(text) < 30:
                continue
            if "t.me" not in href:
                continue
            uid = hashlib.md5((href or text).encode()).hexdigest()[:16]
            ext_id = f"tg-{uid}"
            if ext_id in seen:
                continue
            seen.add(ext_id)
            content = f"{title}\n\n{text}".strip() if title else text
            posts.append({
                "external_id": ext_id,
                "content": content,
                "source_url": href or None,
                "author_name": None,
                "author_username": None,
                "author_url": None,
            })
            if len(posts) >= limit:
                break
        log.info("Telegram DDG search '%s': %d results", query[:60], len(posts))
        return posts
    except Exception:
        log.exception("Telegram DDG search failed for '%s'", query[:60])
        return []


def _parse_subscriber_count(soup: BeautifulSoup) -> int | None:
    """
    Extract member/subscriber count from the t.me/s/ page header.
    Telegram renders counts like "1 234 subscribers", "12.5K members", "1,234 subscribers".
    """
    for el in soup.select(".tgme_page_extra, .tgme_channel_info_counter"):
        text = el.get_text(strip=True).lower()
        if "subscriber" in text or "member" in text:
            # Strip labels and whitespace, keep digits, dots, K/M suffixes
            raw = re.sub(r"[subscribers|members|\s,]", "", text)
            raw = raw.strip()
            try:
                if raw.endswith("k"):
                    return int(float(raw[:-1]) * 1_000)
                if raw.endswith("m"):
                    return int(float(raw[:-1]) * 1_000_000)
                return int(raw)
            except ValueError:
                pass
    return None


def fetch_channel_posts(channel_username: str, limit: int = 20) -> list[dict]:
    """Scrape recent posts from a public Telegram channel via t.me/s/.
    Skips channels with fewer than 1,000 subscribers.
    No bot token required — only works for public channels.
    """
    username = channel_username.lstrip("@").strip()
    if not username:
        return []

    url = f"https://t.me/s/{username}"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code == 404:
            log.warning("Telegram channel @%s not found or private", username)
            return []
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        subscribers = _parse_subscriber_count(soup)
        if subscribers is not None and subscribers < _MIN_SUBSCRIBERS:
            log.warning(
                "Telegram @%s skipped — only %d subscribers (min %d)",
                username, subscribers, _MIN_SUBSCRIBERS,
            )
            return []

        posts = []

        for msg in soup.select(".tgme_widget_message"):
            msg_id = (msg.get("data-post") or "").split("/")[-1]
            text_el = msg.select_one(".tgme_widget_message_text")
            if not msg_id or not text_el:
                continue
            text = text_el.get_text(separator="\n").strip()
            if not text:
                continue

            author_el = msg.select_one(".tgme_widget_message_author_name")
            author_link_el = msg.select_one(".tgme_widget_message_owner_name a")
            author_name = None
            author_url = None
            if author_el:
                author_name = author_el.get_text(strip=True) or None
            if author_link_el:
                author_url = author_link_el.get("href") or None

            posts.append({
                "external_id": msg_id,
                "content": text,
                "source_url": f"https://t.me/{username}/{msg_id}",
                "author_name": author_name,
                "author_username": author_name,
                "author_url": author_url,
            })

        posts = posts[:limit]
        log.info(
            "Telegram @%s (%s subscribers): fetched %d posts",
            username, f"{subscribers:,}" if subscribers else "?", len(posts),
        )
        return posts
    except Exception:
        log.exception("Telegram fetch failed for @%s", username)
        return []

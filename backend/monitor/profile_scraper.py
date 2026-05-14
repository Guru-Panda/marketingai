"""
Fetch author profile data from each platform.
Called only for posts that already passed the intent threshold,
so the extra network calls are limited to genuine leads.
"""
import logging
import re
import httpx
from bs4 import BeautifulSoup
from backend.database import settings

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketingMonitor/1.0)"}


def fetch_reddit_author(username: str) -> list[str]:
    """Return text snippets from a Reddit user's profile bio + recent activity."""
    if not username or username in ("[deleted]", "AutoModerator"):
        return []

    texts: list[str] = []

    # 1. Profile bio (subreddit description field is where users write their bio)
    try:
        resp = httpx.get(
            f"https://www.reddit.com/user/{username}/about.json",
            headers=_HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            bio = (data.get("subreddit") or {}).get("public_description", "").strip()
            if bio:
                texts.append(f"[Profile bio]\n{bio}")
                # Look for URLs in the bio and scrape contact info from the first one
                bio_urls = re.findall(r"https?://\S+", bio)
                for bio_url in bio_urls[:1]:
                    contact_snippets = fetch_website_contact(bio_url)
                    texts.extend(contact_snippets)
    except Exception:
        log.debug("Reddit profile fetch failed for u/%s", username)

    # 2. Recent comments — people often mention contact info in replies
    try:
        resp = httpx.get(
            f"https://www.reddit.com/user/{username}/comments.json",
            headers=_HEADERS,
            params={"limit": 20},
            timeout=12,
        )
        if resp.status_code == 200:
            for child in resp.json().get("data", {}).get("children", []):
                body = (child.get("data") or {}).get("body", "").strip()
                if body:
                    texts.append(body[:800])
    except Exception:
        log.debug("Reddit comments fetch failed for u/%s", username)

    # 3. Recent submitted posts — titles + selftext
    try:
        resp = httpx.get(
            f"https://www.reddit.com/user/{username}/submitted.json",
            headers=_HEADERS,
            params={"limit": 10},
            timeout=12,
        )
        if resp.status_code == 200:
            for child in resp.json().get("data", {}).get("children", []):
                p = child.get("data") or {}
                post_text = p.get("title", "")
                if p.get("selftext"):
                    post_text += f"\n{p['selftext']}"
                if post_text.strip():
                    texts.append(post_text.strip()[:800])
    except Exception:
        log.debug("Reddit submissions fetch failed for u/%s", username)

    log.info("Reddit u/%s: collected %d text snippets for enrichment", username, len(texts))
    return texts


def fetch_telegram_profile(username: str) -> list[str]:
    """Return text snippets from a Telegram user or channel's public profile page."""
    if not username:
        return []

    handle = username.lstrip("@").strip()
    texts: list[str] = []

    try:
        resp = httpx.get(
            f"https://t.me/{handle}",
            headers=_HEADERS,
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Bio / description
        for sel in [".tgme_page_description", ".tgme_channel_info_description"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if text:
                    texts.append(f"[Profile bio]\n{text}")
                break

        # Extra info block (sometimes contains website/email)
        for el in soup.select(".tgme_page_extra"):
            text = el.get_text(strip=True)
            if text:
                texts.append(text)

    except Exception:
        log.debug("Telegram profile fetch failed for @%s", handle)

    log.info("Telegram @%s: collected %d text snippets for enrichment", handle, len(texts))
    return texts


def fetch_discord_user_history(channel_id: str, author_id: str) -> list[str]:
    """Fetch recent channel messages and return those authored by a specific user."""
    if not settings.DISCORD_BOT_TOKEN or not author_id or not channel_id:
        return []

    texts: list[str] = []
    try:
        resp = httpx.get(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
            params={"limit": 100},
            timeout=15,
        )
        resp.raise_for_status()
        for msg in resp.json():
            if msg.get("author", {}).get("id") == author_id:
                content = (msg.get("content") or "").strip()
                if content:
                    texts.append(content[:800])
    except Exception:
        log.debug("Discord user history fetch failed for %s in channel %s", author_id, channel_id)

    log.info(
        "Discord user %s in channel %s: found %d messages for enrichment",
        author_id, channel_id, len(texts),
    )
    return texts


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_SKIP_DOMAINS = {"reddit.com", "twitter.com", "instagram.com", "facebook.com",
                 "t.me", "telegram.me", "discord.com", "discord.gg", "youtube.com"}


def fetch_website_contact(url: str) -> list[str]:
    """Visit a website and scrape contact/about pages for email addresses."""
    if not url or not url.startswith("http"):
        return []
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower().lstrip("www.")
        if any(skip in domain for skip in _SKIP_DOMAINS):
            return []
    except Exception:
        return []

    texts: list[str] = []
    visited = 0

    def _scrape(page_url: str) -> None:
        nonlocal visited
        if visited >= 3:
            return
        visited += 1
        try:
            r = httpx.get(page_url, headers=_HEADERS, timeout=10, follow_redirects=True)
            if r.status_code != 200:
                return
            page_text = BeautifulSoup(r.text, "html.parser").get_text(separator=" ")
            emails = _EMAIL_RE.findall(page_text)
            for em in emails:
                if em not in ("example@example.com", "email@email.com"):
                    texts.append(f"[Website contact]\n{em}")
        except Exception:
            pass

    base = url.rstrip("/")
    _scrape(base)
    for path in ("/contact", "/about", "/team", "/contact-us"):
        _scrape(base + path)

    log.info("Website %s: found %d contact snippets", url, len(texts))
    return texts


def hunt_email_hunter(full_name: str, domain: str) -> str | None:
    """Use Hunter.io email finder API to find email for a person at a domain."""
    from backend.database import settings
    if not settings.HUNTER_API_KEY or not full_name or not domain:
        return None
    parts = full_name.strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    if not first or not last:
        return None
    try:
        resp = httpx.get(
            "https://api.hunter.io/v2/email-finder",
            params={
                "first_name": first,
                "last_name": last,
                "domain": domain,
                "api_key": settings.HUNTER_API_KEY,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            email = resp.json().get("data", {}).get("email")
            if email:
                log.debug("Hunter.io found %s for %s @ %s", email, full_name, domain)
                return email
    except Exception:
        log.debug("Hunter.io lookup failed for %s @ %s", full_name, domain)
    return None

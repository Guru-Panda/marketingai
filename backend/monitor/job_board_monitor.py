"""
Job board monitor.

Fetches recent job listings from common job boards. Job postings signal buying
intent: a company hiring a "Customer Success Manager" is likely evaluating CS
tooling, a company hiring "Data Engineer" may need analytics platforms, etc.

Supported boards (auto-detected from channel URL / name):
  - Indeed (RSS feed, global)
  - Internshala (HTML, India-focused)
  - Naukri (HTML, India-focused)
  - CutShort (HTML, India-focused)
  - WellFound / AngelList (HTML, startup-focused)
  - Generic RSS fallback for any board that exposes /rss or /feed
"""
import hashlib
import logging
import re
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.md5(text.encode()).hexdigest()[:16]}"


# ── Board-specific fetchers ───────────────────────────────────────────────────

def _indeed_rss(keywords: list[str], limit: int) -> list[dict]:
    """Fetch job listings via Indeed's public RSS feed."""
    q = " ".join(keywords[:5])
    url = "https://www.indeed.com/rss"
    try:
        resp = httpx.get(url, params={"q": q, "limit": min(limit, 25)},
                         headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        posts = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(separator=" ").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            author_el = item.find("{https://www.indeed.com/rss}author") or item.find("author")
            author = (author_el.text or "").strip() if author_el is not None else None
            company_el = item.find("{https://www.indeed.com/rss}company")
            company = (company_el.text or "").strip() if company_el is not None else None
            location_el = item.find("{https://www.indeed.com/rss}city")
            location = (location_el.text or "").strip() if location_el is not None else None

            content = f"{title}"
            if company:
                content += f" at {company}"
            if desc:
                content += f"\n\n{desc}"

            if not content.strip():
                continue

            posts.append({
                "external_id": _stable_id("indeed", guid or content),
                "content": content,
                "source_url": link or None,
                "author_name": company or None,
                "author_username": None,
                "author_url": None,
                "author_location": location or None,
            })
            if len(posts) >= limit:
                break

        log.info("Indeed RSS [%s]: %d jobs", q, len(posts))
        return posts
    except Exception:
        log.debug("Indeed RSS failed for query '%s'", q)
        return []


def _internshala(keywords: list[str], limit: int) -> list[dict]:
    """Scrape Internshala public job search listings."""
    q = "-".join(keywords[:3]).lower().replace(" ", "-") if keywords else "jobs"
    url = f"https://internshala.com/jobs/keywords-{q}/"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = []
        for card in soup.select(".individual_internship, .internship-card"):
            title_el = card.select_one(".profile, .job-title, h3")
            company_el = card.select_one(".company_name, .company-name")
            loc_el = card.select_one(".location_link, .location")
            desc_el = card.select_one(".job_description, .about-company-text")

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            location = loc_el.get_text(strip=True) if loc_el else ""
            desc = desc_el.get_text(separator=" ").strip() if desc_el else ""

            if not title:
                continue

            content = title
            if company:
                content += f" at {company}"
            if location:
                content += f" ({location})"
            if desc:
                content += f"\n\n{desc[:500]}"

            link_el = card.select_one("a[href]")
            href = link_el.get("href", "") if link_el else ""
            source_url = f"https://internshala.com{href}" if href.startswith("/") else href or None

            posts.append({
                "external_id": _stable_id("internshala", content),
                "content": content,
                "source_url": source_url,
                "author_name": company or None,
                "author_username": None,
                "author_url": None,
                "author_location": location or None,
            })
            if len(posts) >= limit:
                break

        log.info("Internshala [%s]: %d jobs", q, len(posts))
        return posts
    except Exception:
        log.debug("Internshala scrape failed for query '%s'", q)
        return []


def _naukri(keywords: list[str], limit: int) -> list[dict]:
    """Scrape Naukri public job listings."""
    q = "-".join(k.replace(" ", "-") for k in keywords[:3]) if keywords else "jobs"
    url = f"https://www.naukri.com/{q}-jobs"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = []
        for card in soup.select("article.jobTuple, .srp-jobtuple-wrapper"):
            title_el = card.select_one("a.title, .row1 a")
            company_el = card.select_one("a.comp-name, .comp-name")
            loc_el = card.select_one("li.location span, .loc")
            desc_el = card.select_one(".job-description, .row3")

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            location = loc_el.get_text(strip=True) if loc_el else ""
            desc = desc_el.get_text(separator=" ").strip() if desc_el else ""

            if not title:
                continue

            content = title
            if company:
                content += f" at {company}"
            if location:
                content += f" ({location})"
            if desc:
                content += f"\n\n{desc[:500]}"

            href = title_el.get("href", "") if title_el else ""
            source_url = href if href.startswith("http") else None

            posts.append({
                "external_id": _stable_id("naukri", content),
                "content": content,
                "source_url": source_url,
                "author_name": company or None,
                "author_username": None,
                "author_url": None,
                "author_location": location or None,
            })
            if len(posts) >= limit:
                break

        log.info("Naukri [%s]: %d jobs", q, len(posts))
        return posts
    except Exception:
        log.debug("Naukri scrape failed for query '%s'", q)
        return []


def _cutshort(keywords: list[str], limit: int) -> list[dict]:
    """Scrape CutShort public job listings."""
    q = " ".join(keywords[:4]) if keywords else ""
    url = "https://cutshort.io/jobs"
    try:
        resp = httpx.get(url, params={"q": q} if q else {}, headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = []
        for card in soup.select(".job-card, [class*='JobCard'], article"):
            title_el = card.select_one("h2, h3, .job-title, [class*='title']")
            company_el = card.select_one(".company-name, [class*='company']")
            loc_el = card.select_one(".location, [class*='location']")
            desc_el = card.select_one(".description, [class*='desc']")

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            location = loc_el.get_text(strip=True) if loc_el else ""
            desc = desc_el.get_text(separator=" ").strip() if desc_el else ""

            if not title or len(title) < 3:
                continue

            content = title
            if company:
                content += f" at {company}"
            if location:
                content += f" ({location})"
            if desc:
                content += f"\n\n{desc[:500]}"

            href = card.select_one("a[href]")
            href = href.get("href", "") if href else ""
            source_url = f"https://cutshort.io{href}" if href.startswith("/") else href or None

            posts.append({
                "external_id": _stable_id("cutshort", content),
                "content": content,
                "source_url": source_url,
                "author_name": company or None,
                "author_username": None,
                "author_url": None,
                "author_location": location or None,
            })
            if len(posts) >= limit:
                break

        log.info("CutShort [%s]: %d jobs", q, len(posts))
        return posts
    except Exception:
        log.debug("CutShort scrape failed")
        return []


def _generic_rss(url: str, limit: int) -> list[dict]:
    """Try to fetch an RSS/Atom feed from a job board URL."""
    for feed_path in ("", "/rss", "/feed", "/jobs/rss", "/jobs.rss"):
        feed_url = url.rstrip("/") + feed_path
        try:
            resp = httpx.get(feed_url, headers=_HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                continue
            ct = resp.headers.get("content-type", "")
            if "xml" not in ct and "rss" not in ct and not resp.text.strip().startswith("<"):
                continue

            root = ET.fromstring(resp.text)
            posts = []
            for item in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
                title = (item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                desc_raw = (item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
                desc = BeautifulSoup(desc_raw, "html.parser").get_text(separator=" ").strip()
                link = (item.findtext("link") or item.findtext("{http://www.w3.org/2005/Atom}id") or "").strip()
                guid = (item.findtext("guid") or link).strip()

                content = title
                if desc:
                    content += f"\n\n{desc[:600]}"
                if not content.strip():
                    continue

                posts.append({
                    "external_id": _stable_id("rss", guid or content),
                    "content": content,
                    "source_url": link or None,
                    "author_name": None,
                    "author_username": None,
                    "author_url": None,
                })
                if len(posts) >= limit:
                    break

            if posts:
                log.info("Generic RSS [%s]: %d items", feed_url, len(posts))
                return posts
        except Exception:
            continue

    return []


# ── Proactive search sources ──────────────────────────────────────────────────

def _remoteok(keywords: list[str], buyer_phrases: list[str], limit: int) -> list[dict]:
    """Fetch job listings from RemoteOK's free public JSON API.

    Tags the search with the top keywords. No auth required.
    https://remoteok.com/api
    """
    tags = "+".join(k.lower().replace(" ", "-") for k in keywords[:3]) if keywords else ""
    url = f"https://remoteok.com/api?tags={tags}" if tags else "https://remoteok.com/api"
    try:
        resp = httpx.get(
            url,
            headers={**_HEADERS, "Accept": "application/json"},
            timeout=20,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
        # First item is a legal notice dict, skip it
        posts = []
        for item in data:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            title = (item.get("position") or "").strip()
            company = (item.get("company") or "").strip()
            description = BeautifulSoup(item.get("description") or "", "html.parser").get_text(separator=" ").strip()
            location = (item.get("location") or "Remote").strip()
            tags_list = item.get("tags") or []

            if not title:
                continue

            content = title
            if company:
                content += f" at {company}"
            if location:
                content += f" ({location})"
            if tags_list:
                content += f"\nSkills: {', '.join(str(t) for t in tags_list[:8])}"
            if description:
                content += f"\n\n{description[:600]}"

            posts.append({
                "external_id": f"remoteok-{item['id']}",
                "content": content,
                "source_url": item.get("url") or f"https://remoteok.com/remote-jobs/{item['id']}",
                "author_name": company or None,
                "author_username": None,
                "author_url": None,
                "author_location": location or None,
            })
            if len(posts) >= limit:
                break

        log.info("RemoteOK [%s]: %d jobs", tags, len(posts))
        return posts
    except Exception:
        log.debug("RemoteOK failed for tags '%s'", tags)
        return []


def _hn_hiring(keywords: list[str], buyer_phrases: list[str], limit: int) -> list[dict]:
    """Search the monthly HN 'Who is Hiring?' thread via Algolia.

    Each comment is a job posting from a company. Good signal for B2B tools —
    companies actively hiring reveal their tech stack, pain points, and budget.
    """
    query = " ".join(keywords[:4]) if keywords else " ".join(
        w for p in buyer_phrases[:2] for w in p.split()[:3]
    )
    if not query.strip():
        return []
    try:
        resp = httpx.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "query": query,
                "tags": "comment,author_whoishiring",
                "hitsPerPage": min(limit, 30),
            },
            headers={"User-Agent": "MarketingMonitor/1.0"},
            timeout=15,
        )
        resp.raise_for_status()
        posts = []
        seen: set[str] = set()
        for hit in resp.json().get("hits", []):
            obj_id = hit.get("objectID") or ""
            text = (hit.get("comment_text") or "").strip()
            if not obj_id or not text or len(text) < 40:
                continue
            ext_id = f"hn-hiring-{obj_id}"
            if ext_id in seen:
                continue
            seen.add(ext_id)
            # Strip HTML tags that sometimes appear in HN comments
            text = re.sub(r"<[^>]+>", " ", text)
            posts.append({
                "external_id": ext_id,
                "content": text[:2000],
                "source_url": f"https://news.ycombinator.com/item?id={obj_id}",
                "author_name": None,
                "author_username": hit.get("author") or None,
                "author_url": (
                    f"https://news.ycombinator.com/user?id={hit['author']}"
                    if hit.get("author") else None
                ),
            })
            if len(posts) >= limit:
                break
        log.info("HN Hiring [%s]: %d results", query[:60], len(posts))
        return posts
    except Exception:
        log.debug("HN Hiring search failed for '%s'", query[:60])
        return []


def search_posts(
    keywords: list[str],
    buyer_phrases: list[str] | None = None,
    limit: int = 25,
) -> list[dict]:
    """Proactive job board search combining RemoteOK + HN Hiring + Indeed.

    Called by the sync job for each strategy to find companies whose job
    postings indicate they need the user's product/service.
    """
    phrases = list(buyer_phrases or [])
    seen: set[str] = set()
    combined: list[dict] = []

    sources = [
        lambda: _remoteok(keywords, phrases, limit),
        lambda: _hn_hiring(keywords, phrases, limit),
        lambda: _indeed_rss(keywords, limit),
    ]

    for source_fn in sources:
        for post in source_fn():
            if post["external_id"] not in seen:
                seen.add(post["external_id"])
                combined.append(post)
        if len(combined) >= limit:
            break

    return combined[:limit]


# ── Board router ──────────────────────────────────────────────────────────────

_BOARD_PATTERNS = {
    "indeed": _indeed_rss,
    "internshala": _internshala,
    "naukri": _naukri,
    "cutshort": _cutshort,
}


def fetch_posts(
    channel_name: str,
    channel_url: str | None,
    keywords: list[str],
    limit: int = 20,
) -> list[dict]:
    """Route to the right scraper based on channel name / URL."""
    name_lower = channel_name.lower()

    for board_key, fetcher in _BOARD_PATTERNS.items():
        if board_key in name_lower or (channel_url and board_key in channel_url.lower()):
            posts = fetcher(keywords, limit)
            if posts:
                return posts
            break

    # Generic RSS fallback
    if channel_url:
        posts = _generic_rss(channel_url, limit)
        if posts:
            return posts

    # Last resort: Indeed with the keywords (always has something)
    return _indeed_rss(keywords, limit)

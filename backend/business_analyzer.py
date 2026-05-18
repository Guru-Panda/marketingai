import json
import logging
import re
import anthropic
import httpx
from bs4 import BeautifulSoup
from backend.database import settings

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _parse_json(text: str) -> dict:
    """Extract and parse the first JSON object from Claude's response.

    Handles:
    - Plain JSON
    - JSON wrapped in ```json ... ``` or ``` ... ``` fences
    - JSON embedded in surrounding prose
    """
    text = text.strip()

    # 1. Try stripping code fences first
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 2. Try the raw text as-is
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Find the first {...} block in the text (handles prose wrappers)
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    log.error("_parse_json: could not extract JSON from response (length=%d)", len(text))
    raise ValueError(f"No valid JSON found in Claude response: {text[:300]}")


_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _scrape_one(url: str) -> str:
    """Try to fetch one URL and return cleaned visible text, or '' on failure."""
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True, headers=_SCRAPE_HEADERS)
        if resp.status_code >= 400:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        # Ignore Cloudflare/bot-challenge pages (very short or keyword-flagged)
        if len(text) < 100 or "enable javascript" in text.lower() or "checking your browser" in text.lower():
            return ""
        return text[:4000]
    except Exception:
        return ""


def _fetch_url_text(raw_url: str) -> str:
    """Fetch a webpage and return its visible text.

    Tries several URL variants in order until one succeeds:
    1. The URL exactly as given (with https:// prepended if missing)
    2. If www. prefix present → try without it
    3. If no www. prefix → try with it
    4. Root domain (drop any path) — useful when the homepage loads but a subpage 404s
    """
    if not raw_url.startswith("http"):
        raw_url = "https://" + raw_url

    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(raw_url)
    hostname = parsed.hostname or ""

    candidates: list[str] = [raw_url]

    # Toggle www
    if hostname.startswith("www."):
        no_www = urlunparse(parsed._replace(netloc=hostname[4:]))
        candidates.append(no_www)
    else:
        with_www = urlunparse(parsed._replace(netloc="www." + hostname))
        candidates.append(with_www)

    # Root domain (scheme + host only) if we have a path
    if parsed.path and parsed.path != "/":
        root = urlunparse(parsed._replace(path="/", query="", fragment=""))
        candidates.append(root)

    for url in candidates:
        text = _scrape_one(url)
        if text:
            log.info("_fetch_url_text: scraped %d chars from %s", len(text), url)
            return text

    log.warning("_fetch_url_text: all variants failed for %s", raw_url)
    return ""


def _enrich_user_text(user_text: str) -> str:
    """If the user mentioned a URL, fetch the page and prepend its content.

    If scraping fails entirely, still pass the URL to Claude so it can
    infer business context from the domain name.
    """
    url_pattern = re.compile(
        r"(https?://[^\s]+|www\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?|"
        r"[a-zA-Z0-9.-]+\.(?:com|co\.uk|io|ai|app|co|net|org|dev)(?:/[^\s]*)?)"
    )
    match = url_pattern.search(user_text)
    if not match:
        return user_text

    url = match.group(1)
    page_text = _fetch_url_text(url)

    if page_text:
        return (
            f"Website content scraped from {url}:\n{page_text}\n\n"
            f"Additional context from user: {user_text}"
        )

    # Scrape failed — pass URL as hint so Claude can infer from domain name
    log.info("_enrich_user_text: could not scrape %s, using as domain hint", url)
    return (
        f"The user's website URL: {url}\n"
        f"(Page could not be fetched — infer business context from the domain name.)\n\n"
        f"User's description: {user_text}"
    )


def analyze_business(user_text: str) -> dict:
    """Extract main_problem, ideal_customer, keywords, and buyer_phrases from free-form user text."""
    user_text = _enrich_user_text(user_text)
    prompt = f"""Analyze the following business description and extract structured information.

CRITICAL: You MUST always return a valid JSON object — even if the description is vague, sparse, or only a URL.
If you cannot determine a field with certainty, make a reasonable inference based on available context (domain name, keywords, etc.).
Never return an explanation or refusal — only JSON.

Return ONLY a valid JSON object with exactly these fields:
{{
  "main_problem": "<one sentence describing the core problem the business solves>",
  "ideal_customer": "<short description of the ideal customer profile>",
  "keywords": ["<5 to 10 relevant technical/niche keywords or short phrases>"],
  "buyer_phrases": [
    "<10 to 15 natural phrases that a potential BUYER would actually type in a forum post when they have this problem>",
    "Examples: 'where can I buy X in India', 'looking for a tool to manage Y', 'need help finding Z', 'recommend a good X for Y', 'any good sites for X', 'best X for small teams', 'struggling with Y', 'how do I find X'"
  ],
  "business_type": "<'b2b' if selling to businesses/teams, 'b2c' if selling to individual consumers, or 'mixed' if both>",
  "intent_threshold": <float — use 0.70 for b2b, 0.50 for b2c, 0.60 for mixed>
}}

IMPORTANT for buyer_phrases:
- These must sound like real user posts, NOT marketing copy
- They should reflect the pain/need from the buyer's perspective
- Include phrases with location if the business targets specific regions
- Mix question forms ("where can I..."), statement forms ("I need..."), and request forms ("recommend me...")
- Avoid jargon — use words a non-expert buyer would use

IMPORTANT for business_type and intent_threshold:
- b2b: the primary buyer is a business, team, or professional — set intent_threshold to 0.70
- b2c: the primary buyer is an individual consumer — set intent_threshold to 0.50
- mixed: the business serves both — set intent_threshold to 0.60

Business description:
{user_text}"""

    response = _get_client().messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [b.text for b in response.content if b.type == "text"]
    if not text_blocks:
        raise ValueError("Claude returned no text content for business analysis")
    text = text_blocks[0]
    try:
        return _parse_json(text)
    except Exception:
        log.error("analyze_business: JSON parse failed. Claude raw response:\n%s", text)
        raise


def suggest_channels(business_strategy: dict) -> dict:
    """Given a business strategy dict, suggest relevant marketing channels."""
    keywords = ", ".join(business_strategy.get("keywords", []))
    locations = business_strategy.get("target_locations") or []
    location_str = ", ".join(locations) if locations else "global"

    location_instruction = (
        f"Target locations: {location_str}\n"
        "IMPORTANT: Only suggest communities where people from these locations are "
        "actually active. Prefer region-specific communities (e.g. if India is a target, "
        "suggest Indian startup groups, Indian job boards like Internshala/Naukri/CutShort, "
        "India-focused Telegram channels, etc.). Global communities are only acceptable "
        "if no strong regional alternative exists for that platform."
    ) if locations else ""

    prompt = f"""Given the following business strategy, suggest specific, real online communities and platforms where the ideal customers are active and expressing buying intent.

Main problem solved: {business_strategy.get("main_problem", "")}
Ideal customer: {business_strategy.get("ideal_customer", "")}
Keywords: {keywords}
{location_instruction}

Return ONLY a valid JSON object, no markdown fences:
{{
  "subreddits": [
    {{"name": "<subreddit name without r/>", "url": "https://www.reddit.com/r/<name>"}}
  ],
  "telegram_channels": [
    {{"name": "<channel display name>", "url": "https://t.me/<actual_handle>"}}
  ],
  "discord_servers": [
    {{"name": "<server name>", "url": "https://discord.gg/<real_invite_code>"}}
  ],
  "linkedin_groups": [
    {{"name": "<group name>", "url": "https://www.linkedin.com/groups/<numeric_id>"}}
  ],
  "job_boards": [
    {{"name": "<board name>", "url": "<actual homepage URL>"}}
  ],
  "quora_topics": [
    {{"name": "<topic name>", "url": "https://www.quora.com/topic/<slug>"}}
  ],
  "hackernews_topics": [
    {{"name": "<search keyword or topic to monitor on Hacker News>", "url": "https://news.ycombinator.com"}}
  ],
  "stackoverflow_tags": [
    {{"name": "<exact Stack Overflow tag — must be a real tag>", "url": "https://stackoverflow.com/questions/tagged/<tag>"}}
  ],
  "devto_tags": [
    {{"name": "<exact dev.to tag slug — lowercase, no spaces>", "url": "https://dev.to/t/<tag>"}}
  ],
  "github_repos": [
    {{"name": "<owner/repo — only real repos with open issues relevant to your audience>", "url": "https://github.com/<owner>/<repo>"}}
  ],
  "indiehackers_groups": [
    {{"name": "<IndieHackers group or product name>", "url": "https://www.indiehackers.com/group/<slug>"}}
  ]
}}

Rules:
- MINIMUM SIZE: Only suggest communities with at least 1,000 members/subscribers.
- ACTIVITY: Only suggest communities with recent posts (within last 7 days). Skip dormant groups.
- Suggest 4-5 subreddits — each must have 10,000+ subscribers and be actively posting.
- Suggest 2-3 Telegram channels with real @handles (no spaces) — must have 1,000+ members.
- Discord: only if you know the EXACT current invite code AND server has 1,000+ members. Return empty array if unsure.
- LinkedIn: 2-3 groups with real numeric IDs. Omit if unsure.
- Job boards: 2 high-traffic boards matching target locations.
- Hacker News: 2-3 search keywords that would surface Ask HN / Show HN posts from your ideal customers. e.g. "looking for SaaS tool", "recommend monitoring service".
- Stack Overflow: 2-3 real, active tags where your ideal customers ask technical questions that your product solves.
- Dev.to: 2-3 real tag slugs where developers discuss problems your product solves.
- GitHub repos: 1-3 repos where your ideal customers open issues requesting features or help your product provides. Only suggest repos you are confident exist.
- IndieHackers: 1-2 groups where your ideal customers discuss their problems.
- TARGET communities where the ideal customer ASKS FOR HELP, SEEKS RECOMMENDATIONS, or DISCUSSES PROBLEMS.
- AVOID broad general communities — they create noise, not leads.
- NEVER suggest communities you are not confident exist and are active. Quality over quantity."""

    response = _get_client().messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [b.text for b in response.content if b.type == "text"]
    if not text_blocks:
        raise ValueError("Claude returned no text content for channel suggestions")
    text = text_blocks[0]
    try:
        return _parse_json(text)
    except Exception:
        log.error("suggest_channels: JSON parse failed. Claude raw response:\n%s", text)
        raise

"""
Resolve a real joinable URL for AI-suggested channels.

Strategy:
 1. For Reddit and Telegram: construct URL directly from the name/handle.
 2. For Discord, LinkedIn, and Job Boards: ask Claude, which knows actual
    invite links, group IDs, and job board domains from training data.
    This sidesteps the Cloudflare/bot-challenge walls on every Discord directory.

Called at channel-creation time so the URL gets stored in the DB immediately.
Also exposed via POST /suggested-channels/{id}/resolve for existing channels.
"""
import json
import logging
import re

from backend.database import settings

log = logging.getLogger(__name__)

_DISCORD_RE = re.compile(
    r'https?://(?:discord\.gg|discord\.com/invite)/([\w-]{4,30})'
)
_LINKEDIN_RE = re.compile(
    r'https?://(?:www\.)?linkedin\.com/(?:groups|company)/([\w%-]+)'
)
_HTTP_RE = re.compile(r'https?://\S+')


def _ask_claude(platform_type: str, name: str) -> str | None:
    """Ask the LLM for the real URL of a community. Returns a URL string or None."""
    from backend.llm import llm_call

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    platform_hints = {
        "discord": (
            "Reply with the exact discord.gg or discord.com/invite URL (e.g. https://discord.gg/abc123). "
            "Only reply if you are certain of the current, working invite code. "
            "If unsure, reply: unknown"
        ),
        "linkedin": (
            "Reply with the linkedin.com/groups/NUMERIC-ID URL (e.g. https://www.linkedin.com/groups/40949). "
            "Only include the numeric group ID if you are certain it is correct. "
            "If unsure, reply: unknown"
        ),
        "telegram": (
            "Reply with the t.me/<handle> URL (e.g. https://t.me/saasclub). "
            "Only reply if you know the exact public channel handle. "
            "If unsure, reply: unknown"
        ),
        "job_board": (
            "Reply with the homepage URL of the job board (e.g. https://wellfound.com). "
            "If unsure, reply: unknown"
        ),
    }
    hint = platform_hints.get(platform_type, "Return a full https:// URL. If unsure, reply: unknown")

    prompt = (
        f'What is the real, publicly accessible URL for this {platform_type} community: "{name}"?\n\n'
        f"{hint}\n\n"
        "Reply with ONLY the URL on a single line, nothing else."
    )

    try:
        text = llm_call(prompt, max_tokens=60, high_quality=False)
        if text.lower() == "unknown" or not text.startswith("http"):
            return None
        if _HTTP_RE.match(text):
            return text.split()[0]
    except Exception:
        log.debug("LLM URL resolve failed for [%s] %s", platform_type, name)

    return None


# ── Public entry point ────────────────────────────────────────────────────────

def resolve_channel_url(platform_type: str, name: str) -> str | None:
    """
    Return a joinable/viewable URL for the given platform + channel name.
    Returns None if nothing could be found.
    """
    if platform_type == "reddit":
        slug = name.lstrip("/").removeprefix("r/").strip()
        return f"https://www.reddit.com/r/{slug}" if slug else None

    if platform_type == "telegram":
        handle = name.lstrip("@").strip()
        # If the name has spaces it's a display name, not a handle — we can't
        # construct the URL deterministically without the actual username.
        if handle and " " not in handle:
            return f"https://t.me/{handle}"
        # Fall through to Claude for named telegram channels
        url = _ask_claude(platform_type, name)
        if url:
            log.info("Telegram AI-resolved '%s' → %s", name, url)
        return url

    if platform_type in ("discord", "linkedin", "job_board"):
        url = _ask_claude(platform_type, name)
        if url:
            log.info("[%s] AI-resolved '%s' → %s", platform_type, name, url)
        return url

    return None

import logging
import httpx
from backend.database import settings

log = logging.getLogger(__name__)

_API = "https://discord.com/api/v10"


def _is_snowflake(value: str) -> bool:
    """Discord channel IDs are 17-19 digit numeric snowflakes."""
    return value.isdigit() and len(value) >= 17


def fetch_channel_messages(channel_id: str, limit: int = 50) -> list[dict]:
    """Fetch recent messages from a Discord channel using the bot token.
    channel_id must be a real Discord channel snowflake ID.
    Channels created from AI suggestions won't have real IDs until manually set.
    """
    if not settings.DISCORD_BOT_TOKEN:
        log.warning("DISCORD_BOT_TOKEN not set — skipping channel %s", channel_id)
        return []

    if not _is_snowflake(channel_id):
        log.info(
            "Discord channel %s has no real channel ID (auto-suggested). "
            "Add the actual Discord channel ID via POST /channels/ to enable monitoring.",
            channel_id,
        )
        return []

    try:
        resp = httpx.get(
            f"{_API}/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
            params={"limit": min(limit, 100)},
            timeout=30,
        )
        resp.raise_for_status()
        messages = resp.json()

        posts = []
        for msg in messages:
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            author = msg.get("author") or {}
            username = author.get("username") or ""
            display_name = author.get("global_name") or username or None
            posts.append({
                "external_id": msg["id"],
                "content": content,
                "author_name": display_name,
                "author_username": username or None,
                "author_id": author.get("id"),
                "author_url": None,
            })

        log.info("Discord channel %s: fetched %d messages", channel_id, len(posts))
        return posts
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            log.warning("Discord bot lacks permission for channel %s", channel_id)
        elif e.response.status_code == 404:
            log.warning("Discord channel %s not found", channel_id)
        else:
            log.exception("Discord fetch failed for channel %s", channel_id)
        return []
    except Exception:
        log.exception("Discord fetch failed for channel %s", channel_id)
        return []

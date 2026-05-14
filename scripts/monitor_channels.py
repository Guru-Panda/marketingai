#!/usr/bin/env python3
"""Periodic channel monitor: fetches posts from Reddit, Telegram, and Discord,
scores intent with Claude, and persists high-signal leads to the database."""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import praw
from anthropic import AsyncAnthropic
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal, settings
from backend.model import Channel, Lead, LeadStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("monitor")

INTENT_THRESHOLD = float(os.getenv("INTENT_THRESHOLD", "0.7"))
# claude-haiku-4-5: cost-efficient for high-volume per-post classification
_ANALYSIS_MODEL = "claude-haiku-4-5"
_MAX_CONTENT_CHARS = 3000

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# ── Claude analysis ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are an intent-scoring assistant. "
    "Respond ONLY with a JSON object — no prose, no markdown fences."
)

_USER_PROMPT = """\
Analyze this post and return a JSON object with exactly these fields:
- intent_score: float 0.0–1.0  (1.0 = person clearly wants help solving a problem; 0.0 = no signal)
- problem_summary: string, 1–2 sentences summarizing the post
- keywords: list of up to 8 relevant keyword strings

Post:
{content}"""


async def analyze_post(content: str) -> dict[str, Any]:
    truncated = content[:_MAX_CONTENT_CHARS]
    response = await _anthropic.messages.create(
        model=_ANALYSIS_MODEL,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _USER_PROMPT.format(content=truncated)}],
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "{}").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Failed to parse Claude response: %.200s", raw)
        data = {}
    return {
        "intent_score": float(data.get("intent_score", 0.0)),
        "problem_summary": str(data.get("problem_summary", "")),
        "keywords": list(data.get("keywords", [])),
    }


# ── Lead upsert ───────────────────────────────────────────────────────────────

def upsert_lead(
    db: Session,
    *,
    user_id: int,
    source_platform: str,
    external_id: str,
    content: str,
    content_summary: str,
    intent_score: float,
    keywords: list,
) -> None:
    existing = (
        db.query(Lead)
        .filter(
            Lead.user_id == user_id,
            Lead.source_platform == source_platform,
            Lead.external_id == external_id,
        )
        .first()
    )
    if existing:
        existing.content_summary = content_summary
        existing.intent_score = intent_score
        existing.keywords = keywords
    else:
        db.add(
            Lead(
                user_id=user_id,
                source_platform=source_platform,
                external_id=external_id,
                content=content,
                content_summary=content_summary,
                intent_score=intent_score,
                keywords=keywords,
                status=LeadStatus.new,
            )
        )
    db.commit()


# ── Reddit ────────────────────────────────────────────────────────────────────

def _build_reddit() -> "praw.Reddit | None":
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not (client_id and client_secret):
        log.warning("Reddit credentials not configured; Reddit channels will be skipped")
        return None
    kwargs: dict[str, str] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "user_agent": os.getenv("REDDIT_USER_AGENT", "MarketingMonitor/1.0"),
    }
    username = os.getenv("REDDIT_USERNAME")
    password = os.getenv("REDDIT_PASSWORD")
    if username and password:
        kwargs["username"] = username
        kwargs["password"] = password
    return praw.Reddit(**kwargs)


_reddit: "praw.Reddit | None" = None


def _fetch_reddit_sync(subreddit_name: str, since_ts: float) -> list[dict]:
    global _reddit
    if _reddit is None:
        _reddit = _build_reddit()
    if _reddit is None:
        return []
    posts = []
    try:
        for submission in _reddit.subreddit(subreddit_name).new(limit=100):
            if submission.created_utc <= since_ts:
                break
            text = f"{submission.title}\n\n{submission.selftext}".strip()
            if text:
                posts.append(
                    {
                        "external_id": submission.id,
                        "content": text,
                    }
                )
    except Exception as exc:
        log.error("Reddit fetch error for r/%s: %s", subreddit_name, exc)
    return posts


async def fetch_reddit_posts(channel: Channel, since: datetime | None) -> list[dict]:
    subreddit_name = channel.name.lstrip("r/").lstrip("/")
    since_ts = since.timestamp() if since else 0.0
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_reddit_sync, subreddit_name, since_ts)


# ── Telegram ──────────────────────────────────────────────────────────────────
# Requires the bot to be an administrator of the target channel so that
# channel_post updates flow through getUpdates.

_TG_BASE = "https://api.telegram.org/bot{token}"
_tg_update_offset: int = 0


async def fetch_telegram_messages(channel: Channel, since: datetime | None) -> list[dict]:
    global _tg_update_offset
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN not set; Telegram channels will be skipped")
        return []

    base = _TG_BASE.format(token=token)
    chat_id = channel.external_id  # e.g. "@channelname" or "-100XXXXXXXXX"
    since_ts = since.timestamp() if since else 0.0
    posts = []

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            params: dict[str, Any] = {"limit": 100, "timeout": 0}
            if _tg_update_offset:
                params["offset"] = _tg_update_offset

            resp = await client.get(f"{base}/getUpdates", params=params)
            resp.raise_for_status()
            updates: list[dict] = resp.json().get("result", [])

            for update in updates:
                _tg_update_offset = max(_tg_update_offset, update["update_id"] + 1)
                msg = update.get("channel_post") or update.get("message")
                if not msg:
                    continue
                chat = msg.get("chat", {})
                # Match by numeric ID or @username
                if str(chat.get("id")) != str(chat_id) and (
                    "@" + chat.get("username", "") != chat_id
                    and chat.get("username") != chat_id.lstrip("@")
                ):
                    continue
                if msg.get("date", 0) <= since_ts:
                    continue
                text = msg.get("text") or msg.get("caption") or ""
                if text:
                    posts.append({"external_id": str(msg["message_id"]), "content": text})

        except Exception as exc:
            log.error("Telegram fetch error for %s: %s", chat_id, exc)

    return posts


# ── Discord ───────────────────────────────────────────────────────────────────
# Requires a bot token with Read Message History in the target channel.
# Set DISCORD_BOT_TOKEN; DISCORD_WEBHOOK_URLS is write-only and not used here.

_DISCORD_API = "https://discord.com/api/v10"
_DISCORD_EPOCH_MS = 1420070400000


def _datetime_to_snowflake(dt: datetime) -> str:
    ms = int(dt.timestamp() * 1000)
    return str((ms - _DISCORD_EPOCH_MS) << 22)


async def fetch_discord_messages(channel: Channel, since: datetime | None) -> list[dict]:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        log.warning("DISCORD_BOT_TOKEN not set; Discord channels will be skipped")
        return []

    channel_id = channel.external_id  # Discord channel snowflake ID
    headers = {"Authorization": f"Bot {token}"}
    params: dict[str, Any] = {"limit": 100}
    if since:
        params["after"] = _datetime_to_snowflake(since)

    posts = []
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                headers=headers,
                params=params,
            )
            if resp.status_code == 429:
                retry_after = float(resp.json().get("retry_after", 1.0))
                log.warning("Discord rate limited; sleeping %.1fs", retry_after)
                await asyncio.sleep(retry_after)
                resp = await client.get(
                    f"{_DISCORD_API}/channels/{channel_id}/messages",
                    headers=headers,
                    params=params,
                )
            resp.raise_for_status()
            for msg in resp.json():
                text = msg.get("content", "").strip()
                if text:
                    posts.append({"external_id": msg["id"], "content": text})
        except Exception as exc:
            log.error("Discord fetch error for channel %s: %s", channel_id, exc)

    return posts


# ── LinkedIn / job_board stubs ────────────────────────────────────────────────
# LinkedIn requires OAuth 2.0 + Marketing Developer Platform approval.
# job_board integrations vary per board. Both are unsupported until compliant
# API access is established; channels of these types are explicitly skipped.

async def fetch_linkedin_posts(channel: Channel, since: datetime | None) -> list[dict]:
    log.warning(
        "LinkedIn monitoring not yet implemented (requires Marketing Developer Platform access). "
        "Channel '%s' skipped.", channel.name
    )
    return []


async def fetch_job_board_posts(channel: Channel, since: datetime | None) -> list[dict]:
    log.warning(
        "Job board monitoring not yet implemented for channel '%s'. Skipped.", channel.name
    )
    return []


# ── Platform dispatcher ───────────────────────────────────────────────────────

_FETCHERS = {
    "reddit": fetch_reddit_posts,
    "telegram": fetch_telegram_messages,
    "discord": fetch_discord_messages,
    "linkedin": fetch_linkedin_posts,
    "job_board": fetch_job_board_posts,
}


# ── Core sync logic ───────────────────────────────────────────────────────────

async def sync_channel(channel: Channel, db: Session) -> None:
    fetcher = _FETCHERS.get(channel.platform_type)
    if not fetcher:
        log.debug("No fetcher for platform=%s channel=%s; skipped", channel.platform_type, channel.name)
        return

    log.info("Syncing %s / %s (last_synced=%s)", channel.platform_type, channel.name, channel.last_synced)
    posts = await fetcher(channel, channel.last_synced)
    log.info("Fetched %d post(s) from %s / %s", len(posts), channel.platform_type, channel.name)

    for post in posts:
        content: str = post["content"]
        external_id: str = post["external_id"]
        try:
            analysis = await analyze_post(content)
        except Exception as exc:
            log.error("Claude analysis failed %s/%s: %s", channel.platform_type, external_id, exc)
            continue

        score = analysis["intent_score"]
        log.debug("%s/%s intent_score=%.2f", channel.platform_type, external_id, score)

        if score > INTENT_THRESHOLD:
            upsert_lead(
                db,
                user_id=channel.user_id,
                source_platform=channel.platform_type,
                external_id=external_id,
                content=content,
                content_summary=analysis["problem_summary"],
                intent_score=score,
                keywords=analysis["keywords"],
            )
            log.info(
                "Lead saved: %s/%s score=%.2f summary=%.80s",
                channel.platform_type,
                external_id,
                score,
                analysis["problem_summary"],
            )

    channel.last_synced = datetime.now(timezone.utc)
    channel.error_count = 0
    db.commit()


async def run_sync_cycle() -> None:
    log.info("=== Sync cycle started ===")
    db = SessionLocal()
    try:
        channels = db.query(Channel).filter(Channel.is_active.is_(True)).all()
        log.info("Active channels: %d", len(channels))

        # Limit concurrency to avoid hammering APIs simultaneously
        sem = asyncio.Semaphore(3)

        async def _guarded(ch: Channel) -> None:
            async with sem:
                try:
                    await sync_channel(ch, db)
                except Exception as exc:
                    ch.error_count = (ch.error_count or 0) + 1
                    db.commit()
                    log.error("Sync error for channel %s: %s", ch.name, exc)

        await asyncio.gather(*[_guarded(ch) for ch in channels])
    finally:
        db.close()
    log.info("=== Sync cycle complete ===")

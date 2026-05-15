"""
Daily job: drop all pending (unwatched) suggested channels, then generate
fresh suggestions verified to be actively posting.
"""
import logging

from backend.business_analyzer import suggest_channels
from backend.database import SessionLocal
from backend.model import BusinessStrategy, ChannelStatus, SuggestedChannel
from backend.monitor.channel_resolver import resolve_channel_url
from backend.monitor.channel_verifier import verify_channel

log = logging.getLogger(__name__)

_PLATFORM_MAP = {
    "subreddits": "reddit",
    "telegram_channels": "telegram",
    "discord_servers": "discord",
    "linkedin_groups": "linkedin",
    "job_boards": "job_board",
    "quora_topics": "quora",
}


def refresh_suggested_channels() -> None:
    """
    For every user strategy:
      1. Delete pending (unwatched) suggested channels — they're stale.
      2. Ask AI for fresh suggestions.
      3. Verify each suggestion is actively posting.
      4. Save only the verified ones.
    """
    db = SessionLocal()
    try:
        strategies = db.query(BusinessStrategy).all()
        log.info("Daily channel refresh: processing %d strategies", len(strategies))

        for strategy in strategies:
            try:
                _refresh_for_strategy(strategy, db)
            except Exception:
                log.exception("Channel refresh failed for strategy %d", strategy.id)
    finally:
        db.close()


def _refresh_for_strategy(strategy: BusinessStrategy, db) -> None:
    # ── Step 1: Remove all pending (unwatched) suggestions ───────────────────
    deleted = (
        db.query(SuggestedChannel)
        .filter(
            SuggestedChannel.user_id == strategy.user_id,
            SuggestedChannel.strategy_id == strategy.id,
            SuggestedChannel.status == ChannelStatus.pending,
        )
        .all()
    )
    for ch in deleted:
        db.delete(ch)
    db.commit()
    log.info(
        "Strategy %d (%s): removed %d stale pending suggestions",
        strategy.id, strategy.title or "untitled", len(deleted),
    )

    # ── Step 2: Ask AI for fresh suggestions ─────────────────────────────────
    business_dict = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "keywords": list(strategy.keywords or []),
        "buyer_phrases": list(strategy.buyer_phrases or []),
        "target_locations": list(strategy.target_locations or []),
    }

    try:
        channels_data = suggest_channels(business_dict)
    except Exception:
        log.exception("AI channel suggestion failed for strategy %d", strategy.id)
        return

    # ── Step 3: Verify activity + save ───────────────────────────────────────
    saved = 0
    skipped = 0
    for field, platform_type in _PLATFORM_MAP.items():
        for entry in channels_data.get(field, []):
            if isinstance(entry, dict):
                name = entry.get("name", "").strip()
                url = entry.get("url") or None
            else:
                name = str(entry).strip()
                url = None

            if not name:
                continue

            if not url:
                try:
                    url = resolve_channel_url(platform_type, name)
                except Exception:
                    pass

            # Skip if already watched by this user (don't re-add watched channels)
            already_watching = (
                db.query(SuggestedChannel)
                .filter(
                    SuggestedChannel.user_id == strategy.user_id,
                    SuggestedChannel.platform_type == platform_type,
                    SuggestedChannel.name == name,
                    SuggestedChannel.status == ChannelStatus.watching,
                )
                .first()
            )
            if already_watching:
                continue

            # Verify the channel is actively posting
            if not verify_channel(platform_type, name, url):
                log.info("Skipping inactive channel [%s] %s", platform_type, name)
                skipped += 1
                continue

            channel = SuggestedChannel(
                user_id=strategy.user_id,
                strategy_id=strategy.id,
                platform_type=platform_type,
                name=name,
                url=url,
                status=ChannelStatus.pending,
            )
            db.add(channel)
            saved += 1

    db.commit()
    log.info(
        "Strategy %d (%s): added %d fresh suggestions, skipped %d inactive",
        strategy.id, strategy.title or "untitled", saved, skipped,
    )

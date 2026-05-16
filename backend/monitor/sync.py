import logging
from datetime import datetime, timedelta, timezone

from backend.database import SessionLocal, settings
from backend.email_utils import send_new_lead_alert
from backend.model import BusinessStrategy, Channel, Lead, User
from backend.monitor.discord_monitor import fetch_channel_messages
from backend.monitor.job_board_monitor import fetch_posts as fetch_job_board_posts
from backend.monitor.linkedin_monitor import fetch_posts as fetch_linkedin_posts
from backend.monitor.profile_scraper import (
    fetch_discord_user_history,
    fetch_reddit_author,
    fetch_telegram_profile,
)
from backend.monitor.quora_monitor import fetch_posts as fetch_quora_posts
from backend.monitor.reddit import fetch_posts as fetch_reddit_posts, search_posts as search_reddit_posts
from backend.monitor.scorer import extract_contacts, score_post
from backend.monitor.telegram import fetch_channel_posts

log = logging.getLogger(__name__)


def _user_keywords(user_id: int, db) -> list[str]:
    rows = db.query(BusinessStrategy).filter(BusinessStrategy.user_id == user_id).all()
    seen: set[str] = set()
    for row in rows:
        for kw in (row.keywords or []):
            seen.add(str(kw).lower())
    return list(seen)


def _user_target_locations(user_id: int, db) -> list[str]:
    rows = db.query(BusinessStrategy).filter(BusinessStrategy.user_id == user_id).all()
    seen: set[str] = set()
    for row in rows:
        for loc in (row.target_locations or []):
            seen.add(str(loc).strip())
    return list(seen)


def _strategy_context(strategy_id: int | None, db) -> dict:
    """Return business context fields for scorer enrichment."""
    if not strategy_id:
        return {}
    s = db.query(BusinessStrategy).filter(BusinessStrategy.id == strategy_id).first()
    if not s:
        return {}
    return {
        "main_problem": s.main_problem or "",
        "ideal_customer": s.ideal_customer or "",
        "buyer_phrases": list(s.buyer_phrases or []),
        "keywords": list(s.keywords or []),
        "intent_threshold": s.intent_threshold,
    }


def _location_matches(author_location: str | None, targets: list[str]) -> bool:
    """True if the lead's location falls within any target. Unknown locations always pass."""
    if not targets:
        return True
    if not author_location:
        return True
    loc_words = {w for w in author_location.lower().replace(",", " ").split() if w}
    for target in targets:
        target_words = {w for w in target.lower().replace(",", " ").split() if w}
        if target_words and target_words.issubset(loc_words):
            return True
    return False


def _enrich_author(platform: str, post: dict, channel_external_id: str) -> list[str]:
    """Fetch all available profile and activity texts for the post's author.
    Called only after a post passes the intent threshold, so the extra
    network calls are limited to genuine leads.
    """
    username = post.get("author_username") or ""

    if platform == "reddit" and username:
        return fetch_reddit_author(username)

    if platform == "telegram" and username:
        return fetch_telegram_profile(username)

    if platform == "discord":
        author_id = post.get("author_id") or ""
        if author_id and channel_external_id:
            return fetch_discord_user_history(channel_external_id, author_id)

    return []


def _merge_contacts(from_profile: dict, from_post: dict) -> dict:
    """Profile-level data takes priority; fall back to post-level data."""
    return {
        "email":    from_profile.get("email")    or from_post.get("email"),
        "phone":    from_profile.get("phone")    or from_post.get("phone"),
        "location": from_profile.get("location") or from_post.get("location"),
    }


def _save_lead(
    db,
    user_id: int,
    platform: str,
    external_id: str,
    content: str,
    scored: dict,
    post: dict,
    strategy_id: int | None = None,
) -> bool:
    exists = db.query(Lead).filter(
        Lead.user_id == user_id,
        Lead.source_platform == platform,
        Lead.external_id == external_id,
    ).first()
    if exists:
        return False

    contact = scored.get("contact") or {}

    lead = Lead(
        user_id=user_id,
        strategy_id=strategy_id,
        source_platform=platform,
        external_id=external_id,
        content=content,
        content_summary=scored.get("summary", ""),
        intent_score=float(scored.get("intent_score", 0)),
        keywords=scored.get("keywords", []),
        source_url=post.get("source_url"),
        author_name=post.get("author_name"),
        author_username=post.get("author_username"),
        author_url=post.get("author_url"),
        author_email=contact.get("email") or None,
        author_phone=contact.get("phone") or None,
        author_location=contact.get("location") or None,
    )
    db.add(lead)
    db.commit()

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            send_new_lead_alert(
                to_email=user.email,
                platform=platform,
                intent_score=lead.intent_score,
                summary=lead.content_summary,
                author_name=lead.author_name,
                author_location=lead.author_location,
                source_url=lead.source_url,
            )
    except Exception:
        log.exception("Lead alert email failed for user %d", user_id)

    return True


def _fetch_posts(channel: Channel, keywords: list[str] = [], db=None) -> list[dict]:
    pt = channel.platform_type
    if pt == "reddit":
        return fetch_reddit_posts(channel.name)
    if pt == "telegram":
        return fetch_channel_posts(channel.name)
    if pt == "discord":
        return fetch_channel_messages(channel.external_id)
    if pt == "linkedin":
        return fetch_linkedin_posts(channel.name, channel.url, keywords)
    if pt == "job_board":
        return fetch_job_board_posts(channel.name, channel.url, keywords)
    if pt == "quora":
        return fetch_quora_posts(keywords)
    log.debug("No scraper for platform %s", pt)
    return []


def _is_channel_due(channel: Channel) -> bool:
    if channel.last_synced is None:
        return True
    interval = channel.sync_interval_hours or settings.SYNC_INTERVAL_HOURS
    last = channel.last_synced
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= last + timedelta(hours=interval)


def sync_channel(channel: Channel, db) -> tuple[int, int]:
    """Returns (fetched, saved) counts."""
    keywords = _user_keywords(channel.user_id, db)
    target_locations = _user_target_locations(channel.user_id, db)
    biz = _strategy_context(channel.strategy_id, db)

    posts = _fetch_posts(channel, keywords)
    if not posts:
        return 0, 0
    saved = 0

    for post in posts:
        try:
            # Step 1: Score the post for intent — pass full business context
            scored = score_post(
                post["content"],
                keywords,
                main_problem=biz.get("main_problem", ""),
                ideal_customer=biz.get("ideal_customer", ""),
                buyer_phrases=biz.get("buyer_phrases"),
            )
            intent = float(scored.get("intent_score", 0))
            threshold = biz.get("intent_threshold") or settings.INTENT_THRESHOLD
            log.info("[score] %.2f/%.2f [%s/%s] %s", intent, threshold, channel.platform_type, channel.name, post.get("content", "")[:80])
            if intent < threshold:
                continue

            # Step 2: Enrich the author — fetch their profile + full activity history.
            # This is the source of truth for email/phone/name/location.
            # Only runs for posts that passed the intent threshold.
            profile_texts = _enrich_author(channel.platform_type, post, channel.external_id)

            if profile_texts:
                profile_contacts = extract_contacts(profile_texts)
                # If enrichment found a real name, prefer it over the platform handle
                if profile_contacts.get("name"):
                    post = {**post, "author_name": profile_contacts["name"]}
                merged_contact = _merge_contacts(profile_contacts, scored.get("contact") or {})
                scored = {**scored, "contact": merged_contact}

            # Step 3: Apply geographic filter using the best location we now have
            author_location = (scored.get("contact") or {}).get("location")
            if not _location_matches(author_location, target_locations):
                log.debug(
                    "Skipping post %s — location '%s' outside target %s",
                    post.get("external_id"), author_location, target_locations,
                )
                continue

            if _save_lead(db, channel.user_id, channel.platform_type,
                          post["external_id"], post["content"], scored, post,
                          strategy_id=channel.strategy_id):
                saved += 1

        except Exception:
            log.exception(
                "Processing failed for post %s on %s",
                post.get("external_id"), channel.platform_type,
            )

    channel.last_synced = datetime.now(timezone.utc)
    db.commit()

    effective_threshold = biz.get("intent_threshold") or settings.INTENT_THRESHOLD
    log.info(
        "[%s] %s — %d/%d posts saved as leads (threshold %.2f)",
        channel.platform_type, channel.name, saved, len(posts), effective_threshold,
    )
    return len(posts), saved


def _search_reddit_for_strategy(strategy: BusinessStrategy, db) -> int:
    """Proactively search Reddit-wide using buyer phrases for a strategy.
    Returns count of leads saved.
    """
    phrases = list(strategy.buyer_phrases or [])
    if not phrases:
        return 0

    keywords = list(strategy.keywords or [])
    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]
    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }

    saved = 0
    seen_ids: set[str] = set()

    for phrase in phrases[:8]:  # cap at 8 phrases to limit API calls
        posts = search_reddit_posts(phrase, limit=15)
        for post in posts:
            ext_id = post["external_id"]
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)
            try:
                scored = score_post(
                    post["content"],
                    keywords,
                    main_problem=biz["main_problem"],
                    ideal_customer=biz["ideal_customer"],
                    buyer_phrases=biz["buyer_phrases"],
                )
                intent = float(scored.get("intent_score", 0))
                if intent < (biz.get("intent_threshold") or settings.INTENT_THRESHOLD):
                    continue

                profile_texts = _enrich_author("reddit", post, "")
                if profile_texts:
                    profile_contacts = extract_contacts(profile_texts)
                    if profile_contacts.get("name"):
                        post = {**post, "author_name": profile_contacts["name"]}
                    merged = _merge_contacts(profile_contacts, scored.get("contact") or {})
                    scored = {**scored, "contact": merged}

                author_location = (scored.get("contact") or {}).get("location")
                if not _location_matches(author_location, target_locations):
                    continue

                if _save_lead(db, strategy.user_id, "reddit", ext_id,
                              post["content"], scored, post,
                              strategy_id=strategy.id):
                    saved += 1
            except Exception:
                log.exception("Reddit search scoring failed for post %s", ext_id)

    if saved:
        log.info(
            "[reddit-search] strategy %d (%s) — %d leads from buyer phrase search",
            strategy.id, strategy.title or "untitled", saved,
        )
    return saved


def _search_quora_for_strategy(strategy: BusinessStrategy, db) -> int:
    """Proactively search Quora via DuckDuckGo using buyer phrases for a strategy.
    Returns count of leads saved.
    """
    phrases = list(strategy.buyer_phrases or [])
    keywords = list(strategy.keywords or [])
    if not phrases and not keywords:
        return 0

    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]
    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }

    posts = fetch_quora_posts(keywords=keywords, buyer_phrases=phrases)
    saved = 0
    seen_ids: set[str] = set()

    for post in posts:
        ext_id = post["external_id"]
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        try:
            scored = score_post(
                post["content"],
                keywords,
                main_problem=biz["main_problem"],
                ideal_customer=biz["ideal_customer"],
                buyer_phrases=biz["buyer_phrases"],
            )
            intent = float(scored.get("intent_score", 0))
            if intent < (biz.get("intent_threshold") or settings.INTENT_THRESHOLD):
                continue

            author_location = (scored.get("contact") or {}).get("location")
            if not _location_matches(author_location, target_locations):
                continue

            if _save_lead(db, strategy.user_id, "quora", ext_id,
                          post["content"], scored, post,
                          strategy_id=strategy.id):
                saved += 1
        except Exception:
            log.exception("Quora search scoring failed for post %s", ext_id)

    if saved:
        log.info(
            "[quora-search] strategy %d (%s) — %d leads from buyer phrase search",
            strategy.id, strategy.title or "untitled", saved,
        )
    return saved


def run_sync() -> None:
    """Scheduled job: sync all active channels + run buyer phrase search across all users."""
    db = SessionLocal()
    try:
        # ── Channel sync ─────────────────────────────────────────────────────
        channels = db.query(Channel).filter(Channel.is_active.is_(True)).all()
        due = [ch for ch in channels if _is_channel_due(ch)]
        log.info(
            "Sync check: %d active channel(s), %d due now",
            len(channels), len(due),
        )

        total_fetched = total_saved = 0
        for ch in due:
            try:
                fetched, saved = sync_channel(ch, db)
                total_fetched += fetched
                total_saved += saved
            except Exception:
                log.exception(
                    "Sync failed for channel %d (%s / %s)",
                    ch.id, ch.platform_type, ch.name,
                )

        # ── Reddit buyer phrase search (all strategies with buyer_phrases) ───
        strategies = db.query(BusinessStrategy).all()
        search_saved = 0
        for s in strategies:
            if s.buyer_phrases:
                try:
                    search_saved += _search_reddit_for_strategy(s, db)
                except Exception:
                    log.exception("Buyer phrase search failed for strategy %d", s.id)

        # ── Quora buyer phrase search ────────────────────────────────────────
        for s in strategies:
            if s.keywords or s.buyer_phrases:
                try:
                    search_saved += _search_quora_for_strategy(s, db)
                except Exception:
                    log.exception("Quora search failed for strategy %d", s.id)

        total_saved += search_saved
        log.info(
            "Sync complete — %d posts fetched, %d leads saved (%d from buyer search)",
            total_fetched, total_saved, search_saved,
        )
    finally:
        db.close()

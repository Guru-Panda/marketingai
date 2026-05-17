import logging
from datetime import datetime, timedelta, timezone

from backend.database import SessionLocal, settings
from backend.email_utils import send_new_lead_alert
from backend.model import BusinessStrategy, Channel, Lead, User
from backend.monitor.discord_monitor import fetch_channel_messages
from backend.monitor.job_board_monitor import fetch_posts as fetch_job_board_posts, search_posts as search_job_board_posts
from backend.monitor.linkedin_monitor import fetch_posts as fetch_linkedin_posts
from backend.monitor.profile_scraper import (
    fetch_discord_user_history,
    fetch_reddit_author,
    fetch_telegram_profile,
)
from backend.monitor.reddit import fetch_posts as fetch_reddit_posts, search_posts as search_reddit_posts
from backend.monitor.hackernews_monitor import fetch_posts as fetch_hn_posts, search_posts as search_hn_posts
from backend.monitor.stackoverflow_monitor import fetch_posts as fetch_so_posts, search_posts as search_so_posts
from backend.monitor.devto_monitor import fetch_posts as fetch_devto_posts, search_posts as search_devto_posts
from backend.monitor.github_monitor import fetch_posts as fetch_github_posts, search_issues as search_github_issues
from backend.monitor.indiehackers_monitor import fetch_posts as fetch_ih_posts
from backend.monitor.scorer import extract_contacts, generate_outreach, score_post
from backend.monitor.telegram import fetch_channel_posts, search_posts as search_telegram_channel_posts

log = logging.getLogger(__name__)

# ── Sync stats (in-memory, reset on restart) ─────────────────────────────────
_sync_stats: dict = {
    "last_sync_at": None,
    "posts_scanned": 0,
    "new_leads": 0,
    "is_running": False,
    "runtime_seconds": 0,
}


def get_sync_stats() -> dict:
    return dict(_sync_stats)


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
        "exclude_keywords": [str(k).lower() for k in (s.exclude_keywords or [])],
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
    """Fetch profile / activity texts for the post's author.
    Called only after a post passes the intent threshold.
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


def _try_generate_outreach(
    platform: str,
    post: dict,
    scored: dict,
    biz: dict,
) -> str | None:
    """Best-effort outreach template generation. Never raises."""
    try:
        return generate_outreach(
            platform=platform,
            post_content=post.get("content", ""),
            summary=scored.get("summary", ""),
            business_context=biz,
        )
    except Exception:
        log.debug("Outreach generation skipped for %s", post.get("external_id"))
        return None


def _save_lead(
    db,
    user_id: int,
    platform: str,
    external_id: str,
    content: str,
    scored: dict,
    post: dict,
    strategy_id: int | None = None,
    biz: dict | None = None,
) -> bool:
    exists = db.query(Lead).filter(
        Lead.user_id == user_id,
        Lead.source_platform == platform,
        Lead.external_id == external_id,
    ).first()
    if exists:
        return False

    contact = scored.get("contact") or {}

    # Generate outreach template inline (quick haiku call, non-blocking)
    outreach = _try_generate_outreach(platform, post, scored, biz or {})

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
        outreach_template=outreach,
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
    if pt == "hackernews":
        return fetch_hn_posts(channel.name)
    if pt == "stackoverflow":
        return fetch_so_posts(channel.name)
    if pt == "devto":
        return fetch_devto_posts(channel.name)
    if pt == "github":
        return fetch_github_posts(channel.name)
    if pt == "indiehackers":
        return fetch_ih_posts(keywords)
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
            scored = score_post(
                post["content"],
                keywords,
                main_problem=biz.get("main_problem", ""),
                ideal_customer=biz.get("ideal_customer", ""),
                buyer_phrases=biz.get("buyer_phrases"),
            )
            intent = float(scored.get("intent_score", 0))
            threshold = biz.get("intent_threshold") or settings.INTENT_THRESHOLD
            log.info(
                "[score] %.2f/%.2f [%s/%s] %s",
                intent, threshold, channel.platform_type, channel.name,
                post.get("content", "")[:80],
            )
            if intent < threshold:
                continue

            # Skip if post contains any excluded keyword
            exclude_kws = biz.get("exclude_keywords", [])
            if exclude_kws:
                content_lower = post["content"].lower()
                if any(kw in content_lower for kw in exclude_kws):
                    log.debug(
                        "Skipping post %s — matched exclude keyword", post.get("external_id")
                    )
                    continue

            profile_texts = _enrich_author(channel.platform_type, post, channel.external_id)

            if profile_texts:
                profile_contacts = extract_contacts(profile_texts)
                if profile_contacts.get("name"):
                    post = {**post, "author_name": profile_contacts["name"]}
                merged_contact = _merge_contacts(profile_contacts, scored.get("contact") or {})
                scored = {**scored, "contact": merged_contact}

            author_location = (scored.get("contact") or {}).get("location")
            if not _location_matches(author_location, target_locations):
                log.debug(
                    "Skipping post %s — location '%s' outside target %s",
                    post.get("external_id"), author_location, target_locations,
                )
                continue

            if _save_lead(
                db, channel.user_id, channel.platform_type,
                post["external_id"], post["content"], scored, post,
                strategy_id=channel.strategy_id,
                biz=biz,
            ):
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


# ── Per-platform proactive search helpers ─────────────────────────────────────

def _effective_threshold(strategy: BusinessStrategy, multiplier: float = 1.0) -> float:
    """Return the intent threshold to use for a strategy's proactive search.

    Non-Reddit platforms produce informational/technical content that scores
    lower than Reddit's explicit "I need X" posts.  Apply a multiplier < 1.0
    to widen the net while keeping Reddit at full strength.
    Minimum floor of 0.35 so we never capture completely off-topic posts.
    """
    base = float(strategy.intent_threshold or settings.INTENT_THRESHOLD)
    return max(base * multiplier, 0.35)


def _hn_queries(keywords: list[str], phrases: list[str]) -> list[str]:
    """Build HN-optimised queries.  HN uses 'Ask HN:' / 'best X' language,
    not the buyer-phrase style used on Reddit."""
    kw = " ".join(keywords[:3])
    queries = []
    if kw:
        queries += [
            f"best {kw}",
            f"{kw} recommendation",
            f"{kw} alternative",
            kw,
        ]
    # Add raw buyer phrases too — sometimes they match
    queries += [p for p in phrases[:3] if p not in queries]
    return queries[:6]


def _so_queries(keywords: list[str], phrases: list[str]) -> list[str]:
    """Build Stack Overflow-optimised queries — question-style searches."""
    kw = " ".join(keywords[:3])
    queries = []
    if kw:
        queries += [
            f"looking for {kw}",
            f"recommend {kw}",
            kw,
        ]
    queries += [p for p in phrases[:2] if p not in queries]
    return queries[:5]

def _search_reddit_for_strategy(strategy: BusinessStrategy, db) -> int:
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

    for phrase in phrases[:8]:
        posts = search_reddit_posts(phrase, limit=30, time_filter="week", max_age_days=3)
        for post in posts:
            ext_id = post["external_id"]
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)
            try:
                scored = score_post(
                    post["content"], keywords,
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
                              strategy_id=strategy.id, biz=biz):
                    saved += 1
            except Exception:
                log.exception("Reddit search scoring failed for post %s", ext_id)

    if saved:
        log.info("[reddit-search] strategy %d — %d leads", strategy.id, saved)
    return saved


def _search_quora_for_strategy(strategy: BusinessStrategy, db) -> int:
    # Quora requires authentication to view content and blocks cloud IPs.
    # No free public API or RSS feed is available.
    # Skipping to avoid wasting sync time on empty results.
    log.debug("[quora-search] strategy %d — skipped (no accessible public API)", strategy.id)
    return 0


def _search_hackernews_for_strategy(strategy: BusinessStrategy, db) -> int:
    phrases = list(strategy.buyer_phrases or [])
    keywords = list(strategy.keywords or [])
    if not phrases and not keywords:
        return 0

    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }
    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]

    threshold = _effective_threshold(strategy, multiplier=0.5)
    saved = 0
    seen_ids: set[str] = set()
    fetched_total = 0
    filtered_total = 0

    for query in _hn_queries(keywords, phrases):
        if not query.strip():
            continue
        for post in search_hn_posts(query, limit=30):
            fetched_total += 1
            ext_id = post["external_id"]
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)
            try:
                scored = score_post(
                    post["content"], keywords,
                    main_problem=biz["main_problem"],
                    ideal_customer=biz["ideal_customer"],
                    buyer_phrases=phrases,
                )
                intent = float(scored.get("intent_score", 0))
                if intent < threshold:
                    filtered_total += 1
                    continue

                author_location = (scored.get("contact") or {}).get("location")
                if not _location_matches(author_location, target_locations):
                    continue

                if _save_lead(db, strategy.user_id, "hackernews", ext_id,
                              post["content"], scored, post,
                              strategy_id=strategy.id, biz=biz):
                    saved += 1
            except Exception:
                log.exception("HN search scoring failed for post %s", ext_id)

    log.info("[hn-search] strategy %d — fetched=%d filtered_by_threshold=%d leads=%d threshold=%.2f",
             strategy.id, fetched_total, filtered_total, saved, threshold)
    return saved


def _search_stackoverflow_for_strategy(strategy: BusinessStrategy, db) -> int:
    keywords = list(strategy.keywords or [])
    phrases = list(strategy.buyer_phrases or [])
    if not keywords and not phrases:
        return 0

    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }
    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]

    threshold = _effective_threshold(strategy, multiplier=0.5)
    saved = 0
    seen_ids: set[str] = set()
    fetched_total = 0
    filtered_total = 0

    for query in _so_queries(keywords, phrases):
        if not query.strip():
            continue
        for post in search_so_posts(query, limit=30):
            fetched_total += 1
            ext_id = post["external_id"]
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)
            try:
                scored = score_post(
                    post["content"], keywords,
                    main_problem=biz["main_problem"],
                    ideal_customer=biz["ideal_customer"],
                    buyer_phrases=phrases,
                )
                intent = float(scored.get("intent_score", 0))
                if intent < threshold:
                    filtered_total += 1
                    continue

                author_location = (scored.get("contact") or {}).get("location")
                if not _location_matches(author_location, target_locations):
                    continue

                if _save_lead(db, strategy.user_id, "stackoverflow", ext_id,
                              post["content"], scored, post,
                              strategy_id=strategy.id, biz=biz):
                    saved += 1
            except Exception:
                log.exception("SO search scoring failed for post %s", ext_id)

    log.info("[so-search] strategy %d — fetched=%d filtered_by_threshold=%d leads=%d threshold=%.2f",
             strategy.id, fetched_total, filtered_total, saved, threshold)
    return saved


def _search_github_for_strategy(strategy: BusinessStrategy, db) -> int:
    keywords = list(strategy.keywords or [])
    phrases = list(strategy.buyer_phrases or [])
    if not keywords and not phrases:
        return 0

    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }
    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]

    threshold = _effective_threshold(strategy, multiplier=0.5)
    saved = 0
    seen_ids: set[str] = set()
    fetched_total = 0
    filtered_total = 0
    # Use keywords as primary query, fall back to buyer phrases if no keywords
    kw_query = " ".join(keywords[:3]) if keywords else ""
    queries = ([kw_query] if kw_query else []) + phrases[:3]

    for query in queries:
        if not query.strip():
            continue
        for post in search_github_issues(query, limit=30):
            fetched_total += 1
            ext_id = post["external_id"]
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)
            try:
                scored = score_post(
                    post["content"], keywords,
                    main_problem=biz["main_problem"],
                    ideal_customer=biz["ideal_customer"],
                    buyer_phrases=phrases,
                )
                intent = float(scored.get("intent_score", 0))
                if intent < threshold:
                    filtered_total += 1
                    continue

                author_location = (scored.get("contact") or {}).get("location")
                if not _location_matches(author_location, target_locations):
                    continue

                if _save_lead(db, strategy.user_id, "github", ext_id,
                              post["content"], scored, post,
                              strategy_id=strategy.id, biz=biz):
                    saved += 1
            except Exception:
                log.exception("GitHub search scoring failed for post %s", ext_id)

    log.info("[github-search] strategy %d — fetched=%d filtered=%d leads=%d threshold=%.2f",
             strategy.id, fetched_total, filtered_total, saved, threshold)
    return saved


def _search_devto_for_strategy(strategy: BusinessStrategy, db) -> int:
    keywords = list(strategy.keywords or [])
    phrases = list(strategy.buyer_phrases or [])
    if not keywords and not phrases:
        return 0

    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }
    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]

    threshold = _effective_threshold(strategy, multiplier=0.5)
    saved = 0
    seen_ids: set[str] = set()
    fetched_total = 0
    filtered_total = 0

    # Search using keywords if available, otherwise fall back to buyer phrases
    search_query = " ".join(keywords[:4]) if keywords else " ".join(w for p in phrases[:2] for w in p.split()[:3])
    log.info("[devto-search] strategy %d — query=%r threshold=%.2f", strategy.id, search_query, threshold)
    for post in search_devto_posts(search_query, limit=40):
        fetched_total += 1
        ext_id = post["external_id"]
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        try:
            scored = score_post(
                post["content"], keywords,
                main_problem=biz["main_problem"],
                ideal_customer=biz["ideal_customer"],
                buyer_phrases=phrases,
            )
            intent = float(scored.get("intent_score", 0))
            if intent < threshold:
                filtered_total += 1
                continue

            author_location = (scored.get("contact") or {}).get("location")
            if not _location_matches(author_location, target_locations):
                continue

            if _save_lead(db, strategy.user_id, "devto", ext_id,
                          post["content"], scored, post,
                          strategy_id=strategy.id, biz=biz):
                saved += 1
        except Exception:
            log.exception("Dev.to search scoring failed for post %s", ext_id)

    log.info("[devto-search] strategy %d — fetched=%d filtered=%d leads=%d", strategy.id, fetched_total, filtered_total, saved)
    return saved


def _search_indiehackers_for_strategy(strategy: BusinessStrategy, db) -> int:
    keywords = list(strategy.keywords or [])
    phrases = list(strategy.buyer_phrases or [])
    if not keywords and not phrases:
        return 0

    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }
    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]

    posts = fetch_ih_posts(keywords=keywords, buyer_phrases=phrases)
    threshold = _effective_threshold(strategy, multiplier=0.5)
    saved = 0
    seen_ids: set[str] = set()
    fetched_total = len(posts)
    filtered_total = 0

    log.info("[ih-search] strategy %d — fetched %d posts (threshold=%.2f)", strategy.id, fetched_total, threshold)

    for post in posts:
        ext_id = post["external_id"]
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        try:
            scored = score_post(
                post["content"], keywords,
                main_problem=biz["main_problem"],
                ideal_customer=biz["ideal_customer"],
                buyer_phrases=phrases,
            )
            intent = float(scored.get("intent_score", 0))
            if intent < threshold:
                filtered_total += 1
                continue

            author_location = (scored.get("contact") or {}).get("location")
            if not _location_matches(author_location, target_locations):
                continue

            if _save_lead(db, strategy.user_id, "indiehackers", ext_id,
                          post["content"], scored, post,
                          strategy_id=strategy.id, biz=biz):
                saved += 1
        except Exception:
            log.exception("IndieHackers search scoring failed for post %s", ext_id)

    log.info("[ih-search] strategy %d — fetched=%d filtered=%d leads=%d", strategy.id, fetched_total, filtered_total, saved)
    return saved


def _search_telegram_for_strategy(strategy: BusinessStrategy, db) -> int:
    """Scan the user's monitored Telegram channels for keyword-matching posts.

    Replaces the old DuckDuckGo-based approach (blocked on Railway).
    Fetches recent posts directly from t.me/s/<username> for each active
    Telegram channel the user has added, then filters by keywords before scoring.
    """
    phrases = list(strategy.buyer_phrases or [])
    keywords = list(strategy.keywords or [])
    if not phrases and not keywords:
        return 0

    # Look up active Telegram channels for this user
    tg_channels = db.query(Channel).filter(
        Channel.user_id == strategy.user_id,
        Channel.platform_type == "telegram",
        Channel.is_active.is_(True),
    ).all()

    # Extract usernames from channel names (strip @ if present)
    channel_usernames = []
    for ch in tg_channels:
        name = (ch.name or "").lstrip("@").strip()
        if name:
            channel_usernames.append(name)

    if not channel_usernames:
        log.info("[telegram-search] strategy %d — no active Telegram channels to scan", strategy.id)
        return 0

    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }
    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]
    threshold = _effective_threshold(strategy, multiplier=0.5)

    posts = search_telegram_channel_posts(
        channel_usernames=channel_usernames,
        keywords=keywords,
        buyer_phrases=phrases,
        limit=50,
    )

    saved = 0
    seen_ids: set[str] = set()
    filtered_total = 0

    for post in posts:
        ext_id = post["external_id"]
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        try:
            scored = score_post(
                post["content"], keywords,
                main_problem=biz["main_problem"],
                ideal_customer=biz["ideal_customer"],
                buyer_phrases=phrases,
            )
            intent = float(scored.get("intent_score", 0))
            if intent < threshold:
                filtered_total += 1
                continue

            author_location = (scored.get("contact") or {}).get("location")
            if not _location_matches(author_location, target_locations):
                continue

            if _save_lead(db, strategy.user_id, "telegram", ext_id,
                          post["content"], scored, post,
                          strategy_id=strategy.id, biz=biz):
                saved += 1
        except Exception:
            log.exception("Telegram search scoring failed for post %s", ext_id)

    log.info("[telegram-search] strategy %d — channels=%d fetched=%d filtered=%d leads=%d threshold=%.2f",
             strategy.id, len(channel_usernames), len(posts), filtered_total, saved, threshold)
    return saved


def _search_jobboards_for_strategy(strategy: BusinessStrategy, db) -> int:
    keywords = list(strategy.keywords or [])
    phrases = list(strategy.buyer_phrases or [])
    if not keywords and not phrases:
        return 0

    biz = {
        "main_problem": strategy.main_problem or "",
        "ideal_customer": strategy.ideal_customer or "",
        "buyer_phrases": phrases,
        "keywords": keywords,
        "intent_threshold": strategy.intent_threshold,
    }
    target_locations = [str(loc).strip() for loc in (strategy.target_locations or [])]

    posts = search_job_board_posts(keywords=keywords, buyer_phrases=phrases, limit=50)
    threshold = _effective_threshold(strategy, multiplier=0.5)
    saved = 0
    seen_ids: set[str] = set()
    fetched_total = len(posts)
    filtered_total = 0

    log.info("[jobboard-search] strategy %d — fetched %d posts (threshold=%.2f)", strategy.id, fetched_total, threshold)

    for post in posts:
        ext_id = post["external_id"]
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        try:
            scored = score_post(
                post["content"], keywords,
                main_problem=biz["main_problem"],
                ideal_customer=biz["ideal_customer"],
                buyer_phrases=phrases,
            )
            intent = float(scored.get("intent_score", 0))
            if intent < threshold:
                filtered_total += 1
                continue

            # Prefer location from job posting if scorer didn't find one
            author_location = (scored.get("contact") or {}).get("location") or post.get("author_location")
            if not _location_matches(author_location, target_locations):
                continue

            if _save_lead(db, strategy.user_id, "job_board", ext_id,
                          post["content"], scored, post,
                          strategy_id=strategy.id, biz=biz):
                saved += 1
        except Exception:
            log.exception("Job board search scoring failed for post %s", ext_id)

    log.info("[jobboard-search] strategy %d — fetched=%d filtered=%d leads=%d", strategy.id, fetched_total, filtered_total, saved)
    return saved


# ── Main scheduled job ────────────────────────────────────────────────────────

def run_sync() -> None:
    """Scheduled job: sync all active channels + proactive search across all platforms."""
    import time as _time
    _sync_stats["is_running"] = True
    _sync_stats["last_sync_at"] = datetime.now(timezone.utc).isoformat()
    t0 = _time.monotonic()

    db = SessionLocal()
    try:
        # ── Channel sync ─────────────────────────────────────────────────────
        channels = db.query(Channel).filter(Channel.is_active.is_(True)).all()
        due = [ch for ch in channels if _is_channel_due(ch)]
        log.info("Sync check: %d active channel(s), %d due now", len(channels), len(due))

        total_fetched = total_saved = 0
        for ch in due:
            try:
                fetched, saved = sync_channel(ch, db)
                total_fetched += fetched
                total_saved += saved
            except Exception:
                log.exception("Sync failed for channel %d (%s / %s)", ch.id, ch.platform_type, ch.name)

        # ── Proactive search across all strategies ───────────────────────────
        strategies = db.query(BusinessStrategy).all()
        search_saved = 0

        _search_fns = [
            ("reddit",        _search_reddit_for_strategy,        lambda s: bool(s.buyer_phrases)),
            ("quora",         _search_quora_for_strategy,         lambda s: bool(s.keywords or s.buyer_phrases)),
            ("hackernews",    _search_hackernews_for_strategy,     lambda s: bool(s.keywords or s.buyer_phrases)),
            ("stackoverflow", _search_stackoverflow_for_strategy,  lambda s: bool(s.keywords or s.buyer_phrases)),
            ("github",        _search_github_for_strategy,         lambda s: bool(s.keywords or s.buyer_phrases)),
            ("devto",         _search_devto_for_strategy,          lambda s: bool(s.keywords or s.buyer_phrases)),
            ("indiehackers",  _search_indiehackers_for_strategy,   lambda s: bool(s.keywords or s.buyer_phrases)),
            ("telegram",      _search_telegram_for_strategy,       lambda s: bool(s.keywords or s.buyer_phrases)),
            ("job_board",     _search_jobboards_for_strategy,      lambda s: bool(s.keywords or s.buyer_phrases)),
        ]

        for platform, fn, should_run in _search_fns:
            for s in strategies:
                if not should_run(s):
                    continue
                try:
                    search_saved += fn(s, db)
                except Exception:
                    log.exception("[%s] search failed for strategy %d", platform, s.id)

        total_saved += search_saved
        _sync_stats["posts_scanned"] += total_fetched
        _sync_stats["new_leads"] += total_saved
        log.info(
            "Sync complete — %d posts fetched, %d leads saved (%d from proactive search)",
            total_fetched, total_saved, search_saved,
        )
    finally:
        db.close()
        _sync_stats["is_running"] = False
        _sync_stats["runtime_seconds"] = round(_time.monotonic() - t0, 1)

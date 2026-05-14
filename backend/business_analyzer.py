import json
import re
import anthropic
from backend.database import settings

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def analyze_business(user_text: str) -> dict:
    """Extract main_problem, ideal_customer, keywords, and buyer_phrases from free-form user text."""
    prompt = f"""Analyze the following business description and extract structured information.

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
        model="claude-opus-4-7",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    return _parse_json(text)


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

    prompt = f"""Given the following business strategy, suggest specific, real online communities where the ideal customers are active.

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
  ]
}}

Rules:
- MINIMUM SIZE: Only suggest communities with at least 1,000 members/subscribers. Prefer communities with 10,000+ members. Do NOT suggest small, niche, or dead communities.
- ACTIVITY: Only suggest communities that have had new posts or messages within the last 7 days. Skip dormant or rarely-active groups.
- Suggest 4-5 subreddits — each must have at least 10,000 subscribers and be actively posting. Pick the largest, most relevant ones.
- Suggest 2-3 Telegram channels with real @handles (no spaces in handle) — must have at least 1,000 members and post regularly.
- Discord: only include servers if you know the EXACT current invite code AND the server has 1,000+ members. If unsure, return an empty array — do not guess.
- LinkedIn: include 2-3 groups with real numeric group IDs (e.g. linkedin.com/groups/40949) that have 1,000+ members. If unsure of ID or size, omit.
- Job boards: include 2 real, high-traffic job boards whose audience matches the target locations.
- TARGET communities where the ideal customer goes to ASK FOR HELP, SEEK RECOMMENDATIONS, or DISCUSS PROBLEMS — not just communities where they hang out passively.
- AVOID broad general communities (r/india, r/news, r/worldnews, r/AskReddit etc.) — they create noise, not leads.
- NEVER suggest communities you are not confident exist and are active. Quality over quantity.
- Suggest 2-3 Quora topics where the ideal customer asks questions. Use real Quora topic slugs (lowercase with hyphens, e.g. "Software-as-a-Service"). These should be topics where buyers seek recommendations or ask for help with the problem this business solves."""

    response = _get_client().messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    return _parse_json(text)

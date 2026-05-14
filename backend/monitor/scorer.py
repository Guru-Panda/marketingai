import json
import logging
import re
import anthropic
from backend.database import settings

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def score_post(
    content: str,
    keywords: list[str],
    main_problem: str = "",
    ideal_customer: str = "",
    buyer_phrases: list[str] | None = None,
) -> dict:
    """Score a post for purchase/hiring intent using Claude Haiku.
    Returns: {intent_score, summary, keywords, contact: {email, phone, location}}
    """
    kw_str = ", ".join(keywords) if keywords else "business solutions"

    context_lines = []
    if main_problem:
        context_lines.append(f"Problem the business solves: {main_problem}")
    if ideal_customer:
        context_lines.append(f"Ideal customer: {ideal_customer}")
    if buyer_phrases:
        context_lines.append(f"Example buyer phrases to look for:\n" + "\n".join(f"  - {p}" for p in buyer_phrases[:8]))
    context_lines.append(f"Related keywords: {kw_str}")
    context_block = "\n".join(context_lines)

    prompt = f"""Analyze this social media post and score it for BUYER INTENT.

Business context:
{context_block}

A HIGH score (0.8-1.0) means the person is:
- Actively looking for this type of product/service right now
- Asking for recommendations or where to buy
- Describing a problem that this business solves
- Ready to spend money or make a decision soon

A LOW score (0.0-0.3) means the post is:
- Just general discussion, memes, or news
- About a completely unrelated topic
- From someone who is NOT a potential buyer

Post:
{content[:1500]}

Return ONLY valid JSON:
{{
  "intent_score": <0.0-1.0>,
  "summary": "<one sentence: why this person is or isn't a potential buyer>",
  "keywords": ["<matched keywords or phrases found in post>"],
  "contact": {{
    "email": "<email address mentioned in the post, or null>",
    "phone": "<phone number mentioned in the post, or null>",
    "location": "<country, city, or region mentioned or clearly implied, or null>"
  }}
}}"""

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def extract_contacts(texts: list[str]) -> dict:
    """Extract email, phone, location, and real name from profile/activity text snippets.
    Returns: {email, phone, location, name}
    """
    if not texts:
        return {}

    # Combine snippets, trim to a reasonable context window
    combined = "\n\n---\n\n".join(t[:800] for t in texts[:15])[:4000]

    prompt = f"""You are extracting contact information from a person's social media profile and activity.
Look carefully through all the text for email addresses, phone numbers, real names, and location.

Text snippets:
{combined}

Return ONLY valid JSON with what you found (use null for anything not found):
{{
  "email": "<email address or null>",
  "phone": "<phone number with country code if present, or null>",
  "location": "<most specific location found: city, state, country — or null>",
  "name": "<real full name if clearly stated, not a username — or null>"
}}"""

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        return {}

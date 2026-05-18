import json
import logging
import re
from backend.llm import llm_call  # Groq/Anthropic abstraction — do not use anthropic directly

log = logging.getLogger(__name__)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("LLM returned empty response")
    # Try stripping code fences first (but only if the inner content is non-empty)
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        inner = match.group(1).strip()
        if inner:
            text = inner
    # Try raw parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to first {...} block in case there's surrounding prose
        brace = re.search(r"\{[\s\S]*\}", text)
        if brace:
            return json.loads(brace.group(0))
        raise


def score_post(
    content: str,
    keywords: list[str],
    main_problem: str = "",
    ideal_customer: str = "",
    buyer_phrases: list[str] | None = None,
) -> dict:
    """Score a post for purchase/hiring intent.
    Returns: {intent_score, summary, keywords, contact: {email, phone, location}}
    """
    kw_str = ", ".join(keywords) if keywords else "business solutions"

    context_lines = []
    if main_problem:
        context_lines.append(f"Problem the business solves: {main_problem}")
    if ideal_customer:
        context_lines.append(f"Ideal customer: {ideal_customer}")
    if buyer_phrases:
        context_lines.append("Example buyer phrases to look for:\n" + "\n".join(f"  - {p}" for p in buyer_phrases[:8]))
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

    text = llm_call(prompt, max_tokens=350, high_quality=False)
    return _parse_json(text)


_TONE_PROMPTS = {
    "casual": "casual and friendly — like a helpful peer, not a salesperson",
    "professional": "professional and polished — respectful, clear, concise",
    "direct": "direct and to the point — no fluff, lead with the value proposition immediately",
    "empathetic": "empathetic and human — acknowledge their pain first, offer help second",
}

_PLATFORM_TONES = {
    "reddit": "casual and helpful — like a fellow Redditor",
    "hackernews": "direct and technical — HN readers value substance over sales",
    "stackoverflow": "helpful and non-salesy — offer genuine value first",
    "devto": "developer-friendly and genuine",
    "github": "technical and concise — GitHub users dislike spam",
    "indiehackers": "founder-to-founder, peer tone",
    "linkedin": "professional but warm",
    "telegram": "brief and conversational",
    "discord": "conversational and community-aware",
    "quora": "knowledgeable and helpful",
}


def generate_outreach(
    platform: str,
    post_content: str,
    summary: str,
    business_context: dict,
    extra_context: str = "",
    tone: str | None = None,
) -> str:
    """Generate a personalised outreach message for a lead."""
    tone_str = _TONE_PROMPTS.get(tone or "", "") or _PLATFORM_TONES.get(platform, "professional and helpful")

    prompt = f"""Write a personalised outreach message for a potential customer based on their post.

Platform: {platform}
Tone guide: {tone_str}

Business context:
- Problem we solve: {business_context.get("main_problem", "")}
- Ideal customer: {business_context.get("ideal_customer", "")}
{f"- Extra context: {extra_context}" if extra_context else ""}

Lead's post (summary): {summary}

Lead's original post:
{post_content[:800]}

Write a SHORT outreach message (max 120 words) that:
1. Opens by referencing something SPECIFIC from their post (shows you actually read it)
2. Briefly mentions how we can help with their exact problem
3. Ends with a low-pressure call-to-action (e.g. "happy to share more if useful")
4. Does NOT use generic openers like "I came across your post" or "Hope this helps!"
5. Sounds human, not templated

Return ONLY the message text, no preamble, no subject line."""

    return llm_call(prompt, max_tokens=300, high_quality=False)


def extract_contacts(texts: list[str]) -> dict:
    """Extract email, phone, location, and real name from profile/activity text snippets."""
    if not texts:
        return {}

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

    text = llm_call(prompt, max_tokens=150, high_quality=False)
    try:
        return _parse_json(text)
    except Exception:
        return {}

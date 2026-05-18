"""
Thin LLM abstraction layer.

Priority:
  1. Groq  — if GROQ_API_KEY is set (free tier, no credit card needed)
  2. Anthropic — if ANTHROPIC_API_KEY is set (paid)

Usage:
    from backend.llm import llm_call

    text = llm_call(prompt, max_tokens=1024, high_quality=True)
"""
import logging
from backend.database import settings

log = logging.getLogger(__name__)

# ── Groq models ───────────────────────────────────────────────────────────────
# high_quality=True  → larger model for analysis / channel suggestion
# high_quality=False → smaller/faster model for bulk post scoring
_GROQ_HQ_MODEL  = "llama-3.3-70b-versatile"
_GROQ_FAST_MODEL = "llama-3.1-8b-instant"

# ── Anthropic models ──────────────────────────────────────────────────────────
_ANTHROPIC_HQ_MODEL   = "claude-3-5-sonnet-20241022"
_ANTHROPIC_FAST_MODEL = "claude-haiku-4-5-20251001"

# ── Cached clients ────────────────────────────────────────────────────────────
_groq_client = None
_anthropic_client = None


def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
    return _groq_client


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


def llm_call(
    prompt: str,
    max_tokens: int = 1024,
    high_quality: bool = False,
) -> str:
    """Call the best available LLM and return the text response.

    Tries Groq first (free), falls back to Anthropic.
    Raises if neither key is configured or both fail.
    """
    groq_key = getattr(settings, "GROQ_API_KEY", "")
    anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")

    if groq_key:
        try:
            return _groq_call(prompt, max_tokens, high_quality)
        except Exception as e:
            log.warning("Groq call failed (%s), falling back to Anthropic", e)
            if anthropic_key:
                return _anthropic_call(prompt, max_tokens, high_quality)
            raise

    if anthropic_key:
        return _anthropic_call(prompt, max_tokens, high_quality)

    raise RuntimeError(
        "No LLM API key configured. Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY in Railway env vars."
    )


def _groq_call(prompt: str, max_tokens: int, high_quality: bool) -> str:
    model = _GROQ_HQ_MODEL if high_quality else _GROQ_FAST_MODEL
    client = _get_groq()
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    text = response.choices[0].message.content or ""
    log.debug("Groq [%s] → %d chars", model, len(text))
    return text.strip()


def _anthropic_call(prompt: str, max_tokens: int, high_quality: bool) -> str:
    model = _ANTHROPIC_HQ_MODEL if high_quality else _ANTHROPIC_FAST_MODEL
    client = _get_anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [b.text for b in response.content if b.type == "text"]
    if not text_blocks:
        raise ValueError("Anthropic returned no text content")
    log.debug("Anthropic [%s] → %d chars", model, len(text_blocks[0]))
    return text_blocks[0].strip()

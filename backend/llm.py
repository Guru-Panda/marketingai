"""
Thin LLM abstraction layer.

Priority:
  1. Groq  — if GROQ_API_KEY is set (free tier, no credit card needed)
  2. Anthropic — if ANTHROPIC_API_KEY is set (paid)

Rate-limit handling:
  - Groq 429 → sleep the suggested wait time, retry up to 3 times.
  - Empty/None response → treated as a transient error, retried the same way.
  - Other Groq errors → fall back to Anthropic if key is set, else raise.

Usage:
    from backend.llm import llm_call

    text = llm_call(prompt, max_tokens=1024, high_quality=True)
"""
import logging
import re
import time

from backend.database import settings

log = logging.getLogger(__name__)

# ── Groq models ───────────────────────────────────────────────────────────────
_GROQ_HQ_MODEL   = "llama-3.3-70b-versatile"
_GROQ_FAST_MODEL = "llama-3.1-8b-instant"

# ── Anthropic models ──────────────────────────────────────────────────────────
_ANTHROPIC_HQ_MODEL   = "claude-3-5-sonnet-20241022"
_ANTHROPIC_FAST_MODEL = "claude-haiku-4-5-20251001"

# ── Cached clients ────────────────────────────────────────────────────────────
_groq_client      = None
_anthropic_client = None

_RATE_LIMIT_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)

# Minimum gap between consecutive Groq calls to smooth out TPM usage.
# llama-3.1-8b-instant: 6 000 TPM free tier.
# A score_post call uses ~400 tokens → max ~15 calls/min → 1 call per 4s.
# Using 2s keeps us safely under while not being too slow.
_GROQ_MIN_INTERVAL = 2.0
_last_groq_call_at: float = 0.0


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


def _is_rate_limit(exc: Exception) -> bool:
    return "429" in str(exc) or "rate_limit" in str(exc).lower()


def _is_transient(exc: Exception) -> bool:
    """True for errors worth retrying (rate-limit or empty response)."""
    return _is_rate_limit(exc) or isinstance(exc, _EmptyResponseError)


def _wait_seconds(exc: Exception) -> float:
    """Extract retry-after seconds from Groq rate-limit error, default 10s."""
    m = _RATE_LIMIT_RE.search(str(exc))
    return float(m.group(1)) + 1.0 if m else 10.0


class _EmptyResponseError(Exception):
    pass


def llm_call(
    prompt: str,
    max_tokens: int = 1024,
    high_quality: bool = False,
) -> str:
    """Call the best available LLM and return the text response.

    Groq rate-limit / empty response → sleep + retry (×3).
    Other Groq errors → fall back to Anthropic if key is set, else raise.
    """
    groq_key      = getattr(settings, "GROQ_API_KEY", "")
    anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")

    if groq_key:
        for attempt in range(4):  # 1 initial + 3 retries
            try:
                return _groq_call(prompt, max_tokens, high_quality)
            except Exception as e:
                if _is_transient(e) and attempt < 3:
                    wait = _wait_seconds(e) if _is_rate_limit(e) else 5.0
                    log.info(
                        "Groq transient error (%s), sleeping %.1fs (attempt %d/3)",
                        type(e).__name__, wait, attempt + 1,
                    )
                    time.sleep(wait)
                    continue
                log.warning("Groq call failed after %d attempt(s): %s", attempt + 1, e)
                if anthropic_key:
                    try:
                        return _anthropic_call(prompt, max_tokens, high_quality)
                    except Exception as ae:
                        log.warning("Anthropic fallback also failed: %s", ae)
                raise

    if anthropic_key:
        return _anthropic_call(prompt, max_tokens, high_quality)

    raise RuntimeError(
        "No LLM API key configured. Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY in Railway env vars."
    )


def _groq_call(prompt: str, max_tokens: int, high_quality: bool) -> str:
    global _last_groq_call_at

    # Smooth out TPM: enforce minimum gap between calls
    gap = time.monotonic() - _last_groq_call_at
    if gap < _GROQ_MIN_INTERVAL:
        time.sleep(_GROQ_MIN_INTERVAL - gap)

    model = _GROQ_HQ_MODEL if high_quality else _GROQ_FAST_MODEL
    client = _get_groq()
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    _last_groq_call_at = time.monotonic()

    text = response.choices[0].message.content
    if not text:
        raise _EmptyResponseError(f"Groq [{model}] returned None content")
    stripped = text.strip()
    if not stripped:
        raise _EmptyResponseError(f"Groq [{model}] returned whitespace-only content")
    # Empty code fence (```json\n```) is semantically empty — retry rather than
    # passing a backtick-starting string to the JSON parser.
    if re.match(r'^```(?:json)?\s*```$', stripped):
        raise _EmptyResponseError(f"Groq [{model}] returned empty code fence block")
    log.debug("Groq [%s] → %d chars", model, len(stripped))
    return stripped


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

"""
Thin LLM abstraction layer.

Priority:
  1. Groq  — if GROQ_API_KEY is set (free tier, no credit card needed)
  2. Anthropic — if ANTHROPIC_API_KEY is set (paid)

Groq model fallback chain (each model has its own 500K token/day budget):
  fast  (high_quality=False): llama-3.1-8b-instant → gemma2-9b-it → llama-3.3-70b-versatile
  HQ    (high_quality=True):  llama-3.3-70b-versatile → gemma2-9b-it

On TPM 429 → sleep the suggested wait time and retry (same model, up to 3x).
On TPD 429 (daily limit) → immediately switch to next model in the chain.
Empty / whitespace / empty-code-fence response → retried like a transient error.

Usage:
    from backend.llm import llm_call

    text = llm_call(prompt, max_tokens=1024, high_quality=True)
"""
import logging
import re
import time

from backend.database import settings

log = logging.getLogger(__name__)

# ── Groq model chains ─────────────────────────────────────────────────────────
# Each model has its own independent 500 K tokens/day free-tier bucket.
# We try them in order; on a daily-limit (TPD) error we advance the chain.
_GROQ_FAST_CHAIN = [
    "llama-3.1-8b-instant",   # 6 000 TPM,  500 K TPD
    "gemma2-9b-it",            # 15 000 TPM, 500 K TPD  ← fallback
    "llama-3.3-70b-versatile", # 6 000 TPM,  500 K TPD  ← last resort
]
_GROQ_HQ_CHAIN = [
    "llama-3.3-70b-versatile", # primary HQ model
    "gemma2-9b-it",            # fallback if 70B daily quota exhausted
]

# ── Anthropic models ──────────────────────────────────────────────────────────
_ANTHROPIC_HQ_MODEL   = "claude-3-5-sonnet-20241022"
_ANTHROPIC_FAST_MODEL = "claude-haiku-4-5-20251001"

# ── Cached clients ────────────────────────────────────────────────────────────
_groq_client      = None
_anthropic_client = None

_RATE_LIMIT_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)

# Minimum gap between consecutive Groq calls (TPM smoothing).
# llama-3.1-8b / 70B: 6 000 TPM → ~1 call/sec at 100 tokens.
# Scoring calls use ~1 000 tokens → 1 call/6s to stay safe, but we use 2s
# to balance speed vs. quota given the 2-second inter-call throttle.
_GROQ_MIN_INTERVAL = 2.0
_last_groq_call_at: float = 0.0


class _EmptyResponseError(Exception):
    pass


class _DailyLimitError(Exception):
    """Groq per-model daily token quota (TPD) exhausted."""
    pass


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


def _is_tpm_rate_limit(exc: Exception) -> bool:
    """True for per-minute TPM limits (sleep & retry same model)."""
    msg = str(exc)
    return ("429" in msg or "rate_limit" in msg.lower()) and "per day" not in msg.lower() and "tpd" not in msg.lower()


def _is_tpd_limit(exc: Exception) -> bool:
    """True for per-day TPD limits (advance to next model)."""
    msg = str(exc).lower()
    return ("429" in msg or "rate_limit" in msg) and ("per day" in msg or "tpd" in msg or "tokens per day" in msg)


def _is_transient(exc: Exception) -> bool:
    return _is_tpm_rate_limit(exc) or isinstance(exc, _EmptyResponseError)


def _tpm_wait(exc: Exception) -> float:
    m = _RATE_LIMIT_RE.search(str(exc))
    return float(m.group(1)) + 1.0 if m else 10.0


def llm_call(
    prompt: str,
    max_tokens: int = 1024,
    high_quality: bool = False,
) -> str:
    """Call the best available LLM and return the text response.

    TPM 429  → sleep suggested wait, retry same model (×3).
    TPD 429  → switch to next model in chain immediately.
    All models exhausted → fall back to Anthropic (if key set), else raise.
    """
    groq_key      = getattr(settings, "GROQ_API_KEY", "")
    anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")

    if groq_key:
        chain = _GROQ_HQ_CHAIN if high_quality else _GROQ_FAST_CHAIN
        for model in chain:
            for attempt in range(4):  # 1 call + 3 TPM retries per model
                try:
                    return _groq_call(prompt, max_tokens, model)
                except _DailyLimitError as e:
                    log.warning("Groq model %s daily limit hit, trying next model", model)
                    break  # advance to next model in chain
                except _EmptyResponseError as e:
                    if attempt < 3:
                        log.info("Groq empty response (attempt %d/3), retrying in 5s", attempt + 1)
                        time.sleep(5.0)
                        continue
                    log.warning("Groq %s: empty response after 3 retries", model)
                    break  # try next model
                except Exception as e:
                    if _is_tpm_rate_limit(e) and attempt < 3:
                        wait = _tpm_wait(e)
                        log.info("Groq TPM limit on %s, sleeping %.1fs (attempt %d/3)", model, wait, attempt + 1)
                        time.sleep(wait)
                        continue
                    log.warning("Groq %s failed: %s", model, e)
                    break  # try next model

        # All Groq models exhausted — try Anthropic
        if anthropic_key:
            try:
                return _anthropic_call(prompt, max_tokens, high_quality)
            except Exception as ae:
                log.warning("Anthropic fallback failed: %s", ae)

        raise RuntimeError("All LLM providers exhausted. Groq daily quota likely hit for all models.")

    if anthropic_key:
        return _anthropic_call(prompt, max_tokens, high_quality)

    raise RuntimeError(
        "No LLM API key configured. Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY in Railway env vars."
    )


def _groq_call(prompt: str, max_tokens: int, model: str) -> str:
    global _last_groq_call_at

    # Enforce minimum gap between calls to smooth TPM usage
    gap = time.monotonic() - _last_groq_call_at
    if gap < _GROQ_MIN_INTERVAL:
        time.sleep(_GROQ_MIN_INTERVAL - gap)

    client = _get_groq()
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
    except Exception as e:
        _last_groq_call_at = time.monotonic()
        # Re-classify as daily limit error so the caller can advance the chain
        if _is_tpd_limit(e):
            raise _DailyLimitError(str(e)) from e
        raise

    _last_groq_call_at = time.monotonic()

    text = response.choices[0].message.content
    if not text:
        raise _EmptyResponseError(f"Groq [{model}] returned None content")
    stripped = text.strip()
    if not stripped:
        raise _EmptyResponseError(f"Groq [{model}] returned whitespace-only content")
    if re.match(r'^```(?:json)?\s*```$', stripped):
        raise _EmptyResponseError(f"Groq [{model}] returned empty code-fence block")

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

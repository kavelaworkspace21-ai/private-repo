"""
Provider-agnostic LLM configuration.

The app talks to the answer LLM through the OpenAI SDK, so it works with ANY OpenAI-compatible
endpoint. This lets us run at **zero cost** with a free provider instead of paid OpenAI.

Set these in `.env` (example uses Groq — free, no credit card):
    AI_API_KEY=gsk_your_free_groq_key
    AI_BASE_URL=https://api.groq.com/openai/v1
    AI_MODEL=llama-3.3-70b-versatile

Other free OpenAI-compatible options: Google Gemini (https://generativelanguage.googleapis.com/v1beta/openai/),
Cerebras (https://api.cerebras.ai/v1), OpenRouter free models (https://openrouter.ai/api/v1).

Backward compatible: if AI_* are unset it falls back to OPENAI_API_KEY + the OpenAI default endpoint.
Embeddings are handled separately (local by default) in vector_store.py — they do NOT use this key.
"""
import os
import time
import logging

logger = logging.getLogger(__name__)

# ── Model failover (2026-07-15) ──────────────────────────────────────────────────
# Live incident: NVIDIA's `meta/llama-3.3-70b-instruct` ACCEPTED connections but never
# answered /chat/completions (models list fine, 3.1-70B/8B fine) — so every AI feature
# hung for the full timeout and the whole app looked "broken". Fix: when
# AI_FALLBACK_MODELS is set, ai_config() probes the candidates with a tiny 1-token
# request (6s cap) and returns the FIRST RESPONSIVE model, cached for 10 minutes so
# the probe costs nothing in steady state. With no fallbacks configured the behaviour
# is exactly as before (no probe, no extra traffic).
_PROBE_TTL_SECONDS = 600
_model_cache: dict = {"model": None, "expires": 0.0, "fingerprint": ""}


def _candidate_models(primary: str) -> list[str]:
    fallbacks = [m.strip() for m in os.getenv("AI_FALLBACK_MODELS", "").split(",") if m.strip()]
    return [primary] + [m for m in fallbacks if m != primary]


def _model_responds(api_key: str, base_url: str | None, model: str, timeout: float = 6.0) -> bool:
    """One tiny completion — proves the model actually ANSWERS. (A hanging model still
    passes every connectivity test; only a real completion catches it.)"""
    try:
        import httpx
        url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        r = httpx.post(url, headers={"Authorization": f"Bearer {api_key}"},
                       json={"model": model,
                             "messages": [{"role": "user", "content": "ping"}],
                             "max_tokens": 1},
                       timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _resolve_model(api_key: str, base_url: str | None, primary: str) -> str:
    candidates = _candidate_models(primary)
    if len(candidates) == 1 or not api_key:
        return primary                      # no fallbacks configured → legacy behaviour
    fingerprint = f"{base_url}|{','.join(candidates)}"
    now = time.monotonic()
    if (_model_cache["model"] and _model_cache["fingerprint"] == fingerprint
            and now < _model_cache["expires"]):
        return _model_cache["model"]
    chosen = primary                        # if nothing answers, keep primary (old error paths)
    for m in candidates:
        if _model_responds(api_key, base_url, m):
            chosen = m
            break
        logger.warning(f"AI model '{m}' not responding — trying next fallback.")
    if chosen != primary:
        logger.warning(f"AI model failover: using '{chosen}' (primary '{primary}' unresponsive).")
    _model_cache.update({"model": chosen, "expires": now + _PROBE_TTL_SECONDS,
                         "fingerprint": fingerprint})
    return chosen


def ai_config() -> dict:
    """Resolve {api_key, base_url, model} for the answer LLM (read at call time).
    `model` is the first RESPONSIVE candidate when AI_FALLBACK_MODELS is set."""
    api_key = os.getenv("AI_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("AI_BASE_URL", "").strip() or None   # None => OpenAI default endpoint
    primary = os.getenv("AI_MODEL", "").strip() or "gpt-4o"
    model = _resolve_model(api_key, base_url, primary)
    return {"api_key": api_key, "base_url": base_url, "model": model}


def transcribe_config() -> dict:
    """Resolve {api_key, base_url, model} for audio transcription (Whisper-compatible endpoint).
    Falls back to the main AI key/base; set TRANSCRIBE_* to point at a Whisper-capable provider
    (free option: Groq `whisper-large-v3`). api_key='' means transcription is not configured."""
    api_key = (os.getenv("TRANSCRIBE_API_KEY", "").strip()
               or os.getenv("AI_API_KEY", "").strip()
               or os.getenv("OPENAI_API_KEY", "").strip())
    base_url = (os.getenv("TRANSCRIBE_BASE_URL", "").strip()
                or os.getenv("AI_BASE_URL", "").strip() or None)
    model = os.getenv("TRANSCRIBE_MODEL", "").strip() or "whisper-large-v3"
    return {"api_key": api_key, "base_url": base_url, "model": model}


def is_transcribe_enabled() -> bool:
    """True only when a transcription provider is DELIBERATELY configured (dedicated TRANSCRIBE_*).
    The plain AI fallback (e.g. Gemini) doesn't support audio, so we never falsely advertise voice
    input — the mic button shows only when transcription will actually work (set a free Groq key)."""
    return bool(os.getenv("TRANSCRIBE_API_KEY", "").strip()
                or os.getenv("TRANSCRIBE_BASE_URL", "").strip())


AI_NOT_CONFIGURED_MSG = (
    "**No AI provider configured.**\n\n"
    "Set a free, OpenAI-compatible model in your `.env`, then restart the server. Example (Groq — "
    "free, no credit card):\n\n"
    "```\nAI_API_KEY=gsk_your_free_key\nAI_BASE_URL=https://api.groq.com/openai/v1\n"
    "AI_MODEL=llama-3.3-70b-versatile\n```"
)

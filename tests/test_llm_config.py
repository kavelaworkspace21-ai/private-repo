"""
The answer LLM is provider-agnostic so the app can run on a FREE OpenAI-compatible provider
(e.g. Groq) instead of paid OpenAI. `ai_config()` resolves AI_* env, falling back to OPENAI_API_KEY.
"""
from app.ai.llm_config import ai_config

_VARS = ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "OPENAI_API_KEY")


def _clear(mp):
    for k in _VARS:
        mp.delenv(k, raising=False)


def test_defaults_when_unset(monkeypatch):
    _clear(monkeypatch)
    cfg = ai_config()
    assert cfg["api_key"] == ""
    assert cfg["base_url"] is None
    assert cfg["model"] == "gpt-4o"


def test_free_provider_vars_take_effect(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_API_KEY", "gsk_free")
    monkeypatch.setenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_MODEL", "llama-3.3-70b-versatile")
    cfg = ai_config()
    assert cfg["api_key"] == "gsk_free"
    assert cfg["base_url"] == "https://api.groq.com/openai/v1"
    assert cfg["model"] == "llama-3.3-70b-versatile"


def test_falls_back_to_openai_key(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
    cfg = ai_config()
    assert cfg["api_key"] == "sk-legacy"
    assert cfg["base_url"] is None


def test_ai_key_preferred_over_openai(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
    monkeypatch.setenv("AI_API_KEY", "gsk_free")
    assert ai_config()["api_key"] == "gsk_free"

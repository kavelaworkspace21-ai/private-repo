"""LSAI-LEGAL-01 / 09 — product identity locked + prohibited AI features permanently disabled."""
import pytest
from app import legal_config
from app.legal_config import assert_prohibited_disabled


def test_prohibited_features_all_disabled():
    assert all(v is False for v in legal_config.PROHIBITED_FEATURES.values())
    assert_prohibited_disabled()  # must not raise


def test_identity_flags_locked():
    assert legal_config.PUBLIC_AI_LAWYER is False
    assert legal_config.LAWYER_MARKETPLACE is False
    assert legal_config.LEAD_GENERATION is False
    assert legal_config.ADVOCATE_ADVERTISING is False
    assert "advocate" in legal_config.APP_POSITIONING.lower()


def test_assert_raises_if_a_prohibited_flag_flips(monkeypatch):
    monkeypatch.setitem(legal_config.PROHIBITED_FEATURES, "case_prediction", True)
    with pytest.raises(RuntimeError):
        assert_prohibited_disabled()


def test_public_identity_endpoint(client):
    r = client.get("/api/legal/identity")
    assert r.status_code == 200
    d = r.json()
    assert d["public_ai_lawyer"] is False
    assert d["lead_generation"] is False
    assert d["prohibited_features"]["case_prediction"] is False
    assert "advocate" in d["positioning"].lower()

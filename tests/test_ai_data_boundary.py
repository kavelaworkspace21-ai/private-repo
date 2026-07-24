"""LSAI-LEGAL-06 — AI data boundary: prompts are not exposed in logs; no-training promise surfaced."""
from app.ai.data_boundary import redact_for_log, NO_TRAINING_STATEMENT
from tests.conftest import register_and_login, auth


def test_redact_hides_raw_prompt():
    secret = "Confidential: client Ramesh wants to sue Acme for fraud"
    out = redact_for_log(secret)
    assert "Ramesh" not in out and "fraud" not in out
    assert "redacted" in out and "chars" in out


def test_redact_empty():
    assert redact_for_log("") == "<empty>"


def test_no_training_statement_is_real():
    assert "train" in NO_TRAINING_STATEMENT.lower()


def test_no_training_statement_exposed_via_api(client):
    tok = register_and_login(client, "boundary@firm.com")
    r = client.get("/api/account/privacy", headers=auth(tok)).json()
    assert "train" in r["no_training"].lower()

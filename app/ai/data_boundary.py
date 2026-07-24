"""
AI data boundary (LSAI-LEGAL-06).

Keeps client/matter prompt content out of shared application/server logs while still allowing
metadata-level auditing. Also re-exports the single-source no-training statement.
"""
import hashlib
from app.services.privacy import NO_TRAINING_STATEMENT  # noqa: F401 (re-exported)


def redact_for_log(text: str | None) -> str:
    """Return a log-safe representation of a prompt — length + short hash, never the raw content.

    Use this anywhere AI input might otherwise be logged, so private legal content never lands in
    shared logs (DPDP data minimisation; no leakage of client/matter data)."""
    if not text:
        return "<empty>"
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"<redacted prompt: {len(text)} chars, sha256:{h}>"

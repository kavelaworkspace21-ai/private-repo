"""Phase 5 — corpus edge-case governance.

Pins the transparency guarantees for known corpus anomalies. These are fulltext-only
(no vector store), so they are fast and deterministic.
"""
from app.ai.corpus_updates import corpus_anomalies, corpus_manifest


def test_ipc_354e_duplicate_is_recorded_not_silent():
    """IPC 354E carries two DIFFERENT provisions under one number. The index keeps the first;
    the drop MUST be visible as a legal-review anomaly (never invisible first-wins)."""
    anomalies = corpus_anomalies()
    a354e = [a for a in anomalies
             if a["act_id"] == "ipc_1860" and a["section"] == "354E"]
    assert len(a354e) == 1, "IPC 354E duplicate must be flagged exactly once"
    rec = a354e[0]
    assert rec["type"] == "duplicate_section_number"
    assert rec["count"] == 2
    assert rec["review_state"] == "PENDING_LEGAL_REVIEW"
    # Both provisions' evidence is surfaced: one kept, at least one dropped, and they differ.
    kept = rec["kept_in_index"]["title"]
    dropped_titles = [d["title"] for d in rec["dropped_from_index"]]
    assert kept and dropped_titles
    assert all(kept != d for d in dropped_titles), "kept and dropped must be distinct provisions"


def test_corpus_manifest_surfaces_anomalies():
    """Any corpus report (manifest) carries the anomalies list, so they can't be overlooked."""
    m = corpus_manifest()
    assert "anomalies" in m
    assert any(a["section"] == "354E" for a in m["anomalies"])


def test_no_unexpected_new_anomalies():
    """Regression guard: today the ONLY known duplicate-number anomaly is IPC 354E. A new one
    appearing means a fresh ingest introduced a collision that needs a review decision."""
    sections = {(a["act_id"], a["section"]) for a in corpus_anomalies()}
    assert sections == {("ipc_1860", "354E")}, (
        f"unexpected corpus anomalies changed: {sections} — investigate + govern before shipping")

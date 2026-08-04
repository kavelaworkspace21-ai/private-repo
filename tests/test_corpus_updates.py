"""Roadmap P3 — corpus versioning + upstream-change detection.

The corpus is trustworthy only while it matches the official source; these tests pin the
manifest/fingerprint semantics and the drift-detection contract (report, never mutate).
All offline: the network fetcher is injected."""
import json

from app.ai.corpus_updates import (
    corpus_manifest, corpus_version, check_upstream,
)


def test_manifest_reads_verified_provenance():
    m = corpus_manifest()
    assert m["act_count"] >= 30                      # the shipped corpus
    assert m["section_count"] > 3000
    by_id = {a["id"]: a for a in m["acts"]}
    ipc = by_id["ipc_1860"]
    assert len(ipc["sha256"]) == 64                  # real sha256 provenance
    assert ipc["status"] == "repealed"               # currency metadata surfaces
    assert "Bharatiya Nyaya Sanhita" in ipc["repealed_by"]
    assert len(m["corpus_version"]) == 12


def test_corpus_version_changes_iff_text_changes():
    acts = [{"id": "a", "sha256": "x" * 64}, {"id": "b", "sha256": "y" * 64}]
    v1 = corpus_version(acts)
    assert v1 == corpus_version(list(reversed(acts)))          # order-independent
    acts2 = [{"id": "a", "sha256": "x" * 64}, {"id": "b", "sha256": "z" * 64}]
    assert corpus_version(acts2) != v1                          # any text change → new version


def test_check_upstream_reports_drift_without_mutating(tmp_path, monkeypatch):
    import app.ai.corpus_updates as cu
    monkeypatch.setattr(cu, "CHECK_RESULT_PATH", tmp_path / "check.json")

    manifest = corpus_manifest()
    by_id = {a["id"]: a for a in manifest["acts"]}
    ndps_sha = by_id["ndps_1985"]["sha256"]

    def fake_fetch(url):
        if "narcotic" in url:
            return ndps_sha                     # unchanged
        if "A1988-49" in url:
            return "0" * 64                     # PoCA republished upstream
        raise RuntimeError("connect timeout")   # everything else errors

    out = check_upstream(act_ids=["ndps_1985", "poca_1988", "pmla_2002"], fetcher=fake_fetch)
    assert out["results"]["ndps_1985"]["status"] == "unchanged"
    assert out["results"]["poca_1988"]["status"] == "UPDATED_UPSTREAM"
    assert "re-ingest" in out["results"]["poca_1988"]["detail"]   # points to the discipline
    assert out["results"]["pmla_2002"]["status"] == "error"
    assert out["summary"]["updated_upstream"] == 1

    # persisted for the status endpoint, and corpus files untouched (report-only contract)
    monkeypatch.setattr(cu, "CHECK_RESULT_PATH", tmp_path / "check.json")
    saved = json.loads((tmp_path / "check.json").read_text(encoding="utf-8"))
    assert saved["summary"]["updated_upstream"] == 1
    assert corpus_manifest()["corpus_version"] == manifest["corpus_version"]


def test_handle_page_urls_are_skipped_not_fetched(tmp_path, monkeypatch):
    """Acts whose stored source URL is a handle page (no direct PDF) must be skipped,
    never fetched — no guessing at bitstream URLs."""
    import app.ai.corpus_updates as cu
    monkeypatch.setattr(cu, "CHECK_RESULT_PATH", tmp_path / "check.json")

    def explode(url):
        raise AssertionError("fetcher must not be called for handle-page URLs")

    # constitution's stored source URL is the handle page
    out = check_upstream(act_ids=["constitution_1950"], fetcher=explode)
    assert out["results"]["constitution_1950"]["status"] == "skipped_no_pdf"


def test_corpus_status_endpoint_requires_auth(client):
    assert client.get("/api/library/corpus-status").status_code == 401


def test_corpus_status_endpoint_returns_manifest(client):
    from tests.conftest import register_and_login, auth
    tok = register_and_login(client, "corpus.status@firm.com", "Corpus Status")
    r = client.get("/api/library/corpus-status", headers=auth(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["act_count"] >= 30 and len(body["corpus_version"]) == 12
    assert "last_upstream_check" in body


def test_corpus_check_updates_is_founder_only(client):
    from tests.conftest import register_and_login, auth
    tok = register_and_login(client, "corpus.check@firm.com", "Corpus Check")
    # no admin token → fail-closed 403 (even for an authed advocate)
    r = client.post("/api/library/corpus-check-updates", headers=auth(tok))
    assert r.status_code == 403

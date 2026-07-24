"""Phase 1 — release identity + fail-closed preflight (app/ops/release.py).

These pin the reproducible-release guarantees:
  * RELEASE.json stays honest — its corpus fingerprint + migration head must match the
    actual repo, so a corpus change without a re-freeze is caught.
  * preflight() fails closed on a stale corpus, an unbuilt/mismatched index, a drifted
    migration head, missing secrets, or low disk.
The preflight cases use fabricated live/release dicts, so they're independent of the
machine's real chroma/disk/env.
"""
import copy

from app.ops import release as rel


# ── RELEASE.json is honest about the actual repo ────────────────────────────────
def test_release_json_matches_actual_corpus_and_migrations():
    r = rel.load_release()
    live = rel.live_status()
    assert live["corpus_fingerprint"] == r["corpus_fingerprint"], (
        "RELEASE.json corpus_fingerprint is stale — run `python -m app.ops.release freeze` "
        "after any corpus change")
    assert live["migration_head"] == r["migration_head"], (
        "RELEASE.json migration_head is stale vs the migration scripts")
    assert live["app_version"] == r["app_version"]


def test_live_status_never_leaks_secret_values():
    live = rel.live_status()
    # config reports presence booleans only, never values
    assert set(live["config"].values()) <= {True, False}
    for key in ("app_version", "corpus_fingerprint", "migration_head", "chroma_count",
                "embedding_model", "commit", "branch", "tree_dirty", "python",
                "disk_free_mb", "config"):
        assert key in live


# ── preflight: happy path ───────────────────────────────────────────────────────
def _good_live(r):
    return {
        "app_version": r["app_version"],
        "corpus_fingerprint": r["corpus_fingerprint"],
        "migration_head": r["migration_head"],
        "chroma_count": r["expected_chunk_count"],
        "disk_free_mb": 100_000,
        "config": {"JWT_SECRET": True, "FIELD_ENCRYPTION_KEY": True},
    }


def test_preflight_ok_when_everything_matches():
    r = rel.load_release()
    assert rel.preflight(live=_good_live(r), release=r) == []


# ── preflight: each failure is caught ───────────────────────────────────────────
def test_preflight_blocks_stale_corpus():
    r = rel.load_release()
    live = _good_live(r)
    live["corpus_fingerprint"] = "deadbeefcafe"
    issues = rel.preflight(live=live, release=r)
    assert any("corpus fingerprint" in i for i in issues)


def test_preflight_blocks_unbuilt_or_mismatched_index():
    r = rel.load_release()
    live = _good_live(r)
    live["chroma_count"] = None            # index not built
    assert any("vector index count" in i for i in rel.preflight(live=live, release=r))
    live["chroma_count"] = r["expected_chunk_count"] - 5   # partial reseed
    assert any("vector index count" in i for i in rel.preflight(live=live, release=r))


def test_preflight_blocks_migration_drift():
    r = rel.load_release()
    live = _good_live(r)
    live["migration_head"] = "0000deadbeef"
    assert any("migration head" in i for i in rel.preflight(live=live, release=r))


def test_preflight_blocks_missing_secrets_but_can_be_waived():
    r = rel.load_release()
    live = _good_live(r)
    live["config"] = {"JWT_SECRET": False, "FIELD_ENCRYPTION_KEY": True}
    assert any("JWT_SECRET" in i for i in rel.preflight(live=live, release=r))
    # non-prod preflight can waive the secret checks
    assert rel.preflight(live=live, release=r, require_secrets=False) == []


def test_preflight_blocks_low_disk():
    r = rel.load_release()
    live = _good_live(r)
    live["disk_free_mb"] = 100
    assert any("low disk" in i for i in rel.preflight(live=live, release=r))


# ── Source identity: commit pin + dirty tree (Phase 0) ──────────────────────────
def test_preflight_blocks_dirty_working_tree():
    r = rel.load_release()
    live = _good_live(r)
    live["tree_dirty"] = True
    assert any("uncommitted changes" in i for i in rel.preflight(live=live, release=r))
    # local checks may waive it; a prod deploy never should
    assert rel.preflight(live=live, release=r, require_clean_tree=False) == []


def test_preflight_blocks_tree_that_is_not_the_pinned_commit():
    r = copy.deepcopy(rel.load_release())
    r["commit"] = "aaaaaaa"
    live = _good_live(r)
    live["commit"] = "bbbbbbb"
    assert any("not the audited release" in i for i in rel.preflight(live=live, release=r))


def test_pinned_commit_tolerates_the_release_json_stamp_commit(monkeypatch):
    """freeze() stamps HEAD into RELEASE.json; committing that stamp advances HEAD by
    one commit. That single RELEASE.json-only step must still satisfy the pin."""
    monkeypatch.setattr(rel, "_git", lambda *a: "RELEASE.json")
    assert rel._commit_matches("aaaaaaa", "bbbbbbb") is True
    # anything else in the diff fails the match
    monkeypatch.setattr(rel, "_git", lambda *a: "RELEASE.json\napp/main.py")
    assert rel._commit_matches("aaaaaaa", "bbbbbbb") is False


def test_source_identity_checks_degrade_when_git_is_unavailable(monkeypatch):
    """A production tarball deploy has no .git — status and preflight must still work."""
    monkeypatch.setattr(rel, "_git", lambda *a: None)
    ident = rel._git_identity()
    assert ident == {"commit": None, "branch": None, "tree_dirty": None}
    r = copy.deepcopy(rel.load_release())
    r["commit"] = "aaaaaaa"
    live = _good_live(r)
    live.update(ident)
    assert rel.preflight(live=live, release=r) == []


def test_release_json_pins_the_commit_it_was_frozen_from():
    r = rel.load_release()
    live = rel.live_status()
    if live["commit"] is None:
        return  # not a git checkout (tarball / CI export) — nothing to pin against
    assert r.get("commit"), (
        "RELEASE.json has no commit — run `python -m app.ops.release freeze`")
    assert rel._commit_matches(r["commit"], live["commit"]), (
        f"RELEASE.json pins {r['commit']} but HEAD is {live['commit']} — re-freeze")


# ── CLI ─────────────────────────────────────────────────────────────────────────
def test_cli_status_returns_zero(capsys):
    assert rel.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "corpus_fingerprint" in out

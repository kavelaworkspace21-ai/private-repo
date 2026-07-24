"""Release identity, status, and fail-closed deploy preflight (Phase 1).

Why this exists: the Chroma vector index used to be shipped by copying a local Windows
D:-drive folder — an undocumented, unverifiable release step. That index is actually
DERIVED from the versioned ``app/legal_corpus/fulltext/*.json``, so a clean build can
regenerate it deterministically (``reseed()``) and prove it by fingerprint. ``RELEASE.json``
pins the verified identity; ``preflight()`` refuses to let a deploy proceed on a stale or
altered corpus, a drifted migration head, or missing critical secrets.

Everything here is BOOT-FREE: it never imports ``app.main`` (so it can't trip the soul/
prohibited boot gates) and never prints secret VALUES — only presence booleans.

CLI:
    python -m app.ops.release status      # JSON of live identity + config presence
    python -m app.ops.release preflight   # exit 1 (with reasons) if the deploy must not proceed
    python -m app.ops.release freeze       # rewrite RELEASE.json from the current verified state
"""
from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_PATH = ROOT / "RELEASE.json"
DISK_FLOOR_MB = 500


def load_release() -> dict:
    """The pinned release identity (RELEASE.json)."""
    return json.loads(RELEASE_PATH.read_text(encoding="utf-8"))


def _migration_head() -> str | None:
    """Head revision of the migration scripts (no DB connection needed)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        cfg = Config(str(ROOT / "alembic.ini"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        return None


def _chroma_count() -> int | None:
    """Live vector-index chunk count, or None if the index isn't built yet.

    Opens the collection WITHOUT an embedding function — count() never embeds, so this
    stays fast and doesn't pull the ONNX model.
    """
    try:
        import chromadb
        from app.ai.vector_store import CHROMA_PATH, COLLECTION_NAME
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        return client.get_collection(COLLECTION_NAME).count()
    except Exception:
        return None


def _git(*args: str) -> str | None:
    """Run a git command in the project root; None if git or the repo is unavailable.

    Deliberately tolerant: a production tarball deploy has no .git, and that must not
    break status or preflight — the pinned identity fields carry the guarantee there.
    """
    try:
        out = subprocess.run(["git", "-C", str(ROOT), *args],
                             capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _git_identity() -> dict:
    """Commit / branch / dirty-tree state. All None when git isn't available."""
    commit = _git("rev-parse", "--short=7", "HEAD")
    if not commit:
        return {"commit": None, "branch": None, "tree_dirty": None}
    status = _git("status", "--porcelain")
    return {
        "commit": commit,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        # None (not False) if `git status` itself failed — unknown is not "clean".
        "tree_dirty": None if status is None else bool(status),
    }


def _commit_matches(pinned: str, live: str) -> bool:
    """Is the live commit the pinned release commit?

    Exact prefix match, OR the two commits differ ONLY in RELEASE.json. That exception
    exists because ``freeze()`` stamps the CURRENT commit into RELEASE.json, and
    committing that stamp necessarily advances HEAD by one commit — without this the
    pin could never be satisfied. Any other changed file fails the match.
    """
    if live.startswith(pinned) or pinned.startswith(live):
        return True
    changed = _git("diff", "--name-only", pinned, "HEAD")
    if changed is None:
        return False
    return {f.strip() for f in changed.splitlines() if f.strip()}.issubset({"RELEASE.json"})


def _embedding_model() -> str:
    import os
    return "openai:text-embedding-3-small" if os.getenv("OPENAI_EMBEDDINGS_KEY") else "onnx-default-minilm"


def _config_presence() -> dict:
    """Which critical config is SET (booleans only — never the values)."""
    import os
    return {
        "JWT_SECRET": bool(os.getenv("JWT_SECRET")),
        "FIELD_ENCRYPTION_KEY": bool(os.getenv("FIELD_ENCRYPTION_KEY")),
        "DATABASE_URL": bool(os.getenv("DATABASE_URL")),          # unset => local SQLite
        "AI_MODEL_KEY": bool(os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")),
        "CHROMA_PATH": bool(os.getenv("CHROMA_PATH")),
    }


def live_status() -> dict:
    """Current runtime identity — safe to expose (no secret values)."""
    from app.version import __version__
    from app.ai.corpus_updates import corpus_version
    from app.ai import vector_store as vs
    try:
        free_mb: int | None = round(vs.disk_free_bytes() / 1024 ** 2)
    except Exception:
        free_mb = None
    return {
        "app_version": __version__,
        "corpus_fingerprint": corpus_version(),
        "migration_head": _migration_head(),
        "chroma_count": _chroma_count(),
        "embedding_model": _embedding_model(),
        **_git_identity(),
        "python": platform.python_version(),
        "disk_free_mb": free_mb,
        "chroma_path": str(vs.CHROMA_PATH),
        "config": _config_presence(),
    }


def preflight(live: dict | None = None, release: dict | None = None,
              require_secrets: bool = True, require_clean_tree: bool = True) -> list[str]:
    """Return a list of BLOCKING problems (empty list = safe to deploy).

    Fail-closed: a stale/altered corpus, an unbuilt or mismatched index, a drifted
    migration head, missing secrets, low disk, an uncommitted working tree, or a tree
    that isn't the pinned release commit each block the deploy. ``live``/``release``
    are injectable for tests.
    """
    live = live if live is not None else live_status()
    release = release if release is not None else load_release()
    issues: list[str] = []

    if live.get("app_version") != release.get("app_version"):
        issues.append(
            f"app version {live.get('app_version')} != release {release.get('app_version')}")
    if live.get("corpus_fingerprint") != release.get("corpus_fingerprint"):
        issues.append(
            f"corpus fingerprint {live.get('corpus_fingerprint')} != release "
            f"{release.get('corpus_fingerprint')} — stale or altered corpus")
    if live.get("chroma_count") != release.get("expected_chunk_count"):
        issues.append(
            f"vector index count {live.get('chroma_count')} != expected "
            f"{release.get('expected_chunk_count')} — reseed the index")
    if live.get("migration_head") != release.get("migration_head"):
        issues.append(
            f"migration head {live.get('migration_head')} != release "
            f"{release.get('migration_head')} — run 'alembic upgrade head'")
    # Source identity. Both checks no-op when git is unavailable (tarball deploy), where
    # the pinned corpus/migration/version fields above carry the guarantee instead.
    if require_clean_tree and live.get("tree_dirty"):
        issues.append(
            "working tree has uncommitted changes — deploy the committed release, "
            "not a dirty tree")
    pinned_commit, live_commit = release.get("commit"), live.get("commit")
    if pinned_commit and live_commit and not _commit_matches(pinned_commit, live_commit):
        issues.append(
            f"commit {live_commit} != pinned release commit {pinned_commit} — "
            "this tree is not the audited release")

    if require_secrets:
        cfg = live.get("config", {})
        for key in ("JWT_SECRET", "FIELD_ENCRYPTION_KEY"):
            if not cfg.get(key):
                issues.append(f"missing required secret config: {key}")
    free = live.get("disk_free_mb")
    if free is not None and free < DISK_FLOOR_MB:
        issues.append(f"low disk: {free} MB free (< {DISK_FLOOR_MB} MB floor)")
    return issues


def freeze() -> dict:
    """Rewrite RELEASE.json from the current verified state (run after a corpus reseed)."""
    from app.util.time import utcnow
    live = live_status()
    rel = load_release()
    rel.update({
        "app_version": live["app_version"],
        "corpus_fingerprint": live["corpus_fingerprint"],
        "migration_head": live["migration_head"],
        "embedding_model": live["embedding_model"],
        "expected_chunk_count": live["chroma_count"],
        "generated_at": utcnow().strftime("%Y-%m-%d"),
    })
    if live.get("commit"):
        rel["commit"] = live["commit"]
    RELEASE_PATH.write_text(json.dumps(rel, indent=2) + "\n", encoding="utf-8")
    return rel


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Juriscite release identity / preflight.")
    ap.add_argument("command", choices=["status", "preflight", "freeze"])
    ap.add_argument("--no-require-secrets", action="store_true",
                    help="skip the JWT_SECRET / FIELD_ENCRYPTION_KEY checks (non-prod preflight)")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="allow uncommitted working-tree changes (local checks only, never prod)")
    args = ap.parse_args(argv)

    if args.command == "status":
        print(json.dumps(live_status(), indent=2))
        return 0
    if args.command == "freeze":
        print(json.dumps(freeze(), indent=2))
        return 0
    # preflight
    issues = preflight(require_secrets=not args.no_require_secrets,
                       require_clean_tree=not args.allow_dirty)
    if issues:
        print("PREFLIGHT FAILED — deployment must NOT proceed:")
        for i in issues:
            print(f"  x {i}")
        return 1
    print("PREFLIGHT OK — release identity matches and required config is present.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

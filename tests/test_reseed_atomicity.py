"""Reseed atomicity — build into a temp collection, swap by rename.

The old reseed() deleted the live collection FIRST and then embedded for minutes. Anything
that interrupted that window left the store empty or truncated while still ANSWERING
QUERIES, just with most of the law missing. That is the worst possible failure shape for a
legal tool: it looks healthy and quietly stops finding statutes.

It happened three times:
  * 2026-07-20  sqlite "disk full" mid-write
  * 2026-07-25  a second reseed started while one was running
  * 2026-07-29  a reseed process was killed, leaving 1,200 of 8,704 chunks

These tests pin the guards that make each of those non-silent. They use a fake ChromaDB
client rather than the real store: the point is the ORDER of operations and what survives a
failure, and a real reseed embeds ~8,700 chunks (minutes) which no unit test should do.
"""
import pytest

from app.ai import vector_store as vs


# ── fake chroma ────────────────────────────────────────────────────────────────
class FakeCollection:
    def __init__(self, name, store):
        self.name = name
        self._store = store

    def count(self):
        return self._store[self.name]

    def modify(self, name=None, **kw):
        if name and name != self.name:
            self._store[name] = self._store.pop(self.name)
            self.name = name


class FakeClient:
    """Minimal stand-in: collection name -> chunk count."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.ops = []

    def list_collections(self):
        return [FakeCollection(n, self.store) for n in list(self.store)]

    def get_collection(self, name):
        if name not in self.store:
            raise ValueError(f"no such collection: {name}")
        return FakeCollection(name, self.store)

    def create_collection(self, name, **kw):
        self.ops.append(f"create:{name}")
        self.store[name] = 0
        return FakeCollection(name, self.store)

    def delete_collection(self, name):
        self.ops.append(f"delete:{name}")
        if name not in self.store:
            raise ValueError(f"no such collection: {name}")
        del self.store[name]


LIVE = vs.COLLECTION_NAME
BUILD = vs.BUILD_COLLECTION_NAME


@pytest.fixture
def chroma(monkeypatch, tmp_path):
    """Fake client + ample disk + a lock file isolated to this test."""
    monkeypatch.setattr(vs, "RESEED_LOCK_PATH", tmp_path / ".reseed.lock")
    monkeypatch.setattr(vs, "disk_free_bytes", lambda *a, **k: 50 * 1024 ** 3)
    monkeypatch.setattr(vs, "_embedding_fn", lambda: None)
    monkeypatch.setattr(vs, "_collection", None)

    client = FakeClient({LIVE: 8704})
    monkeypatch.setattr(vs, "_get_client", lambda: client)
    # get_collection() is called at the end of reseed(); short-circuit it.
    monkeypatch.setattr(vs, "get_collection", lambda: FakeCollection(LIVE, client.store))
    return client


def _seed_n(n):
    """A _seed_collection stub that fills the build collection with n chunks."""
    def _seed(collection):
        collection._store[collection.name] = n
    return _seed


# ── the core property: a failed build must not touch the live corpus ───────────
def test_interrupted_build_leaves_live_corpus_intact(chroma, monkeypatch):
    """The 2026-07-29 failure. A build that dies mid-embed must not be visible."""
    def _explode(collection):
        collection._store[collection.name] = 1200   # partial, as in the real incident
        raise KeyboardInterrupt("process killed mid-reseed")
    monkeypatch.setattr(vs, "_seed_collection", _explode)

    with pytest.raises(KeyboardInterrupt):
        vs.reseed()

    assert chroma.store[LIVE] == 8704, "live corpus must survive an interrupted build"
    assert BUILD not in chroma.store, "the partial build must be cleaned up"


def test_live_collection_is_deleted_only_after_a_successful_build(chroma, monkeypatch):
    """Ordering is the whole fix: build fully, THEN delete live, THEN rename."""
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(8704))

    vs.reseed()

    assert chroma.ops.index(f"create:{BUILD}") < chroma.ops.index(f"delete:{LIVE}"), \
        "the build must be created before the live collection is deleted"
    assert chroma.store[LIVE] == 8704
    assert BUILD not in chroma.store, "build must have been renamed, not left behind"


# ── truncation guard ───────────────────────────────────────────────────────────
def test_truncated_build_is_refused(chroma, monkeypatch):
    """A build far smaller than live is the 1,200-of-8,704 shape — refuse the swap."""
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(1200))

    with pytest.raises(RuntimeError, match="untouched"):
        vs.reseed()

    assert chroma.store[LIVE] == 8704, "a truncated build must never replace the corpus"
    assert BUILD not in chroma.store


def test_empty_build_is_refused(chroma, monkeypatch):
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(0))
    with pytest.raises(RuntimeError, match="0 chunks"):
        vs.reseed()
    assert chroma.store[LIVE] == 8704


def test_force_allows_a_genuine_shrink(chroma, monkeypatch):
    """The corpus can legitimately shrink; force must be available but explicit."""
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(1200))
    vs.reseed(force=True)
    assert chroma.store[LIVE] == 1200


def test_small_shrink_within_tolerance_is_allowed(chroma, monkeypatch):
    """Ordinary churn (a few chunks) must not trip the guard."""
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(8600))
    vs.reseed()
    assert chroma.store[LIVE] == 8600


def test_first_ever_seed_has_no_live_collection_to_compare(monkeypatch, tmp_path):
    """With no live collection the shrink check must not fire (division by a live of 0)."""
    monkeypatch.setattr(vs, "RESEED_LOCK_PATH", tmp_path / ".reseed.lock")
    monkeypatch.setattr(vs, "disk_free_bytes", lambda *a, **k: 50 * 1024 ** 3)
    monkeypatch.setattr(vs, "_embedding_fn", lambda: None)
    client = FakeClient({})
    monkeypatch.setattr(vs, "_get_client", lambda: client)
    monkeypatch.setattr(vs, "get_collection", lambda: FakeCollection(LIVE, client.store))
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(42))

    vs.reseed()
    assert client.store[LIVE] == 42


# ── concurrency ────────────────────────────────────────────────────────────────
def test_concurrent_reseed_is_refused(chroma, monkeypatch):
    """The 2026-07-25 / -29 failure: a second reseed while one is running."""
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(8704))

    def _reseed_again(collection):
        # Simulate a second process arriving mid-build.
        with pytest.raises(RuntimeError, match="another reseed is in progress"):
            vs.reseed()
        collection._store[collection.name] = 8704
    monkeypatch.setattr(vs, "_seed_collection", _reseed_again)

    vs.reseed()
    assert chroma.store[LIVE] == 8704


def test_lock_is_released_after_a_failed_reseed(chroma, monkeypatch):
    """A crashed reseed must not wedge the store until someone deletes a lock file."""
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(0))
    with pytest.raises(RuntimeError):
        vs.reseed()
    assert not vs.RESEED_LOCK_PATH.exists(), "lock must be released on failure"

    monkeypatch.setattr(vs, "_seed_collection", _seed_n(8704))
    vs.reseed()          # must not raise "another reseed is in progress"


def test_stale_lock_is_taken_over(chroma, monkeypatch):
    """An hour-old lock means the holder died; don't require manual cleanup forever."""
    vs.RESEED_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    vs.RESEED_LOCK_PATH.write_text("pid=999999 host=dead", encoding="utf-8")
    import os as _os
    old = vs.time.time() - vs.RESEED_LOCK_STALE_SECONDS - 60
    _os.utime(vs.RESEED_LOCK_PATH, (old, old))

    monkeypatch.setattr(vs, "_seed_collection", _seed_n(8704))
    vs.reseed()
    assert chroma.store[LIVE] == 8704


def test_lock_staleness_never_probes_the_pid(chroma):
    """Guard against a Windows footgun.

    os.kill(pid, 0) is the usual liveness probe, but on Windows CPython maps a non-CTRL
    signal to TerminateProcess — so "is it alive?" would KILL the process it asks about.
    Staleness must be decided by mtime alone.
    """
    import ast
    import inspect
    import textwrap

    # Parse rather than grep: the function's own docstring explains the hazard by name, so
    # a substring search matches the warning against it and never the mistake.
    tree = ast.parse(textwrap.dedent(inspect.getsource(vs._reseed_lock)))
    calls = [
        f"{getattr(n.func.value, 'id', '?')}.{n.func.attr}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert "os.kill" not in calls, (
        "os.kill must never be used for lock liveness: on Windows CPython maps it to "
        "TerminateProcess, so the probe kills the process it asks about")


# ── recovery from a death inside the swap window ───────────────────────────────
def test_orphaned_build_is_adopted(monkeypatch):
    """Death between delete(live) and rename leaves a COMPLETE build and no live."""
    client = FakeClient({BUILD: 8704})
    assert vs._adopt_orphaned_build(client) is True
    assert client.store == {LIVE: 8704}, "the rename should have been completed"


def test_orphaned_empty_build_is_discarded(monkeypatch):
    client = FakeClient({BUILD: 0})
    assert vs._adopt_orphaned_build(client) is False
    assert BUILD not in client.store


def test_build_alongside_a_live_collection_is_not_adopted(monkeypatch):
    """If live exists, a leftover build is scrap from a failed run — never adopt it."""
    client = FakeClient({LIVE: 8704, BUILD: 1200})
    assert vs._adopt_orphaned_build(client) is False
    assert client.store[LIVE] == 8704


def test_disk_guard_still_fires_before_any_collection_work(chroma, monkeypatch):
    """The S0.2 guard must remain ahead of the lock and the build."""
    monkeypatch.setattr(vs, "disk_free_bytes", lambda *a, **k: 100 * 1024 ** 2)
    monkeypatch.setattr(vs, "_store_size_bytes", lambda: 0)
    with pytest.raises(RuntimeError, match="reseed refused"):
        vs.reseed()
    assert chroma.ops == [], "nothing should have been created or deleted"


# ── the disk floor must account for build-then-swap holding TWO copies ─────────
def test_disk_floor_scales_with_store_size(chroma, monkeypatch):
    """Build-then-swap needs room for a second copy; a flat floor is not enough.

    Regression guard for the profile change: the old delete-first reseed freed the space
    before writing, so 500 MB free was always sufficient. This one writes the rebuild
    beside the live index, so a 3 GB store needs >3 GB free — and must say so UP FRONT
    rather than running out of room deep into the embed.
    """
    monkeypatch.setattr(vs, "_store_size_bytes", lambda: 3 * 1024 ** 3)      # 3 GB store
    monkeypatch.setattr(vs, "disk_free_bytes", lambda *a, **k: 1024 ** 3)    # 1 GB free
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(8704))

    with pytest.raises(RuntimeError, match="room for both"):
        vs.reseed()
    assert chroma.ops == [], "must refuse before creating the build collection"
    assert chroma.store[LIVE] == 8704


def test_ample_space_for_two_copies_proceeds(chroma, monkeypatch):
    monkeypatch.setattr(vs, "_store_size_bytes", lambda: 1024 ** 3)          # 1 GB store
    monkeypatch.setattr(vs, "disk_free_bytes", lambda *a, **k: 50 * 1024 ** 3)
    monkeypatch.setattr(vs, "_seed_collection", _seed_n(8704))
    vs.reseed()
    assert chroma.store[LIVE] == 8704


def test_store_size_never_raises_on_a_missing_store(monkeypatch):
    """An unreadable/absent store must fall back to the flat floor, not block reseed."""
    monkeypatch.setattr(vs, "CHROMA_PATH", vs.Path("Z:/definitely/not/here"))
    assert vs._store_size_bytes() == 0

"""S0.2 — disk preflight.

The 2026-07-20 incident: a reseed ran with 43 MB free, sqlite raised "database or disk
is full" mid-write, and the store was corrupted. These tests pin the two guards that make
that impossible to repeat silently:

  * reseed() REFUSES to start below a hard free-space floor (before the destructive delete).
  * the boot preflight WARNS (never raises) when the volume is low, and logs OK otherwise.

Both are exercised by monkeypatching shutil.disk_usage, so they never depend on the real
free space of the CI/dev volume.
"""
import logging
from collections import namedtuple

import pytest

from app.ai import vector_store as vs

_Usage = namedtuple("usage", "total used free")


def _fake_usage(free_bytes: int):
    return lambda _path: _Usage(total=free_bytes * 4, used=free_bytes * 3, free=free_bytes)


# ── reseed refuse path ──────────────────────────────────────────────────────────
def test_reseed_refuses_below_free_space_floor(monkeypatch):
    """Below the 500 MB floor, reseed raises BEFORE touching the collection."""
    monkeypatch.setattr(vs.shutil, "disk_usage", _fake_usage(100 * 1024 ** 2))  # 100 MB

    # If reseed got past the guard it would call _get_client(); make that explode so a
    # regression (guard removed) fails loudly instead of hitting the real store.
    def _boom():
        raise AssertionError("reseed proceeded past the disk guard on a near-full volume")
    monkeypatch.setattr(vs, "_get_client", _boom)

    with pytest.raises(RuntimeError, match="reseed refused"):
        vs.reseed()


def test_reseed_allowed_above_floor_reaches_client(monkeypatch):
    """Above the floor the guard is transparent — reseed proceeds to the client step."""
    monkeypatch.setattr(vs.shutil, "disk_usage", _fake_usage(5 * 1024 ** 3))  # 5 GB

    reached = {"client": False}

    def _sentinel():
        reached["client"] = True
        raise RuntimeError("stop-here")  # short-circuit before real Chroma work
    monkeypatch.setattr(vs, "_get_client", _sentinel)

    with pytest.raises(RuntimeError, match="stop-here"):
        vs.reseed()
    assert reached["client"], "reseed should pass the disk guard when space is ample"


# ── disk_free_bytes helper ──────────────────────────────────────────────────────
def test_disk_free_bytes_walks_up_to_existing_ancestor(monkeypatch, tmp_path):
    """Works before the store dir exists (first boot) by stat'ing the nearest parent."""
    seen = {}

    def _record(path):
        seen["path"] = str(path)
        return _Usage(total=10, used=1, free=9)
    monkeypatch.setattr(vs.shutil, "disk_usage", _record)

    missing = tmp_path / "does" / "not" / "exist" / "chroma_db"
    assert vs.disk_free_bytes(missing) == 9
    # It resolved to an existing ancestor (tmp_path), not the missing leaf.
    assert seen["path"] == str(tmp_path)


# ── boot preflight warn / ok paths ──────────────────────────────────────────────
def test_boot_preflight_warns_when_low(monkeypatch, caplog):
    from app.main import _disk_preflight
    monkeypatch.setattr(vs.shutil, "disk_usage", _fake_usage(200 * 1024 ** 2))  # 200 MB
    with caplog.at_level(logging.WARNING):
        _disk_preflight()
    assert any("Disk preflight" in r.message and "free space soon" in r.message
               for r in caplog.records), "low disk must emit a warning"


def test_boot_preflight_ok_when_ample(monkeypatch, caplog):
    from app.main import _disk_preflight
    monkeypatch.setattr(vs.shutil, "disk_usage", _fake_usage(50 * 1024 ** 3))  # 50 GB
    with caplog.at_level(logging.INFO):
        _disk_preflight()
    msgs = " ".join(r.message for r in caplog.records)
    assert "Disk preflight" in msgs and "free space soon" not in msgs

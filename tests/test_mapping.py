"""
Phase A4 — old↔new statute mapping (IPC↔BNS, CrPC↔BNSS, IEA↔BSA).
Data is AI-compiled and must surface its pending-verification caveat.
"""
from app.services import mapping
from tests.conftest import register_and_login, auth


# ── Service ─────────────────────────────────────────────────────────────────────
def test_ipc_to_bns_core_mappings():
    assert mapping.lookup_old("IPC", "420")["new_section"].startswith("318")
    assert mapping.lookup_old("IPC", "302")["new_section"] == "103"
    assert mapping.lookup_old("Indian Penal Code", "Section 376")["new"] == "BNS"


def test_crpc_and_iea_mappings():
    assert mapping.lookup_old("CrPC", "438")["new_section"] == "482"   # anticipatory bail
    assert mapping.lookup_old("CrPC", "154")["new"] == "BNSS"
    assert mapping.lookup_old("IEA", "65B")["new"] == "BSA"


def test_reverse_mapping():
    hit = mapping.lookup_new("BNS", "103")
    assert hit and hit["old"] == "IPC" and hit["old_section"] == "302"


def test_unknown_mapping_returns_none():
    assert mapping.lookup_old("IPC", "99999") is None
    assert mapping.lookup_old("FooAct", "1") is None


def test_mapping_carries_pending_verification_caveat():
    hit = mapping.lookup_old("IPC", "420")
    assert hit["advocate_approved"] is False
    assert "verif" in hit["disclaimer"].lower()


def test_detect_old_refs_in_free_text():
    refs = mapping.detect_old_refs("What is the punishment under IPC 420 and Section 302 IPC now?")
    new_secs = {r["new_section"][:3] for r in refs}
    assert "318" in new_secs and "103" in new_secs


# ── API ─────────────────────────────────────────────────────────────────────────
def test_mapping_endpoint(client):
    t = register_and_login(client, "map@firm.com")
    r = client.get("/api/research/mapping?act=IPC&section=420", headers=auth(t))
    assert r.status_code == 200
    assert r.json()["new"] == "BNS"
    assert r.json()["advocate_approved"] is False


def test_mapping_endpoint_requires_auth(client):
    assert client.get("/api/research/mapping?act=IPC&section=420").status_code == 401


def test_mapping_endpoint_unknown_404(client):
    t = register_and_login(client, "map2@firm.com")
    assert client.get("/api/research/mapping?act=IPC&section=99999", headers=auth(t)).status_code == 404

"""
Legal Library tests — auth gate + that ingested full text is browsable & verbatim.
"""
from tests.conftest import register_and_login, auth


def test_library_requires_auth(client):
    assert client.get("/api/library/acts").status_code == 401


def test_lists_acts_with_sections(client):
    t = register_and_login(client, "lib@firm.com")
    acts = client.get("/api/library/acts", headers=auth(t)).json()
    ids = {a["id"] for a in acts}
    assert "bns_2023" in ids
    bns = next(a for a in acts if a["id"] == "bns_2023")
    assert bns["section_count"] > 300
    assert bns["source_verified"] is True


def test_get_verbatim_section(client):
    t = register_and_login(client, "lib2@firm.com")
    r = client.get("/api/library/acts/bns_2023/sections/318", headers=auth(t))
    assert r.status_code == 200
    body = r.json()
    assert "cheat" in body["text"].lower()        # BNS s.318 is "Cheating"
    assert body["source_verified"] is True
    assert body["source_url"]


def test_no_duplicate_acts_by_title_year(client):
    """A verified act must not ALSO be listed as a heading-only card (the old heading
    index uses different ids, so dedupe must be by normalised title+year)."""
    t = register_and_login(client, "lib3@firm.com")
    acts = client.get("/api/library/acts", headers=auth(t)).json()

    def key(a):
        s = (a["title"] or "").lower().replace("the ", " ")
        return ("".join(ch for ch in s if ch.isalnum()), a["year"])

    seen = {}
    for a in acts:
        k = key(a)
        assert k not in seen, f"duplicate act listed: {a['title']} ({a['year']}) — ids {seen[k]} and {a['id']}"
        seen[k] = a["id"]


def test_search_finds_sections(client):
    t = register_and_login(client, "lib3@firm.com")
    hits = client.get("/api/library/search?q=anticipatory bail", headers=auth(t)).json()
    assert isinstance(hits, list) and len(hits) > 0

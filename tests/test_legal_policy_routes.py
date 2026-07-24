"""LSAI-LEGAL-02 — the legal policy pack is served in-app and complete."""
SLUGS = ["terms", "privacy", "acceptable-use", "grievance", "ai-disclosure",
         "retention", "subprocessors", "law-enforcement"]


def test_legal_index_lists_all(client):
    slugs = {d["slug"] for d in client.get("/api/legal/index").json()}
    for s in SLUGS:
        assert s in slugs


def test_each_policy_doc_served_with_version(client):
    for s in SLUGS:
        r = client.get(f"/api/legal/doc/{s}")
        assert r.status_code == 200, s
        md = r.json()["markdown"]
        assert "Version" in md and len(md) > 200


def test_unknown_policy_returns_404(client):
    assert client.get("/api/legal/doc/not-a-policy").status_code == 404


def test_legal_pages_serve(client):
    assert client.get("/legal").status_code == 200
    assert client.get("/legal/terms").status_code == 200


def test_key_clauses_present(client):
    terms = client.get("/api/legal/doc/terms").json()["markdown"].lower()
    assert "advocate" in terms and "public legal-advice service" in terms
    privacy = client.get("/api/legal/doc/privacy").json()["markdown"].lower()
    assert "never used to train" in privacy
    aup = client.get("/api/legal/doc/acceptable-use").json()["markdown"].lower()
    assert "scraping" in aup and "fake" in aup

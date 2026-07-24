"""Juriscite PWA — installable web app assets are served correctly (Android/iOS install-ready)."""


def test_manifest_served(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert "application/manifest+json" in r.headers.get("content-type", "")
    assert "Juriscite" in r.text and '"display": "standalone"' in r.text


def test_service_worker_served_at_root_scope(client):
    r = client.get("/service-worker.js")
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "")
    assert r.headers.get("Service-Worker-Allowed") == "/"
    # Privacy guard: the SW must never cache API/tenant data.
    assert "/api/" in r.text


def test_offline_page_served(client):
    r = client.get("/offline")
    assert r.status_code == 200 and "offline" in r.text.lower()


def test_pwa_icons_present(client):
    for p in ("/static/icon-192.png", "/static/icon-512.png",
              "/static/icon-maskable-512.png", "/static/apple-touch-icon.png"):
        assert client.get(p).status_code == 200, p


def test_brand_is_juriscite_not_legalserver(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "LegalServer" not in r.text          # fully rebranded
    assert "Juris" in r.text


def test_dashboard_cube_shows_juriscite_logo(client):
    """The hero 3D cube must carry the Juriscite logo mark, not the old § placeholder."""
    assert client.get("/static/logo-mark.svg").status_code == 200          # logo asset served
    assert "logo-mark.svg" in client.get("/static/style.css").text          # cube faces use the logo
    home = client.get("/").text
    i = home.find('class="cube"')
    cube = home[i:i + 250]
    assert "&sect;" not in cube and "§" not in cube                    # § placeholder removed


def test_service_worker_version_is_current(client):
    """SW cache version must be bumped when static assets change, or PWA users get stale CSS/JS."""
    sw = client.get("/service-worker.js").text
    assert "juriscite-v10" in sw
    assert "/static/logo-mark.svg" in sw                                    # logo precached in the shell

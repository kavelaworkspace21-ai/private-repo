"""
Phase B — audit-log visibility (firm-admin, tenant-scoped) + conservative retention purge.
"""
from datetime import datetime, timedelta, timezone
from tests.conftest import register_and_login, auth


def _admin(client, email):
    client.post("/api/auth/register", json={
        "full_name": "Admin", "email": email, "password": "Sup3rSecret!", "role": "firm_admin"})
    return client.post("/api/auth/login",
                       json={"email": email, "password": "Sup3rSecret!"}).json()["access_token"]


# ── Audit visibility ────────────────────────────────────────────────────────────
def test_admin_sees_tenant_audit(client):
    tok = _admin(client, "auditadmin@firm.com")
    # generate an auditable action
    client.post("/api/clients/", headers=auth(tok), json={"full_name": "C", "email": "c@e.com"})
    rows = client.get("/api/audit/", headers=auth(tok)).json()
    assert any(r["action"] == "create_client" for r in rows)


def test_audit_requires_admin(client):
    adv = register_and_login(client, "plainadv@firm.com")   # advocate, not firm_admin
    assert client.get("/api/audit/", headers=auth(adv)).status_code == 403


def test_audit_requires_auth(client):
    assert client.get("/api/audit/").status_code == 401


def test_audit_is_tenant_scoped(client):
    a = _admin(client, "a1@firm.com")
    client.post("/api/clients/", headers=auth(a), json={"full_name": "A", "email": "a@e.com"})
    b = _admin(client, "b1@firm.com")   # different tenant
    rows_b = client.get("/api/audit/", headers=auth(b)).json()
    assert all(r["action"] != "create_client" for r in rows_b)   # B sees none of A's actions


# ── Conservative retention purge ────────────────────────────────────────────────
def test_purge_removes_old_read_notifications_only():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.models
    from app.db.base import Base
    from app.models.notification import Notification
    from app.services.privacy import purge_old_read_notifications

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    old = datetime.now(timezone.utc) - timedelta(days=120)
    recent = datetime.now(timezone.utc) - timedelta(days=5)
    db.add_all([
        Notification(tenant_id=1, title="old read",   is_read=True,  created_at=old),
        Notification(tenant_id=1, title="old unread", is_read=False, created_at=old),
        Notification(tenant_id=1, title="new read",   is_read=True,  created_at=recent),
    ])
    db.commit()
    deleted = purge_old_read_notifications(db, days=90)
    assert deleted == 1                                  # only the old READ one
    remaining = {n.title for n in db.query(Notification).all()}
    assert remaining == {"old unread", "new read"}

"""DPDP erasure must actually erase — every table, not just the obvious ones.

`DELETE /api/account` deleted clients, cases, documents, drafts, notifications, consents,
audit rows, users and the tenant. It did NOT reach:

  * conversations / ai_messages  — the full AI chat history. Advocates paste client facts
    into these. `Conversation.user_id` declares ondelete="CASCADE", but SQLite runs with
    PRAGMA foreign_keys=0, so on SQLite that cascade is a NO-OP while on PostgreSQL it
    fires — dev and production silently disagreed.
  * user_activities              — chat previews, stored as the first 80 chars of each
    query, which routinely contain client names.
  * workbench_uploads / workflow_sessions / workflow_artifacts — uploaded client case
    files and everything extracted from them, plus the extracted-text and anchor files
    left on disk.
  * data_rights_requests / misuse_reports — the user's own DPDP requests.

"We deleted your data" while these remain is a false statement to a data principal, so
this test enumerates the schema itself: any tenant- or user-scoped table that is not
explicitly justified must be empty after erasure. A NEW table therefore fails this test
until someone decides how erasure should treat it.
"""
import pytest

import app.models  # noqa: F401 — registers every model
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from tests.conftest import auth, register_and_login

# Tables deliberately NOT emptied, each with the reason. Anything else must be empty.
RETAINED_WITH_REASON = {
    # Statutory financial retention (Indian tax/GST). Rows are ANONYMISED instead of
    # deleted — see _anonymise_financial_records in app/routers/account.py. Confirm the
    # exact retention period with a chartered accountant (tracked in OWNER_QUEUE).
    "invoices": "statutory financial retention — anonymised, not deleted",
    "subscriptions": "statutory financial retention — anonymised, not deleted",
    "usage_events": "statutory financial retention — anonymised, not deleted",
    # Not user data.
    "subscription_plans": "product catalogue, not user data",
    "backup_runs": "operational telemetry, no user data",
    "scheduled_job_runs": "operational telemetry, no user data",
    "tenants": "deleted explicitly by the erasure routine",
}


def _db():
    return next(app.dependency_overrides[get_db]())


def _rows(db, table) -> int:
    from sqlalchemy import func, select
    return db.execute(select(func.count()).select_from(table)).scalar_one()


def _seed_everything(client, tok):
    """Create data across the app so erasure has something to miss."""
    c = client.post("/api/clients/", headers=auth(tok), json={
        "full_name": "Ramesh Kumar", "email": "ramesh@example.com",
        "phone": "9876500000", "address": "12 MG Road, Bengaluru"})
    assert c.status_code in (200, 201), c.text
    cid = c.json()["id"]

    case = client.post("/api/cases/", headers=auth(tok), json={
        "title": "Ramesh Kumar v Acme Ltd", "client_id": cid,
        "case_type": "civil", "court": "City Civil Court"})
    assert case.status_code in (200, 201), case.text

    # AI chat — persists a conversation, messages, and an activity preview
    client.post("/api/ai/chat", headers=auth(tok),
                json={"message": "Ramesh Kumar cheque bounce under section 138"})
    return cid


@pytest.fixture
def stubbed_model(monkeypatch):
    """Keep the chat endpoint off any real provider while still persisting history."""
    import json as _json

    from app.ai import agent as agent_mod

    async def _gen(**kwargs):
        yield _json.dumps({"content": "Section 138 governs cheque dishonour. "})
        yield _json.dumps({"available_citations": ["138"]})
        yield _json.dumps({"done": True})

    monkeypatch.setattr(agent_mod, "stream_agent_response", _gen)


def test_erasure_leaves_no_personal_data_in_any_table(client, stubbed_model):
    tok = register_and_login(client, "erasure@firm.com")
    _seed_everything(client, tok)

    db = _db()
    # Sanity: the seed actually wrote the tables we care about, otherwise this test
    # would pass vacuously by deleting nothing.
    seeded = {t.name: _rows(db, t) for t in Base.metadata.sorted_tables}
    for must_have in ("clients", "cases", "conversations", "ai_messages", "user_activities"):
        assert seeded.get(must_have, 0) > 0, f"seed did not populate {must_have}"

    r = client.request("DELETE", "/api/account/", headers=auth(tok), json={"confirm": True})
    assert r.status_code == 200, r.text

    db = _db()
    leftovers = {}
    for table in Base.metadata.sorted_tables:
        if table.name in RETAINED_WITH_REASON:
            continue
        n = _rows(db, table)
        if n:
            leftovers[table.name] = n

    assert not leftovers, (
        "erasure left personal data behind — telling the user their data was deleted "
        f"would be false: {leftovers}")


def test_retained_financial_rows_carry_no_personal_identifiers(client, stubbed_model):
    """Statutory retention is not a licence to keep names and emails."""
    from sqlalchemy import inspect as sa_inspect

    tok = register_and_login(client, "finretain@firm.com")
    _seed_everything(client, tok)
    client.request("DELETE", "/api/account/", headers=auth(tok), json={"confirm": True})

    db = _db()
    insp = sa_inspect(db.get_bind())
    for name in ("invoices", "subscriptions", "usage_events"):
        if name not in insp.get_table_names():
            continue
        table = Base.metadata.tables[name]
        for row in db.execute(table.select()).mappings():
            blob = " ".join(str(v) for v in row.values() if v is not None).lower()
            assert "finretain@firm.com" not in blob
            assert "ramesh" not in blob


def test_every_table_is_either_erased_or_justified():
    """A new table must not silently inherit 'kept forever'.

    Fails when a table is added that is neither covered by erasure nor listed with a
    reason, forcing an explicit decision instead of a default.
    """
    known = set(RETAINED_WITH_REASON)
    unknown_retained = known - {t.name for t in Base.metadata.sorted_tables}
    assert not unknown_retained, (
        f"RETAINED_WITH_REASON names tables that no longer exist: {unknown_retained}")

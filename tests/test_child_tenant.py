"""
Child rows must inherit tenant_id from their parent Case on insert (§5).
Verifies the before_insert event listener in app/models/__init__.py.
"""
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  registers models + event listeners
from app.db.base import Base
from app.models.case import Case
from app.models.client import Client
from app.models.hearing import Hearing
from app.models.diary_task import DiaryTask


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_child_inherits_tenant_from_case():
    db = _session()
    client = Client(tenant_id=7, full_name="A", email="a@e.com")
    db.add(client); db.flush()
    case = Case(tenant_id=7, title="T", client_id=client.id, status="open")
    db.add(case); db.flush()

    h = Hearing(case_id=case.id, hearing_date=date.today(), court_name="HC")
    t = DiaryTask(case_id=case.id, title="file it")
    db.add_all([h, t]); db.commit(); db.refresh(h); db.refresh(t)

    assert h.tenant_id == 7
    assert t.tenant_id == 7


def test_explicit_tenant_not_overwritten():
    db = _session()
    client = Client(tenant_id=1, full_name="B", email="b@e.com")
    db.add(client); db.flush()
    case = Case(tenant_id=1, title="T2", client_id=client.id, status="open")
    db.add(case); db.flush()

    h = Hearing(case_id=case.id, tenant_id=1, hearing_date=date.today(), court_name="HC")
    db.add(h); db.commit(); db.refresh(h)
    assert h.tenant_id == 1

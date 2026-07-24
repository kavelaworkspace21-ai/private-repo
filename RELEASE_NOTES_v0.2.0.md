# Juriscite — Release v0.2.0

**Source-grounded legal practice OS for Indian advocates.** Owner: Kavela Narula. Built under the
Master Agent "Legal Server.AI". 230 automated tests passing.

## What this package is (honest)
This is the **deployable source release** of Juriscite (the server + web app + installable PWA).
- **End users install the PWA** — once the app is hosted on a domain with a trusted HTTPS cert, any
  advocate installs it from the browser: Android → "Install app"; iOS → Share → "Add to Home Screen".
- **Native App Store / Play Store apps** are not in this zip — they need a Mac (iOS) + your paid Apple/
  Google developer accounts + signing. See `docs/deployment/MOBILE_BUILD_GUIDE.md` and `mobile/`.

## Run it (developer / self-host)
```bash
python -m venv venv && venv/Scripts/pip install -r requirements.txt   # (Windows venv shown)
copy .env.example .env            # fill JWT_SECRET, optional free AI_* keys; never commit .env
venv/Scripts/python -m alembic upgrade head
venv/Scripts/python -m uvicorn app.main:app            # http://127.0.0.1:8000
venv/Scripts/python -m pytest tests/ -q                # 230 tests
```

## Highlights
- Auth + 2FA + RBAC + multi-tenant; firm workspaces; clients/matters; documents + versioning;
  court diary + reminders + .ics; fees; **cited** research; **advocate-reviewed** drafting (10 templates,
  DOCX/PDF); notifications; account + DPDP data-rights + misuse reporting; audit; legal/policy hub.
- **Zero-cost AI** (free local embeddings + free Gemini), provider-agnostic.
- **Installable PWA** (offline shell; never caches tenant data).
- **The Soul, hard-wired:** fail-closed startup guard (`app/soul.py`) — the app refuses to run if the
  safety doctrine is broken — and **ejection** of any user who tries to use it against the law
  (`app/services/soul_enforcement.py`). Full safety doctrine + no-hallucination + no prohibited AI.
- Full legal-compliance pack (LEGAL-00→22).

## Not included / not done (truthful)
Real `.env`/secrets, the local DB, the Python venv, and any vector-store data are **excluded** by design.
Public launch is **locked** until human gates G1/G6/G7/G8 are signed (`docs/legal/HUMAN_SIGNOFF_PACKET.md`).
No real client data until G6 + G7 clear.

See `docs/PROJECT_KNOWLEDGE.md` for the complete map.

# Juriscite

An advocate-first, AI-native legal operating system for India. FastAPI + SQLAlchemy, a
50-act source-verified statutory corpus with deterministic-first retrieval, and a
vanilla-JS PWA front end (no build step).

Canonical engineering log: [`docs/STATUS.md`](docs/STATUS.md).

---

## ⚠ Security setup — read before deploying

### 1. Secrets live in the environment, never in source

Copy the template and fill it in:

```bash
cp .env.example .env
```

`.env` is gitignored and has **never** been committed (verified against the full history).
Every one of the 41 configuration variables the app reads is documented in `.env.example`
with placeholder values only.

Generate the two secrets the app refuses to start without:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The first is `JWT_SECRET`, the second `FIELD_ENCRYPTION_KEY`. In production these belong in
a secret manager (AWS Secrets Manager / KMS), **not** in a `.env` file on the box.

### 2. `ENVIRONMENT` fails closed

`app/security_gate.py` runs at boot, beside the existing soul and prohibited-feature gates.
An **unset** `ENVIRONMENT` is treated as `production`, so forgetting it fails closed. In
production the app **refuses to start** when:

- `JWT_SECRET` is missing, is the published placeholder, or is under 32 characters
- `FIELD_ENCRYPTION_KEY` is missing

Set `ENVIRONMENT=development` locally to downgrade these to a warning. Never set that in
production. Note that `staging`, `prod-eu`, or a typo all count as production — only the
explicit names `development`, `dev`, `local`, `test`, `testing`, `ci` relax the gate.

### 3. Rotate any secret that was ever exposed

**If a credential was ever hardcoded, pasted into a terminal, or printed into a log or
transcript, rotate it. Removing it from the working tree does not remove it from git
history, and history is trivially searchable.**

For this repository specifically, as of 2026-07-25:

| Credential | History status | Action |
|---|---|---|
| `INDIAN_KANOON_API_KEY` | **Never committed**, but was displayed in plaintext in a 2026-07-24 working session | **Rotate at Indian Kanoon** — this is a live, per-call **billed** key |
| `JWT_SECRET`, `FIELD_ENCRYPTION_KEY`, `AI_API_KEY`, `ECOURTS_API_KEY` | Never committed, never printed | No action |
| Aurora connection string | Present (commented out) in the local `.env` only; never committed | Move to a secret manager before production |

Verify the claim yourself — this searches every blob in history for the live values in your
`.env` and prints only variable names and booleans:

```bash
git rev-list --all --objects | cut -d' ' -f1 | git cat-file --batch | grep -c "$(grep '^JWT_SECRET=' .env | cut -d= -f2-)"
```

A `0` means the value has never been committed.

### 4. What is safe to expose to the browser

This app has **no** client-side SDK keys. There is no Supabase, Stripe, Firebase, or
`NEXT_PUBLIC_`/`REACT_APP_` build-time inlining — the front end is server-rendered HTML plus
static JS, so no environment variable is ever compiled into a bundle.

The only credential-shaped values that legitimately reach the browser are:

- **`RAZORPAY_KEY_ID`** — the publishable-equivalent identifier, returned by the checkout
  endpoint. `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` are server-side only; the
  webhook secret is used solely for HMAC-SHA256 signature verification.
- **The signed-in user's own TOTP secret**, shown once during 2FA setup so it can be entered
  into an authenticator app. It is stored Fernet-encrypted at rest.

---

## Running it

```bash
python -m venv venv && venv/Scripts/python -m pip install -r requirements.txt
```

```bash
python -m alembic upgrade head
```

```bash
python -c "from app.ai import vector_store as vs; vs.reseed()"
```

```bash
python -m app.ops.release preflight --no-require-secrets
```

Then:

```bash
python -m uvicorn app.main:app --port 8000
```

## Before any deploy

```bash
python -m app.ops.release preflight
```

Exits non-zero on a stale corpus, a mismatched vector index, migration drift, missing
secrets, low disk, an uncommitted working tree, or a tree that is not the pinned release
commit. See [`docs/RELEASE_MANIFEST.md`](docs/RELEASE_MANIFEST.md).

## Status

Not production-ready, and should not be represented as such. Production requires
infrastructure that does not yet exist and four human sign-offs that cannot be
self-certified (G1 corpus authenticity, G6 privacy counsel, G7 penetration test, G8
senior-advocate review). See [`docs/GO_LIVE_CHECKLIST.md`](docs/GO_LIVE_CHECKLIST.md) and
[`docs/OWNER_QUEUE.md`](docs/OWNER_QUEUE.md).

Known corpus defect: the statute parser silently dropped some provisions present in the
source PDFs. Fixed in code; **the corpus has not yet been regenerated**. See
[`docs/CORPUS_LIMITATIONS.md`](docs/CORPUS_LIMITATIONS.md).

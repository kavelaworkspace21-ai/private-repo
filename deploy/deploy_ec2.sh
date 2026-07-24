#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Juriscite — on-EC2 deploy (RUN AS ubuntu, ON the EC2 box, which is in-VPC to Aurora).
# Usage:   ./deploy_ec2.sh [path-to-zip]      (default: ~/Juriscite-v0.2.0.zip)
# Safe to re-run. Preserves venv, .env, the ChromaDB vector store, and any local DB.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ZIP="${1:-$HOME/Juriscite-v0.2.0.zip}"
APP_DIR="${APP_DIR:-$HOME/legalserver-ai}"      # adjust if your app lives elsewhere
SERVICE="${SERVICE:-legalserver}"               # systemd unit name
STAMP="$(date +%F_%H%M%S)"

echo "==> [1/7] sanity"
[ -f "$ZIP" ] || { echo "ZIP not found: $ZIP"; exit 1; }
[ -d "$APP_DIR/venv" ] || { echo "venv missing in $APP_DIR — is APP_DIR correct?"; exit 1; }
command -v rsync >/dev/null || { echo "installing rsync"; sudo apt-get update -y && sudo apt-get install -y rsync; }

echo "==> [2/7] backup current CODE (excludes venv/chroma/db; for rollback)"
tar czf "$HOME/juriscite_codebak_$STAMP.tgz" \
    --exclude='venv' --exclude='*.db' --exclude='chroma*' --exclude='.chroma' \
    -C "$APP_DIR" . || true
echo "    backup: $HOME/juriscite_codebak_$STAMP.tgz"

echo "==> [3/7] unzip release"
TMP="$(mktemp -d)"
unzip -oq "$ZIP" -d "$TMP"
SRC="$TMP/Juriscite"
[ -d "$SRC" ] || SRC="$TMP"          # tolerate a flat zip

echo "==> [4/7] sync code into $APP_DIR  (NO --delete: keeps venv/.env/chroma/db)"
rsync -a --exclude='venv' --exclude='.env' --exclude='*.db' \
      --exclude='chroma*' --exclude='.chroma' \
      "$SRC"/ "$APP_DIR"/
rm -rf "$TMP"

cd "$APP_DIR"
# shellcheck disable=SC1091
source venv/bin/activate

echo "==> [5/7] dependencies (no-op if unchanged)"
pip install -q -r requirements.txt

EXPECTED_HEAD="$(python -c "import json;print(json.load(open('RELEASE.json'))['migration_head'])")"

echo "==> [6/8] migrate Aurora to head"
echo "    current revision:"; alembic current || true
alembic upgrade head
echo "    revision after:";  alembic current      # expect head = $EXPECTED_HEAD (from RELEASE.json)

echo "==> [7/8] release preflight — FAIL-CLOSED (stale corpus / migration drift / missing secrets)"
# Refuses to proceed on a stale corpus, an unbuilt/mismatched vector index, a drifted migration
# head, or missing JWT_SECRET/FIELD_ENCRYPTION_KEY. If it flags ONLY the index (count mismatch),
# the corpus is derived from versioned fulltext — rebuild it deterministically and re-verify:
#     python -c "from app.ai.vector_store import reseed; reseed()"
#     python -m app.ops.release preflight
python -m app.ops.release preflight   # set -e aborts the deploy if this exits non-zero

echo "==> [8/8] restart + smoke check"
sudo systemctl restart "$SERVICE"
sleep 4
sudo systemctl --no-pager --lines=0 status "$SERVICE" || true
echo "    /healthz (liveness):"; curl -ks https://localhost/healthz || curl -s http://127.0.0.1:8000/healthz || true
echo; echo "    /readyz (vector index):"; curl -ks https://localhost/readyz || curl -s http://127.0.0.1:8000/readyz || true
echo
echo "==> DONE. Verify above: service active · revision $EXPECTED_HEAD · /healthz \"soul\":\"intact\" · /readyz \"ready\"."
echo "    If the service did NOT start, the soul guard or a migration likely failed — check:"
echo "    journalctl -u $SERVICE -n 50 --no-pager"
echo "    Rollback: extract $HOME/juriscite_codebak_$STAMP.tgz into $APP_DIR, then 'alembic downgrade -1' per migration (or restore the RDS snapshot), then restart."

# Juriscite — Deploy Runbook v0.2.0 (EC2 + Aurora)

Ship the Juriscite rebrand + PWA + hard-wired soul + ejection to the live EC2 box and migrate Aurora.
**~5 minutes.** Additive migrations only; safe + reversible.

## Before you start — fill in YOUR values
- `KEY` = path to your EC2 SSH key, e.g. `C:\Users\prith\keys\juriscite.pem`
- `HOST` = your EC2 user@host, e.g. `ubuntu@ec2-XX-XX-XX-XX.compute.amazonaws.com`
  *(I don't have your live host/key — use the ones you used for the last deploy.)*
- Artifacts already on your Desktop: `Juriscite-v0.2.0.zip` and (in repo) `deploy\deploy_ec2.sh`.

**Recommended safety step (AWS console):** take a **manual RDS/Aurora snapshot** before migrating
(automated PITR also covers you). 1 click; instant rollback insurance.

## Step 1 — Upload (run in PowerShell on your Windows machine)
```powershell
$KEY  = "C:\path\to\your-key.pem"
$HOST = "ubuntu@YOUR_EC2_HOST"
scp -i $KEY "C:\Users\prith\OneDrive\Desktop\Juriscite-v0.2.0.zip" "${HOST}:/home/ubuntu/"
scp -i $KEY "C:\Users\prith\OneDrive\Desktop\LEGAL SERVER CLAUDE\deploy\deploy_ec2.sh" "${HOST}:/home/ubuntu/"
```

## Step 2 — Deploy (SSH in and run the script)
```powershell
ssh -i $KEY $HOST
```
Then **on the EC2 box**:
```bash
sed -i 's/\r$//' ~/deploy_ec2.sh   # strip Windows CRLF so bash can run it
chmod +x ~/deploy_ec2.sh
~/deploy_ec2.sh ~/Juriscite-v0.2.0.zip
```
The script: backs up current code → syncs the new code (preserving `venv`, `.env`, the ChromaDB vector
store, and the DB) → `pip install -r requirements.txt` (no new deps this release) →
**`alembic upgrade head`** on Aurora → restarts the `legalserver` service → smoke-checks `/health`.

> If your app dir or service name differ, run with overrides:
> `APP_DIR=/home/ubuntu/yourdir SERVICE=yoursvc ~/deploy_ec2.sh ~/Juriscite-v0.2.0.zip`

## Step 3 — Verify (on the EC2 box)
```bash
cd ~/legalserver-ai && source venv/bin/activate
alembic current                      # expect: d7e3b1a9c4f2 (head)
curl -ks https://localhost/health    # expect: {"status":"ok",...,"soul":"intact"}
curl -ks https://localhost/ | grep -io 'juris' | head -1     # expect: juris  (rebrand live)
curl -ks https://localhost/manifest.webmanifest | head -c 80 # expect: Juriscite manifest JSON
systemctl --no-pager status legalserver | head -5            # expect: active (running)
```
**If the service did NOT start:** the soul guard intentionally **refuses to boot a broken doctrine**, and
a failed migration also stops it. Check `journalctl -u legalserver -n 50 --no-pager` and fix before retrying.

## Migrations applied this release (head `d7e3b1a9c4f2`)
`f2a1c9d4e7b3` consent receipt · `a3b7e1f0c2d5` data-rights · `b4c8f2a1d6e9` tenant verification ·
`c5d9a3e2f7b1` misuse reports · `d7e3b1a9c4f2` user soul-ejection. (`alembic upgrade head` applies
whichever Aurora is missing; all are additive — new columns/tables.)

## Rollback
- **Code:** `tar xzf ~/juriscite_codebak_<stamp>.tgz -C ~/legalserver-ai` then restart.
- **DB:** `alembic downgrade -1` (repeat per migration) **or** restore the RDS snapshot from Step 0.
- Restart: `sudo systemctl restart legalserver`.

## After deploy — still required for PUBLIC user install (owner/infra, unchanged)
The app will be live + updated, but the **PWA installs for end users only over trusted HTTPS**:
1. **Open EC2 security-group inbound 443 + 80.**
2. **Point a domain at the box + run certbot** (replaces the self-signed cert). The service worker won't
   register under a self-signed cert, so "Install Juriscite" / "Add to Home Screen" needs this.
3. Human gates **G6 privacy + G7 security** before any real client data (pre-publish lock stays engaged).

_Honest note: this runbook is verified against the recorded EC2 layout (`/home/ubuntu/legalserver-ai`,
service `legalserver`, nginx+TLS). If your box differs, adjust `APP_DIR`/`SERVICE`. I prepared and
self-checked the scripts locally; I did not run them on your box (no SSH access from here)._

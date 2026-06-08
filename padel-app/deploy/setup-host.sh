#!/usr/bin/env bash
#
# Padel Booker — Stage 1 host setup (run once on the always-on Mac).
#   cd ~/padel-booker && ./padel-app/deploy/setup-host.sh
#
# Installs web deps, builds the app, creates the Python engine venv + Chromium,
# writes your secrets, and seeds the database. Idempotent — safe to re-run.

set -euo pipefail

# Repo root = two levels up from this script (…/padel-app/deploy/ -> repo root)
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB="$REPO/padel-app/web"
ENGINE="$REPO/padel-booking"
WORKER="$REPO/padel-app/worker/worker.py"

echo "Padel Booker · Stage 1 setup"
echo "Repo: $REPO"
echo

command -v node    >/dev/null || { echo "✗ node not found  → brew install node";   exit 1; }
command -v python3 >/dev/null || { echo "✗ python3 not found → brew install python"; exit 1; }
echo "node $(node --version) · $(python3 --version)"
echo

echo "==> [1/5] Web dependencies (npm install)…"
( cd "$WEB" && npm install )

echo "==> [2/5] Secrets…"
if [ ! -f "$ENGINE/.env" ]; then
  read -rp  "  RCKB email: " RCKB_EMAIL
  read -rsp "  RCKB password: " RCKB_PASSWORD; echo
  printf 'RCKB_EMAIL=%s\nRCKB_PASSWORD=%s\n' "$RCKB_EMAIL" "$RCKB_PASSWORD" > "$ENGINE/.env"
  chmod 600 "$ENGINE/.env"
  echo "  ✓ wrote $ENGINE/.env"
else
  echo "  • $ENGINE/.env already exists — keeping it"
fi
if [ ! -f "$WEB/.env.local" ]; then
  read -rp "  Website (gate) password: " APP_PASSWORD
  printf 'APP_PASSWORD=%s\nAUTH_SECRET=%s\n' "$APP_PASSWORD" "$(openssl rand -hex 32)" > "$WEB/.env.local"
  chmod 600 "$WEB/.env.local"
  echo "  ✓ wrote $WEB/.env.local (random AUTH_SECRET generated)"
else
  echo "  • $WEB/.env.local already exists — keeping it"
fi

echo "==> [3/5] Building the web app (npm run build)…"
( cd "$WEB" && npm run build )

echo "==> [4/5] Python engine: venv + deps + Chromium (a few minutes the first time)…"
[ -d "$ENGINE/.venv" ] || ( cd "$ENGINE" && python3 -m venv .venv )
"$ENGINE/.venv/bin/pip" install --upgrade pip >/dev/null
"$ENGINE/.venv/bin/pip" install -r "$ENGINE/requirements.txt"
"$ENGINE/.venv/bin/python" -m playwright install chromium

echo "==> [5/5] Database (seeds your account from the engine .env)…"
( cd "$WEB" && npm run db:init )

cat <<DONE

✅ Stage 1 complete.

Verify it runs (in two terminals):
  1) Web:    cd "$WEB" && npm start        # then open http://localhost:3030
  2) Worker: "$ENGINE/.venv/bin/python" "$WORKER" --list

When that looks good, tell me and I'll add Stage 2 (always-on: launchd auto-start,
keep-awake, the 06:58→07:02 schedule), then Stage 3 (public URL + hardening).
DONE

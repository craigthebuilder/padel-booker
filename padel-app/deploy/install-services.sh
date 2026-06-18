#!/usr/bin/env bash
#
# Stage 2 — install always-on launchd services on a Mac.
# Run after the deps exist (this machine already has them):
#   ./padel-app/deploy/install-services.sh
#
# Installs two LaunchAgents:
#   com.padel.web    — `next start`, kept alive (the dashboard)
#   com.padel.worker — runs daily at 06:50 → fires the 07:02 strike
# Idempotent: reloads if already installed.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB="$REPO/padel-app/web"
ENGINE="$REPO/padel-app/padel-booking"
[ -d "$ENGINE" ] || ENGINE="$REPO/padel-booking"
WORKER_PY="$REPO/padel-app/worker/worker.py"
NODE="$(command -v node)"
LA="$HOME/Library/LaunchAgents"
PORT="${PADEL_PORT:-3030}"
mkdir -p "$LA" "$REPO/padel-app/deploy/logs"

echo "Repo: $REPO  ·  port: $PORT  ·  node: $NODE"

echo "==> Building the web app (production)…"
( cd "$WEB" && npm run build )

WEB_PLIST="$LA/com.padel.web.plist"
cat > "$WEB_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.padel.web</string>
  <key>ProgramArguments</key><array>
    <string>$NODE</string>
    <string>$WEB/node_modules/next/dist/bin/next</string>
    <string>start</string><string>-p</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$WEB</string>
  <key>EnvironmentVariables</key><dict>
    <key>NODE_ENV</key><string>production</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$REPO/padel-app/deploy/logs/web.log</string>
  <key>StandardErrorPath</key><string>$REPO/padel-app/deploy/logs/web.log</string>
</dict></plist>
PLIST

WORKER_PLIST="$LA/com.padel.worker.plist"
cat > "$WORKER_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.padel.worker</string>
  <key>ProgramArguments</key><array>
    <string>$ENGINE/.venv/bin/python</string>
    <string>$WORKER_PY</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO/padel-app/worker</string>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>6</integer><key>Minute</key><integer>50</integer>
  </dict>
  <key>StandardOutPath</key><string>$REPO/padel-app/deploy/logs/worker.log</string>
  <key>StandardErrorPath</key><string>$REPO/padel-app/deploy/logs/worker.log</string>
</dict></plist>
PLIST

echo "==> Loading agents…"
launchctl unload "$WEB_PLIST" 2>/dev/null || true
launchctl unload "$WORKER_PLIST" 2>/dev/null || true
launchctl load "$WEB_PLIST"
launchctl load "$WORKER_PLIST"

cat <<DONE

✅ Services installed.
   Web:    http://localhost:$PORT   (com.padel.web — auto-restarts)
   Worker: daily 06:50              (com.padel.worker — fires the 07:02 strike)

To make the Mac awake for the 06:50 job (run once, asks your password):
   sudo pmset repeat wakeorpoweron MTWRFSU 06:45:00
   # laptop tip: keep it plugged in; lid-closed unattended also needs:
   #   sudo pmset -c disablesleep 1

Logs: $REPO/padel-app/deploy/logs/{web,worker}.log
Manage:  launchctl list | grep com.padel    ·    launchctl unload <plist> to stop
DONE

# Deploying Padel Booker to an always-on Mac

Goal: the bot runs 24/7 (books on its own, no laptop needed) and is reachable from
anywhere with the password. This is done in **three stages** so each is testable.

The app has two tiers that live side-by-side in this repo:
- `padel-app/web` — Next.js dashboard (+ the SQLite DB it owns)
- `padel-booking` — the Python strike engine; `padel-app/worker` drives it

> **Why a Mac (not a cloud VPS):** the booking needs a *real, headed* browser on a
> *residential* IP to get past RCKB's bot wall. Datacenter IPs get flagged; your home
> Mac is already proven. So we host on a Mac at home and expose it via Cloudflare Tunnel.

---

## Prerequisites (on the Mac Pro)

```bash
# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# Toolchain
brew install node python git gh
# Authenticate to GitHub (needed to clone the private repo)
gh auth login
```

## Stage 1 — build & run

```bash
gh repo clone craigthebuilder/padel-booker ~/padel-booker
cd ~/padel-booker
./padel-app/deploy/setup-host.sh        # installs, builds, makes the venv, writes secrets, seeds the DB
```

The script prompts for your **RCKB email/password** (→ `padel-booking/.env`) and a
**website password** (→ `padel-app/web/.env.local`). Neither is in git; you set them
fresh on this machine.

Verify:
```bash
cd ~/padel-booker/padel-app/web && npm start     # open http://localhost:3030, log in
~/padel-booker/padel-booking/.venv/bin/python ~/padel-booker/padel-app/worker/worker.py --list
```

## Stage 2 — always-on (coming next)
launchd LaunchAgents: web server auto-starts + restarts; worker runs daily at 06:50
(wakes, auths, fires the 07:02 strike). Plus `pmset` (never sleep) and auto-login (so the
headed booking browser has a desktop session). Built after Stage 1 is verified.

## Stage 3 — public URL + hardening (coming next)
Cloudflare Tunnel → a free public HTTPS URL (no open ports). Plus: encrypt the stored
RCKB passwords at rest, a strong gate password, and login rate-limiting.

---

## Updating later
```bash
cd ~/padel-booker && git pull
cd padel-app/web && npm install && npm run build   # if web changed
# restart the web service (Stage 2 adds: launchctl kickstart -k gui/$UID/com.padel.web)
```

## Notes / known limitations
- The worker processes the **soonest** pending request each morning; clear stale/missed
  requests so they don't block a fresh one (a future refinement will auto-expire them).
- macOS auto-login + "never sleep" are required for the headed browser to run unattended.

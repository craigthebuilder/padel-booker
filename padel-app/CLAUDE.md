# Padel Court Booker — agent guide

Two-tier app that books a court at RCKB the instant slots release (07:02 ET).
- web/               Next.js 16 + React 19 dashboard (queue, calendar, attempts, accounts)
- worker/            Python scheduler; fires queued bookings concurrently at 07:02
- ../padel-booking/  the original strike engine — worker IMPORTS book_court_api.py, doesn't reimplement it
- data/booking.db    SQLite (WAL). The contract both tiers meet at.

## Safety boundaries — READ FIRST
This app logs into a real account and CHARGES A CARD when it books.
- NEVER run a real RCKB login or booking POST without my explicit OK in this session.
- `worker.py --now` WITHOUT `--dry-run` = real auth + real POST = books + charges. Destructive.
- Default to --dry-run for everything. If a task seems to need a live call, STOP and ask.
- Never print/log/commit: .env, .env.local, data/booking.db, data/secret.key,
  ../padel-booking/network.jsonl (all gitignored — keep it that way).

## Verify before declaring done (run these, don't assume)
- Typecheck (catches what Turbopack hides):  cd web && npx tsc --noEmit
- Build:                                      cd web && npm run build
- Worker pipeline, OFFLINE + safe:            ../padel-booking/.venv/bin/python worker/worker.py --now --dry-run
- See what's queued (safe):                   ../padel-booking/.venv/bin/python worker/worker.py --list
- Re-seed DB from ../padel-booking/.env:      cd web && npm run db:init

## Known gotchas (these have bitten us)
- node:sqlite returns NULL-PROTOTYPE rows. Any row crossing into a Client Component
  must be normalized first (see lib/db.ts `.map(r => ({...(r as object)}))`). Skip it and
  React throws "Only plain objects can be passed to Client Components." Invisible with
  empty tables — only appears once a table has rows.
- Next 16 != training data. Read node_modules/next/dist/docs/ before writing route handlers,
  Server Actions, caching, or proxy (renamed from middleware).
- @types/node must match the Node 26 runtime, or tsc invents node:sqlite errors.
- WAL mode: web + worker share booking.db live. Don't open it exclusive.

## Autonomy — do vs. ask
- JUST DO IT: read files; git status/diff/log; typecheck; build; --dry-run; --list;
  edit web/worker code; pick a reasonable default for naming/layout and note it.
- ASK FIRST: any real RCKB call; git history rewrite / force-push; schema changes that
  touch existing rows; deleting data; anything that spends money.

## How we work
- Checkpoint with git at every green state; I review `git diff` before you commit.
- When you get stuck and I unstick you, append it to STUCK-LOG.md.

# Stuck Log — what unstuck the agent each time it spun

One entry per real stuck-moment: symptom -> cause -> fix -> lesson.
The lessons are the point — they're debugging intuition, compounding.

## 2026-06-05 — null-prototype rows crashed the client component
**Symptom:** Dashboard returned HTTP 500, but only after `attempts` had its first row;
worked fine while the table was empty.
**Cause:** node:sqlite returns null-prototype objects. Server Components tolerate them,
but passing one into a Client Component (AttemptsDropdown) made React throw
"Only plain objects can be passed to Client Components."
**Fix:** normalize at the data layer — `.map(r => ({...(r as object)}))` in lib/db.ts,
so every row is a plain object before it can reach a client component.
**Lesson:** bugs invisible with empty data only surface on the real end-to-end run.
Test with realistic rows, not just empty tables.

## 2026-06-05 — Turbopack HMR poisoned node:sqlite after rapid edits
**Symptom:** HTTP 500 with "Failed to load external module node:sqlite: require is not
defined" — right after 5 fast edits in a row. node:sqlite had loaded fine dozens of times.
**Cause:** Turbopack hot-reload got node:sqlite into a bad module state. A tooling
artifact, NOT a code bug.
**Fix:** restart the dev server (clean process). No code change.
**Lesson:** tell a real bug apart from a tooling artifact before "fixing" code. If an
error appears after rapid edits to something that worked, suspect HMR state first —
read the exact error, don't guess, and try a clean restart.

## 2026-06-08 — headless Chromium blocked by bot detection
**Symptom:** discover.py returned "Could not locate Login" — the site served a bot
challenge instead of the real page.
**Cause:** RCKB (AWS WAF) detects headless Chrome and hides the real page. The whole
engine runs a *visible* browser + Chrome TLS impersonation for exactly this reason.
**Fix:** run the browser headed, not headless (matches what book_court_api.py does).
**Lesson:** when automating a site that fights bots, the environment (headed vs headless,
IP reputation, TLS fingerprint) matters as much as the code. Match the proven setup.

## 2026-06-11 — first live booking failed: the worker ran headless
**Symptom:** First real scheduled run failed at 06:58 (the auth phase, BEFORE the 07:02
strike). Dashboard: "HTTP — · exception: Could not locate Login (home) within 10000ms".
No booking POST was ever attempted.
**Cause:** worker.py hardcoded `headless=True` in its authenticate() call, so RCKB's WAF
bot-blocked it and served a challenge instead of the login page. The SAME bug as the
2026-06-08 discover.py entry above — the lesson was learned there but never applied to the
worker. It stayed hidden because every prior worker test used --dry-run, which skips auth
entirely. The machine was fine (awake, plugged in, logged into the console) — pure code bug.
**Fix:** worker.py `headless=True` -> `headless=False`. Headed auth needs an active GUI
login session, so keep the Mac logged in.
**Lesson:** a fix in one place (discover.py) must be applied everywhere the same operation
runs (the worker). And "offline-verified" is NOT verified — --dry-run never exercised the
auth path, so the bug could not surface until the first real run. Test the real path before
trusting it; a green dry-run proves the plumbing, not the live behavior.

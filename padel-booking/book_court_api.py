#!/usr/bin/env python3
"""
RCKB Racquet Garden — direct-API court booker (Tier 1: curl_cffi strike).

Architecture (3 phases):
    1. Pre-warm wait    →  asyncio.sleep until T-prewarm_seconds
    2. Auth via Playwright  →  login, navigate to /book, extract cookies + CSRF
    3. Strike via curl_cffi (Chrome TLS impersonation) → fire booking POST(s)

Why curl_cffi instead of Playwright's page.evaluate(fetch)?
    - curl_cffi sends a Chrome-shaped TLS fingerprint (JA3) so Cloudflare
      treats it like a real browser, the same way it treats Chromium.
    - But it's a native HTTP client, no CDP roundtrip overhead.
    - Net: ~80-150 ms per attempt vs ~256 ms with browser-fetch — a clean
      ~150 ms shaved off every shot at the slot.

Why not pure httpx? Because it gets a Cloudflare 403 "Just a moment..."
challenge — generic Python TLS fingerprint is detectable. Tried that,
verified it fails; that's exactly what curl_cffi exists to fix.

The default trigger is 07:02:00.000 ET — confirmed empirically as the
real release time (a 7:00:00 fire returned "Please wait until 07:02:00").

Usage:
    python book_court_api.py                              # next 7:02 ET, 6-7:30PM, today+7
    python book_court_api.py --target-date 2026-05-05
    python book_court_api.py --recon-once --target-date 2026-05-20
    python book_court_api.py --dry-run

Pair with:
    caffeinate -dimsu .venv/bin/python -u book_court_api.py 2>&1 | tee -a booking_results.log
"""

from __future__ import annotations

import argparse
import asyncio
import email.utils
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from curl_cffi.requests import AsyncSession
from dotenv import load_dotenv
from playwright.async_api import (
    Locator,
    Page,
    TimeoutError as PWTimeout,
    async_playwright,
)

# ─── Constants ────────────────────────────────────────────────────────────────

ET = ZoneInfo("America/New_York")
BASE_URL = "https://www.rckbracquetgarden.com"
BOOK_PAGE_URL = f"{BASE_URL}/book/ritz-carlton-racquet-garden-key-biscayne"

# Public venue config (not personal).
COURT_ID = 1241          # Padel 2 (auto_fill_courts:true falls back to 1240/1242)
FACILITY_ID = 127

# Account-specific values come from .env (gitignored) so NO personal/card data
# lives in source. The multi-account worker overrides these per booking; for the
# standalone CLI they default to whatever your .env holds.
load_dotenv(Path(__file__).resolve().parent / ".env")
USER_ID = int(os.getenv("RCKB_USER_ID") or 0)
CARD_ID = int(os.getenv("RCKB_CARD_ID") or 0)
CARD_LAST_FOUR = os.getenv("RCKB_CARD_LAST_FOUR", "")
CARD_BRAND = os.getenv("RCKB_CARD_BRAND", "")
GUEST_USER_ID = int(os.getenv("RCKB_GUEST_USER_ID") or 0)
GUEST_NAME = os.getenv("RCKB_GUEST_NAME", "A")

# Default slot: 6:00–7:30 PM (production target).
DEFAULT_HOUR_START = 64800   # 18 * 3600
DEFAULT_HOUR_END = 70200     # 19.5 * 3600

BOOKING_ENDPOINT = f"{BASE_URL}/api/courts/{COURT_ID}/booking_player"
PROBE_ENDPOINT = f"{BASE_URL}/api/users/{USER_ID}/notifications"

SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_LOG = SCRIPT_DIR / "booking_results.log"

# Pacing
DEFAULT_PREWARM_SECONDS = 240   # auth 4 min before trigger
PROBE_LEAD_S = 30               # warm + calibrate this far before strike
PROBE_SAMPLES = 1               # number of probes. RCKB's rate limit kicks
                                # in around 4 requests in ~2s; the pre-strike
                                # auth flow + probes + strike all count toward
                                # one budget. We've validated 1 probe + 1 POST
                                # 30s apart works (yesterday's recon-once was
                                # exactly that pattern, returned a clean 422).
                                # 3 probes back-to-back tripped 503 in testing.
STRIKE_RETRY_MS = 1500          # cadence within strike loop (gentle, avoid 503)
STRIKE_503_BACKOFF_S = 10       # back off this long after a 503 response
STRIKE_MAX_DURATION_S = 600     # 10 min total budget (covers "wait until X" auto-sleep)
WAIT_UNTIL_SLACK_MS = 50        # add this to the server-indicated wait-until time
                                # (was 100ms; tightening since the timestamp is
                                # server-authoritative, so less slack = faster shot)
SAFETY_LANDING_OFFSET_MS = 20   # aim our packet to arrive at server this many
                                # ms AFTER the release moment, not before. Being
                                # slightly late beats being slightly early —
                                # early fires get 422 "wait until X" and waste a
                                # full round-trip; late fires lose only the gap
                                # between us and the fastest bot (if any).

# curl_cffi browser profile. chrome136 is the most recent Chrome we can mimic;
# its TLS handshake matches modern Chrome closely enough that Cloudflare
# treats it as a legitimate browser.
CHROME_IMPERSONATE = "chrome136"


# ─── Time helpers ─────────────────────────────────────────────────────────────

def now_et() -> datetime:
    return datetime.now(ET)


def fmt(dt: datetime) -> str:
    return dt.astimezone(ET).isoformat(timespec="seconds")


def fmt_exact(dt: datetime) -> str:
    return dt.astimezone(ET).isoformat(timespec="microseconds")


def parse_trigger_at(raw: str | None) -> datetime:
    """ISO8601, '+Ns/m/h', or None → next 7:02 AM ET (confirmed open time)."""
    if raw is None:
        now = now_et()
        t = now.replace(hour=7, minute=2, second=0, microsecond=0)
        if now >= t:
            t += timedelta(days=1)
        return t
    m = re.fullmatch(r"\+(\d+)([smh])", raw.strip())
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        seconds = n * {"s": 1, "m": 60, "h": 3600}[unit]
        return now_et() + timedelta(seconds=seconds)
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


def parse_target_date(raw: str | None, trigger: datetime) -> date:
    if raw is None:
        return trigger.astimezone(ET).date() + timedelta(days=7)
    return date.fromisoformat(raw)


async def sleep_until(target: datetime, *, label: str = "") -> None:
    while True:
        remaining = (target - now_et()).total_seconds()
        if remaining <= 0:
            return
        if remaining > 30:
            await asyncio.sleep(min(remaining - 30, 60))
        elif remaining > 5:
            print(f"[{fmt(now_et())}] {label} — T-{remaining:.0f}s")
            await asyncio.sleep(min(remaining - 5, 5))
        elif remaining > 0.05:
            await asyncio.sleep(0.05)
        else:
            return


def log_result(msg: str) -> None:
    line = f"[{fmt_exact(now_et())}] {msg}"
    print(line)
    with RESULTS_LOG.open("a") as f:
        f.write(line + "\n")


# ─── Login helpers (mirror prod book_court.py) ────────────────────────────────

async def _dismiss_popups(page: Page) -> None:
    for label in ("Accept all", "Accept", "I agree", "OK", "Got it", "Close", "Dismiss"):
        try:
            btn = page.get_by_role("button", name=re.compile(rf"^{re.escape(label)}$", re.I))
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click(timeout=1000)
        except Exception:
            pass


async def _first_visible(page: Page, factories, *, label: str, timeout_ms: int = 10000) -> Locator:
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    last_err: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        for f in factories:
            try:
                loc = f()
                if await loc.count() > 0 and await loc.first.is_visible():
                    return loc.first
            except Exception as e:
                last_err = e
        await asyncio.sleep(0.1)
    raise RuntimeError(f"Could not locate {label} within {timeout_ms}ms (last err: {last_err})")


async def _click_first_match(page: Page, factories, *, label: str, timeout_ms: int = 10000) -> None:
    loc = await _first_visible(page, factories, label=label, timeout_ms=timeout_ms)
    try:
        await loc.click(timeout=3000)
    except Exception:
        await loc.click(force=True, no_wait_after=True, timeout=2000)
    print(f"[{fmt(now_et())}] Clicked: {label}")


async def _login(page: Page, email: str, password: str) -> None:
    await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
    await _dismiss_popups(page)

    await _click_first_match(
        page,
        [
            lambda: page.get_by_role("link", name=re.compile(r"^login$", re.I)),
            lambda: page.get_by_role("button", name=re.compile(r"^login$", re.I)),
            lambda: page.get_by_text(re.compile(r"^login$", re.I)).first,
        ],
        label="Login (home)",
    )

    email_field = await _first_visible(
        page,
        [
            lambda: page.locator("#user_email"),
            lambda: page.locator('input[name="user[email]"]'),
            lambda: page.locator('input[type="email"]'),
            lambda: page.get_by_placeholder(re.compile(r"email", re.I)),
        ],
        label="email field",
    )
    await email_field.fill(email)

    pwd_field = await _first_visible(
        page,
        [
            lambda: page.locator("#user_password"),
            lambda: page.locator('input[name="user[password]"]'),
            lambda: page.locator('input[type="password"]'),
        ],
        label="password field",
    )
    await pwd_field.fill(password)

    await _click_first_match(
        page,
        [
            lambda: page.get_by_role("button", name=re.compile(r"^login$|^sign in$", re.I)),
            lambda: page.locator('button[type="submit"]'),
            lambda: page.get_by_text(re.compile(r"^login$", re.I)).first,
        ],
        label="Login (submit)",
    )
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except PWTimeout:
        pass
    print(f"[{fmt(now_et())}] Login submitted.")


async def authenticate(
    headless: bool = False,
    *,
    email: str | None = None,
    password: str | None = None,
) -> tuple[dict, str, str]:
    """Login via Playwright. Returns (cookies_dict, csrf_token, user_agent).

    Browser is closed before this returns. We don't need it during the strike;
    curl_cffi takes over from here with the captured auth state.

    Credentials come from the email/password args when provided (multi-account
    use by the worker); otherwise they fall back to .env (the original CLI flow).
    """
    if not email or not password:
        load_dotenv(SCRIPT_DIR / ".env")
        email = email or os.getenv("RCKB_EMAIL")
        password = password or os.getenv("RCKB_PASSWORD")
    if not email or not password:
        raise RuntimeError("RCKB credentials missing (pass email/password or set .env)")

    print(f"[{fmt(now_et())}] Authenticating via Playwright (headless={headless})…")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await context.new_page()
        try:
            await _login(page, email, password)
            await page.goto(BOOK_PAGE_URL, wait_until="domcontentloaded")
            csrf = await page.evaluate(
                "() => document.querySelector('meta[name=\"csrf-token\"]')?.content || ''"
            )
            if not csrf:
                raise RuntimeError("CSRF token not found in <meta name=csrf-token>.")
            ua = await page.evaluate("() => navigator.userAgent")
            raw_cookies = await context.cookies(BASE_URL)
            cookies = {c["name"]: c["value"] for c in raw_cookies}
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

    print(f"[{fmt(now_et())}] Auth ready (csrf len={len(csrf)}, "
          f"cookies={len(cookies)}, ua=…{ua[-40:]})")
    return cookies, csrf, ua


# ─── Booking payload + headers ────────────────────────────────────────────────

def build_payload(
    target: date,
    hour_start: int,
    hour_end: int,
    *,
    user_id: int = USER_ID,
    guest_user_id: int = GUEST_USER_ID,
    guest_name: str = GUEST_NAME,
    card_id: int = CARD_ID,
    card_last_four: str = CARD_LAST_FOUR,
    card_brand: str = CARD_BRAND,
) -> dict:
    """Build the booking POST body.

    Account-specific values default to this script's constants (original CLI
    behavior) but can be overridden per-account by the multi-account worker.
    """
    return {
        "reservation": {
            "date": target.isoformat(),
            "hour_start": hour_start,
            "hour_end": hour_end,
            "reservation_type": 4,
            "public_game": False,
            "min_ntrp": 1,
            "max_ntrp": 7,
            "kind": "reservation",
            "ntrp_verified": False,
        },
        "payment": {
            "method": "card",
            "payment_intent_id": "",
            "card_details": {
                "lastFourCardDigits": card_last_four,
                "cardBrand": card_brand,
                "id": card_id,
            },
            "coupon": {"code": ""},
            "moment": "now",
        },
        "user_ids": [user_id, guest_user_id, guest_user_id, guest_user_id],
        "user_excluded_ids": [],
        "user_ids_guest_names": {
            "player0": {"name": None},
            "player1": {"name": guest_name},
            "player2": {"name": guest_name},
            "player3": {"name": guest_name},
        },
        "reservation_fees": [],
        "users_fees": {
            "player0": {"fees": [None]},
            "player1": {"fees": [None]},
            "player2": {"fees": [None]},
            "player3": {"fees": [None]},
        },
        "auto_fill_courts": True,
        "free_fare_players": [],
        "guest_pass_users": [],
    }


def build_headers(csrf: str, ua: str) -> dict:
    """Headers matching the captured browser request as closely as possible.

    user-agent comes from the actual Playwright browser so it stays
    consistent with the cookies (Cloudflare scopes some cookies to UA).
    """
    return {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": BASE_URL,
        "referer": BOOK_PAGE_URL,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": ua,
        "x-csrf-token": csrf,
        "x-requested-with": "XMLHttpRequest",
    }


# ─── Strike via curl_cffi ─────────────────────────────────────────────────────

DEFINITIVE_FAILURE_PATTERNS = (
    "already booked",
    "no longer available",
    "already reserved",
    "not available",
    "slot is no longer",
    "court is no longer",
    "invalidauthenticitytoken",
    "csrf",
)


def _classify_response(status: int, body_text: str) -> str:
    if 200 <= status < 300:
        return "success"
    low = (body_text or "").lower()
    if any(p in low for p in DEFINITIVE_FAILURE_PATTERNS):
        return "definitive-fail"
    return "transient"


# Pulls absolute timestamps out of error strings like:
#   "Please wait until Mon\n04 May 2026 07:02:00 -0400"
#   "You can't book beyond Sun\n03 May 2026 10:14:22 -0400"
_WAIT_UNTIL_RE = re.compile(
    r"(?:wait until|book beyond)\s+"
    r"(?P<wkday>\w+)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<mon>\w+)\s+"
    r"(?P<year>\d{4})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s*"
    r"(?P<tz>[+-]\d{4})",
    re.IGNORECASE | re.DOTALL,
)


def _parse_wait_until(body: str) -> datetime | None:
    if not body:
        return None
    m = _WAIT_UNTIL_RE.search(body)
    if not m:
        return None
    parts = m.groupdict()
    raw = (
        f"{parts['day']} {parts['mon']} {parts['year']} "
        f"{parts['time']} {parts['tz']}"
    )
    try:
        return datetime.strptime(raw, "%d %b %Y %H:%M:%S %z").astimezone(ET)
    except Exception:
        return None


async def fire_via_curl(session: AsyncSession, payload: dict, headers: dict) -> dict:
    """One booking attempt via curl_cffi. Returns {status, body, ms}."""
    t0 = now_et()
    try:
        resp = await session.post(
            BOOKING_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=10,
        )
        ms = (now_et() - t0).total_seconds() * 1000
        return {"status": resp.status_code, "body": resp.text, "ms": ms}
    except Exception as e:
        ms = (now_et() - t0).total_seconds() * 1000
        return {"status": 0, "body": f"exception: {e}", "ms": ms}


async def calibrate_timing(
    session: AsyncSession,
    headers: dict,
    *,
    samples: int = PROBE_SAMPLES,
) -> float:
    """Probe RCKB to warm the TCP+TLS connection AND measure forward latency.

    Default is a SINGLE probe (PROBE_SAMPLES=1) because RCKB rate-limits
    aggressively — 3-4 requests in a few seconds returns 503 "Too many
    requests", and we don't want the strike POST to be the request that
    trips it. The probe at T-30s plus the strike at T+0 are 30 s apart,
    well within safe spacing.

    Trade-off: a single sample has more variance (~±20 ms) than median of 3
    (~±10 ms). For our timing math (where total budget is ~50 ms anyway),
    this doesn't matter. The adaptive "wait until X" recovery on attempt 2
    handles any residual error.

    The HTTP `Date:` header skew estimate is still printed for visibility
    but NOT applied — see prior comment block, it's biased by Date being
    floored to whole seconds + server processing time.

    Returns `forward_ms` — estimated one-way latency, RTT/2.
    """
    rtts: list[float] = []
    for i in range(samples):
        t_send = now_et()
        try:
            r = await session.get(PROBE_ENDPOINT, headers=headers, timeout=5)
            t_recv = now_et()
        except Exception as e:
            print(f"[{fmt(now_et())}] probe {i+1}/{samples} failed: {e}")
            if i < samples - 1:
                await asyncio.sleep(0.4)
            continue

        rtt_ms = (t_recv - t_send).total_seconds() * 1000
        rtts.append(rtt_ms)

        skew_log = ""
        date_str = r.headers.get("date") or r.headers.get("Date")
        if date_str:
            try:
                server_dt = email.utils.parsedate_to_datetime(date_str).astimezone(ET)
                bias_skew = (server_dt - t_send).total_seconds() * 1000 - rtt_ms / 2
                skew_log = f"  skew_diag~{bias_skew:+.0f}ms (biased, ignored)"
            except Exception:
                pass

        print(f"[{fmt(now_et())}]   probe {i+1}: HTTP {r.status_code}  "
              f"rtt={rtt_ms:.0f}ms{skew_log}")

        if r.status_code != 200:
            print(f"     WARNING probe body: {(r.text or '')[:200]}")

        if i < samples - 1:
            await asyncio.sleep(0.4)

    if not rtts:
        print(f"[{fmt(now_et())}] Calibration failed — defaults forward=80ms")
        return 80.0

    # Use median when we have multiple samples; single sample is its own median.
    rtt_use = sorted(rtts)[len(rtts) // 2]
    forward_ms = rtt_use / 2

    label = "median" if len(rtts) > 1 else "single sample"
    print(f"[{fmt(now_et())}] Calibrated: rtt={rtt_use:.0f}ms ({label}), "
          f"forward~{forward_ms:.0f}ms (skew assumed 0 — trusting local NTP)")
    return forward_ms


async def strike_loop(
    session: AsyncSession,
    payload: dict,
    headers: dict,
    trigger: datetime,
    *,
    forward_ms: float = 80.0,
) -> tuple[dict | None, datetime, int]:
    """Fire booking POSTs precisely timed against the trigger.

    The first attempt is scheduled so the *packet arrives at the server*
    SAFETY_LANDING_OFFSET_MS after the release time, assuming the local
    clock is reasonably accurate (NTP-synced):

        local_fire = trigger + landing_offset - forward

    With trigger=7:02:00, forward=80ms, landing_offset=20ms:
    we fire at 7:01:59.940 local → packet arrives server-side at ~7:02:00.020.

    Adaptive recovery for SECOND+ attempts (handles clock-skew error):
      • 422 with "Please wait until X" → sleep until X + WAIT_UNTIL_SLACK_MS
        (server's timestamp is authoritative; this corrects any clock drift)
      • 503 "Too many requests" → back off STRIKE_503_BACKOFF_S seconds
      • Otherwise sleep STRIKE_RETRY_MS between attempts
      • First 2xx wins; definitive failure (slot taken / CSRF stale) stops early
    """
    optimal_fire_local = trigger + timedelta(
        milliseconds=SAFETY_LANDING_OFFSET_MS - forward_ms
    )
    deadline = trigger + timedelta(seconds=STRIKE_MAX_DURATION_S)

    if now_et() < optimal_fire_local:
        await sleep_until(optimal_fire_local, label="Pre-strike (calibrated)")
    print(f"[{fmt_exact(now_et())}] Entering strike loop "
          f"(trigger={fmt_exact(trigger)}, "
          f"landing target=server time +{SAFETY_LANDING_OFFSET_MS}ms, "
          f"deadline=+{STRIKE_MAX_DURATION_S}s)")

    attempt = 0
    last_result: dict | None = None
    last_attempt_time = now_et()
    while now_et() < deadline:
        attempt += 1
        last_attempt_time = now_et()
        result = await fire_via_curl(session, payload, headers)
        status = int(result.get("status", 0))
        body = result.get("body", "") or ""
        ms = float(result.get("ms", 0.0))
        preview = body[:240].replace("\n", " ")
        kind = _classify_response(status, body)
        print(f"[{fmt_exact(last_attempt_time)}] "
              f"attempt {attempt}: HTTP {status} ({ms:.0f}ms, {kind}) — {preview}")
        last_result = result
        if kind in ("success", "definitive-fail"):
            return result, last_attempt_time, attempt

        if status == 503:
            print(f"[{fmt(now_et())}]   503 rate limit — backing off "
                  f"{STRIKE_503_BACKOFF_S}s")
            await asyncio.sleep(STRIKE_503_BACKOFF_S)
            continue

        wait_until = _parse_wait_until(body) if status == 422 else None
        if wait_until is not None:
            slack = wait_until + timedelta(milliseconds=WAIT_UNTIL_SLACK_MS)
            wait_s = (slack - now_et()).total_seconds()
            if 0 < wait_s <= STRIKE_MAX_DURATION_S:
                print(f"[{fmt(now_et())}]   server says wait until "
                      f"{fmt_exact(wait_until)} — sleeping {wait_s*1000:.0f}ms")
                await asyncio.sleep(wait_s)
                continue

        await asyncio.sleep(STRIKE_RETRY_MS / 1000)

    return last_result, last_attempt_time, attempt


# ─── Orchestration ────────────────────────────────────────────────────────────

def _extract_reservation_id(body_text: str) -> str:
    try:
        body = json.loads(body_text)
    except Exception:
        return "?"
    return (
        body.get("reservation_id")
        or body.get("public_id")
        or body.get("id")
        or (body.get("reservation") or {}).get("public_id")
        or (body.get("location") or {}).get("slug")
        or "?"
    )


def _seed_session_cookies(session: AsyncSession, cookies: dict) -> None:
    """Push the Playwright-extracted cookies onto the curl_cffi session.

    Scope to the apex domain so they apply to every subdomain RCKB uses.
    """
    for name, value in cookies.items():
        try:
            session.cookies.set(name, value, domain=".rckbracquetgarden.com", path="/")
        except Exception:
            # Some cookie libs reject leading-dot domains; fall back to bare host.
            try:
                session.cookies.set(name, value, domain="www.rckbracquetgarden.com", path="/")
            except Exception:
                pass


async def run(args) -> int:
    trigger = parse_trigger_at(args.trigger_at)
    target = parse_target_date(args.target_date, trigger)
    prewarm_start = trigger - timedelta(seconds=args.prewarm_seconds)

    print(f"[{fmt(now_et())}] Plan: auth by {fmt(prewarm_start)}, "
          f"strike at {fmt_exact(trigger)}, "
          f"target {target.isoformat()} "
          f"hour_start={args.hour_start} hour_end={args.hour_end}")

    if args.dry_run:
        payload = build_payload(target, args.hour_start, args.hour_end)
        print(f"[{fmt(now_et())}] DRY RUN — would POST {BOOKING_ENDPOINT}")
        print(json.dumps(payload, indent=2))
        return 0

    payload = build_payload(target, args.hour_start, args.hour_end)

    # ── Recon-once: skip pre-warm wait, auth + warm + fire ONE POST. ──
    # We do a probe GET first so the second measurement reflects strike-time
    # latency (warm TCP/TLS) rather than cold-handshake cost. The real strike
    # loop runs on a connection warmed by the pre-probe at T-30s, so this
    # better matches what we'll actually see at 7:02:00 tomorrow.
    if args.recon_once:
        cookies, csrf, ua = await authenticate(headless=args.headless)
        headers = build_headers(csrf, ua)
        async with AsyncSession(impersonate=CHROME_IMPERSONATE) as session:
            _seed_session_cookies(session, cookies)

            # Warm-up GET — mirror the real probe step.
            try:
                tw = now_et()
                rw = await session.get(PROBE_ENDPOINT, headers=headers, timeout=5)
                wms = (now_et() - tw).total_seconds() * 1000
                print(f"[{fmt(now_et())}] probe GET {PROBE_ENDPOINT} → "
                      f"{rw.status_code} ({wms:.0f}ms) [cold, includes TLS]")
                if rw.status_code != 200:
                    print(f"  WARNING probe body: {(rw.text or '')[:300]}")
            except Exception as e:
                print(f"[{fmt(now_et())}] probe failed: {e}")

            # The real measurement: POST on a warm connection.
            t0 = now_et()
            result = await fire_via_curl(session, payload, headers)
            print(f"[{fmt_exact(t0)}] one-shot POST → "
                  f"HTTP {result['status']} ({result['ms']:.0f}ms) [warm]")
            print((result.get("body") or "")[:1500])
            return 0 if 200 <= result.get("status", 0) < 300 else 1

    # ── Real strike. ──
    if now_et() < prewarm_start:
        await sleep_until(prewarm_start, label="Pre-warm")

    cookies, csrf, ua = await authenticate(headless=args.headless)
    headers = build_headers(csrf, ua)

    async with AsyncSession(impersonate=CHROME_IMPERSONATE) as session:
        _seed_session_cookies(session, cookies)

        # Calibration: warm the TCP+TLS connection AND measure forward
        # latency so the strike's first attempt lands at server T+~20ms.
        warm_at = trigger - timedelta(seconds=PROBE_LEAD_S)
        if now_et() < warm_at:
            await sleep_until(warm_at, label="Pre-probe")
        forward_ms = await calibrate_timing(session, headers)

        result, last_attempt_time, n_attempts = await strike_loop(
            session, payload, headers, trigger,
            forward_ms=forward_ms,
        )

    if result is None:
        log_result(
            f"No response after {n_attempts} attempts "
            f"(last at {fmt_exact(last_attempt_time)})"
        )
        return 1

    status = int(result.get("status", 0))
    body = result.get("body", "") or ""

    if 200 <= status < 300:
        res_id = _extract_reservation_id(body)
        log_result(
            f"BOOKED via API: {target.isoformat()} "
            f"hour_start={args.hour_start} hour_end={args.hour_end} "
            f"reservation={res_id} attempts={n_attempts}"
        )
        return 0

    log_result(
        f"Strike failed: HTTP {status} after {n_attempts} attempts. "
        f"Last response: {body[:300]}"
    )
    return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Direct API booker (Tier 1: curl_cffi for low-latency strike)."
    )
    p.add_argument("--trigger-at", default=None,
                   help="ISO8601 or '+Ns/m/h'. Default: next 7:02 AM ET.")
    p.add_argument("--target-date", default=None,
                   help="ISO date YYYY-MM-DD. Default: trigger.date() + 7.")
    p.add_argument("--hour-start", type=int, default=DEFAULT_HOUR_START,
                   help=f"Slot start (sec since midnight, default {DEFAULT_HOUR_START} = 6 PM).")
    p.add_argument("--hour-end", type=int, default=DEFAULT_HOUR_END,
                   help=f"Slot end (sec since midnight, default {DEFAULT_HOUR_END} = 7:30 PM).")
    p.add_argument("--prewarm-seconds", type=int, default=DEFAULT_PREWARM_SECONDS,
                   help=f"Auth this far before trigger (default {DEFAULT_PREWARM_SECONDS}).")
    p.add_argument("--dry-run", action="store_true",
                   help="Print payload but don't POST.")
    p.add_argument("--recon-once", action="store_true",
                   help="Skip the strike loop, fire ONE POST immediately (debug).")
    p.add_argument("--headless", action="store_true",
                   help="Run the auth browser headless (default: visible window).")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    try:
        rc = asyncio.run(run(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()

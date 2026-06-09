#!/usr/bin/env python3
"""Padel booking worker.

Reads queued booking_requests from the shared SQLite DB, fires the RCKB strike
at 07:02 ET for each one CONCURRENTLY (multi-account / multi-bot), and writes
attempt + booking rows back so the web dashboard lights up.

Modes:
    python worker.py --list               # show pending requests and exit (safe)
    python worker.py --now --dry-run      # process soonest group NOW, no auth, no POST (offline)
    python worker.py --now                # process soonest group NOW, REAL auth + POST (recon-ish)
    python worker.py                       # daemon: wait until the trigger's prewarm, then fire for real

The strike engine itself is REUSED from ../../padel-booking/book_court_api.py —
the worker only adds DB plumbing, scheduling, and multi-account fan-out.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parent
ENGINE_DIR = WORKER_DIR.parent.parent / "padel-booking"
DB_PATH = os.environ.get("PADEL_DB_PATH") or str(WORKER_DIR.parent / "data" / "booking.db")

# Reuse the existing, battle-tested strike engine.
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(WORKER_DIR))
from book_court_api import (  # noqa: E402
    ET,
    CHROME_IMPERSONATE,
    PROBE_LEAD_S,
    DEFAULT_PREWARM_SECONDS,
    authenticate,
    build_payload,
    build_headers,
    calibrate_timing,
    strike_loop,
    sleep_until,
    now_et,
    fmt,
    _seed_session_cookies,
    _extract_reservation_id,
    _classify_response,
)
from curl_cffi.requests import AsyncSession  # noqa: E402
from crypto import decrypt  # noqa: E402

REQUIRED_ACCOUNT_FIELDS = (
    "rckb_user_id",
    "card_id",
    "card_last_four",
    "card_brand",
    "guest_user_id",
)


# ─── DB helpers ───────────────────────────────────────────────────────────────

def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def fetch_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.*, a.email, a.password, a.label AS account_label,
               a.rckb_user_id, a.card_id, a.card_last_four, a.card_brand,
               a.guest_user_id, a.guest_name
          FROM booking_requests r
          JOIN accounts a ON a.id = r.account_id
         WHERE r.status = 'pending'
         ORDER BY r.trigger_at
        """
    ).fetchall()


def set_status(conn: sqlite3.Connection, request_id: int, status: str) -> None:
    conn.execute(
        "UPDATE booking_requests SET status=? WHERE id=?", (status, request_id)
    )
    conn.commit()


def write_attempt(conn: sqlite3.Connection, req: dict, res: dict) -> None:
    conn.execute(
        """
        INSERT INTO attempts
          (request_id, account_id, fired_at, target_date, hour_start, hour_end,
           outcome, http_status, reservation_id, n_attempts, message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            req["id"], req["account_id"], now_et().isoformat(timespec="seconds"),
            req["target_date"], req["hour_start"], req["hour_end"],
            res["outcome"], res["http_status"], res["reservation_id"],
            res["n_attempts"], res["message"],
        ),
    )
    conn.commit()


def write_booking(conn: sqlite3.Connection, req: dict, res: dict, *, source: str) -> None:
    conn.execute(
        """
        INSERT INTO bookings
          (account_id, reservation_id, target_date, hour_start, hour_end,
           court_label, source, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (
            req["account_id"], res["reservation_id"], req["target_date"],
            req["hour_start"], req["hour_end"],
            "DRY RUN" if source == "dry-run" else "Padel",
            source,
        ),
    )
    conn.commit()


# ─── Strike (per request) ─────────────────────────────────────────────────────

def payload_for(req: dict) -> dict:
    return build_payload(
        date.fromisoformat(req["target_date"]),
        req["hour_start"],
        req["hour_end"],
        user_id=req["rckb_user_id"],
        guest_user_id=req["guest_user_id"],
        guest_name=req["guest_name"] or "A",
        card_id=req["card_id"],
        card_last_four=req["card_last_four"],
        card_brand=req["card_brand"],
    )


async def strike_one(req: dict, *, dry_run: bool, immediate: bool) -> dict:
    """Auth + strike a single booking request. Returns a result dict."""
    label = req["account_label"]
    trigger = datetime.fromisoformat(req["trigger_at"]).replace(tzinfo=ET)
    if immediate:
        trigger = now_et() + timedelta(seconds=3)

    # ── Offline dry-run: build the payload, send nothing. ──
    if dry_run:
        payload = payload_for(req)
        print(f"[{label}] DRY RUN — payload built for {req['target_date']} "
              f"{req['hour_start']}-{req['hour_end']} (no POST)")
        return {
            "outcome": "success",
            "http_status": None,
            "reservation_id": f"dryrun-{req['id']}",
            "n_attempts": 0,
            "message": "DRY RUN — payload built, no POST sent",
        }

    # ── Real path. Validate the account can actually book. ──
    missing = [f for f in REQUIRED_ACCOUNT_FIELDS if req[f] in (None, "")]
    if missing:
        return {
            "outcome": "error", "http_status": None, "reservation_id": None,
            "n_attempts": 0, "message": f"account '{label}' missing: {', '.join(missing)}",
        }

    payload = payload_for(req)
    cookies, csrf, ua = await authenticate(
        headless=True, email=req["email"], password=decrypt(req["password"])
    )
    headers = build_headers(csrf, ua)

    async with AsyncSession(impersonate=CHROME_IMPERSONATE) as session:
        _seed_session_cookies(session, cookies)
        warm_at = trigger - timedelta(seconds=PROBE_LEAD_S)
        if now_et() < warm_at:
            await sleep_until(warm_at, label=f"{label} pre-probe")
        forward_ms = await calibrate_timing(session, headers)
        result, _last_t, n_attempts = await strike_loop(
            session, payload, headers, trigger, forward_ms=forward_ms
        )

    status = int(result.get("status", 0)) if result else 0
    body = (result.get("body", "") if result else "") or ""
    if 200 <= status < 300:
        return {
            "outcome": "success", "http_status": status,
            "reservation_id": _extract_reservation_id(body),
            "n_attempts": n_attempts, "message": body[:200],
        }
    kind = _classify_response(status, body)
    return {
        "outcome": "definitive-fail" if kind == "definitive-fail" else "transient-fail",
        "http_status": status, "reservation_id": None,
        "n_attempts": n_attempts, "message": body[:200],
    }


# ─── Orchestration ────────────────────────────────────────────────────────────

async def process_group(conn: sqlite3.Connection, group: list[sqlite3.Row], *, dry_run: bool, immediate: bool) -> None:
    trigger_at = group[0]["trigger_at"]
    trigger = datetime.fromisoformat(trigger_at).replace(tzinfo=ET)
    print(f"Firing {len(group)} request(s) for trigger {trigger_at} ET "
          f"(dry_run={dry_run}, immediate={immediate})")

    if not immediate:
        prewarm = trigger - timedelta(seconds=DEFAULT_PREWARM_SECONDS)
        if now_et() < prewarm:
            print(f"Sleeping until prewarm {fmt(prewarm)} …")
            await sleep_until(prewarm, label="prewarm")

    reqs = [dict(r) for r in group]
    for r in reqs:
        set_status(conn, r["id"], "claimed")

    results = await asyncio.gather(
        *[strike_one(r, dry_run=dry_run, immediate=immediate) for r in reqs],
        return_exceptions=True,
    )

    for r, res in zip(reqs, results):
        if isinstance(res, BaseException):
            res = {
                "outcome": "error", "http_status": None, "reservation_id": None,
                "n_attempts": 0, "message": f"exception: {res!r}",
            }
        write_attempt(conn, r, res)
        if res["outcome"] == "success":
            write_booking(conn, r, res, source="dry-run" if dry_run else "app")
            set_status(conn, r["id"], "succeeded")
        else:
            set_status(conn, r["id"], "failed")
        print(f"  [{r['account_label']}] → {res['outcome']} "
              f"(HTTP {res['http_status']}) {res['message'][:80]}")


async def main_async(args: argparse.Namespace) -> int:
    conn = db_conn()
    pending = fetch_pending(conn)
    if not pending:
        print("No pending requests.")
        return 0

    soonest = pending[0]["trigger_at"]
    group = [r for r in pending if r["trigger_at"] == soonest]
    immediate = args.now or args.dry_run  # dry-run is always immediate
    await process_group(conn, group, dry_run=args.dry_run, immediate=immediate)
    print("Done.")
    return 0


def cmd_list() -> int:
    conn = db_conn()
    rows = fetch_pending(conn)
    if not rows:
        print("No pending requests.")
        return 0
    print(f"{len(rows)} pending request(s):")
    for r in rows:
        print(f"  #{r['id']}  trigger {r['trigger_at']} ET  →  book {r['target_date']} "
              f"{r['hour_start']}-{r['hour_end']}  ·  {r['account_label']}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Padel booking worker.")
    p.add_argument("--list", action="store_true", help="List pending requests and exit.")
    p.add_argument("--now", action="store_true",
                   help="Process the soonest pending group immediately (skip the scheduled wait).")
    p.add_argument("--dry-run", action="store_true",
                   help="Build payloads + write simulated results, but NO auth and NO POST (offline).")
    args = p.parse_args()

    if args.list:
        sys.exit(cmd_list())
    try:
        sys.exit(asyncio.run(main_async(args)))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()

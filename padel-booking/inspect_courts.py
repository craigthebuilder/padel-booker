#!/usr/bin/env python3
"""One-off diagnostic: dump the `available_courts` JSON from the RCKB API
to see which numeric court ID corresponds to which "Padel N" name.

Usage:
    python inspect_courts.py
    python inspect_courts.py --date 2026-05-04 --hour-start 64800 --hour-end 70200
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Reuse the auth helper.
from book_court_api import (
    BASE_URL,
    FACILITY_ID,
    DEFAULT_HOUR_START,
    DEFAULT_HOUR_END,
    authenticated_session,
)

ET = ZoneInfo("America/New_York")


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None,
                   help="ISO date YYYY-MM-DD. Default: tomorrow.")
    p.add_argument("--hour-start", type=int, default=DEFAULT_HOUR_START)
    p.add_argument("--hour-end", type=int, default=DEFAULT_HOUR_END)
    p.add_argument("--headless", action="store_true")
    args = p.parse_args()

    if args.date:
        target = date.fromisoformat(args.date)
    else:
        target = datetime.now(ET).date() + timedelta(days=1)

    # Convert ET-midnight to a Unix timestamp the way the site does.
    midnight_ts = int(datetime(
        target.year, target.month, target.day, 0, 0, 0, tzinfo=ET
    ).timestamp())

    courts_url = (
        f"{BASE_URL}/api/facilities/{FACILITY_ID}/available_courts"
        f"?date={midnight_ts}&surface=padel"
        f"&start_hour={args.hour_start}&hour_end={args.hour_end}"
        f"&kind=reservation"
    )
    print(f"GET {courts_url}\n")

    js = """
    async (url) => {
        const r = await fetch(url, {
            method: 'GET',
            headers: {
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'x-requested-with': 'XMLHttpRequest',
            },
            credentials: 'include',
        });
        const text = await r.text();
        return { status: r.status, body: text };
    }
    """
    async with authenticated_session(headless=args.headless) as (page, csrf):
        result = await page.evaluate(js, courts_url)
        print(f"HTTP {result['status']}")
        try:
            parsed = json.loads(result['body'])
            print(json.dumps(parsed, indent=2))
        except Exception:
            print(result['body'][:2000])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

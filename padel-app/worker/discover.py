#!/usr/bin/env python3
"""Discover an RCKB account's booking IDs (READ-ONLY — logs in + reads, never books).

After login it calls two authenticated JSON endpoints (same technique as
inspect_courts.py): /api/cards and /api/guest_users, plus reads user_id from the
page. Prints ONE JSON object (after a @@DISCOVER_RESULT@@ sentinel) with the
clean fields + diagnostics.

Usage:
  python discover.py            # creds from ../../padel-booking/.env
  python discover.py --headed   # visible browser (needed — headless is bot-blocked)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parent
# padel-booking is nested under padel-app; fall back to the legacy sibling layout.
ENGINE_DIR = WORKER_DIR.parent / "padel-booking"
if not ENGINE_DIR.exists():
    ENGINE_DIR = WORKER_DIR.parent.parent / "padel-booking"
sys.path.insert(0, str(ENGINE_DIR))

from book_court_api import _login, BOOK_PAGE_URL, BASE_URL, FACILITY_ID  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402


async def fetch_json(page, url: str) -> dict:
    res = await page.evaluate(
        """async (url) => {
            try {
                const r = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'accept': 'application/json, text/javascript, */*; q=0.01',
                        'x-requested-with': 'XMLHttpRequest',
                    },
                    credentials: 'include',
                });
                return { status: r.status, body: await r.text() };
            } catch (e) { return { status: 0, body: '' }; }
        }""",
        url,
    )
    return res if isinstance(res, dict) else {"status": 0, "body": ""}


def _as_list(data, *keys):
    """Coerce a JSON value into a list of dicts, looking under `keys` if it's a dict."""
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        arr = None
        for k in keys:
            if isinstance(data.get(k), list):
                arr = data[k]
                break
        arr = arr or []
    else:
        arr = []
    return [x for x in arr if isinstance(x, dict)]


def _pick_card(body: str):
    try:
        data = json.loads(body) if body else None
    except Exception:
        data = None
    cards = [
        {
            "id": c.get("id"),
            "last_four": c.get("last_four") or c.get("lastFour") or c.get("last4")
            or c.get("lastFourCardDigits"),
            "brand": c.get("brand") or c.get("card_brand") or c.get("cardBrand"),
        }
        for c in _as_list(data, "cards", "data")
    ]
    return (cards[0] if cards else None), cards


def _pick_guest(body: str):
    try:
        data = json.loads(body) if body else None
    except Exception:
        data = None
    guests = [
        {"id": g.get("id") or g.get("user_id"),
         "name": g.get("name") or g.get("first_name") or g.get("full_name")}
        for g in _as_list(data, "guests", "guest_users", "data")
    ]
    return (guests[0] if guests else None), guests


async def discover(email: str, password: str, *, headless: bool = False) -> dict:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless, args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="en-US",
            timezone_id="America/New_York",
        )
        page = await ctx.new_page()
        try:
            await _login(page, email, password)
            await page.goto(BOOK_PAGE_URL, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)

            html = await page.content()
            m = re.search(r"/api/users/(\d{3,})", html) or re.search(
                r'user_id["%:\s=]+?(\d{4,})', html
            )
            user_id = int(m.group(1)) if m else None

            cards_url = f"{BASE_URL}/api/cards"
            cards_resp = await fetch_json(page, cards_url)

            if user_id is None:
                # No user id on the page → we never actually got logged in.
                return {
                    "ok": False,
                    "error": "Could not confirm login — double-check the email and password.",
                    "_diag": {"cards_status": cards_resp.get("status"),
                              "cards_head": (cards_resp.get("body") or "")[:200]},
                }

            # Logged in but cards empty/null? Could be a render race — retry once.
            if not _pick_card(cards_resp.get("body") or "")[1]:
                await asyncio.sleep(1.5)
                cards_resp = await fetch_json(page, cards_url)

            guests_resp = await fetch_json(
                page, f"{BASE_URL}/api/guest_users?facility_id={FACILITY_ID}&approval=true"
            )

            card, all_cards = _pick_card(cards_resp.get("body") or "")
            guest, all_guests = _pick_guest(guests_resp.get("body") or "")

            return {
                "ok": True,
                "user_id": user_id,
                "card_id": card["id"] if card else None,
                "card_last_four": card["last_four"] if card else None,
                "card_brand": card["brand"] if card else None,
                "guest_user_id": guest["id"] if guest else None,
                "guest_name": guest["name"] if guest else None,
                "_diag": {
                    "cards_status": cards_resp.get("status"),
                    "cards_head": (cards_resp.get("body") or "")[:300],
                    "all_cards": all_cards,
                    "guests_status": guests_resp.get("status"),
                    "all_guests": all_guests,
                },
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        finally:
            for closer in (ctx.close, browser.close):
                try:
                    await closer()
                except Exception:
                    pass


def main() -> None:
    load_dotenv(ENGINE_DIR / ".env")
    email = os.environ.get("RCKB_EMAIL")
    password = os.environ.get("RCKB_PASSWORD")
    headless = "--headed" not in sys.argv
    if not email or not password:
        print("@@DISCOVER_RESULT@@")
        print(json.dumps({"ok": False, "error": "no credentials"}))
        sys.exit(1)
    result = asyncio.run(discover(email, password, headless=headless))
    print("@@DISCOVER_RESULT@@")  # split our JSON from the engine's stdout logs
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()

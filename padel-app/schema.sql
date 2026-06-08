-- padel-app schema  ·  SQLite
--
-- This file is the CONTRACT between the two tiers:
--   • Next.js (web)  writes: accounts, booking_requests   reads: attempts, bookings
--   • Python worker  reads:  accounts, booking_requests    writes: attempts, bookings
-- Neither tier calls the other directly — they rendezvous here, in the database.
--
-- SQLite has no ENUM and no native DATETIME type, so we use:
--   • TEXT for status fields (with the allowed values noted in comments)
--   • ISO-8601 TEXT for timestamps (sortable AND human-readable)

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────────────────────────────────────
-- accounts  ·  one row per RCKB login.
--
-- Holds credentials AND the per-account constants the booking payload needs.
-- These were hard-coded module constants in the engine (USER_ID, CARD_ID, …);
-- supporting multiple logins means each account must carry its own copy.
--
-- !! SECURITY (v1): `password` is PLAINTEXT. This DB stays LOCAL and gitignored.
--    Before any deploy we switch to encryption-at-rest / a secrets manager and
--    never commit real credentials. (This is the security-hygiene skill.)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    label           TEXT    NOT NULL,                 -- shown in the UI dropdown
    email           TEXT    NOT NULL,
    password        TEXT    NOT NULL,                 -- plaintext for now (see warning)
    rckb_user_id    INTEGER,                          -- the account's USER_ID in RCKB
    card_id         INTEGER,                          -- saved card used for payment
    card_last_four  TEXT,
    card_brand      TEXT,
    guest_user_id   INTEGER,                          -- filler "guest" player id
    guest_name      TEXT    DEFAULT 'A',
    is_default      INTEGER NOT NULL DEFAULT 0,       -- 0/1: preselect in the form
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- booking_requests  ·  INTENT.  "Book this slot; fire the strike at 07:02 ET."
-- The web form creates these; the worker consumes them.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS booking_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    target_date  TEXT    NOT NULL,                    -- ISO date to book (= trigger day + 7)
    hour_start   INTEGER NOT NULL,                    -- seconds since midnight (64800 = 18:00)
    hour_end     INTEGER NOT NULL,                    -- 70200 = 19:30
    trigger_at   TEXT    NOT NULL,                    -- ISO datetime ET of the 07:02 strike
    court_id     INTEGER,                             -- NULL → engine default (auto_fill_courts)
    status       TEXT    NOT NULL DEFAULT 'pending',  -- pending|claimed|succeeded|failed|cancelled
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
-- The worker's hot query: "give me pending requests, soonest trigger first."
CREATE INDEX IF NOT EXISTS idx_requests_pending
    ON booking_requests (status, trigger_at);

-- ─────────────────────────────────────────────────────────────────────────────
-- attempts  ·  EXECUTION LOG.  One row per strike run and its outcome.
-- Powers the "success / failed attempts" panel — your audit trail.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id      INTEGER REFERENCES booking_requests(id),  -- NULL if fired ad-hoc
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    fired_at        TEXT    NOT NULL,                 -- when the strike actually ran
    target_date     TEXT    NOT NULL,
    hour_start      INTEGER NOT NULL,
    hour_end        INTEGER NOT NULL,
    outcome         TEXT    NOT NULL,                 -- success|definitive-fail|transient-fail|error
    http_status     INTEGER,                          -- last HTTP status seen
    reservation_id  TEXT,                             -- set on success
    n_attempts      INTEGER NOT NULL DEFAULT 1,       -- POSTs fired inside the strike loop
    message         TEXT,                             -- response preview / error text
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- bookings  ·  ENTITY STATE.  A confirmed reservation.
-- Powers the "current bookings" panel (grouped by account).
--   v1: the worker inserts one on a successful attempt (source='app').
--   v2: a sync job can pull real reservations from RCKB (source='rckb-sync').
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    reservation_id  TEXT,                             -- RCKB reservation id
    target_date     TEXT    NOT NULL,
    hour_start      INTEGER NOT NULL,
    hour_end        INTEGER NOT NULL,
    court_label     TEXT,                             -- e.g. "Padel 2"
    source          TEXT    NOT NULL DEFAULT 'app',   -- app|rckb-sync
    status          TEXT    NOT NULL DEFAULT 'active',-- active|cancelled
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

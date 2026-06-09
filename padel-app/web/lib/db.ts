// web/lib/db.ts — the single door to the database for the web tier.
//
// Design choices worth understanding:
//  1. ONE connection, cached on globalThis. Next.js re-evaluates modules on every
//     hot-reload in dev; without this we'd leak a new DB handle on every save.
//  2. The path is overridable via PADEL_DB_PATH (config-via-env) so deploy can
//     point somewhere else without code changes.
//  3. Query helpers that touch `accounts` NEVER select `password` — secrets must
//     not flow toward the browser. (Security-hygiene skill, enforced in code.)

import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import { encrypt } from './crypto';

const DB_PATH =
  process.env.PADEL_DB_PATH ??
  path.join(process.cwd(), '..', 'data', 'booking.db'); // web/ → ../data/

const g = globalThis as unknown as { __padelDb?: DatabaseSync };

export function getDb(): DatabaseSync {
  if (!g.__padelDb) {
    const db = new DatabaseSync(DB_PATH);
    // WAL = readers don't block the writer — important once BOTH the web tier
    // and the Python worker hit this file concurrently.
    db.exec('PRAGMA journal_mode = WAL;');
    db.exec('PRAGMA foreign_keys = ON;');
    g.__padelDb = db;
  }
  return g.__padelDb;
}

// ─── Row types (mirror schema.sql) ───────────────────────────────────────────

export type Account = {
  id: number;
  label: string;
  email: string;
  password: string;
  rckb_user_id: number | null;
  card_id: number | null;
  card_last_four: string | null;
  card_brand: string | null;
  guest_user_id: number | null;
  guest_name: string | null;
  is_default: number;
  created_at: string;
};
// What we let the browser see — no password.
export type SafeAccount = Omit<Account, 'password'>;

export type BookingRequest = {
  id: number;
  account_id: number;
  target_date: string;
  hour_start: number;
  hour_end: number;
  trigger_at: string;
  court_id: number | null;
  status: string;
  created_at: string;
};

export type Attempt = {
  id: number;
  request_id: number | null;
  account_id: number;
  fired_at: string;
  target_date: string;
  hour_start: number;
  hour_end: number;
  outcome: string;
  http_status: number | null;
  reservation_id: string | null;
  n_attempts: number;
  message: string | null;
  created_at: string;
};

export type Booking = {
  id: number;
  account_id: number;
  reservation_id: string | null;
  target_date: string;
  hour_start: number;
  hour_end: number;
  court_label: string | null;
  source: string;
  status: string;
  created_at: string;
};

// ─── Query helpers (the web tier's vocabulary) ───────────────────────────────

export function listAccounts(): SafeAccount[] {
  return getDb()
    .prepare(
      `SELECT id, label, email, rckb_user_id, card_id, card_last_four,
              card_brand, guest_user_id, guest_name, is_default, created_at
         FROM accounts
        ORDER BY is_default DESC, label`,
    )
    .all()
    .map((r) => ({ ...(r as object) })) as SafeAccount[];
}

export function listAttempts(limit = 50): Attempt[] {
  return getDb()
    .prepare(`SELECT * FROM attempts ORDER BY fired_at DESC LIMIT ?`)
    .all(limit)
    .map((r) => ({ ...(r as object) })) as Attempt[];
}

export function listBookings(): Booking[] {
  return getDb()
    .prepare(
      `SELECT * FROM bookings
        WHERE status = 'active'
        ORDER BY target_date DESC, hour_start`,
    )
    .all()
    .map((r) => ({ ...(r as object) })) as Booking[];
}

export function listBookingRequests(): BookingRequest[] {
  return getDb()
    .prepare(`SELECT * FROM booking_requests ORDER BY trigger_at DESC`)
    .all()
    .map((r) => ({ ...(r as object) })) as BookingRequest[];
}

export function listPendingRequests(): BookingRequest[] {
  return getDb()
    .prepare(
      `SELECT * FROM booking_requests WHERE status = 'pending' ORDER BY trigger_at`,
    )
    .all()
    .map((r) => ({ ...(r as object) })) as BookingRequest[];
}

// ─── Account mutations (server-only) ─────────────────────────────────────────

export type AccountInput = {
  label: string;
  email: string;
  password?: string; // optional on update — blank means "keep current"
  rckb_user_id: number | null;
  card_id: number | null;
  card_last_four: string | null;
  card_brand: string | null;
  guest_user_id: number | null;
  guest_name: string | null;
  is_default: boolean;
};

export function createAccount(a: AccountInput): number {
  const db = getDb();
  if (a.is_default) db.prepare(`UPDATE accounts SET is_default = 0`).run();
  const r = db
    .prepare(
      `INSERT INTO accounts
         (label, email, password, rckb_user_id, card_id, card_last_four,
          card_brand, guest_user_id, guest_name, is_default)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      a.label,
      a.email,
      a.password ? encrypt(a.password) : '',
      a.rckb_user_id,
      a.card_id,
      a.card_last_four,
      a.card_brand,
      a.guest_user_id,
      a.guest_name,
      a.is_default ? 1 : 0,
    );
  return Number(r.lastInsertRowid);
}

export function updateAccount(id: number, a: AccountInput): void {
  const db = getDb();
  if (a.is_default) db.prepare(`UPDATE accounts SET is_default = 0`).run();
  db.prepare(
    `UPDATE accounts SET
       label = ?, email = ?, rckb_user_id = ?, card_id = ?, card_last_four = ?,
       card_brand = ?, guest_user_id = ?, guest_name = ?, is_default = ?
     WHERE id = ?`,
  ).run(
    a.label,
    a.email,
    a.rckb_user_id,
    a.card_id,
    a.card_last_four,
    a.card_brand,
    a.guest_user_id,
    a.guest_name,
    a.is_default ? 1 : 0,
    id,
  );
  // Only touch the password when a new one was actually provided.
  if (a.password && a.password.length > 0) {
    db.prepare(`UPDATE accounts SET password = ? WHERE id = ?`).run(encrypt(a.password), id);
  }
}

export function createBookingRequest(input: {
  account_id: number;
  target_date: string;
  hour_start: number;
  hour_end: number;
  trigger_at: string;
  court_id?: number | null;
}): number {
  const r = getDb()
    .prepare(
      `INSERT INTO booking_requests
         (account_id, target_date, hour_start, hour_end, trigger_at, court_id)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .run(
      input.account_id,
      input.target_date,
      input.hour_start,
      input.hour_end,
      input.trigger_at,
      input.court_id ?? null,
    );
  return Number(r.lastInsertRowid);
}

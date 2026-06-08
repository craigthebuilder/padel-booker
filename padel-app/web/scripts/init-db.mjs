// init-db.mjs — create the SQLite DB from schema.sql and seed the first account.
// Run with:  npm run db:init   (or)   node scripts/init-db.mjs
//
// Idempotent: re-running applies the schema (CREATE TABLE IF NOT EXISTS) and
// only seeds the default account when the accounts table is empty.

import { DatabaseSync } from 'node:sqlite';
import { readFileSync, existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url)); // web/scripts
const ROOT = path.resolve(__dirname, '..', '..'); // padel-app/
const DATA_DIR = path.join(ROOT, 'data');
const DB_PATH = process.env.PADEL_DB_PATH ?? path.join(DATA_DIR, 'booking.db');
const SCHEMA_PATH = path.join(ROOT, 'schema.sql');

mkdirSync(DATA_DIR, { recursive: true });

const db = new DatabaseSync(DB_PATH);
db.exec('PRAGMA journal_mode = WAL;'); // readers don't block the writer
db.exec(readFileSync(SCHEMA_PATH, 'utf8'));
console.log('✓ schema applied →', DB_PATH);

const { n } = db.prepare('SELECT COUNT(*) AS n FROM accounts').get();
if (n === 0) {
  // Read the WHOLE seed account from the engine's .env (gitignored) — so no
  // personal/card data is hard-coded in source. Missing creds → seed nothing
  // (you add an account via the dashboard's "Verify and add account").
  const envPath = path.resolve(ROOT, '..', 'padel-booking', '.env');
  const env = existsSync(envPath) ? readFileSync(envPath, 'utf8') : '';
  const get = (k) =>
    (env.match(new RegExp('^' + k + '=(.*)$', 'm'))?.[1] ?? '').trim();

  const email = get('RCKB_EMAIL');
  const password = get('RCKB_PASSWORD');
  if (email && password) {
    db.prepare(
      `INSERT INTO accounts
         (label, email, password, rckb_user_id, card_id, card_last_four,
          card_brand, guest_user_id, guest_name, is_default)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)`,
    ).run(
      get('RCKB_LABEL') || email,
      email,
      password,
      Number(get('RCKB_USER_ID')) || null,
      Number(get('RCKB_CARD_ID')) || null,
      get('RCKB_CARD_LAST_FOUR') || null,
      get('RCKB_CARD_BRAND') || null,
      Number(get('RCKB_GUEST_USER_ID')) || null,
      get('RCKB_GUEST_NAME') || 'A',
    );
    console.log('✓ seeded default account from padel-booking/.env');
  } else {
    console.log('• no RCKB creds in .env — skipped seeding (add via the dashboard)');
  }
} else {
  console.log(`• accounts already present (${n}) — skipping seed`);
}

db.close();
console.log('✓ done');

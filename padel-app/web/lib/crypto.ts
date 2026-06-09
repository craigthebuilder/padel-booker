// web/lib/crypto.ts — AES-256-GCM at-rest encryption for stored secrets.
//
// Format:  enc1.<base64(iv)>.<base64(ciphertext)>.<base64(tag)>
// The 32-byte key lives in data/secret.key (hex, gitignored) and is shared with
// the Python worker (worker/crypto.py uses the identical format), so the web
// encrypts and the worker decrypts the same value.

import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const KEY_PATH =
  process.env.PADEL_KEY_PATH ??
  path.join(process.cwd(), '..', 'data', 'secret.key');

const PREFIX = 'enc1.';
let keyCache: Buffer | null = null;

function key(): Buffer {
  if (!keyCache) {
    keyCache = Buffer.from(readFileSync(KEY_PATH, 'utf8').trim(), 'hex');
  }
  return keyCache;
}

export function isEncrypted(s: string): boolean {
  return typeof s === 'string' && s.startsWith(PREFIX);
}

export function encrypt(plain: string): string {
  const iv = randomBytes(12);
  const c = createCipheriv('aes-256-gcm', key(), iv);
  const ct = Buffer.concat([c.update(plain, 'utf8'), c.final()]);
  const tag = c.getAuthTag();
  return (
    PREFIX +
    [iv, ct, tag].map((b) => b.toString('base64')).join('.')
  );
}

/** Decrypt an enc1 value; pass through anything not encrypted (legacy plaintext). */
export function decrypt(s: string): string {
  if (!isEncrypted(s)) return s;
  const [, ivB, ctB, tagB] = s.split('.');
  const d = createDecipheriv(
    'aes-256-gcm',
    key(),
    Buffer.from(ivB, 'base64'),
  );
  d.setAuthTag(Buffer.from(tagB, 'base64'));
  return Buffer.concat([
    d.update(Buffer.from(ctB, 'base64')),
    d.final(),
  ]).toString('utf8');
}

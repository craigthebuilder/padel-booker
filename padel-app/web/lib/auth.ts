// web/lib/auth.ts — tiny shared-password gate.
//
// The cookie does NOT store the password. It stores an HMAC token derived from
// the password + a server-only secret, so it can't be forged without AUTH_SECRET.
// Both APP_PASSWORD and AUTH_SECRET live in web/.env.local (gitignored).

import { createHmac } from 'node:crypto';

export const AUTH_COOKIE = 'app_auth';

const PASSWORD = process.env.APP_PASSWORD ?? '';
const SECRET = process.env.AUTH_SECRET ?? 'dev-only-insecure-secret';

export function isCorrectPassword(input: string): boolean {
  return PASSWORD.length > 0 && input === PASSWORD;
}

/** Opaque token stored in the auth cookie (never the password itself). */
export function sessionToken(): string {
  return createHmac('sha256', SECRET).update(`authed:${PASSWORD}`).digest('hex');
}

export function isValidToken(token: string | undefined | null): boolean {
  return !!token && PASSWORD.length > 0 && token === sessionToken();
}

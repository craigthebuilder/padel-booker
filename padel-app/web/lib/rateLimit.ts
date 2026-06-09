// web/lib/rateLimit.ts — tiny in-memory login throttle (per server process).
// Coarse and resets on restart, but it turns the gate from "unlimited guesses"
// into "a handful, then a cooldown" — which is the point.

type Bucket = { fails: number; windowStart: number; lockedUntil: number };

const store = globalThis as unknown as { __loginBuckets?: Map<string, Bucket> };
const buckets: Map<string, Bucket> =
  store.__loginBuckets ?? (store.__loginBuckets = new Map());

const MAX_FAILS = 5;
const WINDOW_MS = 15 * 60_000; // failures counted within a 15-min window
const LOCK_MS = 15 * 60_000; // lockout length once tripped

/** Seconds remaining if this key is locked out, else 0. */
export function lockedFor(key: string): number {
  const b = buckets.get(key);
  if (b && b.lockedUntil > Date.now()) {
    return Math.ceil((b.lockedUntil - Date.now()) / 1000);
  }
  return 0;
}

export function recordFailure(key: string): void {
  const now = Date.now();
  let b = buckets.get(key);
  if (!b || now - b.windowStart > WINDOW_MS) {
    b = { fails: 0, windowStart: now, lockedUntil: 0 };
  }
  b.fails += 1;
  if (b.fails >= MAX_FAILS) b.lockedUntil = now + LOCK_MS;
  buckets.set(key, b);
}

export function recordSuccess(key: string): void {
  buckets.delete(key);
}

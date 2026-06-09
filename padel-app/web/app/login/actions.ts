'use server';

import { cookies, headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { AUTH_COOKIE, isCorrectPassword, sessionToken } from '@/lib/auth';
import { lockedFor, recordFailure, recordSuccess } from '@/lib/rateLimit';

export async function login(formData: FormData) {
  const password = String(formData.get('password') ?? '');
  const next = String(formData.get('next') ?? '/');
  // Only allow local redirects (no open-redirect via ?next=//evil.com).
  const dest = next.startsWith('/') && !next.startsWith('//') ? next : '/';

  // Throttle brute-force. Key by client IP when a proxy provides it, else global.
  const h = await headers();
  const xff = h.get('x-forwarded-for');
  const key =
    ((xff ? xff.split(',')[0] : h.get('x-real-ip')) || 'global').trim() ||
    'global';

  const wait = lockedFor(key);
  if (wait > 0) {
    redirect(
      `/login?error=${encodeURIComponent(`Too many attempts — wait ~${Math.ceil(wait / 60)} min.`)}`,
    );
  }

  if (!isCorrectPassword(password)) {
    recordFailure(key);
    redirect(
      `/login?error=1${dest !== '/' ? `&next=${encodeURIComponent(dest)}` : ''}`,
    );
  }
  recordSuccess(key);

  (await cookies()).set(AUTH_COOKIE, sessionToken(), {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    secure: process.env.NODE_ENV === 'production',
    maxAge: 60 * 60 * 24 * 30, // 30 days
  });
  redirect(dest);
}

export async function logout() {
  (await cookies()).delete(AUTH_COOKIE);
  redirect('/login');
}

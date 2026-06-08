'use server';

import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { AUTH_COOKIE, isCorrectPassword, sessionToken } from '@/lib/auth';

export async function login(formData: FormData) {
  const password = String(formData.get('password') ?? '');
  const next = String(formData.get('next') ?? '/');
  // Only allow local redirects (no open-redirect via ?next=//evil.com).
  const dest = next.startsWith('/') && !next.startsWith('//') ? next : '/';

  if (!isCorrectPassword(password)) {
    redirect(
      `/login?error=1${dest !== '/' ? `&next=${encodeURIComponent(dest)}` : ''}`,
    );
  }

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

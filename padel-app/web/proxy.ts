import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { AUTH_COOKIE, isValidToken } from '@/lib/auth';

// Site-wide password gate. In Next 16 this file is "proxy" (the former
// "middleware"); it runs on the server BEFORE every matched request — including
// Server Action POSTs — so the whole site is protected, not just visible pages.
export function proxy(request: NextRequest) {
  const token = request.cookies.get(AUTH_COOKIE)?.value;
  if (isValidToken(token)) {
    return NextResponse.next();
  }

  const loginUrl = new URL('/login', request.url);
  const { pathname } = request.nextUrl;
  if (pathname && pathname !== '/') {
    loginUrl.searchParams.set('next', pathname); // return here after login
  }
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Gate everything EXCEPT the login route, API, Next internals, and static assets.
  matcher: [
    '/((?!login|api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};

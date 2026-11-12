import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { loginUrl, safeNextPath, DEFAULT_AFTER_LOGIN } from '@/lib/login-redirect';

/**
 * Next.js Middleware for server-side route protection.
 * 
 * Checks for the presence of a `has_session` cookie (set by the frontend
 * on login) to determine if the user has an active session. If not,
 * redirects to /login before any page HTML is sent to the browser.
 * 
 * This eliminates the flash of protected page content that occurs with
 * purely client-side auth guards. The actual token validation still
 * happens client-side via the AuthGuard component.
 */

const PUBLIC_ROUTES = ['/login', '/register', '/sso/callback', '/forgot-password', '/reset-password'];

export function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // Skip middleware for static assets, API routes, and Next.js internals
    if (
        pathname.startsWith('/_next') ||
        pathname.startsWith('/api') ||
        pathname.startsWith('/favicon') ||
        pathname.match(/\.(ico|png|jpg|jpeg|svg|gif|webp|css|js|woff|woff2|ttf)$/)
    ) {
        return NextResponse.next();
    }

    const hasSession = request.cookies.get('has_session')?.value;
    const isPublicRoute = PUBLIC_ROUTES.includes(pathname);

    // Not authenticated, trying to access protected route → redirect to login,
    // remembering the page so sign-in can resume there.
    if (!hasSession && !isPublicRoute) {
        const target = loginUrl(pathname + request.nextUrl.search);
        return NextResponse.redirect(new URL(target, request.url));
    }

    // Authenticated, trying to access login/register → go where ?next= says
    // (a still-valid session opening a resume link), else the dashboard.
    if (hasSession && isPublicRoute) {
        const next = pathname === '/login' ? safeNextPath(request.nextUrl.searchParams.get('next')) : null;
        return NextResponse.redirect(new URL(next ?? DEFAULT_AFTER_LOGIN, request.url));
    }

    return NextResponse.next();
}

export const config = {
    matcher: [
        /*
         * Match all request paths except:
         * - _next/static (static files)
         * - _next/image (image optimization files)
         * - favicon.ico (favicon file)
         */
        '/((?!_next/static|_next/image|favicon.ico).*)',
    ],
};

/**
 * Resume-after-login: when a missing or expired session sends the user to
 * /login, the page they wanted rides along as `?next=` and they land there
 * after signing in (password, 2FA or SSO) instead of on the dashboard.
 *
 * `next` comes from the URL, so it is attacker-controllable: only a
 * same-origin path is accepted (no scheme, no `//host`, no `/\host`), and
 * never one of the auth pages themselves. Anything else falls back to the
 * dashboard. Safe to import from middleware (no window access at load).
 */

export const DEFAULT_AFTER_LOGIN = '/dashboard';

/** Pages reachable without a session. Middleware and AuthGuard both use
 *  this list — they disagreed once, and reset-password / SSO+2FA bounced. */
export const PUBLIC_ROUTES = ['/login', '/register', '/sso/callback', '/forgot-password', '/reset-password'];
/** Public pages a signed-in user is sent away from (the others finish a flow). */
export const SIGNED_IN_REDIRECT_ROUTES = ['/login', '/register'];

/** Pages that must never be a resume target (loops / pointless). */
const AUTH_PAGES = PUBLIC_ROUTES;

const SSO_NEXT_KEY = 'login_next';

/** Normalised same-origin path+query+hash, or null if `raw` isn't one. */
export function safeNextPath(raw: string | null | undefined): string | null {
    if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return null;
    let url: URL;
    try {
        url = new URL(raw, 'http://redwire.invalid');
    } catch {
        return null;
    }
    // URL parsing folds backslashes and dot-segments; re-check the result.
    if (url.origin !== 'http://redwire.invalid') return null;
    if (AUTH_PAGES.includes(url.pathname) || url.pathname === '/') return null;
    return url.pathname + url.search + url.hash;
}

/** /login, carrying `next` when it's a valid resume target. */
export function loginUrl(next?: string | null): string {
    const safe = safeNextPath(next);
    return safe ? `/login?next=${encodeURIComponent(safe)}` : '/login';
}

/** /login?next=<the page the browser is on now>. Client-side only. */
export function loginUrlForCurrentPage(): string {
    if (typeof window === 'undefined') return '/login';
    const { pathname, search, hash } = window.location;
    return loginUrl(pathname + search + hash);
}

/** Where to go after a successful sign-in on /login. Client-side only. */
export function afterLoginPath(): string {
    if (typeof window === 'undefined') return DEFAULT_AFTER_LOGIN;
    return safeNextPath(new URLSearchParams(window.location.search).get('next')) ?? DEFAULT_AFTER_LOGIN;
}

/** SSO leaves the app for the IdP: keep the target in sessionStorage. */
export function stashNextForSso(): void {
    try {
        const next = safeNextPath(new URLSearchParams(window.location.search).get('next'));
        if (next) sessionStorage.setItem(SSO_NEXT_KEY, next);
        else sessionStorage.removeItem(SSO_NEXT_KEY);
    } catch { /* private mode / disabled storage */ }
}

/** Read (and clear) the SSO resume target; dashboard if none. */
export function takeSsoNext(): string {
    try {
        const next = safeNextPath(sessionStorage.getItem(SSO_NEXT_KEY));
        sessionStorage.removeItem(SSO_NEXT_KEY);
        return next ?? DEFAULT_AFTER_LOGIN;
    } catch {
        return DEFAULT_AFTER_LOGIN;
    }
}

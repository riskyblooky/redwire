'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/auth-store';

/**
 * SSO Callback Page
 *
 * After SAML ACS, the backend redirects here with the access token in the
 * URL fragment and the refresh token in an HttpOnly cookie:
 *   /sso/callback#access_token=xxx
 *
 * If the user has 2FA enabled, the fragment instead contains:
 *   /sso/callback#requires_2fa=true&access_token=<pending_token>
 *
 * In the 2FA case we show a TOTP input and call POST /auth/verify-2fa.
 */
export default function SSOCallbackPage() {
    const router = useRouter();
    const { checkAuth, verifySsoTotp } = useAuthStore();
    const [error, setError] = useState<string | null>(null);
    const [needs2fa, setNeeds2fa] = useState(false);
    const [pendingToken, setPendingToken] = useState('');
    const [totpCode, setTotpCode] = useState('');
    const [verifying, setVerifying] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);
    const processedRef = useRef(false);

    useEffect(() => {
        // Guard against React StrictMode double-execution:
        // First run processes the hash and clears it, second run would find
        // no hash and briefly flash an error before redirecting.
        if (processedRef.current) return;

        const hash = window.location.hash.substring(1); // remove #
        const params = new URLSearchParams(hash);
        const accessToken = params.get('access_token');
        const requires2fa = params.get('requires_2fa') === 'true';

        if (!accessToken) {
            // Check if tokens were already stored (StrictMode re-run)
            if (localStorage.getItem('access_token')) {
                checkAuth().then(() => router.push('/dashboard'));
                return;
            }
            setError('No access token received from SSO provider.');
            return;
        }

        processedRef.current = true;

        // Clear the hash from URL
        window.history.replaceState(null, '', '/sso/callback');

        if (requires2fa) {
            // Show 2FA input — don't store the pending token in localStorage
            setPendingToken(accessToken);
            setNeeds2fa(true);
            return;
        }

        // Normal flow — store the access token only. The refresh token rides
        // an HttpOnly cookie set by the SAML ACS response (GHSA-gv65-p25x-qrqj).
        localStorage.setItem('access_token', accessToken);

        // Set session cookie for Next.js middleware
        document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';

        checkAuth().then(() => {
            router.push('/dashboard');
        });
    }, [checkAuth, router]);

    // Auto-focus the TOTP input when 2FA is shown
    useEffect(() => {
        if (needs2fa && inputRef.current) {
            inputRef.current.focus();
        }
    }, [needs2fa]);

    const handleVerify2fa = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!totpCode || totpCode.length !== 6) return;

        setVerifying(true);
        setError(null);

        try {
            await verifySsoTotp(totpCode, pendingToken);
            router.push('/dashboard');
        } catch (err: any) {
            const detail = err?.response?.data?.detail || 'Invalid code. Please try again.';
            setError(detail);
            setTotpCode('');
            setVerifying(false);
            inputRef.current?.focus();
        }
    };

    // 2FA challenge screen
    if (needs2fa) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#0a0f1a]">
                <div className="bg-[#1e293b] border border-zinc-700/50 rounded-xl p-8 max-w-sm w-full">
                    <div className="text-center mb-6">
                        <div className="w-12 h-12 bg-blue-500/10 rounded-full flex items-center justify-center mx-auto mb-3">
                            <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                            </svg>
                        </div>
                        <h1 className="text-lg font-bold text-zinc-100">Two-Factor Authentication</h1>
                        <p className="text-zinc-400 text-sm mt-1">
                            Enter the 6-digit code from your authenticator app
                        </p>
                    </div>

                    <form onSubmit={handleVerify2fa} className="space-y-4">
                        <input
                            ref={inputRef}
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            maxLength={6}
                            value={totpCode}
                            onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                            placeholder="000000"
                            className="w-full text-center text-2xl tracking-[0.5em] font-mono py-3 px-4
                                       bg-[#0f1729] border border-zinc-700 rounded-lg text-zinc-100
                                       focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-hidden
                                       placeholder:text-zinc-600"
                            autoComplete="one-time-code"
                            disabled={verifying}
                        />

                        {error && (
                            <p className="text-red-400 text-sm text-center">{error}</p>
                        )}

                        <button
                            type="submit"
                            disabled={totpCode.length !== 6 || verifying}
                            className="w-full py-2.5 rounded-lg font-medium text-sm
                                       bg-blue-600 hover:bg-blue-500 text-white
                                       disabled:opacity-50 disabled:cursor-not-allowed
                                       transition-colors"
                        >
                            {verifying ? 'Verifying...' : 'Verify'}
                        </button>
                    </form>

                    <div className="mt-4 text-center">
                        <a href="/login" className="text-zinc-500 hover:text-zinc-400 text-xs">
                            Cancel and return to login
                        </a>
                    </div>
                </div>
            </div>
        );
    }

    // Error screen
    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#0a0f1a]">
                <div className="bg-[#1e293b] border border-red-500/30 rounded-xl p-8 max-w-md text-center">
                    <h1 className="text-xl font-bold text-red-400 mb-2">SSO Authentication Failed</h1>
                    <p className="text-zinc-400 text-sm mb-4">{error}</p>
                    <a href="/login" className="text-blue-400 hover:text-blue-300 text-sm underline">
                        Return to login
                    </a>
                </div>
            </div>
        );
    }

    // Loading spinner (default)
    return (
        <div className="min-h-screen flex items-center justify-center bg-[#0a0f1a]">
            <div className="text-center">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500 mx-auto mb-4" />
                <p className="text-zinc-400 text-sm">Completing sign-in...</p>
            </div>
        </div>
    );
}

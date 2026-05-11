'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import api from '@/lib/api';
import { KeyRound, ArrowLeft } from 'lucide-react';

/* ── reused components ── */
function GridBackground() {
    return (
        <div className="absolute inset-0 pointer-events-none" style={{
            backgroundImage: `linear-gradient(to right, rgba(200,30,30,0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(200,30,30,0.04) 1px, transparent 1px)`,
            backgroundSize: '60px 60px'
        }} />
    );
}

function NoiseOverlay() {
    return (
        <div className="absolute inset-0 pointer-events-none opacity-[0.03] z-10" style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }} />
    );
}

function ProgressStrip() {
    return (
        <div className="h-[2px] w-full bg-white/5 overflow-hidden rounded-full">
            <div className="h-full rounded-full transition-all duration-100" style={{
                width: `100%`,
                background: 'linear-gradient(90deg, #ff0000, #ff4444, #ff0000)',
                boxShadow: '0 0 8px rgba(255,0,0,0.5)',
            }} />
        </div>
    );
}

function StatusLine({ text, variant = 'idle' }: { text: string; variant?: 'idle' | 'active' | 'success' | 'error' }) {
    const colors = { idle: '#ff4444', active: '#ff8800', success: '#22c55e', error: '#ff0000' };
    return (
        <div className="flex items-center gap-2 px-4 py-2 bg-black/20">
            <div className={`w-1.5 h-1.5 rounded-full ${variant === 'active' ? 'animate-pulse' : ''}`}
                style={{ backgroundColor: colors[variant], boxShadow: `0 0 6px ${colors[variant]}` }} />
            <span className="text-[10px] font-mono text-white/30 uppercase tracking-wider">{text}</span>
        </div>
    );
}

export default function ResetPasswordPage() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const token = searchParams.get('token');

    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [successMsg, setSuccessMsg] = useState('');
    const [errorMsg, setErrorMsg] = useState('');

    useEffect(() => {
        if (!token) {
            setErrorMsg('Invalid or missing reset token. Please request a new password reset link.');
        }
    }, [token]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!token) return;

        if (password.length < 8) {
            setErrorMsg('Password must be at least 8 characters long');
            return;
        }

        if (password !== confirmPassword) {
            setErrorMsg('Passwords do not match');
            return;
        }

        setIsLoading(true);
        setErrorMsg('');

        try {
            const { data } = await api.post('/auth/reset-password', {
                token,
                new_password: password
            });
            setSuccessMsg(data.message);
            setTimeout(() => {
                router.push('/login');
            }, 3000);
        } catch (err: any) {
            setErrorMsg(err.response?.data?.detail || 'Failed to reset password. The link may have expired.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#060608]">
            <GridBackground />
            <NoiseOverlay />
            <div className="absolute w-[600px] h-[600px] rounded-full bg-red-900/10 blur-[120px] pointer-events-none" />

            <div className="relative z-20 w-full max-w-[420px] mx-4">
                <div className="rounded-xl border border-white/[0.08] bg-[#0c0c10]/80 backdrop-blur-xl shadow-[0_0_60px_rgba(255,0,0,0.08)] overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-black/20">
                        <div className="flex items-center gap-2">
                            <KeyRound className="w-3.5 h-3.5 text-red-500" />
                            <span className="text-[11px] font-mono font-semibold text-white/50 uppercase tracking-widest">
                                Update Password
                            </span>
                        </div>
                        <div className="flex gap-1.5">
                            <div className="w-2.5 h-2.5 rounded-full bg-white/10" />
                            <div className="w-2.5 h-2.5 rounded-full bg-white/10" />
                            <div className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
                        </div>
                    </div>

                    <div className="px-6 pt-6 pb-2 text-center">
                        <h1 className="text-xl font-bold text-white tracking-tight">Set New Password</h1>
                        <p className="text-[11px] font-mono text-white/40 mt-1.5 leading-relaxed">
                            Please enter a strong new password for your account.
                        </p>
                    </div>

                    <div className="px-6 py-2">
                        <ProgressStrip />
                    </div>

                    <div className="px-6 pb-6 pt-2">
                        {errorMsg && (
                            <div className="mb-4 px-3 py-2.5 bg-red-500/10 border border-red-500/20 rounded-lg">
                                <p className="text-xs font-mono text-red-400 text-center">{errorMsg}</p>
                            </div>
                        )}
                        {successMsg ? (
                            <div className="space-y-6">
                                <div className="px-3 py-4 bg-green-500/10 border border-green-500/20 rounded-lg text-center">
                                    <p className="text-sm font-mono text-green-400 leading-relaxed mb-2">{successMsg}</p>
                                    <p className="text-xs font-mono text-white/40">Redirecting to login...</p>
                                </div>
                                <Link
                                    href="/login"
                                    className="w-full flex items-center justify-center px-4 py-3 text-sm font-mono font-bold uppercase tracking-widest text-white rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 transition-colors"
                                >
                                    Proceed to Login
                                </Link>
                            </div>
                        ) : (
                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div className="space-y-1.5">
                                    <label className="text-[11px] font-mono font-semibold text-red-400/80 uppercase tracking-widest">
                                        New Password
                                    </label>
                                    <input
                                        type="password"
                                        required
                                        minLength={8}
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="••••••••"
                                        className="w-full px-3 py-2.5 text-sm font-mono text-white bg-white/[0.03] border border-white/10 rounded-lg outline-none focus:border-red-500/50 focus:bg-white/[0.05] focus:shadow-[0_0_12px_rgba(255,0,0,0.1)] transition-all duration-300 placeholder:text-white/15"
                                    />
                                </div>

                                <div className="space-y-1.5">
                                    <label className="text-[11px] font-mono font-semibold text-red-400/80 uppercase tracking-widest">
                                        Confirm Password
                                    </label>
                                    <input
                                        type="password"
                                        required
                                        minLength={8}
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                        placeholder="••••••••"
                                        className="w-full px-3 py-2.5 text-sm font-mono text-white bg-white/[0.03] border border-white/10 rounded-lg outline-none focus:border-red-500/50 focus:bg-white/[0.05] focus:shadow-[0_0_12px_rgba(255,0,0,0.1)] transition-all duration-300 placeholder:text-white/15"
                                    />
                                </div>

                                <button
                                    type="submit"
                                    disabled={isLoading || !token || !password || !confirmPassword}
                                    className="group relative w-full px-4 py-3 pb-3 mt-2 text-sm font-mono font-bold uppercase tracking-widest text-white rounded-lg overflow-hidden transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    <div className="absolute inset-0 bg-gradient-to-r from-red-700 via-red-500 to-red-700 hover:from-red-600 hover:to-red-600 transition-colors" />
                                    <div className="absolute inset-0 rounded-lg border border-white/10" />
                                    <span className="relative z-10 flex items-center justify-center gap-2">
                                        {isLoading ? 'Processing...' : 'Reset Password'}
                                    </span>
                                </button>
                                
                                <div className="pt-2 mt-2 mx-auto text-center">
                                    <Link href="/login" className="inline-flex items-center gap-1.5 text-[11px] font-mono text-white/30 hover:text-white/60 transition-colors">
                                        Cancel
                                    </Link>
                                </div>
                            </form>
                        )}
                    </div>

                    <StatusLine text={successMsg ? 'Password established' : isLoading ? 'Updating...' : errorMsg ? 'Action required' : 'Awaiting input'} variant={successMsg ? 'success' : isLoading ? 'active' : errorMsg ? 'error' : 'idle'} />
                </div>
            </div>
        </div>
    );
}

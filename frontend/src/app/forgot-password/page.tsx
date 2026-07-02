'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import api, { apiErrorMessage } from '@/lib/api';
import { Mail, ArrowLeft, Send } from 'lucide-react';

/* ── reused components from login page ── */
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
                animation: 'shimmer 2s infinite linear'
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

export default function ForgotPasswordPage() {
    const [email, setEmail] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [successMsg, setSuccessMsg] = useState('');
    const [errorMsg, setErrorMsg] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setErrorMsg('');
        setSuccessMsg('');

        try {
            const { data } = await api.post('/auth/forgot-password', { email });
            setSuccessMsg(data.message);
            setEmail('');
        } catch (err: any) {
            setErrorMsg(apiErrorMessage(err, 'An unexpected error occurred'));
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
                    {/* Title bar */}
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-black/20">
                        <div className="flex items-center gap-2">
                            <Mail className="w-3.5 h-3.5 text-red-500" />
                            <span className="text-[11px] font-mono font-semibold text-white/50 uppercase tracking-widest">
                                Password Recovery
                            </span>
                        </div>
                        <div className="flex gap-1.5">
                            <div className="w-2.5 h-2.5 rounded-full bg-white/10" />
                            <div className="w-2.5 h-2.5 rounded-full bg-white/10" />
                            <div className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
                        </div>
                    </div>

                    <div className="px-6 pt-6 pb-2 text-center">
                        <h1 className="text-xl font-bold text-white tracking-tight">Forgot Password</h1>
                        <p className="text-[11px] font-mono text-white/40 mt-1.5 leading-relaxed">
                            Enter your email address and we'll send you a link to reset your password.
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
                        {successMsg && (
                            <div className="mb-4 px-3 py-3 bg-green-500/10 border border-green-500/20 rounded-lg">
                                <p className="text-xs font-mono text-green-400 text-center leading-relaxed">{successMsg}</p>
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div className="space-y-1.5">
                                <label className="text-[11px] font-mono font-semibold text-red-400/80 uppercase tracking-widest">
                                    Email Address
                                </label>
                                <input
                                    type="email"
                                    required
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="operator@redwire.local"
                                    className="w-full px-3 py-2.5 text-sm font-mono text-white bg-white/[0.03] border border-white/10 rounded-lg outline-none focus:border-red-500/50 focus:bg-white/[0.05] focus:shadow-[0_0_12px_rgba(255,0,0,0.1)] transition-all duration-300 placeholder:text-white/15"
                                />
                            </div>

                            <button
                                type="submit"
                                disabled={isLoading || !email}
                                className="group relative w-full px-4 py-3 pb-3 top-2 text-sm font-mono font-bold uppercase tracking-widest text-white rounded-lg overflow-hidden transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <div className="absolute inset-0 bg-gradient-to-r from-red-700 via-red-500 to-red-700 hover:from-red-600 hover:to-red-600 transition-colors" />
                                <div className="absolute inset-0 rounded-lg border border-white/10" />
                                <span className="relative z-10 flex items-center justify-center gap-2">
                                    {isLoading ? 'Transmitting...' : 'Send Reset Link'}
                                </span>
                            </button>

                            <div className="pt-4 mt-2 border-t border-white/5 mx-auto text-center">
                                <Link href="/login" className="inline-flex items-center gap-1.5 text-[11px] font-mono text-white/30 hover:text-white/60 transition-colors">
                                    <ArrowLeft className="w-3 h-3" /> Back to Login
                                </Link>
                            </div>
                        </form>
                    </div>

                    <StatusLine text={successMsg ? 'Email dispatched' : isLoading ? 'Contacting server...' : 'Awaiting input'} variant={successMsg ? 'success' : isLoading ? 'active' : 'idle'} />
                </div>
            </div>
        </div>
    );
}

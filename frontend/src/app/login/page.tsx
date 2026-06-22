/**
 * login/page.tsx — Login Page
 *
 * Full-screen authentication page with animated grid background
 * and particle effects. Supports three auth flows:
 *  - Local username/password with optional TOTP 2FA challenge
 *  - LDAP (uses the same form, backend routes to LDAP)
 *  - SAML SSO redirect (button shown when SAML provider is enabled)
 *
 * Fetches available auth providers and optional splash/banner config
 * from the backend on mount. Includes helper components: GridBackground,
 * NoiseOverlay, ProgressStrip, GlowButton, StatusLine, StyledInput.
 */
'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/stores/auth-store';
import { Shield, ArrowLeft, LogIn, Zap, AlertTriangle } from 'lucide-react';

interface AuthProviders {
    local: boolean;
    ldap: boolean;
    saml: boolean;
    saml_login_url?: string | null;
}

/* ── animated grid background ── */
function GridBackground() {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let animId: number;
        let time = 0;

        const resize = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };
        resize();
        window.addEventListener('resize', resize);

        // Floating particles
        const particles: { x: number; y: number; vx: number; vy: number; size: number; alpha: number }[] = [];
        for (let i = 0; i < 60; i++) {
            particles.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                vx: (Math.random() - 0.5) * 0.3,
                vy: (Math.random() - 0.5) * 0.3,
                size: Math.random() * 2 + 0.5,
                alpha: Math.random() * 0.5 + 0.1,
            });
        }

        const draw = () => {
            time += 0.005;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Grid lines
            const gridSize = 60;
            ctx.strokeStyle = 'rgba(200, 30, 30, 0.04)';
            ctx.lineWidth = 1;
            for (let x = 0; x < canvas.width; x += gridSize) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, canvas.height);
                ctx.stroke();
            }
            for (let y = 0; y < canvas.height; y += gridSize) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvas.width, y);
                ctx.stroke();
            }

            // Glowing intersections that pulse
            for (let x = 0; x < canvas.width; x += gridSize) {
                for (let y = 0; y < canvas.height; y += gridSize) {
                    const dist = Math.sin(time + x * 0.01 + y * 0.01) * 0.5 + 0.5;
                    if (dist > 0.7) {
                        ctx.beginPath();
                        ctx.arc(x, y, 1.5, 0, Math.PI * 2);
                        ctx.fillStyle = `rgba(255, 50, 50, ${dist * 0.3})`;
                        ctx.fill();
                    }
                }
            }

            // Particles
            for (const p of particles) {
                p.x += p.vx;
                p.y += p.vy;
                if (p.x < 0) p.x = canvas.width;
                if (p.x > canvas.width) p.x = 0;
                if (p.y < 0) p.y = canvas.height;
                if (p.y > canvas.height) p.y = 0;

                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(255, 60, 60, ${p.alpha})`;
                ctx.fill();
            }

            // Connect nearby particles
            for (let i = 0; i < particles.length; i++) {
                for (let j = i + 1; j < particles.length; j++) {
                    const dx = particles[i].x - particles[j].x;
                    const dy = particles[i].y - particles[j].y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < 120) {
                        ctx.beginPath();
                        ctx.moveTo(particles[i].x, particles[i].y);
                        ctx.lineTo(particles[j].x, particles[j].y);
                        ctx.strokeStyle = `rgba(255, 40, 40, ${0.08 * (1 - dist / 120)})`;
                        ctx.stroke();
                    }
                }
            }

            animId = requestAnimationFrame(draw);
        };

        draw();
        return () => {
            cancelAnimationFrame(animId);
            window.removeEventListener('resize', resize);
        };
    }, []);

    return <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />;
}

/* ── subtle noise texture ── */
function NoiseOverlay() {
    return (
        <div
            className="absolute inset-0 pointer-events-none opacity-[0.03] z-10"
            style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
                backgroundRepeat: 'repeat',
            }}
        />
    );
}

/* ── progress bar ── */
function ProgressStrip() {
    const [progress, setProgress] = useState(0);
    useEffect(() => {
        const interval = setInterval(() => {
            setProgress(p => (p >= 100 ? 0 : p + Math.random() * 2));
        }, 80);
        return () => clearInterval(interval);
    }, []);
    return (
        <div className="h-[2px] w-full bg-white/5 overflow-hidden rounded-full">
            <div
                className="h-full rounded-full transition-all duration-100"
                style={{
                    width: `${progress}%`,
                    background: 'linear-gradient(90deg, #ff0000, #ff4444, #ff0000)',
                    boxShadow: '0 0 8px rgba(255,0,0,0.5)',
                }}
            />
        </div>
    );
}

/* ── glowing button ── */
function GlowButton({ children, variant = 'primary', className = '', ...props }: {
    children: React.ReactNode;
    variant?: 'primary' | 'ghost';
    className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
    if (variant === 'ghost') {
        return (
            <button
                {...props}
                className={`w-full flex items-center justify-center gap-1.5 px-4 py-2.5 text-sm font-mono font-semibold uppercase tracking-wider text-white/50 bg-transparent border border-white/10 rounded-lg hover:border-white/20 hover:text-white/70 transition-all duration-300 ${className}`}
            >
                {children}
            </button>
        );
    }
    return (
        <button
            {...props}
            className={`group relative w-full px-4 py-3 text-sm font-mono font-bold uppercase tracking-widest text-white rounded-lg overflow-hidden transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
        >
            {/* Animated gradient background */}
            <div className="absolute inset-0 bg-gradient-to-r from-red-700 via-red-500 to-red-700 bg-[length:200%_100%] animate-[shimmer_3s_linear_infinite] group-hover:from-red-600 group-hover:via-red-400 group-hover:to-red-600 transition-colors" />
            {/* Glow effect */}
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300" style={{ boxShadow: 'inset 0 0 20px rgba(255,100,100,0.3)' }} />
            {/* Border highlight */}
            <div className="absolute inset-0 rounded-lg border border-white/10 group-hover:border-white/20" />
            <span className="relative z-10 flex items-center justify-center gap-2">
                {children}
            </span>
        </button>
    );
}

/* ── status indicator ── */
function StatusLine({ text, variant = 'idle' }: { text: string; variant?: 'idle' | 'active' | 'error' }) {
    const colors = { idle: '#ff4444', active: '#ff8800', error: '#ff0000' };
    return (
        <div className="flex items-center gap-2 px-4 py-2">
            <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: colors[variant], boxShadow: `0 0 6px ${colors[variant]}` }} />
            <span className="text-[10px] font-mono text-white/30 uppercase tracking-wider">
                {text}
            </span>
        </div>
    );
}

/* ── styled input ── */
function StyledInput({ id, label, ...props }: { id: string; label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
    return (
        <div className="space-y-1.5">
            <label htmlFor={id} className="text-[11px] font-mono font-semibold text-red-400/80 uppercase tracking-widest">
                {label}
            </label>
            <input
                id={id}
                {...props}
                className="w-full px-3 py-2.5 text-sm font-mono text-white bg-white/[0.03] border border-white/10 rounded-lg outline-none focus:border-red-500/50 focus:bg-white/[0.05] focus:shadow-[0_0_12px_rgba(255,0,0,0.1)] transition-all duration-300 placeholder:text-white/15"
            />
        </div>
    );
}

/* ═══════ MAIN PAGE ═══════ */
export default function LoginPage() {
    const router = useRouter();
    const { login, verifyTotp, cancel2fa, requires2fa } = useAuthStore();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [totpCode, setTotpCode] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const totpInputRef = useRef<HTMLInputElement>(null);
    const [providers, setProviders] = useState<AuthProviders | null>(null);
    const [statusText, setStatusText] = useState('Awaiting credentials');
    const [splashConfig, setSplashConfig] = useState<{ enabled: boolean; title: string; message: string } | null>(null);
    const [splashAcknowledged, setSplashAcknowledged] = useState(() => {
        if (typeof window !== 'undefined') {
            return sessionStorage.getItem('splash_acknowledged') === 'true';
        }
        return false;
    });

    const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    useEffect(() => {
        fetch(`${API}/auth/providers`)
            .then((r) => r.json())
            .then((data) => setProviders(data))
            .catch(() => { });
        fetch(`${API}/auth/splash`)
            .then((r) => r.json())
            .then((data) => setSplashConfig(data))
            .catch(() => { });
    }, [API]);

    useEffect(() => {
        if (requires2fa && totpInputRef.current) {
            totpInputRef.current.focus();
            setStatusText('2FA challenge — enter token');
        }
    }, [requires2fa]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);
        setStatusText('Establishing connection...');

        try {
            await login(username, password);
            if (!useAuthStore.getState().requires2fa) {
                setStatusText('Access granted');
                window.location.href = '/dashboard';
            }
        } catch (err: any) {
            const msg = err.response?.data?.detail || 'Authentication failed.';
            setError(msg);
            setPassword('');
            setStatusText('Connection refused');
        } finally {
            setIsLoading(false);
        }
    };

    const handleTotpSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);
        setStatusText('Verifying token...');

        try {
            await verifyTotp(totpCode);
            setStatusText('Verified');
            window.location.href = '/dashboard';
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Invalid token.');
            setTotpCode('');
            setStatusText('Token rejected');
        } finally {
            setIsLoading(false);
        }
    };

    const handleBack = () => {
        cancel2fa();
        setTotpCode('');
        setError('');
        setStatusText('Awaiting credentials');
    };

    const showSplash = splashConfig?.enabled && !splashAcknowledged;

    return (
        <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#060608]">
            {/* Background */}
            <GridBackground />
            <NoiseOverlay />

            {/* Splash Screen Overlay */}
            {showSplash && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
                    <div className="w-full max-w-[600px] rounded-xl border-2 border-amber-500/60 bg-[#0c0c10]/95 shadow-[0_0_40px_rgba(245,158,11,0.15)] overflow-hidden">
                        {/* Warning header strip */}
                        <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-3 flex items-center gap-3">
                            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
                            <span className="text-xs font-mono font-bold text-amber-400 uppercase tracking-widest">
                                {splashConfig.title || 'NOTICE'}
                            </span>
                            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 ml-auto" />
                        </div>

                        {/* Message body */}
                        <div className="px-6 py-6">
                            <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-mono">
                                {splashConfig.message}
                            </div>
                        </div>

                        {/* Acknowledge button */}
                        <div className="px-6 pb-6">
                            <button
                                onClick={() => {
                                    sessionStorage.setItem('splash_acknowledged', 'true');
                                    setSplashAcknowledged(true);
                                }}
                                className="w-full px-4 py-3 text-sm font-mono font-bold uppercase tracking-widest text-white rounded-lg bg-amber-600 hover:bg-amber-500 transition-colors duration-200 border border-amber-500/50"
                            >
                                I Acknowledge
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Radial glow behind window */}
            <div className="absolute w-[600px] h-[600px] rounded-full bg-red-900/20 blur-[120px] pointer-events-none" />

            {/* Main window */}
            <div className="relative z-20 w-full max-w-[420px] mx-4">
                <div className="rounded-xl border border-white/[0.08] bg-[#0c0c10]/80 backdrop-blur-xl shadow-[0_0_60px_rgba(255,0,0,0.08)] overflow-hidden">
                    {/* Title bar */}
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
                        <div className="flex items-center gap-2">
                            <Zap className="w-3.5 h-3.5 text-red-500" />
                            <span className="text-[11px] font-mono font-semibold text-white/50 uppercase tracking-widest">
                                {requires2fa ? 'Verification' : 'Authentication'}
                            </span>
                        </div>
                        <div className="flex gap-1.5">
                            <div className="w-2.5 h-2.5 rounded-full bg-white/10 hover:bg-yellow-500/60 transition-colors" />
                            <div className="w-2.5 h-2.5 rounded-full bg-white/10 hover:bg-green-500/60 transition-colors" />
                            <div className="w-2.5 h-2.5 rounded-full bg-red-500/40 hover:bg-red-500/80 transition-colors" />
                        </div>
                    </div>

                    {/* Header */}
                    <div className="px-6 pt-6 pb-2 text-center">
                        <div className="flex justify-center mb-4">
                            <img src="/redwire.png" alt="RedWire" className="h-10 w-auto drop-shadow-[0_0_12px_rgba(255,0,0,0.4)]" />
                        </div>
                        <h1 className="text-lg font-bold text-white tracking-tight">
                            {requires2fa ? 'Two-Factor Auth' : 'Secure Login'}
                        </h1>
                        <p className="text-[11px] font-mono text-white/25 mt-1">
                            {requires2fa ? 'Enter your authenticator code' : 'Red Team Operations Platform'}
                        </p>
                    </div>

                    <div className="px-6 py-1">
                        <ProgressStrip />
                    </div>

                    {/* Form area */}
                    <div className="px-6 pt-3 pb-2">
                        {error && (
                            <div className="mb-4 px-3 py-2.5 bg-red-500/10 border border-red-500/20 rounded-lg">
                                <p className="text-xs font-mono text-red-400">
                                    {error}
                                </p>
                            </div>
                        )}

                        {requires2fa ? (
                            <form onSubmit={handleTotpSubmit} className="space-y-4">
                                <div className="flex justify-center mb-2">
                                    <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                                        <Shield className="h-6 w-6 text-red-400" />
                                    </div>
                                </div>
                                <div className="space-y-1.5">
                                    <label className="text-[11px] font-mono font-semibold text-red-400/80 uppercase tracking-widest">
                                        OTP Token or Recovery Code
                                    </label>
                                    <input
                                        ref={totpInputRef}
                                        type="text"
                                        autoComplete="one-time-code"
                                        placeholder="000000  or  XXXX-XXXX"
                                        value={totpCode}
                                        // Allow both 6-digit TOTP and 8-char alnum recovery
                                        // codes (with optional hyphen / spaces). Server
                                        // dispatches by shape — see
                                        // backend/auth/recovery_codes.py::looks_like_recovery_code.
                                        // GHSA-vm6w-9wm5-q367 follow-up.
                                        onChange={(e) => setTotpCode(e.target.value.slice(0, 16))}
                                        maxLength={16}
                                        required
                                        className="w-full px-3 py-3 text-xl font-mono text-white bg-white/[0.03] border border-white/10 rounded-lg outline-none text-center tracking-[0.25em] focus:border-red-500/50 focus:shadow-[0_0_12px_rgba(255,0,0,0.15)] transition-all placeholder:text-white/15"
                                    />
                                    <p className="text-[10px] text-slate-500 text-center">
                                        Lost your authenticator? Use one of the recovery
                                        codes you saved at enrollment.
                                    </p>
                                </div>
                                <div className="space-y-2">
                                    <GlowButton type="submit" disabled={isLoading || totpCode.replace(/[-\s]/g, '').length < 6}>
                                        {isLoading ? 'Verifying...' : 'Verify'}
                                    </GlowButton>
                                    <GlowButton type="button" variant="ghost" onClick={handleBack}>
                                        <ArrowLeft className="h-3.5 w-3.5 mr-1" /> Back
                                    </GlowButton>
                                </div>
                            </form>
                        ) : (
                            <form onSubmit={handleSubmit} className="space-y-4">
                                <StyledInput
                                    id="username"
                                    label="Username"
                                    type="text"
                                    placeholder="operator"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    required
                                />
                                <StyledInput
                                    id="password"
                                    label="Password"
                                    type="password"
                                    placeholder="••••••••"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                />
                                <div className="flex justify-end -mt-2">
                                    <Link href="/forgot-password" className="text-[10px] font-mono text-white/30 hover:text-white/60 transition-colors">
                                        Forgot password?
                                    </Link>
                                </div>
                                <div className="pt-1 space-y-3">
                                    <GlowButton type="submit" disabled={isLoading}>
                                        <Zap className="w-3.5 h-3.5" />
                                        {isLoading ? 'Connecting...' : 'Connect'}
                                    </GlowButton>

                                    {providers?.saml && providers.saml_login_url && (
                                        <>
                                            <div className="flex items-center gap-3">
                                                <div className="flex-1 h-px bg-white/[0.06]" />
                                                <span className="text-[9px] font-mono text-white/20 uppercase">or</span>
                                                <div className="flex-1 h-px bg-white/[0.06]" />
                                            </div>
                                            <a
                                                href={providers.saml_login_url}
                                                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-mono font-semibold uppercase tracking-wider text-white/60 bg-white/[0.03] border border-white/10 rounded-lg hover:border-white/20 hover:text-white/80 hover:bg-white/[0.05] transition-all duration-300"
                                            >
                                                <LogIn className="h-3.5 w-3.5" />
                                                SSO Login
                                            </a>
                                        </>
                                    )}
                                </div>

                                <div className="text-center pt-1">
                                    <p className="text-[11px] font-mono text-white/25">
                                        No access?{' '}
                                        <Link href="/register" className="text-red-400/70 hover:text-red-400 underline underline-offset-2 transition-colors">
                                            Request credentials
                                        </Link>
                                    </p>
                                </div>
                            </form>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="px-6 pb-1">
                        <div className="h-px bg-white/[0.04]" />
                    </div>
                    <StatusLine text={statusText} variant={error ? 'error' : isLoading ? 'active' : 'idle'} />
                </div>

                {/* Branding below window */}
                <p className="text-center text-[9px] font-mono text-white/10 mt-4 tracking-widest uppercase">
                    RedWire Security Platform — v2.0
                </p>
            </div>

            {/* Shimmer animation keyframe */}
            <style jsx global>{`
                @keyframes shimmer {
                    0% { background-position: 200% 0; }
                    100% { background-position: -200% 0; }
                }
            `}</style>
        </div>
    );
}

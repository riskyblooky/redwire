/**
 * register/page.tsx — Registration Page
 *
 * New operator registration form requiring a valid invite/registration
 * code. Uses the same animated grid background and visual style as the
 * login page. Fields: invite code, username, full name, email, password.
 * On success, redirects to /login with a toast notification.
 */
'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Ticket, Zap } from 'lucide-react';
import { toast } from 'sonner';

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

/* ── noise overlay ── */
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

/* ── progress strip ── */
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

/* ── glow button ── */
function GlowButton({ children, ...props }: { children: React.ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
    return (
        <button
            {...props}
            className="group relative w-full px-4 py-3 text-sm font-mono font-bold uppercase tracking-widest text-white rounded-lg overflow-hidden transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
        >
            <div className="absolute inset-0 bg-gradient-to-r from-red-700 via-red-500 to-red-700 bg-[length:200%_100%] animate-[shimmer_3s_linear_infinite] group-hover:from-red-600 group-hover:via-red-400 group-hover:to-red-600" />
            <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300" style={{ boxShadow: 'inset 0 0 20px rgba(255,100,100,0.3)' }} />
            <div className="absolute inset-0 rounded-lg border border-white/10 group-hover:border-white/20" />
            <span className="relative z-10 flex items-center justify-center gap-2">{children}</span>
        </button>
    );
}

/* ── styled input ── */
function StyledInput({ id, label, accent, className: _cn, ...props }: { id: string; label: string; accent?: boolean } & React.InputHTMLAttributes<HTMLInputElement>) {
    return (
        <div className="space-y-1.5">
            <label htmlFor={id} className={`text-[11px] font-mono font-semibold uppercase tracking-widest ${accent ? 'text-red-400' : 'text-red-400/80'} flex items-center gap-1.5`}>
                {accent && <Ticket className="h-3 w-3" />}
                {label}
            </label>
            <input
                id={id}
                {...props}
                className={`w-full px-3 py-2.5 text-sm font-mono text-white bg-white/[0.03] border border-white/10 rounded-lg outline-none focus:border-red-500/50 focus:bg-white/[0.05] focus:shadow-[0_0_12px_rgba(255,0,0,0.1)] transition-all duration-300 placeholder:text-white/15 ${_cn || ''}`}
            />
        </div>
    );
}

/* ── status line ── */
function StatusLine({ text }: { text: string }) {
    return (
        <div className="flex items-center gap-2 px-4 py-2">
            <div className="w-1.5 h-1.5 rounded-full bg-red-500/60 animate-pulse" style={{ boxShadow: '0 0 6px rgba(255,50,50,0.5)' }} />
            <span className="text-[10px] font-mono text-white/30 uppercase tracking-wider">{text}</span>
        </div>
    );
}

/* ═══════ MAIN PAGE ═══════ */
export default function RegisterPage() {
    const router = useRouter();
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        password: '',
        full_name: '',
        registration_code: ''
    });
    const [isLoading, setIsLoading] = useState(false);
    const [statusText, setStatusText] = useState('Registration module loaded');

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setFormData(prev => ({ ...prev, [e.target.id]: e.target.value }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setStatusText('Validating registration code...');

        try {
            await api.post('/auth/register', {
                ...formData,
                registration_code: formData.registration_code.toUpperCase()
            });
            setStatusText('Registration complete');
            toast.success('Registration successful! Please sign in.');
            router.push('/login');
        } catch (err: any) {
            const detail = err.response?.data?.detail;
            let message = 'Registration failed';
            if (typeof detail === 'string') {
                message = detail;
            } else if (Array.isArray(detail)) {
                message = detail.map((d: any) => {
                    const field = d.loc?.slice(-1)[0];
                    const msg = d.msg?.replace(/^Value error, /i, '').replace(/^String /i, '');
                    return field ? `${field}: ${msg}` : msg;
                }).join(', ');
            }
            toast.error(message);
            setStatusText('Registration rejected');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#060608]">
            <GridBackground />
            <NoiseOverlay />

            {/* Radial glow */}
            <div className="absolute w-[600px] h-[600px] rounded-full bg-red-900/20 blur-[120px] pointer-events-none" />

            {/* Main window */}
            <div className="relative z-20 w-full max-w-[420px] mx-4">
                <div className="rounded-xl border border-white/[0.08] bg-[#0c0c10]/80 backdrop-blur-xl shadow-[0_0_60px_rgba(255,0,0,0.08)] overflow-hidden">
                    {/* Title bar */}
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
                        <div className="flex items-center gap-2">
                            <Zap className="w-3.5 h-3.5 text-red-500" />
                            <span className="text-[11px] font-mono font-semibold text-white/50 uppercase tracking-widest">
                                Registration
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
                            New Operator
                        </h1>
                        <p className="text-[11px] font-mono text-white/25 mt-1">
                            Valid invite code required for access
                        </p>
                    </div>

                    <div className="px-6 py-1">
                        <ProgressStrip />
                    </div>

                    {/* Form */}
                    <form onSubmit={handleSubmit} className="px-6 pt-3 pb-2 space-y-3">
                        {/* Serial / Invite Code */}
                        <StyledInput
                            id="registration_code"
                            label="Serial / Invite Code"
                            accent
                            type="text"
                            placeholder="XXXX-XXXX-XXXX"
                            value={formData.registration_code}
                            onChange={handleChange}
                            required
                            className="text-center uppercase tracking-[0.3em] text-red-400 placeholder:text-red-900/40"
                        />
                        <p className="text-[9px] font-mono text-white/20 text-center -mt-1">
                            Contact admin for a valid registration key
                        </p>

                        {/* Separator */}
                        <div className="flex items-center gap-3 py-0.5">
                            <div className="flex-1 h-px bg-white/[0.04]" />
                            <span className="text-[9px] font-mono text-white/15 uppercase tracking-widest">Operator Info</span>
                            <div className="flex-1 h-px bg-white/[0.04]" />
                        </div>

                        {/* Two-column row */}
                        <div className="grid grid-cols-2 gap-3">
                            <StyledInput
                                id="username"
                                label="Handle"
                                type="text"
                                placeholder="operator"
                                value={formData.username}
                                onChange={handleChange}
                                required
                            />
                            <StyledInput
                                id="full_name"
                                label="Full Name"
                                type="text"
                                placeholder="John Doe"
                                value={formData.full_name}
                                onChange={handleChange}
                            />
                        </div>

                        <StyledInput
                            id="email"
                            label="Email"
                            type="email"
                            placeholder="operator@example.com"
                            value={formData.email}
                            onChange={handleChange}
                            required
                        />

                        <StyledInput
                            id="password"
                            label="Password"
                            type="password"
                            placeholder="••••••••"
                            value={formData.password}
                            onChange={handleChange}
                            required
                        />

                        <div className="pt-1">
                            <GlowButton type="submit" disabled={isLoading}>
                                <Zap className="w-3.5 h-3.5" />
                                {isLoading ? 'Processing...' : 'Register Operator'}
                            </GlowButton>
                        </div>

                        <div className="text-center pt-1">
                            <p className="text-[11px] font-mono text-white/25">
                                Already registered?{' '}
                                <Link href="/login" className="text-red-400/70 hover:text-red-400 underline underline-offset-2 transition-colors">
                                    Login here
                                </Link>
                            </p>
                        </div>
                    </form>

                    {/* Footer */}
                    <div className="px-6 pb-1">
                        <div className="h-px bg-white/[0.04]" />
                    </div>
                    <StatusLine text={statusText} />
                </div>

                <p className="text-center text-[9px] font-mono text-white/10 mt-4 tracking-widest uppercase">
                    RedWire Security Platform — v2.0
                </p>
            </div>

            <style jsx global>{`
                @keyframes shimmer {
                    0% { background-position: 200% 0; }
                    100% { background-position: -200% 0; }
                }
            `}</style>
        </div>
    );
}

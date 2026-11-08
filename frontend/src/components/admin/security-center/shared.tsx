'use client';

import { ReactNode } from 'react';
import { format, formatDistanceToNow } from 'date-fns';
import { Badge } from '@/components/ui/badge';
import { cn, parseUTCDate } from '@/lib/utils';
import type { CheckStatus, EventOutcome } from '@/lib/hooks/use-security-center';

export const TOOLTIP_STYLE = {
    contentStyle: { backgroundColor: '#1a2235', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0' },
    itemStyle: { color: '#e2e8f0' },
    labelStyle: { color: '#94a3b8' },
};

export const CHART = {
    grid: '#1e293b',
    axis: '#64748b',
    ok: '#22c55e',
    fail: '#ef4444',
    warn: '#f59e0b',
    neutral: '#6366f1',
};

export const WINDOWS = [
    { hours: 1, label: '1h' },
    { hours: 24, label: '24h' },
    { hours: 24 * 7, label: '7d' },
    { hours: 24 * 30, label: '30d' },
];

export function ago(iso?: string | null): string {
    if (!iso) return '—';
    return formatDistanceToNow(parseUTCDate(iso), { addSuffix: true });
}

/** Compact relative time for narrow columns: "now", "5m", "3h", "2d". */
export function agoShort(iso?: string | null): string {
    if (!iso) return '—';
    const secs = Math.max(0, (Date.now() - parseUTCDate(iso).getTime()) / 1000);
    if (secs < 60) return 'now';
    if (secs < 3600) return `${Math.floor(secs / 60)}m`;
    if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
    return `${Math.floor(secs / 86400)}d`;
}

export function stamp(iso?: string | null): string {
    if (!iso) return '—';
    return format(parseUTCDate(iso), 'yyyy-MM-dd HH:mm:ss');
}

export function hourLabel(iso: string, spanHours: number): string {
    const d = parseUTCDate(iso);
    return spanHours > 24 ? format(d, 'MMM d HH:00') : format(d, 'HH:00');
}

export function StatCard({ label, value, hint, tone = 'default', icon, onClick }: {
    label: string;
    value: ReactNode;
    hint?: ReactNode;
    tone?: 'default' | 'good' | 'warn' | 'bad';
    icon?: ReactNode;
    onClick?: () => void;
}) {
    const toneClass = {
        default: 'text-foreground',
        good: 'text-green-400',
        warn: 'text-amber-400',
        bad: 'text-red-400',
    }[tone];
    return (
        <div
            onClick={onClick}
            className={cn('rounded-xl border border-border bg-card p-4', onClick && 'cursor-pointer hover:bg-accent/40 transition-colors')}
        >
            <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
                <span>{label}</span>
                {icon}
            </div>
            <div className={cn('mt-2 text-2xl font-semibold tabular-nums', toneClass)}>{value}</div>
            {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
        </div>
    );
}

export function Panel({ title, action, children, className }: {
    title: ReactNode;
    action?: ReactNode;
    children: ReactNode;
    className?: string;
}) {
    return (
        <div className={cn('rounded-xl border border-border bg-card', className)}>
            <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
                <h3 className="text-sm font-semibold text-foreground">{title}</h3>
                {action}
            </div>
            <div className="p-4">{children}</div>
        </div>
    );
}

export function WindowPicker({ value, onChange, options = WINDOWS }: {
    value: number;
    onChange: (hours: number) => void;
    options?: { hours: number; label: string }[];
}) {
    return (
        <div className="inline-flex rounded-lg border border-border bg-background p-0.5">
            {options.map((w) => (
                <button
                    key={w.hours}
                    onClick={() => onChange(w.hours)}
                    className={cn(
                        'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                        value === w.hours ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
                    )}
                >
                    {w.label}
                </button>
            ))}
        </div>
    );
}

const OUTCOME_CLASS: Record<EventOutcome, string> = {
    success: 'bg-green-500/10 text-green-400 border-green-500/20',
    failure: 'bg-red-500/10 text-red-400 border-red-500/20',
    info: 'bg-slate-500/10 text-slate-300 border-slate-500/20',
};

export function OutcomeBadge({ outcome }: { outcome: EventOutcome }) {
    return <Badge variant="outline" className={cn('text-[10px] uppercase', OUTCOME_CLASS[outcome])}>{outcome}</Badge>;
}

const STATUS_CLASS: Record<CheckStatus, string> = {
    pass: 'bg-green-500/10 text-green-400 border-green-500/20',
    warn: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    fail: 'bg-red-500/10 text-red-400 border-red-500/20',
    info: 'bg-slate-500/10 text-slate-300 border-slate-500/20',
};

export function CheckBadge({ status }: { status: CheckStatus }) {
    return <Badge variant="outline" className={cn('w-12 justify-center text-[10px] uppercase', STATUS_CLASS[status])}>{status}</Badge>;
}

export function HttpStatus({ code }: { code: number }) {
    const cls = code >= 500 ? 'text-red-400' : code === 429 ? 'text-orange-400' : code >= 400 ? 'text-amber-400'
        : code >= 300 ? 'text-sky-400' : 'text-green-400';
    return <span className={cn('font-mono tabular-nums', cls)}>{code}</span>;
}

const FLAG_LABEL: Record<string, { label: string; cls: string }> = {
    probe: { label: 'probe', cls: 'bg-red-500/10 text-red-400 border-red-500/20' },
    scanner_ua: { label: 'scanner', cls: 'bg-orange-500/10 text-orange-400 border-orange-500/20' },
    tool_ua: { label: 'tool', cls: 'bg-slate-500/10 text-slate-300 border-slate-500/20' },
};

export function FlagBadges({ flags }: { flags: string[] }) {
    return (
        <span className="inline-flex gap-1">
            {flags.map((f) => (
                <Badge key={f} variant="outline" className={cn('text-[10px]', FLAG_LABEL[f]?.cls)}>{FLAG_LABEL[f]?.label ?? f}</Badge>
            ))}
        </span>
    );
}

/** Human labels for security_events.event_type. */
export const EVENT_LABELS: Record<string, string> = {
    login: 'Sign-in',
    mfa_challenge: '2FA challenge',
    logout: 'Sign-out',
    register: 'Registration',
    password_changed: 'Password changed',
    password_reset: 'Password reset',
    password_reset_requested: 'Reset requested',
    mfa_enabled: '2FA enabled',
    mfa_disabled: '2FA disabled',
    mfa_recovery_regenerated: 'Recovery codes regenerated',
    sessions_revoked: 'Signed out everywhere',
    api_token_created: 'API token created',
    api_token_revoked: 'API token revoked',
    user_created: 'User created',
    user_updated: 'User changed',
    user_deleted: 'User deleted',
    rate_limited: 'Rate limited',
    sso_error: 'SSO error',
    config_changed: 'Config changed',
};

export function eventLabel(type: string) {
    return EVENT_LABELS[type] ?? type.replace(/_/g, ' ');
}

/** One-line description of an event's details for table rows. */
export function describeEvent(e: { event_type: string; reason: string | null; details: Record<string, any> | null }): string {
    const d = e.details || {};
    switch (e.event_type) {
        case 'login':
            return e.reason ? e.reason.replace(/_/g, ' ') + (d.known_user === false ? ' (unknown user)' : '')
                : [d.provider, d.mfa ? 'with 2FA' : null, d.method === 'recovery_code' ? 'recovery code' : null].filter(Boolean).join(' · ');
        case 'user_updated':
            return Object.entries(d.changes || {}).map(([k, v]: [string, any]) =>
                k === 'groups' ? 'groups changed' : `${k}: ${String(v.old)} → ${String(v.new)}`).join(', ');
        case 'api_token_created':
        case 'api_token_revoked':
            return [d.token_prefix && `${d.token_prefix}…`, d.permission].filter(Boolean).join(' · ');
        case 'rate_limited':
            return `${d.method ?? ''} ${d.path ?? ''} — ${e.reason ?? ''}`.trim();
        case 'config_changed':
            return e.reason ?? '';
        default:
            return e.reason?.replace(/_/g, ' ') ?? '';
    }
}

export function EmptyRow({ cols, children }: { cols: number; children: ReactNode }) {
    return (
        <tr>
            <td colSpan={cols} className="px-3 py-8 text-center text-sm text-muted-foreground">{children}</td>
        </tr>
    );
}

export const TH = 'px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wide text-muted-foreground';
export const TD = 'px-3 py-2 text-sm align-top';

export function Pager({ offset, limit, total, onChange }: {
    offset: number; limit: number; total: number; onChange: (offset: number) => void;
}) {
    if (total <= limit) return null;
    return (
        <div className="flex items-center justify-end gap-2 pt-3 text-xs text-muted-foreground">
            <span>{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
            <button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}
                className="rounded border border-border px-2 py-1 hover:bg-accent disabled:opacity-40">Prev</button>
            <button disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}
                className="rounded border border-border px-2 py-1 hover:bg-accent disabled:opacity-40">Next</button>
        </div>
    );
}

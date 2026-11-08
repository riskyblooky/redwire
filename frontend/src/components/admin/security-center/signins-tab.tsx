'use client';

import { useState } from 'react';
import { Search, X } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { EventOutcome, useSecurityEvents, useSigninSummary } from '@/lib/hooks/use-security-center';
import {
    CHART, EmptyRow, OutcomeBadge, Pager, Panel, StatCard, TD, TH, TOOLTIP_STYLE, WindowPicker,
    ago, agoShort, describeEvent, eventLabel, hourLabel, stamp,
} from './shared';

const TYPE_FILTERS = [
    { value: 'all', label: 'All events' },
    { value: 'login', label: 'Sign-ins' },
    { value: 'login,mfa_challenge', label: 'Sign-ins + 2FA' },
    { value: 'mfa_challenge,mfa_enabled,mfa_disabled,mfa_recovery_regenerated', label: '2FA' },
    { value: 'password_changed,password_reset,password_reset_requested', label: 'Passwords' },
    { value: 'logout,sessions_revoked', label: 'Sessions' },
    { value: 'api_token_created,api_token_revoked', label: 'API tokens' },
    { value: 'rate_limited', label: 'Rate limited' },
    { value: 'sso_error', label: 'SSO errors' },
];

const PAGE = 50;

export function SigninsTab({ initialIp }: { initialIp?: string }) {
    const [hours, setHours] = useState(24);
    const [type, setType] = useState('all');
    const [outcome, setOutcome] = useState<'all' | EventOutcome>('all');
    const [ip, setIp] = useState<string | undefined>(initialIp);
    const [q, setQ] = useState('');
    const [offset, setOffset] = useState(0);
    const dq = useDebounce(q, 300);

    const { data: summary } = useSigninSummary(Math.min(hours, 24 * 90));
    const { data: events, isFetching } = useSecurityEvents({
        hours, offset, limit: PAGE, ip, q: dq || undefined,
        event_type: type === 'all' ? undefined : type,
        outcome: outcome === 'all' ? undefined : outcome,
    });
    const reset = () => setOffset(0);
    const series = (summary?.hourly ?? []).map((h) => ({ ...h, label: hourLabel(h.bucket, hours) }));

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <WindowPicker value={hours} onChange={(h) => { setHours(h); reset(); }} />
                {ip && (
                    <button onClick={() => { setIp(undefined); reset(); }}
                        className="inline-flex items-center gap-1 rounded-full border border-border bg-accent/40 px-2.5 py-1 text-xs">
                        IP {ip} <X className="h-3 w-3" />
                    </button>
                )}
            </div>

            {summary && (
                <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                    <StatCard label="Successful sign-ins" value={summary.logins_ok} tone="good" />
                    <StatCard label="Failed sign-ins" value={summary.logins_failed} tone={summary.logins_failed ? 'warn' : 'default'} />
                    <StatCard label="Failed 2FA" value={summary.mfa_failed} tone={summary.mfa_failed ? 'warn' : 'default'} />
                    <StatCard label="Rate limited" value={summary.rate_limited} tone={summary.rate_limited ? 'warn' : 'default'} />
                    <StatCard label="Failing source IPs" value={summary.failing_ips} />
                </div>
            )}

            <div className="grid gap-4 lg:grid-cols-3">
                <Panel title="Sign-ins over time" className="lg:col-span-1">
                    {series.length === 0 ? <p className="text-sm text-muted-foreground">No sign-ins in this window.</p> : (
                        <ResponsiveContainer width="100%" height={180}>
                            <BarChart data={series}>
                                <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                                <XAxis dataKey="label" stroke={CHART.axis} fontSize={10} />
                                <YAxis stroke={CHART.axis} fontSize={10} allowDecimals={false} width={28} />
                                <Tooltip {...TOOLTIP_STYLE} />
                                <Bar dataKey="success" name="Succeeded" stackId="a" fill={CHART.ok} />
                                <Bar dataKey="failure" name="Failed" stackId="a" fill={CHART.fail} />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </Panel>
                <Panel title="Top failing IPs">
                    <table className="w-full">
                        <thead><tr><th className={TH}>IP</th><th className={TH}>Fails</th><th className={TH}>Users</th><th className={TH}>Last</th></tr></thead>
                        <tbody>
                            {(summary?.top_ips ?? []).length === 0 && <EmptyRow cols={4}>No failures.</EmptyRow>}
                            {summary?.top_ips.map((r) => (
                                <tr key={r.ip} className="cursor-pointer hover:bg-accent/40" onClick={() => { setIp(r.ip); reset(); }}>
                                    <td className={`${TD} font-mono text-xs`}>{r.ip}</td>
                                    <td className={`${TD} tabular-nums text-red-400`}>{r.failures}</td>
                                    <td className={`${TD} tabular-nums`}>{r.usernames}</td>
                                    <td className={`${TD} whitespace-nowrap text-xs text-muted-foreground`} title={stamp(r.last)}>{agoShort(r.last)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Panel>
                <Panel title="Most-targeted usernames">
                    <table className="w-full">
                        <thead><tr><th className={TH}>Username</th><th className={TH}>Fails</th><th className={TH}>IPs</th><th className={TH}>Last</th></tr></thead>
                        <tbody>
                            {(summary?.top_usernames ?? []).length === 0 && <EmptyRow cols={4}>No failures.</EmptyRow>}
                            {summary?.top_usernames.map((r) => (
                                <tr key={r.username} className="cursor-pointer hover:bg-accent/40" onClick={() => { setQ(r.username); reset(); }}>
                                    <td className={`${TD} text-xs`}>{r.username}</td>
                                    <td className={`${TD} tabular-nums text-red-400`}>{r.failures}</td>
                                    <td className={`${TD} tabular-nums`}>{r.ips}</td>
                                    <td className={`${TD} whitespace-nowrap text-xs text-muted-foreground`} title={stamp(r.last)}>{agoShort(r.last)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Panel>
            </div>

            <Panel
                title={<span>Security events {events && <span className="font-normal text-muted-foreground">· {events.total}</span>}</span>}
                action={isFetching ? <span className="text-xs text-muted-foreground">Refreshing…</span> : undefined}
            >
                <div className="mb-3 flex flex-wrap gap-2">
                    <div className="relative min-w-[220px] flex-1">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input value={q} onChange={(e) => { setQ(e.target.value); reset(); }} placeholder="Username, IP or reason"
                            className="h-9 pl-8" />
                    </div>
                    <Select value={type} onValueChange={(v) => { setType(v); reset(); }}>
                        <SelectTrigger className="h-9 w-[180px]"><SelectValue /></SelectTrigger>
                        <SelectContent>{TYPE_FILTERS.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                    </Select>
                    <Select value={outcome} onValueChange={(v) => { setOutcome(v as any); reset(); }}>
                        <SelectTrigger className="h-9 w-[130px]"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Any outcome</SelectItem>
                            <SelectItem value="failure">Failures</SelectItem>
                            <SelectItem value="success">Successes</SelectItem>
                            <SelectItem value="info">Info</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="border-b border-border">
                            <tr>
                                <th className={TH}>Time</th><th className={TH}>Event</th><th className={TH}>Outcome</th>
                                <th className={TH}>User</th><th className={TH}>IP</th><th className={TH}>Detail</th><th className={TH}>Client</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                            {events && events.items.length === 0 && <EmptyRow cols={7}>No events match.</EmptyRow>}
                            {events?.items.map((e) => (
                                <tr key={e.id} className="hover:bg-accent/30">
                                    <td className={`${TD} whitespace-nowrap text-xs text-muted-foreground`} title={stamp(e.created_at)}>{ago(e.created_at)}</td>
                                    <td className={`${TD} whitespace-nowrap`}>{eventLabel(e.event_type)}</td>
                                    <td className={TD}><OutcomeBadge outcome={e.outcome} /></td>
                                    <td className={`${TD} text-xs`}>
                                        {e.username ?? '—'}
                                        {e.actor_username && e.actor_id !== e.user_id && <span className="block text-muted-foreground">by {e.actor_username}</span>}
                                    </td>
                                    <td className={`${TD} font-mono text-xs`}>
                                        {e.ip ? <button className="hover:underline" onClick={() => { setIp(e.ip!); reset(); }}>{e.ip}</button> : '—'}
                                    </td>
                                    <td className={`${TD} text-xs text-muted-foreground`}>{describeEvent(e)}</td>
                                    <td className={`${TD} max-w-[220px] truncate text-xs text-muted-foreground`} title={e.user_agent ?? ''}>{e.user_agent ?? '—'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {events && <Pager offset={offset} limit={PAGE} total={events.total} onChange={setOffset} />}
            </Panel>
        </div>
    );
}

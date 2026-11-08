'use client';

import { AlertTriangle, CheckCircle2, Loader2, Lock } from 'lucide-react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useSecurityOverview } from '@/lib/hooks/use-security-center';
import { cn } from '@/lib/utils';
import { CHART, Panel, StatCard, TOOLTIP_STYLE, hourLabel } from './shared';
import type { SecurityNav } from './index';

export function SecurityOverviewTab({ nav }: { nav: SecurityNav }) {
    const { data, isLoading, isError } = useSecurityOverview();
    if (isLoading) return <div className="flex justify-center p-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;
    if (isError || !data) return <p className="p-6 text-sm text-red-400">Couldn&apos;t load the security overview.</p>;

    const { signins, traffic, posture, attention, tls } = data;
    const signinSeries = signins.hourly.map((h) => ({ ...h, label: hourLabel(h.bucket, 24) }));
    const trafficSeries = traffic.hourly.map((h) => ({ ...h, label: hourLabel(h.bucket, 24) }));

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
                <StatCard label="Failed sign-ins · 24h" value={signins.logins_failed + signins.mfa_failed}
                    hint={`${signins.failing_ips} source IP${signins.failing_ips === 1 ? '' : 's'}`}
                    tone={signins.logins_failed + signins.mfa_failed > 0 ? 'warn' : 'good'} onClick={() => nav.go('signins')} />
                <StatCard label="Sign-ins · 24h" value={signins.logins_ok} onClick={() => nav.go('signins')} />
                <StatCard label="Rate limited · 24h" value={signins.rate_limited} tone={signins.rate_limited ? 'warn' : 'default'}
                    onClick={() => nav.go('signins')} />
                <StatCard label="Requests · 24h" value={traffic.requests.toLocaleString()} hint={`${traffic.unique_ips} IPs`}
                    onClick={() => nav.go('traffic')} />
                <StatCard label="Probes / scanners · 24h" value={`${traffic.probes} / ${traffic.scanner}`}
                    tone={traffic.probes || traffic.scanner ? 'warn' : 'good'} onClick={() => nav.go('traffic')} />
                <StatCard label="5xx · 24h" value={traffic.s5xx} hint={`${traffic.s4xx} 4xx · ${traffic.s429} 429`}
                    tone={traffic.s5xx ? 'bad' : 'good'} onClick={() => nav.go('traffic')} />
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
                <Panel title="Needs attention" className="lg:col-span-1"
                    action={<span className="text-xs text-muted-foreground">v{data.version}</span>}>
                    {attention.length === 0 ? (
                        <div className="flex items-center gap-2 text-sm text-green-400">
                            <CheckCircle2 className="h-4 w-4" /> Nothing needs attention.
                        </div>
                    ) : (
                        <ul className="space-y-2">
                            {attention.map((a, i) => (
                                <li key={i}>
                                    <button onClick={() => nav.go(a.tab as any, { ip: a.ip })}
                                        className="flex w-full gap-2 rounded-lg p-2 text-left hover:bg-accent/50">
                                        <AlertTriangle className={cn('mt-0.5 h-4 w-4 shrink-0', a.severity === 'high' ? 'text-red-400' : 'text-amber-400')} />
                                        <span>
                                            <span className="block text-sm text-foreground">{a.title}</span>
                                            <span className="block text-xs text-muted-foreground">{a.detail}</span>
                                        </span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </Panel>

                <div className="space-y-4 lg:col-span-2">
                    <Panel title="Sign-ins · last 24h">
                        {signinSeries.length === 0 ? <p className="text-sm text-muted-foreground">No sign-in activity.</p> : (
                            <ResponsiveContainer width="100%" height={160}>
                                <BarChart data={signinSeries}>
                                    <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                                    <XAxis dataKey="label" stroke={CHART.axis} fontSize={11} />
                                    <YAxis stroke={CHART.axis} fontSize={11} allowDecimals={false} width={32} />
                                    <Tooltip {...TOOLTIP_STYLE} />
                                    <Bar dataKey="success" name="Succeeded" stackId="a" fill={CHART.ok} />
                                    <Bar dataKey="failure" name="Failed" stackId="a" fill={CHART.fail} />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </Panel>
                    <Panel title="Web traffic · last 24h">
                        {trafficSeries.length === 0 ? <p className="text-sm text-muted-foreground">No traffic recorded yet.</p> : (
                            <ResponsiveContainer width="100%" height={160}>
                                <AreaChart data={trafficSeries}>
                                    <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                                    <XAxis dataKey="label" stroke={CHART.axis} fontSize={11} />
                                    <YAxis stroke={CHART.axis} fontSize={11} allowDecimals={false} width={40} />
                                    <Tooltip {...TOOLTIP_STYLE} />
                                    <Area dataKey="requests" name="Requests" stroke={CHART.neutral} fill={CHART.neutral} fillOpacity={0.15} />
                                    <Area dataKey="flagged" name="Flagged" stroke={CHART.warn} fill={CHART.warn} fillOpacity={0.15} />
                                    <Area dataKey="s5xx" name="5xx" stroke={CHART.fail} fill={CHART.fail} fillOpacity={0.15} />
                                </AreaChart>
                            </ResponsiveContainer>
                        )}
                    </Panel>
                </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
                <button onClick={() => nav.go('posture')} className="flex items-center justify-between rounded-xl border border-border bg-card p-4 text-left hover:bg-accent/40">
                    <span className="text-sm font-medium">Posture checks</span>
                    <span className="flex gap-3 text-sm tabular-nums">
                        <span className="text-red-400">{posture.fail} fail</span>
                        <span className="text-amber-400">{posture.warn} warn</span>
                        <span className="text-green-400">{posture.pass} pass</span>
                    </span>
                </button>
                <button onClick={() => nav.go('posture')} className="flex items-center justify-between rounded-xl border border-border bg-card p-4 text-left hover:bg-accent/40">
                    <span className="flex items-center gap-2 text-sm font-medium"><Lock className="h-4 w-4 text-muted-foreground" /> TLS certificate</span>
                    <span className={cn('text-sm', tls?.status === 'pass' ? 'text-green-400' : tls?.status === 'fail' ? 'text-red-400' : 'text-amber-400')}>
                        {tls?.detail ?? 'Unknown'}
                    </span>
                </button>
            </div>
        </div>
    );
}

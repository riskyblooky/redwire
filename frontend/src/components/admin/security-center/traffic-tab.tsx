'use client';

import { useState } from 'react';
import { AlertTriangle, Search, X } from 'lucide-react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { format } from 'date-fns';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { CountRow, RequestFilters, useTrafficHistory, useTrafficRequests, useTrafficSummary } from '@/lib/hooks/use-security-center';
import {
    CHART, EmptyRow, FlagBadges, HttpStatus, Pager, Panel, StatCard, TD, TH, TOOLTIP_STYLE, WindowPicker,
    ago, agoShort, hourLabel, stamp,
} from './shared';

const PAGE = 100;
const WINDOWS = [
    { hours: 1, label: '1h' },
    { hours: 24, label: '24h' },
    { hours: 24 * 7, label: '7d' },
    { hours: 24 * 14, label: '14d' },
];

function TopList({ rows, onPick, mono = true }: { rows: CountRow[]; onPick?: (v: string) => void; mono?: boolean }) {
    if (rows.length === 0) return <p className="text-sm text-muted-foreground">None.</p>;
    const max = Math.max(...rows.map((r) => r.count));
    return (
        <ul className="space-y-1.5">
            {rows.map((r) => (
                <li key={r.value}>
                    <button onClick={() => onPick?.(r.value)} disabled={!onPick}
                        className="group relative flex w-full items-center justify-between gap-3 overflow-hidden rounded px-2 py-1 text-left text-xs enabled:hover:bg-accent/40">
                        <span className="absolute inset-y-0 left-0 bg-primary/10" style={{ width: `${(r.count / max) * 100}%` }} />
                        <span className={`relative truncate ${mono ? 'font-mono' : ''}`} title={r.value}>{r.value}</span>
                        <span className="relative tabular-nums text-muted-foreground">{r.count}</span>
                    </button>
                </li>
            ))}
        </ul>
    );
}

export function TrafficTab({ initialIp }: { initialIp?: string }) {
    const [hours, setHours] = useState(24);
    const [ip, setIp] = useState<string | undefined>(initialIp);
    const [path, setPath] = useState('');
    const [status, setStatus] = useState('all');
    const [flag, setFlag] = useState<'all' | NonNullable<RequestFilters['flag']>>('all');
    const [area, setArea] = useState<'all' | NonNullable<RequestFilters['area']>>('all');
    const [offset, setOffset] = useState(0);
    const dPath = useDebounce(path, 300);
    const reset = () => setOffset(0);

    const { data: s, isLoading } = useTrafficSummary(hours);
    const { data: history } = useTrafficHistory(90);
    const { data: reqs, isFetching } = useTrafficRequests({
        hours, offset, limit: PAGE, ip, path: dPath || undefined,
        status: status === 'all' ? undefined : status,
        flag: flag === 'all' ? undefined : flag,
        area: area === 'all' ? undefined : area,
    });
    const series = (s?.hourly ?? []).map((h) => ({ ...h, label: hourLabel(h.bucket, hours) }));
    // Rollup days are UTC dates — label them as such, not shifted into local time.
    const days = (history ?? []).map((d) => ({ ...d, label: format(new Date(`${d.day.slice(0, 10)}T12:00:00`), 'MMM d') }));
    const pickPath = (p: string) => { setPath(p); reset(); };

    return (
        <div className="space-y-4">
            {s && !s.ingest.configured && (
                <div className="flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-300">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                        nginx&apos;s JSON access log isn&apos;t mounted into the backend at <code className="text-xs">{s.ingest.path}</code>,
                        so no web traffic is being recorded. Redeploy with the current <code className="text-xs">docker-compose.yml</code> (adds the <code className="text-xs">nginx_logs</code> volume).
                    </span>
                </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2">
                <WindowPicker value={hours} onChange={(h) => { setHours(h); reset(); }} options={WINDOWS} />
                <div className="flex items-center gap-2">
                    {ip && (
                        <button onClick={() => { setIp(undefined); reset(); }}
                            className="inline-flex items-center gap-1 rounded-full border border-border bg-accent/40 px-2.5 py-1 text-xs">
                            IP {ip} <X className="h-3 w-3" />
                        </button>
                    )}
                    {s?.ingest.last_ingest && <span className="text-xs text-muted-foreground">Last ingest {ago(s.ingest.last_ingest)}</span>}
                </div>
            </div>

            {s && (
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
                    <StatCard label="Requests" value={s.requests.toLocaleString()} />
                    <StatCard label="Unique IPs" value={s.unique_ips} />
                    <StatCard label="4xx" value={s.s4xx} tone={s.s4xx ? 'warn' : 'default'} onClick={() => { setStatus('4xx'); reset(); }} />
                    <StatCard label="5xx" value={s.s5xx} tone={s.s5xx ? 'bad' : 'good'} onClick={() => { setStatus('5xx'); reset(); }} />
                    <StatCard label="429" value={s.s429} tone={s.s429 ? 'warn' : 'default'} onClick={() => { setStatus('429'); reset(); }} />
                    <StatCard label="Probe requests" value={s.probes} tone={s.probes ? 'warn' : 'good'} onClick={() => { setFlag('probe'); reset(); }} />
                    <StatCard label="Scanner UAs" value={s.scanner} tone={s.scanner ? 'warn' : 'good'} onClick={() => { setFlag('scanner_ua'); reset(); }} />
                </div>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
                <Panel title="Requests over time">
                    {isLoading ? null : series.length === 0 ? <p className="text-sm text-muted-foreground">No traffic in this window.</p> : (
                        <ResponsiveContainer width="100%" height={180}>
                            <AreaChart data={series}>
                                <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                                <XAxis dataKey="label" stroke={CHART.axis} fontSize={10} />
                                <YAxis stroke={CHART.axis} fontSize={10} allowDecimals={false} width={40} />
                                <Tooltip {...TOOLTIP_STYLE} />
                                <Area dataKey="requests" name="Requests" stroke={CHART.neutral} fill={CHART.neutral} fillOpacity={0.15} />
                                <Area dataKey="s4xx" name="4xx" stroke={CHART.warn} fill={CHART.warn} fillOpacity={0.1} />
                                <Area dataKey="s5xx" name="5xx" stroke={CHART.fail} fill={CHART.fail} fillOpacity={0.15} />
                                <Area dataKey="flagged" name="Flagged" stroke="#f97316" fill="#f97316" fillOpacity={0.1} />
                            </AreaChart>
                        </ResponsiveContainer>
                    )}
                </Panel>
                <Panel title="Daily · last 90 days" action={<span className="text-xs text-muted-foreground">from hourly rollups</span>}>
                    {days.length === 0 ? <p className="text-sm text-muted-foreground">No history yet.</p> : (
                        <ResponsiveContainer width="100%" height={180}>
                            <BarChart data={days}>
                                <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                                <XAxis dataKey="label" stroke={CHART.axis} fontSize={10} />
                                <YAxis stroke={CHART.axis} fontSize={10} allowDecimals={false} width={40} />
                                <Tooltip {...TOOLTIP_STYLE} />
                                <Bar dataKey="requests" name="Requests" fill={CHART.neutral} />
                                <Bar dataKey="probes" name="Probes" fill="#f97316" />
                                <Bar dataKey="s5xx" name="5xx" fill={CHART.fail} />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </Panel>
            </div>

            {s && (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <Panel title="Top client IPs">
                        <table className="w-full">
                            <thead><tr><th className={TH}>IP</th><th className={TH}>Req</th><th className={TH}>Err</th><th className={TH}>Flagged</th><th className={TH}>Last</th></tr></thead>
                            <tbody>
                                {s.top_ips.length === 0 && <EmptyRow cols={5}>None.</EmptyRow>}
                                {s.top_ips.map((r) => (
                                    <tr key={r.ip} className="cursor-pointer hover:bg-accent/40" onClick={() => { setIp(r.ip); reset(); }}>
                                        <td className={`${TD} font-mono text-xs`}>{r.ip}</td>
                                        <td className={`${TD} tabular-nums`}>{r.requests}</td>
                                        <td className={`${TD} tabular-nums text-amber-400`}>{r.errors}</td>
                                        <td className={`${TD} tabular-nums text-orange-400`}>{r.flagged}</td>
                                        <td className={`${TD} whitespace-nowrap text-xs text-muted-foreground`} title={stamp(r.last)}>{agoShort(r.last)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </Panel>
                    <Panel title="Probe paths (scanners looking for other software or secrets)">
                        <TopList rows={s.top_probes} onPick={pickPath} />
                    </Panel>
                    <Panel title="Scanner / tool user agents">
                        <TopList rows={s.flagged_user_agents} mono={false} />
                    </Panel>
                    <Panel title="Top 404 paths"><TopList rows={s.top_404} onPick={pickPath} /></Panel>
                    <Panel title="Top 5xx paths"><TopList rows={s.top_5xx} onPick={pickPath} /></Panel>
                    <Panel title="Top user agents"><TopList rows={s.top_user_agents} mono={false} /></Panel>
                </div>
            )}

            <Panel
                title={<span>Request log {reqs && <span className="font-normal text-muted-foreground">· {reqs.total.toLocaleString()}</span>}</span>}
                action={isFetching ? <span className="text-xs text-muted-foreground">Refreshing…</span> : undefined}
            >
                <div className="mb-3 flex flex-wrap gap-2">
                    <div className="relative min-w-[220px] flex-1">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input value={path} onChange={(e) => { setPath(e.target.value); reset(); }} placeholder="Path contains"
                            className="h-9 pl-8 font-mono text-xs" />
                    </div>
                    <Select value={status} onValueChange={(v) => { setStatus(v); reset(); }}>
                        <SelectTrigger className="h-9 w-[120px]"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {['all', '2xx', '3xx', '4xx', '5xx', '401', '403', '404', '429'].map((v) =>
                                <SelectItem key={v} value={v}>{v === 'all' ? 'Any status' : v}</SelectItem>)}
                        </SelectContent>
                    </Select>
                    <Select value={flag} onValueChange={(v) => { setFlag(v as any); reset(); }}>
                        <SelectTrigger className="h-9 w-[140px]"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All requests</SelectItem>
                            <SelectItem value="any">Any flag</SelectItem>
                            <SelectItem value="probe">Probes</SelectItem>
                            <SelectItem value="scanner_ua">Scanner UA</SelectItem>
                            <SelectItem value="tool_ua">Tool UA</SelectItem>
                        </SelectContent>
                    </Select>
                    <Select value={area} onValueChange={(v) => { setArea(v as any); reset(); }}>
                        <SelectTrigger className="h-9 w-[110px]"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Web + API</SelectItem>
                            <SelectItem value="web">Web</SelectItem>
                            <SelectItem value="api">API</SelectItem>
                            <SelectItem value="ws">WebSocket</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="border-b border-border">
                            <tr>
                                <th className={TH}>Time</th><th className={TH}>IP</th><th className={TH}>Request</th>
                                <th className={TH}>Status</th><th className={TH}>ms</th><th className={TH}>Flags</th><th className={TH}>User agent</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                            {reqs && reqs.items.length === 0 && <EmptyRow cols={7}>No requests match.</EmptyRow>}
                            {reqs?.items.map((r) => (
                                <tr key={r.id} className="hover:bg-accent/30">
                                    <td className={`${TD} whitespace-nowrap text-xs text-muted-foreground`}>{stamp(r.ts)}</td>
                                    <td className={`${TD} font-mono text-xs`}>
                                        {r.ip ? <button className="hover:underline" onClick={() => { setIp(r.ip!); reset(); }}>{r.ip}</button> : '—'}
                                    </td>
                                    <td className={`${TD} max-w-[360px] font-mono text-xs`}>
                                        <span className="mr-1.5 text-muted-foreground">{r.method}</span>
                                        <span className="break-all">{r.path}</span>
                                    </td>
                                    <td className={TD}><HttpStatus code={r.status} /></td>
                                    <td className={`${TD} tabular-nums text-xs text-muted-foreground`}>{r.duration_ms ?? '—'}</td>
                                    <td className={TD}><FlagBadges flags={r.flags} /></td>
                                    <td className={`${TD} max-w-[240px] truncate text-xs text-muted-foreground`} title={r.user_agent ?? ''}>{r.user_agent ?? '—'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {reqs && <Pager offset={offset} limit={PAGE} total={reqs.total} onChange={setOffset} />}
            </Panel>
        </div>
    );
}

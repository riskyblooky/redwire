'use client';

import { useMemo, useState } from 'react';
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    BarChart3,
    Briefcase,
    Building2,
    GitCompare,
    Loader2,
    ShieldAlert,
    TrendingDown,
    TrendingUp,
    Minus,
    Calendar,
    Clock,
} from 'lucide-react';
import {
    Bar,
    BarChart,
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
    Legend,
} from 'recharts';
import {
    EngagementSummary,
    useClientEngagements,
    useClientStats,
    useCompareEngagements,
} from '@/lib/hooks/use-clients';
import { Client } from '@/lib/types';
import Link from 'next/link';

const SEVERITY_COLORS: Record<string, string> = {
    CRITICAL: '#ef4444',
    HIGH: '#f97316',
    MEDIUM: '#f59e0b',
    LOW: '#3b82f6',
    INFO: '#64748b',
};

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] as const;

const TOOLTIP_STYLE = {
    contentStyle: { backgroundColor: '#1a2235', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0' },
    itemStyle: { color: '#e2e8f0' },
    labelStyle: { color: '#94a3b8' },
};

function fmtDate(s: string | null): string {
    if (!s) return '—';
    return new Date(s).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function fmtMttr(days: number | null): string {
    if (days === null || days === undefined) return '—';
    if (days < 1) return `${(days * 24).toFixed(1)}h`;
    return `${days.toFixed(1)}d`;
}

function deltaIcon(n: number) {
    if (n > 0) return <TrendingUp className="h-3.5 w-3.5 text-red-400" />;
    if (n < 0) return <TrendingDown className="h-3.5 w-3.5 text-emerald-400" />;
    return <Minus className="h-3.5 w-3.5 text-slate-500" />;
}

function deltaText(n: number, suffix = ''): string {
    const sign = n > 0 ? '+' : '';
    return `${sign}${n}${suffix}`;
}

// ───────────────────────────── Panel ─────────────────────────────

export function ClientStatsPanel({ client, hasDescendants = false }: { client: Client | null; hasDescendants?: boolean }) {
    const clientId = client?.id ?? null;
    const [includeDescendants, setIncludeDescendants] = useState(true);
    const effectiveInclude = hasDescendants && includeDescendants;
    const { data: stats, isLoading: statsLoading } = useClientStats(clientId, effectiveInclude);
    const { data: engagements, isLoading: engsLoading } = useClientEngagements(clientId, effectiveInclude);

    const [tab, setTab] = useState<'overview' | 'engagements' | 'trends'>('overview');
    const [compareIds, setCompareIds] = useState<string[]>([]);
    const [compareOpen, setCompareOpen] = useState(false);

    const descendantClientCount = useMemo(() => {
        if (!engagements || !client) return 0;
        const ids = new Set(engagements.map(e => e.client_id).filter(id => id && id !== client.id));
        return ids.size;
    }, [engagements, client]);

    if (!client) {
        return (
            <Card className="border-slate-800 bg-slate-900/50 h-full">
                <CardContent className="flex flex-col items-center justify-center py-24 text-slate-500">
                    <Building2 className="h-12 w-12 mb-3 opacity-20" />
                    <p className="text-sm">Select a client from the hierarchy to see metrics.</p>
                </CardContent>
            </Card>
        );
    }

    const toggleCompare = (id: string) => {
        setCompareIds((prev) => {
            if (prev.includes(id)) return prev.filter((x) => x !== id);
            if (prev.length >= 2) return [prev[1], id];
            return [...prev, id];
        });
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50 h-full">
            <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                    <CardTitle className="text-white text-lg flex items-center gap-2 flex-wrap">
                        <Building2 className="h-5 w-5 text-primary" />
                        {client.name}
                        {effectiveInclude && descendantClientCount > 0 && (
                            <Badge variant="outline" className="text-[10px] border-cyan-500/30 text-cyan-400 bg-cyan-500/5">
                                +{descendantClientCount} child {descendantClientCount === 1 ? 'client' : 'clients'} rolled up
                            </Badge>
                        )}
                        {!effectiveInclude && hasDescendants && (
                            <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">
                                this client only
                            </Badge>
                        )}
                    </CardTitle>
                    {hasDescendants && (
                        <div className="flex items-center gap-2 shrink-0">
                            <Label htmlFor="include-descendants" className="text-xs text-slate-400 cursor-pointer">
                                Include descendants
                            </Label>
                            <Switch
                                id="include-descendants"
                                checked={includeDescendants}
                                onCheckedChange={setIncludeDescendants}
                            />
                        </div>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)} className="space-y-4">
                    <TabsList className="bg-slate-950/40 border border-slate-800/50 rounded-lg p-1 h-auto">
                        <TabsTrigger value="overview" className="text-xs">Overview</TabsTrigger>
                        <TabsTrigger value="engagements" className="text-xs">
                            Engagements{engagements ? ` (${engagements.length})` : ''}
                        </TabsTrigger>
                        <TabsTrigger value="trends" className="text-xs">Trends</TabsTrigger>
                    </TabsList>

                    {/* OVERVIEW */}
                    <TabsContent value="overview" className="space-y-4">
                        {statsLoading ? (
                            <div className="flex items-center justify-center py-12 text-slate-500">
                                <Loader2 className="h-5 w-5 animate-spin" />
                            </div>
                        ) : !stats ? null : (
                            <>
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                    <KpiCard label="Engagements" value={stats.engagement_count} icon={Briefcase} color="text-amber-400 bg-amber-500/10" />
                                    <KpiCard label="Findings" value={stats.finding_count} icon={ShieldAlert} color="text-rose-400 bg-rose-500/10" />
                                    <KpiCard label="Open" value={stats.open_findings} icon={ShieldAlert} color="text-orange-400 bg-orange-500/10" />
                                    <KpiCard label="Avg MTTR" value={fmtMttr(stats.mttr_days)} icon={Clock} color="text-cyan-400 bg-cyan-500/10" />
                                </div>

                                <SeverityBar counts={stats.findings_by_severity} />

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-slate-400">
                                    <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-3">
                                        <div className="flex items-center gap-2 mb-2 text-slate-300">
                                            <Calendar className="h-3.5 w-3.5" /> Engagement window
                                        </div>
                                        <div>First: <span className="text-white">{fmtDate(stats.first_engagement_at)}</span></div>
                                        <div>Last: <span className="text-white">{fmtDate(stats.last_engagement_at)}</span></div>
                                    </div>
                                    <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-3">
                                        <div className="flex items-center gap-2 mb-2 text-slate-300">
                                            <BarChart3 className="h-3.5 w-3.5" /> Engagement status mix
                                        </div>
                                        {Object.entries(stats.engagements_by_status).length === 0 ? (
                                            <span className="text-slate-500">No engagements yet.</span>
                                        ) : (
                                            <div className="flex flex-wrap gap-1">
                                                {Object.entries(stats.engagements_by_status).map(([k, v]) => (
                                                    <Badge key={k} variant="outline" className="text-[10px] border-slate-700 text-slate-300">
                                                        {k.replace('_', ' ')} · {v}
                                                    </Badge>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </>
                        )}
                    </TabsContent>

                    {/* ENGAGEMENTS */}
                    <TabsContent value="engagements" className="space-y-3">
                        <div className="flex items-center justify-between gap-3">
                            <p className="text-xs text-slate-500">
                                {compareIds.length === 0 && 'Tick two engagements to compare them.'}
                                {compareIds.length === 1 && 'Pick one more to compare.'}
                                {compareIds.length === 2 && 'Two selected — ready to compare.'}
                            </p>
                            <Button
                                size="sm"
                                disabled={compareIds.length !== 2}
                                onClick={() => setCompareOpen(true)}
                                className="bg-primary hover:bg-primary/90"
                            >
                                <GitCompare className="h-3.5 w-3.5 mr-1.5" /> Compare
                            </Button>
                        </div>

                        {engsLoading ? (
                            <div className="flex items-center justify-center py-8 text-slate-500">
                                <Loader2 className="h-5 w-5 animate-spin" />
                            </div>
                        ) : !engagements || engagements.length === 0 ? (
                            <div className="text-center py-12 text-sm text-slate-500">No engagements for this client yet.</div>
                        ) : (
                            <div className="space-y-1.5">
                                {engagements.map((e) => (
                                    <EngagementRow
                                        key={e.id}
                                        eng={e}
                                        checked={compareIds.includes(e.id)}
                                        onToggle={() => toggleCompare(e.id)}
                                        rootClientId={client.id}
                                    />
                                ))}
                            </div>
                        )}
                    </TabsContent>

                    {/* TRENDS */}
                    <TabsContent value="trends" className="space-y-4">
                        {engsLoading ? (
                            <div className="flex items-center justify-center py-12 text-slate-500">
                                <Loader2 className="h-5 w-5 animate-spin" />
                            </div>
                        ) : !engagements || engagements.length === 0 ? (
                            <div className="text-center py-12 text-sm text-slate-500">
                                Not enough history for this client yet — needs at least one completed engagement.
                            </div>
                        ) : (
                            <TrendsView engagements={engagements} rootClientId={client.id} />
                        )}
                    </TabsContent>
                </Tabs>
            </CardContent>

            <CompareModal
                open={compareOpen}
                onOpenChange={(o) => setCompareOpen(o)}
                a={compareIds[0] ?? null}
                b={compareIds[1] ?? null}
            />
        </Card>
    );
}

// ───────────────────────────── Sub-pieces ─────────────────────────────

function KpiCard({ label, value, icon: Icon, color }: { label: string; value: number | string; icon: React.ElementType; color: string }) {
    return (
        <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-3">
            <div className="flex items-center gap-2 mb-1.5">
                <div className={`p-1.5 rounded ${color}`}>
                    <Icon className="h-3.5 w-3.5" />
                </div>
                <span className="text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
            </div>
            <div className="text-xl font-bold text-white">{value}</div>
        </div>
    );
}

function SeverityBar({ counts }: { counts: Record<string, number> }) {
    const total = SEVERITY_ORDER.reduce((acc, k) => acc + (counts[k] || 0), 0);
    if (total === 0) {
        return <div className="text-xs text-slate-500 italic">No findings yet for this client.</div>;
    }
    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between text-[10px] text-slate-500">
                <span>SEVERITY MIX</span>
                <span>{total} findings</span>
            </div>
            <div className="flex h-2.5 rounded-full overflow-hidden bg-slate-800">
                {SEVERITY_ORDER.map((k) => {
                    const v = counts[k] || 0;
                    if (v === 0) return null;
                    return (
                        <div
                            key={k}
                            style={{ width: `${(v / total) * 100}%`, backgroundColor: SEVERITY_COLORS[k] }}
                            title={`${k}: ${v}`}
                        />
                    );
                })}
            </div>
            <div className="flex flex-wrap gap-2 text-[10px]">
                {SEVERITY_ORDER.map((k) => (counts[k] || 0) > 0 && (
                    <span key={k} className="flex items-center gap-1 text-slate-400">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: SEVERITY_COLORS[k] }} />
                        {k} <span className="text-slate-500">{counts[k]}</span>
                    </span>
                ))}
            </div>
        </div>
    );
}

function EngagementRow({ eng, checked, onToggle, rootClientId }: { eng: EngagementSummary; checked: boolean; onToggle: () => void; rootClientId: string }) {
    const status = eng.status.replace('_', ' ');
    const isFromDescendant = eng.client_id && eng.client_id !== rootClientId && eng.client_name;
    return (
        <div className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-colors ${checked ? 'border-primary/50 bg-primary/5' : 'border-slate-800 bg-slate-900/30 hover:bg-slate-800/40'}`}>
            <Checkbox
                checked={checked}
                onCheckedChange={onToggle}
                className="border-slate-700 data-[state=checked]:bg-primary"
            />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <Link href={`/engagements/${eng.id}`} className="text-sm text-white font-medium truncate hover:text-primary transition-colors">
                        {eng.name}
                    </Link>
                    <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400 shrink-0">
                        {status}
                    </Badge>
                    {isFromDescendant && (
                        <Badge variant="outline" className="text-[10px] border-cyan-500/30 text-cyan-400 bg-cyan-500/5 shrink-0">
                            {eng.client_name}
                        </Badge>
                    )}
                </div>
                <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-0.5">
                    <span>{fmtDate(eng.start_date)} → {fmtDate(eng.end_date)}</span>
                    <span>·</span>
                    <span>{eng.finding_count} findings</span>
                    <span>·</span>
                    <span>{eng.open_findings} open</span>
                    <span>·</span>
                    <span>MTTR {fmtMttr(eng.mttr_days)}</span>
                </div>
            </div>
            <div className="hidden sm:flex gap-1 shrink-0">
                {SEVERITY_ORDER.map((k) => {
                    const v = eng.findings_by_severity[k] || 0;
                    if (v === 0) return null;
                    return (
                        <span
                            key={k}
                            className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                            style={{ color: SEVERITY_COLORS[k], backgroundColor: `${SEVERITY_COLORS[k]}20` }}
                            title={k}
                        >
                            {v}
                        </span>
                    );
                })}
            </div>
        </div>
    );
}

function TrendsView({ engagements, rootClientId }: { engagements: EngagementSummary[]; rootClientId: string }) {
    const hasMultipleClients = useMemo(
        () => new Set(engagements.map(e => e.client_id).filter(Boolean)).size > 1,
        [engagements],
    );
    const ordered = useMemo(() => {
        const sorted = [...engagements].sort((a, b) => {
            const da = a.start_date ? new Date(a.start_date).getTime() : 0;
            const db = b.start_date ? new Date(b.start_date).getTime() : 0;
            return da - db;
        });
        return sorted.map((e, idx) => {
            // When multiple sub-clients are aggregated, prefix descendant labels so two
            // engagements with the same name don't collapse on the X-axis.
            const isDescendant = hasMultipleClients && e.client_id && e.client_id !== rootClientId && e.client_name;
            const baseLabel = isDescendant ? `${e.client_name}: ${e.name}` : e.name;
            const label = baseLabel.length > 22 ? baseLabel.slice(0, 20) + '…' : baseLabel;
            return {
                label,
                order: idx + 1,
                CRITICAL: e.findings_by_severity.CRITICAL || 0,
                HIGH: e.findings_by_severity.HIGH || 0,
                MEDIUM: e.findings_by_severity.MEDIUM || 0,
                LOW: e.findings_by_severity.LOW || 0,
                INFO: e.findings_by_severity.INFO || 0,
                mttr: e.mttr_days,
                open: e.open_findings,
                closed: e.closed_findings,
            };
        });
    }, [engagements, rootClientId, hasMultipleClients]);

    return (
        <div className="space-y-5">
            <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Findings by severity, per engagement (chronological)</p>
                <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={ordered}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey="label" stroke="#64748b" fontSize={11} />
                            <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
                            <Tooltip {...TOOLTIP_STYLE} />
                            <Legend wrapperStyle={{ fontSize: 11 }} />
                            {SEVERITY_ORDER.map((k) => (
                                <Bar key={k} dataKey={k} stackId="a" fill={SEVERITY_COLORS[k]} />
                            ))}
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Open vs closed findings</p>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                        <ResponsiveContainer width="100%" height={180}>
                            <BarChart data={ordered}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis dataKey="label" stroke="#64748b" fontSize={11} />
                                <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
                                <Tooltip {...TOOLTIP_STYLE} />
                                <Legend wrapperStyle={{ fontSize: 11 }} />
                                <Bar dataKey="open" fill="#f97316" name="Open" />
                                <Bar dataKey="closed" fill="#10b981" name="Closed" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div>
                    <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Mean time to resolve (days)</p>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                        <ResponsiveContainer width="100%" height={180}>
                            <LineChart data={ordered}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis dataKey="label" stroke="#64748b" fontSize={11} />
                                <YAxis stroke="#64748b" fontSize={11} />
                                <Tooltip {...TOOLTIP_STYLE} />
                                <Line type="monotone" dataKey="mttr" stroke="#06b6d4" strokeWidth={2} dot={{ fill: '#06b6d4', r: 3 }} connectNulls />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
            <p className="text-[10px] text-slate-600 italic">
                Trend reads left → right by start date. Lower critical/high counts and shorter MTTR over time = improving posture.
            </p>
        </div>
    );
}

// ───────────────────────────── Compare modal ─────────────────────────────

function CompareModal({ open, onOpenChange, a, b }: { open: boolean; onOpenChange: (o: boolean) => void; a: string | null; b: string | null }) {
    const { data, isLoading } = useCompareEngagements(open ? a : null, open ? b : null);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-950 border-slate-800 max-w-3xl">
                <DialogHeader>
                    <DialogTitle className="text-white flex items-center gap-2">
                        <GitCompare className="h-5 w-5 text-primary" />
                        Compare Engagements
                    </DialogTitle>
                </DialogHeader>
                {isLoading || !data ? (
                    <div className="py-12 flex items-center justify-center text-slate-500">
                        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading comparison…
                    </div>
                ) : (
                    <div className="space-y-4 pt-2">
                        <div className="grid grid-cols-3 gap-3">
                            <CompareColumn label="A" eng={data.a} />
                            <CompareColumn label="B" eng={data.b} highlight />
                            <DeltaColumn delta={data.delta} />
                        </div>
                        <p className="text-[10px] text-slate-600 italic">
                            Delta is B − A. Per-finding diff (which exact findings recurred or got resolved) is not yet implemented.
                        </p>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

function CompareColumn({ label, eng, highlight = false }: { label: string; eng: EngagementSummary; highlight?: boolean }) {
    return (
        <div className={`rounded-lg border p-3 space-y-2 ${highlight ? 'border-primary/40 bg-primary/5' : 'border-slate-800 bg-slate-900/30'}`}>
            <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">{label}</Badge>
                <Link href={`/engagements/${eng.id}`} className="text-sm text-white truncate hover:text-primary">{eng.name}</Link>
            </div>
            <div className="text-[11px] text-slate-500">{fmtDate(eng.start_date)} → {fmtDate(eng.end_date)}</div>
            <div className="space-y-1 text-xs pt-2 border-t border-slate-800">
                <Row k="Findings" v={eng.finding_count} />
                <Row k="Open" v={eng.open_findings} />
                <Row k="Closed" v={eng.closed_findings} />
                <Row k="MTTR" v={fmtMttr(eng.mttr_days)} />
                <div className="pt-2 mt-1 border-t border-slate-800 space-y-0.5">
                    {SEVERITY_ORDER.map((k) => (
                        <Row key={k} k={k} v={eng.findings_by_severity[k] || 0} color={SEVERITY_COLORS[k]} />
                    ))}
                </div>
            </div>
        </div>
    );
}

function DeltaColumn({ delta }: { delta: { finding_count: number; open_findings: number; closed_findings: number; by_severity: Record<string, number>; mttr_days: number | null } }) {
    return (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 space-y-2">
            <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">Δ</Badge>
                <span className="text-sm text-slate-300">B minus A</span>
            </div>
            <div className="text-[11px] text-slate-600 italic h-[14px]">aggregate delta</div>
            <div className="space-y-1 text-xs pt-2 border-t border-slate-800">
                <DeltaRow k="Findings" v={delta.finding_count} />
                <DeltaRow k="Open" v={delta.open_findings} />
                <DeltaRow k="Closed" v={delta.closed_findings} invertGood />
                <DeltaRow k="MTTR" v={delta.mttr_days} suffix="d" />
                <div className="pt-2 mt-1 border-t border-slate-800 space-y-0.5">
                    {SEVERITY_ORDER.map((k) => (
                        <DeltaRow key={k} k={k} v={delta.by_severity[k] ?? 0} color={SEVERITY_COLORS[k]} />
                    ))}
                </div>
            </div>
        </div>
    );
}

function Row({ k, v, color }: { k: string; v: number | string; color?: string }) {
    return (
        <div className="flex items-center justify-between">
            <span className="text-slate-400 flex items-center gap-1.5">
                {color && <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />}
                {k}
            </span>
            <span className="text-white font-mono">{v}</span>
        </div>
    );
}

function DeltaRow({ k, v, color, suffix = '', invertGood = false }: { k: string; v: number | null; color?: string; suffix?: string; invertGood?: boolean }) {
    if (v === null || v === undefined) {
        return (
            <div className="flex items-center justify-between">
                <span className="text-slate-400 flex items-center gap-1.5">
                    {color && <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />}
                    {k}
                </span>
                <span className="text-slate-600 font-mono text-[11px]">—</span>
            </div>
        );
    }
    // For "closed", an increase is good; flip colours.
    const goodWhenUp = invertGood;
    const tone = v === 0 ? 'text-slate-500' : ((v > 0) === goodWhenUp ? 'text-emerald-400' : 'text-red-400');
    return (
        <div className="flex items-center justify-between">
            <span className="text-slate-400 flex items-center gap-1.5">
                {color && <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />}
                {k}
            </span>
            <span className={`font-mono flex items-center gap-1 ${tone}`}>
                {deltaIcon(v)}
                {deltaText(typeof v === 'number' && !Number.isInteger(v) ? Number(v.toFixed(1)) : v, suffix)}
            </span>
        </div>
    );
}

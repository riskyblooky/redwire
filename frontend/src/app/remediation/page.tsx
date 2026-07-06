/**
 * remediation/page.tsx — Remediation Dashboard
 *
 * Per-engagement remediation tracker with two tabs:
 *
 * **Findings tab**
 *  - Engagement selector dropdown.
 *  - Summary metric strip: Total Findings, Remediation %, Open Findings,
 *    Assets Remediated (with progress bar).
 *  - Filterable, sortable finding list (severity, status, search text,
 *    sort by severity/title/status/remediation%/CVSS).
 *  - Expandable finding rows showing per-asset checkboxes. Checking the
 *    last unremediated asset triggers a prompt to set the finding's status
 *    to REMEDIATED.
 *  - Per-finding inline `<DiscussionSection>` for threaded review comments.
 *
 * **Cleanup tab**
 *  - Lists cleanup artifacts (SSH keys, files, accounts, backdoors, etc.)
 *    with type icon, status dropdown (Pending / Cleaned / Partial / N/A),
 *    location, linked assets, and a detail modal (`CleanupDetailModal`).
 *  - Overall cleanup discussion thread at the bottom.
 *
 * Live WebSocket updates invalidate remediation-summary, findings, and
 * cleanup-artifact queries on relevant activity_log events.
 *
 * Config maps: `severityConfig`, `statusConfig`, `cleanupStatusConfig`,
 * `ARTIFACT_TYPE_CONFIG`, `CLEANUP_STATUS_ICON`.
 */
'use client';

import { useState, useMemo } from 'react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog';
import {
    ClipboardCheck, Search, Target, Shield, Bug, CheckCircle2,
    ChevronDown, ChevronRight, Loader2, AlertTriangle, TrendingUp,
    Trash2, FileText, ExternalLink, Server,
    Key, UserCog, ShieldOff, Terminal, Package, HelpCircle,
    Clock, MinusCircle, ArrowUpDown, ArrowUp, ArrowDown, Sparkles, MessageSquare,
} from 'lucide-react';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import Link from 'next/link';
import { CleanupDetailModal } from '@/components/engagements/cleanup-detail-modal';
import DiscussionSection from '@/components/discussions/discussion-section';
import { useAuthStore } from '@/stores/auth-store';
import { useCollaboration } from '@/lib/hooks/use-collaboration';

// ── Config Maps ───────────────────────────────────────────────────

const severityConfig: Record<string, { color: string; bg: string; border: string; order: number }> = {
    CRITICAL: { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30', order: 0 },
    HIGH: { color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30', order: 1 },
    MEDIUM: { color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30', order: 2 },
    LOW: { color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30', order: 3 },
    INFO: { color: 'text-slate-400', bg: 'bg-slate-500/10', border: 'border-slate-500/30', order: 4 },
};

const statusConfig: Record<string, { color: string; bg: string }> = {
    OPEN: { color: 'text-red-400', bg: 'bg-red-500/15' },
    IN_REVIEW: { color: 'text-amber-400', bg: 'bg-amber-500/15' },
    VERIFIED: { color: 'text-blue-400', bg: 'bg-blue-500/15' },
    REMEDIATED: { color: 'text-green-400', bg: 'bg-green-500/15' },
    CLOSED: { color: 'text-slate-400', bg: 'bg-slate-500/15' },
};

const cleanupStatusConfig: Record<string, { color: string; bg: string; label: string }> = {
    PENDING: { color: 'text-amber-400', bg: 'bg-amber-500/15', label: 'Pending' },
    CLEANED: { color: 'text-green-400', bg: 'bg-green-500/15', label: 'Cleaned' },
    PARTIALLY_CLEANED: { color: 'text-blue-400', bg: 'bg-blue-500/15', label: 'Partial' },
    NOT_APPLICABLE: { color: 'text-slate-400', bg: 'bg-slate-500/15', label: 'N/A' },
};

const ARTIFACT_TYPE_CONFIG: Record<string, { icon: any; color: string; bg: string; label: string }> = {
    SSH_KEY: { icon: Key, label: 'SSH Key', color: 'text-amber-400', bg: 'bg-amber-500/10' },
    FILE: { icon: FileText, label: 'File', color: 'text-blue-400', bg: 'bg-blue-500/10' },
    ACCOUNT: { icon: UserCog, label: 'Account', color: 'text-purple-400', bg: 'bg-purple-500/10' },
    PERMISSION: { icon: ShieldOff, label: 'Permission', color: 'text-rose-400', bg: 'bg-rose-500/10' },
    BACKDOOR: { icon: Terminal, label: 'Backdoor', color: 'text-red-400', bg: 'bg-red-500/10' },
    IMPLANT: { icon: Package, label: 'Implant', color: 'text-orange-400', bg: 'bg-orange-500/10' },
    OTHER: { icon: HelpCircle, label: 'Other', color: 'text-slate-400', bg: 'bg-slate-500/10' },
};

const CLEANUP_STATUS_ICON: Record<string, any> = {
    PENDING: Clock,
    CLEANED: CheckCircle2,
    PARTIALLY_CLEANED: AlertTriangle,
    NOT_APPLICABLE: MinusCircle,
};

// ── Main Component ────────────────────────────────────────────────

export default function RemediationPage() {
    const { data: engagements = [], isLoading: isLoadingEngagements } = useEngagements();
    const [selectedEngagementId, setSelectedEngagementId] = useState('');
    const [searchFilter, setSearchFilter] = useState('');
    const [severityFilter, setSeverityFilter] = useState('ALL');
    const [statusFilter, setStatusFilter] = useState('ALL');
    const [expandedFindings, setExpandedFindings] = useState<Set<string>>(new Set());
    const [activeTab, setActiveTab] = useState('findings');
    const [sortField, setSortField] = useState<string>('severity');
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
    const [assetFilter, setAssetFilter] = useState('ALL');
    const queryClient = useQueryClient();
    const { user } = useAuthStore();

    // ── Live updates via WebSocket ───────────────────────────────
    useCollaboration({
        resourceType: 'dashboard', resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                const rt = (data.resource_type || '').toLowerCase();
                if (rt === 'finding' || rt === 'asset' || rt === 'cleanup_artifact') {
                    queryClient.invalidateQueries({ queryKey: ['remediation-summary'] });
                    queryClient.invalidateQueries({ queryKey: ['findings'] });
                    queryClient.invalidateQueries({ queryKey: ['cleanup-artifacts'] });
                }
            }
        },
    });

    // Remediation prompt dialog
    const [remediatePrompt, setRemediatePrompt] = useState<{ findingId: string; title: string } | null>(null);

    // Cleanup detail modal
    const [viewCleanupArtifact, setViewCleanupArtifact] = useState<any>(null);
    const [isViewCleanupOpen, setIsViewCleanupOpen] = useState(false);

    // Fetch remediation summary
    const { data: summary, isLoading: isLoadingSummary } = useQuery({
        queryKey: ['remediation-summary', selectedEngagementId],
        queryFn: async () => {
            const { data } = await api.get(`/findings/remediation-summary?engagement_id=${selectedEngagementId}`);
            return data;
        },
        enabled: !!selectedEngagementId,
    });

    // Toggle asset remediation
    const toggleRemediation = useMutation({
        mutationFn: async ({ findingId, assetId }: { findingId: string; assetId: string }) => {
            const { data } = await api.patch(`/findings/${findingId}/assets/${assetId}/remediate`);
            return data;
        },
        onSuccess: (data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['remediation-summary', selectedEngagementId] });
            toast.success(data.remediated ? 'Asset marked as remediated' : 'Asset remediation reverted');

            // Check if ALL assets for this finding are now remediated
            if (data.remediated) {
                const finding = summary?.findings?.find((f: any) => f.id === variables.findingId);
                if (finding && finding.status !== 'REMEDIATED') {
                    // After this toggle, check updated counts
                    const newRemediatedCount = finding.remediated_assets + 1;
                    if (newRemediatedCount >= finding.total_assets && finding.total_assets > 0) {
                        setRemediatePrompt({ findingId: variables.findingId, title: finding.title });
                    }
                }
            }
        },
        onError: () => {
            toast.error('Failed to update remediation status');
        },
    });

    // Update finding status to REMEDIATED
    const updateFindingStatus = useMutation({
        mutationFn: async (findingId: string) => {
            const { data } = await api.put(`/findings/${findingId}`, { status: 'REMEDIATED' });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['remediation-summary', selectedEngagementId] });
            toast.success('Finding marked as Remediated');
            setRemediatePrompt(null);
        },
        onError: () => {
            toast.error('Failed to update finding status');
        },
    });

    // Update cleanup artifact status
    const updateCleanupStatus = useMutation({
        mutationFn: async ({ artifactId, newStatus }: { artifactId: string; newStatus: string }) => {
            const { data } = await api.put(`/cleanup-artifacts/${artifactId}`, { status: newStatus });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['remediation-summary', selectedEngagementId] });
            toast.success('Cleanup artifact status updated');
        },
        onError: () => {
            toast.error('Failed to update cleanup status');
        },
    });

    const toggleFinding = (id: string) => {
        setExpandedFindings(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    // Derive unique assets from all findings for filter dropdown
    const uniqueAssets = useMemo(() => {
        const map = new Map<string, { id: string; name: string; identifier: string }>();
        for (const f of (summary?.findings || [])) {
            for (const a of (f.assets || [])) {
                if (!map.has(a.id)) map.set(a.id, { id: a.id, name: a.name, identifier: a.identifier });
            }
        }
        return [...map.values()].sort((a, b) => a.name.localeCompare(b.name));
    }, [summary?.findings]);

    // Filter findings
    const filteredFindings = useMemo(() => {
        const filtered = (summary?.findings || []).filter((f: any) => {
            if (severityFilter !== 'ALL' && f.severity !== severityFilter) return false;
            if (statusFilter !== 'ALL' && f.status !== statusFilter) return false;
            if (assetFilter !== 'ALL' && !f.assets?.some((a: any) => a.id === assetFilter)) return false;
            if (searchFilter) {
                const q = searchFilter.toLowerCase();
                const matchesAssetName = f.assets?.some((a: any) =>
                    a.name?.toLowerCase().includes(q) || a.identifier?.toLowerCase().includes(q)
                );
                if (!f.title.toLowerCase().includes(q) && !f.category?.toLowerCase().includes(q) && !matchesAssetName) return false;
            }
            return true;
        });
        // Sort
        return [...filtered].sort((a: any, b: any) => {
            let cmp = 0;
            switch (sortField) {
                case 'severity':
                    cmp = (severityConfig[a.severity]?.order ?? 99) - (severityConfig[b.severity]?.order ?? 99);
                    break;
                case 'title':
                    cmp = a.title.localeCompare(b.title);
                    break;
                case 'status':
                    cmp = a.status.localeCompare(b.status);
                    break;
                case 'remediation':
                    cmp = (a.remediation_pct || 0) - (b.remediation_pct || 0);
                    break;
                case 'cvss':
                    cmp = (a.cvss_score || 0) - (b.cvss_score || 0);
                    break;
                default:
                    cmp = 0;
            }
            return sortOrder === 'desc' ? -cmp : cmp;
        });
    }, [summary?.findings, severityFilter, statusFilter, assetFilter, searchFilter, sortField, sortOrder]);

    const s = summary?.summary || {};
    const cleanupArtifacts = summary?.cleanup_artifacts || [];
    const pendingCleanup = cleanupArtifacts.filter((ca: any) => ca.status === 'PENDING').length;

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 w-full">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="p-3 rounded-xl bg-gradient-to-br from-green-500/20 to-emerald-500/20 border border-green-500/20">
                            <ClipboardCheck className="h-7 w-7 text-green-400" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-white">Remediation</h1>
                        </div>
                    </div>
                </div>

                {/* Engagement Selector */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md">
                    <CardContent className="py-4">
                        <div className="flex items-center gap-4">
                            <label className="text-sm font-semibold text-slate-300 uppercase tracking-wider whitespace-nowrap">Engagement</label>
                            <Select value={selectedEngagementId} onValueChange={setSelectedEngagementId}>
                                <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white h-11 max-w-lg">
                                    <SelectValue placeholder="Select an engagement to view remediation..." />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white max-h-80">
                                    {isLoadingEngagements ? (
                                        <div className="p-4 text-center"><Loader2 className="h-4 w-4 animate-spin mx-auto" /></div>
                                    ) : (
                                        engagements.map((eng) => (
                                            <SelectItem key={eng.id} value={eng.id}>
                                                <div className="flex items-center gap-2">
                                                    <span>{eng.name}</span>
                                                    <Badge variant="outline" className={cn(
                                                        "text-[9px] px-1.5 h-4 border-none uppercase font-bold",
                                                        eng.status === 'COMPLETED' ? 'bg-green-500/10 text-green-400' :
                                                            eng.status === 'IN_PROGRESS' ? 'bg-blue-500/10 text-blue-400' :
                                                                'bg-slate-500/10 text-slate-400'
                                                    )}>
                                                        {eng.status?.replace(/_/g, ' ')}
                                                    </Badge>
                                                </div>
                                            </SelectItem>
                                        ))
                                    )}
                                </SelectContent>
                            </Select>
                        </div>
                    </CardContent>
                </Card>

                {/* No engagement selected */}
                {!selectedEngagementId && (
                    <div className="flex flex-col items-center justify-center py-20 border border-dashed border-slate-800 rounded-xl">
                        <ClipboardCheck className="h-16 w-16 text-slate-700 mb-4" />
                        <p className="text-slate-400 text-lg font-medium">Select an engagement above</p>
                        <p className="text-slate-500 text-sm mt-1">to view its remediation progress and manage findings</p>
                    </div>
                )}

                {/* Loading */}
                {selectedEngagementId && isLoadingSummary && (
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="h-8 w-8 animate-spin text-green-500" />
                    </div>
                )}

                {/* Dashboard Content */}
                {summary && !isLoadingSummary && (
                    <>
                        {/* Summary Cards */}
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                            <Card className="border-slate-800 bg-slate-900/50 overflow-hidden">
                                <div className="h-1 bg-gradient-to-r from-blue-500 to-cyan-500" />
                                <CardContent className="pt-5 pb-4">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Findings</p>
                                            <p className="text-3xl font-bold text-white mt-1">{s.total_findings || 0}</p>
                                        </div>
                                        <div className="p-2.5 rounded-xl bg-blue-500/10">
                                            <Bug className="h-6 w-6 text-blue-400" />
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="border-slate-800 bg-slate-900/50 overflow-hidden">
                                <div className="h-1 bg-gradient-to-r from-green-500 to-emerald-500" />
                                <CardContent className="pt-5 pb-4">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Remediation</p>
                                            <p className="text-3xl font-bold text-white mt-1">{s.overall_remediation_pct || 0}%</p>
                                        </div>
                                        <div className="p-2.5 rounded-xl bg-green-500/10">
                                            <TrendingUp className="h-6 w-6 text-green-400" />
                                        </div>
                                    </div>
                                    <Progress value={s.overall_remediation_pct || 0} className="mt-3 h-1.5 bg-slate-800" />
                                </CardContent>
                            </Card>

                            <Card className="border-slate-800 bg-slate-900/50 overflow-hidden">
                                <div className="h-1 bg-gradient-to-r from-amber-500 to-orange-500" />
                                <CardContent className="pt-5 pb-4">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Open Findings</p>
                                            <p className="text-3xl font-bold text-white mt-1">{(s.by_status?.OPEN || 0) + (s.by_status?.IN_REVIEW || 0) + (s.by_status?.VERIFIED || 0)}</p>
                                        </div>
                                        <div className="p-2.5 rounded-xl bg-amber-500/10">
                                            <AlertTriangle className="h-6 w-6 text-amber-400" />
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="border-slate-800 bg-slate-900/50 overflow-hidden">
                                <div className="h-1 bg-gradient-to-r from-purple-500 to-pink-500" />
                                <CardContent className="pt-5 pb-4">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Assets Remediated</p>
                                            <p className="text-3xl font-bold text-white mt-1">
                                                <span className="text-green-400">{s.remediated_assets || 0}</span>
                                                <span className="text-slate-600 text-lg font-normal"> / {s.total_assets || 0}</span>
                                            </p>
                                        </div>
                                        <div className="p-2.5 rounded-xl bg-primary/10">
                                            <Target className="h-6 w-6 text-primary" />
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>


                        {/* Tabs: Findings / Cleanup Items */}
                        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                            <TabsList className="bg-slate-950/40 border border-slate-800/60 p-1.5 h-auto flex-wrap justify-start gap-1 rounded-xl backdrop-blur-md">
                                <TabsTrigger
                                    value="findings"
                                    className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-red-500/10 data-[state=active]:text-red-400 data-[state=active]:border-red-500/30 hover:border-red-500/20 hover:text-red-400/80 border border-transparent transition-all duration-300 group"
                                >
                                    <Bug className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                                    <span className="font-semibold">Findings</span>
                                    {(summary?.findings?.length || 0) > 0 && (
                                        <Badge variant="secondary" className="ml-2 bg-red-500/20 text-red-400 border-none px-1.5 h-4 text-[10px]">
                                            {summary?.findings?.length}
                                        </Badge>
                                    )}
                                </TabsTrigger>
                                <TabsTrigger
                                    value="cleanup"
                                    className="flex-1 min-w-[150px] rounded-lg py-2.5 data-[state=active]:bg-lime-500/10 data-[state=active]:text-lime-400 data-[state=active]:border-lime-500/30 hover:border-lime-500/20 hover:text-lime-400/80 border border-transparent transition-all duration-300 group"
                                >
                                    <Sparkles className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                                    <span className="font-semibold">Cleanup</span>
                                    {pendingCleanup > 0 && (
                                        <Badge variant="secondary" className="ml-2 bg-lime-500/20 text-lime-400 border-none px-1.5 h-4 text-[10px]">
                                            {pendingCleanup}
                                        </Badge>
                                    )}
                                </TabsTrigger>
                            </TabsList>

                            {/* ── Findings Tab ─────────────────────────────────── */}
                            <TabsContent value="findings" className="mt-6 space-y-4 focus-visible:outline-hidden focus-visible:ring-0">
                                {/* Filters + Sort */}
                                <div className="flex items-center gap-3 flex-wrap">
                                    <div className="relative flex-1 max-w-sm">
                                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                        <Input
                                            value={searchFilter}
                                            onChange={(e) => setSearchFilter(e.target.value)}
                                            placeholder="Search findings..."
                                            className="pl-10 bg-slate-950/50 border-slate-800 text-white h-10"
                                        />
                                    </div>
                                    <Select value={severityFilter} onValueChange={setSeverityFilter}>
                                        <SelectTrigger className="w-36 bg-slate-950/50 border-slate-800 text-white h-10">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            <SelectItem value="ALL">All Severities</SelectItem>
                                            {Object.keys(severityConfig).map(sv => (
                                                <SelectItem key={sv} value={sv}>{sv}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Select value={statusFilter} onValueChange={setStatusFilter}>
                                        <SelectTrigger className="w-36 bg-slate-950/50 border-slate-800 text-white h-10">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            <SelectItem value="ALL">All Statuses</SelectItem>
                                            {Object.keys(statusConfig).map(st => (
                                                <SelectItem key={st} value={st}>{st.replace(/_/g, ' ')}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Select value={sortField} onValueChange={setSortField}>
                                        <SelectTrigger className="w-36 bg-slate-950/50 border-slate-800 text-white h-10">
                                            <ArrowUpDown className="h-3 w-3 mr-1" />
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            <SelectItem value="severity">Severity</SelectItem>
                                            <SelectItem value="title">Title</SelectItem>
                                            <SelectItem value="status">Status</SelectItem>
                                            <SelectItem value="remediation">Remediation %</SelectItem>
                                            <SelectItem value="cvss">CVSS Score</SelectItem>
                                        </SelectContent>
                                    </Select>
                                    {/* Asset filter */}
                                    {uniqueAssets.length > 0 && (
                                        <Select value={assetFilter} onValueChange={setAssetFilter}>
                                            <SelectTrigger className={cn(
                                                "w-44 bg-slate-950/50 border-slate-800 text-white h-10",
                                                assetFilter !== 'ALL' && "border-blue-500/50 text-blue-300"
                                            )}>
                                                <Server className="h-3 w-3 mr-1 shrink-0" />
                                                <SelectValue placeholder="All Assets" />
                                            </SelectTrigger>
                                            <SelectContent className="bg-slate-900 border-slate-800 text-white max-h-64">
                                                <SelectItem value="ALL">All Assets</SelectItem>
                                                {uniqueAssets.map(asset => (
                                                    <SelectItem key={asset.id} value={asset.id}>
                                                        <div className="flex flex-col items-start">
                                                            <span className="font-medium">{asset.name}</span>
                                                            <span className="text-[9px] font-mono text-slate-500">{asset.identifier}</span>
                                                        </div>
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    )}
                                    <Button
                                        variant="outline"
                                        size="icon"
                                        className="border-slate-800 bg-slate-950/50 text-slate-400 hover:text-white h-10 w-10 shrink-0"
                                        onClick={() => setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}
                                    >
                                        {sortOrder === 'asc' ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
                                    </Button>
                                    {/* Clear filters button */}
                                    {(severityFilter !== 'ALL' || statusFilter !== 'ALL' || assetFilter !== 'ALL' || searchFilter) && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-10 text-xs text-slate-500 hover:text-white px-2"
                                            onClick={() => {
                                                setSeverityFilter('ALL');
                                                setStatusFilter('ALL');
                                                setAssetFilter('ALL');
                                                setSearchFilter('');
                                            }}
                                        >
                                            Clear
                                        </Button>
                                    )}
                                    <span className="text-xs text-slate-500">{filteredFindings.length} findings</span>
                                </div>

                                {/* Findings List */}
                                <div className="space-y-3">
                                    {filteredFindings.length === 0 ? (
                                        <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                                            <Shield className="h-12 w-12 mx-auto mb-3 text-slate-700" />
                                            <p className="text-slate-400">No findings match your filters</p>
                                        </div>
                                    ) : (
                                        filteredFindings.map((finding: any) => {
                                            const isExpanded = expandedFindings.has(finding.id);
                                            const sevCfg = severityConfig[finding.severity] || severityConfig.INFO;
                                            const stCfg = statusConfig[finding.status] || statusConfig.OPEN;

                                            return (
                                                <Card key={finding.id} className={cn("border-slate-800 bg-slate-900/40 overflow-hidden transition-all", isExpanded && "ring-1 ring-slate-700")}>
                                                    {/* Finding Header Row */}
                                                    <div
                                                        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-slate-800/30 transition-colors"
                                                        onClick={() => toggleFinding(finding.id)}
                                                    >
                                                        {isExpanded ? (
                                                            <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
                                                        ) : (
                                                            <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
                                                        )}

                                                        <Badge className={cn("text-[10px] px-2 py-0 h-5 font-bold border shrink-0 uppercase", sevCfg.color, sevCfg.bg, sevCfg.border)}>
                                                            {finding.severity}
                                                        </Badge>

                                                        <span className="text-sm font-semibold text-white truncate flex-1">{finding.title}</span>

                                                        {(finding.unresolved_thread_count || 0) > 0 && (
                                                            <div className="flex items-center gap-1 shrink-0 text-amber-400">
                                                                <MessageSquare className="h-3.5 w-3.5" />
                                                                <span className="text-xs font-bold">{finding.unresolved_thread_count}</span>
                                                            </div>
                                                        )}

                                                        <Badge className={cn("text-[10px] px-2 py-0 h-5 font-bold border-none shrink-0 uppercase", stCfg.color, stCfg.bg)}>
                                                            {finding.status.replace(/_/g, ' ')}
                                                        </Badge>

                                                        {finding.cvss_score > 0 && (
                                                            <span className="text-xs font-mono font-bold text-slate-400 shrink-0">
                                                                {finding.cvss_score}
                                                            </span>
                                                        )}

                                                        <div className="flex items-center gap-2 shrink-0 w-40">
                                                            <Progress
                                                                value={finding.remediation_pct}
                                                                className={cn("h-2 bg-slate-800 flex-1", finding.remediation_pct === 100 && "[&>div]:bg-green-500")}
                                                            />
                                                            <span className={cn(
                                                                "text-xs font-bold tabular-nums w-10 text-right",
                                                                finding.remediation_pct === 100 ? "text-green-400" :
                                                                    finding.remediation_pct > 0 ? "text-amber-400" : "text-slate-500"
                                                            )}>
                                                                {finding.remediation_pct}%
                                                            </span>
                                                        </div>

                                                        <Link
                                                            href={`/findings/${finding.id}?engagementId=${selectedEngagementId}`}
                                                            onClick={(e) => e.stopPropagation()}
                                                            className="text-slate-500 hover:text-white transition-colors shrink-0"
                                                        >
                                                            <ExternalLink className="h-3.5 w-3.5" />
                                                        </Link>
                                                    </div>

                                                    {/* Expanded: Asset-level remediation */}
                                                    {isExpanded && (
                                                        <div className="border-t border-slate-800/60 px-4 py-3 bg-slate-950/30">
                                                            {finding.total_assets === 0 ? (
                                                                <p className="text-xs text-slate-500 italic py-2">No assets linked to this finding</p>
                                                            ) : (
                                                                <div className="space-y-1.5">
                                                                    <div className="flex items-center justify-between mb-2">
                                                                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                                                                            Affected Assets ({finding.remediated_assets}/{finding.total_assets} remediated)
                                                                        </span>
                                                                    </div>
                                                                    {finding.assets.map((asset: any) => (
                                                                        <div
                                                                            key={asset.id}
                                                                            className={cn(
                                                                                "flex items-center gap-3 px-3 py-2 rounded-lg border transition-all",
                                                                                asset.remediated
                                                                                    ? "bg-green-500/5 border-green-500/20"
                                                                                    : "bg-slate-900/30 border-slate-800/60"
                                                                            )}
                                                                        >
                                                                            <Checkbox
                                                                                checked={asset.remediated}
                                                                                onCheckedChange={() => toggleRemediation.mutate({ findingId: finding.id, assetId: asset.id })}
                                                                                className={cn(asset.remediated && "data-[state=checked]:bg-green-500 data-[state=checked]:border-green-500")}
                                                                            />
                                                                            <div className="flex-1 min-w-0">
                                                                                <div className="flex items-center gap-2">
                                                                                    <span className={cn(
                                                                                        "text-sm font-bold truncate",
                                                                                        asset.remediated ? "text-green-300 line-through opacity-70" : "text-white"
                                                                                    )}>
                                                                                        {asset.name}
                                                                                    </span>
                                                                                    {asset.asset_type && (
                                                                                        <Badge variant="outline" className="text-[8px] px-1.5 h-4 border-slate-700 text-slate-500 uppercase shrink-0">
                                                                                            {asset.asset_type.replace(/_/g, ' ')}
                                                                                        </Badge>
                                                                                    )}
                                                                                </div>
                                                                                <span className="text-[10px] text-slate-500 font-mono uppercase">{asset.identifier}</span>
                                                                            </div>
                                                                            {asset.remediated && asset.remediated_by_username && (
                                                                                <span className="text-[10px] text-green-500/60 shrink-0">
                                                                                    by {asset.remediated_by_username}
                                                                                </span>
                                                                            )}
                                                                            {asset.remediated && (
                                                                                <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                                                                            )}
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            )}

                                                            {/* Per-finding discussion thread */}
                                                            <div className="mt-4 pt-3 border-t border-slate-800/40">
                                                                <DiscussionSection
                                                                    engagementId={selectedEngagementId}
                                                                    resourceType="finding_remediation"
                                                                    resourceId={finding.id}
                                                                    currentUserId={user?.id}
                                                                    isAdmin={user?.role === 'admin'}
                                                                />
                                                            </div>
                                                        </div>
                                                    )}
                                                </Card>
                                            );
                                        })
                                    )}
                                </div>
                            </TabsContent>

                            {/* ── Cleanup Items Tab ─────────────────────────────── */}
                            <TabsContent value="cleanup" className="mt-6 space-y-4 focus-visible:outline-hidden focus-visible:ring-0">
                                {cleanupArtifacts.length === 0 ? (
                                    <div className="text-center py-16 border border-dashed border-slate-800 rounded-xl">
                                        <Trash2 className="h-12 w-12 mx-auto mb-3 text-slate-700" />
                                        <p className="text-slate-400">No cleanup artifacts for this engagement</p>
                                    </div>
                                ) : (
                                    <div className="space-y-3">
                                        {cleanupArtifacts.map((ca: any) => {
                                            const csCfg = cleanupStatusConfig[ca.status] || cleanupStatusConfig.PENDING;
                                            const typeCfg = ARTIFACT_TYPE_CONFIG[ca.artifact_type] || ARTIFACT_TYPE_CONFIG.OTHER;
                                            const TypeIcon = typeCfg.icon;
                                            const StatusIcon = CLEANUP_STATUS_ICON[ca.status] || Clock;

                                            return (
                                                <Card key={ca.id} className="border-slate-800 bg-slate-900/40">
                                                    <CardContent className="py-4 px-5">
                                                        <div className="flex items-start gap-4">
                                                            {/* Type Icon */}
                                                            <div className={cn("p-2 rounded-lg shrink-0", typeCfg.bg)}>
                                                                <TypeIcon className={cn("h-4 w-4", typeCfg.color)} />
                                                            </div>

                                                            {/* Main Content */}
                                                            <div className="flex-1 min-w-0 space-y-2">
                                                                <div className="flex items-center gap-2">
                                                                    <button
                                                                        className="text-sm font-semibold text-white truncate hover:text-primary/80 transition-colors text-left"
                                                                        onClick={() => {
                                                                            setViewCleanupArtifact(ca);
                                                                            setIsViewCleanupOpen(true);
                                                                        }}
                                                                    >
                                                                        {ca.title}
                                                                    </button>
                                                                    <Badge variant="outline" className={cn("text-[8px] px-1.5 h-4 border-slate-700 uppercase shrink-0", typeCfg.color)}>
                                                                        {typeCfg.label}
                                                                    </Badge>
                                                                </div>

                                                                {ca.location && (
                                                                    <code className="text-[10px] text-slate-500 font-mono block truncate">{ca.location}</code>
                                                                )}

                                                                {ca.description && (
                                                                    <p className="text-xs text-slate-500 line-clamp-2">{ca.description}</p>
                                                                )}

                                                                {/* Linked Assets */}
                                                                {ca.linked_assets && ca.linked_assets.length > 0 && (
                                                                    <div className="flex items-center gap-2 flex-wrap pt-1">
                                                                        <Server className="h-3 w-3 text-blue-400 shrink-0" />
                                                                        {ca.linked_assets.map((asset: any) => (
                                                                            <Badge
                                                                                key={asset.id}
                                                                                variant="outline"
                                                                                className="text-[9px] px-1.5 h-5 border-blue-500/20 bg-blue-500/5 text-blue-300 cursor-pointer hover:border-blue-500/40 transition-colors"
                                                                                onClick={() => {
                                                                                    setViewCleanupArtifact(ca);
                                                                                    setIsViewCleanupOpen(true);
                                                                                }}
                                                                            >
                                                                                {asset.name}
                                                                            </Badge>
                                                                        ))}
                                                                    </div>
                                                                )}
                                                            </div>

                                                            {/* Status Dropdown */}
                                                            <Select
                                                                value={ca.status}
                                                                onValueChange={(val) => updateCleanupStatus.mutate({ artifactId: ca.id, newStatus: val })}
                                                            >
                                                                <SelectTrigger className={cn("w-40 h-8 text-[10px] font-bold uppercase border-none shrink-0 gap-1.5", csCfg.color, csCfg.bg)}>
                                                                    <StatusIcon className="h-3 w-3" />
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                                    {Object.entries(cleanupStatusConfig).map(([st, cfg]) => (
                                                                        <SelectItem key={st} value={st}>
                                                                            <span className={cn("text-xs font-bold uppercase", cfg.color)}>
                                                                                {st.replace(/_/g, ' ')}
                                                                            </span>
                                                                        </SelectItem>
                                                                    ))}
                                                                </SelectContent>
                                                            </Select>
                                                        </div>
                                                    </CardContent>
                                                </Card>
                                            );
                                        })}
                                    </div>
                                )}

                                {/* Overall cleanup discussion thread */}
                                {cleanupArtifacts.length > 0 && (
                                    <div className="mt-6">
                                        <DiscussionSection
                                            engagementId={selectedEngagementId}
                                            resourceType="cleanup_artifact"
                                            resourceId={selectedEngagementId}
                                            currentUserId={user?.id}
                                            isAdmin={user?.role === 'admin'}
                                        />
                                    </div>
                                )}
                            </TabsContent>
                        </Tabs>
                    </>
                )}
            </div>

            {/* Remediation Prompt Dialog */}
            <Dialog open={!!remediatePrompt} onOpenChange={(open) => !open && setRemediatePrompt(null)}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <CheckCircle2 className="h-5 w-5 text-green-400" />
                            All Assets Remediated
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">
                            All assets for <span className="text-white font-semibold">{remediatePrompt?.title}</span> have been marked as remediated. Would you like to update the finding status to <span className="text-green-400 font-semibold">REMEDIATED</span>?
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="gap-2 sm:gap-0">
                        <Button
                            variant="ghost"
                            className="text-slate-400 hover:text-white"
                            onClick={() => setRemediatePrompt(null)}
                        >
                            Not Now
                        </Button>
                        <Button
                            className="bg-green-600 hover:bg-green-500 text-white"
                            onClick={() => remediatePrompt && updateFindingStatus.mutate(remediatePrompt.findingId)}
                            disabled={updateFindingStatus.isPending}
                        >
                            {updateFindingStatus.isPending ? (
                                <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Updating...</>
                            ) : (
                                'Mark as Remediated'
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Cleanup Detail Modal */}
            <CleanupDetailModal
                artifact={viewCleanupArtifact}
                open={isViewCleanupOpen}
                onOpenChange={setIsViewCleanupOpen}
            />
        </DashboardLayout>
    );
}

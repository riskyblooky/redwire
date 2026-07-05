/**
 * imports/page.tsx — Scanner Import Wizard
 *
 * Three-step import flow for ingesting scanner output files into
 * an engagement:
 *
 * **Step 1 — Upload**: Drag-and-drop zone with engagement selector
 * and supported format badges (Nessus, Burp, Nuclei, Nmap, CSV, XLSX).
 *
 * **Step 2 — Preview**: Two-tab view (Assets / Findings) showing
 * parsed results with duplicate indicators, severity badges, and
 * select/deselect checkboxes. Summary cards show counts and
 * severity distribution.
 *
 * **Step 3 — Results**: Animated counters for assets/findings
 * created/skipped, with links to the engagement.
 */
'use client';

import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { useEngagements } from '@/lib/hooks/use-engagements';
import {
    usePreviewImport,
    useCommitImport,
    type PreviewResponse,
    type PreviewAsset,
    type PreviewFinding,
    type CommitResponse,
} from '@/lib/hooks/use-imports';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import {
    Upload, FileUp, AlertTriangle, CheckCircle2, XCircle,
    ArrowRight, ArrowLeft, Loader2, Server, Bug, Link2,
    Layers, RefreshCw, ExternalLink, ChevronDown, Info,
    Shield, Search,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';

/* ── Severity badge helper ──────────────────────────────────────── */

const SEV_COLORS: Record<string, string> = {
    CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/30',
    HIGH: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    MEDIUM: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    LOW: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    INFO: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

function SeverityBadge({ severity }: { severity: string }) {
    return (
        <Badge className={cn('text-[10px] font-bold uppercase border', SEV_COLORS[severity] || SEV_COLORS.INFO)}>
            {severity}
        </Badge>
    );
}

/* ── Tool/format badges ─────────────────────────────────────────── */

const TOOL_BADGES: Record<string, { label: string; color: string }> = {
    nessus: { label: 'Nessus', color: 'bg-green-500/20 text-green-400 border-green-500/30' },
    burp: { label: 'Burp Suite', color: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
    nuclei: { label: 'Nuclei', color: 'bg-purple-500/20 text-purple-400 border-purple-500/30' },
    nmap: { label: 'Nmap', color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' },
};

/* ── Supported format badges ────────────────────────────────────── */

const FORMATS = [
    { ext: '.nessus', tool: 'Nessus / OpenVAS', color: 'text-green-400' },
    { ext: '.xml', tool: 'Burp Suite / Nmap', color: 'text-orange-400' },
    { ext: '.json / .jsonl', tool: 'Nuclei', color: 'text-purple-400' },
    { ext: '.csv / .xlsx', tool: 'Spreadsheet', color: 'text-blue-400' },
];

/* ── Step Indicator ─────────────────────────────────────────────── */

function StepIndicator({ current }: { current: number }) {
    const steps = ['Upload', 'Preview', 'Results'];
    return (
        <div className="flex items-center gap-2">
            {steps.map((label, i) => (
                <div key={label} className="flex items-center gap-2">
                    <div className={cn(
                        'flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold transition-all duration-300',
                        i === current
                            ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/20'
                            : i < current
                                ? 'bg-green-500/20 text-green-400'
                                : 'bg-slate-800 text-slate-500'
                    )}>
                        {i < current ? (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                        ) : (
                            <span className="w-4 text-center">{i + 1}</span>
                        )}
                        {label}
                    </div>
                    {i < steps.length - 1 && (
                        <ArrowRight className={cn('h-3.5 w-3.5', i < current ? 'text-green-500' : 'text-slate-700')} />
                    )}
                </div>
            ))}
        </div>
    );
}

/* ═══════════════ Main Page ═══════════════ */

export default function ImportsPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    // Pre-scope the wizard to a specific engagement when the URL carries
    // ``?engagement=<id>``. This is how the "Import" button on the
    // engagement detail page opens the wizard scoped — no more picking
    // your way through the engagement dropdown. When set, the wizard
    // hides the selector and shows a back link to the engagement.
    const preScopedEngagementId = searchParams?.get('engagement') || '';

    const { data: engagements = [] } = useEngagements();
    const previewMutation = usePreviewImport();
    const commitMutation = useCommitImport();

    // Wizard state
    const [step, setStep] = useState(0);
    const [selectedEngagement, setSelectedEngagement] = useState(preScopedEngagementId);

    // Sync from URL if it changes after mount (unlikely in practice, but keeps
    // the state honest if a link handler pushes a new ?engagement= param).
    useEffect(() => {
        if (preScopedEngagementId && preScopedEngagementId !== selectedEngagement) {
            setSelectedEngagement(preScopedEngagementId);
        }
        // Intentionally only depends on preScopedEngagementId — we don't want
        // to reset state on every internal selectedEngagement change.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [preScopedEngagementId]);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<PreviewResponse | null>(null);
    const [result, setResult] = useState<CommitResponse | null>(null);

    // Preview options
    const [importAssets, setImportAssets] = useState(true);
    const [importFindings, setImportFindings] = useState(true);
    const [previewTab, setPreviewTab] = useState<'assets' | 'findings'>('findings');
    const [selectedAssets, setSelectedAssets] = useState<Set<number>>(new Set());
    const [selectedFindings, setSelectedFindings] = useState<Set<number>>(new Set());
    const [searchAssets, setSearchAssets] = useState('');
    const [searchFindings, setSearchFindings] = useState('');

    // Drag state
    const [isDragOver, setIsDragOver] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // ── Handlers ────────────────────────────────────────────────

    const handleFile = useCallback(async (file: File) => {
        setSelectedFile(file);

        // Auto-preview
        try {
            const data = await previewMutation.mutateAsync({
                file,
                engagementId: selectedEngagement || undefined,
            });
            setPreview(data);
            // Select all by default
            setSelectedAssets(new Set(data.assets.map((_, i) => i)));
            setSelectedFindings(new Set(data.findings.map((_, i) => i)));
            // Auto-switch to findings tab if no assets but has findings
            if (data.findings.length > 0 && data.assets.length === 0) {
                setPreviewTab('findings');
            } else if (data.assets.length > 0 && data.findings.length === 0) {
                setPreviewTab('assets');
            } else {
                setPreviewTab('findings');
            }
            setStep(1);
        } catch (err: any) {
            toast.error('Parse failed', {
                description: apiErrorMessage(err) || err?.message || 'Unknown error',
            });
        }
    }, [previewMutation, selectedEngagement]);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) handleFile(file);
    }, [handleFile]);

    const handleCommit = useCallback(async () => {
        if (!selectedFile || !selectedEngagement) return;

        try {
            const data = await commitMutation.mutateAsync({
                file: selectedFile,
                engagementId: selectedEngagement,
                importAssets,
                importFindings,
                assetIndices: importAssets ? Array.from(selectedAssets) : [],
                findingIndices: importFindings ? Array.from(selectedFindings) : [],
            });
            setResult(data);
            setStep(2);
            toast.success('Import complete!');
        } catch (err: any) {
            toast.error('Import failed', {
                description: apiErrorMessage(err) || err?.message || 'Unknown error',
            });
        }
    }, [selectedFile, selectedEngagement, importAssets, importFindings, selectedAssets, selectedFindings, commitMutation]);

    const handleReset = useCallback(() => {
        setStep(0);
        setSelectedFile(null);
        setPreview(null);
        setResult(null);
        setImportAssets(true);
        setImportFindings(true);
        setSelectedAssets(new Set());
        setSelectedFindings(new Set());
        setSearchAssets('');
        setSearchFindings('');
    }, []);

    // ── Filtered data ───────────────────────────────────────────

    const filteredAssets = useMemo(() => {
        if (!preview) return [];
        if (!searchAssets) return preview.assets;
        const q = searchAssets.toLowerCase();
        return preview.assets.filter(a =>
            a.name.toLowerCase().includes(q) ||
            a.identifier.toLowerCase().includes(q) ||
            a.asset_type.toLowerCase().includes(q)
        );
    }, [preview, searchAssets]);

    const filteredFindings = useMemo(() => {
        if (!preview) return [];
        if (!searchFindings) return preview.findings;
        const q = searchFindings.toLowerCase();
        return preview.findings.filter(f =>
            f.title.toLowerCase().includes(q) ||
            (f.category || '').toLowerCase().includes(q) ||
            f.severity.toLowerCase().includes(q)
        );
    }, [preview, searchFindings]);

    // Severity counts
    const sevCounts = useMemo(() => {
        if (!preview) return {};
        const counts: Record<string, number> = {};
        for (const f of preview.findings) {
            counts[f.severity] = (counts[f.severity] || 0) + 1;
        }
        return counts;
    }, [preview]);

    // ── Engagement name lookup ──────────────────────────────────

    const engagementName = useMemo(() => {
        return engagements.find((e: any) => e.id === selectedEngagement)?.name || '';
    }, [engagements, selectedEngagement]);

    // ── Render ──────────────────────────────────────────────────

    return (
        <DashboardLayout>
            <div className="p-6 max-w-6xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-black text-white tracking-tight flex items-center gap-3">
                            <div className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center shadow-lg shadow-primary/20">
                                <Upload className="h-5 w-5 text-primary-foreground" />
                            </div>
                            Import Scanner Output
                        </h1>
                        <p className="text-slate-500 mt-1 text-sm ml-12">
                            Import assets and findings from Nessus, Burp Suite, Nuclei, Nmap, and more
                        </p>
                    </div>
                    <StepIndicator current={step} />
                </div>

                {/* ═══ Step 0: Upload ═══ */}
                {step === 0 && (
                    <div className="space-y-4">
                        {/* Engagement Selector — hidden when the URL pre-scopes
                            us to a specific engagement (opened from the
                            engagement detail page). Show a scope pill + back
                            link instead so the operator knows what they're
                            importing into. */}
                        {preScopedEngagementId ? (
                            <Card className="border-primary/30 bg-primary/5">
                                <CardContent className="p-4 flex items-center justify-between gap-3">
                                    <div className="flex items-center gap-2 min-w-0">
                                        <Layers className="h-4 w-4 text-primary shrink-0" />
                                        <div className="min-w-0">
                                            <p className="text-[10px] font-bold text-primary uppercase tracking-wider">
                                                Importing into
                                            </p>
                                            <p className="text-sm text-white font-medium truncate">
                                                {engagementName || '…'}
                                            </p>
                                        </div>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => router.push(`/engagements/${preScopedEngagementId}`)}
                                        className="text-slate-400 hover:text-white shrink-0"
                                    >
                                        <ArrowLeft className="h-4 w-4 mr-1" />
                                        Back to engagement
                                    </Button>
                                </CardContent>
                            </Card>
                        ) : (
                            <Card className="border-slate-800 bg-slate-900/50">
                                <CardContent className="p-4">
                                    <label className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 block">
                                        Target Engagement
                                    </label>
                                    <select
                                        value={selectedEngagement}
                                        onChange={(e) => setSelectedEngagement(e.target.value)}
                                        className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                                    >
                                        <option value="">Select an engagement...</option>
                                        {engagements.map((eng: any) => (
                                            <option key={eng.id} value={eng.id}>{eng.name}</option>
                                        ))}
                                    </select>
                                </CardContent>
                            </Card>
                        )}

                        {/* Drop Zone */}
                        <div
                            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                            onDragLeave={() => setIsDragOver(false)}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                            className={cn(
                                'relative cursor-pointer rounded-xl border-2 border-dashed transition-all duration-300 p-16',
                                isDragOver
                                    ? 'border-primary bg-primary/5 shadow-lg shadow-primary/10'
                                    : 'border-slate-700 bg-slate-900/30 hover:border-slate-600 hover:bg-slate-900/50',
                                previewMutation.isPending && 'pointer-events-none opacity-60',
                            )}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                className="hidden"
                                accept=".nessus,.xml,.json,.jsonl,.csv,.xlsx,.xls"
                                onChange={(e) => {
                                    const file = e.target.files?.[0];
                                    if (file) handleFile(file);
                                }}
                            />

                            <div className="flex flex-col items-center gap-4">
                                {previewMutation.isPending ? (
                                    <>
                                        <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
                                            <Loader2 className="h-8 w-8 text-primary animate-spin" />
                                        </div>
                                        <p className="text-slate-300 font-medium">Parsing file...</p>
                                    </>
                                ) : (
                                    <>
                                        <div className={cn(
                                            'w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-300',
                                            isDragOver
                                                ? 'bg-primary/20 scale-110'
                                                : 'bg-slate-800'
                                        )}>
                                            <FileUp className={cn(
                                                'h-8 w-8 transition-colors',
                                                isDragOver ? 'text-primary' : 'text-slate-500'
                                            )} />
                                        </div>
                                        <div className="text-center">
                                            <p className="text-slate-300 font-medium">
                                                Drop a scanner output file here, or click to browse
                                            </p>
                                            <p className="text-slate-600 text-sm mt-1">
                                                Supports Nessus, Burp Suite, Nuclei, Nmap, CSV, and XLSX
                                            </p>
                                        </div>
                                    </>
                                )}
                            </div>
                        </div>

                        {/* Format badges */}
                        <div className="flex items-center gap-3 flex-wrap">
                            <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest">
                                Supported Formats
                            </span>
                            {FORMATS.map((f) => (
                                <Badge
                                    key={f.ext}
                                    className="bg-slate-800/50 border border-slate-700/50 text-slate-400 text-[10px] font-mono"
                                >
                                    <span className={f.color}>{f.ext}</span>
                                    <span className="text-slate-600 ml-1.5">{f.tool}</span>
                                </Badge>
                            ))}
                        </div>
                    </div>
                )}

                {/* ═══ Step 1: Preview ═══ */}
                {step === 1 && preview && (
                    <div className="space-y-4">
                        {/* Source tool + metadata */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardContent className="p-4">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <Badge className={cn('text-xs font-bold border', TOOL_BADGES[preview.source_tool]?.color || 'bg-slate-700 text-slate-300')}>
                                            {TOOL_BADGES[preview.source_tool]?.label || preview.source_tool.toUpperCase()}
                                        </Badge>
                                        <span className="text-sm text-slate-400">
                                            {selectedFile?.name}
                                        </span>
                                        <span className="text-xs text-slate-600">
                                            ({((selectedFile?.size || 0) / 1024).toFixed(0)} KB)
                                        </span>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-slate-400 hover:text-white h-7 text-xs"
                                        onClick={handleReset}
                                    >
                                        <RefreshCw className="h-3.5 w-3.5 mr-1" /> Change File
                                    </Button>
                                </div>

                                {/* Warnings */}
                                {preview.warnings.length > 0 && (
                                    <div className="mt-3 rounded-lg bg-amber-500/10 border border-amber-500/20 px-3 py-2">
                                        <div className="flex items-center gap-2 text-amber-400 text-xs font-bold mb-1">
                                            <AlertTriangle className="h-3.5 w-3.5" /> Parser Warnings
                                        </div>
                                        {preview.warnings.map((w, i) => (
                                            <p key={i} className="text-xs text-amber-300/70">{w}</p>
                                        ))}
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Summary strip */}
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                            <StatCard icon={Server} label="Assets" value={preview.assets.length} color="cyan" />
                            <StatCard icon={Bug} label="Findings" value={preview.findings.length} color="red" />
                            <StatCard icon={Layers} label="Ports" value={preview.assets.reduce((t, a) => t + a.ports.length, 0)} color="blue" />
                            <StatCard icon={Link2} label="Duplicates" value={preview.assets.filter(a => a.is_duplicate).length + preview.findings.filter(f => f.is_duplicate).length} color="amber" />
                            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
                                <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Severity</div>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'].map(s => (
                                        sevCounts[s] ? (
                                            <Badge key={s} className={cn('text-[9px] border', SEV_COLORS[s])}>
                                                {s.slice(0, 1)}: {sevCounts[s]}
                                            </Badge>
                                        ) : null
                                    ))}
                                    {Object.keys(sevCounts).length === 0 && (
                                        <span className="text-xs text-slate-600">No findings</span>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Import toggles */}
                        <div className="flex items-center gap-6">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <Switch checked={importAssets} onCheckedChange={setImportAssets} />
                                <span className="text-sm text-slate-300">Import Assets</span>
                                <Badge className="bg-slate-800 text-slate-400 text-[10px]">{selectedAssets.size} selected</Badge>
                            </label>
                            <label className="flex items-center gap-2 cursor-pointer">
                                <Switch checked={importFindings} onCheckedChange={setImportFindings} />
                                <span className="text-sm text-slate-300">Import Findings</span>
                                <Badge className="bg-slate-800 text-slate-400 text-[10px]">{selectedFindings.size} selected</Badge>
                            </label>
                        </div>

                        {/* Tab bar */}
                        <div className="flex items-center gap-1 border-b border-slate-800">
                            <button
                                onClick={() => setPreviewTab('findings')}
                                className={cn(
                                    'px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
                                    previewTab === 'findings'
                                        ? 'border-red-500 text-white'
                                        : 'border-transparent text-slate-500 hover:text-slate-300'
                                )}
                            >
                                <Bug className="h-3.5 w-3.5 inline mr-1.5 -mt-0.5" />
                                Findings ({preview.findings.length})
                            </button>
                            <button
                                onClick={() => setPreviewTab('assets')}
                                className={cn(
                                    'px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
                                    previewTab === 'assets'
                                        ? 'border-cyan-500 text-white'
                                        : 'border-transparent text-slate-500 hover:text-slate-300'
                                )}
                            >
                                <Server className="h-3.5 w-3.5 inline mr-1.5 -mt-0.5" />
                                Assets ({preview.assets.length})
                            </button>
                        </div>

                        {/* Table content */}
                        {previewTab === 'findings' && (
                            <div className="space-y-2">
                                {/* Search + select all */}
                                <div className="flex items-center gap-3">
                                    <div className="relative flex-1">
                                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
                                        <input
                                            value={searchFindings}
                                            onChange={(e) => setSearchFindings(e.target.value)}
                                            placeholder="Search findings..."
                                            className="w-full rounded-lg border border-slate-800 bg-slate-900/50 pl-9 pr-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-primary focus:outline-none"
                                        />
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-xs text-slate-400 h-7"
                                        onClick={() => {
                                            if (selectedFindings.size === preview.findings.length) {
                                                setSelectedFindings(new Set());
                                            } else {
                                                setSelectedFindings(new Set(preview.findings.map((_, i) => i)));
                                            }
                                        }}
                                    >
                                        {selectedFindings.size === preview.findings.length ? 'Deselect All' : 'Select All'}
                                    </Button>
                                </div>

                                {/* Findings table */}
                                <div className="rounded-xl border border-slate-800 overflow-hidden">
                                    <table className="w-full">
                                        <thead>
                                            <tr className="bg-slate-900/80 text-left">
                                                <th className="w-10 px-3 py-2"></th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider">Title</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider w-24">Severity</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider w-32">Category</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider w-16 text-center">CVSS</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider w-20 text-center">Assets</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider w-20">Status</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-800/50">
                                            {filteredFindings.map((f) => (
                                                <tr
                                                    key={f.index}
                                                    className={cn(
                                                        'transition-colors hover:bg-slate-800/30',
                                                        f.is_duplicate && 'opacity-60'
                                                    )}
                                                >
                                                    <td className="px-3 py-2">
                                                        <input
                                                            type="checkbox"
                                                            checked={selectedFindings.has(f.index)}
                                                            onChange={() => {
                                                                setSelectedFindings(prev => {
                                                                    const next = new Set(prev);
                                                                    next.has(f.index) ? next.delete(f.index) : next.add(f.index);
                                                                    return next;
                                                                });
                                                            }}
                                                            className="rounded border-slate-600 bg-slate-800 text-primary focus:ring-primary"
                                                        />
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        <span className="text-sm text-white line-clamp-1">{f.title}</span>
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        <SeverityBadge severity={f.severity} />
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        <span className="text-xs text-slate-400 line-clamp-1">{f.category || '—'}</span>
                                                    </td>
                                                    <td className="px-3 py-2 text-center">
                                                        <span className="text-xs text-slate-300 font-mono">
                                                            {f.cvss_score != null ? f.cvss_score.toFixed(1) : '—'}
                                                        </span>
                                                    </td>
                                                    <td className="px-3 py-2 text-center">
                                                        <span className="text-xs text-slate-400">{f.affected_asset_count}</span>
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        {f.is_duplicate && (
                                                            <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20 text-[9px]">
                                                                DUP
                                                            </Badge>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                    {filteredFindings.length === 0 && (
                                        <div className="py-12 text-center text-slate-600">
                                            <Bug className="h-8 w-8 mx-auto mb-2 opacity-40" />
                                            <p className="text-sm">{searchFindings ? 'No matching findings' : 'No findings found in this file'}</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {previewTab === 'assets' && (
                            <div className="space-y-2">
                                {/* Search + select all */}
                                <div className="flex items-center gap-3">
                                    <div className="relative flex-1">
                                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
                                        <input
                                            value={searchAssets}
                                            onChange={(e) => setSearchAssets(e.target.value)}
                                            placeholder="Search assets..."
                                            className="w-full rounded-lg border border-slate-800 bg-slate-900/50 pl-9 pr-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-primary focus:outline-none"
                                        />
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-xs text-slate-400 h-7"
                                        onClick={() => {
                                            if (selectedAssets.size === preview.assets.length) {
                                                setSelectedAssets(new Set());
                                            } else {
                                                setSelectedAssets(new Set(preview.assets.map((_, i) => i)));
                                            }
                                        }}
                                    >
                                        {selectedAssets.size === preview.assets.length ? 'Deselect All' : 'Select All'}
                                    </Button>
                                </div>

                                {/* Assets table */}
                                <div className="rounded-xl border border-slate-800 overflow-hidden">
                                    <table className="w-full">
                                        <thead>
                                            <tr className="bg-slate-900/80 text-left">
                                                <th className="w-10 px-3 py-2"></th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider">Name</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider w-28">Type</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider">Identifier</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider w-16 text-center">Ports</th>
                                                <th className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider w-20">Status</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-800/50">
                                            {filteredAssets.map((a) => (
                                                <tr
                                                    key={a.index}
                                                    className={cn(
                                                        'transition-colors hover:bg-slate-800/30',
                                                        a.is_duplicate && 'opacity-60'
                                                    )}
                                                >
                                                    <td className="px-3 py-2">
                                                        <input
                                                            type="checkbox"
                                                            checked={selectedAssets.has(a.index)}
                                                            onChange={() => {
                                                                setSelectedAssets(prev => {
                                                                    const next = new Set(prev);
                                                                    next.has(a.index) ? next.delete(a.index) : next.add(a.index);
                                                                    return next;
                                                                });
                                                            }}
                                                            className="rounded border-slate-600 bg-slate-800 text-primary focus:ring-primary"
                                                        />
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        <span className="text-sm text-white line-clamp-1">{a.name}</span>
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        <Badge className="bg-slate-800 text-slate-300 text-[10px] border-slate-700">{a.asset_type}</Badge>
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        <span className="text-xs text-slate-400 font-mono">{a.identifier}</span>
                                                    </td>
                                                    <td className="px-3 py-2 text-center">
                                                        <span className="text-xs text-slate-400">{a.ports.length}</span>
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        {a.is_duplicate && (
                                                            <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20 text-[9px]">
                                                                DUP
                                                            </Badge>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                    {filteredAssets.length === 0 && (
                                        <div className="py-12 text-center text-slate-600">
                                            <Server className="h-8 w-8 mx-auto mb-2 opacity-40" />
                                            <p className="text-sm">{searchAssets ? 'No matching assets' : 'No assets found in this file'}</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Engagement selector & commit */}
                        <div className="flex items-center justify-between pt-2">
                            <div className="flex items-center gap-3">
                                {!selectedEngagement && (
                                    <div className="flex items-center gap-2 text-amber-400 text-xs">
                                        <AlertTriangle className="h-3.5 w-3.5" />
                                        Select an engagement to import into
                                    </div>
                                )}
                                {selectedEngagement && (
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-slate-500">Importing to:</span>
                                        <Badge className="bg-primary/10 text-primary border-primary/20 text-xs">
                                            {engagementName}
                                        </Badge>
                                        <select
                                            value={selectedEngagement}
                                            onChange={(e) => setSelectedEngagement(e.target.value)}
                                            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-white focus:border-primary focus:outline-none"
                                        >
                                            <option value="">Change...</option>
                                            {engagements.map((eng: any) => (
                                                <option key={eng.id} value={eng.id}>{eng.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    className="border-slate-700 text-slate-400 hover:bg-slate-800"
                                    onClick={handleReset}
                                >
                                    <ArrowLeft className="h-4 w-4 mr-1.5" /> Back
                                </Button>
                                <Button
                                    onClick={handleCommit}
                                    disabled={
                                        !selectedEngagement ||
                                        commitMutation.isPending ||
                                        (selectedAssets.size === 0 && selectedFindings.size === 0)
                                    }
                                    className="bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
                                >
                                    {commitMutation.isPending ? (
                                        <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Importing...</>
                                    ) : (
                                        <><Upload className="h-4 w-4 mr-1.5" /> Import {selectedAssets.size + selectedFindings.size} Items</>
                                    )}
                                </Button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ═══ Step 2: Results ═══ */}
                {step === 2 && result && (
                    <div className="space-y-6">
                        {/* Success card */}
                        <Card className="border-green-500/20 bg-green-500/5">
                            <CardContent className="p-6 text-center">
                                <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mx-auto mb-4">
                                    <CheckCircle2 className="h-8 w-8 text-green-400" />
                                </div>
                                <h2 className="text-xl font-bold text-white mb-1">Import Complete</h2>
                                <p className="text-sm text-slate-400">
                                    Successfully imported {preview?.source_tool?.toUpperCase()} scan into <strong>{engagementName}</strong>
                                </p>
                            </CardContent>
                        </Card>

                        {/* Result counters */}
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                            <ResultCard label="Assets Created" value={result.assets_created} color="cyan" />
                            <ResultCard label="Assets Merged" value={result.assets_skipped} color="blue" />
                            <ResultCard label="Findings Created" value={result.findings_created} color="red" />
                            <ResultCard label="Findings Skipped" value={result.findings_skipped} color="amber" />
                            <ResultCard label="Ports Added" value={result.ports_added} color="purple" />
                            <ResultCard label="Asset Links" value={result.finding_asset_links} color="green" />
                        </div>

                        {/* Errors */}
                        {result.errors.length > 0 && (
                            <Card className="border-red-500/20 bg-red-500/5">
                                <CardContent className="p-4">
                                    <div className="flex items-center gap-2 text-red-400 text-xs font-bold mb-2">
                                        <XCircle className="h-3.5 w-3.5" /> Errors ({result.errors.length})
                                    </div>
                                    {result.errors.map((err, i) => (
                                        <p key={i} className="text-xs text-red-300/70">{err}</p>
                                    ))}
                                </CardContent>
                            </Card>
                        )}

                        {/* Actions */}
                        <div className="flex items-center justify-center gap-3 pt-2">
                            <Button
                                variant="outline"
                                className="border-slate-700 text-slate-400 hover:bg-slate-800"
                                onClick={handleReset}
                            >
                                <RefreshCw className="h-4 w-4 mr-1.5" /> Import Another
                            </Button>
                            {selectedEngagement && (
                                <>
                                    <Button
                                        variant="outline"
                                        className="border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10"
                                        onClick={() => router.push(`/assets?engagement=${selectedEngagement}`)}
                                    >
                                        <Server className="h-4 w-4 mr-1.5" /> View Assets
                                    </Button>
                                    <Button
                                        variant="outline"
                                        className="border-red-500/30 text-red-400 hover:bg-red-500/10"
                                        onClick={() => router.push(`/findings?engagement=${selectedEngagement}`)}
                                    >
                                        <Bug className="h-4 w-4 mr-1.5" /> View Findings
                                    </Button>
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </DashboardLayout>
    );
}

/* ── Sub-components ──────────────────────────────────────────────── */

function StatCard({ icon: Icon, label, value, color }: { icon: any; label: string; value: number; color: string }) {
    const colorMap: Record<string, string> = {
        cyan: 'text-cyan-400',
        red: 'text-red-400',
        blue: 'text-blue-400',
        amber: 'text-amber-400',
        purple: 'text-purple-400',
        green: 'text-green-400',
    };
    return (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
            <div className="flex items-center gap-2 mb-1">
                <Icon className={cn('h-3.5 w-3.5', colorMap[color])} />
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{label}</span>
            </div>
            <p className={cn('text-2xl font-black', colorMap[color])}>{value}</p>
        </div>
    );
}

function ResultCard({ label, value, color }: { label: string; value: number; color: string }) {
    const colorMap: Record<string, { text: string; bg: string }> = {
        cyan: { text: 'text-cyan-400', bg: 'bg-cyan-500/10' },
        red: { text: 'text-red-400', bg: 'bg-red-500/10' },
        blue: { text: 'text-blue-400', bg: 'bg-blue-500/10' },
        amber: { text: 'text-amber-400', bg: 'bg-amber-500/10' },
        purple: { text: 'text-purple-400', bg: 'bg-purple-500/10' },
        green: { text: 'text-green-400', bg: 'bg-green-500/10' },
    };
    const c = colorMap[color] || colorMap.cyan;
    return (
        <div className={cn('rounded-xl border border-slate-800 p-4 text-center', c.bg)}>
            <p className={cn('text-3xl font-black', c.text)}>{value}</p>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mt-1">{label}</p>
        </div>
    );
}

'use client';

import { useState, useMemo } from 'react';
import { useVersionHistory, useVersionSnapshot, VersionSummary } from '@/lib/hooks/use-versions';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { GitCommitHorizontal, ChevronDown, Clock, User, ArrowRight, Loader2, History, X } from 'lucide-react';
import { UserAvatar } from '@/components/ui/user-avatar';
import { cn } from '@/lib/utils';

// Human-readable field labels
const FIELD_LABELS: Record<string, string> = {
    title: 'Title',
    category: 'Category',
    description: 'Description',
    severity: 'Severity',
    status: 'Status',
    cvss_score: 'CVSS Score',
    cvss_vector: 'CVSS Vector',
    impact: 'Impact',
    technical_details: 'Technical Details',
    steps_to_reproduce: 'Steps to Reproduce',
    mitigations: 'Mitigations',
    references: 'References',
    steps: 'Steps',
    expected_result: 'Expected Result',
    actual_result: 'Actual Result',
    is_executed: 'Executed',
    is_successful: 'Successful',
    notes: 'Notes',
};

// Severity / status badge colors
const SEVERITY_COLORS: Record<string, string> = {
    CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/30',
    HIGH: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    MEDIUM: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    LOW: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    INFO: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

function timeAgo(dateStr: string) {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(dateStr).toLocaleDateString();
}

/**
 * Compute a simple line diff between two strings.
 * Returns arrays of { type, text } where type is 'add', 'remove', or 'same'.
 */
function computeLineDiff(oldText: string, newText: string) {
    const oldLines = (oldText || '').split('\n');
    const newLines = (newText || '').split('\n');

    // Simple LCS-based diff
    const m = oldLines.length;
    const n = newLines.length;

    // For very long texts, just show full old/new
    if (m + n > 500) {
        return [
            ...oldLines.map(l => ({ type: 'remove' as const, text: l })),
            ...newLines.map(l => ({ type: 'add' as const, text: l })),
        ];
    }

    // Build LCS table
    const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            dp[i][j] = oldLines[i - 1] === newLines[j - 1]
                ? dp[i - 1][j - 1] + 1
                : Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
    }

    // Backtrack
    const result: { type: 'add' | 'remove' | 'same'; text: string }[] = [];
    let i = m, j = n;
    const stack: typeof result = [];
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
            stack.push({ type: 'same', text: oldLines[i - 1] });
            i--; j--;
        } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
            stack.push({ type: 'add', text: newLines[j - 1] });
            j--;
        } else {
            stack.push({ type: 'remove', text: oldLines[i - 1] });
            i--;
        }
    }
    stack.reverse();
    return stack;
}

interface DiffFieldProps {
    field: string;
    oldValue: any;
    newValue: any;
}

function DiffField({ field, oldValue, newValue }: DiffFieldProps) {
    const label = FIELD_LABELS[field] || field;

    // Boolean fields
    if (typeof oldValue === 'boolean' || typeof newValue === 'boolean') {
        return (
            <div className="space-y-1">
                <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">{label}</h4>
                <div className="flex items-center gap-2 text-xs">
                    <span className="bg-red-500/10 text-red-400 px-2 py-0.5 rounded line-through">
                        {String(oldValue ?? 'null')}
                    </span>
                    <ArrowRight className="h-3 w-3 text-slate-600" />
                    <span className="bg-green-500/10 text-green-400 px-2 py-0.5 rounded">
                        {String(newValue ?? 'null')}
                    </span>
                </div>
            </div>
        );
    }

    // Short scalar fields (severity, status, category, numbers)
    if (
        field === 'severity' || field === 'status' || field === 'category' ||
        field === 'cvss_score' || field === 'cvss_vector' || field === 'title'
    ) {
        return (
            <div className="space-y-1">
                <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">{label}</h4>
                <div className="flex items-center gap-2 text-xs flex-wrap">
                    <Badge variant="outline" className={cn(
                        "line-through opacity-60",
                        field === 'severity' && SEVERITY_COLORS[oldValue] || 'border-red-500/30 text-red-400 bg-red-500/10'
                    )}>
                        {oldValue ?? 'empty'}
                    </Badge>
                    <ArrowRight className="h-3 w-3 text-slate-600 shrink-0" />
                    <Badge variant="outline" className={cn(
                        field === 'severity' && SEVERITY_COLORS[newValue] || 'border-green-500/30 text-green-400 bg-green-500/10'
                    )}>
                        {newValue ?? 'empty'}
                    </Badge>
                </div>
            </div>
        );
    }

    // Long text fields — line diff
    const diff = computeLineDiff(String(oldValue || ''), String(newValue || ''));
    const hasChanges = diff.some(d => d.type !== 'same');

    return (
        <div className="space-y-1">
            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">{label}</h4>
            <div className="bg-slate-950 rounded-lg border border-slate-800 overflow-hidden font-mono text-[11px] max-h-64 overflow-y-auto">
                {diff.map((line, i) => (
                    <div
                        key={i}
                        className={cn(
                            'px-3 py-0.5 leading-relaxed whitespace-pre-wrap break-all',
                            line.type === 'add' && 'bg-green-500/10 text-green-300 border-l-2 border-green-500',
                            line.type === 'remove' && 'bg-red-500/10 text-red-300 border-l-2 border-red-500 line-through opacity-60',
                            line.type === 'same' && 'text-slate-500',
                        )}
                    >
                        <span className="select-none text-slate-600 mr-2 inline-block w-4 text-right">
                            {line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' '}
                        </span>
                        {line.text || ' '}
                    </div>
                ))}
                {!hasChanges && (
                    <div className="px-3 py-2 text-slate-600 italic">No changes</div>
                )}
            </div>
        </div>
    );
}


interface VersionHistoryPanelProps {
    entityType: 'finding' | 'testcase';
    entityId: string;
    /** Current entity data for diffing */
    currentData: Record<string, any>;
}

export function VersionHistoryPanel({ entityType, entityId, currentData }: VersionHistoryPanelProps) {
    const [selectorOpen, setSelectorOpen] = useState(false);
    const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
    const [diffOpen, setDiffOpen] = useState(false);

    const { data: versions = [], isLoading } = useVersionHistory(entityType, entityId);
    const { data: selectedVersion, isLoading: snapshotLoading } = useVersionSnapshot(
        entityType, entityId, selectedVersionId,
    );

    const latestVersion = versions[0];

    const handleSelectVersion = (v: VersionSummary) => {
        setSelectedVersionId(v.id);
        setSelectorOpen(false);
        setDiffOpen(true);
    };

    // Compute which fields differ between snapshot and current
    const diffFields = useMemo(() => {
        if (!selectedVersion) return [];
        const { snapshot, changed_fields } = selectedVersion;
        // Show all tracked fields that were part of the change
        return changed_fields;
    }, [selectedVersion]);

    if (versions.length === 0 && !isLoading) return null;

    return (
        <>
            {/* GitHub-style version button */}
            <Popover open={selectorOpen} onOpenChange={setSelectorOpen}>
                <PopoverTrigger asChild>
                    <Button
                        variant="outline"
                        size="sm"
                        className="border-slate-700 text-slate-300 hover:text-white hover:border-slate-600 gap-1.5 h-8 text-xs font-mono"
                    >
                        <History className="h-3.5 w-3.5 text-primary" />
                        {isLoading ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                        ) : latestVersion ? (
                            <>
                                <span className="font-bold">v{latestVersion.version}</span>
                                <span className="text-slate-500 hidden sm:inline">· {timeAgo(latestVersion.created_at)}</span>
                            </>
                        ) : (
                            <span className="text-slate-500">No edits</span>
                        )}
                        <ChevronDown className="h-3 w-3 text-slate-500 ml-0.5" />
                    </Button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-80 p-0 bg-slate-900 border-slate-700 shadow-2xl" sideOffset={8}>
                    <div className="px-3 py-2.5 border-b border-slate-800">
                        <h3 className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                            <GitCommitHorizontal className="h-3.5 w-3.5 text-primary" />
                            Version History
                        </h3>
                        <p className="text-[10px] text-slate-500 mt-0.5">{versions.length} version{versions.length !== 1 ? 's' : ''} recorded</p>
                    </div>
                    <div className="max-h-72 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-slate-900 [&::-webkit-scrollbar-thumb]:bg-slate-700 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb:hover]:bg-slate-600" style={{ scrollbarColor: '#334155 #0f172a' }}>
                        {versions.map((v, i) => (
                            <button
                                key={v.id}
                                onClick={() => handleSelectVersion(v)}
                                className="w-full text-left px-3 py-2.5 hover:bg-slate-800/60 transition-colors border-b border-slate-800/40 last:border-0 group"
                            >
                                <div className="flex items-start gap-2.5">
                                    {/* Commit dot + line */}
                                    <div className="flex flex-col items-center mt-1">
                                        <div className={cn(
                                            "h-2.5 w-2.5 rounded-full border-2 shrink-0",
                                            i === 0
                                                ? "border-primary bg-primary/30"
                                                : "border-slate-600 bg-slate-800"
                                        )} />
                                        {i < versions.length - 1 && (
                                            <div className="w-0.5 h-full min-h-[12px] bg-slate-800 mt-0.5" />
                                        )}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center justify-between">
                                            <span className="text-xs font-bold text-white group-hover:text-primary/80 transition-colors font-mono">
                                                v{v.version}
                                            </span>
                                            <span className="text-[10px] text-slate-500 flex items-center gap-1">
                                                <Clock className="h-2.5 w-2.5" />
                                                {timeAgo(v.created_at)}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-1 mt-1">
                                            <User className="h-2.5 w-2.5 text-slate-600" />
                                            <span className="text-[10px] text-slate-400">{v.changed_by_username || 'Unknown'}</span>
                                        </div>
                                        <div className="flex flex-wrap gap-1 mt-1.5">
                                            {v.changed_fields.map(f => (
                                                <Badge key={f} variant="outline" className="text-[8px] px-1 py-0 h-4 border-primary/20 text-primary bg-primary/5 font-medium">
                                                    {FIELD_LABELS[f] || f}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </button>
                        ))}
                    </div>
                </PopoverContent>
            </Popover>

            {/* Diff dialog */}
            <Dialog open={diffOpen} onOpenChange={setDiffOpen}>
                <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto bg-slate-900 border-slate-700 p-0">
                    <DialogHeader className="px-6 pt-6 pb-4 border-b border-slate-800 sticky top-0 bg-slate-900 z-10">
                        <DialogTitle className="text-white flex items-center gap-2">
                            <GitCommitHorizontal className="h-5 w-5 text-primary" />
                            {selectedVersion ? (
                                <span>
                                    Version {selectedVersion.version}
                                    <span className="text-slate-500 font-normal text-sm ml-2">
                                        → Current
                                    </span>
                                </span>
                            ) : 'Loading...'}
                        </DialogTitle>
                        {selectedVersion && (
                            <div className="flex items-center gap-3 text-xs text-slate-400 mt-1">
                                <span className="flex items-center gap-1">
                                    <User className="h-3 w-3" />
                                    {selectedVersion.changed_by_username || 'Unknown'}
                                </span>
                                <span className="flex items-center gap-1">
                                    <Clock className="h-3 w-3" />
                                    {new Date(selectedVersion.created_at).toLocaleString()}
                                </span>
                            </div>
                        )}
                    </DialogHeader>

                    {snapshotLoading ? (
                        <div className="flex items-center justify-center py-20">
                            <Loader2 className="h-6 w-6 animate-spin text-primary" />
                        </div>
                    ) : selectedVersion ? (
                        <div className="px-6 py-4 space-y-6">
                            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.15em]">
                                Showing what changed from v{selectedVersion.version} to the current version
                            </p>
                            {diffFields.map(field => (
                                <DiffField
                                    key={field}
                                    field={field}
                                    oldValue={selectedVersion.snapshot[field]}
                                    newValue={currentData[field]}
                                />
                            ))}
                            {diffFields.length === 0 && (
                                <div className="text-center py-10 text-slate-500 text-sm">
                                    No differences to display.
                                </div>
                            )}
                        </div>
                    ) : null}
                </DialogContent>
            </Dialog>
        </>
    );
}

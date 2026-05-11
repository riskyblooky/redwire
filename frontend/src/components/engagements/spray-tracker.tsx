'use client';

import { useState, useMemo, useCallback } from 'react';
import {
    useSprayCampaigns,
    useSprayCampaign,
    useImportSpray,
    useCommitSpray,
    useDeleteSprayCampaign,
    useVaultSprayHits,
    SprayImportPreview,
    SprayResultPreview,
} from '@/lib/hooks/use-spray';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
    Dialog, DialogContent, DialogDescription, DialogFooter,
    DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
    Upload, Loader2, CheckCircle, XCircle, Lock, Shield, Crown,
    Trash2, ArrowLeft, Search, Eye, EyeOff, ChevronRight,
    AlertTriangle, Server, Target, FileText, Vault, Plus, Filter, KeyRound,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import Link from 'next/link';
import { usePermission } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';

interface SprayTrackerProps {
    engagementId: string;
}

// ── Result badge colors ─────────────────────────────────────────
const resultConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
    success: { label: 'Success', color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', icon: <CheckCircle className="h-3 w-3" /> },
    success_admin: { label: 'Admin!', color: 'bg-amber-500/10 text-amber-400 border-amber-500/20', icon: <Crown className="h-3 w-3" /> },
    failed: { label: 'Failed', color: 'bg-slate-500/10 text-slate-400 border-slate-500/20', icon: <XCircle className="h-3 w-3" /> },
    locked: { label: 'Locked', color: 'bg-red-500/10 text-red-400 border-red-500/20', icon: <Lock className="h-3 w-3" /> },
    disabled: { label: 'Disabled', color: 'bg-slate-500/10 text-slate-500 border-slate-600/20', icon: <XCircle className="h-3 w-3" /> },
};

// ── Protocol colors ─────────────────────────────────────────────
const protocolColors: Record<string, string> = {
    SMB: 'border-blue-500/30 text-blue-400',
    LDAP: 'border-primary/30 text-primary',
    RDP: 'border-cyan-500/30 text-cyan-400',
    MSSQL: 'border-orange-500/30 text-orange-400',
    WINRM: 'border-pink-500/30 text-pink-400',
    SSH: 'border-green-500/30 text-green-400',
    FTP: 'border-yellow-500/30 text-yellow-400',
};


export function SprayTracker({ engagementId }: SprayTrackerProps) {
    const { data: campaigns = [], isLoading } = useSprayCampaigns(engagementId);
    const importSpray = useImportSpray();
    const commitSpray = useCommitSpray();
    const deleteSpray = useDeleteSprayCampaign();
    const vaultHits = useVaultSprayHits();
    const canCreate = usePermission(engagementId, 'vault_create');
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // ── State ───────────────────────────────────────────────────
    const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
    const [importDialogOpen, setImportDialogOpen] = useState(false);
    const [importStep, setImportStep] = useState<'upload' | 'preview' | 'confirm'>('upload');
    const [importFile, setImportFile] = useState<File | null>(null);
    const [importPreview, setImportPreview] = useState<SprayImportPreview | null>(null);
    const [importName, setImportName] = useState('');
    const [importNotes, setImportNotes] = useState('');
    const [createMissingAssets, setCreateMissingAssets] = useState(true);
    const [isDragging, setIsDragging] = useState(false);

    // ── Import flow ─────────────────────────────────────────────
    const handleFileSelect = useCallback(async (file: File) => {
        setImportFile(file);
        try {
            const preview = await importSpray.mutateAsync({ file, engagementId });
            setImportPreview(preview);
            // Auto-generate name. Prefer the CLI target spec (recovered from
            // the log preamble) since it shows the user's actual intent
            // (e.g. "192.168.69.0/24"). When that isn't available and the
            // run touched many hosts, append the host count.
            const targetLabel = preview.target_host
                || (preview.host_count > 1 ? `${preview.host_count} hosts` : null);
            const parts = [preview.protocol, targetLabel, preview.domain].filter(Boolean);
            setImportName(parts.length ? `Spray: ${parts.join(' · ')}` : `Import: ${file.name}`);
            setImportStep('preview');
        } catch (error: any) {
            const detail = error?.response?.data?.detail || error.message;
            toast.error(`Parse failed: ${detail}`);
        }
    }, [engagementId, importSpray]);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFileSelect(file);
    }, [handleFileSelect]);

    const handleCommit = async () => {
        if (!importPreview) return;
        try {
            await commitSpray.mutateAsync({
                engagement_id: engagementId,
                name: importName || 'Unnamed Campaign',
                protocol: importPreview.protocol,
                target_host: importPreview.target_host,
                target_port: importPreview.target_port,
                target_hostname: importPreview.target_hostname,
                domain: importPreview.domain,
                password_used: importPreview.password_used,
                notes: importNotes || null,
                imported_from: importPreview.imported_from,
                create_missing_assets: createMissingAssets,
                results: importPreview.results,
            });
            toast.success('Spray campaign imported successfully');
            closeImportDialog();
        } catch (error: any) {
            toast.error(`Import failed: ${error?.response?.data?.detail || error.message}`);
        }
    };

    const closeImportDialog = () => {
        setImportDialogOpen(false);
        setImportStep('upload');
        setImportFile(null);
        setImportPreview(null);
        setImportName('');
        setImportNotes('');
        setCreateMissingAssets(true);
    };

    const handleDelete = async (campaignId: string) => {
        const confirmed = await confirm({
            title: 'Delete Spray Campaign',
            description: 'This will permanently delete this spray campaign and all its results. This cannot be undone.',
        });
        if (!confirmed) return;
        try {
            await deleteSpray.mutateAsync({ campaignId, engagementId });
            setSelectedCampaignId(null);
            toast.success('Campaign deleted');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to delete campaign'));
        }
    };

    const handleVaultHits = async (campaignId: string) => {
        try {
            const result = await vaultHits.mutateAsync({ campaignId, engagementId });
            toast.success(result.message);
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to vault hits'));
        }
    };

    // ── Render ──────────────────────────────────────────────────
    if (selectedCampaignId) {
        return (
            <>
                <ConfirmDialog />
                <CampaignDetail
                    campaignId={selectedCampaignId}
                    engagementId={engagementId}
                    onBack={() => setSelectedCampaignId(null)}
                    onDelete={handleDelete}
                    onVaultHits={handleVaultHits}
                    isVaulting={vaultHits.isPending}
                />
            </>
        );
    }

    return (
        <>
            <ConfirmDialog />
            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h3 className="text-sm font-bold text-white flex items-center gap-2">
                            <Target className="h-4 w-4 text-red-400" />
                            Spray Campaigns
                        </h3>
                        <p className="text-xs text-slate-500 mt-0.5">
                            Import NetExec/CrackMapExec spray logs
                        </p>
                    </div>
                    {canCreate && (
                        <Button
                            className="bg-primary hover:bg-primary/90 text-white rounded-xl shadow-lg shadow-primary/20"
                            onClick={() => setImportDialogOpen(true)}
                        >
                            <Upload className="h-4 w-4 mr-2" />
                            Import NetExec Log
                        </Button>
                    )}
                </div>

                {/* Campaign list */}
                {isLoading ? (
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="h-8 w-8 text-slate-500 animate-spin" />
                    </div>
                ) : campaigns.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-center">
                        <div className="p-4 rounded-2xl bg-slate-800/50 border border-slate-700 mb-4">
                            <Target className="h-10 w-10 text-slate-500" />
                        </div>
                        <p className="text-sm font-semibold text-slate-400">No spray campaigns yet</p>
                        <p className="text-xs text-slate-500 mt-1 max-w-sm">
                            Import a NetExec log file to track your password spray campaigns, auto-vault hits, and get operational analytics.
                        </p>
                        {canCreate && (
                            <Button
                                className="mt-4 bg-primary hover:bg-primary/90 text-white rounded-xl"
                                size="sm"
                                onClick={() => setImportDialogOpen(true)}
                            >
                                <Upload className="h-4 w-4 mr-2" />
                                Import Your First Log
                            </Button>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                        {campaigns.map(campaign => (
                            <Card
                                key={campaign.id}
                                className="border-slate-800 bg-slate-900/40 hover:border-indigo-500/30 transition-all cursor-pointer group"
                                onClick={() => setSelectedCampaignId(campaign.id)}
                            >
                                <CardHeader className="p-4 pb-2">
                                    <div className="flex items-center justify-between">
                                        <CardTitle className="text-sm font-bold text-white truncate max-w-[200px]">
                                            {campaign.name}
                                        </CardTitle>
                                        <ChevronRight className="h-4 w-4 text-slate-500 group-hover:text-indigo-400 transition-colors" />
                                    </div>
                                    <div className="flex items-center gap-2 mt-1">
                                        {campaign.protocol && (
                                            <Badge variant="outline" className={cn('text-[9px] uppercase tracking-wider', protocolColors[campaign.protocol] || 'border-slate-700 text-slate-400')}>
                                                {campaign.protocol}
                                            </Badge>
                                        )}
                                        {campaign.target_host && (
                                            <span className="text-[10px] text-slate-500 font-mono">{campaign.target_host}</span>
                                        )}
                                        {campaign.domain && (
                                            <span className="text-[10px] text-slate-500">{campaign.domain}</span>
                                        )}
                                    </div>
                                </CardHeader>
                                <CardContent className="p-4 pt-2">
                                    {/* Stats bar */}
                                    <div className="flex items-center gap-3 mb-2">
                                        <span className="text-[10px] text-slate-500 font-bold">{campaign.total_attempts} attempts</span>
                                    </div>
                                    <div className="flex h-2 rounded-full overflow-hidden bg-slate-800 gap-px">
                                        {campaign.successful > 0 && (
                                            <div
                                                className="bg-emerald-500 rounded-l-full transition-all"
                                                style={{ width: `${(campaign.successful / campaign.total_attempts) * 100}%` }}
                                                title={`${campaign.successful} success`}
                                            />
                                        )}
                                        {campaign.locked_out > 0 && (
                                            <div
                                                className="bg-red-500 transition-all"
                                                style={{ width: `${(campaign.locked_out / campaign.total_attempts) * 100}%` }}
                                                title={`${campaign.locked_out} locked`}
                                            />
                                        )}
                                        {campaign.failed > 0 && (
                                            <div
                                                className="bg-slate-600 rounded-r-full transition-all"
                                                style={{ width: `${(campaign.failed / campaign.total_attempts) * 100}%` }}
                                                title={`${campaign.failed} failed`}
                                            />
                                        )}
                                    </div>
                                    <div className="flex items-center justify-between mt-2">
                                        <div className="flex items-center gap-3 text-[10px]">
                                            <span className="text-emerald-400 font-bold">✓ {campaign.successful}</span>
                                            <span className="text-red-400 font-bold">🔒 {campaign.locked_out}</span>
                                            <span className="text-slate-500">✕ {campaign.failed}</span>
                                        </div>
                                        <span className="text-[9px] text-slate-600">
                                            {new Date(campaign.created_at).toLocaleDateString()}
                                        </span>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}
            </div>

            {/* ── Import Dialog ─────────────────────────────────────── */}
            <Dialog open={importDialogOpen} onOpenChange={(open) => !open && closeImportDialog()}>
                <DialogContent className="sm:max-w-2xl bg-slate-950 border-slate-800 text-white max-h-[90vh] flex flex-col">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Upload className="h-5 w-5 text-indigo-400" />
                            Import NetExec Log
                        </DialogTitle>
                        <DialogDescription asChild>
                            <div className="text-sm text-slate-400">
                                {importStep === 'upload' && 'Upload a NetExec/CrackMapExec log file to parse spray results.'}
                                {importStep === 'preview' && `Parsed ${importPreview?.total_attempts || 0} results from ${importFile?.name || 'file'}.`}
                                {importStep === 'confirm' && 'Name your campaign and confirm the import.'}
                            </div>
                        </DialogDescription>
                    </DialogHeader>

                    <div className="flex-1 min-h-0 overflow-y-auto">
                        {/* Step 1: Upload */}
                        {importStep === 'upload' && (
                            <div
                                className={cn(
                                    'border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer',
                                    isDragging
                                        ? 'border-indigo-500 bg-indigo-500/10'
                                        : 'border-slate-700 hover:border-slate-600 bg-slate-900/30',
                                    importSpray.isPending && 'opacity-50 pointer-events-none'
                                )}
                                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                                onDragLeave={() => setIsDragging(false)}
                                onDrop={handleDrop}
                                onClick={() => {
                                    const input = document.createElement('input');
                                    input.type = 'file';
                                    input.accept = '.txt,.log,.out';
                                    input.onchange = (e) => {
                                        const file = (e.target as HTMLInputElement).files?.[0];
                                        if (file) handleFileSelect(file);
                                    };
                                    input.click();
                                }}
                            >
                                {importSpray.isPending ? (
                                    <div className="flex flex-col items-center gap-3">
                                        <Loader2 className="h-10 w-10 text-indigo-400 animate-spin" />
                                        <p className="text-sm text-slate-300">Parsing log file...</p>
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center gap-3">
                                        <div className="p-4 rounded-2xl bg-slate-800 border border-slate-700">
                                            <FileText className="h-10 w-10 text-slate-400" />
                                        </div>
                                        <div>
                                            <p className="text-sm font-semibold text-white">Drop nxc log file here</p>
                                            <p className="text-xs text-slate-500 mt-1">
                                                Supports .txt, .log, .out files from <code className="text-indigo-400">nxc ... --log file.txt</code>
                                            </p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Step 2: Preview */}
                        {importStep === 'preview' && importPreview && (
                            <div className="space-y-4">
                                {/* Stats summary */}
                                <div className="grid grid-cols-4 gap-2">
                                    <StatCard label="Total" value={importPreview.total_attempts} color="text-white" />
                                    <StatCard label="Success" value={importPreview.successful} color="text-emerald-400" />
                                    <StatCard label="Locked" value={importPreview.locked_out} color="text-red-400" />
                                    <StatCard label="Failed" value={importPreview.failed} color="text-slate-400" />
                                </div>

                                {/* Campaign metadata */}
                                <div className="grid grid-cols-2 gap-2 text-xs">
                                    {importPreview.protocol && (
                                        <MetaRow label="Protocol" value={importPreview.protocol} />
                                    )}
                                    {importPreview.target_host && (
                                        <MetaRow label="Target" value={`${importPreview.target_host}:${importPreview.target_port}`} />
                                    )}
                                    {importPreview.domain && (
                                        <MetaRow label="Domain" value={importPreview.domain} />
                                    )}
                                    {importPreview.password_used && (
                                        <MetaRow label="Password" value={importPreview.password_used} masked />
                                    )}
                                </div>

                                {/* Asset linking summary */}
                                {importPreview.host_count > 0 && (
                                    <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-3 space-y-3">
                                        <div className="flex items-center gap-2 text-xs">
                                            <Server className="h-3.5 w-3.5 text-blue-400" />
                                            <span className="text-slate-400">
                                                Sprayed <span className="text-white font-semibold">{importPreview.host_count}</span> distinct {importPreview.host_count === 1 ? 'host' : 'hosts'} —{' '}
                                                <span className="text-emerald-400 font-semibold">{importPreview.matched_asset_count}</span> already in scope,{' '}
                                                <span className="text-amber-400 font-semibold">{importPreview.unmatched_hosts.length}</span> not yet inventoried.
                                            </span>
                                        </div>
                                        {importPreview.unmatched_hosts.length > 0 && (
                                            <>
                                                <div className="flex items-start justify-between gap-3">
                                                    <Label
                                                        htmlFor="create-missing-assets"
                                                        className="text-xs text-slate-300 cursor-pointer flex-1 leading-snug"
                                                    >
                                                        Auto-create the {importPreview.unmatched_hosts.length} new {importPreview.unmatched_hosts.length === 1 ? 'host' : 'hosts'} as assets and link results
                                                    </Label>
                                                    <Switch
                                                        id="create-missing-assets"
                                                        checked={createMissingAssets}
                                                        onCheckedChange={setCreateMissingAssets}
                                                        className="data-[state=checked]:bg-blue-500"
                                                    />
                                                </div>
                                                {createMissingAssets && (
                                                    <p className="text-[10px] text-slate-500 font-mono leading-relaxed line-clamp-2">
                                                        {importPreview.unmatched_hosts.slice(0, 8).join(', ')}
                                                        {importPreview.unmatched_hosts.length > 8 && ` +${importPreview.unmatched_hosts.length - 8} more`}
                                                    </p>
                                                )}
                                            </>
                                        )}
                                    </div>
                                )}

                                {/* Lockout warning */}
                                {importPreview.locked_out > 0 && (
                                    <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                                        <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                                        <span>
                                            <strong>{importPreview.locked_out}</strong> account{importPreview.locked_out > 1 ? 's' : ''} locked out during this spray.
                                        </span>
                                    </div>
                                )}

                                {/* Results table */}
                                <div className="rounded-xl border border-slate-800 overflow-hidden max-h-[300px] overflow-y-auto">
                                    <table className="w-full text-xs">
                                        <thead className="bg-slate-900/80 sticky top-0">
                                            <tr>
                                                <th className="text-left px-3 py-2 text-slate-500 font-semibold">Host</th>
                                                <th className="text-left px-3 py-2 text-slate-500 font-semibold">Username</th>
                                                <th className="text-left px-3 py-2 text-slate-500 font-semibold">Domain</th>
                                                <th className="text-left px-3 py-2 text-slate-500 font-semibold">Result</th>
                                                <th className="text-left px-3 py-2 text-slate-500 font-semibold">Status</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-800/50">
                                            {importPreview.results.map((r, i) => {
                                                const cfg = resultConfig[r.result] || resultConfig.failed;
                                                return (
                                                    <tr key={i} className={cn(
                                                        'hover:bg-slate-900/40',
                                                        r.result.startsWith('success') && 'bg-emerald-500/5',
                                                        r.result === 'locked' && 'bg-red-500/5',
                                                    )}>
                                                        <td className="px-3 py-1.5 font-mono text-slate-400 text-[11px]">{r.target_host || '—'}</td>
                                                        <td className="px-3 py-1.5 font-mono text-white">
                                                            {r.username}
                                                            {r.is_admin && <Crown className="h-3 w-3 text-amber-400 inline ml-1" />}
                                                        </td>
                                                        <td className="px-3 py-1.5 text-slate-500">{r.domain || '—'}</td>
                                                        <td className="px-3 py-1.5">
                                                            <Badge variant="outline" className={cn('text-[9px] gap-0.5', cfg.color)}>
                                                                {cfg.icon} {cfg.label}
                                                            </Badge>
                                                        </td>
                                                        <td className="px-3 py-1.5 text-slate-600 font-mono text-[10px]">{r.status_code || '—'}</td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* Step 3: Confirm */}
                        {importStep === 'confirm' && (
                            <div className="space-y-4 py-2">
                                <div className="space-y-2">
                                    <Label className="text-slate-300 text-xs">Campaign Name</Label>
                                    <Input
                                        value={importName}
                                        onChange={(e) => setImportName(e.target.value)}
                                        className="bg-slate-900 border-slate-700 text-white"
                                        placeholder="e.g. Domain Spray Round 1"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label className="text-slate-300 text-xs">Notes (optional)</Label>
                                    <Textarea
                                        value={importNotes}
                                        onChange={(e) => setImportNotes(e.target.value)}
                                        className="bg-slate-900 border-slate-700 text-white min-h-[80px]"
                                        placeholder="e.g. Sprayed after hours to avoid lockout policy..."
                                    />
                                </div>
                            </div>
                        )}
                    </div>

                    <DialogFooter className="border-t border-slate-800 pt-4">
                        {importStep === 'preview' && (
                            <div className="flex items-center justify-between w-full">
                                <Button variant="ghost" onClick={() => setImportStep('upload')} className="text-slate-400">
                                    <ArrowLeft className="h-4 w-4 mr-1" /> Re-upload
                                </Button>
                                <Button
                                    className="bg-primary hover:bg-primary/90 text-white"
                                    onClick={() => setImportStep('confirm')}
                                >
                                    Next: Name & Save <ChevronRight className="h-4 w-4 ml-1" />
                                </Button>
                            </div>
                        )}
                        {importStep === 'confirm' && (
                            <div className="flex items-center justify-between w-full">
                                <Button variant="ghost" onClick={() => setImportStep('preview')} className="text-slate-400">
                                    <ArrowLeft className="h-4 w-4 mr-1" /> Back
                                </Button>
                                <Button
                                    className="bg-emerald-600 hover:bg-emerald-500 text-white"
                                    onClick={handleCommit}
                                    disabled={commitSpray.isPending || !importName.trim()}
                                >
                                    {commitSpray.isPending ? (
                                        <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</>
                                    ) : (
                                        <><CheckCircle className="h-4 w-4 mr-2" /> Import Campaign</>
                                    )}
                                </Button>
                            </div>
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}


// ── Campaign Detail View ────────────────────────────────────────

function CampaignDetail({
    campaignId, engagementId, onBack, onDelete, onVaultHits, isVaulting
}: {
    campaignId: string;
    engagementId: string;
    onBack: () => void;
    onDelete: (id: string) => void;
    onVaultHits: (id: string) => void;
    isVaulting: boolean;
}) {
    const { data: campaign, isLoading } = useSprayCampaign(campaignId);
    const [searchQuery, setSearchQuery] = useState('');
    const [filterResult, setFilterResult] = useState<string>('all');
    const [showPassword, setShowPassword] = useState(false);

    const filteredResults = useMemo(() => {
        if (!campaign) return [];
        const q = searchQuery.toLowerCase();
        return campaign.results.filter(r => {
            const matchesSearch = !q ||
                r.username.toLowerCase().includes(q) ||
                r.domain?.toLowerCase().includes(q) ||
                r.target_host?.toLowerCase().includes(q);
            const matchesFilter = filterResult === 'all' || r.result === filterResult ||
                (filterResult === 'success' && r.result.startsWith('success'));
            return matchesSearch && matchesFilter;
        });
    }, [campaign, searchQuery, filterResult]);

    const unvaultedHits = useMemo(() => {
        if (!campaign) return 0;
        return campaign.results.filter(r => r.result.startsWith('success') && !r.vault_item_id).length;
    }, [campaign]);

    if (isLoading || !campaign) {
        return (
            <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 text-slate-500 animate-spin" />
            </div>
        );
    }

    return (
        <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Button variant="ghost" size="icon" onClick={onBack} className="h-8 w-8 text-slate-400 hover:text-white">
                        <ArrowLeft className="h-4 w-4" />
                    </Button>
                    <div>
                        <h3 className="text-sm font-bold text-white flex items-center gap-2">
                            {campaign.name}
                            {campaign.protocol && (
                                <Badge variant="outline" className={cn('text-[9px] uppercase', protocolColors[campaign.protocol] || 'border-slate-700 text-slate-400')}>
                                    {campaign.protocol}
                                </Badge>
                            )}
                        </h3>
                        <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                            {campaign.target_host && (
                                <span className="flex items-center gap-1">
                                    <Server className="h-3 w-3" /> {campaign.target_host}:{campaign.target_port}
                                </span>
                            )}
                            {campaign.domain && (
                                <span className="flex items-center gap-1">
                                    <Shield className="h-3 w-3" /> {campaign.domain}
                                </span>
                            )}
                            {campaign.imported_from && (
                                <span className="flex items-center gap-1">
                                    <FileText className="h-3 w-3" /> {campaign.imported_from}
                                </span>
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {unvaultedHits > 0 && (
                        <Button
                            size="sm"
                            className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs"
                            onClick={() => onVaultHits(campaignId)}
                            disabled={isVaulting}
                        >
                            {isVaulting ? (
                                <><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Vaulting...</>
                            ) : (
                                <><KeyRound className="h-3 w-3 mr-1" /> Vault {unvaultedHits} Hit{unvaultedHits > 1 ? 's' : ''}</>
                            )}
                        </Button>
                    )}
                    <Button
                        variant="ghost" size="icon"
                        className="h-8 w-8 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                        onClick={() => onDelete(campaignId)}
                    >
                        <Trash2 className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            {/* Stats cards */}
            <div className="grid grid-cols-5 gap-2">
                <StatCard label="Total" value={campaign.total_attempts} color="text-white" />
                <StatCard label="Success" value={campaign.successful} color="text-emerald-400" />
                <StatCard label="Locked" value={campaign.locked_out} color="text-red-400" />
                <StatCard label="Failed" value={campaign.failed} color="text-slate-400" />
                <StatCard
                    label="Password"
                    value={
                        campaign.password_used
                            ? showPassword ? campaign.password_used : '••••••••'
                            : '—'
                    }
                    color="text-indigo-400"
                    isText
                    action={campaign.password_used ? (
                        <button onClick={() => setShowPassword(p => !p)} className="text-slate-500 hover:text-white">
                            {showPassword ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                        </button>
                    ) : undefined}
                />
            </div>

            {/* Lockout warning */}
            {campaign.locked_out > 0 && (
                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                    <span><strong>{campaign.locked_out}</strong> account lockout{campaign.locked_out > 1 ? 's' : ''} detected in this campaign.</span>
                </div>
            )}

            {/* Toolbar */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1 max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                    <Input
                        placeholder="Search usernames..."
                        className="pl-9 h-9 bg-slate-900/50 border-slate-800 text-white text-xs rounded-xl"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
                <div className="flex items-center gap-1 border border-slate-700 rounded-xl overflow-hidden text-[10px]">
                    {['all', 'success', 'locked', 'failed'].map(f => (
                        <button
                            key={f}
                            className={cn(
                                'px-3 py-2 transition-colors capitalize',
                                filterResult === f
                                    ? 'bg-indigo-600 text-white'
                                    : 'bg-slate-900 text-slate-400 hover:text-white'
                            )}
                            onClick={() => setFilterResult(f)}
                        >
                            {f}
                        </button>
                    ))}
                </div>
            </div>

            {/* Results table */}
            <div className="rounded-xl border border-slate-800 overflow-hidden">
                <table className="w-full text-xs">
                    <thead className="bg-slate-900/80">
                        <tr>
                            <th className="text-left px-4 py-2.5 text-slate-500 font-semibold">Username</th>
                            <th className="text-left px-4 py-2.5 text-slate-500 font-semibold">Host</th>
                            <th className="text-left px-4 py-2.5 text-slate-500 font-semibold">Domain</th>
                            <th className="text-left px-4 py-2.5 text-slate-500 font-semibold">Result</th>
                            <th className="text-left px-4 py-2.5 text-slate-500 font-semibold">Status Code</th>
                            <th className="text-left px-4 py-2.5 text-slate-500 font-semibold">Vaulted</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/50">
                        {filteredResults.length === 0 ? (
                            <tr>
                                <td colSpan={6} className="text-center py-8 text-slate-500">
                                    No results match your filters
                                </td>
                            </tr>
                        ) : filteredResults.map(r => {
                            const cfg = resultConfig[r.result] || resultConfig.failed;
                            return (
                                <tr key={r.id} className={cn(
                                    'hover:bg-slate-900/40 transition-colors',
                                    r.result.startsWith('success') && 'bg-emerald-500/5',
                                    r.result === 'locked' && 'bg-red-500/5',
                                )}>
                                    <td className="px-4 py-2 font-mono text-white">
                                        {r.username}
                                        {r.is_admin && (
                                            <Badge variant="outline" className="ml-1.5 text-[8px] border-amber-500/30 text-amber-400 px-1 py-0">
                                                <Crown className="h-2.5 w-2.5 mr-0.5" /> ADMIN
                                            </Badge>
                                        )}
                                    </td>
                                    <td className="px-4 py-2 font-mono text-slate-400 text-[11px]">
                                        {r.target_host
                                            ? (r.asset_id
                                                ? <Link href={`/assets/${r.asset_id}`} className="hover:text-blue-400 hover:underline">{r.target_host}</Link>
                                                : r.target_host)
                                            : '—'}
                                    </td>
                                    <td className="px-4 py-2 text-slate-500">{r.domain || '—'}</td>
                                    <td className="px-4 py-2">
                                        <Badge variant="outline" className={cn('text-[9px] gap-0.5', cfg.color)}>
                                            {cfg.icon} {cfg.label}
                                        </Badge>
                                    </td>
                                    <td className="px-4 py-2 text-slate-600 font-mono text-[10px]">{r.status_code || '—'}</td>
                                    <td className="px-4 py-2">
                                        {r.vault_item_id ? (
                                            <Badge variant="outline" className="text-[9px] bg-indigo-500/10 text-indigo-400 border-indigo-500/20 gap-0.5">
                                                <Vault className="h-2.5 w-2.5" /> Vaulted
                                            </Badge>
                                        ) : r.result.startsWith('success') ? (
                                            <span className="text-[10px] text-slate-600">Pending</span>
                                        ) : null}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Notes */}
            {campaign.notes && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-4">
                    <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">Notes</p>
                    <p className="text-xs text-slate-400 whitespace-pre-wrap">{campaign.notes}</p>
                </div>
            )}
        </div>
    );
}


// ── Shared UI components ────────────────────────────────────────

function StatCard({ label, value, color, isText, action }: {
    label: string;
    value: number | string;
    color: string;
    isText?: boolean;
    action?: React.ReactNode;
}) {
    return (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3 text-center">
            <p className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">{label}</p>
            <div className="flex items-center justify-center gap-1.5 mt-1">
                <p className={cn(isText ? 'text-xs font-mono truncate max-w-[80px]' : 'text-lg font-bold', color)}>
                    {value}
                </p>
                {action}
            </div>
        </div>
    );
}

function MetaRow({ label, value, masked }: { label: string; value: string; masked?: boolean }) {
    const [show, setShow] = useState(!masked);
    return (
        <div className="flex items-center justify-between rounded-lg bg-slate-900/40 border border-slate-800 px-3 py-2">
            <span className="text-slate-500 font-semibold">{label}</span>
            <div className="flex items-center gap-1.5">
                <span className="text-white font-mono">
                    {masked && !show ? '••••••••' : value}
                </span>
                {masked && (
                    <button onClick={() => setShow(p => !p)} className="text-slate-500 hover:text-white">
                        {show ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                    </button>
                )}
            </div>
        </div>
    );
}

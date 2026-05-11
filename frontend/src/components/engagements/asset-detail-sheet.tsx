'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Edit, Trash2, FileText, Loader2, Radar, Skull, EyeOff, CheckCircle,
    CheckSquare, Sparkles, StickyNote, Bug, Server, Target, User, Clock,
    Lock, Key, Shield, Plus, X, ExternalLink, Link as LinkIcon, Globe,
} from 'lucide-react';
import { useAsset, useUpdateAsset, useDeleteAsset, useAddAssetPort, useDeleteAssetPort } from '@/lib/hooks/use-assets';
import { useFindings } from '@/lib/hooks/use-findings';
import { useNotes } from '@/lib/hooks/use-notes';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import {
    useLinkAssetToFinding, useUnlinkAssetFromFinding,
    useLinkAssetToTestCase, useUnlinkAssetFromTestCase,
    useLinkAssetToVaultItem, useUnlinkAssetFromVaultItem,
    useLinkAssetToCleanup, useUnlinkAssetFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import Link from 'next/link';

const assetTypeColors: Record<string, string> = {
    IP_ADDRESS: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    DOMAIN: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    URL: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    APPLICATION: 'bg-green-500/10 text-green-400 border-green-500/20',
    SERVER: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    NETWORK: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
    OTHER: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

const assetTypeAccentColors: Record<string, string> = {
    IP_ADDRESS: 'bg-blue-500',
    DOMAIN: 'bg-primary',
    URL: 'bg-cyan-500',
    APPLICATION: 'bg-green-500',
    SERVER: 'bg-amber-500',
    NETWORK: 'bg-pink-500',
    OTHER: 'bg-slate-500',
};

const assetTypeLabels: Record<string, string> = {
    IP_ADDRESS: 'IP Address',
    DOMAIN: 'Domain',
    URL: 'URL',
    APPLICATION: 'Application',
    SERVER: 'Server',
    NETWORK: 'Network',
    OTHER: 'Other',
};

const severityColors: Record<string, string> = {
    CRITICAL: 'bg-red-500/10 text-red-400 border-red-500/20',
    HIGH: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    MEDIUM: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    LOW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    INFO: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

interface AssetDetailSheetProps {
    assetId: string | null;
    engagementId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    /** When true, background stays interactive (no overlay, no scroll lock). */
    nonModal?: boolean;
}

export function AssetDetailSheet({ assetId, engagementId, open, onOpenChange, nonModal }: AssetDetailSheetProps) {
    const router = useRouter();

    // Radix Dialog locks body scroll even with modal={false}. Continuously clear it
    // while the non-modal panel is open using a 50ms interval to beat Radix's scheduler.
    useEffect(() => {
        if (!nonModal || !open) return;
        const unlock = () => {
            if (document.body.style.overflow) document.body.style.removeProperty('overflow');
            if (document.body.style.paddingRight) document.body.style.removeProperty('padding-right');
        };
        unlock();
        const id = setInterval(unlock, 50);
        return () => clearInterval(id);
    }, [nonModal, open]);
    const { data: asset, isLoading } = useAsset(assetId || '');
    const { data: findings = [] } = useFindings({ engagement_id: engagementId });
    const { data: allNotes = [] } = useNotes(engagementId);

    const updateAsset = useUpdateAsset();
    const deleteAsset = useDeleteAsset();
    const addPort = useAddAssetPort();
    const deletePort = useDeleteAssetPort();

    const canEdit = useCanEdit(engagementId, 'asset', asset?.created_by);
    const canDelete = useCanDelete(engagementId, 'asset', asset?.created_by);
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [showAddPort, setShowAddPort] = useState(false);
    const [newPort, setNewPort] = useState({ port_number: '', protocol: 'TCP' as 'TCP' | 'UDP', service_name: '' });
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);

    // ServiceNow CMDB enrichment data
    const [snowData, setSnowData] = useState<any>(null);
    const [snowLoading, setSnowLoading] = useState(false);
    useEffect(() => {
        if (!assetId || !open) { setSnowData(null); return; }
        let cancelled = false;
        setSnowLoading(true);
        fetch(`/api/plugins/servicenow-cmdb/enrichment/${assetId}`, { credentials: 'include' })
            .then(r => r.ok ? r.json() : null)
            .then(d => { if (!cancelled) setSnowData(d?.enrichment ?? null); })
            .catch(() => { if (!cancelled) setSnowData(null); })
            .finally(() => { if (!cancelled) setSnowLoading(false); });
        return () => { cancelled = true; };
    }, [assetId, open]);

    // Link/unlink hooks
    const linkFinding = useLinkAssetToFinding();
    const unlinkFinding = useUnlinkAssetFromFinding();
    const linkTC = useLinkAssetToTestCase();
    const unlinkTC = useUnlinkAssetFromTestCase();
    const linkVault = useLinkAssetToVaultItem();
    const unlinkVault = useUnlinkAssetFromVaultItem();
    const linkCleanup = useLinkAssetToCleanup();
    const unlinkCleanup = useUnlinkAssetFromCleanup();

    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (!asset) return;
        if (type === 'findings') await linkFinding.mutateAsync({ entityId: asset.id, resourceId });
        if (type === 'testcases') await linkTC.mutateAsync({ entityId: asset.id, resourceId });
        if (type === 'vault') await linkVault.mutateAsync({ entityId: asset.id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: asset.id, resourceId });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (!asset) return;
        if (type === 'findings') await unlinkFinding.mutateAsync({ entityId: asset.id, resourceId });
        if (type === 'testcases') await unlinkTC.mutateAsync({ entityId: asset.id, resourceId });
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: asset.id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: asset.id, resourceId });
    };

    const assetFindings = asset
        ? findings.filter((f: any) => f.asset_ids?.includes(asset.id) || f.assets?.some((a: any) => a.id === asset.id))
        : [];

    const linkedIds: LinkedIdMap = {
        findings: new Set(assetFindings.map((f: any) => f.id)),
        testcases: new Set((asset?.testcases ?? []).map((t: any) => t.id)),
        assets: new Set(),
        vault: new Set((asset?.vault_items ?? []).map((v: any) => v.id)),
        cleanup: new Set((asset?.cleanup_artifacts ?? []).map((c: any) => c.id)),
        intel: new Set(),
        infra: new Set(),
    };

    const linkedNotes = asset
        ? allNotes.filter((n: any) => n.linked_assets?.some((a: any) => a.id === asset?.id))
        : [];

    const handleToggleStatus = async (field: 'is_scanned' | 'is_pwned' | 'in_scope') => {
        if (!asset) return;
        try {
            await updateAsset.mutateAsync({ id: asset.id, [field]: !asset[field] });
        } catch (error: any) {
            toast.error(getErrorMessage(error, `Failed to update ${field.replace('_', ' ')}`));
        }
    };

    const handleDelete = async () => {
        if (!asset) return;
        const confirmed = await confirm({
            title: 'Delete Asset',
            description: 'Are you sure you want to delete this asset?',
        });
        if (!confirmed) return;
        try {
            await deleteAsset.mutateAsync(asset.id);
            onOpenChange(false);
            toast.success('Asset deleted');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to delete asset'));
        }
    };

    const handleAddPort = async () => {
        if (!asset || !newPort.port_number) return;
        try {
            await addPort.mutateAsync({
                assetId: asset.id,
                port_number: parseInt(newPort.port_number),
                protocol: newPort.protocol,
                service_name: newPort.service_name || undefined,
            });
            setNewPort({ port_number: '', protocol: 'TCP', service_name: '' });
            setShowAddPort(false);
            toast.success('Port added');
        } catch (error: any) {
            toast.error(error?.response?.data?.detail || 'Failed to add port');
        }
    };

    return (
        <>
            <ConfirmDialog />
            <Sheet open={open} onOpenChange={onOpenChange} modal={!nonModal}>
                <SheetContent
                    side="right"
                    nonModal={nonModal}
                    className="w-full sm:max-w-2xl bg-slate-950 border-slate-800 p-0 overflow-y-auto"
                >
                    {isLoading || !asset ? (
                        <div className="flex items-center justify-center h-full">
                            <VisuallyHidden><SheetTitle>Loading asset details</SheetTitle></VisuallyHidden>
                            <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        </div>
                    ) : (
                        <div className="flex flex-col h-full">
                            {/* Color accent bar */}
                            <div className={cn("h-1.5 w-full shrink-0", assetTypeAccentColors[asset.asset_type] || 'bg-slate-500')} />

                            {/* Header */}
                            <SheetHeader className="p-5 pb-0">
                                <div className="flex items-start justify-between gap-3 pr-8">
                                    <div className="min-w-0">
                                        <SheetTitle className="text-xl font-bold text-white tracking-tight truncate">
                                            {asset.name}
                                        </SheetTitle>
                                        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                                            <Badge className={cn('px-2 py-0.5 text-[10px]', assetTypeColors[asset.asset_type] || assetTypeColors.OTHER)}>
                                                {assetTypeLabels[asset.asset_type] || asset.asset_type}
                                            </Badge>
                                            <code
                                                className="text-xs font-mono text-pink-400 bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/50 cursor-pointer hover:bg-slate-700/60 transition-colors"
                                                onClick={() => {
                                                    navigator.clipboard.writeText(asset.identifier);
                                                    toast.success('Copied to clipboard');
                                                }}
                                                title="Click to copy"
                                            >
                                                {asset.identifier}
                                            </code>
                                        </div>
                                    </div>
                                </div>

                                {/* Action buttons */}
                                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-800/60">
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="border-slate-700 text-slate-300 text-xs h-8"
                                        onClick={() => {
                                            onOpenChange(false);
                                            router.push(`/assets/${asset.id}?engagementId=${engagementId}&tab=assets`);
                                        }}
                                    >
                                        <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> Full Page
                                    </Button>
                                    {canEdit && (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="border-slate-700 text-slate-300 text-xs h-8"
                                            onClick={() => {
                                                onOpenChange(false);
                                                router.push(`/assets/${asset.id}/edit?engagementId=${engagementId}&tab=assets`);
                                            }}
                                        >
                                            <Edit className="h-3.5 w-3.5 mr-1.5" /> Edit
                                        </Button>
                                    )}
                                    {canDelete && (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="border-red-500/20 text-red-400 hover:bg-red-500/10 text-xs h-8 ml-auto"
                                            onClick={handleDelete}
                                        >
                                            <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Delete
                                        </Button>
                                    )}
                                </div>
                            </SheetHeader>

                            {/* Content */}
                            <div className="flex-1 p-5 space-y-5 overflow-y-auto">

                                {/* Status Toggles */}
                                <div className="space-y-2">
                                    <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Status</h4>
                                    <div className="grid grid-cols-3 gap-2">
                                        {([
                                            { field: 'is_scanned' as const, label: 'Scanned', icon: Radar, activeColor: 'bg-blue-500/10 border-blue-500/30 text-blue-400', active: asset.is_scanned },
                                            { field: 'is_pwned' as const, label: 'Pwned', icon: Skull, activeColor: 'bg-red-500/10 border-red-500/30 text-red-400', active: asset.is_pwned },
                                            { field: 'in_scope' as const, label: 'In Scope', icon: asset.in_scope ? CheckCircle : EyeOff, activeColor: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400', active: asset.in_scope },
                                        ]).map(({ field, label, icon: Icon, activeColor, active }) => (
                                            <button
                                                key={field}
                                                onClick={() => canEdit && handleToggleStatus(field)}
                                                disabled={!canEdit}
                                                className={cn(
                                                    "flex flex-col items-center gap-1.5 p-3 rounded-lg border transition-all",
                                                    active ? activeColor : "bg-slate-800/30 border-slate-700/50 text-slate-500",
                                                    canEdit && "hover:brightness-125 cursor-pointer",
                                                    !canEdit && "cursor-default opacity-80"
                                                )}
                                            >
                                                <Icon className="h-4 w-4" />
                                                <span className="text-[10px] font-bold uppercase tracking-wider">{label}</span>
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <Separator className="bg-slate-800/60" />

                                {/* Description */}
                                {asset.description && (
                                    <>
                                        <div>
                                            <div className="flex items-center gap-2 mb-2 text-white">
                                                <FileText className="h-4 w-4 text-primary" />
                                                <h4 className="text-sm font-bold">Description</h4>
                                            </div>
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50">
                                                <MarkdownPreview value={asset.description} theme="dark" />
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Notes */}
                                {asset.notes && (
                                    <>
                                        <div>
                                            <div className="flex items-center gap-2 mb-2 text-white">
                                                <StickyNote className="h-4 w-4 text-teal-400" />
                                                <h4 className="text-sm font-bold">Internal Notes</h4>
                                            </div>
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-900/40 p-3 rounded-lg border border-slate-800/60">
                                                <MarkdownPreview value={asset.notes} theme="dark" />
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Ports */}
                                <div>
                                    <div className="flex items-center justify-between mb-2">
                                        <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">
                                            Ports {(asset.ports?.length ?? 0) > 0 && <span className="text-slate-600 ml-1">({asset.ports?.length})</span>}
                                        </h4>
                                        {canEdit && (
                                            <button
                                                onClick={() => setShowAddPort(!showAddPort)}
                                                className="text-[10px] text-primary hover:text-primary/80 transition-colors flex items-center gap-0.5"
                                            >
                                                {showAddPort ? <X className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
                                                {showAddPort ? 'Cancel' : 'Add'}
                                            </button>
                                        )}
                                    </div>

                                    {showAddPort && (
                                        <div className="mb-3 p-3 rounded-lg bg-slate-900/40 border border-slate-800/60 space-y-2">
                                            <div className="flex gap-2">
                                                <Input
                                                    type="number" placeholder="Port" min={1} max={65535}
                                                    value={newPort.port_number}
                                                    onChange={(e) => setNewPort(p => ({ ...p, port_number: e.target.value }))}
                                                    className="w-20 h-7 text-xs bg-slate-900 border-slate-700 text-white"
                                                />
                                                <Select value={newPort.protocol} onValueChange={(v: 'TCP' | 'UDP') => setNewPort(p => ({ ...p, protocol: v }))}>
                                                    <SelectTrigger className="w-20 h-7 text-xs bg-slate-900 border-slate-700 text-white">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent className="bg-slate-900 border-slate-700">
                                                        <SelectItem value="TCP">TCP</SelectItem>
                                                        <SelectItem value="UDP">UDP</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                                <Input
                                                    placeholder="Service"
                                                    value={newPort.service_name}
                                                    onChange={(e) => setNewPort(p => ({ ...p, service_name: e.target.value }))}
                                                    className="flex-1 h-7 text-xs bg-slate-900 border-slate-700 text-white"
                                                />
                                            </div>
                                            <Button
                                                size="sm" className="w-full h-7 text-xs bg-primary hover:bg-primary/90"
                                                disabled={!newPort.port_number || addPort.isPending}
                                                onClick={handleAddPort}
                                            >
                                                {addPort.isPending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Plus className="h-3 w-3 mr-1" />}
                                                Add Port
                                            </Button>
                                        </div>
                                    )}

                                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                                        {asset.ports && asset.ports.length > 0 ? (
                                            asset.ports
                                                .sort((a: any, b: any) => a.port_number - b.port_number)
                                                .map((port: any) => (
                                                    <div
                                                        key={port.id}
                                                        className="flex items-center justify-between p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 group hover:border-slate-700 transition-colors"
                                                    >
                                                        <div className="flex items-center gap-2 min-w-0">
                                                            <span className="text-xs font-mono font-bold text-cyan-400">{port.port_number}</span>
                                                            <span className="text-[9px] text-slate-500 uppercase">{port.protocol}</span>
                                                            {port.service_name && <span className="text-[10px] text-slate-400 truncate">{port.service_name}</span>}
                                                        </div>
                                                        <div className="flex items-center gap-1.5">
                                                            <Badge variant="outline" className={cn(
                                                                "text-[8px] px-1 py-0 h-4 border-none uppercase font-bold",
                                                                port.state === 'OPEN' ? 'bg-green-500/10 text-green-400' :
                                                                    port.state === 'FILTERED' ? 'bg-yellow-500/10 text-yellow-400' :
                                                                        'bg-red-500/10 text-red-400'
                                                            )}>
                                                                {port.state}
                                                            </Badge>
                                                            {canEdit && (
                                                                <button
                                                                    onClick={async () => {
                                                                        const confirmed = await confirm({
                                                                            title: 'Remove Port',
                                                                            description: `Remove port ${port.port_number}/${port.protocol.toLowerCase()}?`,
                                                                        });
                                                                        if (!confirmed) return;
                                                                        try {
                                                                            await deletePort.mutateAsync({ assetId: asset.id, portId: port.id });
                                                                            toast.success('Port removed');
                                                                        } catch { toast.error('Failed to remove port'); }
                                                                    }}
                                                                    className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 transition-all"
                                                                >
                                                                    <X className="h-3 w-3" />
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                ))
                                        ) : (
                                            <div className="text-[10px] text-slate-500 italic p-3 text-center border border-dashed border-slate-800 rounded-lg">
                                                No ports defined
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <Separator className="bg-slate-800/60" />

                                {/* ServiceNow CMDB */}
                                {(snowLoading || (snowData && snowData.results?.length > 0)) && (
                                    <>
                                        <div>
                                            <div className="flex items-center justify-between mb-2">
                                                <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                                                    <Globe className="h-3 w-3" /> ServiceNow CMDB
                                                    {snowData?.results?.length > 0 && <span className="text-slate-600 ml-1">({snowData.results.length})</span>}
                                                </h4>
                                            </div>
                                            {snowLoading ? (
                                                <div className="flex items-center justify-center py-4">
                                                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                                                </div>
                                            ) : (
                                                <div className="space-y-2">
                                                    {snowData?.results?.map((ci: any, idx: number) => (
                                                        <div key={ci.sys_id || idx} className="p-3 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-orange-500/30 transition-colors space-y-1.5">
                                                            <div className="flex items-center justify-between">
                                                                <span className="text-sm font-bold text-white">{ci.name || 'Unnamed CI'}</span>
                                                                <a
                                                                    href={ci.link}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="flex items-center gap-1 text-[10px] text-orange-400 hover:text-orange-300 font-medium transition-colors"
                                                                >
                                                                    <ExternalLink className="h-3 w-3" />
                                                                    Open in ServiceNow
                                                                </a>
                                                            </div>
                                                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                                                                {ci.class && <span className="text-slate-400"><span className="text-slate-500">Class:</span> {ci.class}</span>}
                                                                {ci.ip_address && <span className="text-slate-400"><span className="text-slate-500">IP:</span> {ci.ip_address}</span>}
                                                                {ci.fqdn && <span className="text-slate-400"><span className="text-slate-500">FQDN:</span> {ci.fqdn}</span>}
                                                                {ci.status && <span className="text-slate-400"><span className="text-slate-500">Status:</span> {ci.status}</span>}
                                                                {ci.os && <span className="text-slate-400"><span className="text-slate-500">OS:</span> {ci.os}{ci.os_version ? ` ${ci.os_version}` : ''}</span>}
                                                                {ci.location && <span className="text-slate-400"><span className="text-slate-500">Location:</span> {ci.location}</span>}
                                                                {ci.company && <span className="text-slate-400"><span className="text-slate-500">Company:</span> {ci.company}</span>}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Linked Resources header */}
                                <div className="flex items-center justify-between">
                                    <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Linked Resources</h4>
                                    {canEdit && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 px-2 text-[10px] text-indigo-400 hover:text-indigo-300 hover:bg-primary/90/10 gap-1"
                                            onClick={() => setLinkDialogOpen(true)}
                                        >
                                            <LinkIcon className="h-3 w-3" />
                                            + Link
                                        </Button>
                                    )}
                                </div>

                                {/* Associated Findings */}
                                <div>
                                    <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                        Associated Findings {assetFindings.length > 0 && <span className="text-slate-600 ml-1">({assetFindings.length})</span>}
                                    </h4>
                                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                                        {assetFindings.length > 0 ? (
                                            assetFindings.map((finding: any) => (
                                                <Link
                                                    href={`/findings/${finding.id}?engagementId=${engagementId}&tab=assets`}
                                                    key={finding.id}
                                                    className="flex items-center justify-between p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-slate-700 transition-colors group"
                                                    onClick={() => onOpenChange(false)}
                                                >
                                                    <div className="flex items-center gap-2 min-w-0">
                                                        <Badge className={cn('text-[8px] uppercase font-bold border px-1 py-0 h-4 shrink-0', severityColors[finding.severity] || severityColors.INFO)}>
                                                            {finding.severity}
                                                        </Badge>
                                                        <span className="text-xs font-bold text-white group-hover:text-primary transition-colors truncate">{finding.title}</span>
                                                    </div>
                                                </Link>
                                            ))
                                        ) : (
                                            <div className="text-[10px] text-slate-500 italic p-3 text-center border border-dashed border-slate-800 rounded-lg">
                                                No findings linked
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Linked Test Cases */}
                                {asset.testcases && asset.testcases.length > 0 && (
                                    <>
                                        <Separator className="bg-slate-800/60" />
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Linked Test Cases <span className="text-slate-600 ml-1">({asset.testcases.length})</span>
                                            </h4>
                                            <div className="space-y-1.5 max-h-40 overflow-y-auto">
                                                {asset.testcases.map((tc: any) => (
                                                    <Link
                                                        href={`/testcases/${tc.id}?engagementId=${engagementId}&tab=testcases`}
                                                        key={tc.id}
                                                        className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-emerald-500/30 transition-colors group"
                                                        onClick={() => onOpenChange(false)}
                                                    >
                                                        <CheckSquare className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                                                        <span className="text-xs font-bold text-white group-hover:text-emerald-300 truncate">{tc.title}</span>
                                                    </Link>
                                                ))}
                                            </div>
                                        </div>
                                    </>
                                )}

                                {/* Linked Vault Items */}
                                {asset.vault_items && asset.vault_items.length > 0 && (
                                    <>
                                        <Separator className="bg-slate-800/60" />
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Linked Vault Items <span className="text-slate-600 ml-1">({asset.vault_items.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {asset.vault_items.map((vi: any) => {
                                                    const VIcon = vi.item_type === 'CREDENTIAL' ? Lock : vi.item_type === 'KEY' ? Key : Shield;
                                                    const vColor = vi.item_type === 'CREDENTIAL' ? 'text-amber-400' : vi.item_type === 'KEY' ? 'text-primary' : 'text-emerald-400';
                                                    return (
                                                        <div key={vi.id} className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60">
                                                            <VIcon className={cn("h-3.5 w-3.5 shrink-0", vColor)} />
                                                            <span className="text-xs font-bold text-white truncate">{vi.name}</span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    </>
                                )}

                                {/* Linked Cleanup Artifacts */}
                                {asset.cleanup_artifacts && asset.cleanup_artifacts.length > 0 && (
                                    <>
                                        <Separator className="bg-slate-800/60" />
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Cleanup Artifacts <span className="text-slate-600 ml-1">({asset.cleanup_artifacts.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {asset.cleanup_artifacts.map((ca: any) => (
                                                    <div key={ca.id} className="flex items-center justify-between p-2 bg-slate-900/40 rounded-lg border border-slate-800/60">
                                                        <div className="flex items-center gap-2">
                                                            <Sparkles className="h-3.5 w-3.5 text-lime-400 shrink-0" />
                                                            <span className="text-xs font-bold text-white truncate">{ca.title}</span>
                                                        </div>
                                                        <Badge variant="outline" className={cn(
                                                            "text-[8px] px-1 py-0 h-4 border-none uppercase font-bold",
                                                            ca.status === 'CLEANED' ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'
                                                        )}>
                                                            {ca.status}
                                                        </Badge>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </>
                                )}

                                {/* Linked Notes */}
                                {linkedNotes.length > 0 && (
                                    <>
                                        <Separator className="bg-slate-800/60" />
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Linked Notes <span className="text-slate-600 ml-1">({linkedNotes.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {linkedNotes.map((note: any) => (
                                                    <Link
                                                        key={note.id}
                                                        href={`/engagements/${engagementId}?tab=notes&noteId=${note.id}`}
                                                        className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-teal-500/30 transition-colors group"
                                                        onClick={() => onOpenChange(false)}
                                                    >
                                                        <StickyNote className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                                                        <span className="text-xs font-medium text-slate-300 group-hover:text-teal-300 truncate">{note.title}</span>
                                                    </Link>
                                                ))}
                                            </div>
                                        </div>
                                    </>
                                )}

                                <Separator className="bg-slate-800/60" />

                                {/* Metadata */}
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <User className="h-3 w-3" /> Created By
                                        </span>
                                        <span className="text-slate-300 font-mono">{asset.created_by_username || asset.created_by?.slice(0, 8)}</span>
                                    </div>
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <Clock className="h-3 w-3" /> Added
                                        </span>
                                        <span className="text-slate-300">{new Date(asset.created_at).toLocaleString()}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </SheetContent>
            </Sheet>
            {asset && (
                <LinkEntityDialog
                    open={linkDialogOpen}
                    onOpenChange={setLinkDialogOpen}
                    engagementId={engagementId}
                    entityType="asset"
                    entityId={asset.id}
                    entityName={asset.name}
                    linkedIds={linkedIds}
                    onLink={handleEntityLink}
                    onUnlink={handleEntityUnlink}
                />
            )}
        </>
    );
}

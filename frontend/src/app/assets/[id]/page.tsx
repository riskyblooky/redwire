/**
 * assets/[id]/page.tsx — Asset Detail Page
 *
 * Read-only view of a single target asset. Layout:
 *  - Main column: description and internal notes.
 *  - Sidebar: status toggles (scanned, pwned, in-scope), port list with
 *    inline add/remove, associated findings (severity-badged links),
 *    linked test cases, vault items, cleanup artifacts, notes, and
 *    creation metadata (user + date).
 *  - Full-width discussion section at the bottom.
 *
 * Ports are colour-coded by state (open/filtered/closed) and can be
 * added or removed inline. Real-time presence via WebSocket; permission-
 * gated edit/delete actions with context-aware back navigation.
 */
'use client';

import { useParams } from '@/lib/hooks/use-params';
import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ArrowLeft, Edit, Trash2, Calendar, FileText, Loader2, Radar, Skull, EyeOff, CheckCircle, CheckSquare, Sparkles, StickyNote, Bug, Server, Target, User, Clock, Lock, Key, Shield, Network, Plus, X } from 'lucide-react';
import { useAsset, useDeleteAsset, useUpdateAsset, useAddAssetPort, useDeleteAssetPort } from '@/lib/hooks/use-assets';
import { useEngagement } from '@/lib/hooks/use-engagements';
import { toast } from 'sonner';
import { useFindings } from '@/lib/hooks/use-findings';
import { useAuthStore } from '@/stores/auth-store';
import Link from 'next/link';
import { cn, parseUTCDate } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import DiscussionSection from '@/components/discussions/discussion-section';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { UserAvatar } from '@/components/ui/user-avatar';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { CleanupDetailModal } from '@/components/engagements/cleanup-detail-modal';
import { useNotes } from '@/lib/hooks/use-notes';
import { CustomFieldsDisplay } from '@/components/custom-fields/custom-fields-display';
import { LinkEntityDialog } from '@/components/ui/link-entity-dialog';
import {
    useLinkAssetToFinding, useUnlinkAssetFromFinding,
    useLinkAssetToTestCase, useUnlinkAssetFromTestCase,
    useLinkAssetToCleanup, useUnlinkAssetFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { Link as LinkIcon } from 'lucide-react';
import { apiErrorMessage } from '@/lib/api';
import { MarkdownPreview } from '@/components/ui/markdown-editor';

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

export default function AssetDetailPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const returnEngagementId = searchParams?.get('engagementId');
    const returnTab = searchParams?.get('tab') || 'assets';
    const { user } = useAuthStore();

    const { data: asset, isLoading: isLoadingAsset, error: assetError } = useAsset(id);
    const { data: engagement } = useEngagement(asset?.engagement_id || '');
    const { data: findings = [] } = useFindings({ engagement_id: asset?.engagement_id });

    const { activeUsers } = useCollaboration({
        resourceType: 'asset',
        resourceId: id,
        enabled: !!asset
    });

    const deleteAsset = useDeleteAsset();
    const updateAsset = useUpdateAsset();
    const addPort = useAddAssetPort();
    const deletePort = useDeleteAssetPort();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const [viewCleanup, setViewCleanup] = useState<any>(null);
    const [showAddPort, setShowAddPort] = useState(false);
    const [newPort, setNewPort] = useState({ port_number: '', protocol: 'TCP' as 'TCP' | 'UDP', service_name: '' });
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);

    // Link/unlink hooks for asset
    const linkFinding = useLinkAssetToFinding();
    const unlinkFinding = useUnlinkAssetFromFinding();
    const linkTC = useLinkAssetToTestCase();
    const unlinkTC = useUnlinkAssetFromTestCase();
    const linkCleanup = useLinkAssetToCleanup();
    const unlinkCleanup = useUnlinkAssetFromCleanup();

    const handleEntityLink = async (type: import('@/components/ui/link-entity-dialog').LinkResourceType, resourceId: string) => {
        if (type === 'findings') await linkFinding.mutateAsync({ entityId: id, resourceId });
        if (type === 'testcases') await linkTC.mutateAsync({ entityId: id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: id, resourceId });
    };
    const handleEntityUnlink = async (type: import('@/components/ui/link-entity-dialog').LinkResourceType, resourceId: string) => {
        if (type === 'findings') await unlinkFinding.mutateAsync({ entityId: id, resourceId });
        if (type === 'testcases') await unlinkTC.mutateAsync({ entityId: id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: id, resourceId });
    };

    // Get notes linked to this asset
    const { data: allNotes = [] } = useNotes(asset?.engagement_id || '');
    const linkedNotes = allNotes.filter(n => n.linked_assets?.some(a => a.id === id));

    const handleToggleStatus = async (field: 'is_scanned' | 'is_pwned' | 'in_scope') => {
        if (!asset) return;
        try {
            await updateAsset.mutateAsync({
                id: asset.id,
                [field]: !asset[field],
            });
        } catch (error: any) {
            toast.error(getErrorMessage(error, `Failed to update ${field.replace('_', ' ')}`));
        }
    };

    const assetFindings = findings.filter(f => f.asset_ids?.includes(id) || f.assets?.some(a => a.id === id));

    // Check permissions for edit/delete
    const canEdit = useCanEdit(asset?.engagement_id, 'asset', asset?.created_by);
    const canDelete = useCanDelete(asset?.engagement_id, 'asset', asset?.created_by);

    const handleEdit = () => {
        const query = returnEngagementId ? `?engagementId=${returnEngagementId}&tab=${returnTab}` : '';
        router.push(`/assets/${id}/edit${query}`);
    };

    const handleDelete = async () => {
        const confirmed = await confirm({
            title: 'Delete Asset',
            description: 'Are you sure you want to delete this asset?',
        });
        if (!confirmed) return;

        try {
            await deleteAsset.mutateAsync(id);
            const redirectPath = returnEngagementId
                ? `/engagements/${returnEngagementId}?tab=${returnTab}`
                : '/assets';
            router.push(redirectPath);
        } catch (error: any) {
            console.error('Failed to delete asset:', error);
            toast.error(getErrorMessage(error, 'Failed to delete asset'));
        }
    };

    if (isLoadingAsset) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    if (assetError || !asset) {
        return (
            <DashboardLayout>
                <div className="p-6 text-center text-red-400">Asset not found.</div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                                const backPath = returnEngagementId
                                    ? `/engagements/${returnEngagementId}?tab=${returnTab}`
                                    : '/assets';
                                router.push(backPath);
                            }}
                            className="text-slate-400 hover:text-white"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <div className="flex items-center gap-3">
                                <h1 className="text-3xl font-bold text-white tracking-tight">{asset.name}</h1>
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                                <Badge className={cn('px-2 py-0.5', assetTypeColors[asset.asset_type] || assetTypeColors.OTHER)}>
                                    {assetTypeLabels[asset.asset_type] || asset.asset_type}
                                </Badge>
                                <code
                                    className="text-xs font-mono text-pink-400 bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/50 cursor-pointer hover:bg-slate-700/60 hover:text-pink-300 transition-colors"
                                    onClick={() => {
                                        navigator.clipboard.writeText(asset.identifier);
                                        toast.success('Copied to clipboard', { description: asset.identifier });
                                    }}
                                    title="Click to copy"
                                >
                                    {asset.identifier}
                                </code>
                                {engagement && (
                                    <Link href={`/engagements/${engagement.id}?tab=${returnTab}`} className="text-sm text-primary hover:underline flex items-center gap-1 ml-2">
                                        <Target className="h-3 w-3" /> {engagement.name}
                                    </Link>
                                )}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-4 relative z-30">
                        {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}
                        <div className="h-8 w-px bg-slate-800" />
                        <div className="flex gap-2">
                            {canEdit && (
                                <Button
                                    onClick={handleEdit}
                                    variant="outline"
                                    className="border-slate-700 text-slate-300"
                                >
                                    <Edit className="h-4 w-4 mr-2" /> Edit
                                </Button>
                            )}
                            {canDelete && (
                                <Button
                                    onClick={handleDelete}
                                    variant="outline"
                                    disabled={deleteAsset.isPending}
                                    className="border-red-500/20 text-red-400 hover:bg-red-500/10"
                                >
                                    {deleteAsset.isPending ? (
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    ) : (
                                        <Trash2 className="h-4 w-4 mr-2" />
                                    )}
                                    Delete
                                </Button>
                            )}
                        </div>
                    </div>
                </div>

                {/* Main Grid: 4-col like findings */}
                <div className="grid gap-6 lg:grid-cols-4">
                    {/* Main Content - 3 cols */}
                    <div className="lg:col-span-3 space-y-6">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs overflow-hidden">
                            <div className={cn("h-1.5 w-full", assetTypeAccentColors[asset.asset_type] || 'bg-slate-500')} />
                            <CardContent className="p-0">
                                <div className="p-8 space-y-10">
                                    {/* Description Section */}
                                    <section>
                                        <div className="flex items-center gap-2 mb-4 text-white">
                                            <FileText className="h-5 w-5 text-primary" />
                                            <h3 className="text-xl font-bold tracking-tight">Description</h3>
                                        </div>
                                        {asset.description
                                            ? <MarkdownPreview value={asset.description} />
                                            : <p className="text-slate-600 italic">No description provided</p>}
                                    </section>

                                    {asset.notes && (
                                        <>
                                            <Separator className="bg-slate-800/60" />

                                            {/* Internal Notes Section */}
                                            <section>
                                                <div className="flex items-center gap-2 mb-4 text-white">
                                                    <StickyNote className="h-5 w-5 text-teal-400" />
                                                    <h3 className="text-xl font-bold tracking-tight">Internal Notes</h3>
                                                </div>
                                                <div className="bg-slate-950/30 p-4 rounded-lg border border-slate-800/50">
                                                    <MarkdownPreview value={asset.notes} />
                                                </div>
                                            </section>
                                        </>
                                    )}
                                    <CustomFieldsDisplay entity="asset" value={asset.custom_fields} className="pt-2" />
                                </div>
                            </CardContent>
                        </Card>

                        {/* Ports Section — in main content area */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="flex flex-row items-center justify-between pb-3">
                                <div className="flex items-center gap-2">
                                    <Network className="h-5 w-5 text-cyan-400" />
                                    <CardTitle className="text-white text-lg tracking-tight">Ports</CardTitle>
                                    {asset.ports && asset.ports.length > 0 && (
                                        <Badge variant="secondary" className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20 text-[10px] px-1.5">
                                            {asset.ports.length}
                                        </Badge>
                                    )}
                                </div>
                                {canEdit && (
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="border-slate-700 text-slate-300 hover:text-white hover:bg-slate-800 text-xs h-8"
                                        onClick={() => setShowAddPort(!showAddPort)}
                                    >
                                        {showAddPort ? <X className="h-3.5 w-3.5 mr-1.5" /> : <Plus className="h-3.5 w-3.5 mr-1.5" />}
                                        {showAddPort ? 'Cancel' : 'Add Port'}
                                    </Button>
                                )}
                            </CardHeader>
                            <CardContent className="pt-0">
                                {/* Add Port Inline Form */}
                                {showAddPort && (
                                    <div className="mb-4 p-4 rounded-lg bg-slate-950/40 border border-slate-800/60 space-y-3">
                                        <div className="flex gap-3 items-end">
                                            <div className="flex flex-col gap-1">
                                                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Port</span>
                                                <Input
                                                    type="number" placeholder="e.g. 443" min={1} max={65535}
                                                    value={newPort.port_number}
                                                    onChange={(e) => setNewPort(p => ({ ...p, port_number: e.target.value }))}
                                                    className="w-24 h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                />
                                            </div>
                                            <div className="flex flex-col gap-1">
                                                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Protocol</span>
                                                <Select value={newPort.protocol} onValueChange={(v: 'TCP' | 'UDP') => setNewPort(p => ({ ...p, protocol: v }))}>
                                                    <SelectTrigger className="w-24 h-8 text-xs bg-slate-900 border-slate-700 text-white">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent className="bg-slate-900 border-slate-700">
                                                        <SelectItem value="TCP">TCP</SelectItem>
                                                        <SelectItem value="UDP">UDP</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div className="flex flex-col gap-1 flex-1">
                                                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Service</span>
                                                <Input
                                                    placeholder="e.g. https"
                                                    value={newPort.service_name}
                                                    onChange={(e) => setNewPort(p => ({ ...p, service_name: e.target.value }))}
                                                    className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                />
                                            </div>
                                            <Button
                                                size="sm" className="h-8 text-xs bg-primary hover:bg-primary/90 px-4"
                                                disabled={!newPort.port_number || addPort.isPending}
                                                onClick={async () => {
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
                                                        toast.error(apiErrorMessage(error, 'Failed to add port'));
                                                    }
                                                }}
                                            >
                                                {addPort.isPending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Plus className="h-3 w-3 mr-1" />}
                                                Add
                                            </Button>
                                        </div>
                                    </div>
                                )}

                                {/* Port Grid */}
                                {asset.ports && asset.ports.length > 0 ? (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                                        {asset.ports
                                            .sort((a: any, b: any) => a.port_number - b.port_number)
                                            .map((port: any) => (
                                                <div
                                                    key={port.id}
                                                    className="flex items-center justify-between p-3 bg-slate-950/40 rounded-lg border border-slate-800/60 group hover:border-cyan-500/20 transition-colors"
                                                >
                                                    <div className="flex items-center gap-3 min-w-0">
                                                        <span className="text-sm font-mono font-bold text-cyan-400">{port.port_number}</span>
                                                        <span className="text-[10px] text-slate-500 uppercase font-medium">{port.protocol}</span>
                                                        {port.service_name && (
                                                            <span className="text-xs text-slate-300 truncate">{port.service_name}</span>
                                                        )}
                                                        {port.version && (
                                                            <span className="text-[10px] text-slate-600 truncate">{port.version}</span>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <Badge
                                                            variant="outline"
                                                            className={cn(
                                                                "text-[9px] px-1.5 py-0 h-5 border-none uppercase font-bold",
                                                                port.state === 'OPEN' ? 'bg-green-500/10 text-green-400' :
                                                                    port.state === 'FILTERED' ? 'bg-yellow-500/10 text-yellow-400' :
                                                                        'bg-red-500/10 text-red-400'
                                                            )}
                                                        >
                                                            {port.state}
                                                        </Badge>
                                                        {canEdit && (
                                                            <button
                                                                onClick={async () => {
                                                                    const confirmed = await confirm({
                                                                        title: 'Remove Port',
                                                                        description: `Remove port ${port.port_number}/${port.protocol.toLowerCase()} from this asset?`,
                                                                    });
                                                                    if (!confirmed) return;
                                                                    try {
                                                                        await deletePort.mutateAsync({ assetId: asset.id, portId: port.id });
                                                                        toast.success('Port removed');
                                                                    } catch {
                                                                        toast.error('Failed to remove port');
                                                                    }
                                                                }}
                                                                className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 transition-all"
                                                            >
                                                                <X className="h-3.5 w-3.5" />
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            ))}
                                    </div>
                                ) : (
                                    <div className="text-sm text-slate-500 italic p-6 text-center border border-dashed border-slate-800 rounded-lg">
                                        No ports defined for this asset
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>

                    {/* Sidebar - 1 col */}
                    <div className="space-y-6">
                        {/* Asset Status Card */}
                        <Card className="border-slate-800 bg-slate-900/50 overflow-hidden relative h-full flex flex-col">
                            <div className="absolute top-0 right-0 p-4 opacity-5">
                                <Server className="h-24 w-24" />
                            </div>
                            <CardHeader className="pb-4">
                                <CardTitle className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Asset Status</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3 flex-1 flex flex-col">
                                {/* Scanned Toggle */}
                                <button
                                    onClick={() => canEdit && handleToggleStatus('is_scanned')}
                                    disabled={!canEdit}
                                    className={cn(
                                        "w-full flex items-center gap-3 p-2.5 rounded-lg border transition-all text-left",
                                        asset.is_scanned
                                            ? "bg-blue-500/10 border-blue-500/30 text-blue-400"
                                            : "bg-slate-800/30 border-slate-700/50 text-slate-500",
                                        canEdit && "hover:brightness-125 cursor-pointer",
                                        !canEdit && "cursor-default opacity-80"
                                    )}
                                >
                                    <Radar className={cn("h-4 w-4 shrink-0", asset.is_scanned && "animate-pulse")} />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs font-bold">Port Scanned</p>
                                        <p className="text-[9px] opacity-60">{asset.is_scanned ? 'Scanned' : 'Not scanned'}</p>
                                    </div>
                                    <div className={cn(
                                        "h-4 w-8 rounded-full transition-colors relative shrink-0",
                                        asset.is_scanned ? "bg-blue-500" : "bg-slate-700"
                                    )}>
                                        <div className={cn(
                                            "absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform",
                                            asset.is_scanned ? "translate-x-4" : "translate-x-0.5"
                                        )} />
                                    </div>
                                </button>

                                {/* Pwned Toggle */}
                                <button
                                    onClick={() => canEdit && handleToggleStatus('is_pwned')}
                                    disabled={!canEdit}
                                    className={cn(
                                        "w-full flex items-center gap-3 p-2.5 rounded-lg border transition-all text-left",
                                        asset.is_pwned
                                            ? "bg-red-500/10 border-red-500/30 text-red-400"
                                            : "bg-slate-800/30 border-slate-700/50 text-slate-500",
                                        canEdit && "hover:brightness-125 cursor-pointer",
                                        !canEdit && "cursor-default opacity-80"
                                    )}
                                >
                                    <Skull className={cn("h-4 w-4 shrink-0", asset.is_pwned && "animate-bounce")} />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs font-bold">Pwned</p>
                                        <p className="text-[9px] opacity-60">{asset.is_pwned ? 'Compromised' : 'Not compromised'}</p>
                                    </div>
                                    <div className={cn(
                                        "h-4 w-8 rounded-full transition-colors relative shrink-0",
                                        asset.is_pwned ? "bg-red-500" : "bg-slate-700"
                                    )}>
                                        <div className={cn(
                                            "absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform",
                                            asset.is_pwned ? "translate-x-4" : "translate-x-0.5"
                                        )} />
                                    </div>
                                </button>

                                {/* In Scope Toggle */}
                                <button
                                    onClick={() => canEdit && handleToggleStatus('in_scope')}
                                    disabled={!canEdit}
                                    className={cn(
                                        "w-full flex items-center gap-3 p-2.5 rounded-lg border transition-all text-left",
                                        asset.in_scope
                                            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                                            : "bg-slate-800/30 border-slate-700/50 text-slate-500",
                                        canEdit && "hover:brightness-125 cursor-pointer",
                                        !canEdit && "cursor-default opacity-80"
                                    )}
                                >
                                    {asset.in_scope ? <CheckCircle className="h-4 w-4 shrink-0" /> : <EyeOff className="h-4 w-4 shrink-0" />}
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs font-bold">In Scope</p>
                                        <p className="text-[9px] opacity-60">{asset.in_scope ? 'Within scope' : 'Out of scope'}</p>
                                    </div>
                                    <div className={cn(
                                        "h-4 w-8 rounded-full transition-colors relative shrink-0",
                                        asset.in_scope ? "bg-emerald-500" : "bg-slate-700"
                                    )}>
                                        <div className={cn(
                                            "absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform",
                                            asset.in_scope ? "translate-x-4" : "translate-x-0.5"
                                        )} />
                                    </div>
                                </button>

                                {/* Linked Resources header with + Link button */}
                                <div className="flex items-center justify-between mb-3">
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

                                {/* Linked Findings */}
                                <div>
                                    <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Associated Findings</h4>
                                    <div className="space-y-2">
                                        {assetFindings.length > 0 ? (
                                            assetFindings.map((finding) => (
                                                <Link href={`/findings/${finding.id}?engagementId=${asset.engagement_id}&tab=assets`} key={finding.id} className="flex items-center justify-between p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-slate-700 transition-colors group cursor-pointer hover:bg-slate-900/60">
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
                                    <div>
                                        <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Test Cases</h4>
                                        <div className="space-y-2">
                                            {asset.testcases.map((tc: any) => (
                                                <Link href={`/testcases/${tc.id}?engagementId=${asset.engagement_id}&tab=testcases`} key={tc.id} className="flex items-center gap-2 p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-emerald-500/30 transition-colors group">
                                                    <CheckSquare className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                                                    <span className="text-xs font-bold text-white group-hover:text-emerald-300 truncate">{tc.title}</span>
                                                </Link>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Linked Vault Items */}
                                {asset.vault_items && asset.vault_items.length > 0 && (
                                    <div>
                                        <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Vault Items</h4>
                                        <div className="space-y-2">
                                            {asset.vault_items.map((vi: any) => {
                                                const icon = vi.item_type === 'CREDENTIAL' ? <Lock className="h-3.5 w-3.5 text-amber-400 shrink-0" /> :
                                                    vi.item_type === 'KEY' ? <Key className="h-3.5 w-3.5 text-primary shrink-0" /> :
                                                        <Shield className="h-3.5 w-3.5 text-emerald-400 shrink-0" />;
                                                return (
                                                    <Link href={`/engagements/${asset.engagement_id}?tab=vault`} key={vi.id} className="flex items-center gap-2 p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-amber-500/30 transition-colors group">
                                                        {icon}
                                                        <span className="text-xs font-bold text-white group-hover:text-amber-300 truncate">{vi.name}</span>
                                                    </Link>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}

                                {/* Linked Cleanup Artifacts */}
                                {asset.cleanup_artifacts && asset.cleanup_artifacts.length > 0 && (
                                    <div>
                                        <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Cleanup Artifacts</h4>
                                        <div className="space-y-2">
                                            {asset.cleanup_artifacts.map((ca: any) => (
                                                <div key={ca.id} className="flex items-center justify-between p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 cursor-pointer hover:border-lime-500/30 hover:bg-lime-500/5 transition-colors" onClick={() => setViewCleanup(ca)}>
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
                                )}

                                {/* Linked Notes */}
                                {linkedNotes.length > 0 && (
                                    <div>
                                        <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Notes</h4>
                                        <div className="space-y-2">
                                            {linkedNotes.map(note => (
                                                <Link
                                                    key={note.id}
                                                    href={`/engagements/${asset.engagement_id}?tab=notes&noteId=${note.id}`}
                                                    className="flex items-center gap-2 p-2 rounded-lg bg-slate-950/40 border border-slate-800/60 hover:border-teal-500/30 transition-colors group"
                                                >
                                                    <StickyNote className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                                                    <span className="text-xs font-medium text-slate-300 group-hover:text-teal-300 truncate">{note.title}</span>
                                                </Link>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Metadata — pinned to bottom */}
                                <div className="mt-auto pt-4 space-y-4 border-t border-slate-800/40">
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <User className="h-3 w-3" /> Created By
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <UserAvatar
                                                user={engagement?.assigned_users?.find((u: any) => u.id === asset.created_by)}
                                                userId={asset.created_by}
                                                username={asset.created_by_username || asset.created_by}
                                                className="h-5 w-5"
                                            />
                                            <span className="text-slate-300 font-mono">
                                                {engagement?.assigned_users?.find((u: any) => u.id === asset.created_by)?.username || asset.created_by_username || asset.created_by?.slice(0, 8)}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <Clock className="h-3 w-3" /> Added
                                        </span>
                                        <span className="text-slate-300">{parseUTCDate(asset.created_at).toLocaleString()}</span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>

                {/* Discussions - Full Width */}
                <DiscussionSection
                    engagementId={asset.engagement_id}
                    resourceType="asset"
                    resourceId={id}
                    currentUserId={user?.id}
                    isAdmin={user?.role === 'admin'}
                    users={engagement?.assigned_users}
                />
            </div>
            <ConfirmDialog />
            <CleanupDetailModal
                artifact={viewCleanup}
                open={!!viewCleanup}
                onOpenChange={(open) => !open && setViewCleanup(null)}
            />
            <LinkEntityDialog
                open={linkDialogOpen}
                onOpenChange={setLinkDialogOpen}
                engagementId={asset.engagement_id}
                entityType="asset"
                entityId={id}
                entityName={asset.name}
                linkedIds={{
                    findings:  new Set(assetFindings.map((f: any) => f.id)),
                    testcases: new Set(asset.testcases?.map((t: any) => t.id) ?? []),
                    assets:    new Set(),
                    vault:     new Set(),
                    cleanup:   new Set(asset.cleanup_artifacts?.map((c: any) => c.id) ?? []),
                    intel:     new Set(),
                    infra:     new Set(),
                }}
                onLink={handleEntityLink}
                onUnlink={handleEntityUnlink}
            />
        </DashboardLayout>
    );
}

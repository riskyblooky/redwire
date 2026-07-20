/**
 * assets-tab.tsx — Engagement Assets Tab
 *
 * Server-paginated, sortable, searchable table of target assets for
 * an engagement. Supports smart search syntax ("port:80", "service:http")
 * to filter by open ports or services. Features include:
 *  - Toggle buttons per row: is_scanned, is_pwned, in_scope
 *  - CSV/TXT export with column selection dialog
 *  - Asset import via AssetImportDialog
 *  - Slide-over detail sheet (AssetDetailSheet)
 *  - Advanced filter panel with port/service dropdowns
 *  - Reverse-lookup maps to display linked findings, test cases, and notes
 *
 * Sort and search preferences are persisted to localStorage.
 * Pagination resets automatically on search/sort changes.
 */
'use client';

import { useState, useMemo, useEffect } from 'react';
import { useColumnVisibility, ColumnDef } from '@/lib/hooks/use-column-visibility';
import { CustomFieldListHeads, CustomFieldListCells, useCustomFieldListDefs, customFieldColumnDefs } from '@/components/custom-fields/custom-field-list-columns';
import { ColumnToggle } from '@/components/ui/column-toggle';
import { useRouter } from 'next/navigation';
import {
    Search, Plus, Server, Loader2, ArrowUpDown, ArrowUp, ArrowDown,
    Sparkles, MoreVertical, Trash2, Edit, MessageSquare, X,
    StickyNote, Bug, CheckSquare, Filter, Download, Upload,
    Target, Globe, LinkIcon, Box, Monitor, NetworkIcon, Radar,
    Skull, CheckCircle, EyeOff, Lock,
    ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
    Settings,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useAssets, useUpdateAsset, useDeleteAsset, useAssetPortFilters } from '@/lib/hooks/use-assets';
import { useFindings } from '@/lib/hooks/use-findings';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { useNotes } from '@/lib/hooks/use-notes';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { usePermission, useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { LinkTooltip } from '@/components/ui/link-tooltip';
import { UserAvatar } from '@/components/ui/user-avatar';
import { AssetImportDialog } from '@/components/engagements/asset-import-dialog';
import { AssetDetailSheet } from '@/components/engagements/asset-detail-sheet';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuSub,
    DropdownMenuSubTrigger,
    DropdownMenuSubContent,
    DropdownMenuPortal,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    useLinkAssetToVaultItem, useUnlinkAssetFromVaultItem,
    useLinkAssetToCleanup, useUnlinkAssetFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import {
    Tooltip as RadixTooltip,
    TooltipContent as RadixTooltipContent,
    TooltipProvider as RadixTooltipProvider,
    TooltipTrigger as RadixTooltipTrigger,
} from '@/components/ui/tooltip';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';

// ── Constants ────────────────────────────────────────────────────────
const ASSET_PAGE_SIZE = 25;

const assetTypeLabels: Record<string, string> = {
    IP_ADDRESS: 'IP', DOMAIN: 'Domain', URL: 'URL',
    APPLICATION: 'App', SERVER: 'Server', NETWORK: 'Network', OTHER: 'Other',
};

const assetTypeStyles: Record<string, { color: string; icon: any }> = {
    IP_ADDRESS: { color: 'bg-blue-500/10 text-blue-400 border-blue-500/20', icon: Target },
    DOMAIN: { color: 'bg-green-500/10 text-green-400 border-green-500/20', icon: Globe },
    URL: { color: 'bg-purple-500/10 text-purple-400 border-purple-500/20', icon: LinkIcon },
    APPLICATION: { color: 'bg-pink-500/10 text-pink-400 border-pink-500/20', icon: Box },
    SERVER: { color: 'bg-orange-500/10 text-orange-400 border-orange-500/20', icon: Monitor },
    NETWORK: { color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20', icon: NetworkIcon },
    OTHER: { color: 'bg-slate-500/10 text-slate-400 border-slate-500/20', icon: Server },
};

/**
 * Parses smart search syntax from the search input.
 * Extracts "port:N" and "service:name" tokens from the query string,
 * returning them separately from the remaining free-text search.
 */
function parseAssetSearch(input: string): { search: string; port?: number; service?: string } {
    let port: number | undefined;
    let service: string | undefined;
    let remaining = input;
    const portMatch = remaining.match(/\bport:(\d+)/i);
    if (portMatch) { port = parseInt(portMatch[1], 10); remaining = remaining.replace(portMatch[0], ''); }
    const serviceMatch = remaining.match(/\bservice:(\S+)/i);
    if (serviceMatch) { service = serviceMatch[1]; remaining = remaining.replace(serviceMatch[0], ''); }
    return { search: remaining.trim(), port, service };
}

const SortIcon = ({ field, currentField, order }: { field: string; currentField: string; order: 'asc' | 'desc' }) => {
    if (currentField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
    return order === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
};

/** Single asset table row with status toggles, linked entity tooltips, port popover, and action menu. */
const AssetRow = ({ asset, engagementId, handleToggleAssetStatus, onAddCleanup, onAddVaultItem, onFilterByPort, noteItems = [], findingItems = [], testcaseItems = [], onViewDetail, col = () => true }: any) => {
    const router = useRouter();
    const canEdit = useCanEdit(engagementId, 'asset', asset.created_by);
    const canDelete = useCanDelete(engagementId, 'asset', asset.created_by);
    const deleteAsset = useDeleteAsset();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const style = assetTypeStyles[asset.asset_type] || assetTypeStyles.OTHER;
    const TypeIcon = style.icon;
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);

    // Unified link/unlink wiring (vault + cleanup only for assets)
    const linkVault = useLinkAssetToVaultItem();
    const unlinkVault = useUnlinkAssetFromVaultItem();
    const linkCleanup = useLinkAssetToCleanup();
    const unlinkCleanup = useUnlinkAssetFromCleanup();

    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (type === 'vault') await linkVault.mutateAsync({ entityId: asset.id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: asset.id, resourceId });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: asset.id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: asset.id, resourceId });
    };

    const linkedIds: LinkedIdMap = {
        findings: new Set(),
        testcases: new Set(),
        assets: new Set(),
        vault: new Set((asset.vault_items ?? []).map((v: any) => v.id)),
        cleanup: new Set((asset.cleanup_artifacts ?? []).map((c: any) => c.id)),
        intel: new Set(),
        infra: new Set(),
    };

    return (
        <>
            <ConfirmDialog />
            <TableRow
                className={cn(
                    "border-slate-800 transition-colors cursor-pointer",
                    asset.in_scope ? "hover:bg-slate-800/50" : "opacity-40 hover:opacity-100 grayscale hover:grayscale-0 bg-slate-950/30"
                )}
                onClick={() => onViewDetail ? onViewDetail(asset.id) : router.push(`/assets/${asset.id}?engagementId=${engagementId}&tab=assets`)}
            >
                <TableCell>
                    <div className="flex flex-col">
                        <span className="font-bold text-white group-hover:text-primary transition-colors uppercase tracking-tight text-xs">
                            {asset.name}
                            {!asset.in_scope && <span className="ml-2 text-[10px] text-slate-500 italic lowercase tracking-normal">(out of scope)</span>}
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                            <span className="text-slate-400 font-mono text-xs">{asset.identifier}</span>
                            {asset.ports && asset.ports.length > 0 && (
                                <Popover>
                                    <PopoverTrigger asChild>
                                        <button
                                            className="text-[9px] font-mono text-cyan-400/80 bg-cyan-500/10 px-1.5 py-0 rounded border border-cyan-500/20 hover:bg-cyan-500/20 hover:border-cyan-500/40 transition-colors cursor-pointer"
                                            onClick={(e) => e.stopPropagation()}
                                            title="Click to filter by port"
                                        >
                                            {asset.ports.filter((p: any) => p.state === 'OPEN').length}/{asset.ports.length} ports
                                        </button>
                                    </PopoverTrigger>
                                    <PopoverContent className="w-64 p-0 bg-slate-900 border-slate-700" align="start" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
                                        <div className="px-3 py-2 border-b border-slate-800">
                                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Ports — click to filter</span>
                                        </div>
                                        <div className="max-h-48 overflow-y-auto">
                                            {asset.ports.map((p: any) => (
                                                <button
                                                    key={p.id}
                                                    className="w-full flex items-center justify-between px-3 py-1.5 text-xs hover:bg-slate-800 transition-colors cursor-pointer text-left"
                                                    onClick={(e) => { e.stopPropagation(); onFilterByPort?.(`port:${p.port_number}`); }}
                                                >
                                                    <span className="font-mono text-white">{p.port_number}/{p.protocol.toLowerCase()}</span>
                                                    {p.service_name ? (
                                                        <span
                                                            className="text-emerald-400 hover:underline cursor-pointer"
                                                            onClick={(e) => { e.stopPropagation(); onFilterByPort?.(`service:${p.service_name}`); }}
                                                        >
                                                            {p.service_name}
                                                        </span>
                                                    ) : (
                                                        <span className="text-slate-600">—</span>
                                                    )}
                                                    <Badge className={cn(
                                                        "text-[9px] px-1.5 py-0 h-4",
                                                        p.state === 'OPEN' ? 'bg-green-500/15 text-green-400 border-green-500/25' :
                                                            p.state === 'FILTERED' ? 'bg-amber-500/15 text-amber-400 border-amber-500/25' :
                                                                'bg-red-500/15 text-red-400 border-red-500/25'
                                                    )}>
                                                        {p.state}
                                                    </Badge>
                                                </button>
                                            ))}
                                        </div>
                                    </PopoverContent>
                                </Popover>
                            )}
                        </div>
                    </div>
                </TableCell>
                {col('type') && <TableCell>
                    <Badge className={cn("gap-1.5 py-1 px-2.5 font-bold text-[10px] uppercase tracking-wider border", style.color)}>
                        <TypeIcon className="h-3 w-3" />
                        {assetTypeLabels[asset.asset_type]}
                    </Badge>
                </TableCell>}
                {col('status') && <TableCell>
                    <div className="flex items-center gap-2">
                        {canEdit && (
                            <Button size="icon" variant="ghost" title={asset.is_scanned ? "Mark as Not Scanned" : "Mark as Port Scanned"}
                                onClick={(e) => { e.stopPropagation(); handleToggleAssetStatus(asset, 'is_scanned'); }}
                                className={cn("h-8 w-8 rounded-full transition-all", asset.is_scanned ? "bg-blue-500/20 text-blue-400 border border-blue-500/30 shadow-[0_0_10px_rgba(59,130,246,0.2)]" : "text-slate-600 hover:text-slate-400 hover:bg-slate-800")}
                            >
                                <Radar className={cn("h-4 w-4", asset.is_scanned && "animate-pulse")} />
                            </Button>
                        )}
                        {canEdit && (
                            <Button size="icon" variant="ghost" title={asset.is_pwned ? "Mark as Not Pwned" : "Mark as Pwned"}
                                onClick={(e) => { e.stopPropagation(); handleToggleAssetStatus(asset, 'is_pwned'); }}
                                className={cn("h-8 w-8 rounded-full transition-all", asset.is_pwned ? "bg-red-500/20 text-red-500 border border-red-500/30 shadow-[0_0_15px_rgba(239,68,68,0.3)]" : "text-slate-600 hover:text-slate-400 hover:bg-slate-800")}
                            >
                                <Skull className={cn("h-4 w-4", asset.is_pwned && "animate-bounce")} />
                            </Button>
                        )}
                        {canEdit && (
                            <Button size="icon" variant="ghost" title={asset.in_scope ? "Remove from Scope" : "Add to Scope"}
                                onClick={(e) => { e.stopPropagation(); handleToggleAssetStatus(asset, 'in_scope'); }}
                                className={cn("h-8 w-8 rounded-full transition-all", asset.in_scope ? "bg-green-500/20 text-green-500 border border-green-500/30" : "bg-slate-800/50 text-slate-500 border border-slate-700/50")}
                            >
                                {asset.in_scope ? <CheckCircle className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                            </Button>
                        )}
                    </div>
                </TableCell>}
                {col('discussions') && <TableCell>
                    {asset.unresolved_thread_count && asset.unresolved_thread_count > 0 ? (
                        <div className="flex items-center gap-2 text-amber-400">
                            <MessageSquare className="h-4 w-4" />
                            <span className="text-sm font-medium">{asset.unresolved_thread_count}</span>
                        </div>
                    ) : (
                        <span className="text-slate-600 text-sm">—</span>
                    )}
                </TableCell>}
                {col('createdBy') && <TableCell className="text-slate-300 text-sm">
                    <RadixTooltipProvider delayDuration={200}>
                        <RadixTooltip>
                            <RadixTooltipTrigger asChild>
                                <div className="w-fit">
                                    <UserAvatar user={{ id: asset.created_by, username: asset.created_by_username || 'System', profile_photo: asset.created_by_profile_photo }} className="h-7 w-7" />
                                </div>
                            </RadixTooltipTrigger>
                            <RadixTooltipContent side="top"><span className="text-xs">{asset.created_by_username || 'System'}</span></RadixTooltipContent>
                        </RadixTooltip>
                    </RadixTooltipProvider>
                </TableCell>}
                {col('created') && <TableCell className="text-slate-400">
                    <RadixTooltipProvider delayDuration={200}>
                        <RadixTooltip>
                            <RadixTooltipTrigger asChild>
                                <span className="cursor-default">{formatDistanceToNow(parseUTCDate(asset.created_at), { addSuffix: true })}</span>
                            </RadixTooltipTrigger>
                            <RadixTooltipContent side="top"><span className="text-xs">{parseUTCDate(asset.created_at).toLocaleString()}</span></RadixTooltipContent>
                        </RadixTooltip>
                    </RadixTooltipProvider>
                </TableCell>}
                {col('links') && <TableCell>
                    <div className="flex items-center gap-3">
                        <LinkTooltip icon={<Bug className="h-3.5 w-3.5" />} count={(asset.findings || findingItems).length} items={(asset.findings || findingItems).map((f: any) => ({ name: f.title || f.name, href: `/findings/${f.id}?engagementId=${engagementId}` }))} label="Findings" colorClass="text-red-400" />
                        <LinkTooltip icon={<CheckSquare className="h-3.5 w-3.5" />} count={(asset.testcases || testcaseItems).length} items={(asset.testcases || testcaseItems).map((t: any) => ({ name: t.title || t.name, href: `/engagements/${engagementId}?tab=testcases&testcaseId=${t.id}` }))} label="Test Cases" colorClass="text-emerald-400" />
                        <LinkTooltip icon={<Lock className="h-3.5 w-3.5" />} count={asset.vault_items?.length || 0} items={(asset.vault_items || []).map((v: any) => ({ name: v.name }))} label="Vault Items" colorClass="text-amber-400" />
                        <LinkTooltip icon={<Sparkles className="h-3.5 w-3.5" />} count={asset.cleanup_artifacts?.length || 0} items={(asset.cleanup_artifacts || []).map((c: any) => ({ name: c.title || c.name || 'Cleanup artifact' }))} label="Cleanup Artifacts" colorClass="text-lime-400" />
                        <LinkTooltip icon={<StickyNote className="h-3.5 w-3.5" />} count={noteItems.length} items={noteItems.map((n: any) => ({ name: n.title, href: `/engagements/${engagementId}?tab=notes&noteId=${n.id}` }))} label="Notes" colorClass="text-teal-400" />
                        {(asset.findings || findingItems).length === 0 && (asset.testcases || testcaseItems).length === 0 && !asset.vault_items?.length && !asset.cleanup_artifacts?.length && noteItems.length === 0 && (
                            <span className="text-slate-600 text-sm">—</span>
                        )}
                    </div>
                </TableCell>}
                <CustomFieldListCells entity="asset" value={asset.custom_fields} isVisible={col} />
                <TableCell className="text-right">
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-white" onClick={(e) => e.stopPropagation()}>
                                <MoreVertical className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent className="bg-slate-900 border-slate-800 text-white" align="end">
                            <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); setLinkDialogOpen(true); }}>
                                <LinkIcon className="h-4 w-4 mr-2" />Link…
                            </DropdownMenuItem>

                            <DropdownMenuSub>
                                <DropdownMenuSubTrigger className="text-slate-300 focus:bg-slate-800/50 focus:text-white data-[state=open]:bg-slate-800/50 data-[state=open]:text-white">
                                    <Plus className="h-4 w-4 mr-2" />Quick Add
                                </DropdownMenuSubTrigger>
                                <DropdownMenuPortal>
                                    <DropdownMenuSubContent className="bg-slate-900 border-slate-800 text-white">
                                        {onAddVaultItem && (
                                            <DropdownMenuItem className="text-amber-400 focus:bg-amber-500/10 focus:text-amber-400" onClick={(e) => { e.stopPropagation(); onAddVaultItem({ type: 'asset', id: asset.id, name: asset.name }); }}>
                                                <Lock className="h-4 w-4 mr-2" />Vault Item
                                            </DropdownMenuItem>
                                        )}
                                        <DropdownMenuItem className="text-lime-400 focus:bg-lime-500/10 focus:text-lime-400" onClick={(e) => { e.stopPropagation(); onAddCleanup({ type: 'asset', id: asset.id, name: asset.name }); }}>
                                            <Sparkles className="h-4 w-4 mr-2" />Cleanup Artifact
                                        </DropdownMenuItem>
                                    </DropdownMenuSubContent>
                                </DropdownMenuPortal>
                            </DropdownMenuSub>

                            <DropdownMenuSeparator className="bg-slate-800" />
                            {canEdit && (
                                <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); router.push(`/assets/${asset.id}/edit?engagementId=${engagementId}&tab=assets`); }}>
                                    <Edit className="h-4 w-4 mr-2" />Edit
                                </DropdownMenuItem>
                            )}
                            {canDelete && (
                                <DropdownMenuItem className="text-red-400 focus:bg-red-500/10 focus:text-red-400" onClick={async (e) => {
                                    e.stopPropagation();
                                    const confirmed = await confirm({ title: 'Delete Asset', description: 'Are you sure you want to delete this asset? This action cannot be undone.' });
                                    if (!confirmed) return;
                                    try { await deleteAsset.mutateAsync(asset.id); } catch (error: any) { console.error('Failed to delete asset:', error); toast.error(getErrorMessage(error, 'Failed to delete asset')); }
                                }}>
                                    <Trash2 className="h-4 w-4 mr-2" />Delete
                                </DropdownMenuItem>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </TableCell>
            </TableRow>
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
                allowedTypes={['vault', 'cleanup']}
            />
        </>
    );
};

/**
 * AssetsTab — Server-paginated assets table with smart search.
 *
 * Manages search (with debounce), pagination, sorting, export, import,
 * and detail-sheet state. Builds reverse-lookup maps from findings,
 * test cases, and notes to show linked-entity tooltips per row.
 */
interface AssetsTabPropsExtras {
    onAddVaultItem?: (target: any) => void;
}
interface AssetsTabProps extends AssetsTabPropsExtras {
    engagementId: string;
    onAddCleanup: (target: any) => void;
}

const ASSETS_COLUMNS: ColumnDef[] = [
    { key: 'name',        label: 'Name',        required: true },
    { key: 'type',        label: 'Type' },
    { key: 'status',      label: 'Status' },
    { key: 'discussions', label: 'Discussions' },
    { key: 'createdBy',   label: 'Created By' },
    { key: 'created',     label: 'Created' },
    { key: 'links',       label: 'Links' },
    { key: 'actions',     label: 'Actions',     required: true },
];

export function AssetsTab({ engagementId, onAddCleanup, onAddVaultItem }: AssetsTabProps) {
    const router = useRouter();
    const canCreateAsset = usePermission(engagementId, 'asset_create');
    const updateAsset = useUpdateAsset();

    // Search & filters
    const [search, setSearch] = useState('');
    const debouncedSearch = useDebounce(search, 500);
    const parsedSearch = useMemo(() => parseAssetSearch(debouncedSearch), [debouncedSearch]);
    const { data: portFilterOptions } = useAssetPortFilters(engagementId);
    const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
    const [assetFilters, setAssetFilters] = useState<{
        types: string[];
        scope: '' | 'in' | 'out';
        scanned: '' | 'yes' | 'no';
        pwned: '' | 'yes' | 'no';
        createdBy: string;
        dateAfter: string;
    }>({ types: [], scope: '', scanned: '', pwned: '', createdBy: '', dateAfter: '' });

    const hasAssetFilters = assetFilters.types.length > 0 || !!assetFilters.scope || !!assetFilters.scanned || !!assetFilters.pwned || !!assetFilters.createdBy || !!assetFilters.dateAfter;

    const toggleAssetType = (t: string) => setAssetFilters(prev => ({
        ...prev,
        types: prev.types.includes(t) ? prev.types.filter(v => v !== t) : [...prev.types, t],
    }));
    const clearAssetFilters = () => setAssetFilters({ types: [], scope: '', scanned: '', pwned: '', createdBy: '', dateAfter: '' });

    // Sort (persisted)
    const [sortField, setSortField] = useState<string>(() => {
        if (typeof window !== 'undefined') return localStorage.getItem('redwire_sort_engagement_assets_field') || 'name';
        return 'name';
    });
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') return (localStorage.getItem('redwire_sort_engagement_assets_order') as 'asc' | 'desc') || 'asc';
        return 'asc';
    });
    useEffect(() => { localStorage.setItem('redwire_sort_engagement_assets_field', sortField); localStorage.setItem('redwire_sort_engagement_assets_order', sortOrder); }, [sortField, sortOrder]);

    // Pagination
    const [currentPage, setCurrentPage] = useState(1);
    useEffect(() => { setCurrentPage(1); }, [debouncedSearch, sortField, sortOrder]);

    const { data: assets = [], isLoading, total: totalAssets } = useAssets({
        engagementId,
        search: parsedSearch.search || undefined,
        port: parsedSearch.port,
        service: parsedSearch.service,
        sortBy: sortField,
        sortOrder,
        skip: (currentPage - 1) * ASSET_PAGE_SIZE,
        limit: ASSET_PAGE_SIZE,
    });
    const totalPages = Math.max(1, Math.ceil(totalAssets / ASSET_PAGE_SIZE));

    // Reverse-lookup maps
    const findingsParams = useMemo(() => ({ engagement_id: engagementId }), [engagementId]);
    const { data: findings = [] } = useFindings(findingsParams);
    const { data: testcases = [] } = useTestCases(engagementId);
    const { data: notes = [] } = useNotes(engagementId);

    const notesByAsset = useMemo(() => {
        const map: Record<string, { id: string; title: string }[]> = {};
        notes.forEach((n: any) => n.linked_assets?.forEach((a: any) => { if (!map[a.id]) map[a.id] = []; map[a.id].push({ id: n.id, title: n.title }); }));
        return map;
    }, [notes]);
    const findingsByAsset = useMemo(() => {
        const map: Record<string, { count: number; items: { id: string; name: string }[] }> = {};
        findings.forEach((f: any) => { const ids = f.asset_ids || (f.assets || []).map((a: any) => a.id); ids.forEach((aid: string) => { if (!map[aid]) map[aid] = { count: 0, items: [] }; map[aid].count++; map[aid].items.push({ id: f.id, name: f.title }); }); });
        return map;
    }, [findings]);
    const testcasesByAsset = useMemo(() => {
        const map: Record<string, { count: number; items: { id: string; name: string }[] }> = {};
        (testcases || []).forEach((tc: any) => { (tc.assets || []).forEach((a: any) => { if (!map[a.id]) map[a.id] = { count: 0, items: [] }; map[a.id].count++; map[a.id].items.push({ id: tc.id, name: tc.title }); }); });
        return map;
    }, [testcases]);

    // Column visibility — merge custom-field (show_in_list) columns so they
    // appear in the ColumnToggle and can be shown/hidden like any other.
    const cfListDefs = useCustomFieldListDefs('asset');
    const assetColumns = useMemo(
        () => [...ASSETS_COLUMNS, ...customFieldColumnDefs(cfListDefs)],
        [cfListDefs],
    );
    const [visibleCols, toggleCol] = useColumnVisibility('redwire_col_assets', assetColumns);
    const col = (key: string) => visibleCols.has(key);

    // Client-side asset filtering (post server-fetch)
    const filteredAssets = useMemo(() => {
        if (!hasAssetFilters) return assets;
        return assets.filter((a: any) => {
            if (assetFilters.types.length > 0 && !assetFilters.types.includes(a.asset_type)) return false;
            if (assetFilters.scope === 'in' && !a.in_scope) return false;
            if (assetFilters.scope === 'out' && a.in_scope) return false;
            if (assetFilters.scanned === 'yes' && !a.is_scanned) return false;
            if (assetFilters.scanned === 'no' && a.is_scanned) return false;
            if (assetFilters.pwned === 'yes' && !a.is_pwned) return false;
            if (assetFilters.pwned === 'no' && a.is_pwned) return false;
            if (assetFilters.createdBy && !(a.created_by_username || '').toLowerCase().includes(assetFilters.createdBy.toLowerCase())) return false;
            if (assetFilters.dateAfter && new Date(a.created_at) < new Date(assetFilters.dateAfter)) return false;
            return true;
        });
    }, [assets, assetFilters, hasAssetFilters]);

    // Export
    const [showExportDialog, setShowExportDialog] = useState(false);
    const [exportColumns, setExportColumns] = useState({ name: true, identifier: true, type: false });
    const [isExporting, setIsExporting] = useState(false);

    // Import + detail sheet
    const [showImport, setShowImport] = useState(false);
    const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

    // View mode toggle: 'panel' = side sheet, 'page' = full page nav
    const [viewMode, setViewMode] = useState<'panel' | 'page'>(() => {
        if (typeof window !== 'undefined') return (localStorage.getItem('redwire_asset_view_mode') as 'panel' | 'page') || 'panel';
        return 'panel';
    });
    useEffect(() => { localStorage.setItem('redwire_asset_view_mode', viewMode); }, [viewMode]);

    const handleAssetClick = (assetId: string) => {
        if (viewMode === 'page') {
            router.push(`/assets/${assetId}?engagementId=${engagementId}&tab=assets`);
        } else {
            setSelectedAssetId(assetId);
        }
    };

    const handleToggleAssetStatus = async (asset: any, field: 'is_pwned' | 'is_scanned' | 'in_scope') => {
        try { await updateAsset.mutateAsync({ id: asset.id, [field]: !asset[field] }); } catch (error) { console.error(`Failed to update asset ${field}:`, error); }
    };

    const handleSort = (field: string) => {
        if (sortField === field) setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
        else { setSortField(field); setSortOrder('asc'); }
    };

    return (
        <>
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="flex flex-row items-center justify-between">
                <div>
                    <CardTitle className="text-white">Assets</CardTitle>
                    <CardDescription>Target systems and resources</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative w-64 mr-2">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
                        <Input placeholder="Search... (port:80, service:http)" className="pl-8 bg-slate-900/50 border-slate-700 text-xs h-9" value={search} onChange={(e) => setSearch(e.target.value)} />
                    </div>
                    {(parsedSearch.port !== undefined || parsedSearch.service) && (
                        <div className="flex items-center gap-1">
                            {parsedSearch.port !== undefined && (
                                <Badge variant="secondary" className="bg-cyan-500/15 text-cyan-400 border border-cyan-500/25 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-cyan-500/25" onClick={() => setSearch(prev => prev.replace(/\bport:\d+\s*/i, '').trim())}>
                                    Port: {parsedSearch.port}<X className="h-3 w-3" />
                                </Badge>
                            )}
                            {parsedSearch.service && (
                                <Badge variant="secondary" className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-emerald-500/25" onClick={() => setSearch(prev => prev.replace(/\bservice:\S+\s*/i, '').trim())}>
                                    Service: {parsedSearch.service}<X className="h-3 w-3" />
                                </Badge>
                            )}
                        </div>
                    )}
                    <Button size="icon" variant="ghost" className={cn("h-9 w-9", showAdvancedFilters || hasAssetFilters ? "text-primary bg-primary/10" : "text-slate-400 hover:text-white")} title="Advanced Filters" onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}>
                        <Filter className="h-4 w-4" />
                    </Button>
                    <ColumnToggle columns={assetColumns} visible={visibleCols} onToggle={toggleCol} />
                    <Popover>
                        <PopoverTrigger asChild>
                            <Button size="icon" variant="ghost" className="h-9 w-9 text-slate-400 hover:text-white" title="View Settings">
                                <Settings className="h-4 w-4" />
                            </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-56 p-3 bg-slate-900 border-slate-700" align="end">
                            <div className="space-y-2">
                                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">View Settings</span>
                                <label className="flex items-center gap-2.5 cursor-pointer py-1">
                                    <Checkbox
                                        checked={viewMode === 'panel'}
                                        onCheckedChange={(checked) => setViewMode(checked ? 'panel' : 'page')}
                                    />
                                    <span className="text-sm text-slate-200">Open in side panel</span>
                                </label>
                            </div>
                        </PopoverContent>
                    </Popover>
                    <Button onClick={() => setShowExportDialog(true)} size="sm" variant="outline" className="border-slate-700 text-slate-300 hover:text-white hover:bg-slate-800">
                        <Download className="h-4 w-4 mr-2" />Export
                    </Button>
                    {canCreateAsset && (
                        <>
                            <Button onClick={() => setShowImport(true)} size="sm" variant="outline" className="border-slate-700 text-slate-300 hover:text-white hover:bg-slate-800">
                                <Upload className="h-4 w-4 mr-2" />Import
                            </Button>
                            <Button onClick={() => router.push(`/assets/new?engagementId=${engagementId}`)} size="sm" className="bg-primary hover:bg-primary/90">
                                <Plus className="h-4 w-4 mr-2" />Add Asset
                            </Button>
                        </>
                    )}
                </div>
            </CardHeader>

            {/* Export Dialog */}
            <Dialog open={showExportDialog} onOpenChange={setShowExportDialog}>
                <DialogContent className="bg-slate-900 border-slate-700 max-w-sm">
                    <DialogHeader>
                        <DialogTitle className="text-white">Export Assets</DialogTitle>
                        <DialogDescription>Select columns to include. Single column exports as .txt (one per line), multiple as .csv.</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 py-2">
                        <label className="flex items-center gap-2 cursor-pointer"><Checkbox checked={exportColumns.name} onCheckedChange={(v) => setExportColumns(prev => ({ ...prev, name: !!v }))} /><span className="text-sm text-slate-200">Name</span></label>
                        <label className="flex items-center gap-2 cursor-pointer"><Checkbox checked={exportColumns.identifier} onCheckedChange={(v) => setExportColumns(prev => ({ ...prev, identifier: !!v }))} /><span className="text-sm text-slate-200">Identifier</span></label>
                        <label className="flex items-center gap-2 cursor-pointer"><Checkbox checked={exportColumns.type} onCheckedChange={(v) => setExportColumns(prev => ({ ...prev, type: !!v }))} /><span className="text-sm text-slate-200">Type</span></label>
                    </div>
                    {Object.values(exportColumns).filter(Boolean).length === 0 && <p className="text-xs text-amber-400">Select at least one column.</p>}
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowExportDialog(false)} className="border-slate-700 text-slate-300">Cancel</Button>
                        <Button
                            onClick={async () => {
                                const selectedCols = Object.entries(exportColumns).filter(([, v]) => v).map(([k]) => k);
                                if (selectedCols.length === 0) return;
                                setIsExporting(true);
                                try {
                                    const params: Record<string, string> = { limit: '10000' };
                                    if (engagementId) params.engagement_id = engagementId;
                                    if (parsedSearch.search) params.search = parsedSearch.search;
                                    if (parsedSearch.port !== undefined) params.port = String(parsedSearch.port);
                                    if (parsedSearch.service) params.service = parsedSearch.service;
                                    const { data } = await api.get<{ items: any[]; total: number }>('/assets', { params });
                                    const allExportAssets = data.items;
                                    const isSingleCol = selectedCols.length === 1;
                                    const colKey = selectedCols[0] as keyof typeof exportColumns;
                                    const fieldMap: Record<string, string> = { name: 'name', identifier: 'identifier', type: 'asset_type' };

                                    if (isSingleCol) {
                                        const lines = allExportAssets.map((a: any) => a[fieldMap[colKey]] || '').join('\n');
                                        const blob = new Blob([lines], { type: 'text/plain' });
                                        const url = URL.createObjectURL(blob);
                                        const anchor = document.createElement('a'); anchor.href = url; anchor.download = `assets_${colKey}.txt`; anchor.click();
                                        URL.revokeObjectURL(url);
                                    } else {
                                        const headers = selectedCols.map(c => c.charAt(0).toUpperCase() + c.slice(1));
                                        const rows = allExportAssets.map((a: any) => selectedCols.map(c => { const val = String(a[fieldMap[c]] || ''); return val.includes(',') || val.includes('"') ? `"${val.replace(/"/g, '""')}"` : val; }).join(','));
                                        const csv = [headers.join(','), ...rows].join('\n');
                                        const blob = new Blob([csv], { type: 'text/csv' });
                                        const url = URL.createObjectURL(blob);
                                        const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'assets_export.csv'; anchor.click();
                                        URL.revokeObjectURL(url);
                                    }
                                    setShowExportDialog(false);
                                    toast.success(`Exported ${data.items.length} assets`);
                                } catch { toast.error('Export failed'); } finally { setIsExporting(false); }
                            }}
                            disabled={Object.values(exportColumns).filter(Boolean).length === 0 || isExporting}
                            className="bg-primary hover:bg-primary/90"
                        >
                            {isExporting ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Exporting...</> : <><Download className="h-4 w-4 mr-2" />Export</>}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Active asset filter chips */}
            {hasAssetFilters && (
                <div className="px-6 pb-2 flex flex-wrap gap-1.5">
                    {assetFilters.types.map(t => (
                        <Badge key={t} className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-blue-500/20" onClick={() => toggleAssetType(t)}>
                            {assetTypeLabels[t] ?? t}<X className="h-3 w-3" />
                        </Badge>
                    ))}
                    {assetFilters.scope && (
                        <Badge className="bg-green-500/10 text-green-400 border border-green-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-green-500/20" onClick={() => setAssetFilters(p => ({ ...p, scope: '' }))}>
                            {assetFilters.scope === 'in' ? 'In Scope' : 'Out of Scope'}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    {assetFilters.scanned && (
                        <Badge className="bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-cyan-500/20" onClick={() => setAssetFilters(p => ({ ...p, scanned: '' }))}>
                            {assetFilters.scanned === 'yes' ? 'Scanned' : 'Not Scanned'}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    {assetFilters.pwned && (
                        <Badge className="bg-red-500/10 text-red-400 border border-red-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-red-500/20" onClick={() => setAssetFilters(p => ({ ...p, pwned: '' }))}>
                            {assetFilters.pwned === 'yes' ? 'Pwned' : 'Not Pwned'}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    {assetFilters.createdBy && (
                        <Badge className="bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-primary/90/20" onClick={() => setAssetFilters(p => ({ ...p, createdBy: '' }))}>
                            By: {assetFilters.createdBy}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    {assetFilters.dateAfter && (
                        <Badge className="bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-amber-500/20" onClick={() => setAssetFilters(p => ({ ...p, dateAfter: '' }))}>
                            After: {assetFilters.dateAfter}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    <button className="text-[10px] text-slate-500 hover:text-slate-300 ml-1 underline" onClick={clearAssetFilters}>Clear all</button>
                </div>
            )}

            {/* Advanced filters */}
            {showAdvancedFilters && (
                <div className="px-6 pb-4 border-b border-slate-800">
                    <div className="flex items-center gap-3">
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Port</span>
                            <Select value={parsedSearch.port !== undefined ? String(parsedSearch.port) : '__none__'} onValueChange={(val) => { let s = search.replace(/\bport:\d+\s*/i, '').trim(); if (val !== '__none__') s = `port:${val} ${s}`.trim(); setSearch(s); }}>
                                <SelectTrigger className="w-32 h-8 text-xs bg-slate-800/50 border-slate-700"><SelectValue placeholder="Any port" /></SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-700">
                                    <SelectItem value="__none__">Any port</SelectItem>
                                    {portFilterOptions?.ports?.map((p: any) => (<SelectItem key={`${p.port_number}-${p.protocol}`} value={String(p.port_number)}>{p.port_number}/{p.protocol.toLowerCase()}</SelectItem>))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Service</span>
                            <Select value={parsedSearch.service || '__none__'} onValueChange={(val) => { let s = search.replace(/\bservice:\S+\s*/i, '').trim(); if (val !== '__none__') s = `service:${val} ${s}`.trim(); setSearch(s); }}>
                                <SelectTrigger className="w-40 h-8 text-xs bg-slate-800/50 border-slate-700"><SelectValue placeholder="Any service" /></SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-700">
                                    <SelectItem value="__none__">Any service</SelectItem>
                                    {portFilterOptions?.services?.map((s: any) => (<SelectItem key={s} value={s}>{s}</SelectItem>))}
                                </SelectContent>
                            </Select>
                        </div>
                        {/* Asset Type */}
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Type</span>
                            <div className="flex flex-wrap gap-x-2 gap-y-1 max-w-[280px]">
                                {Object.entries(assetTypeLabels).map(([key, label]) => (
                                    <label key={key} className="flex items-center gap-1.5 cursor-pointer">
                                        <Checkbox checked={assetFilters.types.includes(key)} onCheckedChange={() => toggleAssetType(key)} className="h-3.5 w-3.5" />
                                        <span className="text-xs text-slate-300">{label}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                        {/* Scope */}
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Scope</span>
                            <div className="flex gap-1">
                                {(['', 'in', 'out'] as const).map(v => (
                                    <button key={v} onClick={() => setAssetFilters(p => ({ ...p, scope: v }))} className={cn('px-2 py-1 rounded text-xs font-medium transition-colors', assetFilters.scope === v ? 'bg-green-500/20 text-green-300 border border-green-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700 hover:text-white')}>
                                        {v === '' ? 'All' : v === 'in' ? 'In' : 'Out'}
                                    </button>
                                ))}
                            </div>
                        </div>
                        {/* Scanned */}
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Scanned</span>
                            <div className="flex gap-1">
                                {(['', 'yes', 'no'] as const).map(v => (
                                    <button key={v} onClick={() => setAssetFilters(p => ({ ...p, scanned: v }))} className={cn('px-2 py-1 rounded text-xs font-medium transition-colors', assetFilters.scanned === v ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700 hover:text-white')}>
                                        {v === '' ? 'All' : v === 'yes' ? 'Yes' : 'No'}
                                    </button>
                                ))}
                            </div>
                        </div>
                        {/* Pwned */}
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Pwned</span>
                            <div className="flex gap-1">
                                {(['', 'yes', 'no'] as const).map(v => (
                                    <button key={v} onClick={() => setAssetFilters(p => ({ ...p, pwned: v }))} className={cn('px-2 py-1 rounded text-xs font-medium transition-colors', assetFilters.pwned === v ? 'bg-red-500/20 text-red-300 border border-red-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700 hover:text-white')}>
                                        {v === '' ? 'All' : v === 'yes' ? 'Yes' : 'No'}
                                    </button>
                                ))}
                            </div>
                        </div>
                        {/* Created By */}
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Created By</span>
                            <input type="text" placeholder="username..." value={assetFilters.createdBy} onChange={e => setAssetFilters(p => ({ ...p, createdBy: e.target.value }))} className="h-7 text-xs bg-slate-800/50 border border-slate-700 rounded px-2 text-white placeholder:text-slate-600 focus:outline-none focus:border-primary w-28" />
                        </div>
                        {/* Date After */}
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Created After</span>
                            <input type="date" value={assetFilters.dateAfter} onChange={e => setAssetFilters(p => ({ ...p, dateAfter: e.target.value }))} className="h-7 text-xs bg-slate-800/50 border border-slate-700 rounded px-2 text-white focus:outline-none focus:border-primary w-36 [color-scheme:dark]" />
                        </div>
                        {(parsedSearch.port !== undefined || parsedSearch.service || hasAssetFilters) && (
                            <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white mt-4 text-xs" onClick={() => { setSearch(prev => prev.replace(/\bport:\d+\s*/i, '').replace(/\bservice:\S+\s*/i, '').trim()); clearAssetFilters(); }}>Clear all</Button>
                        )}
                    </div>
                </div>
            )}

            <CardContent>
                {isLoading ? (
                    <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
                ) : assets.length === 0 ? (
                    <div className="text-center py-8 text-slate-400"><Server className="h-12 w-12 mx-auto mb-4 opacity-50" /><p>No assets defined</p></div>
                ) : filteredAssets.length === 0 ? (
                    <div className="text-center py-8 text-slate-400"><Server className="h-12 w-12 mx-auto mb-4 opacity-50" /><p>No assets match the current filters</p></div>
                ) : (
                    <div className="overflow-x-auto">
                        <Table>
                            <TableHeader>
                                <TableRow className="border-slate-800 hover:bg-transparent">
                                    <TableHead className="text-slate-400 w-[200px] cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('name')}>
                                        <div className="flex items-center">Name <SortIcon field="name" currentField={sortField} order={sortOrder} /></div>
                                    </TableHead>
                                    {col('type') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('asset_type')}><div className="flex items-center">Type <SortIcon field="asset_type" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                    {col('status') && <TableHead className="text-slate-400">Status</TableHead>}
                                    {col('discussions') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('unresolved_thread_count')}><div className="flex items-center">Discussions <SortIcon field="unresolved_thread_count" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                    {col('createdBy') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('created_by_username')}><div className="flex items-center">Created By <SortIcon field="created_by_username" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                    {col('created') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('created_at')}><div className="flex items-center">Created <SortIcon field="created_at" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                    {col('links') && <TableHead className="text-slate-400">Links</TableHead>}
                                    <CustomFieldListHeads entity="asset" isVisible={col} sortField={sortField} sortOrder={sortOrder} onSort={handleSort} />
                                    <TableHead className="text-slate-400 text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredAssets.map((asset) => (
                                    <AssetRow
                                        key={asset.id}
                                        asset={asset}
                                        engagementId={engagementId}
                                        handleToggleAssetStatus={handleToggleAssetStatus}
                                        onAddCleanup={onAddCleanup}
                                        onAddVaultItem={onAddVaultItem}
                                        onFilterByPort={setSearch}
                                        noteItems={notesByAsset[asset.id] || []}
                                        findingItems={findingsByAsset[asset.id]?.items || []}
                                        testcaseItems={testcasesByAsset[asset.id]?.items || []}
                                        onViewDetail={handleAssetClick}
                                        col={col}
                                    />
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                )}

                {/* Pagination */}
                {totalAssets > ASSET_PAGE_SIZE && (
                    <div className="flex items-center justify-between pt-4 border-t border-slate-800/50 mt-4">
                        <p className="text-xs text-slate-500">Showing {((currentPage - 1) * ASSET_PAGE_SIZE) + 1}–{Math.min(currentPage * ASSET_PAGE_SIZE, totalAssets)} of {totalAssets} assets</p>
                        <div className="flex items-center gap-1">
                            <Button variant="outline" size="icon" className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30" onClick={() => setCurrentPage(1)} disabled={currentPage === 1}><ChevronsLeft className="h-3.5 w-3.5" /></Button>
                            <Button variant="outline" size="icon" className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30" onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1}><ChevronLeft className="h-3.5 w-3.5" /></Button>
                            <span className="text-xs text-slate-400 px-3 font-medium">Page {currentPage} of {totalPages}</span>
                            <Button variant="outline" size="icon" className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30" onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages}><ChevronRight className="h-3.5 w-3.5" /></Button>
                            <Button variant="outline" size="icon" className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30" onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages}><ChevronsRight className="h-3.5 w-3.5" /></Button>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>

        {/* Import Dialog */}
        {showImport && <AssetImportDialog engagementId={engagementId} open={showImport} onOpenChange={setShowImport} />}

        {/* Detail Sheet */}
        {selectedAssetId && (
            <AssetDetailSheet
                engagementId={engagementId}
                assetId={selectedAssetId}
                open={!!selectedAssetId}
                onOpenChange={(open) => !open && setSelectedAssetId(null)}
                nonModal
            />
        )}
        </>
    );
}

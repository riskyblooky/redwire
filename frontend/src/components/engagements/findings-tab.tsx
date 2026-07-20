/**
 * findings-tab.tsx — Engagement Findings Tab
 *
 * Sortable, searchable table of security findings for an engagement.
 * Each row (FindingRow) shows severity, status, discussion count,
 * creator avatar, age, and linked entity tooltips (assets, vault items,
 * cleanup artifacts, notes, intel, infra). Sort preferences are
 * persisted to localStorage. The search uses a relevance-weighted
 * comparator so exact title matches float to the top.
 *
 * Action menu per row supports: create & link vault item, quick-add
 * cleanup artifact, link asset/intel/infra, edit, and delete (with
 * permission guards).
 */
'use client';

import { useState, useMemo, useEffect } from 'react';
import { useColumnVisibility, ColumnDef } from '@/lib/hooks/use-column-visibility';
import { CustomFieldListHeads, CustomFieldListCells, useCustomFieldListDefs, customFieldColumnDefs, compareCustomFieldValues } from '@/components/custom-fields/custom-field-list-columns';
import { ColumnToggle } from '@/components/ui/column-toggle';
import { useRouter } from 'next/navigation';
import {
    Search, Plus, Bug, Loader2, ArrowUpDown, ArrowUp, ArrowDown,
    Lock, Sparkles, Server, MoreVertical, Trash2, Edit, MessageSquare,
    StickyNote, Radar, Settings, Filter, X, Link as LinkIcon, Paperclip, GitBranch,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useFindings, useDeleteFinding } from '@/lib/hooks/use-findings';
import { useNotes } from '@/lib/hooks/use-notes';
import { usePermission, useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { useInfraByEntity } from '@/lib/hooks/use-infra';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';
import { LinkTooltip } from '@/components/ui/link-tooltip';
import { UserAvatar } from '@/components/ui/user-avatar';
import { relevanceComparator } from '@/lib/search-relevance';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
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
    useLinkFindingToVaultItem, useUnlinkFindingFromVaultItem,
    useLinkFindingToCleanup, useUnlinkFindingFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { useLinkAssetToFinding, useUnlinkAssetFromFinding } from '@/lib/hooks/use-entity-links';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import { AttachmentQuickAddDialog } from '@/components/ui/attachment-quick-add-dialog';
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
import { Checkbox } from '@/components/ui/checkbox';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { FindingDetailSheet } from '@/components/engagements/finding-detail-sheet';
import { ChainLinksDialog } from '@/components/engagements/chain-links-section';

// ── Constants ────────────────────────────────────────────────────────
const severityColors: Record<string, string> = {
    CRITICAL: 'bg-red-500/20 text-red-500 border-red-500/30',
    HIGH: 'bg-orange-500/20 text-orange-500 border-orange-500/30',
    MEDIUM: 'bg-amber-500/20 text-amber-500 border-amber-500/30',
    LOW: 'bg-blue-500/20 text-blue-500 border-blue-500/30',
    INFO: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

const severityOrder: Record<string, number> = {
    CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4,
};

const findingStatusColors: Record<string, string> = {
    OPEN: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    IN_REVIEW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    VERIFIED: 'bg-green-500/10 text-green-400 border-green-500/20',
    CLOSED: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
    FALSE_POSITIVE: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
};

/** Renders the appropriate sort direction indicator for a column header. */
const SortIcon = ({ field, currentField, order }: { field: string; currentField: string; order: 'asc' | 'desc' }) => {
    if (currentField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
    return order === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
};

/** Single finding table row with severity badge, linked entity tooltips, and action menu. */
const FindingRow = ({ finding, engagementId, onAddVaultItem, onAddCleanup, onLinkAsset, onLinkIntel, onLinkInfra, noteItems = [], col = () => true, onViewDetail }: any) => {
    const router = useRouter();
    const canEdit = useCanEdit(engagementId, 'finding', finding.created_by);
    const canDelete = useCanDelete(engagementId, 'finding', finding.created_by);
    const deleteFinding = useDeleteFinding();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const { data: findingIntelItems = [] } = useIntelByEntity('finding', finding.id);
    const { data: findingInfraItems = [] } = useInfraByEntity('finding', finding.id);
    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);
    const [attachmentDialogOpen, setAttachmentDialogOpen] = useState(false);
    const [chainDialogOpen, setChainDialogOpen] = useState(false);

    // Unified link/unlink wiring (vault, cleanup, asset; intel/infra handled by the dialog internally)
    const linkVault = useLinkFindingToVaultItem();
    const unlinkVault = useUnlinkFindingFromVaultItem();
    const linkCleanup = useLinkFindingToCleanup();
    const unlinkCleanup = useUnlinkFindingFromCleanup();
    const linkAsset = useLinkAssetToFinding();      // direction reversed — same DB row
    const unlinkAsset = useUnlinkAssetFromFinding();

    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (type === 'vault') await linkVault.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: finding.id, resourceId });
        // For assets: API is /assets/{assetId}/findings/{findingId} — pass the asset
        // as the entity and the finding as the resource so the URL builds correctly.
        if (type === 'assets') await linkAsset.mutateAsync({ entityId: resourceId, resourceId: finding.id });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'assets') await unlinkAsset.mutateAsync({ entityId: resourceId, resourceId: finding.id });
    };

    const linkedIds: LinkedIdMap = {
        findings: new Set(),
        testcases: new Set(),
        assets: new Set((finding.assets ?? []).map((a: any) => a.id)),
        vault: new Set((finding.vault_items ?? []).map((v: any) => v.id)),
        cleanup: new Set((finding.cleanup_artifacts ?? []).map((c: any) => c.id)),
        intel: new Set(findingIntelItems.map((i: any) => i.id)),
        infra: new Set(findingInfraItems.map((i: any) => i.id)),
    };

    const handleDelete = async (e: React.MouseEvent) => {
        e.stopPropagation();
        const confirmed = await confirm({
            title: 'Delete Finding',
            description: 'Are you sure you want to delete this finding? This action cannot be undone.',
        });
        if (!confirmed) return;

        try {
            await deleteFinding.mutateAsync(finding.id);
            toast.success('Finding deleted successfully');
        } catch (error: any) {
            console.error('Failed to delete finding:', error);
            toast.error(getErrorMessage(error, 'Failed to delete finding'));
        }
    };

    return (
        <>
            <ConfirmDialog />
            <TableRow
                className="border-slate-800 hover:bg-slate-800/50 cursor-pointer"
                onClick={() => onViewDetail ? onViewDetail(finding.id) : router.push(`/findings/${finding.id}?engagementId=${engagementId}&tab=findings`)}
            >
                <TableCell className="font-medium text-white">{finding.title}</TableCell>
                {col('severity') && <TableCell><Badge className={severityColors[finding.severity]}>{finding.severity}</Badge></TableCell>}
                {col('status') && <TableCell><Badge variant="outline" className={findingStatusColors[finding.status]}>{finding.status.replace('_', ' ')}</Badge></TableCell>}
                {col('discussions') && <TableCell>
                    {finding.unresolved_thread_count && finding.unresolved_thread_count > 0 ? (
                        <div className="flex items-center gap-2 text-amber-400">
                            <MessageSquare className="h-4 w-4" />
                            <span className="text-sm font-medium">{finding.unresolved_thread_count}</span>
                        </div>
                    ) : (
                        <span className="text-slate-600 text-sm">—</span>
                    )}
                </TableCell>}
                {col('createdBy') && <TableCell className="text-slate-300">
                    <RadixTooltipProvider delayDuration={200}>
                        <RadixTooltip>
                            <RadixTooltipTrigger asChild>
                                <div className="w-fit">
                                    <UserAvatar
                                        user={{
                                            id: finding.created_by,
                                            username: finding.created_by_username || 'System',
                                            profile_photo: finding.created_by_profile_photo,
                                        }}
                                        className="h-7 w-7"
                                    />
                                </div>
                            </RadixTooltipTrigger>
                            <RadixTooltipContent side="top">
                                <span className="text-xs">{finding.created_by_username || 'System'}</span>
                            </RadixTooltipContent>
                        </RadixTooltip>
                    </RadixTooltipProvider>
                </TableCell>}
                {col('created') && <TableCell className="text-slate-400">
                    <RadixTooltipProvider delayDuration={200}>
                        <RadixTooltip>
                            <RadixTooltipTrigger asChild>
                                <span className="cursor-default">{formatDistanceToNow(parseUTCDate(finding.created_at), { addSuffix: true })}</span>
                            </RadixTooltipTrigger>
                            <RadixTooltipContent side="top"><span className="text-xs">{new Date(finding.created_at).toLocaleString()}</span></RadixTooltipContent>
                        </RadixTooltip>
                    </RadixTooltipProvider>
                </TableCell>}
                {col('links') && <TableCell>
                    <div className="flex items-center gap-3">
                        <LinkTooltip icon={<Server className="h-3.5 w-3.5" />} count={(finding.assets || []).length} items={(finding.assets || []).map((a: any) => ({ name: a.name, href: `/assets/${a.id}?engagementId=${engagementId}` }))} label="Assets" colorClass="text-cyan-400" />
                        <LinkTooltip icon={<Lock className="h-3.5 w-3.5" />} count={(finding.vault_items || []).length} items={(finding.vault_items || []).map((v: any) => ({ name: v.name }))} label="Vault Items" colorClass="text-amber-400" />
                        <LinkTooltip icon={<Sparkles className="h-3.5 w-3.5" />} count={(finding.cleanup_artifacts || []).length} items={(finding.cleanup_artifacts || []).map((c: any) => ({ name: c.title || c.name || 'Cleanup artifact' }))} label="Cleanup Artifacts" colorClass="text-lime-400" />
                        <LinkTooltip icon={<Paperclip className="h-3.5 w-3.5" />} count={(finding.evidence || []).length} items={(finding.evidence || []).map((e: any) => ({ name: e.original_filename }))} label="Evidence" colorClass="text-pink-400" />
                        <LinkTooltip icon={<StickyNote className="h-3.5 w-3.5" />} count={noteItems.length} items={noteItems.map((n: any) => ({ name: n.title, href: `/engagements/${engagementId}?tab=notes&noteId=${n.id}` }))} label="Notes" colorClass="text-teal-400" />
                        <LinkTooltip icon={<Radar className="h-3.5 w-3.5" />} count={findingIntelItems.length} items={findingIntelItems.map((i: any) => ({ name: i.title || i.value, onClick: () => setIntelDetailId(i.id) }))} label="Intel" colorClass="text-violet-400" />
                        <LinkTooltip icon={<Server className="h-3.5 w-3.5" />} count={findingInfraItems.length} items={findingInfraItems.map((i: any) => ({ name: i.name }))} label="Infrastructure" colorClass="text-teal-400" />
                        {(finding.assets || []).length === 0 && (finding.vault_items || []).length === 0 && (finding.cleanup_artifacts || []).length === 0 && (finding.evidence || []).length === 0 && noteItems.length === 0 && findingIntelItems.length === 0 && findingInfraItems.length === 0 && (
                            <span className="text-slate-600 text-sm">—</span>
                        )}
                    </div>
                </TableCell>}
                <CustomFieldListCells entity="finding" value={finding.custom_fields} isVisible={col} />
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
                            <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); setChainDialogOpen(true); }}>
                                <GitBranch className="h-4 w-4 mr-2" />Attack Chain
                            </DropdownMenuItem>

                            <DropdownMenuSub>
                                <DropdownMenuSubTrigger className="text-slate-300 focus:bg-slate-800/50 focus:text-white data-[state=open]:bg-slate-800/50 data-[state=open]:text-white">
                                    <Plus className="h-4 w-4 mr-2" />Quick Add
                                </DropdownMenuSubTrigger>
                                <DropdownMenuPortal>
                                    <DropdownMenuSubContent className="bg-slate-900 border-slate-800 text-white">
                                        <DropdownMenuItem className="text-amber-400 focus:bg-amber-500/10 focus:text-amber-400" onClick={(e) => { e.stopPropagation(); onAddVaultItem({ type: 'finding', id: finding.id, name: finding.title }); }}>
                                            <Lock className="h-4 w-4 mr-2" />Vault Item
                                        </DropdownMenuItem>
                                        <DropdownMenuItem className="text-lime-400 focus:bg-lime-500/10 focus:text-lime-400" onClick={(e) => { e.stopPropagation(); onAddCleanup({ type: 'finding', id: finding.id, name: finding.title }); }}>
                                            <Sparkles className="h-4 w-4 mr-2" />Cleanup Artifact
                                        </DropdownMenuItem>
                                        <DropdownMenuItem className="text-pink-400 focus:bg-pink-500/10 focus:text-pink-400" onClick={(e) => { e.stopPropagation(); setAttachmentDialogOpen(true); }}>
                                            <Paperclip className="h-4 w-4 mr-2" />Attachment
                                        </DropdownMenuItem>
                                    </DropdownMenuSubContent>
                                </DropdownMenuPortal>
                            </DropdownMenuSub>

                            <DropdownMenuSeparator className="bg-slate-800" />
                            {canEdit && (
                                <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); router.push(`/findings/${finding.id}/edit?engagementId=${engagementId}&tab=findings`); }}>
                                    <Edit className="h-4 w-4 mr-2" />
                                    Edit
                                </DropdownMenuItem>
                            )}
                            {canDelete && (
                                <DropdownMenuItem className="text-red-400 focus:bg-red-500/10 focus:text-red-400" onClick={handleDelete}>
                                    <Trash2 className="h-4 w-4 mr-2" />
                                    Delete
                                </DropdownMenuItem>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </TableCell>
            </TableRow>
            {intelDetailId && <IntelDetailDialog itemId={intelDetailId} onClose={() => setIntelDetailId(null)} />}
            <LinkEntityDialog
                open={linkDialogOpen}
                onOpenChange={setLinkDialogOpen}
                engagementId={engagementId}
                entityType="finding"
                entityId={finding.id}
                entityName={finding.title}
                linkedIds={linkedIds}
                onLink={handleEntityLink}
                onUnlink={handleEntityUnlink}
                allowedTypes={['vault', 'cleanup', 'assets', 'intel', 'infra']}
            />
            <ChainLinksDialog
                open={chainDialogOpen}
                onOpenChange={setChainDialogOpen}
                engagementId={engagementId}
                entityType="finding"
                entityId={finding.id}
                entityName={finding.title}
                canEdit={canEdit}
            />
            <AttachmentQuickAddDialog
                open={attachmentDialogOpen}
                onOpenChange={setAttachmentDialogOpen}
                findingId={finding.id}
                entityName={finding.title}
            />
        </>
    );
};

/**
 * FindingsTab — Sortable/searchable findings table.
 *
 * Fetches findings and notes for the engagement, builds a reverse-lookup
 * map (notesByFinding), and renders a paginated table with sort controls.
 * The search uses relevanceComparator for title-priority ranking.
 */
interface FindingsTabProps {
    engagementId: string;
    onAddVaultItem: (target: any) => void;
    onAddCleanup: (target: any) => void;
    onLinkAsset: (target: any) => void;
    onLinkIntel: (target: any) => void;
    onLinkInfra: (target: any) => void;
}

const FINDINGS_COLUMNS: ColumnDef[] = [
    { key: 'title',       label: 'Title',       required: true },
    { key: 'severity',    label: 'Severity' },
    { key: 'status',      label: 'Status' },
    { key: 'discussions', label: 'Discussions' },
    { key: 'createdBy',   label: 'Created By' },
    { key: 'created',     label: 'Created' },
    { key: 'links',       label: 'Links' },
    { key: 'actions',     label: 'Actions',     required: true },
];

export function FindingsTab({ engagementId, onAddVaultItem, onAddCleanup, onLinkAsset, onLinkIntel, onLinkInfra }: FindingsTabProps) {
    const router = useRouter();
    const canCreateFinding = usePermission(engagementId, 'finding_create');
    const cfListDefs = useCustomFieldListDefs('finding');
    const findingColumns = useMemo(() => [...FINDINGS_COLUMNS, ...customFieldColumnDefs(cfListDefs)], [cfListDefs]);
    const [visibleCols, toggleCol] = useColumnVisibility('redwire_col_findings', findingColumns);
    const col = (key: string) => visibleCols.has(key);

    // Data
    const findingsParams = useMemo(() => ({ engagement_id: engagementId }), [engagementId]);
    const { data: findings = [], isLoading } = useFindings(findingsParams);
    const { data: notes = [] } = useNotes(engagementId);

    // Notes reverse-lookup
    const notesByFinding = useMemo(() => {
        const map: Record<string, { id: string; title: string }[]> = {};
        notes.forEach((n: any) => n.linked_findings?.forEach((f: any) => {
            if (!map[f.id]) map[f.id] = [];
            map[f.id].push({ id: n.id, title: n.title });
        }));
        return map;
    }, [notes]);

    // Detail sheet state
    const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);

    // View mode toggle: 'panel' = side sheet, 'page' = full page nav
    const [viewMode, setViewMode] = useState<'panel' | 'page'>(() => {
        if (typeof window !== 'undefined') return (localStorage.getItem('redwire_finding_view_mode') as 'panel' | 'page') || 'panel';
        return 'panel';
    });
    useEffect(() => { localStorage.setItem('redwire_finding_view_mode', viewMode); }, [viewMode]);

    const handleFindingClick = (findingId: string) => {
        if (viewMode === 'page') {
            router.push(`/findings/${findingId}?engagementId=${engagementId}&tab=findings`);
        } else {
            setSelectedFindingId(findingId);
        }
    };

    // Sort & search & filter state
    const [search, setSearch] = useState('');
    const [showFilters, setShowFilters] = useState(false);
    const [filters, setFilters] = useState<{
        severities: string[];
        statuses: string[];
        createdBy: string;
        dateAfter: string;
    }>({ severities: [], statuses: [], createdBy: '', dateAfter: '' });

    const hasActiveFilters = filters.severities.length > 0 || filters.statuses.length > 0 || !!filters.createdBy || !!filters.dateAfter;

    const toggleMulti = (key: 'severities' | 'statuses', val: string) => {
        setFilters(prev => {
            const cur = prev[key];
            return { ...prev, [key]: cur.includes(val) ? cur.filter(v => v !== val) : [...cur, val] };
        });
    };
    const clearFilters = () => setFilters({ severities: [], statuses: [], createdBy: '', dateAfter: '' });

    const [sortField, setSortField] = useState<string>(() => {
        if (typeof window !== 'undefined') return localStorage.getItem('redwire_sort_engagement_findings_field') || 'created_at';
        return 'created_at';
    });
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') return (localStorage.getItem('redwire_sort_engagement_findings_order') as 'asc' | 'desc') || 'desc';
        return 'desc';
    });

    const handleSort = (field: string) => {
        if (sortField === field) {
            const next = sortOrder === 'asc' ? 'desc' : 'asc';
            setSortOrder(next);
            localStorage.setItem('redwire_sort_engagement_findings_order', next);
        } else {
            setSortField(field);
            setSortOrder('asc');
            localStorage.setItem('redwire_sort_engagement_findings_field', field);
            localStorage.setItem('redwire_sort_engagement_findings_order', 'asc');
        }
    };

    const sortedFindings = [...findings]
        .filter(f => {
            const term = search.toLowerCase();
            const matchesText = !term || f.title.toLowerCase().includes(term) ||
                f.description.toLowerCase().includes(term) ||
                f.status.toLowerCase().includes(term) ||
                f.severity.toLowerCase().includes(term);
            const matchesSeverity = filters.severities.length === 0 || filters.severities.includes(f.severity);
            const matchesStatus = filters.statuses.length === 0 || filters.statuses.includes(f.status);
            const matchesCreatedBy = !filters.createdBy || (f.created_by_username || '').toLowerCase().includes(filters.createdBy.toLowerCase());
            const matchesDate = !filters.dateAfter || new Date(f.created_at) >= new Date(filters.dateAfter);
            return matchesText && matchesSeverity && matchesStatus && matchesCreatedBy && matchesDate;
        })
        .sort(relevanceComparator(
            search,
            [item => item.title, item => item.description],
            (a, b) => {
                let comparison = 0;
                if (sortField === 'severity') comparison = severityOrder[a.severity] - severityOrder[b.severity];
                else if (sortField === 'created_at') comparison = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
                else if (sortField === 'unresolved_thread_count') comparison = (a.unresolved_thread_count || 0) - (b.unresolved_thread_count || 0);
                else if (sortField === 'created_by_username') comparison = (a.created_by_username || '').localeCompare(b.created_by_username || '');
                else if (sortField.startsWith('cf:')) comparison = compareCustomFieldValues((a.custom_fields as any)?.[sortField.slice(3)], (b.custom_fields as any)?.[sortField.slice(3)]);
                else comparison = String((a as any)[sortField]).localeCompare(String((b as any)[sortField]));
                return sortOrder === 'asc' ? comparison : -comparison;
            }
        ));

    return (
        <>
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="flex flex-row items-center justify-between">
                <div>
                    <CardTitle className="text-white">Findings</CardTitle>
                    <CardDescription>Manage and track security vulnerabilities</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative w-64 mr-2">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
                        <Input placeholder="Search findings..." className="pl-8 bg-slate-900/50 border-slate-700 text-xs h-9" value={search} onChange={(e) => setSearch(e.target.value)} />
                    </div>
                    <Button
                        size="icon" variant="ghost"
                        className={cn("h-9 w-9", hasActiveFilters ? "text-primary bg-primary/10" : "text-slate-400 hover:text-white")}
                        title="Advanced Filters"
                        onClick={() => setShowFilters(!showFilters)}
                    >
                        <Filter className="h-4 w-4" />
                    </Button>
                    <ColumnToggle columns={findingColumns} visible={visibleCols} onToggle={toggleCol} />
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
                    {canCreateFinding && (
                        <Button onClick={() => router.push(`/findings/new?engagementId=${engagementId}`)} size="sm" className="bg-red-600 hover:bg-red-700">
                            <Plus className="h-4 w-4 mr-2" />
                            Add Finding
                        </Button>
                    )}
                </div>
            </CardHeader>

            {/* Active filter chips */}
            {hasActiveFilters && (
                <div className="px-6 pb-2 flex flex-wrap gap-1.5">
                    {filters.severities.map(s => (
                        <Badge key={s} className="bg-red-500/10 text-red-400 border border-red-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-red-500/20" onClick={() => toggleMulti('severities', s)}>
                            {s}<X className="h-3 w-3" />
                        </Badge>
                    ))}
                    {filters.statuses.map(s => (
                        <Badge key={s} className="bg-primary/10 text-primary border border-primary/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-primary/20" onClick={() => toggleMulti('statuses', s)}>
                            {s.replace('_', ' ')}<X className="h-3 w-3" />
                        </Badge>
                    ))}
                    {filters.createdBy && (
                        <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-blue-500/20" onClick={() => setFilters(p => ({ ...p, createdBy: '' }))}>
                            By: {filters.createdBy}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    {filters.dateAfter && (
                        <Badge className="bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-amber-500/20" onClick={() => setFilters(p => ({ ...p, dateAfter: '' }))}>
                            After: {filters.dateAfter}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    <button className="text-[10px] text-slate-500 hover:text-slate-300 ml-1 underline" onClick={clearFilters}>Clear all</button>
                </div>
            )}

            {/* Advanced filter panel */}
            {showFilters && (
                <div className="px-6 pb-4 border-b border-slate-800">
                    <div className="flex flex-wrap gap-6">
                        {/* Severity */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Severity</span>
                            <div className="flex flex-wrap gap-x-3 gap-y-1">
                                {['CRITICAL','HIGH','MEDIUM','LOW','INFO'].map(s => (
                                    <label key={s} className="flex items-center gap-1.5 cursor-pointer">
                                        <Checkbox checked={filters.severities.includes(s)} onCheckedChange={() => toggleMulti('severities', s)} className="h-3.5 w-3.5" />
                                        <span className={cn('text-xs font-medium', severityColors[s]?.split(' ')[1] ?? 'text-slate-300')}>{s}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                        {/* Status */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Status</span>
                            <div className="flex flex-wrap gap-x-3 gap-y-1">
                                {['OPEN','IN_REVIEW','VERIFIED','CLOSED','FALSE_POSITIVE'].map(s => (
                                    <label key={s} className="flex items-center gap-1.5 cursor-pointer">
                                        <Checkbox checked={filters.statuses.includes(s)} onCheckedChange={() => toggleMulti('statuses', s)} className="h-3.5 w-3.5" />
                                        <span className="text-xs text-slate-300">{s.replace('_', ' ')}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                        {/* Created By */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Created By</span>
                            <input
                                type="text"
                                placeholder="username..."
                                value={filters.createdBy}
                                onChange={e => setFilters(p => ({ ...p, createdBy: e.target.value }))}
                                className="h-7 text-xs bg-slate-800/50 border border-slate-700 rounded px-2 text-white placeholder:text-slate-600 focus:outline-none focus:border-primary w-32"
                            />
                        </div>
                        {/* Date After */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Created After</span>
                            <input
                                type="date"
                                value={filters.dateAfter}
                                onChange={e => setFilters(p => ({ ...p, dateAfter: e.target.value }))}
                                className="h-7 text-xs bg-slate-800/50 border border-slate-700 rounded px-2 text-white focus:outline-none focus:border-primary w-36 [color-scheme:dark]"
                            />
                        </div>
                        {hasActiveFilters && (
                            <div className="flex items-end pb-0.5">
                                <Button size="sm" variant="ghost" className="text-slate-400 hover:text-white text-xs h-7" onClick={clearFilters}>Clear all</Button>
                            </div>
                        )}
                    </div>
                </div>
            )}

            <CardContent>
                {isLoading ? (
                    <div className="flex justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                    </div>
                ) : findings.length === 0 ? (
                    <div className="text-center py-8 text-slate-400">
                        <Bug className="h-12 w-12 mx-auto mb-4 opacity-50" />
                        <p>No findings yet</p>
                    </div>
                ) : (
                    <Table>
                        <TableHeader>
                            <TableRow className="border-slate-800">
                                <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('title')}><div className="flex items-center">Title <SortIcon field="title" currentField={sortField} order={sortOrder} /></div></TableHead>
                                {col('severity') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('severity')}><div className="flex items-center">Severity <SortIcon field="severity" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('status') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('status')}><div className="flex items-center">Status <SortIcon field="status" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('discussions') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('unresolved_thread_count')}><div className="flex items-center">Discussions <SortIcon field="unresolved_thread_count" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('createdBy') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('created_by_username')}><div className="flex items-center">Created By <SortIcon field="created_by_username" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('created') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => handleSort('created_at')}><div className="flex items-center">Created <SortIcon field="created_at" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('links') && <TableHead className="text-slate-400">Links</TableHead>}
                                <CustomFieldListHeads entity="finding" isVisible={col} sortField={sortField} sortOrder={sortOrder} onSort={handleSort} />
                                <TableHead className="text-right text-slate-400">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {sortedFindings.map((finding) => (
                                <FindingRow
                                    key={finding.id}
                                    finding={finding}
                                    engagementId={engagementId}
                                    onAddVaultItem={onAddVaultItem}
                                    onAddCleanup={onAddCleanup}
                                    onLinkAsset={onLinkAsset}
                                    onLinkIntel={onLinkIntel}
                                    onLinkInfra={onLinkInfra}
                                    noteItems={notesByFinding[finding.id] || []}
                                    col={col}
                                    onViewDetail={handleFindingClick}
                                />
                            ))}
                        </TableBody>
                    </Table>
                )}
            </CardContent>
        </Card>
        <FindingDetailSheet
            findingId={selectedFindingId}
            engagementId={engagementId}
            open={!!selectedFindingId}
            onOpenChange={(open) => { if (!open) setSelectedFindingId(null); }}
            nonModal
        />
        </>
    );
}

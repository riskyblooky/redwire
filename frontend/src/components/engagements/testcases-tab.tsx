/**
 * testcases-tab.tsx — Engagement Test Cases Tab
 *
 * Hierarchical (tree) view of test cases with drag-and-drop reordering
 * (via @dnd-kit). Supports two modes:
 *  - Tree view (default: sort=title, order=asc) — shows parent/child
 *    nesting with expand/collapse, indent guides, and DnD handles
 *  - Flat table — activates when searching or sorting by non-title field
 *
 * Features include:
 *  - Runbook import dialog (applies a template tree as test cases)
 *  - Move-in-tree dialog for reparenting test cases
 *  - Per-row action menu: add sub-test case, link finding/asset/intel/
 *    infra, create vault item, quick-add cleanup, edit, delete
 *  - Expand/collapse all toggle, search with child-match propagation
 *  - Sort preferences and expanded-node state persisted to localStorage
 */
'use client';

import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { useColumnVisibility, ColumnDef } from '@/lib/hooks/use-column-visibility';
import { ColumnToggle } from '@/components/ui/column-toggle';
import { useRouter } from 'next/navigation';
import {
    Search, Plus, Bug, Loader2, ArrowUpDown, ArrowUp, ArrowDown,
    Lock, Sparkles, Server, MoreVertical, Trash2, Edit, MessageSquare,
    StickyNote, Radar, Paperclip, CheckSquare, ChevronDown, ChevronRight,
    CornerDownRight, GripVertical, FolderTree, TreePine, Table2, Zap,
    Flag, Layout, Circle, ArrowUpCircle, GitBranch, Globe, Settings, Filter, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
    useTestCases, useDeleteTestCase, useUpdateTestCase,
    buildTestCaseTree, flattenTree, TestCaseTreeNode,
    useLinkFinding, useUnlinkFinding, useLinkAsset, useUnlinkAsset,
} from '@/lib/hooks/use-testcases';
import {
    useLinkTestCaseToFinding, useUnlinkTestCaseFromFinding,
    useLinkTestCaseToAsset, useUnlinkTestCaseFromAsset,
    useLinkTestCaseToVaultItem, useUnlinkTestCaseFromVaultItem,
    useLinkTestCaseToCleanup, useUnlinkTestCaseFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import { AttachmentQuickAddDialog } from '@/components/ui/attachment-quick-add-dialog';
import { useNotes } from '@/lib/hooks/use-notes';
import { usePermission, useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { useInfraByEntity } from '@/lib/hooks/use-infra';
import { useRunbooks, useApplyRunbook, Runbook, RunbookItem } from '@/lib/hooks/use-runbooks';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';
import { MoveTestCaseDialog } from '@/components/ui/move-testcase-dialog';
import { LinkTooltip } from '@/components/ui/link-tooltip';
import { UserAvatar } from '@/components/ui/user-avatar';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
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
    DropdownMenuSubContent,
    DropdownMenuSubTrigger,
    DropdownMenuPortal,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Link as LinkIcon } from 'lucide-react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { TestCaseDetailSheet } from '@/components/engagements/testcase-detail-sheet';
import {
    DndContext,
    closestCenter,
    DragOverlay,
    DragStartEvent,
    DragEndEvent,
    PointerSensor,
    useSensor,
    useSensors,
} from '@dnd-kit/core';
import {
    SortableContext,
    useSortable,
    verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

// ── Constants ────────────────────────────────────────────────────────
const testCaseCategoryStyles: Record<string, { color: string; icon: any }> = {
    RECONNAISSANCE: { color: 'bg-blue-500/10 text-blue-400 border-blue-500/20', icon: Globe },
    SCANNING: { color: 'bg-purple-500/10 text-purple-400 border-purple-500/20', icon: Radar },
    EXPLOITATION: { color: 'bg-red-500/10 text-red-400 border-red-500/20', icon: Zap },
    POST_EXPLOITATION: { color: 'bg-orange-500/10 text-orange-400 border-orange-500/20', icon: Flag },
    PRIVILEGE_ESCALATION: { color: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20', icon: ArrowUpCircle },
    WEB_APPLICATION: { color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20', icon: Layout },
    OTHER: { color: 'bg-slate-500/10 text-slate-400 border-slate-500/20', icon: Circle },
};

const SortIcon = ({ field, currentField, order }: { field: string; currentField: string; order: 'asc' | 'desc' }) => {
    if (currentField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
    return order === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
};

/** Single test case table row with tree-indent, DnD handle, category badge, status, and action menu. */
const TestCaseRow = ({ testcase, engagementId, depth = 0, hasChildren = false, isExpanded = false, onToggleExpand, onAddVaultItem, onAddCleanup, onAddFinding, onLinkAsset, onLinkIntel, onLinkInfra, onMove, noteItems = [], isDraggable = false, col = () => true, onViewDetail }: any) => {
    const router = useRouter();
    const canEdit = useCanEdit(engagementId, 'testcase', testcase.created_by);
    const canDelete = useCanDelete(engagementId, 'testcase', testcase.created_by);
    const deleteTestCase = useDeleteTestCase();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const { data: testcaseIntelItems = [] } = useIntelByEntity('testcase', testcase.id);
    const { data: testcaseInfraItems = [] } = useInfraByEntity('testcase', testcase.id);
    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);
    const [attachmentDialogOpen, setAttachmentDialogOpen] = useState(false);

    // Unified link/unlink wiring (matches the testcase detail sheet pattern)
    const linkFinding = useLinkTestCaseToFinding();
    const unlinkFinding = useUnlinkTestCaseFromFinding();
    const linkAsset = useLinkTestCaseToAsset();
    const unlinkAsset = useUnlinkTestCaseFromAsset();
    const linkVault = useLinkTestCaseToVaultItem();
    const unlinkVault = useUnlinkTestCaseFromVaultItem();
    const linkCleanup = useLinkTestCaseToCleanup();
    const unlinkCleanup = useUnlinkTestCaseFromCleanup();

    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (type === 'findings') await linkFinding.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'assets') await linkAsset.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'vault') await linkVault.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: testcase.id, resourceId });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (type === 'findings') await unlinkFinding.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'assets') await unlinkAsset.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: testcase.id, resourceId });
    };

    const linkedIds: LinkedIdMap = {
        findings: new Set((testcase.findings ?? []).map((f: any) => f.id)),
        testcases: new Set(),
        assets: new Set((testcase.assets ?? []).map((a: any) => a.id)),
        vault: new Set((testcase.vault_items ?? []).map((v: any) => v.id)),
        cleanup: new Set((testcase.cleanup_artifacts ?? []).map((c: any) => c.id)),
        intel: new Set(testcaseIntelItems.map((i: any) => i.id)),
        infra: new Set(testcaseInfraItems.map((i: any) => i.id)),
    };

    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
        id: testcase.id,
        disabled: !isDraggable,
    });
    const sortableStyle = isDraggable ? {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.4 : 1,
        position: 'relative' as const,
        zIndex: isDragging ? 50 : undefined,
    } : {};

    const handleDelete = async (e: React.MouseEvent) => {
        e.stopPropagation();
        if (hasChildren) {
            // Count descendants for the prompt
            const childCount = testcase.children?.length || 0;
            const result = await confirm({
                title: 'Delete Test Case with Children',
                description: `"${testcase.title}" has ${childCount} direct sub-test case${childCount !== 1 ? 's' : ''}. What would you like to do?`,
                confirmLabel: 'Delete All (with children)',
                variant: 'destructive',
                extraAction: {
                    label: 'Delete Only This',
                    variant: 'outline' as const,
                },
            });
            if (result === false) return; // cancelled
            const cascade = result === true; // true = Delete All, 'extra' = Delete Only This
            try {
                await deleteTestCase.mutateAsync({ id: testcase.id, cascade });
                toast.success(cascade ? 'Test case and all children deleted' : 'Test case deleted (children moved to root)');
            } catch (error: any) {
                console.error('Failed to delete test case:', error);
                toast.error(getErrorMessage(error, 'Failed to delete test case'));
            }
        } else {
            const confirmed = await confirm({
                title: 'Delete Test Case',
                description: 'Are you sure you want to delete this test case? This action cannot be undone.',
            });
            if (!confirmed) return;
            try {
                await deleteTestCase.mutateAsync({ id: testcase.id });
                toast.success('Test case deleted successfully');
            } catch (error: any) {
                console.error('Failed to delete test case:', error);
                toast.error(getErrorMessage(error, 'Failed to delete test case'));
            }
        }
    };

    const depthPadding = 16 + depth * 24;

    return (
        <>
            <ConfirmDialog />
            <TableRow
                ref={isDraggable ? setNodeRef : undefined}
                style={sortableStyle}
                className={cn("border-slate-800 hover:bg-slate-800/50 cursor-pointer group", isDragging && "bg-slate-800/80 shadow-lg shadow-primary/10")}
                onClick={() => onViewDetail ? onViewDetail(testcase.id) : router.push(`/testcases/${testcase.id}?engagementId=${engagementId}&tab=testcases`)}
            >
                <TableCell className="font-medium text-white" style={{ paddingLeft: `${depthPadding}px` }}>
                    <div className="flex items-center gap-1.5">
                        {isDraggable && (
                            <button {...attributes} {...listeners} className="p-0.5 rounded hover:bg-slate-700/50 cursor-grab active:cursor-grabbing text-slate-600 hover:text-slate-300 transition-colors shrink-0 touch-none opacity-0 group-hover:opacity-100" onClick={(e) => e.stopPropagation()} style={{ opacity: isDragging ? 1 : undefined }}>
                                <GripVertical className="h-3.5 w-3.5" />
                            </button>
                        )}
                        {hasChildren ? (
                            <button onClick={(e) => { e.stopPropagation(); onToggleExpand?.(testcase.id); }} className="p-0.5 rounded hover:bg-slate-700/50 transition-colors shrink-0">
                                {isExpanded ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
                            </button>
                        ) : (
                            <span className="w-5 shrink-0">{depth > 0 && <CornerDownRight className="h-3.5 w-3.5 text-slate-600" />}</span>
                        )}
                        <span className="truncate">{testcase.title}</span>
                    </div>
                </TableCell>
                {col('category') && (() => { const style = testCaseCategoryStyles[testcase.category] || testCaseCategoryStyles.OTHER; const Icon = style.icon; return (<TableCell><Badge className={cn("gap-1.5 py-1 px-2.5 font-bold text-[10px] uppercase tracking-wider border", style.color)}><Icon className="h-3 w-3" />{testcase.category.replace('_', ' ')}</Badge></TableCell>); })()}
                {col('status') && <TableCell>{testcase.is_executed ? <Badge className="bg-blue-500/20 text-blue-400">Executed</Badge> : <Badge className="bg-slate-500/20 text-slate-400">Pending</Badge>}</TableCell>}
                {col('result') && <TableCell>{testcase.is_executed ? (testcase.is_successful ? <Badge className="bg-green-500/20 text-green-400">Passed</Badge> : <Badge className="bg-red-500/20 text-red-400">Failed</Badge>) : <span className="text-slate-500">-</span>}</TableCell>}
                {col('discussions') && <TableCell>
                    {testcase.unresolved_thread_count && testcase.unresolved_thread_count > 0 ? (
                        <div className="flex items-center gap-2 text-amber-400"><MessageSquare className="h-4 w-4" /><span className="text-sm font-medium">{testcase.unresolved_thread_count}</span></div>
                    ) : <span className="text-slate-600 text-sm">—</span>}
                </TableCell>}
                {col('createdBy') && <TableCell className="text-slate-300 text-sm">
                    <RadixTooltipProvider delayDuration={200}><RadixTooltip><RadixTooltipTrigger asChild><div className="w-fit"><UserAvatar user={{ id: testcase.created_by, username: testcase.created_by_username || 'System', profile_photo: testcase.created_by_profile_photo }} className="h-7 w-7" /></div></RadixTooltipTrigger><RadixTooltipContent side="top"><span className="text-xs">{testcase.created_by_username || 'System'}</span></RadixTooltipContent></RadixTooltip></RadixTooltipProvider>
                </TableCell>}
                {col('created') && <TableCell className="text-slate-400">
                    <RadixTooltipProvider delayDuration={200}>
                        <RadixTooltip>
                            <RadixTooltipTrigger asChild>
                                <span className="cursor-default">{formatDistanceToNow(parseUTCDate(testcase.created_at), { addSuffix: true })}</span>
                            </RadixTooltipTrigger>
                            <RadixTooltipContent side="top"><span className="text-xs">{new Date(testcase.created_at).toLocaleString()}</span></RadixTooltipContent>
                        </RadixTooltip>
                    </RadixTooltipProvider>
                </TableCell>}
                {col('links') && <TableCell>
                    <div className="flex items-center gap-3">
                        <LinkTooltip icon={<Bug className="h-3.5 w-3.5" />} count={testcase.findings?.length || 0} items={(testcase.findings || []).map((f: any) => ({ name: f.title, href: `/findings/${f.id}?engagementId=${engagementId}` }))} label="Findings" colorClass="text-primary" />
                        <LinkTooltip icon={<Server className="h-3.5 w-3.5" />} count={testcase.assets?.length || 0} items={(testcase.assets || []).map((a: any) => ({ name: a.name, href: `/assets/${a.id}?engagementId=${engagementId}` }))} label="Assets" colorClass="text-cyan-400" />
                        <LinkTooltip icon={<Lock className="h-3.5 w-3.5" />} count={testcase.vault_items?.length || 0} items={(testcase.vault_items || []).map((v: any) => ({ name: v.name }))} label="Vault Items" colorClass="text-amber-400" />
                        <LinkTooltip icon={<Sparkles className="h-3.5 w-3.5" />} count={testcase.cleanup_artifacts?.length || 0} items={(testcase.cleanup_artifacts || []).map((c: any) => ({ name: c.title }))} label="Cleanup Artifacts" colorClass="text-lime-400" />
                        <LinkTooltip icon={<Paperclip className="h-3.5 w-3.5" />} count={testcase.evidence?.length || 0} items={(testcase.evidence || []).map((e: any) => ({ name: e.original_filename }))} label="Evidence" colorClass="text-pink-400" />
                        <LinkTooltip icon={<StickyNote className="h-3.5 w-3.5" />} count={noteItems.length} items={noteItems.map((n: any) => ({ name: n.title, href: `/engagements/${engagementId}?tab=notes&noteId=${n.id}` }))} label="Notes" colorClass="text-teal-400" />
                        <LinkTooltip icon={<Radar className="h-3.5 w-3.5" />} count={testcaseIntelItems.length} items={testcaseIntelItems.map((i: any) => ({ name: i.title, onClick: () => setIntelDetailId(i.id) }))} label="Intel" colorClass="text-cyan-400" />
                        <LinkTooltip icon={<Server className="h-3.5 w-3.5" />} count={testcaseInfraItems.length} items={testcaseInfraItems.map((i: any) => ({ name: i.name }))} label="Infrastructure" colorClass="text-teal-400" />
                        {(!testcase.findings || testcase.findings.length === 0) && (!testcase.assets || testcase.assets.length === 0) && (!testcase.vault_items || testcase.vault_items.length === 0) && (!testcase.cleanup_artifacts || testcase.cleanup_artifacts.length === 0) && (!testcase.evidence || testcase.evidence.length === 0) && noteItems.length === 0 && testcaseIntelItems.length === 0 && testcaseInfraItems.length === 0 && (
                            <span className="text-slate-600 text-sm">—</span>
                        )}
                    </div>
                </TableCell>}
                <TableCell className="text-right">
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-white" onClick={(e) => e.stopPropagation()}><MoreVertical className="h-4 w-4" /></Button></DropdownMenuTrigger>
                        <DropdownMenuContent className="bg-slate-900 border-slate-800 text-white" align="end">
                            <DropdownMenuItem className="text-emerald-400 focus:bg-emerald-500/10 focus:text-emerald-400" onClick={(e) => { e.stopPropagation(); router.push(`/testcases/new?parentId=${testcase.id}&engagementId=${engagementId}`); }}><Plus className="h-4 w-4 mr-2" />Add Sub-Test Case</DropdownMenuItem>

                            <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); setLinkDialogOpen(true); }}><LinkIcon className="h-4 w-4 mr-2" />Link…</DropdownMenuItem>

                            <DropdownMenuSub>
                                <DropdownMenuSubTrigger className="text-slate-300 focus:bg-slate-800/50 focus:text-white data-[state=open]:bg-slate-800/50 data-[state=open]:text-white">
                                    <Plus className="h-4 w-4 mr-2" />Quick Add
                                </DropdownMenuSubTrigger>
                                <DropdownMenuPortal>
                                    <DropdownMenuSubContent className="bg-slate-900 border-slate-800 text-white">
                                        <DropdownMenuItem className="text-red-400 focus:bg-red-500/10 focus:text-red-400" onClick={(e) => { e.stopPropagation(); router.push(`/findings/new?engagementId=${engagementId}&testCaseId=${testcase.id}`); }}><Bug className="h-4 w-4 mr-2" />Finding</DropdownMenuItem>
                                        <DropdownMenuItem className="text-lime-400 focus:bg-lime-500/10 focus:text-lime-400" onClick={(e) => { e.stopPropagation(); onAddCleanup({ type: 'testcase', id: testcase.id, name: testcase.title }); }}><Sparkles className="h-4 w-4 mr-2" />Cleanup Artifact</DropdownMenuItem>
                                        <DropdownMenuItem className="text-amber-400 focus:bg-amber-500/10 focus:text-amber-400" onClick={(e) => { e.stopPropagation(); onAddVaultItem({ type: 'testcase', id: testcase.id, name: testcase.title }); }}><Lock className="h-4 w-4 mr-2" />Vault Item</DropdownMenuItem>
                                        <DropdownMenuItem className="text-pink-400 focus:bg-pink-500/10 focus:text-pink-400" onClick={(e) => { e.stopPropagation(); setAttachmentDialogOpen(true); }}><Paperclip className="h-4 w-4 mr-2" />Attachment</DropdownMenuItem>
                                    </DropdownMenuSubContent>
                                </DropdownMenuPortal>
                            </DropdownMenuSub>

                            <DropdownMenuSeparator className="bg-slate-800" />
                            {canEdit && <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); onMove?.({ id: testcase.id, title: testcase.title, parent_id: testcase.parent_id }); }}><FolderTree className="h-4 w-4 mr-2" />Move in Tree</DropdownMenuItem>}
                            {canEdit && <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); router.push(`/testcases/${testcase.id}/edit?engagementId=${engagementId}&tab=testcases`); }}><Edit className="h-4 w-4 mr-2" />Edit</DropdownMenuItem>}
                            {canDelete && <DropdownMenuItem className="text-red-400 focus:bg-red-500/10 focus:text-red-400" onClick={handleDelete}><Trash2 className="h-4 w-4 mr-2" />Delete</DropdownMenuItem>}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </TableCell>
            </TableRow>
            {intelDetailId && <IntelDetailDialog itemId={intelDetailId} onClose={() => setIntelDetailId(null)} />}
            <LinkEntityDialog
                open={linkDialogOpen}
                onOpenChange={setLinkDialogOpen}
                engagementId={engagementId}
                entityType="testcase"
                entityId={testcase.id}
                entityName={testcase.title}
                linkedIds={linkedIds}
                onLink={handleEntityLink}
                onUnlink={handleEntityUnlink}
            />
            <AttachmentQuickAddDialog
                open={attachmentDialogOpen}
                onOpenChange={setAttachmentDialogOpen}
                testcaseId={testcase.id}
                entityName={testcase.title}
            />
        </>
    );
};

/**
 * TestCasesTab — Tree/table view of test cases with DnD reordering.
 *
 * Manages tree expansion state, search filtering (propagates matches
 * to parent nodes), sort persistence, DnD sensors, runbook import,
 * and move-in-tree dialog. Automatically switches between tree and
 * flat-table mode based on the active sort field.
 */
interface TestCasesTabProps {
    engagementId: string;
    onAddVaultItem: (target: any) => void;
    onAddCleanup: (target: any) => void;
    onAddFinding: (target: any) => void;
    onLinkAsset: (target: any) => void;
    onLinkIntel: (target: any) => void;
    onLinkInfra: (target: any) => void;
}

const TESTCASES_COLUMNS: ColumnDef[] = [
    { key: 'title',       label: 'Title',       required: true },
    { key: 'category',    label: 'Category' },
    { key: 'status',      label: 'Status' },
    { key: 'result',      label: 'Result' },
    { key: 'discussions', label: 'Discussions' },
    { key: 'createdBy',   label: 'Created By' },
    { key: 'created',     label: 'Created' },
    { key: 'links',       label: 'Links' },
    { key: 'actions',     label: 'Actions',     required: true },
];

export function TestCasesTab({ engagementId, onAddVaultItem, onAddCleanup, onAddFinding, onLinkAsset, onLinkIntel, onLinkInfra }: TestCasesTabProps) {
    const router = useRouter();
    const canCreateTestCase = usePermission(engagementId, 'testcase_create');
    const updateTestCase = useUpdateTestCase();
    const [visibleCols, toggleCol] = useColumnVisibility('redwire_col_testcases', TESTCASES_COLUMNS);
    const col = (key: string) => visibleCols.has(key);

    // Data
    const { data: testcases = [], isLoading } = useTestCases(engagementId);
    const { data: notes = [] } = useNotes(engagementId);

    const notesByTestCase = useMemo(() => {
        const map: Record<string, { id: string; title: string }[]> = {};
        notes.forEach((n: any) => n.linked_testcases?.forEach((t: any) => { if (!map[t.id]) map[t.id] = []; map[t.id].push({ id: n.id, title: n.title }); }));
        return map;
    }, [notes]);

    // Detail sheet state
    const [selectedTestcaseId, setSelectedTestcaseId] = useState<string | null>(null);

    // View mode toggle: 'panel' = side sheet, 'page' = full page nav
    const [viewMode, setViewMode] = useState<'panel' | 'page'>(() => {
        if (typeof window !== 'undefined') return (localStorage.getItem('redwire_testcase_view_mode') as 'panel' | 'page') || 'panel';
        return 'panel';
    });
    useEffect(() => { localStorage.setItem('redwire_testcase_view_mode', viewMode); }, [viewMode]);

    const handleTestcaseClick = (testcaseId: string) => {
        if (viewMode === 'page') {
            router.push(`/testcases/${testcaseId}?engagementId=${engagementId}&tab=testcases`);
        } else {
            setSelectedTestcaseId(testcaseId);
        }
    };

    // Search & sort (persisted)
    const [search, setSearch] = useState('');
    const [showFilters, setShowFilters] = useState(false);
    const [filters, setFilters] = useState<{
        categories: string[];
        status: '' | 'pending' | 'executed';
        result: '' | 'passed' | 'failed';
        createdBy: string;
        dateAfter: string;
    }>({ categories: [], status: '', result: '', createdBy: '', dateAfter: '' });

    const hasActiveFilters = filters.categories.length > 0 || !!filters.status || !!filters.result || !!filters.createdBy || !!filters.dateAfter;

    const toggleCategory = (cat: string) => setFilters(prev => ({
        ...prev,
        categories: prev.categories.includes(cat) ? prev.categories.filter(c => c !== cat) : [...prev.categories, cat],
    }));
    const clearFilters = () => setFilters({ categories: [], status: '', result: '', createdBy: '', dateAfter: '' });

    const [sortField, setSortField] = useState<string>(() => {
        if (typeof window !== 'undefined') return localStorage.getItem('redwire_sort_engagement_testcases_field') || 'title';
        return 'title';
    });
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') return (localStorage.getItem('redwire_sort_engagement_testcases_order') as 'asc' | 'desc') || 'asc';
        return 'asc';
    });
    useEffect(() => { localStorage.setItem('redwire_sort_engagement_testcases_field', sortField); localStorage.setItem('redwire_sort_engagement_testcases_order', sortOrder); }, [sortField, sortOrder]);

    // Tree view
    const testCaseTree = useMemo(() => buildTestCaseTree(testcases), [testcases]);
    const tcStorageKey = `redwire_tc_expanded_${engagementId}`;
    const [tcExpandedIds, setTcExpandedIds] = useState<Set<string>>(new Set());
    const tcInitialized = useRef(false);

    useEffect(() => {
        if (tcInitialized.current || testcases.length === 0) return;
        tcInitialized.current = true;
        const saved = localStorage.getItem(tcStorageKey);
        if (saved) { try { const parsed = JSON.parse(saved); if (Array.isArray(parsed)) { setTcExpandedIds(new Set(parsed)); return; } } catch { /* ignore */ } }
        const parentIds = new Set(testcases.filter(tc => testcases.some(child => child.parent_id === tc.id)).map(tc => tc.id));
        setTcExpandedIds(parentIds);
    }, [testcases, tcStorageKey]);

    useEffect(() => { if (!tcInitialized.current) return; localStorage.setItem(tcStorageKey, JSON.stringify([...tcExpandedIds])); }, [tcExpandedIds, tcStorageKey]);

    const filteredTestCaseTree = useMemo(() => {
        const term = search.toLowerCase();
        function matchesNode(node: TestCaseTreeNode) {
            const matchesText = !term || node.title.toLowerCase().includes(term) || node.category.toLowerCase().includes(term) || node.description.toLowerCase().includes(term);
            const matchesCat = filters.categories.length === 0 || filters.categories.includes(node.category);
            const matchesStatus = !filters.status || (filters.status === 'executed' ? node.is_executed : !node.is_executed);
            const matchesResult = !filters.result || (node.is_executed && (filters.result === 'passed' ? node.is_successful : !node.is_successful));
            const matchesCreatedBy = !filters.createdBy || (node.created_by_username || '').toLowerCase().includes(filters.createdBy.toLowerCase());
            const matchesDate = !filters.dateAfter || new Date(node.created_at) >= new Date(filters.dateAfter);
            return matchesText && matchesCat && matchesStatus && matchesResult && matchesCreatedBy && matchesDate;
        }
        if (!search && !hasActiveFilters) return testCaseTree;
        function filterNodes(nodes: TestCaseTreeNode[]): TestCaseTreeNode[] {
            const result: TestCaseTreeNode[] = [];
            for (const node of nodes) { const fc = filterNodes(node.children); if (matchesNode(node) || fc.length > 0) result.push({ ...node, children: fc }); }
            return result;
        }
        return filterNodes(testCaseTree);
    }, [testCaseTree, search, filters, hasActiveFilters]);

    const displayTestCases = useMemo(() => {
        function sortNodes(nodes: TestCaseTreeNode[]): TestCaseTreeNode[] {
            const sorted = [...nodes].sort((a, b) => {
                let cmp = 0;
                switch (sortField) {
                    case 'title': cmp = a.title.localeCompare(b.title); break;
                    case 'category': cmp = a.category.localeCompare(b.category); break;
                    case 'is_executed': cmp = (a.is_executed ? 1 : 0) - (b.is_executed ? 1 : 0); break;
                    case 'result': cmp = (a.is_executed ? (a.is_successful ? 2 : 1) : 0) - (b.is_executed ? (b.is_successful ? 2 : 1) : 0); break;
                    case 'created_at': cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime(); break;
                    case 'unresolved_thread_count': cmp = (a.unresolved_thread_count || 0) - (b.unresolved_thread_count || 0); break;
                    case 'created_by_username': cmp = (a.created_by_username || '').localeCompare(b.created_by_username || ''); break;
                    default: cmp = a.title.localeCompare(b.title);
                }
                return sortOrder === 'desc' ? -cmp : cmp;
            });
            return sorted.map(node => ({ ...node, children: sortNodes(node.children) }));
        }
        const sortedTree = sortNodes(filteredTestCaseTree);
        return flattenTree(sortedTree, search ? new Set(testcases.map(tc => tc.id)) : tcExpandedIds);
    }, [filteredTestCaseTree, tcExpandedIds, search, testcases, sortField, sortOrder]);

    const toggleTcExpand = (id: string) => { setTcExpandedIds(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; }); };
    const expandAllTc = () => { setTcExpandedIds(new Set(testcases.filter(tc => testcases.some(child => child.parent_id === tc.id)).map(tc => tc.id))); };
    const collapseAllTc = () => { setTcExpandedIds(new Set()); };

    const isTreeView = !search && !hasActiveFilters && sortField === 'title' && sortOrder === 'asc';

    // DnD
    const tcDndSensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
    const [activeDragId, setActiveDragId] = useState<string | null>(null);
    const handleTcDragStart = useCallback((event: DragStartEvent) => { setActiveDragId(event.active.id as string); }, []);
    const handleTcDragEnd = useCallback(async (event: DragEndEvent) => {
        setActiveDragId(null);
        const { active, over } = event;
        if (!over || active.id === over.id) return;
        const draggedId = active.id as string;
        const targetId = over.id as string;
        const draggedTc = testcases.find(tc => tc.id === draggedId);
        if (!draggedTc) return;
        function isDescendant(parentId: string, targetId: string): boolean {
            const children = testcases.filter(tc => tc.parent_id === parentId);
            for (const child of children) { if (child.id === targetId || isDescendant(child.id, targetId)) return true; }
            return false;
        }
        if (isDescendant(draggedId, targetId)) { toast.error('Cannot move a test case into its own child'); return; }
        try { await updateTestCase.mutateAsync({ id: draggedId, parent_id: targetId }); toast.success('Test case moved successfully'); } catch (error: any) { toast.error(getErrorMessage(error, 'Failed to move test case')); }
    }, [testcases, updateTestCase]);

    // Move dialog
    const [isMoveDialogOpen, setIsMoveDialogOpen] = useState(false);
    const [moveTarget, setMoveTarget] = useState<{ id: string; title: string; parent_id: string | null } | null>(null);
    const handleOpenMove = (target: { id: string; title: string; parent_id: string | null }) => { setMoveTarget(target); setIsMoveDialogOpen(true); };
    const handleMove = async (testcaseId: string, newParentId: string | null) => {
        try { await updateTestCase.mutateAsync({ id: testcaseId, parent_id: newParentId }); toast.success('Test case moved successfully'); setIsMoveDialogOpen(false); setMoveTarget(null); } catch (error: any) { toast.error(getErrorMessage(error, 'Failed to move test case')); }
    };

    // Runbook import
    const { data: runbooksList = [] } = useRunbooks();
    const applyRunbook = useApplyRunbook();
    const [isImportRunbookOpen, setIsImportRunbookOpen] = useState(false);
    const [importingRunbookId, setImportingRunbookId] = useState<string | null>(null);
    const [rbImportSearch, setRbImportSearch] = useState('');
    const [rbImportTypeFilter, setRbImportTypeFilter] = useState('');
    const [previewRunbook, setPreviewRunbook] = useState<Runbook | null>(null);
    const { data: runbookTypeConfigs = [] } = useConfigurableTypes('runbook');
    const runbookTypeColors = useMemo(() => {
        const map: Record<string, string> = {};
        runbookTypeConfigs.forEach(t => { map[t.name] = t.color; });
        return map;
    }, [runbookTypeConfigs]);
    const filteredImportRunbooks = useMemo(() => {
        return runbooksList.filter(r => {
            const matchesSearch = r.name.toLowerCase().includes(rbImportSearch.toLowerCase()) ||
                (r.description || '').toLowerCase().includes(rbImportSearch.toLowerCase()) ||
                (r.runbook_type || '').toLowerCase().includes(rbImportSearch.toLowerCase());
            const matchesType = !rbImportTypeFilter || r.runbook_type === rbImportTypeFilter;
            return matchesSearch && matchesType;
        });
    }, [runbooksList, rbImportSearch, rbImportTypeFilter]);

    const handleSort = (field: string) => {
        if (sortField === field) setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
        else { setSortField(field); setSortOrder('asc'); }
    };

    return (
        <>
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="flex flex-row items-center justify-between">
                <div className="flex items-center gap-3">
                    <div>
                        <CardTitle className="text-white">Test Cases</CardTitle>
                        <CardDescription>Security testing procedures and results</CardDescription>
                    </div>
                    <Badge variant="outline" className={cn("text-[10px] gap-1 h-5 px-1.5 transition-all", isTreeView ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10" : "border-blue-500/30 text-blue-400 bg-blue-500/10")}>
                        {isTreeView ? <TreePine className="h-3 w-3" /> : <Table2 className="h-3 w-3" />}
                        {isTreeView ? 'Tree' : 'Table'}
                    </Badge>
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative w-64 mr-2">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
                        <Input placeholder="Search test cases..." className="pl-8 bg-slate-900/50 border-slate-700 text-xs h-9" value={search} onChange={(e) => setSearch(e.target.value)} />
                    </div>
                    <Button
                        size="icon" variant="ghost"
                        className={cn("h-9 w-9", hasActiveFilters ? "text-primary bg-primary/10" : "text-slate-400 hover:text-white")}
                        title="Advanced Filters"
                        onClick={() => setShowFilters(!showFilters)}
                    >
                        <Filter className="h-4 w-4" />
                    </Button>
                    {isTreeView && (
                        <>
                            <Button variant="outline" size="sm" onClick={expandAllTc} className="text-slate-300 border-slate-700 hover:bg-slate-800 h-9 text-xs">Expand All</Button>
                            <Button variant="outline" size="sm" onClick={collapseAllTc} className="text-slate-300 border-slate-700 hover:bg-slate-800 h-9 text-xs">Collapse All</Button>
                        </>
                    )}
                    {!isTreeView && (
                        <Button variant="outline" size="sm" onClick={() => { setSearch(''); setSortField('title'); setSortOrder('asc'); }} className="text-slate-300 border-slate-700 hover:bg-slate-800 h-9 text-xs gap-1.5">
                            <TreePine className="h-3.5 w-3.5" />Back to Tree
                        </Button>
                    )}
                    <ColumnToggle columns={TESTCASES_COLUMNS} visible={visibleCols} onToggle={toggleCol} />
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
                    {canCreateTestCase && (
                        <>
                            <Button variant="outline" size="sm" onClick={() => setIsImportRunbookOpen(true)} className="text-slate-300 border-slate-700 hover:bg-slate-800 h-9 text-xs gap-1.5">
                                <GitBranch className="h-4 w-4" />Import Runbook
                            </Button>
                            <Button onClick={() => router.push(`/testcases/new?engagementId=${engagementId}`)} size="sm" className="bg-primary hover:bg-primary/90">
                                <Plus className="h-4 w-4 mr-2" />Add Test Case
                            </Button>
                        </>
                    )}
                </div>
            </CardHeader>

            {/* Active filter chips */}
            {hasActiveFilters && (
                <div className="px-6 pb-2 flex flex-wrap gap-1.5">
                    {filters.categories.map(c => (
                        <Badge key={c} className="bg-primary/10 text-primary border border-primary/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-primary/20" onClick={() => toggleCategory(c)}>
                            {c.replace('_', ' ')}<X className="h-3 w-3" />
                        </Badge>
                    ))}
                    {filters.status && (
                        <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-blue-500/20" onClick={() => setFilters(p => ({ ...p, status: '' }))}>
                            {filters.status}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    {filters.result && (
                        <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-emerald-500/20" onClick={() => setFilters(p => ({ ...p, result: '' }))}>
                            {filters.result}<X className="h-3 w-3" />
                        </Badge>
                    )}
                    {filters.createdBy && (
                        <Badge className="bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-[10px] gap-1 pr-1 cursor-pointer hover:bg-primary/90/20" onClick={() => setFilters(p => ({ ...p, createdBy: '' }))}>
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
                        {/* Category */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Category</span>
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                                {Object.keys(testCaseCategoryStyles).map(cat => (
                                    <label key={cat} className="flex items-center gap-1.5 cursor-pointer">
                                        <Checkbox checked={filters.categories.includes(cat)} onCheckedChange={() => toggleCategory(cat)} className="h-3.5 w-3.5" />
                                        <span className="text-xs text-slate-300">{cat.replace(/_/g, ' ')}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                        {/* Status */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Status</span>
                            <div className="flex gap-1">
                                {(['', 'pending', 'executed'] as const).map(v => (
                                    <button key={v} onClick={() => setFilters(p => ({ ...p, status: v }))} className={cn('px-2.5 py-1 rounded text-xs font-medium transition-colors', filters.status === v ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-slate-800 text-slate-400 border border-slate-700 hover:text-white')}>
                                        {v === '' ? 'All' : v.charAt(0).toUpperCase() + v.slice(1)}
                                    </button>
                                ))}
                            </div>
                        </div>
                        {/* Result */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Result</span>
                            <div className="flex gap-1">
                                {(['', 'passed', 'failed'] as const).map(v => (
                                    <button key={v} onClick={() => setFilters(p => ({ ...p, result: v }))} className={cn('px-2.5 py-1 rounded text-xs font-medium transition-colors', filters.result === v ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700 hover:text-white')}>
                                        {v === '' ? 'All' : v.charAt(0).toUpperCase() + v.slice(1)}
                                    </button>
                                ))}
                            </div>
                        </div>
                        {/* Created By */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Created By</span>
                            <input type="text" placeholder="username..." value={filters.createdBy} onChange={e => setFilters(p => ({ ...p, createdBy: e.target.value }))} className="h-7 text-xs bg-slate-800/50 border border-slate-700 rounded px-2 text-white placeholder:text-slate-600 focus:outline-none focus:border-primary w-32" />
                        </div>
                        {/* Date After */}
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Created After</span>
                            <input type="date" value={filters.dateAfter} onChange={e => setFilters(p => ({ ...p, dateAfter: e.target.value }))} className="h-7 text-xs bg-slate-800/50 border border-slate-700 rounded px-2 text-white focus:outline-none focus:border-primary w-36 [color-scheme:dark]" />
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
                    <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
                ) : displayTestCases.length === 0 ? (
                    <div className="text-center py-8 text-slate-400"><CheckSquare className="h-12 w-12 mx-auto mb-4 opacity-50" /><p>No test cases defined</p></div>
                ) : (
                    <DndContext sensors={tcDndSensors} collisionDetection={closestCenter} onDragStart={handleTcDragStart} onDragEnd={handleTcDragEnd}>
                        <SortableContext items={displayTestCases.map(tc => tc.id)} strategy={verticalListSortingStrategy}>
                            <Table>
                                <TableHeader>
                                    <TableRow className="border-slate-800">
                                        <TableHead className="text-slate-300 cursor-pointer select-none hover:text-white transition-colors" onClick={() => handleSort('title')}><span className="flex items-center">Title <SortIcon field="title" currentField={sortField} order={sortOrder} /></span></TableHead>
                                        {col('category') && <TableHead className="text-slate-300 cursor-pointer select-none hover:text-white transition-colors" onClick={() => handleSort('category')}><span className="flex items-center">Category <SortIcon field="category" currentField={sortField} order={sortOrder} /></span></TableHead>}
                                        {col('status') && <TableHead className="text-slate-400 cursor-pointer select-none hover:text-white transition-colors" onClick={() => handleSort('is_executed')}><span className="flex items-center">Status <SortIcon field="is_executed" currentField={sortField} order={sortOrder} /></span></TableHead>}
                                        {col('result') && <TableHead className="text-slate-400 cursor-pointer select-none hover:text-white transition-colors" onClick={() => handleSort('result')}><span className="flex items-center">Result <SortIcon field="result" currentField={sortField} order={sortOrder} /></span></TableHead>}
                                        {col('discussions') && <TableHead className="text-slate-400 cursor-pointer select-none hover:text-white transition-colors" onClick={() => handleSort('unresolved_thread_count')}><span className="flex items-center">Discussions <SortIcon field="unresolved_thread_count" currentField={sortField} order={sortOrder} /></span></TableHead>}
                                        {col('createdBy') && <TableHead className="text-slate-400 cursor-pointer select-none hover:text-white transition-colors" onClick={() => handleSort('created_by_username')}><span className="flex items-center">Created By <SortIcon field="created_by_username" currentField={sortField} order={sortOrder} /></span></TableHead>}
                                        {col('created') && <TableHead className="text-slate-400 cursor-pointer select-none hover:text-white transition-colors" onClick={() => handleSort('created_at')}><span className="flex items-center">Created <SortIcon field="created_at" currentField={sortField} order={sortOrder} /></span></TableHead>}
                                        {col('links') && <TableHead className="text-slate-400">Links</TableHead>}
                                        <TableHead className="text-slate-400 text-right">Actions</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {displayTestCases.map(tc => (
                                        <TestCaseRow key={tc.id} testcase={tc} engagementId={engagementId} depth={isTreeView ? tc.depth : 0} hasChildren={isTreeView && tc.children.length > 0} isExpanded={tcExpandedIds.has(tc.id)} onToggleExpand={toggleTcExpand} onAddVaultItem={onAddVaultItem} onAddCleanup={onAddCleanup} onAddFinding={onAddFinding} onLinkAsset={onLinkAsset} onLinkIntel={onLinkIntel} onLinkInfra={onLinkInfra} onMove={handleOpenMove} noteItems={notesByTestCase[tc.id] || []} isDraggable={isTreeView} col={col} onViewDetail={handleTestcaseClick} />
                                    ))}
                                </TableBody>
                            </Table>
                        </SortableContext>
                        <DragOverlay>
                            {activeDragId ? (<div className="bg-slate-800 border border-primary/50 rounded-lg px-4 py-2 shadow-xl shadow-primary/20 text-sm text-white font-medium">{testcases.find(tc => tc.id === activeDragId)?.title || 'Test Case'}</div>) : null}
                        </DragOverlay>
                    </DndContext>
                )}
            </CardContent>
        </Card>

        <MoveTestCaseDialog open={isMoveDialogOpen} onOpenChange={(open) => { setIsMoveDialogOpen(open); if (!open) setMoveTarget(null); }} testcases={testcases || []} movingTestCase={moveTarget} isMoving={updateTestCase.isPending} onMove={handleMove} />

        {/* Import Runbook Dialog */}
        <Dialog open={isImportRunbookOpen} onOpenChange={(open) => { setIsImportRunbookOpen(open); if (!open) { setPreviewRunbook(null); setRbImportSearch(''); setRbImportTypeFilter(''); } }}>
            <DialogContent className="max-w-4xl">
                <DialogHeader>
                    <DialogTitle className="text-white flex items-center gap-2"><GitBranch className="h-5 w-5 text-primary" />Import Runbook</DialogTitle>
                    <DialogDescription>Browse runbooks, preview their contents, then apply to create test cases.</DialogDescription>
                </DialogHeader>
                <div className="grid grid-cols-5 gap-4 min-h-[400px] max-h-[65vh]">
                    {/* Left panel: search + list */}
                    <div className="col-span-2 flex flex-col gap-3 overflow-hidden">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                            <Input
                                placeholder="Search runbooks..."
                                value={rbImportSearch}
                                onChange={e => setRbImportSearch(e.target.value)}
                                className="pl-9 bg-slate-800/50 border-slate-700 text-sm"
                            />
                        </div>
                        {runbookTypeConfigs.length > 0 && (
                            <Select
                                value={rbImportTypeFilter || 'all'}
                                onValueChange={val => setRbImportTypeFilter(val === 'all' ? '' : val)}
                            >
                                <SelectTrigger className="h-9 bg-slate-800/50 border-slate-700 text-sm">
                                    <SelectValue placeholder="All Types" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All Types</SelectItem>
                                    {runbookTypeConfigs.map(t => (
                                        <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        )}
                        <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
                            {filteredImportRunbooks.length === 0 ? (
                                <div className="text-center py-8 text-slate-500"><GitBranch className="h-10 w-10 mx-auto mb-2 opacity-20" /><p className="text-sm">{runbooksList.length === 0 ? 'No runbooks available' : 'No runbooks match'}</p></div>
                            ) : (
                                filteredImportRunbooks.map(rb => {
                                    const isSelected = previewRunbook?.id === rb.id;
                                    const typeColor = rb.runbook_type ? (runbookTypeColors[rb.runbook_type] || '#a855f7') : null;
                                    return (
                                        <button
                                            key={rb.id}
                                            onClick={() => setPreviewRunbook(rb)}
                                            className={cn(
                                                'w-full text-left px-3 py-2.5 rounded-lg border transition-all',
                                                isSelected
                                                    ? 'border-primary/50 bg-primary/10'
                                                    : 'border-slate-800 hover:border-slate-700 hover:bg-slate-800/40'
                                            )}
                                        >
                                            <div className="flex items-center gap-2">
                                                <GitBranch className="h-3.5 w-3.5 text-primary shrink-0" />
                                                <span className="text-sm font-medium text-white truncate flex-1">{rb.name}</span>
                                                <Badge variant="secondary" className="text-[10px] shrink-0">{rb.items.length}</Badge>
                                            </div>
                                            <div className="flex items-center gap-2 mt-1">
                                                {rb.runbook_type && typeColor && (
                                                    <Badge variant="outline" className="text-[10px] py-0 px-1.5" style={{ backgroundColor: `${typeColor}15`, color: typeColor, borderColor: `${typeColor}33` }}>
                                                        {rb.runbook_type}
                                                    </Badge>
                                                )}
                                                {rb.description && <span className="text-[11px] text-slate-500 truncate">{rb.description}</span>}
                                            </div>
                                        </button>
                                    );
                                })
                            )}
                        </div>
                    </div>

                    {/* Right panel: preview */}
                    <div className="col-span-3 border-l border-slate-800 pl-4 flex flex-col overflow-hidden">
                        {!previewRunbook ? (
                            <div className="flex-1 flex items-center justify-center text-slate-500">
                                <div className="text-center">
                                    <GitBranch className="h-10 w-10 mx-auto mb-3 opacity-20" />
                                    <p className="text-sm">Select a runbook to preview</p>
                                </div>
                            </div>
                        ) : (
                            <>
                                <div className="mb-3">
                                    <h3 className="text-base font-semibold text-white">{previewRunbook.name}</h3>
                                    <div className="flex items-center gap-2 mt-1">
                                        {previewRunbook.runbook_type && (() => {
                                            const c = runbookTypeColors[previewRunbook.runbook_type] || '#a855f7';
                                            return <Badge variant="outline" className="text-[10px]" style={{ backgroundColor: `${c}15`, color: c, borderColor: `${c}33` }}>{previewRunbook.runbook_type}</Badge>;
                                        })()}
                                        <Badge variant="secondary" className="text-[10px]">{previewRunbook.items.length} items</Badge>
                                    </div>
                                    {previewRunbook.description && <p className="text-xs text-slate-400 mt-1.5">{previewRunbook.description}</p>}
                                </div>
                                <div className="flex-1 overflow-y-auto border border-slate-800 rounded-lg p-3 space-y-0.5">
                                    <RunbookPreviewTree items={previewRunbook.items} typeColors={runbookTypeColors} />
                                </div>
                                <div className="mt-3 flex justify-end">
                                    <Button
                                        className="bg-primary hover:bg-primary/90 text-white gap-2"
                                        disabled={importingRunbookId === previewRunbook.id}
                                        onClick={async () => {
                                            setImportingRunbookId(previewRunbook.id);
                                            try {
                                                await applyRunbook.mutateAsync({ runbookId: previewRunbook.id, engagementId });
                                                toast.success(`Runbook "${previewRunbook.name}" applied — ${previewRunbook.items.length} test cases created`);
                                                setIsImportRunbookOpen(false);
                                                setPreviewRunbook(null);
                                            } catch (err: any) {
                                                toast.error(err?.response?.data?.detail || 'Failed to apply runbook');
                                            } finally {
                                                setImportingRunbookId(null);
                                            }
                                        }}
                                    >
                                        {importingRunbookId === previewRunbook.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitBranch className="h-4 w-4" />}
                                        Apply Runbook
                                    </Button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
                <DialogFooter><Button variant="ghost" onClick={() => setIsImportRunbookOpen(false)}>Cancel</Button></DialogFooter>
            </DialogContent>
        </Dialog>
        <TestCaseDetailSheet
            testcaseId={selectedTestcaseId}
            engagementId={engagementId}
            open={!!selectedTestcaseId}
            onOpenChange={(open) => { if (!open) setSelectedTestcaseId(null); }}
            nonModal
        />

        </>
    );
}

// ─── RunbookPreviewTree: renders a runbook's template hierarchy ──
function RunbookPreviewTree({ items, typeColors, depth = 0 }: { items: RunbookItem[]; typeColors: Record<string, string>; depth?: number }) {
    // Build tree from flat items
    const tree = useMemo(() => {
        if (depth > 0) return []; // only build at root level
        const map = new Map<string, RunbookItem & { children: RunbookItem[] }>();
        const roots: (RunbookItem & { children: RunbookItem[] })[] = [];
        for (const item of items) {
            map.set(item.id, { ...item, children: [] });
        }
        for (const item of items) {
            const node = map.get(item.id)!;
            if (item.parent_id && map.has(item.parent_id)) {
                map.get(item.parent_id)!.children.push(node);
            } else {
                roots.push(node);
            }
        }
        const sortAll = (nodes: typeof roots) => {
            nodes.sort((a, b) => a.sort_order - b.sort_order);
            nodes.forEach(n => sortAll(n.children as typeof roots));
        };
        sortAll(roots);
        return roots;
    }, [items, depth]);

    const renderNodes = (nodes: (RunbookItem & { children: RunbookItem[] })[], d: number) => (
        <div className="space-y-0.5">
            {nodes.map(item => {
                const catColor = typeColors[item.template?.category || ''] || '#06b6d4';
                return (
                    <div key={item.id}>
                        <div
                            className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-slate-800/40"
                            style={{ paddingLeft: `${d * 20 + 8}px` }}
                        >
                            {item.children.length > 0 && <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                            {item.children.length === 0 && <div className="w-3.5" />}
                            <span className="text-sm text-white">{item.template?.title || 'Unknown template'}</span>
                            <Badge variant="outline" className="ml-auto text-[10px]" style={{ backgroundColor: `${catColor}15`, color: catColor, borderColor: `${catColor}33` }}>
                                {item.template?.category || '—'}
                            </Badge>
                        </div>
                        {item.children.length > 0 && renderNodes(item.children as (RunbookItem & { children: RunbookItem[] })[], d + 1)}
                    </div>
                );
            })}
        </div>
    );

    return <>{renderNodes(tree, 0)}</>;
}

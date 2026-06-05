/**
 * templates/page.tsx — Template Library Hub
 *
 * Five-tab management centre for all reusable template types.
 * ADMIN / TEAM_LEAD users can create, edit, and delete; others see
 * a "View Only" badge.
 *
 * **Finding Templates** — searchable table with title, category badge
 *   (coloured via `useConfigurableTypes`), and truncated description.
 *   Click opens a preview dialog with rendered markdown.
 *
 * **Test Case Templates** — same pattern, category-coloured badges.
 *
 * **Runbooks** — hierarchical test-case-template trees. Table shows
 *   name, description, item count. Click opens a preview dialog with
 *   `RunbookTreePreview` rendering a nested tree view.
 *
 * **Report Layout Templates** — table with name, description, and
 *   section count. Click opens a preview showing sections in order
 *   with type badges (Text / Findings / Test Cases / Cleanup).
 *
 * **Report Themes** — table with name, colour swatches, font family,
 *   default badge. Inline edit and delete actions.
 *
 * Helpers: `canManageTemplates`, `buildRunbookTree`,
 * `RunbookTreePreview`. All tab lists use `relevanceComparator` for
 * search sorting. Deep-link to a tab via `?tab=` query parameter.
 */
'use client';

import { useState, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/types';
import { cn } from '@/lib/utils';
import {
    useFindingTemplates,
    useDeleteFindingTemplate,
    useSubmitFindingTemplate,
    useWithdrawFindingTemplate,
    useApproveFindingTemplate,
    useRejectFindingTemplate,
    useUnpublishFindingTemplate,
    FindingTemplate,
    TemplateStatus,
} from '@/lib/hooks/use-findings';
import {
    useTestCaseTemplates,
    useDeleteTestCaseTemplate,
    useSubmitTestCaseTemplate,
    useWithdrawTestCaseTemplate,
    useApproveTestCaseTemplate,
    useRejectTestCaseTemplate,
    useUnpublishTestCaseTemplate,
    TestCaseTemplate,
} from '@/lib/hooks/use-testcase-templates';
import {
    useRunbooks,
    useDeleteRunbook,
    useSubmitRunbook,
    useWithdrawRunbook,
    useApproveRunbook,
    useRejectRunbook,
    useUnpublishRunbook,
    Runbook,
    RunbookItem,
} from '@/lib/hooks/use-runbooks';
import {
    useReportLayoutTemplates,
    useDeleteReportLayoutTemplate,
} from '@/lib/hooks/use-report-layout-templates';
import { useReportThemes, useDeleteReportTheme, ReportTheme } from '@/lib/hooks/use-report-themes';
import { ReportLayoutTemplate, SectionType } from '@/lib/types';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { relevanceComparator } from '@/lib/search-relevance';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
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
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import {
    BookOpen,
    Plus,
    Search,
    Pencil,
    Trash2,
    Loader2,
    FileText,
    ClipboardList,
    ShieldAlert,
    GitBranch,
    ChevronRight,
    LayoutTemplate,
    Type,
    Palette,
    Send,
    Undo2,
    Check,
    X,
    AlertTriangle,
    SlidersHorizontal,
    ArrowUp,
    ArrowDown,
    ChevronsUpDown,
} from 'lucide-react';
import { MarkingProfilesManager } from '@/components/marking/marking-profiles-manager';
import { useMarkingProfiles } from '@/lib/hooks/use-marking-profiles';

// ─── Permission helper ───────────────────────────────────────────
function canManageTemplates(role?: UserRole) {
    return role === UserRole.ADMIN || role === UserRole.TEAM_LEAD;
}

// ─── Template status badge ───────────────────────────────────────
const TEMPLATE_STATUS_STYLES: Record<TemplateStatus, { bg: string; fg: string; border: string; label: string }> = {
    DRAFT:     { bg: 'rgba(148,163,184,0.10)', fg: '#94a3b8', border: 'rgba(148,163,184,0.30)', label: 'Draft' },
    SUBMITTED: { bg: 'rgba(234,179,8,0.10)',   fg: '#eab308', border: 'rgba(234,179,8,0.30)',   label: 'Submitted' },
    PUBLISHED: { bg: 'rgba(34,197,94,0.10)',   fg: '#22c55e', border: 'rgba(34,197,94,0.30)',   label: 'Published' },
};

function TemplateStatusBadge({ status }: { status: TemplateStatus }) {
    const s = TEMPLATE_STATUS_STYLES[status];
    return (
        <Badge variant="outline" className="text-[10px] uppercase tracking-wider" style={{ backgroundColor: s.bg, color: s.fg, borderColor: s.border }}>
            {s.label}
        </Badge>
    );
}

// ─── Helper: build tree from flat RunbookItem list ───────────────
function buildRunbookTree(items: RunbookItem[]): (RunbookItem & { children: any[] })[] {
    const map = new Map<string, RunbookItem & { children: any[] }>();
    const roots: (RunbookItem & { children: any[] })[] = [];
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
    // Sort children by sort_order
    const sortChildren = (nodes: typeof roots) => {
        nodes.sort((a, b) => a.sort_order - b.sort_order);
        nodes.forEach(n => sortChildren(n.children));
    };
    sortChildren(roots);
    return roots;
}

function RunbookTreePreview({ items, depth = 0, categoryColors }: { items: (RunbookItem & { children: any[] })[]; depth?: number; categoryColors?: Record<string, string> }) {
    return (
        <div className="space-y-1">
            {items.map(item => {
                const catColor = categoryColors?.[item.template?.category || ''] || '#06b6d4';
                return (
                    <div key={item.id}>
                        <div className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-slate-800/40" style={{ paddingLeft: `${depth * 24 + 8}px` }}>
                            {item.children.length > 0 && <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                            {item.children.length === 0 && <div className="w-3.5" />}
                            <span className="text-sm text-white">{item.template?.title || 'Unknown template'}</span>
                            <Badge variant="outline" className="ml-auto text-[10px]" style={{ backgroundColor: `${catColor}15`, color: catColor, borderColor: `${catColor}33` }}>
                                {item.template?.category || '—'}
                            </Badge>
                        </div>
                        {item.children.length > 0 && <RunbookTreePreview items={item.children} depth={depth + 1} categoryColors={categoryColors} />}
                    </div>
                );
            })}
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════
// Main Templates Page
// ═══════════════════════════════════════════════════════════════════
export default function TemplatesPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { user } = useAuthStore();
    const canManage = canManageTemplates(user?.role as UserRole | undefined);

    // ── Finding templates ──
    const { data: findingTemplates = [], isLoading: ftLoading } = useFindingTemplates();
    const deleteFT = useDeleteFindingTemplate();
    const submitFT = useSubmitFindingTemplate();
    const withdrawFT = useWithdrawFindingTemplate();
    const approveFT = useApproveFindingTemplate();
    const rejectFT = useRejectFindingTemplate();
    const unpublishFT = useUnpublishFindingTemplate();

    // ── Test case templates ──
    const { data: tcTemplates = [], isLoading: tcLoading } = useTestCaseTemplates();
    const deleteTC = useDeleteTestCaseTemplate();
    const submitTC = useSubmitTestCaseTemplate();
    const withdrawTC = useWithdrawTestCaseTemplate();
    const approveTC = useApproveTestCaseTemplate();
    const rejectTC = useRejectTestCaseTemplate();
    const unpublishTC = useUnpublishTestCaseTemplate();

    // ── Configurable types for colors ──
    const { data: findingCategoryTypes = [] } = useConfigurableTypes('finding');
    const { data: testcaseCategoryTypes = [] } = useConfigurableTypes('testcase');

    const findingCategoryColors = useMemo(() => {
        const map: Record<string, string> = {};
        findingCategoryTypes.forEach(t => { map[t.name] = t.color; });
        return map;
    }, [findingCategoryTypes]);

    const testcaseCategoryColors = useMemo(() => {
        const map: Record<string, string> = {};
        testcaseCategoryTypes.forEach(t => { map[t.name] = t.color; });
        return map;
    }, [testcaseCategoryTypes]);

    // ── Runbooks ──
    const { data: runbooks = [], isLoading: rbLoading } = useRunbooks();
    const deleteRB = useDeleteRunbook();
    const submitRB = useSubmitRunbook();
    const withdrawRB = useWithdrawRunbook();
    const approveRB = useApproveRunbook();
    const rejectRB = useRejectRunbook();
    const unpublishRB = useUnpublishRunbook();

    // ── Runbook types for colors/filter ──
    const { data: runbookTypeConfigs = [] } = useConfigurableTypes('runbook');
    const runbookTypeColors = useMemo(() => {
        const map: Record<string, string> = {};
        runbookTypeConfigs.forEach(t => { map[t.name] = t.color; });
        return map;
    }, [runbookTypeConfigs]);

    // ── Report layout templates ──
    const { data: reportLayoutTemplates = [], isLoading: rltLoading } = useReportLayoutTemplates();
    const deleteRLT = useDeleteReportLayoutTemplate();

    // ── Report themes ──
    const { data: reportThemes = [], isLoading: rtLoading } = useReportThemes();
    const { data: markingProfiles = [] } = useMarkingProfiles();
    const deleteRT = useDeleteReportTheme();

    // ── UI state ──
    const [ftSearch, setFtSearch] = useState('');
    const [ftMineOnly, setFtMineOnly] = useState(false);
    const [ftFiltersOpen, setFtFiltersOpen] = useState(false);
    const [ftStatusFilter, setFtStatusFilter] = useState<'ALL' | TemplateStatus>('ALL');
    const [ftCategoryFilter, setFtCategoryFilter] = useState<string>('all');
    const [ftSortBy, setFtSortBy] = useState<'title' | 'status' | 'category' | 'updated_at'>('title');
    const [ftSortDir, setFtSortDir] = useState<'asc' | 'desc'>('asc');
    const [tcSearch, setTcSearch] = useState('');
    const [tcMineOnly, setTcMineOnly] = useState(false);
    const [tcFiltersOpen, setTcFiltersOpen] = useState(false);
    const [tcStatusFilter, setTcStatusFilter] = useState<'ALL' | TemplateStatus>('ALL');
    const [tcCategoryFilter, setTcCategoryFilter] = useState<string>('all');
    const [tcSortBy, setTcSortBy] = useState<'title' | 'status' | 'category' | 'updated_at'>('title');
    const [tcSortDir, setTcSortDir] = useState<'asc' | 'desc'>('asc');

    const [rbSearch, setRbSearch] = useState('');
    const [rbMineOnly, setRbMineOnly] = useState(false);
    const [rbFiltersOpen, setRbFiltersOpen] = useState(false);
    const [rbStatusFilter, setRbStatusFilter] = useState<'ALL' | TemplateStatus>('ALL');
    const [rbTypeFilter, setRbTypeFilter] = useState('');
    const [rbSortBy, setRbSortBy] = useState<'name' | 'status' | 'runbook_type' | 'updated_at'>('name');
    const [rbSortDir, setRbSortDir] = useState<'asc' | 'desc'>('asc');
    const [rltSearch, setRltSearch] = useState('');
    const [rtSearch, setRtSearch] = useState('');
    const [viewingFT, setViewingFT] = useState<FindingTemplate | null>(null);
    const [viewingTC, setViewingTC] = useState<TestCaseTemplate | null>(null);
    const [viewingRB, setViewingRB] = useState<Runbook | null>(null);
    const [viewingRLT, setViewingRLT] = useState<ReportLayoutTemplate | null>(null);
    const [rejectingFT, setRejectingFT] = useState<FindingTemplate | null>(null);
    const [rejectingTC, setRejectingTC] = useState<TestCaseTemplate | null>(null);
    const [rejectingRB, setRejectingRB] = useState<Runbook | null>(null);
    const [rejectNote, setRejectNote] = useState('');

    const { confirm, ConfirmDialog } = useConfirmDialog();

    // ── Filtered lists ──
    const ftStatusCounts = useMemo(() => {
        const visible = ftMineOnly ? findingTemplates.filter(t => t.created_by === user?.id) : findingTemplates;
        return {
            ALL: visible.length,
            DRAFT: visible.filter(t => t.status === 'DRAFT').length,
            SUBMITTED: visible.filter(t => t.status === 'SUBMITTED').length,
            PUBLISHED: visible.filter(t => t.status === 'PUBLISHED').length,
        };
    }, [findingTemplates, ftMineOnly, user?.id]);

    const ftCategoryOptions = useMemo(() => {
        const set = new Set<string>();
        for (const t of findingTemplates) {
            if (t.category) set.add(t.category);
        }
        return Array.from(set).sort();
    }, [findingTemplates]);

    const ftActiveFilterCount =
        (ftStatusFilter !== 'ALL' ? 1 : 0) + (ftCategoryFilter !== 'all' ? 1 : 0);

    const filteredFT = useMemo(() => {
        const search = ftSearch.toLowerCase().trim();
        let rows = findingTemplates.filter(t => {
            if (ftMineOnly && t.created_by !== user?.id) return false;
            if (ftStatusFilter !== 'ALL' && t.status !== ftStatusFilter) return false;
            if (ftCategoryFilter !== 'all' && (t.category || '') !== ftCategoryFilter) return false;
            if (!search) return true;
            return (
                t.title.toLowerCase().includes(search) ||
                (t.category || '').toLowerCase().includes(search) ||
                t.description.toLowerCase().includes(search)
            );
        });

        if (ftSortBy === 'title') {
            // When the user is searching and hasn't picked a non-default sort, fall back to relevance.
            if (search && ftSortDir === 'asc') {
                rows = rows.sort(
                    relevanceComparator(
                        search,
                        [t => t.title, t => t.category || '', t => t.description],
                        (a, b) => a.title.localeCompare(b.title),
                    ),
                );
            } else {
                rows = rows.sort((a, b) => a.title.localeCompare(b.title));
                if (ftSortDir === 'desc') rows.reverse();
            }
        } else {
            const STATUS_ORDER: Record<TemplateStatus, number> = { DRAFT: 0, SUBMITTED: 1, PUBLISHED: 2 };
            const cmp = (a: FindingTemplate, b: FindingTemplate) => {
                if (ftSortBy === 'status') return STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
                if (ftSortBy === 'category') return (a.category || '').localeCompare(b.category || '');
                // updated_at
                return (a.updated_at || '').localeCompare(b.updated_at || '');
            };
            rows = rows.sort((a, b) => {
                const r = cmp(a, b);
                if (r !== 0) return r;
                return a.title.localeCompare(b.title);
            });
            if (ftSortDir === 'desc') rows.reverse();
        }
        return rows;
    }, [findingTemplates, ftSearch, ftMineOnly, ftStatusFilter, ftCategoryFilter, ftSortBy, ftSortDir, user?.id]);

    const toggleFtSort = (col: 'title' | 'status' | 'category' | 'updated_at') => {
        if (ftSortBy === col) {
            setFtSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
        } else {
            setFtSortBy(col);
            setFtSortDir('asc');
        }
    };

    const clearFtFilters = () => {
        setFtStatusFilter('ALL');
        setFtCategoryFilter('all');
    };
    // ── Test case template filtering / sorting ──
    const tcStatusCounts = useMemo(() => {
        const visible = tcMineOnly ? tcTemplates.filter(t => t.created_by === user?.id) : tcTemplates;
        return {
            ALL: visible.length,
            DRAFT: visible.filter(t => t.status === 'DRAFT').length,
            SUBMITTED: visible.filter(t => t.status === 'SUBMITTED').length,
            PUBLISHED: visible.filter(t => t.status === 'PUBLISHED').length,
        };
    }, [tcTemplates, tcMineOnly, user?.id]);

    const tcCategoryOptions = useMemo(() => {
        const set = new Set<string>();
        for (const t of tcTemplates) {
            if (t.category) set.add(t.category);
        }
        return Array.from(set).sort();
    }, [tcTemplates]);

    const tcActiveFilterCount =
        (tcStatusFilter !== 'ALL' ? 1 : 0) + (tcCategoryFilter !== 'all' ? 1 : 0);

    const filteredTC = useMemo(() => {
        const search = tcSearch.toLowerCase().trim();
        let rows = tcTemplates.filter(t => {
            if (tcMineOnly && t.created_by !== user?.id) return false;
            if (tcStatusFilter !== 'ALL' && t.status !== tcStatusFilter) return false;
            if (tcCategoryFilter !== 'all' && t.category !== tcCategoryFilter) return false;
            if (!search) return true;
            return (
                t.title.toLowerCase().includes(search) ||
                t.category.toLowerCase().includes(search) ||
                t.description.toLowerCase().includes(search)
            );
        });

        if (tcSortBy === 'title') {
            if (search && tcSortDir === 'asc') {
                rows = rows.sort(
                    relevanceComparator(
                        search,
                        [t => t.title, t => t.category, t => t.description],
                        (a, b) => a.title.localeCompare(b.title),
                    ),
                );
            } else {
                rows = rows.sort((a, b) => a.title.localeCompare(b.title));
                if (tcSortDir === 'desc') rows.reverse();
            }
        } else {
            const STATUS_ORDER: Record<TemplateStatus, number> = { DRAFT: 0, SUBMITTED: 1, PUBLISHED: 2 };
            const cmp = (a: TestCaseTemplate, b: TestCaseTemplate) => {
                if (tcSortBy === 'status') return STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
                if (tcSortBy === 'category') return a.category.localeCompare(b.category);
                return (a.updated_at || '').localeCompare(b.updated_at || '');
            };
            rows = rows.sort((a, b) => {
                const r = cmp(a, b);
                if (r !== 0) return r;
                return a.title.localeCompare(b.title);
            });
            if (tcSortDir === 'desc') rows.reverse();
        }
        return rows;
    }, [tcTemplates, tcSearch, tcMineOnly, tcStatusFilter, tcCategoryFilter, tcSortBy, tcSortDir, user?.id]);

    const toggleTcSort = (col: 'title' | 'status' | 'category' | 'updated_at') => {
        if (tcSortBy === col) {
            setTcSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
        } else {
            setTcSortBy(col);
            setTcSortDir('asc');
        }
    };

    const clearTcFilters = () => {
        setTcStatusFilter('ALL');
        setTcCategoryFilter('all');
    };

    // ── Runbook filtering / sorting ──
    const rbStatusCounts = useMemo(() => {
        const visible = rbMineOnly ? runbooks.filter(r => r.created_by === user?.id) : runbooks;
        return {
            ALL: visible.length,
            DRAFT: visible.filter(r => r.status === 'DRAFT').length,
            SUBMITTED: visible.filter(r => r.status === 'SUBMITTED').length,
            PUBLISHED: visible.filter(r => r.status === 'PUBLISHED').length,
        };
    }, [runbooks, rbMineOnly, user?.id]);

    const rbActiveFilterCount =
        (rbStatusFilter !== 'ALL' ? 1 : 0) + (rbTypeFilter ? 1 : 0);

    const filteredRB = useMemo(() => {
        const search = rbSearch.toLowerCase().trim();
        let rows = runbooks.filter(r => {
            if (rbMineOnly && r.created_by !== user?.id) return false;
            if (rbStatusFilter !== 'ALL' && r.status !== rbStatusFilter) return false;
            if (rbTypeFilter && r.runbook_type !== rbTypeFilter) return false;
            if (!search) return true;
            return (
                r.name.toLowerCase().includes(search) ||
                (r.description || '').toLowerCase().includes(search) ||
                (r.runbook_type || '').toLowerCase().includes(search)
            );
        });

        if (rbSortBy === 'name') {
            if (search && rbSortDir === 'asc') {
                rows = rows.sort(
                    relevanceComparator(
                        search,
                        [r => r.name, r => r.description || '', r => r.runbook_type || ''],
                        (a, b) => a.name.localeCompare(b.name),
                    ),
                );
            } else {
                rows = rows.sort((a, b) => a.name.localeCompare(b.name));
                if (rbSortDir === 'desc') rows.reverse();
            }
        } else {
            const STATUS_ORDER: Record<TemplateStatus, number> = { DRAFT: 0, SUBMITTED: 1, PUBLISHED: 2 };
            const cmp = (a: Runbook, b: Runbook) => {
                if (rbSortBy === 'status') return STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
                if (rbSortBy === 'runbook_type') return (a.runbook_type || '').localeCompare(b.runbook_type || '');
                return (a.updated_at || '').localeCompare(b.updated_at || '');
            };
            rows = rows.sort((a, b) => {
                const r = cmp(a, b);
                if (r !== 0) return r;
                return a.name.localeCompare(b.name);
            });
            if (rbSortDir === 'desc') rows.reverse();
        }
        return rows;
    }, [runbooks, rbSearch, rbMineOnly, rbStatusFilter, rbTypeFilter, rbSortBy, rbSortDir, user?.id]);

    const toggleRbSort = (col: 'name' | 'status' | 'runbook_type' | 'updated_at') => {
        if (rbSortBy === col) {
            setRbSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
        } else {
            setRbSortBy(col);
            setRbSortDir('asc');
        }
    };

    const clearRbFilters = () => {
        setRbStatusFilter('ALL');
        setRbTypeFilter('');
    };
    const filteredRLT = reportLayoutTemplates.filter(t =>
        t.name.toLowerCase().includes(rltSearch.toLowerCase()) ||
        (t.description || '').toLowerCase().includes(rltSearch.toLowerCase())
    ).sort(relevanceComparator(rltSearch, [t => t.name, t => t.description || ''], (a, b) => a.name.localeCompare(b.name)));
    const filteredRT = reportThemes.filter(t =>
        t.name.toLowerCase().includes(rtSearch.toLowerCase()) ||
        (t.description || '').toLowerCase().includes(rtSearch.toLowerCase())
    ).sort(relevanceComparator(rtSearch, [t => t.name, t => t.description || ''], (a, b) => a.name.localeCompare(b.name)));

    // ── Delete handlers ──
    const handleDeleteFT = async (template: FindingTemplate) => {
        const confirmed = await confirm({
            title: 'Delete Finding Template',
            description: `Are you sure you want to delete "${template.title}"? This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        });
        if (!confirmed) return;
        try {
            await deleteFT.mutateAsync(template.id);
            toast.success('Finding template deleted');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to delete template'));
        }
    };

    // ── Workflow handlers ──
    const handleSubmitFT = async (template: FindingTemplate) => {
        const confirmed = await confirm({
            title: 'Submit for Review',
            description: `Submit "${template.title}" for review? Once submitted you will not be able to edit it until a reviewer rejects it back to draft.`,
            confirmLabel: 'Submit',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await submitFT.mutateAsync({ id: template.id });
            toast.success('Submitted for review');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to submit'));
        }
    };

    const handleWithdrawFT = async (template: FindingTemplate) => {
        try {
            await withdrawFT.mutateAsync({ id: template.id });
            toast.success('Submission withdrawn');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to withdraw'));
        }
    };

    const handleApproveFT = async (template: FindingTemplate) => {
        const confirmed = await confirm({
            title: 'Publish Template',
            description: `Publish "${template.title}" to the shared library? It will become visible to all users.`,
            confirmLabel: 'Publish',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await approveFT.mutateAsync({ id: template.id });
            toast.success('Template published');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to publish'));
        }
    };

    const handleUnpublishFT = async (template: FindingTemplate) => {
        const confirmed = await confirm({
            title: 'Unpublish Template',
            description: `Move "${template.title}" back to draft? It will no longer be visible to other users.`,
            confirmLabel: 'Unpublish',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await unpublishFT.mutateAsync({ id: template.id });
            toast.success('Template unpublished');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to unpublish'));
        }
    };

    const openRejectFT = (template: FindingTemplate) => {
        setRejectingFT(template);
        setRejectingTC(null);
        setRejectingRB(null);
        setRejectNote('');
    };

    // ── Test case template workflow handlers ──
    const handleSubmitTC = async (template: TestCaseTemplate) => {
        const confirmed = await confirm({
            title: 'Submit for Review',
            description: `Submit "${template.title}" for review? Once submitted you will not be able to edit it until a reviewer rejects it back to draft.`,
            confirmLabel: 'Submit',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await submitTC.mutateAsync({ id: template.id });
            toast.success('Submitted for review');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to submit'));
        }
    };

    const handleWithdrawTC = async (template: TestCaseTemplate) => {
        try {
            await withdrawTC.mutateAsync({ id: template.id });
            toast.success('Submission withdrawn');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to withdraw'));
        }
    };

    const handleApproveTC = async (template: TestCaseTemplate) => {
        const confirmed = await confirm({
            title: 'Publish Template',
            description: `Publish "${template.title}" to the shared library? It will become visible to all users.`,
            confirmLabel: 'Publish',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await approveTC.mutateAsync({ id: template.id });
            toast.success('Template published');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to publish'));
        }
    };

    const handleUnpublishTC = async (template: TestCaseTemplate) => {
        const confirmed = await confirm({
            title: 'Unpublish Template',
            description: `Move "${template.title}" back to draft? It will no longer be visible to other users.`,
            confirmLabel: 'Unpublish',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await unpublishTC.mutateAsync({ id: template.id });
            toast.success('Template unpublished');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to unpublish'));
        }
    };

    const openRejectTC = (template: TestCaseTemplate) => {
        setRejectingTC(template);
        setRejectingFT(null);
        setRejectingRB(null);
        setRejectNote('');
    };

    // ── Runbook workflow handlers ──
    const handleSubmitRB = async (rb: Runbook) => {
        const confirmed = await confirm({
            title: 'Submit for Review',
            description: `Submit "${rb.name}" for review? Once submitted you will not be able to edit it until a reviewer rejects it back to draft.`,
            confirmLabel: 'Submit',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await submitRB.mutateAsync({ id: rb.id });
            toast.success('Submitted for review');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to submit'));
        }
    };

    const handleWithdrawRB = async (rb: Runbook) => {
        try {
            await withdrawRB.mutateAsync({ id: rb.id });
            toast.success('Submission withdrawn');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to withdraw'));
        }
    };

    const handleApproveRB = async (rb: Runbook) => {
        const confirmed = await confirm({
            title: 'Publish Runbook',
            description: `Publish "${rb.name}" to the shared library? It will become visible to all users.`,
            confirmLabel: 'Publish',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await approveRB.mutateAsync({ id: rb.id });
            toast.success('Runbook published');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to publish'));
        }
    };

    const handleUnpublishRB = async (rb: Runbook) => {
        const confirmed = await confirm({
            title: 'Unpublish Runbook',
            description: `Move "${rb.name}" back to draft? It will no longer be visible to other users.`,
            confirmLabel: 'Unpublish',
            variant: 'warning',
        });
        if (!confirmed) return;
        try {
            await unpublishRB.mutateAsync({ id: rb.id });
            toast.success('Runbook unpublished');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to unpublish'));
        }
    };

    const openRejectRB = (rb: Runbook) => {
        setRejectingRB(rb);
        setRejectingFT(null);
        setRejectingTC(null);
        setRejectNote('');
    };

    const handleConfirmReject = async () => {
        const note = rejectNote.trim();
        if (!note) return;
        try {
            if (rejectingFT) {
                await rejectFT.mutateAsync({ id: rejectingFT.id, review_note: note });
            } else if (rejectingTC) {
                await rejectTC.mutateAsync({ id: rejectingTC.id, review_note: note });
            } else if (rejectingRB) {
                await rejectRB.mutateAsync({ id: rejectingRB.id, review_note: note });
            } else {
                return;
            }
            toast.success('Submission rejected');
            setRejectingFT(null);
            setRejectingTC(null);
            setRejectingRB(null);
            setRejectNote('');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to reject'));
        }
    };

    const handleDeleteTC = async (template: TestCaseTemplate) => {
        const confirmed = await confirm({
            title: 'Delete Test Case Template',
            description: `Are you sure you want to delete "${template.title}"? This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        });
        if (!confirmed) return;
        try {
            await deleteTC.mutateAsync(template.id);
            toast.success('Test case template deleted');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to delete template'));
        }
    };

    const handleDeleteRB = async (runbook: Runbook) => {
        const confirmed = await confirm({
            title: 'Delete Runbook',
            description: `Are you sure you want to delete "${runbook.name}"? This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        });
        if (!confirmed) return;
        try {
            await deleteRB.mutateAsync(runbook.id);
            toast.success('Runbook deleted');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to delete runbook'));
        }
    };

    const handleDeleteRLT = async (template: ReportLayoutTemplate) => {
        const confirmed = await confirm({
            title: 'Delete Report Layout Template',
            description: `Are you sure you want to delete "${template.name}"? This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        });
        if (!confirmed) return;
        try {
            await deleteRLT.mutateAsync(template.id);
            toast.success('Report layout template deleted');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to delete template'));
        }
    };

    const handleDeleteRT = async (theme: ReportTheme) => {
        const confirmed = await confirm({
            title: 'Delete Report Theme',
            description: `Are you sure you want to delete "${theme.name}"? This action cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        });
        if (!confirmed) return;
        try {
            await deleteRT.mutateAsync(theme.id);
            toast.success('Report theme deleted');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to delete theme'));
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 max-w-7xl mx-auto">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-linear-to-br from-purple-500/20 to-pink-500/20">
                                <BookOpen className="h-6 w-6 text-primary" />
                            </div>
                            Templates
                        </h1>
                        <p className="text-slate-400 mt-1">
                            Manage reusable templates for findings and test cases
                        </p>
                    </div>
                    {!canManage && (
                        <Badge variant="outline" className="bg-amber-500/10 text-amber-400 border-amber-500/20 gap-1.5">
                            <ShieldAlert className="h-3.5 w-3.5" />
                            View Only
                        </Badge>
                    )}
                </div>

                {/* Tabs */}
                <Tabs defaultValue={searchParams.get('tab') || 'findings'} className="space-y-4">
                    <TabsList className="bg-slate-800/50 border border-slate-700">
                        <TabsTrigger value="findings" className="data-[state=active]:bg-primary data-[state=active]:text-white gap-2">
                            <FileText className="h-4 w-4" />
                            Finding Templates
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">{findingTemplates.length}</Badge>
                        </TabsTrigger>
                        <TabsTrigger value="testcases" className="data-[state=active]:bg-primary data-[state=active]:text-white gap-2">
                            <ClipboardList className="h-4 w-4" />
                            Test Case Templates
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">{tcTemplates.length}</Badge>
                        </TabsTrigger>
                        <TabsTrigger value="runbooks" className="data-[state=active]:bg-primary data-[state=active]:text-white gap-2">
                            <GitBranch className="h-4 w-4" />
                            Runbooks
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">{runbooks.length}</Badge>
                        </TabsTrigger>
                        <TabsTrigger value="report-layouts" className="data-[state=active]:bg-primary data-[state=active]:text-white gap-2">
                            <LayoutTemplate className="h-4 w-4" />
                            Report Layouts
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">{reportLayoutTemplates.length}</Badge>
                        </TabsTrigger>
                        <TabsTrigger value="report-themes" className="data-[state=active]:bg-primary data-[state=active]:text-white gap-2">
                            <Palette className="h-4 w-4" />
                            Report Themes
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">{reportThemes.length}</Badge>
                        </TabsTrigger>
                        <TabsTrigger value="marking-profiles" className="data-[state=active]:bg-primary data-[state=active]:text-white gap-2">
                            <ShieldAlert className="h-4 w-4" />
                            Marking Profiles
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">{markingProfiles.length}</Badge>
                        </TabsTrigger>
                    </TabsList>

                    {/* ─── Finding Templates Tab ─── */}
                    <TabsContent value="findings">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <CardTitle className="text-white">Finding Templates</CardTitle>
                                        <CardDescription>Pre-defined finding descriptions to speed up report writing</CardDescription>
                                    </div>
                                    <div className="flex items-center gap-3 flex-wrap justify-end">
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                            <Input
                                                placeholder="Search title, category, description..."
                                                value={ftSearch}
                                                onChange={e => setFtSearch(e.target.value)}
                                                className="pl-9 w-72 bg-slate-800/50 border-slate-700"
                                            />
                                        </div>
                                        <label className="flex items-center gap-2 text-sm text-slate-300 select-none cursor-pointer">
                                            <Switch checked={ftMineOnly} onCheckedChange={setFtMineOnly} />
                                            Mine only
                                        </label>
                                        <Button
                                            variant="outline"
                                            className="border-slate-700 bg-slate-800/50 text-slate-300 hover:bg-slate-800 hover:text-white gap-2 relative"
                                            onClick={() => setFtFiltersOpen(o => !o)}
                                        >
                                            <SlidersHorizontal className="h-4 w-4" />
                                            Filters
                                            {ftActiveFilterCount > 0 && (
                                                <Badge variant="secondary" className="h-5 px-1.5 text-[10px] bg-purple-500/20 text-purple-400 border-purple-500/30">
                                                    {ftActiveFilterCount}
                                                </Badge>
                                            )}
                                        </Button>
                                        <Button
                                            className="bg-primary hover:bg-primary/90 text-white gap-2"
                                            onClick={() => router.push('/templates/findings/new/edit')}
                                        >
                                            <Plus className="h-4 w-4" /> New Template
                                        </Button>
                                    </div>
                                </div>
                                {ftFiltersOpen && (
                                    <div className="mt-4 pt-4 border-t border-slate-800 flex flex-wrap items-center gap-x-6 gap-y-3">
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Status</span>
                                            <div className="flex items-center gap-1">
                                                {(['ALL', 'DRAFT', 'SUBMITTED', 'PUBLISHED'] as const).map(s => {
                                                    const active = ftStatusFilter === s;
                                                    const count = ftStatusCounts[s];
                                                    const label = s === 'ALL' ? 'All' : TEMPLATE_STATUS_STYLES[s].label;
                                                    return (
                                                        <button
                                                            key={s}
                                                            type="button"
                                                            onClick={() => setFtStatusFilter(s)}
                                                            className={cn(
                                                                'h-7 px-2.5 rounded-md text-xs border transition-colors flex items-center gap-1.5',
                                                                active
                                                                    ? 'bg-primary/15 border-primary/40 text-primary'
                                                                    : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800',
                                                            )}
                                                        >
                                                            {label}
                                                            <span className={cn('text-[10px]', active ? 'text-primary/80' : 'text-slate-500')}>{count}</span>
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Category</span>
                                            <Select value={ftCategoryFilter} onValueChange={setFtCategoryFilter}>
                                                <SelectTrigger className="h-8 w-48 bg-slate-800/50 border-slate-700 text-sm">
                                                    <SelectValue placeholder="All categories" />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="all">All categories</SelectItem>
                                                    {ftCategoryOptions.map(c => (
                                                        <SelectItem key={c} value={c}>{c}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        {ftActiveFilterCount > 0 && (
                                            <Button variant="ghost" size="sm" className="h-7 text-xs text-slate-400 hover:text-white" onClick={clearFtFilters}>
                                                Clear filters
                                            </Button>
                                        )}
                                    </div>
                                )}
                            </CardHeader>
                            <CardContent>
                                {ftLoading ? (
                                    <div className="flex items-center justify-center py-16">
                                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                                    </div>
                                ) : filteredFT.length === 0 ? (() => {
                                    const hasFilters = !!ftSearch || ftMineOnly || ftActiveFilterCount > 0;
                                    return (
                                        <div className="text-center py-16 text-slate-500">
                                            <FileText className="h-12 w-12 mx-auto mb-3 opacity-20" />
                                            <p className="text-sm font-medium">
                                                {hasFilters ? 'No templates match your filters' : 'No finding templates yet'}
                                            </p>
                                            {!hasFilters && (
                                                <p className="text-xs text-slate-600 mt-1">Click &ldquo;New Template&rdquo; to create one</p>
                                            )}
                                        </div>
                                    );
                                })() : (
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                        <Table>
                                            <TableHeader>
                                                <TableRow className="border-slate-800 hover:bg-transparent">
                                                    {([
                                                        { key: 'title', label: 'Title', className: '' },
                                                        { key: 'status', label: 'Status', className: 'w-28' },
                                                        { key: 'category', label: 'Category', className: '' },
                                                        { key: 'updated_at', label: 'Updated', className: 'hidden lg:table-cell w-32' },
                                                    ] as const).map(col => {
                                                        const isActive = ftSortBy === col.key;
                                                        const Icon = isActive
                                                            ? (ftSortDir === 'asc' ? ArrowUp : ArrowDown)
                                                            : ChevronsUpDown;
                                                        return (
                                                            <TableHead key={col.key} className={cn('text-slate-400', col.className)}>
                                                                <button
                                                                    type="button"
                                                                    onClick={() => toggleFtSort(col.key)}
                                                                    className={cn(
                                                                        'inline-flex items-center gap-1 hover:text-white transition-colors',
                                                                        isActive && 'text-white',
                                                                    )}
                                                                >
                                                                    {col.label}
                                                                    <Icon className={cn('h-3.5 w-3.5', !isActive && 'opacity-40')} />
                                                                </button>
                                                            </TableHead>
                                                        );
                                                    })}
                                                    <TableHead className="text-slate-400 w-44 text-right">Actions</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {filteredFT.map(template => {
                                                    const isOwner = template.created_by === user?.id;
                                                    const isDraft = template.status === 'DRAFT';
                                                    const isSubmitted = template.status === 'SUBMITTED';
                                                    const isPublished = template.status === 'PUBLISHED';
                                                    const canEditRow = (isDraft && (isOwner || canManage)) || (isPublished && canManage);
                                                    const canDeleteRow = (isDraft && (isOwner || user?.role === UserRole.ADMIN)) || (isPublished && canManage);
                                                    return (
                                                        <TableRow key={template.id} className="border-slate-800 hover:bg-slate-800/50 cursor-pointer" onClick={() => setViewingFT(template)}>
                                                            <TableCell className="font-medium text-white">
                                                                <div className="flex items-center gap-2">
                                                                    <span>{template.title}</span>
                                                                    {isDraft && template.review_note && isOwner && (
                                                                        <AlertTriangle className="h-3.5 w-3.5 text-yellow-400" aria-label="Has reviewer feedback" />
                                                                    )}
                                                                </div>
                                                            </TableCell>
                                                            <TableCell><TemplateStatusBadge status={template.status} /></TableCell>
                                                            <TableCell>
                                                                {template.category ? (() => {
                                                                    const c = findingCategoryColors[template.category] || '#a855f7';
                                                                    return (
                                                                        <Badge variant="outline" style={{ backgroundColor: `${c}15`, color: c, borderColor: `${c}33` }}>
                                                                            {template.category}
                                                                        </Badge>
                                                                    );
                                                                })() : (
                                                                    <span className="text-slate-600">—</span>
                                                                )}
                                                            </TableCell>
                                                            <TableCell className="hidden lg:table-cell text-slate-400 text-xs whitespace-nowrap">
                                                                {template.updated_at
                                                                    ? new Date(template.updated_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
                                                                    : '—'}
                                                            </TableCell>
                                                            <TableCell className="text-right">
                                                                <div className="flex items-center justify-end gap-1">
                                                                    {isDraft && isOwner && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-primary" title="Submit for review" onClick={(e) => { e.stopPropagation(); handleSubmitFT(template); }}>
                                                                            <Send className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {isSubmitted && isOwner && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white" title="Withdraw submission" onClick={(e) => { e.stopPropagation(); handleWithdrawFT(template); }}>
                                                                            <Undo2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && (isSubmitted || (isDraft && isOwner)) && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-green-400" title="Publish" onClick={(e) => { e.stopPropagation(); handleApproveFT(template); }}>
                                                                            <Check className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && isSubmitted && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-400" title="Reject" onClick={(e) => { e.stopPropagation(); openRejectFT(template); }}>
                                                                            <X className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && isPublished && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-yellow-400" title="Unpublish" onClick={(e) => { e.stopPropagation(); handleUnpublishFT(template); }}>
                                                                            <Undo2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canEditRow && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white" title="Edit" onClick={(e) => { e.stopPropagation(); router.push(`/templates/findings/${template.id}/edit`); }}>
                                                                            <Pencil className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canDeleteRow && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-400" title="Delete" onClick={(e) => { e.stopPropagation(); handleDeleteFT(template); }}>
                                                                            <Trash2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                </div>
                                                            </TableCell>
                                                        </TableRow>
                                                    );
                                                })}
                                            </TableBody>
                                        </Table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ─── Test Case Templates Tab ─── */}
                    <TabsContent value="testcases">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <CardTitle className="text-white">Test Case Templates</CardTitle>
                                        <CardDescription>Reusable test case templates for common security checks</CardDescription>
                                    </div>
                                    <div className="flex items-center gap-3 flex-wrap justify-end">
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                            <Input
                                                placeholder="Search title, category, description..."
                                                value={tcSearch}
                                                onChange={e => setTcSearch(e.target.value)}
                                                className="pl-9 w-72 bg-slate-800/50 border-slate-700"
                                            />
                                        </div>
                                        <label className="flex items-center gap-2 text-sm text-slate-300 select-none cursor-pointer">
                                            <Switch checked={tcMineOnly} onCheckedChange={setTcMineOnly} />
                                            Mine only
                                        </label>
                                        <Button
                                            variant="outline"
                                            className="border-slate-700 bg-slate-800/50 text-slate-300 hover:bg-slate-800 hover:text-white gap-2 relative"
                                            onClick={() => setTcFiltersOpen(o => !o)}
                                        >
                                            <SlidersHorizontal className="h-4 w-4" />
                                            Filters
                                            {tcActiveFilterCount > 0 && (
                                                <Badge variant="secondary" className="h-5 px-1.5 text-[10px] bg-purple-500/20 text-purple-400 border-purple-500/30">
                                                    {tcActiveFilterCount}
                                                </Badge>
                                            )}
                                        </Button>
                                        <Button
                                            className="bg-primary hover:bg-primary/90 text-white gap-2"
                                            onClick={() => router.push('/templates/testcases/new/edit')}
                                        >
                                            <Plus className="h-4 w-4" /> New Template
                                        </Button>
                                    </div>
                                </div>
                                {tcFiltersOpen && (
                                    <div className="mt-4 pt-4 border-t border-slate-800 flex flex-wrap items-center gap-x-6 gap-y-3">
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Status</span>
                                            <div className="flex items-center gap-1">
                                                {(['ALL', 'DRAFT', 'SUBMITTED', 'PUBLISHED'] as const).map(s => {
                                                    const active = tcStatusFilter === s;
                                                    const count = tcStatusCounts[s];
                                                    const label = s === 'ALL' ? 'All' : TEMPLATE_STATUS_STYLES[s].label;
                                                    return (
                                                        <button
                                                            key={s}
                                                            type="button"
                                                            onClick={() => setTcStatusFilter(s)}
                                                            className={cn(
                                                                'h-7 px-2.5 rounded-md text-xs border transition-colors flex items-center gap-1.5',
                                                                active
                                                                    ? 'bg-primary/15 border-primary/40 text-primary'
                                                                    : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800',
                                                            )}
                                                        >
                                                            {label}
                                                            <span className={cn('text-[10px]', active ? 'text-primary/80' : 'text-slate-500')}>{count}</span>
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Category</span>
                                            <Select value={tcCategoryFilter} onValueChange={setTcCategoryFilter}>
                                                <SelectTrigger className="h-8 w-48 bg-slate-800/50 border-slate-700 text-sm">
                                                    <SelectValue placeholder="All categories" />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="all">All categories</SelectItem>
                                                    {tcCategoryOptions.map(c => (
                                                        <SelectItem key={c} value={c}>{c}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        {tcActiveFilterCount > 0 && (
                                            <Button variant="ghost" size="sm" className="h-7 text-xs text-slate-400 hover:text-white" onClick={clearTcFilters}>
                                                Clear filters
                                            </Button>
                                        )}
                                    </div>
                                )}
                            </CardHeader>
                            <CardContent>
                                {tcLoading ? (
                                    <div className="flex items-center justify-center py-16">
                                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                                    </div>
                                ) : filteredTC.length === 0 ? (() => {
                                    const hasFilters = !!tcSearch || tcMineOnly || tcActiveFilterCount > 0;
                                    return (
                                        <div className="text-center py-16 text-slate-500">
                                            <ClipboardList className="h-12 w-12 mx-auto mb-3 opacity-20" />
                                            <p className="text-sm font-medium">
                                                {hasFilters ? 'No templates match your filters' : 'No test case templates yet'}
                                            </p>
                                            {!hasFilters && (
                                                <p className="text-xs text-slate-600 mt-1">Click &ldquo;New Template&rdquo; to create one</p>
                                            )}
                                        </div>
                                    );
                                })() : (
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                        <Table>
                                            <TableHeader>
                                                <TableRow className="border-slate-800 hover:bg-transparent">
                                                    {([
                                                        { key: 'title', label: 'Title', className: '' },
                                                        { key: 'status', label: 'Status', className: 'w-28' },
                                                        { key: 'category', label: 'Category', className: '' },
                                                        { key: 'updated_at', label: 'Updated', className: 'hidden lg:table-cell w-32' },
                                                    ] as const).map(col => {
                                                        const isActive = tcSortBy === col.key;
                                                        const Icon = isActive
                                                            ? (tcSortDir === 'asc' ? ArrowUp : ArrowDown)
                                                            : ChevronsUpDown;
                                                        return (
                                                            <TableHead key={col.key} className={cn('text-slate-400', col.className)}>
                                                                <button
                                                                    type="button"
                                                                    onClick={() => toggleTcSort(col.key)}
                                                                    className={cn(
                                                                        'inline-flex items-center gap-1 hover:text-white transition-colors',
                                                                        isActive && 'text-white',
                                                                    )}
                                                                >
                                                                    {col.label}
                                                                    <Icon className={cn('h-3.5 w-3.5', !isActive && 'opacity-40')} />
                                                                </button>
                                                            </TableHead>
                                                        );
                                                    })}
                                                    <TableHead className="text-slate-400 w-44 text-right">Actions</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {filteredTC.map(template => {
                                                    const isOwner = template.created_by === user?.id;
                                                    const isDraft = template.status === 'DRAFT';
                                                    const isSubmitted = template.status === 'SUBMITTED';
                                                    const isPublished = template.status === 'PUBLISHED';
                                                    const canEditRow = (isDraft && (isOwner || canManage)) || (isPublished && canManage);
                                                    const canDeleteRow = (isDraft && (isOwner || user?.role === UserRole.ADMIN)) || (isPublished && canManage);
                                                    return (
                                                        <TableRow key={template.id} className="border-slate-800 hover:bg-slate-800/50 cursor-pointer" onClick={() => setViewingTC(template)}>
                                                            <TableCell className="font-medium text-white">
                                                                <div className="flex items-center gap-2">
                                                                    <span>{template.title}</span>
                                                                    {isDraft && template.review_note && isOwner && (
                                                                        <AlertTriangle className="h-3.5 w-3.5 text-yellow-400" aria-label="Has reviewer feedback" />
                                                                    )}
                                                                </div>
                                                            </TableCell>
                                                            <TableCell><TemplateStatusBadge status={template.status} /></TableCell>
                                                            <TableCell>
                                                                {(() => {
                                                                    const c = testcaseCategoryColors[template.category] || '#06b6d4';
                                                                    return (
                                                                        <Badge variant="outline" style={{ backgroundColor: `${c}15`, color: c, borderColor: `${c}33` }}>
                                                                            {template.category}
                                                                        </Badge>
                                                                    );
                                                                })()}
                                                            </TableCell>
                                                            <TableCell className="hidden lg:table-cell text-slate-400 text-xs whitespace-nowrap">
                                                                {template.updated_at
                                                                    ? new Date(template.updated_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
                                                                    : '—'}
                                                            </TableCell>
                                                            <TableCell className="text-right">
                                                                <div className="flex items-center justify-end gap-1">
                                                                    {isDraft && isOwner && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-primary" title="Submit for review" onClick={(e) => { e.stopPropagation(); handleSubmitTC(template); }}>
                                                                            <Send className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {isSubmitted && isOwner && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white" title="Withdraw submission" onClick={(e) => { e.stopPropagation(); handleWithdrawTC(template); }}>
                                                                            <Undo2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && (isSubmitted || (isDraft && isOwner)) && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-green-400" title="Publish" onClick={(e) => { e.stopPropagation(); handleApproveTC(template); }}>
                                                                            <Check className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && isSubmitted && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-400" title="Reject" onClick={(e) => { e.stopPropagation(); openRejectTC(template); }}>
                                                                            <X className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && isPublished && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-yellow-400" title="Unpublish" onClick={(e) => { e.stopPropagation(); handleUnpublishTC(template); }}>
                                                                            <Undo2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canEditRow && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white" title="Edit" onClick={(e) => { e.stopPropagation(); router.push(`/templates/testcases/${template.id}/edit`); }}>
                                                                            <Pencil className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canDeleteRow && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-400" title="Delete" onClick={(e) => { e.stopPropagation(); handleDeleteTC(template); }}>
                                                                            <Trash2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                </div>
                                                            </TableCell>
                                                        </TableRow>
                                                    );
                                                })}
                                            </TableBody>
                                        </Table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ─── Runbooks Tab ─── */}
                    <TabsContent value="runbooks">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <CardTitle className="text-white">Runbooks</CardTitle>
                                        <CardDescription>Hierarchical test case template trees for common workflows</CardDescription>
                                    </div>
                                    <div className="flex items-center gap-3 flex-wrap justify-end">
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                            <Input
                                                placeholder="Search name, description, type..."
                                                value={rbSearch}
                                                onChange={e => setRbSearch(e.target.value)}
                                                className="pl-9 w-72 bg-slate-800/50 border-slate-700"
                                            />
                                        </div>
                                        <label className="flex items-center gap-2 text-sm text-slate-300 select-none cursor-pointer">
                                            <Switch checked={rbMineOnly} onCheckedChange={setRbMineOnly} />
                                            Mine only
                                        </label>
                                        <Button
                                            variant="outline"
                                            className="border-slate-700 bg-slate-800/50 text-slate-300 hover:bg-slate-800 hover:text-white gap-2 relative"
                                            onClick={() => setRbFiltersOpen(o => !o)}
                                        >
                                            <SlidersHorizontal className="h-4 w-4" />
                                            Filters
                                            {rbActiveFilterCount > 0 && (
                                                <Badge variant="secondary" className="h-5 px-1.5 text-[10px] bg-purple-500/20 text-purple-400 border-purple-500/30">
                                                    {rbActiveFilterCount}
                                                </Badge>
                                            )}
                                        </Button>
                                        <Button
                                            className="bg-primary hover:bg-primary/90 text-white gap-2"
                                            onClick={() => router.push('/templates/runbooks/new/edit')}
                                        >
                                            <Plus className="h-4 w-4" /> New Runbook
                                        </Button>
                                    </div>
                                </div>
                                {rbFiltersOpen && (
                                    <div className="mt-4 pt-4 border-t border-slate-800 flex flex-wrap items-center gap-x-6 gap-y-3">
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Status</span>
                                            <div className="flex items-center gap-1">
                                                {(['ALL', 'DRAFT', 'SUBMITTED', 'PUBLISHED'] as const).map(s => {
                                                    const active = rbStatusFilter === s;
                                                    const count = rbStatusCounts[s];
                                                    const label = s === 'ALL' ? 'All' : TEMPLATE_STATUS_STYLES[s].label;
                                                    return (
                                                        <button
                                                            key={s}
                                                            type="button"
                                                            onClick={() => setRbStatusFilter(s)}
                                                            className={cn(
                                                                'h-7 px-2.5 rounded-md text-xs border transition-colors flex items-center gap-1.5',
                                                                active
                                                                    ? 'bg-primary/15 border-primary/40 text-primary'
                                                                    : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800',
                                                            )}
                                                        >
                                                            {label}
                                                            <span className={cn('text-[10px]', active ? 'text-primary/80' : 'text-slate-500')}>{count}</span>
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                        {runbookTypeConfigs.length > 0 && (
                                            <div className="flex items-center gap-2">
                                                <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Type</span>
                                                <Select value={rbTypeFilter || 'all'} onValueChange={val => setRbTypeFilter(val === 'all' ? '' : val)}>
                                                    <SelectTrigger className="h-8 w-48 bg-slate-800/50 border-slate-700 text-sm">
                                                        <SelectValue placeholder="All types" />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        <SelectItem value="all">All types</SelectItem>
                                                        {runbookTypeConfigs.map(t => (
                                                            <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                        )}
                                        {rbActiveFilterCount > 0 && (
                                            <Button variant="ghost" size="sm" className="h-7 text-xs text-slate-400 hover:text-white" onClick={clearRbFilters}>
                                                Clear filters
                                            </Button>
                                        )}
                                    </div>
                                )}
                            </CardHeader>
                            <CardContent>
                                {rbLoading ? (
                                    <div className="flex items-center justify-center py-16">
                                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                                    </div>
                                ) : filteredRB.length === 0 ? (() => {
                                    const hasFilters = !!rbSearch || rbMineOnly || rbActiveFilterCount > 0;
                                    return (
                                        <div className="text-center py-16 text-slate-500">
                                            <GitBranch className="h-12 w-12 mx-auto mb-3 opacity-20" />
                                            <p className="text-sm font-medium">
                                                {hasFilters ? 'No runbooks match your filters' : 'No runbooks yet'}
                                            </p>
                                            {!hasFilters && (
                                                <p className="text-xs text-slate-600 mt-1">Click &ldquo;New Runbook&rdquo; to create one</p>
                                            )}
                                        </div>
                                    );
                                })() : (
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                        <Table>
                                            <TableHeader>
                                                <TableRow className="border-slate-800 hover:bg-transparent">
                                                    {([
                                                        { key: 'name', label: 'Name', className: '' },
                                                        { key: 'status', label: 'Status', className: 'w-28' },
                                                        { key: 'runbook_type', label: 'Type', className: '' },
                                                        { key: 'updated_at', label: 'Updated', className: 'hidden lg:table-cell w-32' },
                                                    ] as const).map(col => {
                                                        const isActive = rbSortBy === col.key;
                                                        const Icon = isActive
                                                            ? (rbSortDir === 'asc' ? ArrowUp : ArrowDown)
                                                            : ChevronsUpDown;
                                                        return (
                                                            <TableHead key={col.key} className={cn('text-slate-400', col.className)}>
                                                                <button
                                                                    type="button"
                                                                    onClick={() => toggleRbSort(col.key)}
                                                                    className={cn(
                                                                        'inline-flex items-center gap-1 hover:text-white transition-colors',
                                                                        isActive && 'text-white',
                                                                    )}
                                                                >
                                                                    {col.label}
                                                                    <Icon className={cn('h-3.5 w-3.5', !isActive && 'opacity-40')} />
                                                                </button>
                                                            </TableHead>
                                                        );
                                                    })}
                                                    <TableHead className="text-slate-400 w-20 text-center">Items</TableHead>
                                                    <TableHead className="text-slate-400 w-44 text-right">Actions</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {filteredRB.map(rb => {
                                                    const isOwner = rb.created_by === user?.id;
                                                    const isDraft = rb.status === 'DRAFT';
                                                    const isSubmitted = rb.status === 'SUBMITTED';
                                                    const isPublished = rb.status === 'PUBLISHED';
                                                    const canEditRow = (isDraft && (isOwner || canManage)) || (isPublished && canManage);
                                                    const canDeleteRow = (isDraft && (isOwner || user?.role === UserRole.ADMIN)) || (isPublished && canManage);
                                                    return (
                                                        <TableRow key={rb.id} className="border-slate-800 hover:bg-slate-800/50 cursor-pointer" onClick={() => setViewingRB(rb)}>
                                                            <TableCell className="font-medium text-white">
                                                                <div className="flex items-center gap-2">
                                                                    <GitBranch className="h-4 w-4 text-primary shrink-0" />
                                                                    <span>{rb.name}</span>
                                                                    {isDraft && rb.review_note && isOwner && (
                                                                        <AlertTriangle className="h-3.5 w-3.5 text-yellow-400" aria-label="Has reviewer feedback" />
                                                                    )}
                                                                </div>
                                                            </TableCell>
                                                            <TableCell><TemplateStatusBadge status={rb.status} /></TableCell>
                                                            <TableCell>
                                                                {rb.runbook_type ? (() => {
                                                                    const c = runbookTypeColors[rb.runbook_type] || '#a855f7';
                                                                    return (
                                                                        <Badge variant="outline" style={{ backgroundColor: `${c}15`, color: c, borderColor: `${c}33` }}>
                                                                            {rb.runbook_type}
                                                                        </Badge>
                                                                    );
                                                                })() : (
                                                                    <span className="text-slate-600">—</span>
                                                                )}
                                                            </TableCell>
                                                            <TableCell className="hidden lg:table-cell text-slate-400 text-xs whitespace-nowrap">
                                                                {rb.updated_at
                                                                    ? new Date(rb.updated_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
                                                                    : '—'}
                                                            </TableCell>
                                                            <TableCell className="text-center">
                                                                <Badge variant="secondary" className="text-xs">{rb.items.length}</Badge>
                                                            </TableCell>
                                                            <TableCell className="text-right">
                                                                <div className="flex items-center justify-end gap-1">
                                                                    {isDraft && isOwner && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-primary" title="Submit for review" onClick={(e) => { e.stopPropagation(); handleSubmitRB(rb); }}>
                                                                            <Send className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {isSubmitted && isOwner && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white" title="Withdraw submission" onClick={(e) => { e.stopPropagation(); handleWithdrawRB(rb); }}>
                                                                            <Undo2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && (isSubmitted || (isDraft && isOwner)) && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-green-400" title="Publish" onClick={(e) => { e.stopPropagation(); handleApproveRB(rb); }}>
                                                                            <Check className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && isSubmitted && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-400" title="Reject" onClick={(e) => { e.stopPropagation(); openRejectRB(rb); }}>
                                                                            <X className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canManage && isPublished && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-yellow-400" title="Unpublish" onClick={(e) => { e.stopPropagation(); handleUnpublishRB(rb); }}>
                                                                            <Undo2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canEditRow && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white" title="Edit" onClick={(e) => { e.stopPropagation(); router.push(`/templates/runbooks/${rb.id}/edit`); }}>
                                                                            <Pencil className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                    {canDeleteRow && (
                                                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-400" title="Delete" onClick={(e) => { e.stopPropagation(); handleDeleteRB(rb); }}>
                                                                            <Trash2 className="h-4 w-4" />
                                                                        </Button>
                                                                    )}
                                                                </div>
                                                            </TableCell>
                                                        </TableRow>
                                                    );
                                                })}
                                            </TableBody>
                                        </Table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ─── Report Layout Templates Tab ─── */}
                    <TabsContent value="report-layouts">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <CardTitle className="text-white">Report Layout Templates</CardTitle>
                                        <CardDescription>Reusable report structures with pre-defined sections</CardDescription>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                            <Input
                                                placeholder="Search templates..."
                                                value={rltSearch}
                                                onChange={e => setRltSearch(e.target.value)}
                                                className="pl-9 w-64 bg-slate-800/50 border-slate-700"
                                            />
                                        </div>
                                        {canManage && (
                                            <Button
                                                className="bg-primary hover:bg-primary/90 text-white gap-2"
                                                onClick={() => router.push('/templates/report-layouts/new/edit')}
                                            >
                                                <Plus className="h-4 w-4" /> New Template
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                {rltLoading ? (
                                    <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>
                                ) : filteredRLT.length === 0 ? (
                                    <div className="text-center py-12">
                                        <LayoutTemplate className="h-10 w-10 text-slate-700 mx-auto mb-3" />
                                        <p className="text-slate-500">No report layout templates found</p>
                                    </div>
                                ) : (
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                        <Table>
                                            <TableHeader>
                                                <TableRow className="border-slate-800 bg-slate-800/30">
                                                    <TableHead className="text-slate-400">Name</TableHead>
                                                    <TableHead className="text-slate-400">Description</TableHead>
                                                    <TableHead className="text-slate-400 text-center">Sections</TableHead>
                                                    <TableHead className="text-right text-slate-400">Actions</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {filteredRLT.map(template => (
                                                    <TableRow
                                                        key={template.id}
                                                        className="border-slate-800 hover:bg-slate-800/50 cursor-pointer"
                                                        onClick={() => setViewingRLT(template)}
                                                    >
                                                        <TableCell className="font-medium text-white">{template.name}</TableCell>
                                                        <TableCell className="text-slate-400 max-w-xs truncate">{template.description || '—'}</TableCell>
                                                        <TableCell className="text-center">
                                                            <Badge variant="secondary" className="text-xs">{template.sections.length}</Badge>
                                                        </TableCell>
                                                        <TableCell className="text-right">
                                                            <div className="flex justify-end gap-2">
                                                                {canManage && (
                                                                    <>
                                                                        <Button
                                                                            variant="ghost"
                                                                            size="icon"
                                                                            className="h-8 w-8 text-slate-400 hover:text-white"
                                                                            onClick={e => { e.stopPropagation(); router.push(`/templates/report-layouts/${template.id}/edit`); }}
                                                                        >
                                                                            <Pencil className="h-4 w-4" />
                                                                        </Button>
                                                                        <Button
                                                                            variant="ghost"
                                                                            size="icon"
                                                                            className="h-8 w-8 text-slate-400 hover:text-red-500"
                                                                            onClick={e => { e.stopPropagation(); handleDeleteRLT(template); }}
                                                                        >
                                                                            <Trash2 className="h-4 w-4" />
                                                                        </Button>
                                                                    </>
                                                                )}
                                                            </div>
                                                        </TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ─── Report Themes Tab ─── */}
                    <TabsContent value="report-themes">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <CardTitle className="text-white">Report Themes</CardTitle>
                                        <CardDescription>Customize the visual appearance (colors, fonts, logo) of generated PDF reports</CardDescription>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                            <Input
                                                placeholder="Search themes..."
                                                value={rtSearch}
                                                onChange={e => setRtSearch(e.target.value)}
                                                className="pl-9 w-64 bg-slate-800/50 border-slate-700"
                                            />
                                        </div>
                                        {canManage && (
                                            <Button
                                                className="bg-primary hover:bg-primary/90 text-white gap-2"
                                                onClick={() => router.push('/templates/report-themes/new/edit')}
                                            >
                                                <Plus className="h-4 w-4" /> New Theme
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                {rtLoading ? (
                                    <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>
                                ) : filteredRT.length === 0 ? (
                                    <div className="text-center py-12">
                                        <Palette className="h-10 w-10 text-slate-700 mx-auto mb-3" />
                                        <p className="text-slate-500">No report themes found</p>
                                    </div>
                                ) : (
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                        <Table>
                                            <TableHeader>
                                                <TableRow className="border-slate-800 bg-slate-800/30">
                                                    <TableHead className="text-slate-400">Name</TableHead>
                                                    <TableHead className="text-slate-400">Colors</TableHead>
                                                    <TableHead className="text-slate-400">Font</TableHead>
                                                    <TableHead className="text-slate-400 text-center">Default</TableHead>
                                                    <TableHead className="text-right text-slate-400">Actions</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {filteredRT.map(theme => (
                                                    <TableRow
                                                        key={theme.id}
                                                        className="border-slate-800 hover:bg-slate-800/50 cursor-pointer"
                                                        onClick={() => router.push(`/templates/report-themes/${theme.id}/edit`)}
                                                    >
                                                        <TableCell>
                                                            <div>
                                                                <p className="font-medium text-white">{theme.name}</p>
                                                                {theme.description && <p className="text-xs text-slate-400 mt-0.5 truncate max-w-xs">{theme.description}</p>}
                                                            </div>
                                                        </TableCell>
                                                        <TableCell>
                                                            <div className="flex items-center gap-1.5">
                                                                <span className="w-4 h-4 rounded-full border border-slate-700" style={{ backgroundColor: theme.primary_color }} title="Primary" />
                                                                <span className="w-4 h-4 rounded-full border border-slate-700" style={{ backgroundColor: theme.secondary_color }} title="Secondary" />
                                                                <span className="w-4 h-4 rounded-full border border-slate-700" style={{ backgroundColor: theme.table_header_bg }} title="Table" />
                                                            </div>
                                                        </TableCell>
                                                        <TableCell className="text-slate-400 text-sm">{theme.font_family}</TableCell>
                                                        <TableCell className="text-center">
                                                            {theme.is_default && <Badge variant="outline" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-xs">Default</Badge>}
                                                        </TableCell>
                                                        <TableCell className="text-right">
                                                            <div className="flex justify-end gap-2">
                                                                {canManage && (
                                                                    <>
                                                                        <Button
                                                                            variant="ghost"
                                                                            size="icon"
                                                                            className="h-8 w-8 text-slate-400 hover:text-white"
                                                                            onClick={e => { e.stopPropagation(); router.push(`/templates/report-themes/${theme.id}/edit`); }}
                                                                        >
                                                                            <Pencil className="h-4 w-4" />
                                                                        </Button>
                                                                        <Button
                                                                            variant="ghost"
                                                                            size="icon"
                                                                            className="h-8 w-8 text-slate-400 hover:text-red-500"
                                                                            onClick={e => { e.stopPropagation(); handleDeleteRT(theme); }}
                                                                        >
                                                                            <Trash2 className="h-4 w-4" />
                                                                        </Button>
                                                                    </>
                                                                )}
                                                            </div>
                                                        </TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ─── Marking Profiles Tab ─── */}
                    <TabsContent value="marking-profiles">
                        <MarkingProfilesManager />
                    </TabsContent>
                </Tabs>

                {/* ─── View Finding Template Dialog ─── */}
                <Dialog open={!!viewingFT} onOpenChange={open => !open && setViewingFT(null)}>
                    <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle className="text-white text-lg flex items-center gap-2">
                                <span>{viewingFT?.title}</span>
                                {viewingFT && <TemplateStatusBadge status={viewingFT.status} />}
                            </DialogTitle>
                            {viewingFT?.category && (() => {
                                const c = findingCategoryColors[viewingFT.category] || '#a855f7';
                                return (
                                    <Badge variant="outline" className="w-fit" style={{ backgroundColor: `${c}15`, color: c, borderColor: `${c}33` }}>
                                        {viewingFT.category}
                                    </Badge>
                                );
                            })()}
                        </DialogHeader>
                        {viewingFT && (
                            <div className="space-y-5">
                                {viewingFT.status === 'DRAFT' && viewingFT.review_note && viewingFT.created_by === user?.id && (
                                    <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                                        <div className="flex items-center gap-2 mb-2">
                                            <AlertTriangle className="h-4 w-4 text-yellow-400" />
                                            <span className="text-xs uppercase tracking-wide text-yellow-400 font-medium">Reviewer Feedback</span>
                                        </div>
                                        <p className="text-sm text-slate-200 whitespace-pre-wrap">{viewingFT.review_note}</p>
                                    </div>
                                )}
                                <div>
                                    <Label className="text-slate-400 text-xs uppercase tracking-wide">Description</Label>
                                    <div className="mt-1 rounded-lg bg-slate-800/30 p-4 border border-slate-800">
                                        <MarkdownPreview value={viewingFT.description} />
                                    </div>
                                </div>
                                {viewingFT.impact && (
                                    <div>
                                        <Label className="text-slate-400 text-xs uppercase tracking-wide">Impact</Label>
                                        <div className="mt-1 rounded-lg bg-slate-800/30 p-4 border border-slate-800">
                                            <MarkdownPreview value={viewingFT.impact} />
                                        </div>
                                    </div>
                                )}
                                {viewingFT.mitigations && (
                                    <div>
                                        <Label className="text-slate-400 text-xs uppercase tracking-wide">Mitigations</Label>
                                        <div className="mt-1 rounded-lg bg-slate-800/30 p-4 border border-slate-800">
                                            <MarkdownPreview value={viewingFT.mitigations} />
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                        <DialogFooter>
                            <Button variant="ghost" onClick={() => setViewingFT(null)}>Close</Button>
                            {viewingFT && (() => {
                                const isOwner = viewingFT.created_by === user?.id;
                                const canEditDialog =
                                    (viewingFT.status === 'DRAFT' && (isOwner || canManage)) ||
                                    (viewingFT.status === 'PUBLISHED' && canManage);
                                if (!canEditDialog) return null;
                                return (
                                    <Button
                                        className="bg-primary hover:bg-primary/90 text-white"
                                        onClick={() => { setViewingFT(null); router.push(`/templates/findings/${viewingFT.id}/edit`); }}
                                    >
                                        <Pencil className="h-4 w-4 mr-2" /> Edit
                                    </Button>
                                );
                            })()}
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                {/* ─── Reject Submission Dialog (shared by FT/TC/RB) ─── */}
                {(() => {
                    const rejecting = rejectingFT || rejectingTC || rejectingRB;
                    const rejectName = rejectingFT?.title || rejectingTC?.title || rejectingRB?.name;
                    const rejectKind = rejectingRB ? 'runbook' : 'template';
                    const isPending = rejectFT.isPending || rejectTC.isPending || rejectRB.isPending;
                    const closeReject = () => {
                        setRejectingFT(null);
                        setRejectingTC(null);
                        setRejectingRB(null);
                        setRejectNote('');
                    };
                    return (
                        <Dialog open={!!rejecting} onOpenChange={open => { if (!open) closeReject(); }}>
                            <DialogContent className="max-w-lg">
                                <DialogHeader>
                                    <DialogTitle className="text-white">Reject Submission</DialogTitle>
                                </DialogHeader>
                                {rejecting && (
                                    <div className="space-y-3">
                                        <p className="text-sm text-slate-400">
                                            Reject {rejectKind} &ldquo;<span className="text-white">{rejectName}</span>&rdquo; back to draft. The author will see your feedback and can revise and resubmit.
                                        </p>
                                        <div>
                                            <Label className="text-slate-300 text-xs uppercase tracking-wide">Feedback</Label>
                                            <Textarea
                                                value={rejectNote}
                                                onChange={e => setRejectNote(e.target.value)}
                                                placeholder="What needs to change before this can be published?"
                                                rows={5}
                                                className="mt-1 bg-slate-800/50 border-slate-700"
                                            />
                                        </div>
                                    </div>
                                )}
                                <DialogFooter>
                                    <Button variant="ghost" onClick={closeReject}>Cancel</Button>
                                    <Button
                                        className="bg-red-600 hover:bg-red-700 text-white"
                                        disabled={!rejectNote.trim() || isPending}
                                        onClick={handleConfirmReject}
                                    >
                                        <X className="h-4 w-4 mr-2" /> Reject
                                    </Button>
                                </DialogFooter>
                            </DialogContent>
                        </Dialog>
                    );
                })()}

                {/* ─── View Test Case Template Dialog ─── */}
                <Dialog open={!!viewingTC} onOpenChange={open => !open && setViewingTC(null)}>
                    <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle className="text-white text-lg flex items-center gap-2">
                                <span>{viewingTC?.title}</span>
                                {viewingTC && <TemplateStatusBadge status={viewingTC.status} />}
                            </DialogTitle>
                            {viewingTC?.category && (() => {
                                const c = testcaseCategoryColors[viewingTC.category] || '#06b6d4';
                                return (
                                    <Badge variant="outline" className="w-fit" style={{ backgroundColor: `${c}15`, color: c, borderColor: `${c}33` }}>
                                        {viewingTC.category}
                                    </Badge>
                                );
                            })()}
                        </DialogHeader>
                        {viewingTC && (
                            <div className="space-y-5">
                                {viewingTC.status === 'DRAFT' && viewingTC.review_note && viewingTC.created_by === user?.id && (
                                    <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                                        <div className="flex items-center gap-2 mb-2">
                                            <AlertTriangle className="h-4 w-4 text-yellow-400" />
                                            <span className="text-xs uppercase tracking-wide text-yellow-400 font-medium">Reviewer Feedback</span>
                                        </div>
                                        <p className="text-sm text-slate-200 whitespace-pre-wrap">{viewingTC.review_note}</p>
                                    </div>
                                )}
                                <div>
                                    <Label className="text-slate-400 text-xs uppercase tracking-wide">Description</Label>
                                    <div className="mt-1 rounded-lg bg-slate-800/30 p-4 border border-slate-800">
                                        <MarkdownPreview value={viewingTC.description} />
                                    </div>
                                </div>
                                {viewingTC.steps && (
                                    <div>
                                        <Label className="text-slate-400 text-xs uppercase tracking-wide">Steps</Label>
                                        <div className="mt-1 rounded-lg bg-slate-800/30 p-4 border border-slate-800">
                                            <MarkdownPreview value={viewingTC.steps} />
                                        </div>
                                    </div>
                                )}
                                {viewingTC.expected_result && (
                                    <div>
                                        <Label className="text-slate-400 text-xs uppercase tracking-wide">Expected Result</Label>
                                        <div className="mt-1 rounded-lg bg-slate-800/30 p-4 border border-slate-800">
                                            <MarkdownPreview value={viewingTC.expected_result} />
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                        <DialogFooter>
                            <Button variant="ghost" onClick={() => setViewingTC(null)}>Close</Button>
                            {viewingTC && (() => {
                                const isOwner = viewingTC.created_by === user?.id;
                                const canEditDialog =
                                    (viewingTC.status === 'DRAFT' && (isOwner || canManage)) ||
                                    (viewingTC.status === 'PUBLISHED' && canManage);
                                if (!canEditDialog) return null;
                                return (
                                    <Button
                                        className="bg-primary hover:bg-primary/90 text-white"
                                        onClick={() => { setViewingTC(null); router.push(`/templates/testcases/${viewingTC.id}/edit`); }}
                                    >
                                        <Pencil className="h-4 w-4 mr-2" /> Edit
                                    </Button>
                                );
                            })()}
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                {/* ─── View Runbook Dialog ─── */}
                <Dialog open={!!viewingRB} onOpenChange={open => !open && setViewingRB(null)}>
                    <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle className="text-white text-lg flex items-center gap-2">
                                <GitBranch className="h-5 w-5 text-primary" />
                                <span>{viewingRB?.name}</span>
                                {viewingRB && <TemplateStatusBadge status={viewingRB.status} />}
                            </DialogTitle>
                        </DialogHeader>
                        {viewingRB && (
                            <div className="space-y-5">
                                {viewingRB.status === 'DRAFT' && viewingRB.review_note && viewingRB.created_by === user?.id && (
                                    <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
                                        <div className="flex items-center gap-2 mb-2">
                                            <AlertTriangle className="h-4 w-4 text-yellow-400" />
                                            <span className="text-xs uppercase tracking-wide text-yellow-400 font-medium">Reviewer Feedback</span>
                                        </div>
                                        <p className="text-sm text-slate-200 whitespace-pre-wrap">{viewingRB.review_note}</p>
                                    </div>
                                )}
                                {viewingRB.description && (
                                    <div>
                                        <Label className="text-slate-400 text-xs uppercase tracking-wide">Description</Label>
                                        <p className="mt-1 text-sm text-slate-300">{viewingRB.description}</p>
                                    </div>
                                )}
                                <div>
                                    <Label className="text-slate-400 text-xs uppercase tracking-wide">Template Tree ({viewingRB.items.length} items)</Label>
                                    <div className="mt-2 rounded-lg bg-slate-800/30 p-3 border border-slate-800">
                                        {viewingRB.items.length > 0 ? (
                                            <RunbookTreePreview items={buildRunbookTree(viewingRB.items)} categoryColors={testcaseCategoryColors} />
                                        ) : (
                                            <p className="text-sm text-slate-500 text-center py-4">No items in this runbook</p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                        <DialogFooter>
                            <Button variant="ghost" onClick={() => setViewingRB(null)}>Close</Button>
                            {viewingRB && (() => {
                                const isOwner = viewingRB.created_by === user?.id;
                                const canEditDialog =
                                    (viewingRB.status === 'DRAFT' && (isOwner || canManage)) ||
                                    (viewingRB.status === 'PUBLISHED' && canManage);
                                if (!canEditDialog) return null;
                                return (
                                    <Button
                                        className="bg-primary hover:bg-primary/90 text-white"
                                        onClick={() => { setViewingRB(null); router.push(`/templates/runbooks/${viewingRB.id}/edit`); }}
                                    >
                                        <Pencil className="h-4 w-4 mr-2" /> Edit
                                    </Button>
                                );
                            })()}
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                {/* ─── View Report Layout Template Dialog ─── */}
                <Dialog open={!!viewingRLT} onOpenChange={open => !open && setViewingRLT(null)}>
                    <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle className="text-white text-lg flex items-center gap-2">
                                <LayoutTemplate className="h-5 w-5 text-primary" />
                                {viewingRLT?.name}
                            </DialogTitle>
                        </DialogHeader>
                        {viewingRLT && (
                            <div className="space-y-5">
                                {viewingRLT.description && (
                                    <div>
                                        <Label className="text-slate-400 text-xs uppercase tracking-wide">Description</Label>
                                        <p className="mt-1 text-sm text-slate-300">{viewingRLT.description}</p>
                                    </div>
                                )}
                                <div>
                                    <Label className="text-slate-400 text-xs uppercase tracking-wide">Sections ({viewingRLT.sections.length})</Label>
                                    <div className="mt-2 space-y-2">
                                        {viewingRLT.sections.sort((a, b) => a.sort_order - b.sort_order).map((s, idx) => (
                                            <div key={s.id} className="flex items-center gap-2 p-2.5 rounded-lg border border-slate-800 bg-slate-800/30">
                                                <span className="text-xs text-slate-500 w-6 text-center">{idx + 1}</span>
                                                <span className="text-sm text-white flex-1 truncate">{s.title}</span>
                                                <Badge variant="outline" className={`text-[10px] ${s.section_type === SectionType.TEXT ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                                    s.section_type === SectionType.FINDINGS ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                                        s.section_type === SectionType.TESTCASES ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                                            'bg-lime-500/10 text-lime-400 border-lime-500/20'
                                                    }`}>
                                                    {s.section_type === SectionType.TEXT ? 'Text' : s.section_type === SectionType.FINDINGS ? 'Findings' : s.section_type === SectionType.TESTCASES ? 'Test Cases' : 'Cleanup'}
                                                </Badge>
                                            </div>
                                        ))}
                                        {viewingRLT.sections.length === 0 && (
                                            <p className="text-sm text-slate-500 text-center py-4">No sections in this template</p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                        <DialogFooter>
                            <Button variant="ghost" onClick={() => setViewingRLT(null)}>Close</Button>
                            {canManage && viewingRLT && (
                                <Button
                                    className="bg-primary hover:bg-primary/90 text-white"
                                    onClick={() => { setViewingRLT(null); router.push(`/templates/report-layouts/${viewingRLT.id}/edit`); }}
                                >
                                    <Pencil className="h-4 w-4 mr-2" /> Edit
                                </Button>
                            )}
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                <ConfirmDialog />
            </div>
        </DashboardLayout>
    );
}

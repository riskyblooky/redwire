/**
 * engagements/page.tsx — Engagements List Page
 *
 * Sortable, searchable table of all engagements with status filter
 * buttons (All / In Progress / Planning). Supports:
 *  - Export to .zip (creates downloadable engagement archive)
 *  - Import from .zip with user-mapping dialog for unmatched users
 *  - Per-row action menu: view, edit, export, delete (permission-gated)
 *  - Real-time updates via WebSocket for engagement CRUD events
 *  - Sort preferences persisted to localStorage
 */
'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { Plus, Search, Eye, Edit, Trash2, Briefcase, Loader2, ArrowUpDown, ArrowUp, ArrowDown, Upload, Download, Users, ArrowRight, CheckCircle2, AlertCircle, MoreHorizontal, Filter, X } from 'lucide-react';
import { useEngagements, useDeleteEngagement } from '@/lib/hooks/use-engagements';
import { useEngagementTypes } from '@/lib/hooks/use-engagement-types';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { relevanceComparator } from '@/lib/search-relevance';
import api from '@/lib/api';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { useQueryClient } from '@tanstack/react-query';

const statusColors: Record<string, string> = {
    PROPOSED: 'bg-teal-500/10 text-teal-400 border-teal-500/20',
    PLANNING: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    IN_PROGRESS: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    REPORTING: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    COMPLETED: 'bg-green-500/10 text-green-400 border-green-500/20',
    ON_HOLD: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};



type SortField = 'name' | 'engagement_type' | 'status' | 'start_date' | 'end_date';
type SortOrder = 'asc' | 'desc';

const ALL_STATUSES = [
    { value: 'PROPOSED',    label: 'Proposed' },
    { value: 'PLANNING',    label: 'Planning' },
    { value: 'IN_PROGRESS', label: 'In Progress' },
    { value: 'REPORTING',   label: 'Reporting' },
    { value: 'COMPLETED',   label: 'Completed' },
    { value: 'ON_HOLD',     label: 'On Hold' },
];

interface EngagementRowProps {
    engagement: any;
    handleView: (id: string) => void;
    handleEdit: (id: string) => void;
    handleDelete: (id: string) => void;
    handleExport: (id: string, name: string) => void;
    isDeleting: boolean;
    isExporting: string | null;
    typeLabels: Record<string, string>;
}

const EngagementRow = ({ engagement, handleView, handleEdit, handleDelete, handleExport, isDeleting, isExporting, typeLabels }: EngagementRowProps) => {
    const canEdit = useCanEdit(engagement.id, 'engagement' as any, engagement.created_by);
    const canDelete = useCanDelete(engagement.id, 'engagement' as any, engagement.created_by);

    return (
        <TableRow
            className="border-slate-800 hover:bg-slate-800/50 cursor-pointer transition-colors"
            onClick={() => handleView(engagement.id)}
        >
            <TableCell className="font-medium text-white">
                <div>
                    <div className="font-semibold">{engagement.name}</div>
                    {engagement.description && (
                        <div className="text-sm text-slate-400 truncate max-w-md">
                            {engagement.description}
                        </div>
                    )}
                </div>
            </TableCell>
            <TableCell className="text-slate-300">
                <span className="text-sm">{typeLabels[engagement.engagement_type] || engagement.engagement_type}</span>
            </TableCell>
            <TableCell>
                <Badge className={statusColors[engagement.status] || statusColors.PLANNING}>
                    {engagement.status.replace('_', ' ')}
                </Badge>
            </TableCell>
            <TableCell className="text-slate-300 text-sm">
                {new Date(engagement.start_date).toLocaleDateString()}
            </TableCell>
            <TableCell className="text-slate-300 text-sm">
                {engagement.end_date ? new Date(engagement.end_date).toLocaleDateString() : <span className="text-slate-500">—</span>}
            </TableCell>
            <TableCell className="text-right">
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-slate-400 hover:text-white hover:bg-slate-800"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <MoreHorizontal className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                        <DropdownMenuItem onClick={() => handleView(engagement.id)}>
                            <Eye className="h-4 w-4 mr-2" />
                            View
                        </DropdownMenuItem>
                        {canEdit && (
                            <DropdownMenuItem onClick={() => handleEdit(engagement.id)}>
                                <Edit className="h-4 w-4 mr-2" />
                                Edit
                            </DropdownMenuItem>
                        )}
                        <DropdownMenuItem
                            onClick={() => handleExport(engagement.id, engagement.name)}
                            disabled={isExporting === engagement.id}
                        >
                            {isExporting === engagement.id ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Download className="h-4 w-4 mr-2" />
                            )}
                            Export
                        </DropdownMenuItem>
                        {canDelete && (
                            <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                    onClick={() => handleDelete(engagement.id)}
                                    className="text-red-400 focus:text-red-400"
                                    disabled={isDeleting}
                                >
                                    {isDeleting ? (
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    ) : (
                                        <Trash2 className="h-4 w-4 mr-2" />
                                    )}
                                    Delete
                                </DropdownMenuItem>
                            </>
                        )}
                    </DropdownMenuContent>
                </DropdownMenu>
            </TableCell>
        </TableRow>
    );
};

export default function EngagementsPage() {
    const router = useRouter();
    const [searchTerm, setSearchTerm] = useState('');
    const queryClient = useQueryClient();

    // ── Live updates via WebSocket ───────────────────────────────
    useCollaboration({
        resourceType: 'dashboard', resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                const rt = (data.resource_type || '').toLowerCase();
                if (rt === 'engagement') {
                    queryClient.invalidateQueries({ queryKey: ['engagements'] });
                }
            }
        },
    });

    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [typeFilter, setTypeFilter] = useState<string>('all');
    const [dateFrom, setDateFrom] = useState<string>('');
    const [dateTo, setDateTo] = useState<string>('');

    // PROPOSED engagements normally live on the Planning page. Admins,
    // read-only admins, and team leads can opt to mix them in here too.
    // TODO: replace this hardcoded role trio with a proper permission
    // (e.g. `engagement_view_proposed`) once a second consumer needs it
    // — same gate is currently inlined in
    // backend/routers/engagements.py for `/engagements/proposed`.
    const currentUser = useAuthStore(s => s.user);
    const canSeeProposed =
        currentUser?.role === UserRole.ADMIN ||
        currentUser?.role === UserRole.READ_ONLY_ADMIN ||
        currentUser?.role === UserRole.TEAM_LEAD;
    const [showProposed, setShowProposed] = useState<boolean>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_engagements_show_proposed') === '1';
        }
        return false;
    });
    useEffect(() => {
        if (typeof window !== 'undefined') {
            localStorage.setItem('redwire_engagements_show_proposed', showProposed ? '1' : '0');
        }
    }, [showProposed]);
    const [sortField, setSortField] = useState<SortField>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('redwire_sort_engagements_field');
            if (saved) return saved as SortField;
        }
        return 'start_date';
    });
    const [sortOrder, setSortOrder] = useState<SortOrder>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('redwire_sort_engagements_order');
            if (saved) return saved as SortOrder;
        }
        return 'desc';
    });

    // Save preferences to localStorage when they change
    useEffect(() => {
        localStorage.setItem('redwire_sort_engagements_field', sortField);
        localStorage.setItem('redwire_sort_engagements_order', sortOrder);
    }, [sortField, sortOrder]);

    const { data: engagements = [], isLoading, error } = useEngagements({
        includeProposed: canSeeProposed && showProposed,
    });
    const { data: engagementTypes = [] } = useEngagementTypes();
    const deleteEngagement = useDeleteEngagement();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const [isExporting, setIsExporting] = useState<string | null>(null);
    const [isImporting, setIsImporting] = useState(false);
    const importInputRef = useRef<HTMLInputElement>(null);
    const [importFile, setImportFile] = useState<File | null>(null);
    const [showUserMapping, setShowUserMapping] = useState(false);
    const [userMappingData, setUserMappingData] = useState<{
        engagementName: string;
        matchedUsers: any[];
        unmatchedUsers: any[];
        localUsers: any[];
    } | null>(null);
    const [userMapping, setUserMapping] = useState<Record<string, string>>({});

    // Build dynamic type label lookup
    const typeLabels: Record<string, string> = {};
    engagementTypes.forEach(t => { typeLabels[t.name] = t.description || t.name; });

    const hasActiveFilters = statusFilter !== 'all' || typeFilter !== 'all' || searchTerm !== '' || dateFrom !== '' || dateTo !== '';

    const filteredEngagements = [...engagements]
        .filter((engagement) => {
            const q = searchTerm.toLowerCase();
            const matchesSearch = !q ||
                engagement.name.toLowerCase().includes(q) ||
                (engagement.description?.toLowerCase().includes(q) ?? false) ||
                (engagement.client_name?.toLowerCase().includes(q) ?? false);
            const matchesStatus = statusFilter === 'all' || engagement.status === statusFilter;
            const matchesType = typeFilter === 'all' || engagement.engagement_type === typeFilter;
            const startTs = new Date(engagement.start_date).getTime();
            const matchesFrom = !dateFrom || startTs >= new Date(dateFrom).getTime();
            const matchesTo   = !dateTo   || startTs <= new Date(dateTo).getTime();
            return matchesSearch && matchesStatus && matchesType && matchesFrom && matchesTo;
        })
        .sort(relevanceComparator(
            searchTerm,
            [item => item.name, item => item.description || ''],
            (a, b) => {
                let comparison = 0;
                if (sortField === 'start_date') {
                    comparison = new Date(a.start_date).getTime() - new Date(b.start_date).getTime();
                } else if (sortField === 'end_date') {
                    const aEnd = a.end_date ? new Date(a.end_date).getTime() : 0;
                    const bEnd = b.end_date ? new Date(b.end_date).getTime() : 0;
                    comparison = aEnd - bEnd;
                } else {
                    comparison = String((a as any)[sortField]).localeCompare(String((b as any)[sortField]));
                }
                return sortOrder === 'asc' ? comparison : -comparison;
            }
        ));

    const handleSort = (field: SortField) => {
        if (sortField === field) {
            setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortOrder('asc');
        }
    };

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
        return sortOrder === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
    };

    const handleView = (id: string) => {
        router.push(`/engagements/${id}`);
    };

    const handleEdit = (id: string) => {
        router.push(`/engagements/${id}/edit`);
    };

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Engagement',
            description: 'Are you sure you want to delete this engagement? All associated findings, test cases, and data will be permanently removed.',
        });
        if (!confirmed) return;

        try {
            await deleteEngagement.mutateAsync(id);
        } catch (error: any) {
            console.error('Failed to delete engagement:', error);
            toast.error(getErrorMessage(error, 'Failed to delete engagement'));
        }
    };

    const handleCreate = () => {
        router.push('/engagements/new');
    };

    const handleExport = async (id: string, name: string) => {
        setIsExporting(id);
        try {
            const token = localStorage.getItem('access_token');
            const resp = await fetch(`${api.defaults.baseURL}/engagements/${id}/export`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                toast.error(err.detail || 'Export failed');
                setIsExporting(null);
                return;
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const disposition = resp.headers.get('content-disposition');
            const match = disposition?.match(/filename="(.+)"/);
            a.download = match?.[1] || `${name.replace(/\s+/g, '_')}_export.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            toast.success('Engagement exported successfully');
        } catch (err: any) {
            toast.error(err.message || 'Export failed');
        }
        setIsExporting(null);
    };

    const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (!file.name.endsWith('.zip')) {
            toast.error('Please select a .zip file');
            return;
        }
        setImportFile(file);
        setIsImporting(true);

        // Step 1: Preview — check for unmatched users
        try {
            const previewData = new FormData();
            previewData.append('file', file);
            const preview = await api.post('/engagements/import/preview', previewData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            const { engagement_name, matched_users, unmatched_users, local_users } = preview.data;

            if (unmatched_users.length > 0) {
                // Show mapping dialog
                setUserMappingData({
                    engagementName: engagement_name,
                    matchedUsers: matched_users,
                    unmatchedUsers: unmatched_users,
                    localUsers: local_users,
                });
                // Pre-populate mapping with empty (will fallback to importer)
                const initial: Record<string, string> = {};
                unmatched_users.forEach((u: any) => { initial[u.id] = ''; });
                setUserMapping(initial);
                setShowUserMapping(true);
                setIsImporting(false);
                if (importInputRef.current) importInputRef.current.value = '';
                return;
            }

            // No unmatched users — import directly
            await doImport(file, {});
        } catch (err: any) {
            const detail = err?.response?.data?.detail || err.message;
            toast.error(`Import preview failed: ${detail}`);
            setIsImporting(false);
        }
        if (importInputRef.current) importInputRef.current.value = '';
    };

    const doImport = async (file: File, mapping: Record<string, string>) => {
        setIsImporting(true);
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('user_mapping', JSON.stringify(mapping));
            const resp = await api.post('/engagements/import', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            toast.success(`Imported: ${resp.data.name}`);
            setShowUserMapping(false);
            setUserMappingData(null);
            setImportFile(null);
            router.push(`/engagements/${resp.data.id}`);
        } catch (err: any) {
            const detail = err?.response?.data?.detail || err.message;
            toast.error(`Import failed: ${detail}`);
        }
        setIsImporting(false);
    };

    const handleConfirmImportWithMapping = () => {
        if (importFile) {
            // Clean mapping: remove empty and '_self' entries (those fall back to importer)
            const cleanedMapping: Record<string, string> = {};
            for (const [oldId, newId] of Object.entries(userMapping)) {
                if (newId && newId !== '_self') {
                    cleanedMapping[oldId] = newId;
                }
            }
            doImport(importFile, cleanedMapping);
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                            <Briefcase className="h-8 w-8 text-primary" />
                            Engagements
                        </h1>
                        <p className="text-slate-400 mt-1">Manage security testing engagements and projects</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <input
                            ref={importInputRef}
                            type="file"
                            accept=".zip"
                            onChange={handleImport}
                            className="hidden"
                            id="import-engagement"
                        />
                        <Button
                            variant="outline"
                            onClick={() => importInputRef.current?.click()}
                            disabled={isImporting}
                            className="border-slate-700 text-slate-300 hover:text-white hover:bg-slate-800"
                        >
                            {isImporting ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Upload className="h-4 w-4 mr-2" />
                            )}
                            Import
                        </Button>
                        <Button onClick={handleCreate} className="bg-primary hover:bg-primary/90 text-white">
                            <Plus className="h-4 w-4 mr-2" />
                            New Engagement
                        </Button>
                    </div>
                </div>

                {/* Filters and Search */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                    <CardContent className="pt-6">
                        <div className="flex flex-col gap-3">
                            {/* Row 1: Search */}
                            <div className="flex gap-3">
                                <div className="flex-1 relative">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                                    <Input
                                        placeholder="Search by name, description, or client…"
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        className="pl-10 bg-slate-800/50 border-slate-700 text-white"
                                    />
                                    {searchTerm && (
                                        <button
                                            onClick={() => setSearchTerm('')}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
                                        >
                                            <X className="h-4 w-4" />
                                        </button>
                                    )}
                                </div>
                            </div>
                            {/* Row 2: Filters */}
                            <div className="flex flex-wrap items-center gap-2">
                                <Filter className="h-4 w-4 text-slate-400 flex-shrink-0" />
                                {/* Status filter */}
                                <Select value={statusFilter} onValueChange={setStatusFilter}>
                                    <SelectTrigger className="w-[160px] bg-slate-800/50 border-slate-700 text-slate-300 h-9 text-sm">
                                        <SelectValue placeholder="All Statuses" />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-900 border-slate-700">
                                        <SelectItem value="all" className="text-slate-300">All Statuses</SelectItem>
                                        {ALL_STATUSES.map(s => (
                                            <SelectItem key={s.value} value={s.value} className="text-slate-300">
                                                {s.label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                {/* Type filter */}
                                <Select value={typeFilter} onValueChange={setTypeFilter}>
                                    <SelectTrigger className="w-[180px] bg-slate-800/50 border-slate-700 text-slate-300 h-9 text-sm">
                                        <SelectValue placeholder="All Types" />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-900 border-slate-700">
                                        <SelectItem value="all" className="text-slate-300">All Types</SelectItem>
                                        {engagementTypes.map(t => (
                                            <SelectItem key={t.name} value={t.name} className="text-slate-300">
                                                {t.description || t.name}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                {/* Date range filter */}
                                <div className="flex items-center gap-1.5 text-sm">
                                    <span className="text-slate-500 text-xs">From</span>
                                    <input
                                        type="date"
                                        value={dateFrom}
                                        onChange={e => setDateFrom(e.target.value)}
                                        className="h-9 px-2 rounded-md bg-slate-800/50 border border-slate-700 text-slate-300 text-sm [color-scheme:dark] focus:outline-none focus:ring-1 focus:ring-primary"
                                    />
                                    <span className="text-slate-500 text-xs">To</span>
                                    <input
                                        type="date"
                                        value={dateTo}
                                        onChange={e => setDateTo(e.target.value)}
                                        className="h-9 px-2 rounded-md bg-slate-800/50 border border-slate-700 text-slate-300 text-sm [color-scheme:dark] focus:outline-none focus:ring-1 focus:ring-primary"
                                    />
                                </div>
                                {/* Show Proposed toggle (admins / team leads only) */}
                                {canSeeProposed && (
                                    <button
                                        type="button"
                                        onClick={() => setShowProposed(v => !v)}
                                        className={cn(
                                            'h-9 px-3 rounded-md border text-xs font-medium flex items-center gap-1.5 transition-colors',
                                            showProposed
                                                ? 'bg-teal-500/15 border-teal-500/40 text-teal-300 hover:bg-teal-500/20'
                                                : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:text-white',
                                        )}
                                        title="Include PROPOSED engagements (Planning page)"
                                    >
                                        <span
                                            className={cn(
                                                'h-1.5 w-1.5 rounded-full',
                                                showProposed ? 'bg-teal-400' : 'bg-slate-500',
                                            )}
                                        />
                                        Show Proposed
                                    </button>
                                )}
                                {/* Active filter badges */}
                                {statusFilter !== 'all' && (
                                    <Badge
                                        className="bg-purple-500/20 text-purple-400 border-purple-500/30 cursor-pointer hover:bg-primary/30 gap-1"
                                        onClick={() => setStatusFilter('all')}
                                    >
                                        {ALL_STATUSES.find(s => s.value === statusFilter)?.label}
                                        <X className="h-3 w-3" />
                                    </Badge>
                                )}
                                {typeFilter !== 'all' && (
                                    <Badge
                                        className="bg-blue-500/20 text-blue-300 border-blue-500/30 cursor-pointer hover:bg-blue-500/30 gap-1"
                                        onClick={() => setTypeFilter('all')}
                                    >
                                        {typeLabels[typeFilter] || typeFilter}
                                        <X className="h-3 w-3" />
                                    </Badge>
                                )}
                                {hasActiveFilters && (
                                    <button
                                        onClick={() => { setStatusFilter('all'); setTypeFilter('all'); setSearchTerm(''); setDateFrom(''); setDateTo(''); }}
                                        className="text-xs text-slate-400 hover:text-white transition-colors ml-1 underline underline-offset-2"
                                    >
                                        Clear all
                                    </button>
                                )}
                                <span className="ml-auto text-xs text-slate-500">
                                    {filteredEngagements.length} result{filteredEngagements.length !== 1 ? 's' : ''}
                                </span>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Engagements Table */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                    <CardHeader>
                        <CardTitle className="text-white">
                            All Engagements {!isLoading && `(${filteredEngagements.length})`}
                        </CardTitle>
                        <CardDescription>View and manage your security engagements</CardDescription>
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <div className="flex items-center justify-center py-10">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            </div>
                        ) : error ? (
                            <div className="text-center py-10 text-red-400">
                                Failed to load engagements. Please try again.
                            </div>
                        ) : (
                            <div className="rounded-md border border-slate-800">
                                <Table>
                                    <TableHeader>
                                        <TableRow className="border-slate-800 hover:bg-transparent">
                                            <TableHead
                                                className="text-slate-300 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('name')}
                                            >
                                                <div className="flex items-center">
                                                    Name <SortIcon field="name" />
                                                </div>
                                            </TableHead>
                                            <TableHead
                                                className="text-slate-300 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('engagement_type')}
                                            >
                                                <div className="flex items-center">
                                                    Type <SortIcon field="engagement_type" />
                                                </div>
                                            </TableHead>
                                            <TableHead
                                                className="text-slate-300 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('status')}
                                            >
                                                <div className="flex items-center">
                                                    Status <SortIcon field="status" />
                                                </div>
                                            </TableHead>
                                            <TableHead
                                                className="text-slate-300 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('start_date')}
                                            >
                                                <div className="flex items-center">
                                                    Start Date <SortIcon field="start_date" />
                                                </div>
                                            </TableHead>
                                            <TableHead
                                                className="text-slate-300 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('end_date')}
                                            >
                                                <div className="flex items-center">
                                                    End Date <SortIcon field="end_date" />
                                                </div>
                                            </TableHead>
                                            <TableHead className="text-slate-300 text-right">Actions</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {filteredEngagements.length === 0 ? (
                                            <TableRow>
                                                <TableCell colSpan={6} className="text-center text-slate-400 py-10">
                                                    {hasActiveFilters ? 'No engagements match your filters.' : 'No engagements found. Create your first engagement to get started.'}
                                                </TableCell>
                                            </TableRow>
                                        ) : (
                                            filteredEngagements.map((engagement) => (
                                                <EngagementRow
                                                    key={engagement.id}
                                                    engagement={engagement}
                                                    handleView={handleView}
                                                    handleEdit={handleEdit}
                                                    handleDelete={handleDelete}
                                                    handleExport={handleExport}
                                                    isDeleting={deleteEngagement.isPending}
                                                    isExporting={isExporting}
                                                    typeLabels={typeLabels}
                                                />
                                            ))
                                        )}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </CardContent>
                </Card>

                <ConfirmDialog />

                {/* User Mapping Dialog */}
                <Dialog open={showUserMapping} onOpenChange={(open) => {
                    if (!open) {
                        setShowUserMapping(false);
                        setImportFile(null);
                        setUserMappingData(null);
                    }
                }}>
                    <DialogContent className="sm:max-w-[600px] bg-slate-900 border-slate-700 text-white max-h-[80vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2 text-lg">
                                <Users className="h-5 w-5 text-amber-400" />
                                Map Users for Import
                            </DialogTitle>
                            <DialogDescription className="text-slate-400">
                                Importing <span className="text-white font-medium">{userMappingData?.engagementName}</span>.
                                Some users from the export don&apos;t exist on this instance.
                                Map them to local users or leave blank to assign to you.
                            </DialogDescription>
                        </DialogHeader>

                        <div className="space-y-4 py-4">
                            {/* Matched users */}
                            {userMappingData?.matchedUsers && userMappingData.matchedUsers.length > 0 && (
                                <div>
                                    <h4 className="text-sm font-medium text-emerald-400 mb-2 flex items-center gap-1.5">
                                        <CheckCircle2 className="h-4 w-4" /> Matched Users ({userMappingData.matchedUsers.length})
                                    </h4>
                                    <div className="space-y-1">
                                        {userMappingData.matchedUsers.map((u) => (
                                            <div key={u.id} className="flex items-center gap-2 px-3 py-2 bg-emerald-500/10 border border-emerald-500/20 rounded-md text-sm">
                                                <span className="text-slate-300">{u.full_name || u.username}</span>
                                                <ArrowRight className="h-3 w-3 text-emerald-400" />
                                                <span className="text-emerald-400">{u.local_full_name || u.local_username}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Unmatched users — need mapping */}
                            {userMappingData?.unmatchedUsers && userMappingData.unmatchedUsers.length > 0 && (
                                <div>
                                    <h4 className="text-sm font-medium text-amber-400 mb-2 flex items-center gap-1.5">
                                        <AlertCircle className="h-4 w-4" /> Unmatched Users ({userMappingData.unmatchedUsers.length})
                                    </h4>
                                    <div className="space-y-3">
                                        {userMappingData.unmatchedUsers.map((u) => (
                                            <div key={u.id} className="flex items-center gap-3 p-3 bg-slate-800/80 border border-slate-700 rounded-lg">
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm font-medium text-white truncate">
                                                        {u.full_name || u.username}
                                                    </p>
                                                    <p className="text-xs text-slate-500">
                                                        {u.username}{u.email ? ` • ${u.email}` : ''}
                                                    </p>
                                                </div>
                                                <ArrowRight className="h-4 w-4 text-slate-500 flex-shrink-0" />
                                                <Select
                                                    value={userMapping[u.id] || ''}
                                                    onValueChange={(val) => setUserMapping(prev => ({ ...prev, [u.id]: val }))}
                                                >
                                                    <SelectTrigger className="w-[200px] bg-slate-900 border-slate-600 text-sm">
                                                        <SelectValue placeholder="Assign to me" />
                                                    </SelectTrigger>
                                                    <SelectContent className="bg-slate-900 border-slate-700">
                                                        <SelectItem value="_self" className="text-slate-300">Assign to me</SelectItem>
                                                        {userMappingData.localUsers.map((lu) => (
                                                            <SelectItem key={lu.id} value={lu.id} className="text-slate-300">
                                                                {lu.full_name || lu.username}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>

                        <DialogFooter className="gap-2">
                            <Button
                                variant="outline"
                                onClick={() => {
                                    setShowUserMapping(false);
                                    setImportFile(null);
                                    setUserMappingData(null);
                                }}
                                className="border-slate-700 text-slate-300"
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={handleConfirmImportWithMapping}
                                disabled={isImporting}
                                className="bg-primary hover:bg-primary/90 text-white"
                            >
                                {isImporting ? (
                                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Importing...</>
                                ) : (
                                    <><Upload className="h-4 w-4 mr-2" /> Import Engagement</>
                                )}
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </div>
        </DashboardLayout>
    );
}

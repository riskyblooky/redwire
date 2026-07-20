/**
 * findings/page.tsx — Findings List Page
 *
 * Sortable, searchable table of all findings across every engagement.
 * Columns: title, severity (with icon), status, unresolved discussions,
 * primary asset, and created date. Supports:
 *  - Column-header sort (title, severity, status, date) with localStorage persistence
 *  - Relevance-ranked search across title, description, and asset names
 *  - Per-row action buttons (view, edit, delete) permission-gated per engagement
 *  - Real-time WebSocket updates for finding CRUD events
 */
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { parseUTCDate } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { CustomFieldListHeads, CustomFieldListCells } from '@/components/custom-fields/custom-field-list-columns';
import {
    Plus, Search, Eye, Edit, Trash2, Bug, Filter, Loader2,
    AlertTriangle, AlertCircle, Info, ShieldAlert, MessageSquare,
    ArrowUpDown, ArrowUp, ArrowDown
} from 'lucide-react';
import { useFindings, useDeleteFinding } from '@/lib/hooks/use-findings';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { useQueryClient } from '@tanstack/react-query';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { relevanceComparator } from '@/lib/search-relevance';
import { useCollaboration } from '@/lib/hooks/use-collaboration';

const FindingRow = ({ finding, router, severityColors, statusColors, getSeverityIcon, handleDelete, isDeleting }: any) => {
    const canEdit = useCanEdit(finding.engagement_id, 'finding', finding.created_by);
    const canDelete = useCanDelete(finding.engagement_id, 'finding', finding.created_by);

    return (
        <TableRow key={finding.id} className="border-slate-800 hover:bg-slate-800/50 group">
            <TableCell className="font-medium text-white pl-6 max-w-sm">
                <div className="flex flex-col">
                    <span>{finding.title}</span>
                    <span className="text-xs text-slate-500 truncate">{finding.description}</span>
                </div>
            </TableCell>
            <TableCell>
                <Badge className={`${severityColors[finding.severity]} border flex items-center gap-1.5 w-fit`}>
                    {getSeverityIcon(finding.severity)}
                    {finding.severity}
                </Badge>
            </TableCell>
            <TableCell>
                <Badge variant="outline" className={statusColors[finding.status]}>
                    {finding.status.replace('_', ' ')}
                </Badge>
            </TableCell>
            <TableCell>
                {finding.unresolved_thread_count && finding.unresolved_thread_count > 0 ? (
                    <div className="flex items-center gap-2 text-amber-400">
                        <MessageSquare className="h-4 w-4" />
                        <span className="text-sm font-medium">{finding.unresolved_thread_count}</span>
                    </div>
                ) : (
                    <span className="text-slate-600 text-sm">—</span>
                )}
            </TableCell>
            <TableCell className="text-slate-400 text-sm font-mono">
                {finding.assets && finding.assets.length > 0 ? finding.assets[0].name : '—'}
            </TableCell>
            <TableCell className="text-slate-400 text-sm">
                {parseUTCDate(finding.created_at).toLocaleDateString()}
            </TableCell>
            <CustomFieldListCells entity="finding" value={finding.custom_fields} />
            <TableCell className="text-right pr-6">
                <div className="flex justify-end gap-1">
                    <Button
                        variant="ghost" size="icon"
                        onClick={() => router.push(`/findings/${finding.id}`)}
                        className="text-slate-400 hover:text-white"
                    >
                        <Eye className="h-4 w-4" />
                    </Button>
                    {canEdit && (
                        <Button
                            variant="ghost" size="icon"
                            onClick={() => router.push(`/findings/${finding.id}/edit`)}
                            className="text-slate-400 hover:text-white"
                        >
                            <Edit className="h-4 w-4" />
                        </Button>
                    )}
                    {canDelete && (
                        <Button
                            variant="ghost" size="icon"
                            onClick={() => handleDelete(finding.id)}
                            disabled={isDeleting}
                            className="text-slate-400 hover:text-red-500"
                        >
                            <Trash2 className="h-4 w-4" />
                        </Button>
                    )}
                </div>
            </TableCell>
        </TableRow>
    );
};
import { toast } from 'sonner';
import { useState as useStateForEngagement } from 'react';

const severityColors: Record<string, string> = {
    CRITICAL: 'bg-red-500/20 text-red-500 border-red-500/30',
    HIGH: 'bg-orange-500/20 text-orange-500 border-orange-500/30',
    MEDIUM: 'bg-amber-500/20 text-amber-500 border-amber-500/30',
    LOW: 'bg-blue-500/20 text-blue-500 border-blue-500/30',
    INFO: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

const severityOrder: Record<string, number> = {
    CRITICAL: 0,
    HIGH: 1,
    MEDIUM: 2,
    LOW: 3,
    INFO: 4,
};

const statusColors: Record<string, string> = {
    OPEN: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    IN_REVIEW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    VERIFIED: 'bg-green-500/10 text-green-400 border-green-500/20',
    REMEDIATED: 'bg-teal-500/10 text-teal-400 border-teal-500/20',
    CLOSED: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

type SortField = 'title' | 'severity' | 'status' | 'created_at';
type SortOrder = 'asc' | 'desc';

export default function FindingsPage() {
    const router = useRouter();
    const [searchTerm, setSearchTerm] = useState('');
    const [sortField, setSortField] = useState<SortField>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('redwire_sort_findings_field');
            if (saved) return saved as SortField;
        }
        return 'created_at';
    });
    const [sortOrder, setSortOrder] = useState<SortOrder>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('redwire_sort_findings_order');
            if (saved) return saved as SortOrder;
        }
        return 'desc';
    });

    // Save preferences to localStorage when they change
    useEffect(() => {
        localStorage.setItem('redwire_sort_findings_field', sortField);
        localStorage.setItem('redwire_sort_findings_order', sortOrder);
    }, [sortField, sortOrder]);

    const { data: findings = [], isLoading, error, refetch } = useFindings();
    const deleteFinding = useDeleteFinding();
    const queryClient = useQueryClient();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // ── Live updates via WebSocket ───────────────────────────────
    useCollaboration({
        resourceType: 'dashboard', resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                const rt = (data.resource_type || '').toLowerCase();
                if (rt === 'finding') {
                    queryClient.invalidateQueries({ queryKey: ['findings'] });
                }
            }
        },
    });

    // Note: For global findings list, we can't check engagement-specific permissions
    // since findings may belong to different engagements. Permission checks are done
    // per-finding based on their engagement_id.

    const handleSort = (field: SortField) => {
        if (sortField === field) {
            setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortOrder('asc');
        }
    };

    const sortedFindings = [...findings]
        .filter((f) => {
            const matchesSearch = f.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                f.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
                (f.assets?.some(a => a.name.toLowerCase().includes(searchTerm.toLowerCase())) ?? false);
            return matchesSearch;
        })
        .sort(relevanceComparator(
            searchTerm,
            [item => item.title, item => item.description],
            (a, b) => {
                let comparison = 0;
                if (sortField === 'severity') {
                    comparison = severityOrder[a.severity] - severityOrder[b.severity];
                } else if (sortField === 'created_at') {
                    comparison = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
                } else {
                    comparison = String(a[sortField]).localeCompare(String(b[sortField]));
                }
                return sortOrder === 'asc' ? comparison : -comparison;
            }
        ));

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Finding',
            description: 'Are you sure you want to delete this finding?',
        });
        if (!confirmed) return;

        try {
            await deleteFinding.mutateAsync(id, {
                onSuccess: () => {
                    queryClient.invalidateQueries({ queryKey: ['threads'] });
                    queryClient.invalidateQueries({ queryKey: ['findings'], refetchType: 'all' });
                    queryClient.invalidateQueries({ queryKey: ['assets'], refetchType: 'all' });
                    queryClient.invalidateQueries({ queryKey: ['testcases'], refetchType: 'all' });
                },
            });
            refetch();
        } catch (error: any) {
            console.error('Failed to delete finding:', error);
            toast.error(getErrorMessage(error, 'Failed to delete finding'));
        }
    };

    const getSeverityIcon = (severity: string) => {
        switch (severity) {
            case 'CRITICAL': return <ShieldAlert className="h-4 w-4" />;
            case 'HIGH': return <AlertTriangle className="h-4 w-4" />;
            case 'MEDIUM': return <AlertCircle className="h-4 w-4" />;
            case 'LOW': return <Info className="h-4 w-4" />;
            default: return <Info className="h-4 w-4" />;
        }
    };

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
        return sortOrder === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                            <Bug className="h-8 w-8 text-red-500" />
                            Findings
                        </h1>
                    </div>
                    {/* Note: Create button shown for all users - engagement selection happens on create page */}
                    <Button onClick={() => router.push('/findings/new')} className="bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-500/20">
                        <Plus className="h-4 w-4 mr-2" />
                        New Finding
                    </Button>
                </div>

                {/* Search and Filters */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                    <CardContent className="pt-6">
                        <div className="flex gap-4">
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                                <Input
                                    placeholder="Search by title, description, or asset..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="pl-10 bg-slate-800/50 border-slate-700 text-white focus:ring-red-500 focus:border-red-500"
                                />
                            </div>
                            <Button variant="outline" className="border-slate-700 text-slate-300">
                                <Filter className="h-4 w-4 mr-2" />
                                Filters
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {/* Findings Table */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs overflow-hidden">
                    <CardHeader>
                        <CardTitle className="text-white">
                            All Findings {!isLoading && `(${sortedFindings.length})`}
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="px-0">
                        {isLoading ? (
                            <div className="flex items-center justify-center py-20">
                                <Loader2 className="h-10 w-10 animate-spin text-red-500" />
                            </div>
                        ) : error ? (
                            <div className="text-center py-20 text-red-400">
                                Failed to load findings. Please check your connection.
                            </div>
                        ) : (
                            <div className="border-t border-slate-800">
                                <Table>
                                    <TableHeader className="bg-slate-800/30">
                                        <TableRow className="border-slate-800 hover:bg-transparent">
                                            <TableHead
                                                className="text-slate-300 font-semibold pl-6 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('title')}
                                            >
                                                <div className="flex items-center">
                                                    Finding Title <SortIcon field="title" />
                                                </div>
                                            </TableHead>
                                            <TableHead
                                                className="text-slate-300 font-semibold cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('severity')}
                                            >
                                                <div className="flex items-center">
                                                    Severity <SortIcon field="severity" />
                                                </div>
                                            </TableHead>
                                            <TableHead
                                                className="text-slate-300 font-semibold cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('status')}
                                            >
                                                <div className="flex items-center">
                                                    Status <SortIcon field="status" />
                                                </div>
                                            </TableHead>
                                            <TableHead className="text-slate-300 font-semibold">Discussions</TableHead>
                                            <TableHead className="text-slate-300 font-semibold">Asset</TableHead>
                                            <TableHead
                                                className="text-slate-300 font-semibold cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('created_at')}
                                            >
                                                <div className="flex items-center">
                                                    Created <SortIcon field="created_at" />
                                                </div>
                                            </TableHead>
                                            <CustomFieldListHeads entity="finding" />
                                            <TableHead className="text-right text-slate-300 font-semibold pr-6">Actions</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {sortedFindings.length === 0 ? (
                                            <TableRow>
                                                <TableCell colSpan={7} className="text-center text-slate-400 py-20">
                                                    No findings matches your search criteria.
                                                </TableCell>
                                            </TableRow>
                                        ) : (
                                            sortedFindings.map((f) => (
                                                <FindingRow
                                                    key={f.id}
                                                    finding={f}
                                                    router={router}
                                                    severityColors={severityColors}
                                                    statusColors={statusColors}
                                                    getSeverityIcon={getSeverityIcon}
                                                    handleDelete={handleDelete}
                                                    isDeleting={deleteFinding.isPending}
                                                />
                                            ))
                                        )}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
            <ConfirmDialog />
        </DashboardLayout>
    );
}

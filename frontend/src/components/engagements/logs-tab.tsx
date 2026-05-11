'use client';

import { useState, useEffect, useMemo } from 'react';
import {
    ChevronLeft,
    ChevronRight,
    ChevronsLeft,
    ChevronsRight,
} from 'lucide-react';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from '@/components/ui/table';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Loader2,
    Search,
    History,
    Filter,
    ArrowUpDown,
    ArrowUp,
    ArrowDown,
    User,
    Calendar,
    Target,
    Bug,
    Server,
    CheckSquare,
    FileText as FileIcon,
    Shield,
    MessageSquare,
    Link as LinkIcon,
    Sparkles
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { ActivityLog } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { cn } from '@/lib/utils';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { useQueryClient } from '@tanstack/react-query';
import { UserAvatar } from '@/components/ui/user-avatar';

interface LogsTabProps {
    engagementId: string;
}

const resourceTypeIcons: Record<string, any> = {
    engagement: Target,
    finding: Bug,
    asset: Server,
    testcase: CheckSquare,
    evidence: FileIcon,
    comment: MessageSquare,
    note: FileIcon,
    vault: Shield,
    cleanup_artifact: Sparkles,
};

const resourceTypeColors: Record<string, string> = {
    engagement: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    finding: 'bg-red-500/10 text-red-400 border-red-500/20',
    asset: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    testcase: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    evidence: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    comment: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
    note: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    vault: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    cleanup_artifact: 'bg-lime-500/10 text-lime-400 border-lime-500/20',
};

const PAGE_SIZE = 25;

export function LogsTab({ engagementId }: LogsTabProps) {
    const [search, setSearch] = useState('');
    const debouncedSearch = useDebounce(search, 500);
    const [resourceType, setResourceType] = useState<string>('all');
    const [actionFilter, setActionFilter] = useState<string>('all');
    const [userFilter, setUserFilter] = useState<string>('all');
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
    const [currentPage, setCurrentPage] = useState(1);
    const queryClient = useQueryClient();

    // Reset to page 1 when filters change
    useEffect(() => {
        setCurrentPage(1);
    }, [debouncedSearch, resourceType, actionFilter, userFilter, sortOrder]);

    // Listen for real-time updates
    useCollaboration({
        resourceType: 'engagement',
        resourceId: engagementId,
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                queryClient.invalidateQueries({ queryKey: ['engagement-logs', engagementId] });
            }
        }
    });

    // Fetch engagement details to get assigned users for filter
    const { data: engagement } = useQuery({
        queryKey: ['engagement', engagementId],
        queryFn: async () => {
            const response = await api.get(`/engagements/${engagementId}`);
            return response.data;
        }
    });

    const { data: logsData, isLoading } = useQuery({
        queryKey: ['engagement-logs', engagementId, debouncedSearch, resourceType, actionFilter, userFilter, sortOrder, currentPage],
        refetchOnMount: 'always',
        queryFn: async () => {
            const params = new URLSearchParams();
            if (debouncedSearch) params.append('search', debouncedSearch);
            if (resourceType && resourceType !== 'all') params.append('resource_type', resourceType);
            if (actionFilter && actionFilter !== 'all') params.append('action', actionFilter);
            if (userFilter && userFilter !== 'all') params.append('user_id', userFilter);
            params.append('sort_order', sortOrder);
            params.append('sort_by', 'created_at');
            params.append('limit', String(PAGE_SIZE));
            params.append('offset', String((currentPage - 1) * PAGE_SIZE));

            const response = await api.get<{ items: ActivityLog[]; total: number }>(`/discussions/activity?engagement_id=${engagementId}&${params.toString()}`);
            return response.data;
        }
    });

    const logs = logsData?.items ?? [];
    const totalLogs = logsData?.total ?? 0;
    const totalPages = Math.max(1, Math.ceil(totalLogs / PAGE_SIZE));

    // Extract unique actions for filter (from current page — best effort)
    const uniqueActions = Array.from(new Set(logs.map(log => log.action))).sort();

    const getIcon = (type: string) => {
        const Icon = resourceTypeIcons[type.toLowerCase()] || History;
        return <Icon className="h-4 w-4" />;
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div>
                    <CardTitle className="text-white">Engagement Activity Log</CardTitle>
                    <CardDescription>Comprehensive timeline of all actions and changes</CardDescription>
                </div>
            </CardHeader>
            <CardContent className="space-y-6">
                {/* Filters */}
                <div className="flex flex-col md:flex-row gap-4 items-center justify-between bg-slate-950/30 p-4 rounded-lg border border-slate-800/50">
                    <div className="flex items-center gap-2 w-full md:w-auto flex-1 max-w-sm">
                        <Search className="h-4 w-4 text-slate-500" />
                        <Input
                            placeholder="Search logs..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="bg-transparent border-none focus-visible:ring-0 h-8 text-sm px-0 placeholder:text-slate-600"
                        />
                    </div>
                    <div className="flex items-center gap-2 w-full md:w-auto flex-wrap">
                        <Select value={resourceType} onValueChange={setResourceType}>
                            <SelectTrigger className="w-[140px] h-8 bg-slate-900 border-slate-700 text-xs">
                                <div className="flex items-center gap-2">
                                    <Filter className="h-3 w-3 text-slate-400" />
                                    <SelectValue placeholder="Resource Type" />
                                </div>
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-800">
                                <SelectItem value="all">All Types</SelectItem>
                                <SelectItem value="engagement">Engagement</SelectItem>
                                <SelectItem value="finding">Finding</SelectItem>
                                <SelectItem value="asset">Asset</SelectItem>
                                <SelectItem value="testcase">Test Case</SelectItem>
                                <SelectItem value="evidence">Evidence</SelectItem>
                                <SelectItem value="comment">Discussion</SelectItem>
                                <SelectItem value="note">Note</SelectItem>
                                <SelectItem value="vault">Vault</SelectItem>
                                <SelectItem value="cleanup_artifact">Cleanup</SelectItem>
                            </SelectContent>
                        </Select>

                        <Select value={actionFilter} onValueChange={setActionFilter}>
                            <SelectTrigger className="w-[140px] h-8 bg-slate-900 border-slate-700 text-xs">
                                <SelectValue placeholder="Action" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-800">
                                <SelectItem value="all">All Actions</SelectItem>
                                {uniqueActions.map(action => (
                                    <SelectItem key={action} value={action} className="capitalize">{action.replace('_', ' ')}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Select value={userFilter} onValueChange={setUserFilter}>
                            <SelectTrigger className="w-[140px] h-8 bg-slate-900 border-slate-700 text-xs">
                                <div className="flex items-center gap-2">
                                    <User className="h-3 w-3 text-slate-400" />
                                    <SelectValue placeholder="User" />
                                </div>
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-800">
                                <SelectItem value="all">All Users</SelectItem>
                                {(engagement?.assigned_users || []).map((user: any) => (
                                    <SelectItem key={user.id} value={user.id}>{user.username}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                </div>

                {isLoading ? (
                    <div className="flex justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                ) : logs.length === 0 ? (
                    <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                        <History className="h-12 w-12 mx-auto mb-4 text-slate-600 opacity-20" />
                        <p className="text-slate-500">No activity logs match your criteria.</p>
                    </div>
                ) : (
                    <div className="rounded-md border border-slate-800 overflow-hidden">
                        <Table>
                            <TableHeader className="bg-slate-900/50">
                                <TableRow className="border-slate-800 hover:bg-transparent">
                                    <TableHead
                                        className="w-[180px] text-slate-400 cursor-pointer hover:text-white transition-colors select-none"
                                        onClick={() => setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}
                                    >
                                        <div className="flex items-center gap-2">
                                            Timestamp
                                            {sortOrder === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
                                        </div>
                                    </TableHead>
                                    <TableHead className="w-[150px] text-slate-400">User</TableHead>
                                    <TableHead className="w-[120px] text-slate-400">Action</TableHead>
                                    <TableHead className="w-[150px] text-slate-400">Resource</TableHead>
                                    <TableHead className="text-slate-400">Details</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {logs.map((log) => {
                                    const resourceType = log.resource_type?.toLowerCase();
                                    const link = (resourceType === 'engagement')
                                        ? `/engagements/${log.resource_id}`
                                        : (resourceType === 'finding')
                                            ? `/findings/${log.resource_id}?engagementId=${engagementId}`
                                            : (resourceType === 'asset')
                                                ? `/assets/edit/${log.resource_id}?engagementId=${engagementId}`
                                                : (resourceType === 'evidence')
                                                    ? `/engagements/${engagementId}?tab=attachments`
                                                    : (resourceType === 'testcase')
                                                        ? `/testcases/${log.resource_id}?engagementId=${engagementId}`
                                                        : null;

                                    return (
                                        <TableRow
                                            key={log.id}
                                            className={cn(
                                                "border-slate-800 transition-all duration-200",
                                                link ? "cursor-pointer hover:bg-primary/90/5" : "hover:bg-slate-800/30"
                                            )}
                                            onClick={() => link && window.location.assign(link)}
                                        >
                                            <TableCell className="text-xs text-slate-500 font-mono whitespace-nowrap">
                                                {new Date(log.created_at).toLocaleString()}
                                                <div className="text-[10px] opacity-60">
                                                    {formatDistanceToNow(parseUTCDate(log.created_at), { addSuffix: true })}
                                                </div>
                                            </TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-2">
                                                    <UserAvatar
                                                        user={{ id: log.user_id, username: log.user_name || 'System', profile_photo: (log as any).user_profile_photo }}
                                                        userId={log.user_id}
                                                        username={log.user_name}
                                                        className="h-6 w-6"
                                                    />
                                                    <span className="text-sm text-slate-300">{log.user_name || 'System'}</span>
                                                </div>
                                            </TableCell>
                                            <TableCell>
                                                <Badge variant="outline" className="text-[10px] uppercase font-bold bg-slate-800 border-none text-slate-400">
                                                    {log.action}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-2">
                                                    <Badge
                                                        variant="outline"
                                                        className={`w-6 h-6 p-0 flex items-center justify-center rounded-md border-none ${resourceTypeColors[log.resource_type?.toLowerCase()] || 'bg-slate-800 text-slate-400'}`}
                                                    >
                                                        {getIcon(log.resource_type)}
                                                    </Badge>
                                                    <span className="text-xs font-medium text-slate-300 truncate max-w-[120px]" title={log.resource_name}>
                                                        {log.resource_name || 'Unknown'}
                                                    </span>
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-sm text-slate-400">
                                                {log.details}
                                            </TableCell>
                                        </TableRow>
                                    );
                                })}
                            </TableBody>
                        </Table>
                    </div>
                )}

                {/* Pagination Controls */}
                {totalLogs > 0 && (
                    <div className="flex items-center justify-between pt-4 border-t border-slate-800/50">
                        <p className="text-xs text-slate-500">
                            Showing {((currentPage - 1) * PAGE_SIZE) + 1}–{Math.min(currentPage * PAGE_SIZE, totalLogs)} of {totalLogs} entries
                        </p>
                        <div className="flex items-center gap-1">
                            <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30"
                                onClick={() => setCurrentPage(1)}
                                disabled={currentPage === 1}
                            >
                                <ChevronsLeft className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30"
                                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                disabled={currentPage === 1}
                            >
                                <ChevronLeft className="h-3.5 w-3.5" />
                            </Button>
                            <span className="text-xs text-slate-400 px-3 font-medium">
                                Page {currentPage} of {totalPages}
                            </span>
                            <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30"
                                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                disabled={currentPage === totalPages}
                            >
                                <ChevronRight className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30"
                                onClick={() => setCurrentPage(totalPages)}
                                disabled={currentPage === totalPages}
                            >
                                <ChevronsRight className="h-3.5 w-3.5" />
                            </Button>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { formatDistanceToNow } from 'date-fns';
import {
    Bell, Search, Filter, ArrowUp, ArrowDown, Mail, MailOpen, Trash2,
    ExternalLink, CheckCheck, X, Loader2, User as UserIcon,
    ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
} from 'lucide-react';
import { toast } from 'sonner';
import DashboardLayout from '@/components/layout/dashboard-layout';
import {
    useNotificationsBrowse, useMarkRead, useMarkUnread, useMarkAllRead,
    useClearAllNotifications, useDeleteNotification, useNotificationPreferences,
    type NotificationItem,
} from '@/lib/hooks/use-notifications';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { cn, parseUTCDate } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

const EVENT_ICON: Record<string, string> = {
    engagement_assigned: '👥',
    engagement_removed: '🚫',
    finding_created: '🔍',
    finding_status_changed: '🔄',
    engagement_status_changed: '📋',
    password_reset: '🔑',
    mention: '💬',
    automation: '⚙️',
};

const PAGE_SIZE = 25;

export default function NotificationsPage() {
    const router = useRouter();
    const [search, setSearch] = useState('');
    const debouncedSearch = useDebounce(search, 400);
    const [readStatus, setReadStatus] = useState<'all' | 'unread' | 'read'>('all');
    const [eventType, setEventType] = useState('all');
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
    const [page, setPage] = useState(1);

    useEffect(() => {
        setPage(1);
    }, [debouncedSearch, readStatus, eventType, sortOrder]);

    const { data: prefs = [] } = useNotificationPreferences();
    const { data, isLoading } = useNotificationsBrowse({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        read_status: readStatus === 'all' ? '' : readStatus,
        event_type: eventType === 'all' ? '' : eventType,
        search: debouncedSearch,
        sort_order: sortOrder,
    });

    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const markRead = useMarkRead();
    const markUnread = useMarkUnread();
    const markAllRead = useMarkAllRead();
    const clearAll = useClearAllNotifications();
    const del = useDeleteNotification();

    const eventLabel = (et: string) => prefs.find((p) => p.event_type === et)?.label || et;

    const openNotif = (n: NotificationItem) => {
        if (!n.is_read) markRead.mutate(n.id);
        if (n.link) router.push(n.link);
    };

    const hasFilters = !!debouncedSearch || readStatus !== 'all' || eventType !== 'all';
    const clearFilters = () => { setSearch(''); setReadStatus('all'); setEventType('all'); };

    return (
        <DashboardLayout>
            <div className="mx-auto max-w-5xl space-y-4 p-6">
                {/* Header */}
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <h1 className="flex items-center gap-3 text-3xl font-bold text-white">
                            <Bell className="h-8 w-8 text-primary" /> Notifications
                        </h1>
                        <p className="text-sm text-slate-500">{total} total</p>
                    </div>
                    <div className="flex gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5 border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800 hover:text-white"
                            onClick={() => markAllRead.mutate(undefined, { onSuccess: () => toast.success('All notifications marked read') })}
                        >
                            <CheckCheck className="h-3.5 w-3.5" /> Mark all read
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5 border-red-500/30 bg-slate-900 text-red-400 hover:bg-red-500/10 hover:text-red-300"
                            onClick={() => {
                                if (window.confirm('Delete ALL notifications? This cannot be undone.')) {
                                    clearAll.mutate(undefined, { onSuccess: () => toast.success('Notifications cleared') });
                                }
                            }}
                        >
                            <Trash2 className="h-3.5 w-3.5" /> Clear all
                        </Button>
                    </div>
                </div>

                {/* Filters */}
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800/50 bg-slate-950/30 p-3">
                    <div className="flex min-w-[180px] flex-1 items-center gap-2">
                        <Search className="h-4 w-4 shrink-0 text-slate-500" />
                        <Input
                            placeholder="Search notifications…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="h-8 border-none bg-transparent px-0 text-sm placeholder:text-slate-600 focus-visible:ring-0"
                        />
                    </div>

                    <Select value={readStatus} onValueChange={(v) => setReadStatus(v as any)}>
                        <SelectTrigger className="h-8 w-[120px] border-slate-700 bg-slate-900 text-xs">
                            <SelectValue placeholder="Status" />
                        </SelectTrigger>
                        <SelectContent className="border-slate-800 bg-slate-900">
                            <SelectItem value="all">All</SelectItem>
                            <SelectItem value="unread">Unread</SelectItem>
                            <SelectItem value="read">Read</SelectItem>
                        </SelectContent>
                    </Select>

                    <Select value={eventType} onValueChange={setEventType}>
                        <SelectTrigger className="h-8 w-[180px] border-slate-700 bg-slate-900 text-xs">
                            <div className="flex items-center gap-2">
                                <Filter className="h-3 w-3 text-slate-400" />
                                <SelectValue placeholder="Type" />
                            </div>
                        </SelectTrigger>
                        <SelectContent className="border-slate-800 bg-slate-900">
                            <SelectItem value="all">All types</SelectItem>
                            {prefs.map((p) => (
                                <SelectItem key={p.event_type} value={p.event_type}>
                                    {EVENT_ICON[p.event_type] || '🔔'} {p.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>

                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setSortOrder((p) => (p === 'asc' ? 'desc' : 'asc'))}
                        className="h-8 gap-1 border-slate-700 bg-slate-900 text-xs text-slate-300 hover:bg-slate-800 hover:text-white"
                        title="Toggle sort order"
                    >
                        {sortOrder === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
                        {sortOrder === 'asc' ? 'Oldest' : 'Newest'}
                    </Button>

                    {hasFilters && (
                        <Button variant="ghost" size="sm" onClick={clearFilters} className="h-8 gap-1 text-xs text-slate-400 hover:text-white">
                            <X className="h-3 w-3" /> Clear
                        </Button>
                    )}
                </div>

                {/* List */}
                {isLoading ? (
                    <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
                ) : items.length === 0 ? (
                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="py-16 text-center">
                            <Bell className="mx-auto mb-4 h-12 w-12 text-slate-600 opacity-20" />
                            <p className="text-slate-500">{hasFilters ? 'No notifications match your filters.' : "You're all caught up."}</p>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="space-y-1.5">
                        {items.map((n) => (
                            <div
                                key={n.id}
                                className={cn(
                                    'group flex items-start gap-3 rounded-lg border p-3 transition-colors',
                                    n.is_read
                                        ? 'border-slate-800 bg-slate-900/30 hover:bg-slate-800/30'
                                        : 'border-blue-500/20 bg-blue-500/5 hover:bg-blue-500/10',
                                )}
                            >
                                <span className="mt-0.5 shrink-0 text-lg leading-none">{EVENT_ICON[n.event_type] || '🔔'}</span>
                                <button type="button" onClick={() => openNotif(n)} className="min-w-0 flex-1 text-left">
                                    <div className="flex items-center gap-2">
                                        {!n.is_read && <span className="h-2 w-2 shrink-0 rounded-full bg-blue-400" />}
                                        <span className={cn('truncate text-sm', n.is_read ? 'font-medium text-slate-300' : 'font-semibold text-white')}>
                                            {n.title}
                                        </span>
                                        {n.link && <ExternalLink className="h-3 w-3 shrink-0 text-slate-500" />}
                                    </div>
                                    {n.message && <p className="mt-0.5 line-clamp-2 text-xs text-slate-400">{n.message}</p>}
                                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
                                        <Badge variant="outline" className="h-4 border-slate-700 bg-slate-800/60 px-1.5 text-[10px] text-slate-400">
                                            {eventLabel(n.event_type)}
                                        </Badge>
                                        {n.actor_name && (
                                            <span className="flex items-center gap-1"><UserIcon className="h-3 w-3" />{n.actor_name}</span>
                                        )}
                                        <span title={parseUTCDate(n.created_at).toLocaleString()}>
                                            {formatDistanceToNow(parseUTCDate(n.created_at), { addSuffix: true })}
                                        </span>
                                    </div>
                                </button>
                                <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                                    {n.is_read ? (
                                        <button
                                            type="button"
                                            title="Mark unread"
                                            onClick={() => markUnread.mutate(n.id)}
                                            className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                                        >
                                            <Mail className="h-3.5 w-3.5" />
                                        </button>
                                    ) : (
                                        <button
                                            type="button"
                                            title="Mark read"
                                            onClick={() => markRead.mutate(n.id)}
                                            className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                                        >
                                            <MailOpen className="h-3.5 w-3.5" />
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        title="Delete"
                                        onClick={() => del.mutate(n.id)}
                                        className="rounded p-1.5 text-slate-400 hover:bg-red-500/10 hover:text-red-400"
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Pagination */}
                {total > 0 && (
                    <div className="flex items-center justify-between border-t border-slate-800/50 pt-4">
                        <p className="text-xs text-slate-500">
                            Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
                        </p>
                        <div className="flex items-center gap-1">
                            <Button variant="outline" size="icon" className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30" onClick={() => setPage(1)} disabled={page === 1}><ChevronsLeft className="h-3.5 w-3.5" /></Button>
                            <Button variant="outline" size="icon" className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}><ChevronLeft className="h-3.5 w-3.5" /></Button>
                            <span className="px-3 text-xs font-medium text-slate-400">Page {page} of {totalPages}</span>
                            <Button variant="outline" size="icon" className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}><ChevronRight className="h-3.5 w-3.5" /></Button>
                            <Button variant="outline" size="icon" className="h-7 w-7 border-slate-700 bg-slate-900/50 text-slate-400 hover:text-white disabled:opacity-30" onClick={() => setPage(totalPages)} disabled={page === totalPages}><ChevronsRight className="h-3.5 w-3.5" /></Button>
                        </div>
                    </div>
                )}
            </div>
        </DashboardLayout>
    );
}

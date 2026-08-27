'use client';

import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import {
    Loader2, Search, Filter, ArrowUp, ArrowDown, User as UserIcon,
    History, X, ArrowRight, ChevronLeft, ChevronRight,
    ChevronsLeft, ChevronsRight,
} from 'lucide-react';
import { api } from '@/lib/api';
import { cn, parseUTCDate } from '@/lib/utils';
import { displayName } from '@/lib/display-name';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { UserAvatar } from '@/components/ui/user-avatar';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { computeLineDiff } from '@/components/ui/version-history-panel';
import { resourceTypeIcons, resourceTypeColors, openThreadFromLog } from './logs-tab';
import { FeedItemPicker } from './feed-item-picker';
import { MultiSelectFilter } from '@/components/ui/multi-select-filter';
import { DateRangeFilter } from '@/components/ui/date-range-filter';

interface FeedChange { field: string; label: string; old: string | null; new: string | null }
interface FeedItem {
    id: string;
    created_at: string;
    user_id: string;
    user_name: string;
    user_profile_photo?: string | null;
    action: string;
    action_category: string;
    resource_type: string;
    resource_id: string;
    resource_name?: string | null;
    details?: string | null;
    content_kind: 'text' | 'diff' | 'none';
    content?: string | null;
    changes: FeedChange[];
}

const PAGE_SIZE = 20;

// Multi-select vocabulary — the content-bearing resource types.
const ACTION_OPTIONS: { value: string; label: string }[] = [
    { value: 'created', label: 'Created' },
    { value: 'updated', label: 'Updated' },
    { value: 'deleted', label: 'Deleted' },
    { value: 'commented', label: 'Comments' },
];

const TYPE_OPTIONS: { value: string; label: string }[] = [
    { value: 'finding', label: 'Findings' },
    { value: 'testcase', label: 'Test Cases' },
    { value: 'note', label: 'Notes' },
    { value: 'comment', label: 'Discussion' },
    { value: 'asset', label: 'Assets' },
    { value: 'evidence', label: 'Evidence' },
    { value: 'cleanup_artifact', label: 'Cleanup' },
    { value: 'vault', label: 'Vault' },
];

// Fields rendered as compact old→new chips; everything else gets a line diff.
const SHORT_FIELDS = new Set([
    'severity', 'status', 'category', 'cvss_score', 'cvss_vector', 'title',
    'is_executed', 'is_successful',
]);

const ACTION_CATEGORY_STYLE: Record<string, string> = {
    created: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    updated: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    deleted: 'bg-red-500/10 text-red-400 border-red-500/20',
    commented: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    other: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};
const ACTION_CATEGORY_LABEL: Record<string, string> = {
    created: 'Created', updated: 'Updated', deleted: 'Deleted', commented: 'Comment', other: 'Activity',
};

function feedLink(item: FeedItem, engagementId: string): string | null {
    const rt = (item.resource_type || '').toLowerCase();
    switch (rt) {
        case 'engagement': return `/engagements/${item.resource_id}`;
        case 'finding': return `/findings/${item.resource_id}?engagementId=${engagementId}`;
        case 'asset': return `/assets/${item.resource_id}?engagementId=${engagementId}`;
        case 'testcase': return `/testcases/${item.resource_id}?engagementId=${engagementId}`;
        case 'vault': return `/engagements/${engagementId}?tab=vault`;
        case 'cleanup_artifact': return `/engagements/${engagementId}?tab=cleanup`;
        case 'note': return `/engagements/${engagementId}?tab=notes&noteId=${item.resource_id}`;
        case 'evidence': return `/engagements/${engagementId}?tab=attachments`;
        default: return null;
    }
}

function ChangeRow({ change }: { change: FeedChange }) {
    const oldV = change.old ?? '';
    const newV = change.new ?? '';

    if (SHORT_FIELDS.has(change.field)) {
        return (
            <div className="space-y-1">
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">{change.label}</div>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded bg-red-500/10 px-2 py-0.5 text-red-400 line-through">{oldV || '∅'}</span>
                    <ArrowRight className="h-3 w-3 shrink-0 text-slate-600" />
                    <span className="rounded bg-green-500/10 px-2 py-0.5 text-green-400">{newV || '∅'}</span>
                </div>
            </div>
        );
    }

    const diff = computeLineDiff(oldV, newV);
    return (
        <div className="space-y-1">
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">{change.label}</div>
            <div className="max-h-64 overflow-auto rounded-md border border-slate-800 bg-slate-950/60 p-2 font-mono text-[11px] leading-relaxed">
                {diff.map((line, i) => (
                    <div
                        key={i}
                        className={cn(
                            'whitespace-pre-wrap px-1',
                            line.type === 'add' && 'bg-green-500/10 text-green-300',
                            line.type === 'remove' && 'bg-red-500/10 text-red-300',
                            line.type === 'same' && 'text-slate-500',
                        )}
                    >
                        <span className="mr-1 select-none opacity-50">
                            {line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' '}
                        </span>
                        {line.text || ' '}
                    </div>
                ))}
            </div>
        </div>
    );
}

function FeedCard({ item, engagementId }: { item: FeedItem; engagementId: string }) {
    const Icon = resourceTypeIcons[item.resource_type?.toLowerCase()] || History;
    const link = feedLink(item, engagementId);
    const isThread = item.resource_type?.toLowerCase() === 'comment';
    const clickable = !!link || (isThread && !!item.resource_id);
    const go = () => {
        if (link) window.location.assign(link);
        else if (isThread && item.resource_id) openThreadFromLog(item.resource_id, engagementId);
    };

    return (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
            <div className="flex items-start gap-3">
                <UserAvatar
                    user={{ id: item.user_id, username: item.user_name || 'System', profile_photo: item.user_profile_photo }}
                    userId={item.user_id}
                    username={item.user_name}
                    className="mt-0.5 h-7 w-7 shrink-0"
                />
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-sm font-semibold text-slate-200">{item.user_name || 'System'}</span>
                        <Badge variant="outline" className={cn('h-4 px-1.5 text-[10px] font-bold uppercase', ACTION_CATEGORY_STYLE[item.action_category] || ACTION_CATEGORY_STYLE.other)}>
                            {ACTION_CATEGORY_LABEL[item.action_category] || item.action}
                        </Badge>
                        <Badge variant="outline" className={cn('flex h-4 items-center gap-1 px-1.5 text-[10px]', resourceTypeColors[item.resource_type?.toLowerCase()] || 'bg-slate-800 text-slate-400 border-none')}>
                            <Icon className="h-3 w-3" />
                            {item.resource_type}
                        </Badge>
                        <button
                            type="button"
                            onClick={clickable ? go : undefined}
                            className={cn('max-w-[280px] truncate text-sm font-medium', clickable ? 'text-blue-400 hover:underline' : 'text-slate-400 cursor-default')}
                            title={item.resource_name || undefined}
                        >
                            {item.resource_name || 'Unknown'}
                        </button>
                        <span className="ml-auto whitespace-nowrap text-[11px] text-slate-500" title={parseUTCDate(item.created_at).toLocaleString()}>
                            {parseUTCDate(item.created_at).toLocaleString()}
                            <span className="ml-1.5 opacity-60">· {formatDistanceToNow(parseUTCDate(item.created_at), { addSuffix: true })}</span>
                        </span>
                    </div>

                    {/* Body */}
                    {item.content_kind === 'diff' && item.changes.length > 0 ? (
                        <div className="mt-2 space-y-3 border-t border-slate-800/60 pt-2">
                            {item.changes.map((c) => <ChangeRow key={c.field} change={c} />)}
                        </div>
                    ) : item.content_kind === 'text' && item.content ? (
                        <div className="mt-2 max-h-80 overflow-auto rounded-md border border-slate-800/60 bg-slate-950/40 px-3 py-2">
                            <MarkdownPreview value={item.content} />
                        </div>
                    ) : item.details ? (
                        <div className="mt-1 text-xs text-slate-500">{item.details}</div>
                    ) : null}
                </div>
            </div>
        </div>
    );
}

export function ActivityFeedTab({ engagementId }: { engagementId: string }) {
    const [search, setSearch] = useState('');
    const debouncedSearch = useDebounce(search, 500);
    const [types, setTypes] = useState<string[]>([]);
    const [itemIds, setItemIds] = useState<string[]>([]);
    const [actionCategories, setActionCategories] = useState<string[]>([]);
    const [userIds, setUserIds] = useState<string[]>([]);
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [includeAll, setIncludeAll] = useState(false);
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
    const [page, setPage] = useState(1);
    const queryClient = useQueryClient();

    useEffect(() => {
        setPage(1);
    }, [debouncedSearch, types, itemIds, actionCategories, userIds, dateFrom, dateTo, includeAll, sortOrder]);

    useCollaboration({
        resourceType: 'engagement',
        resourceId: engagementId,
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                queryClient.invalidateQueries({ queryKey: ['engagement-feed', engagementId] });
            }
        },
    });

    const { data: engagement } = useQuery({
        queryKey: ['engagement', engagementId],
        queryFn: async () => (await api.get(`/engagements/${engagementId}`)).data,
    });

    const { data, isLoading } = useQuery({
        queryKey: ['engagement-feed', engagementId, debouncedSearch, types, itemIds, actionCategories, userIds, dateFrom, dateTo, includeAll, sortOrder, page],
        refetchOnMount: 'always',
        queryFn: async () => {
            const params = new URLSearchParams();
            params.append('engagement_id', engagementId);
            if (debouncedSearch) params.append('search', debouncedSearch);
            if (types.length) params.append('resource_types', types.join(','));
            if (itemIds.length) params.append('resource_ids', itemIds.join(','));
            if (actionCategories.length) params.append('action_categories', actionCategories.join(','));
            if (userIds.length) params.append('user_ids', userIds.join(','));
            if (dateFrom) params.append('date_from', `${dateFrom}T00:00:00`);
            if (dateTo) params.append('date_to', `${dateTo}T23:59:59`);
            if (includeAll) params.append('include_all', 'true');
            params.append('sort_order', sortOrder);
            params.append('limit', String(PAGE_SIZE));
            params.append('offset', String((page - 1) * PAGE_SIZE));
            const res = await api.get<{ items: FeedItem[]; total: number }>(`/discussions/activity/feed?${params.toString()}`);
            return res.data;
        },
    });

    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const hasFilters = !!debouncedSearch || types.length > 0 || itemIds.length > 0 || actionCategories.length > 0 ||
        userIds.length > 0 || !!dateFrom || !!dateTo || includeAll;
    const clearFilters = () => {
        setSearch(''); setTypes([]); setItemIds([]); setActionCategories([]); setUserIds([]);
        setDateFrom(''); setDateTo(''); setIncludeAll(false);
    };

    const typeOptions = TYPE_OPTIONS.map((o) => ({
        value: o.value, label: o.label,
        icon: resourceTypeIcons[o.value], badgeClass: resourceTypeColors[o.value],
    }));

    const userOptions = (engagement?.assigned_users || []).map((u: any) => ({
        value: u.id, label: displayName(u), sublabel: `@${u.username}`,
        avatar: { id: u.id, full_name: u.full_name, username: u.username, profile_photo: u.profile_photo },
    }));

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader>
                <CardTitle className="text-white">Activity Feed</CardTitle>
                <CardDescription>Everything operators have posted in this engagement — comments, notes, findings, test cases and more, with edit diffs.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Filter bar */}
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800/50 bg-slate-950/30 p-3">
                    <div className="flex min-w-[180px] flex-1 items-center gap-2">
                        <Search className="h-4 w-4 shrink-0 text-slate-500" />
                        <Input
                            placeholder="Search content…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="h-8 border-none bg-transparent px-0 text-sm placeholder:text-slate-600 focus-visible:ring-0"
                        />
                    </div>

                    {/* Type multi-select (searchable, colour-coded per type) */}
                    <MultiSelectFilter
                        label="All types" icon={Filter} countNoun="type"
                        options={typeOptions} selected={types} onChange={setTypes}
                        searchPlaceholder="Search types…"
                    />

                    {/* Specific-item multi-select */}
                    <FeedItemPicker engagementId={engagementId} selected={itemIds} onChange={setItemIds} />

                    {/* Action multi-select */}
                    <MultiSelectFilter
                        label="All actions" countNoun="action" searchable={false}
                        options={ACTION_OPTIONS} selected={actionCategories} onChange={setActionCategories}
                    />

                    {/* User multi-select (searchable) */}
                    <MultiSelectFilter
                        label="All users" icon={UserIcon} countNoun="user"
                        options={userOptions} selected={userIds} onChange={setUserIds}
                        searchPlaceholder="Search users…"
                    />

                    {/* Date range — presets + custom, collapsed into one button */}
                    <DateRangeFilter
                        from={dateFrom} to={dateTo}
                        onChange={(f, t) => { setDateFrom(f); setDateTo(t); }}
                    />

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

                    <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400" title="Include non-content events (status changes, imports, settings…)">
                        <Switch checked={includeAll} onCheckedChange={setIncludeAll} />
                        All events
                    </label>

                    {hasFilters && (
                        <Button variant="ghost" size="sm" onClick={clearFilters} className="h-8 gap-1 text-xs text-slate-400 hover:text-white">
                            <X className="h-3 w-3" /> Clear
                        </Button>
                    )}
                </div>

                {/* Feed */}
                {isLoading ? (
                    <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
                ) : items.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-800 py-12 text-center">
                        <History className="mx-auto mb-4 h-12 w-12 text-slate-600 opacity-20" />
                        <p className="text-slate-500">No activity matches your criteria.</p>
                    </div>
                ) : (
                    <div className="space-y-2">
                        {items.map((item) => <FeedCard key={item.id} item={item} engagementId={engagementId} />)}
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
            </CardContent>
        </Card>
    );
}

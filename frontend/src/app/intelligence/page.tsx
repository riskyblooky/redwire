/**
 * intelligence/page.tsx — Threat Intelligence Hub
 *
 * Tabbed view for managing threat-intel items and RSS/Atom/JSON feed
 * sources. Features:
 *  - **Intel Items tab**: paginated card grid with search, type, and
 *    severity filters. Each `IntelCard` shows title, CVE badge, severity
 *    badge, type badge, source, published time, linked-entity count, and
 *    a delete action. Clicking opens `IntelDetailDialog`.
 *  - **Feed Sources tab**: list of configured feeds with active/disabled
 *    badge, last-fetched timestamp, type badge, and delete button.
 *  - Create Intel dialog: rich-text (TipTap) content, type + severity
 *    selectors, CVE ID, source URL, and multi-file attachment upload.
 *  - Add Feed dialog: name, URL, and feed type (RSS/Atom/JSON).
 *  - "Refresh Feeds" action fetches new items from all enabled feeds.
 *  - Permission-gated create, delete, and feed-management actions.
 *  - Live WebSocket updates invalidate queries on intel_item / intel_feed
 *    activity events.
 *
 * Helper components: `IntelCard`, `IntelDetailDialog` (shared).
 * Utility: `formatTimeAgo` — human-readable relative timestamps.
 */
'use client';

import { useState } from 'react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import TiptapEditor from '@/components/ui/tiptap-editor';
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
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import {
    Radar,
    Plus,
    Search,
    ExternalLink,
    RefreshCw,
    Loader2,
    Shield,
    AlertTriangle,
    Bug,
    FileText,
    Newspaper,
    Trash2,
    Link2,
    Rss,
    Globe,
    Clock,
    ChevronRight,
    ChevronLeft,
    Zap,
    BookOpen,
    Paperclip,
} from 'lucide-react';
import { toast } from 'sonner';
import {
    useIntelItems,
    useCreateIntelItem,
    useDeleteIntelItem,
    useIntelItem,
    useIntelFeeds,
    useCreateIntelFeed,
    useDeleteIntelFeed,
    useRefreshFeeds,
    useLinkIntel,
    useUnlinkIntel,
    useUploadIntelAttachment,
    type IntelItem,
    type IntelItemDetail,
} from '@/lib/hooks/use-intel';
import { IntelDetailDialog, INTEL_TYPE_CONFIG as TYPE_CONFIG, INTEL_SEVERITY_CONFIG as SEVERITY_CONFIG } from '@/components/intel/intel-detail-dialog';
import { useGlobalPermission } from '@/lib/hooks/use-permissions';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { useQueryClient } from '@tanstack/react-query';
import { apiErrorMessage } from '@/lib/api';

// ── Constants ───────────────────────────────────────────────────


function formatTimeAgo(dateStr?: string): string {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 30) return `${diffDays}d ago`;
    return date.toLocaleDateString();
}

// ── Main Page ───────────────────────────────────────────────────

export default function IntelligencePage() {
    const [activeTab, setActiveTab] = useState<'items' | 'feeds'>('items');
    const [search, setSearch] = useState('');
    const [typeFilter, setTypeFilter] = useState<string>('');
    const [severityFilter, setSeverityFilter] = useState<string>('');
    const [createDialogOpen, setCreateDialogOpen] = useState(false);
    const [detailItem, setDetailItem] = useState<string | null>(null);
    const [addFeedOpen, setAddFeedOpen] = useState(false);
    const [page, setPage] = useState(0);
    const PAGE_SIZE = 50;
    const queryClient = useQueryClient();

    // ── Live updates via WebSocket ───────────────────────────────
    useCollaboration({
        resourceType: 'dashboard', resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                const rt = (data.resource_type || '').toLowerCase();
                if (rt === 'intel_item' || rt === 'intel_feed') {
                    queryClient.invalidateQueries({ queryKey: ['intel-items'] });
                    queryClient.invalidateQueries({ queryKey: ['intel-feeds'] });
                }
            }
        },
    });

    const { data: intelTypes = [] } = useConfigurableTypes('intel');

    // Data
    const { data: itemsData, isLoading: itemsLoading } = useIntelItems({
        search: search || undefined,
        item_type: typeFilter || undefined,
        severity: severityFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
    });
    const items = itemsData?.items ?? [];
    const totalItems = itemsData?.total ?? 0;
    const totalPages = Math.ceil(totalItems / PAGE_SIZE);
    const { data: feeds = [], isLoading: feedsLoading } = useIntelFeeds();
    const refreshFeeds = useRefreshFeeds();
    const createItem = useCreateIntelItem();
    const deleteItem = useDeleteIntelItem();
    const createFeed = useCreateIntelFeed();
    const deleteFeed = useDeleteIntelFeed();
    const uploadAttachment = useUploadIntelAttachment();

    // Permissions
    const canCreate = useGlobalPermission('intel_create');
    const canDelete = useGlobalPermission('intel_delete');
    const canManageFeeds = useGlobalPermission('intel_manage_feeds');
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // Create form state
    const [newItem, setNewItem] = useState({
        title: '', content: '', source_url: '', item_type: 'OTHER', severity: '', cve_id: '',
    });
    const [pendingFiles, setPendingFiles] = useState<File[]>([]);

    const handleCreateItem = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            const created = await createItem.mutateAsync({
                ...newItem,
                severity: newItem.severity || undefined,
                cve_id: newItem.cve_id || undefined,
            });
            // Upload pending files if any
            if (pendingFiles.length > 0 && created.id) {
                try {
                    await uploadAttachment.mutateAsync({ itemId: created.id, files: pendingFiles });
                } catch {
                    toast.error('Item created but file upload failed');
                }
            }
            toast.success('Intel item created');
            setCreateDialogOpen(false);
            setNewItem({ title: '', content: '', source_url: '', item_type: 'OTHER', severity: '', cve_id: '' });
            setPendingFiles([]);
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Failed to create intel item'));
        }
    };

    // Feed form state
    const [newFeed, setNewFeed] = useState({ name: '', url: '', feed_type: 'RSS' });

    const handleCreateFeed = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createFeed.mutateAsync(newFeed);
            toast.success('Feed added');
            setAddFeedOpen(false);
            setNewFeed({ name: '', url: '', feed_type: 'RSS' });
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Failed to add feed'));
        }
    };

    const handleRefresh = async () => {
        try {
            const result = await refreshFeeds.mutateAsync();
            toast.success(`Fetched ${result.new_items} new items from ${result.feeds_processed} feeds`);
        } catch (err: any) {
            toast.error('Failed to refresh feeds');
        }
    };

    const tabs = [
        { key: 'items' as const, label: 'Intel Items', count: totalItems },
        { key: 'feeds' as const, label: 'Feed Sources', count: feeds.length },
    ];

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-xl bg-primary/10 border border-primary/20">
                            <Radar className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-white">Intelligence</h1>
                            <p className="text-slate-400 text-sm">Threat intel, CVEs, advisories, and security research</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {canManageFeeds && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleRefresh}
                            disabled={refreshFeeds.isPending}
                            className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5"
                        >
                            {refreshFeeds.isPending ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <RefreshCw className="h-4 w-4" />
                            )}
                            Refresh Feeds
                        </Button>
                        )}
                        {canCreate && (
                        <Button
                            size="sm"
                            onClick={() => setCreateDialogOpen(true)}
                            className="bg-primary hover:bg-primary/90 text-white gap-1.5"
                        >
                            <Plus className="h-4 w-4" />
                            Add Intel
                        </Button>
                        )}
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex gap-1 bg-slate-900/50 border border-slate-800 rounded-lg p-1 w-fit">
                    {tabs.map(tab => (
                        <button
                            key={tab.key}
                            onClick={() => setActiveTab(tab.key)}
                            className={`px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${
                                activeTab === tab.key
                                    ? 'bg-primary/15 text-primary shadow-sm'
                                    : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                            }`}
                        >
                            {tab.label}
                            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                                activeTab === tab.key ? 'bg-primary/20 text-primary' : 'bg-slate-700/50 text-slate-500'
                            }`}>
                                {tab.count}
                            </span>
                        </button>
                    ))}
                </div>

                {/* ── Intel Items Tab ─────────────────────────────── */}
                {activeTab === 'items' && (
                    <div className="space-y-4">
                        {/* Filters */}
                        <div className="flex items-center gap-3">
                            <div className="relative flex-1 max-w-md">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                <Input
                                    value={search}
                                    onChange={e => { setSearch(e.target.value); setPage(0); }}
                                    placeholder="Search intel items, CVEs..."
                                    className="pl-9 bg-slate-900/50 border-slate-800 text-white h-9"
                                />
                            </div>
                            <Select value={typeFilter} onValueChange={v => { setTypeFilter(v === 'ALL' ? '' : v); setPage(0); }}>
                                <SelectTrigger className="w-36 bg-slate-900/50 border-slate-800 text-white h-9">
                                    <SelectValue placeholder="Type" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="ALL">All Types</SelectItem>
                                    {intelTypes.map(t => (
                                        <SelectItem key={t.name} value={t.name}>{t.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <Select value={severityFilter} onValueChange={v => { setSeverityFilter(v === 'ALL' ? '' : v); setPage(0); }}>
                                <SelectTrigger className="w-36 bg-slate-900/50 border-slate-800 text-white h-9">
                                    <SelectValue placeholder="Severity" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="ALL">All Severities</SelectItem>
                                    <SelectItem value="CRITICAL">Critical</SelectItem>
                                    <SelectItem value="HIGH">High</SelectItem>
                                    <SelectItem value="MEDIUM">Medium</SelectItem>
                                    <SelectItem value="LOW">Low</SelectItem>
                                    <SelectItem value="INFO">Info</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Items Grid */}
                        {itemsLoading ? (
                            <div className="flex items-center justify-center py-20">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            </div>
                        ) : items.length === 0 ? (
                            <Card className="border-slate-800 bg-slate-900/30">
                                <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                                    <Radar className="h-12 w-12 text-slate-700 mb-3" />
                                    <p className="text-slate-400 font-medium">No intel items yet</p>
                                    <p className="text-slate-500 text-sm mt-1">Click &ldquo;Refresh Feeds&rdquo; to fetch from configured RSS sources, or create one manually.</p>
                                </CardContent>
                            </Card>
                        ) : (
                            <div className="grid gap-3">
                                {items.map(item => (
                                    <IntelCard
                                        key={item.id}
                                        item={item}
                                        onView={() => setDetailItem(item.id)}
                                        onDelete={async () => {
                                            const ok = await confirm({
                                                title: 'Delete Intel Item',
                                                description: `Are you sure you want to delete "${item.title}"? This will also remove all attachments and linked entities.`,
                                                confirmLabel: 'Delete',
                                                variant: 'destructive',
                                            });
                                            if (!ok) return;
                                            await deleteItem.mutateAsync(item.id);
                                            toast.success('Deleted');
                                        }}
                                        canDelete={canDelete}
                                    />
                                ))}
                            </div>
                        )}

                        {/* Pagination */}
                        {totalPages > 1 && (
                            <div className="flex items-center justify-between pt-2">
                                <p className="text-xs text-slate-500">
                                    Showing {page * PAGE_SIZE + 1}&ndash;{Math.min((page + 1) * PAGE_SIZE, totalItems)} of {totalItems} items
                                </p>
                                <div className="flex items-center gap-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        disabled={page === 0}
                                        onClick={() => setPage(p => p - 1)}
                                        className="border-slate-700 text-slate-300 hover:bg-slate-800 h-8 gap-1"
                                    >
                                        <ChevronLeft className="h-4 w-4" /> Previous
                                    </Button>
                                    <span className="text-xs text-slate-400 px-2">
                                        Page {page + 1} of {totalPages}
                                    </span>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        disabled={page >= totalPages - 1}
                                        onClick={() => setPage(p => p + 1)}
                                        className="border-slate-700 text-slate-300 hover:bg-slate-800 h-8 gap-1"
                                    >
                                        Next <ChevronRight className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* ── Feeds Config Tab ────────────────────────────── */}
                {activeTab === 'feeds' && (
                    <div className="space-y-4">
                        {canManageFeeds && (
                        <div className="flex justify-end">
                            <Button size="sm" onClick={() => setAddFeedOpen(true)} className="bg-primary hover:bg-primary/90 text-white gap-1.5">
                                <Plus className="h-4 w-4" /> Add Feed
                            </Button>
                        </div>
                        )}

                        {feedsLoading ? (
                            <div className="flex items-center justify-center py-20">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            </div>
                        ) : (
                            <div className="grid gap-3">
                                {feeds.map(feed => (
                                    <Card key={feed.id} className="border-slate-800 bg-slate-900/50">
                                        <CardContent className="flex items-center justify-between p-4">
                                            <div className="flex items-center gap-3">
                                                <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                                                    <Rss className="h-4 w-4 text-cyan-400" />
                                                </div>
                                                <div>
                                                    <p className="text-sm font-medium text-white">{feed.name}</p>
                                                    <p className="text-xs text-slate-500 truncate max-w-md">{feed.url}</p>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-3">
                                                <Badge className={`text-[10px] ${feed.enabled ? 'bg-green-500/15 text-green-400 border-green-500/30' : 'bg-slate-700 text-slate-500'}`}>
                                                    {feed.enabled ? 'Active' : 'Disabled'}
                                                </Badge>
                                                {feed.last_fetched_at && (
                                                    <span className="text-xs text-slate-500 flex items-center gap-1">
                                                        <Clock className="h-3 w-3" />
                                                        {formatTimeAgo(feed.last_fetched_at)}
                                                    </span>
                                                )}
                                                <Badge className="text-[10px] bg-slate-800 text-slate-400 border-slate-700">
                                                    {feed.feed_type}
                                                </Badge>
                                                {canManageFeeds && (
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-8 w-8 text-slate-500 hover:text-red-400 hover:bg-red-500/10"
                                                    onClick={async () => {
                                                        await deleteFeed.mutateAsync(feed.id);
                                                        toast.success('Feed removed');
                                                    }}
                                                >
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </Button>
                                                )}
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ── Create Intel Dialog ─────────────────────────────── */}
            <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-2xl">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Radar className="h-5 w-5 text-cyan-400" />
                            Add Intel Item
                        </DialogTitle>
                        <DialogDescription>Create a manual intelligence entry</DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleCreateItem} className="space-y-4">
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Title *</Label>
                            <Input
                                value={newItem.title}
                                onChange={e => setNewItem({ ...newItem, title: e.target.value })}
                                required
                                className="bg-slate-800/50 border-slate-700 text-white"
                                placeholder="e.g. CVE-2024-1234: Critical RCE in..."
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">Type</Label>
                                <Select value={newItem.item_type} onValueChange={v => setNewItem({ ...newItem, item_type: v })}>
                                    <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {intelTypes.map(t => (
                                            <SelectItem key={t.name} value={t.name}>{t.name}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">Severity</Label>
                                <Select value={newItem.severity} onValueChange={v => setNewItem({ ...newItem, severity: v })}>
                                    <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                        <SelectValue placeholder="Optional" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="CRITICAL">Critical</SelectItem>
                                        <SelectItem value="HIGH">High</SelectItem>
                                        <SelectItem value="MEDIUM">Medium</SelectItem>
                                        <SelectItem value="LOW">Low</SelectItem>
                                        <SelectItem value="INFO">Info</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">CVE ID</Label>
                            <Input
                                value={newItem.cve_id}
                                onChange={e => setNewItem({ ...newItem, cve_id: e.target.value })}
                                className="bg-slate-800/50 border-slate-700 text-white"
                                placeholder="CVE-2024-1234 (optional)"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Source URL</Label>
                            <Input
                                value={newItem.source_url}
                                onChange={e => setNewItem({ ...newItem, source_url: e.target.value })}
                                className="bg-slate-800/50 border-slate-700 text-white"
                                placeholder="https://..."
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Content / Notes</Label>
                            <TiptapEditor
                                value={newItem.content}
                                onChange={(val) => setNewItem({ ...newItem, content: val })}
                                placeholder="Description, impact, notes..."
                                minHeight="150px"
                                className="bg-slate-800/50 border-slate-700"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Attachments</Label>
                            <div className="flex items-center gap-2">
                                <label className="flex items-center gap-2 px-3 py-2 rounded-md border border-dashed border-slate-700 bg-slate-800/30 hover:bg-slate-800/50 cursor-pointer transition-colors text-sm text-slate-400 flex-1">
                                    <Paperclip className="h-4 w-4" />
                                    {pendingFiles.length > 0 ? `${pendingFiles.length} file(s) selected` : 'Choose files...'}
                                    <input
                                        type="file"
                                        multiple
                                        className="hidden"
                                        onChange={e => {
                                            if (e.target.files) setPendingFiles(Array.from(e.target.files));
                                        }}
                                    />
                                </label>
                                {pendingFiles.length > 0 && (
                                    <Button type="button" variant="ghost" size="sm" className="text-slate-500 hover:text-red-400 h-8" onClick={() => setPendingFiles([])}>
                                        Clear
                                    </Button>
                                )}
                            </div>
                            {pendingFiles.length > 0 && (
                                <div className="text-xs text-slate-500 space-y-0.5">
                                    {pendingFiles.map((f, i) => (
                                        <div key={i} className="truncate">{f.name} ({(f.size / 1024).toFixed(0)} KB)</div>
                                    ))}
                                </div>
                            )}
                        </div>
                        <div className="flex justify-end gap-2 pt-2">
                            <Button type="button" variant="outline" onClick={() => setCreateDialogOpen(false)} className="border-slate-700 text-slate-300 hover:bg-slate-800">Cancel</Button>
                            <Button type="submit" disabled={createItem.isPending} className="bg-primary hover:bg-primary/90 text-white">
                                {createItem.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Creating...</> : 'Create'}
                            </Button>
                        </div>
                    </form>
                </DialogContent>
            </Dialog>

            {/* ── Add Feed Dialog ─────────────────────────────────── */}
            <Dialog open={addFeedOpen} onOpenChange={setAddFeedOpen}>
                <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Rss className="h-5 w-5 text-cyan-400" />
                            Add RSS Feed
                        </DialogTitle>
                        <DialogDescription>Add a new intelligence feed source</DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleCreateFeed} className="space-y-4">
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Feed Name *</Label>
                            <Input
                                value={newFeed.name}
                                onChange={e => setNewFeed({ ...newFeed, name: e.target.value })}
                                required
                                className="bg-slate-800/50 border-slate-700 text-white"
                                placeholder="e.g. SecurityWeek"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Feed URL *</Label>
                            <Input
                                value={newFeed.url}
                                onChange={e => setNewFeed({ ...newFeed, url: e.target.value })}
                                required
                                className="bg-slate-800/50 border-slate-700 text-white"
                                placeholder="https://example.com/feed.xml"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Feed Type</Label>
                            <Select value={newFeed.feed_type} onValueChange={v => setNewFeed({ ...newFeed, feed_type: v })}>
                                <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="RSS">RSS</SelectItem>
                                    <SelectItem value="ATOM">Atom</SelectItem>
                                    <SelectItem value="JSON">JSON</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="flex justify-end gap-2 pt-2">
                            <Button type="button" variant="outline" onClick={() => setAddFeedOpen(false)} className="border-slate-700 text-slate-300 hover:bg-slate-800">Cancel</Button>
                            <Button type="submit" disabled={createFeed.isPending} className="bg-primary hover:bg-primary/90 text-white">
                                {createFeed.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Adding...</> : 'Add Feed'}
                            </Button>
                        </div>
                    </form>
                </DialogContent>
            </Dialog>

            {/* ── Item Detail Dialog ──────────────────────────────── */}
            {detailItem && (
                <IntelDetailDialog itemId={detailItem} onClose={() => setDetailItem(null)} />
            )}
            <ConfirmDialog />
        </DashboardLayout>
    );
}


// ── Intel Card Component ────────────────────────────────────────

function IntelCard({ item, onView, onDelete, canDelete = false }: { item: IntelItem; onView: () => void; onDelete: () => void; canDelete?: boolean }) {
    const typeConf = TYPE_CONFIG[item.item_type] || TYPE_CONFIG.OTHER;
    const TypeIcon = typeConf.icon;

    return (
        <Card className="border-slate-800 bg-slate-900/50 hover:bg-slate-900/80 transition-colors group cursor-pointer" onClick={onView}>
            <CardContent className="flex items-start justify-between p-4">
                <div className="flex items-start gap-3 min-w-0 flex-1">
                    <div className={`p-2 rounded-lg border ${typeConf.color} shrink-0 mt-0.5`}>
                        <TypeIcon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <h3 className="text-sm font-semibold text-white truncate max-w-lg">{item.title}</h3>
                            {item.cve_id && (
                                <Badge className="text-[10px] py-0 bg-red-500/10 text-red-400 border-red-500/30 font-mono shrink-0">
                                    {item.cve_id}
                                </Badge>
                            )}
                        </div>
                        {item.content && (
                            <p className="text-xs text-slate-400 line-clamp-2 mb-2">{item.content}</p>
                        )}
                        <div className="flex items-center gap-3 text-[11px] text-slate-500">
                            {item.source && (
                                <span className="flex items-center gap-1">
                                    <Globe className="h-3 w-3" />
                                    {item.source}
                                </span>
                            )}
                            {(item.published_at || item.created_at) && (
                                <span className="flex items-center gap-1">
                                    <Clock className="h-3 w-3" />
                                    {formatTimeAgo(item.published_at || item.created_at)}
                                </span>
                            )}
                            {item.linked_count > 0 && (
                                <span className="flex items-center gap-1 text-cyan-500">
                                    <Link2 className="h-3 w-3" />
                                    {item.linked_count} linked
                                </span>
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-3">
                    {item.severity && SEVERITY_CONFIG[item.severity] && (
                        <Badge className={`text-[10px] py-0 ${SEVERITY_CONFIG[item.severity].color}`}>
                            {SEVERITY_CONFIG[item.severity].label}
                        </Badge>
                    )}
                    <Badge className={`text-[10px] py-0 ${typeConf.color}`}>
                        {typeConf.label}
                    </Badge>
                    {item.source_url && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-slate-500 hover:text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity"
                            onClick={e => { e.stopPropagation(); window.open(item.source_url, '_blank'); }}
                        >
                            <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                    )}
                    {canDelete && (
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={e => { e.stopPropagation(); onDelete(); }}
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                    )}
                    <ChevronRight className="h-4 w-4 text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
            </CardContent>
        </Card>
    );
}


// ── Detail Dialog ───────────────────────────────────────────────



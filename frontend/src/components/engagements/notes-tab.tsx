'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import {
    useNotes, useCreateNote, useUpdateNote, useDeleteNote, Note,
    useLinkNoteToFinding, useUnlinkNoteFromFinding,
    useLinkNoteToTestCase, useUnlinkNoteFromTestCase,
    useLinkNoteToAsset, useUnlinkNoteFromAsset,
    useLinkNoteToVaultItem, useUnlinkNoteFromVaultItem,
    useLinkNoteToCleanupArtifact, useUnlinkNoteFromCleanupArtifact,
} from '@/lib/hooks/use-notes';
import { usePermission, useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
    Plus, Trash2, FileText, Loader2, Search,
    Clock, User as UserIcon, StickyNote, PenLine, ChevronLeft,
    Link as LinkIcon, X, Bug, Target, Server, Key, Trash, ExternalLink, Radar,
    ChevronRight, ChevronDown, Filter, CalendarDays, CornerDownRight,
} from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import dynamic from 'next/dynamic';
const CollaborativeEditor = dynamic(() => import('@/components/ui/collaborative-editor'), {
    ssr: false,
    loading: () => <div className="h-[300px] w-full bg-slate-900/50 animate-pulse rounded-lg border border-slate-800" />,
});
import { useAuthStore } from '@/stores/auth-store';
import { LinkNoteDialog } from '@/components/ui/link-note-dialog';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { UserAvatar } from '@/components/ui/user-avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useIntelByEntity, useUnlinkIntel } from '@/lib/hooks/use-intel';
import { useInfraByEntity, useUnlinkInfra } from '@/lib/hooks/use-infra';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';

interface NotesTabProps {
    engagementId: string;
    initialNoteId?: string | null;
}

export function NotesTab({ engagementId, initialNoteId }: NotesTabProps) {
    const { data: notes = [], isLoading } = useNotes(engagementId);
    const createNote = useCreateNote();
    const updateNote = useUpdateNote();
    const deleteNote = useDeleteNote();
    const queryClient = useQueryClient();
    const { user: currentUser } = useAuthStore();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const router = useRouter();
    const pathname = usePathname();
    const searchParams = useSearchParams();

    // Link/unlink hooks
    const linkToFinding = useLinkNoteToFinding();
    const unlinkFromFinding = useUnlinkNoteFromFinding();
    const linkToTestCase = useLinkNoteToTestCase();
    const unlinkFromTestCase = useUnlinkNoteFromTestCase();
    const linkToAsset = useLinkNoteToAsset();
    const unlinkFromAsset = useUnlinkNoteFromAsset();
    const linkToVaultItem = useLinkNoteToVaultItem();
    const unlinkFromVaultItem = useUnlinkNoteFromVaultItem();
    const linkToCleanupArtifact = useLinkNoteToCleanupArtifact();
    const unlinkFromCleanupArtifact = useUnlinkNoteFromCleanupArtifact();

    const [isLinkDialogOpen, setIsLinkDialogOpen] = useState(false);

    const canView = usePermission(engagementId, 'note_view');
    const canCreate = usePermission(engagementId, 'note_create');

    const [selectedNoteId, setSelectedNoteId] = useState<string | null>(initialNoteId || null);
    const hasAutoSelected = useRef(false);

    // Intel linked to the selected note
    const { data: linkedIntel = [] } = useIntelByEntity('note', selectedNoteId || '');
    const unlinkIntel = useUnlinkIntel();

    // Infra linked to the selected note
    const { data: linkedInfra = [] } = useInfraByEntity('note', selectedNoteId || '');
    const unlinkInfra = useUnlinkInfra();

    // Auto-select note from URL param when notes load
    useEffect(() => {
        if (initialNoteId && !hasAutoSelected.current && notes.length > 0) {
            const noteExists = notes.find(n => n.id === initialNoteId);
            if (noteExists) {
                setSelectedNoteId(initialNoteId);
                hasAutoSelected.current = true;
            }
        }
    }, [initialNoteId, notes]);

    // Update URL when selecting a note
    const handleSelectNote = useCallback((noteId: string | null) => {
        setSelectedNoteId(noteId);
        const params = new URLSearchParams(searchParams?.toString() || "");
        if (noteId) {
            params.set('noteId', noteId);
        } else {
            params.delete('noteId');
        }
        router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    }, [searchParams, pathname, router]);
    const [editTitle, setEditTitle] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [isCreating, setIsCreating] = useState(false);
    const [creatingParentId, setCreatingParentId] = useState<string | null>(null);
    const [newTitle, setNewTitle] = useState('');
    const [isTitleSaving, setIsTitleSaving] = useState(false);
    const [showSidebar, setShowSidebar] = useState(true);
    const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

    // Filters
    const [filterTime, setFilterTime] = useState<string>('all');
    const [filterUser, setFilterUser] = useState<string>('all');
    const [filterAsset, setFilterAsset] = useState<string>('all');
    const [showFilters, setShowFilters] = useState(false);

    const activeFilterCount = [filterTime !== 'all', filterUser !== 'all', filterAsset !== 'all'].filter(Boolean).length;

    const titleSaveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const lastSavedTitleRef = useRef<string>('');

    const selectedNote = notes.find(n => n.id === selectedNoteId) || null;

    // Permission checks for the selected note
    const canEditNote = useCanEdit(engagementId, 'note', selectedNote?.created_by);
    const canDeleteNote = useCanDelete(engagementId, 'note', selectedNote?.created_by);

    // WebSocket: listen for note events on the engagement channel
    const selectedNoteIdRef = useRef<string | null>(null);
    selectedNoteIdRef.current = selectedNoteId;

    const handleWsMessage = useCallback((data: any) => {
        if (data.type === 'note_created' || data.type === 'note_updated' || data.type === 'note_deleted') {
            if (data.user_id !== currentUser?.id) {
                // Refresh the note list (sidebar) — content sync is handled by Y.js
                queryClient.invalidateQueries({ queryKey: ['notes', engagementId] }).then(() => {
                    if (data.type === 'note_updated' && data.note_id === selectedNoteIdRef.current) {
                        // Update title from fresh cache (content is Y.js-synced)
                        const freshNotes = queryClient.getQueryData<Note[]>(['notes', engagementId]);
                        const freshNote = freshNotes?.find(n => n.id === data.note_id);
                        if (freshNote) {
                            setEditTitle(freshNote.title);
                            lastSavedTitleRef.current = freshNote.title;
                        }
                    }
                });
                if (data.type === 'note_deleted' && data.note_id === selectedNoteIdRef.current) {
                    setSelectedNoteId(null);
                    toast.info('This note was deleted by another user.');
                }
            }
        }
    }, [currentUser?.id, engagementId, queryClient]);

    // Engagement-level WS: only for note CRUD events (create/update/delete)
    useCollaboration({
        resourceType: 'engagement',
        resourceId: engagementId,
        enabled: true,
        onMessage: handleWsMessage,
    });

    // Note-level WS: scoped presence — only shows users viewing THIS specific note
    const { activeUsers } = useCollaboration({
        resourceType: 'note',
        resourceId: selectedNoteId || '',
        enabled: !!selectedNoteId,
    });

    // Sync title when selected note changes
    useEffect(() => {
        if (selectedNote) {
            setEditTitle(selectedNote.title);
            lastSavedTitleRef.current = selectedNote.title;
        } else if (selectedNoteId) {
            setEditTitle('');
            lastSavedTitleRef.current = '';
        }
    }, [selectedNoteId, selectedNote?.id]); // eslint-disable-line react-hooks/exhaustive-deps

    // Debounced title save (content is synced via Y.js)
    const handleTitleChange = useCallback((value: string) => {
        setEditTitle(value);
        if (titleSaveTimeoutRef.current) clearTimeout(titleSaveTimeoutRef.current);
        titleSaveTimeoutRef.current = setTimeout(async () => {
            if (!selectedNoteId || value === lastSavedTitleRef.current) return;
            setIsTitleSaving(true);
            try {
                await updateNote.mutateAsync({ id: selectedNoteId, title: value });
                lastSavedTitleRef.current = value;
            } catch {
                toast.error('Failed to save title');
            } finally {
                setIsTitleSaving(false);
            }
        }, 1500);
    }, [selectedNoteId, updateNote]);

    // Flush pending title save on unmount or note switch
    useEffect(() => {
        return () => {
            if (titleSaveTimeoutRef.current) clearTimeout(titleSaveTimeoutRef.current);
        };
    }, [selectedNoteId]);

    const handleCreate = async () => {
        if (!newTitle.trim()) {
            toast.error('Please enter a title');
            return;
        }
        try {
            const created = await createNote.mutateAsync({
                engagementId,
                title: newTitle.trim(),
                content: '',
                parentId: creatingParentId,
            });
            // Title state is managed locally; content is handled by Y.js collaborative editor
            setEditTitle(created.title);
            lastSavedTitleRef.current = created.title;
            handleSelectNote(created.id);
            setIsCreating(false);
            setCreatingParentId(null);
            setNewTitle('');
            // Auto-expand parent if creating a sub-note
            if (creatingParentId) {
                setExpandedNodes(prev => new Set([...prev, creatingParentId]));
            }
            toast.success('Note created');
        } catch {
            toast.error('Failed to create note');
        }
    };

    const handleStartCreateSubNote = (parentId: string) => {
        setCreatingParentId(parentId);
        setIsCreating(true);
        setExpandedNodes(prev => new Set([...prev, parentId]));
    };

    const toggleExpand = (noteId: string) => {
        setExpandedNodes(prev => {
            const next = new Set(prev);
            if (next.has(noteId)) next.delete(noteId); else next.add(noteId);
            return next;
        });
    };

    const handleDelete = async (noteId: string, noteTitle: string) => {
        const ok = await confirm({
            title: 'Delete Note',
            description: `Are you sure you want to delete "${noteTitle}"? This cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        });
        if (!ok) return;

        try {
            await deleteNote.mutateAsync({ id: noteId, engagementId });
            if (selectedNoteId === noteId) {
                handleSelectNote(null);
            }
            toast.success('Note deleted');
        } catch {
            toast.error('Failed to delete note');
        }
    };

    const handleLink = async (resourceType: string, resourceId: string) => {
        if (!selectedNoteId) return;
        const args = { noteId: selectedNoteId, resourceId };
        switch (resourceType) {
            case 'findings': await linkToFinding.mutateAsync(args); break;
            case 'testcases': await linkToTestCase.mutateAsync(args); break;
            case 'assets': await linkToAsset.mutateAsync(args); break;
            case 'vault': await linkToVaultItem.mutateAsync(args); break;
            case 'cleanup': await linkToCleanupArtifact.mutateAsync(args); break;
        }
    };

    const handleUnlink = async (resourceType: string, resourceId: string) => {
        if (!selectedNoteId) return;
        const args = { noteId: selectedNoteId, resourceId };
        switch (resourceType) {
            case 'findings': await unlinkFromFinding.mutateAsync(args); break;
            case 'testcases': await unlinkFromTestCase.mutateAsync(args); break;
            case 'assets': await unlinkFromAsset.mutateAsync(args); break;
            case 'vault': await unlinkFromVaultItem.mutateAsync(args); break;
            case 'cleanup': await unlinkFromCleanupArtifact.mutateAsync(args); break;
        }
    };

    // ── Filtering logic ────────────────────────────────────────────
    const filteredNotes = notes.filter(n => {
        // Search filter
        if (searchQuery && !n.title.toLowerCase().includes(searchQuery.toLowerCase())) return false;
        // Time filter
        if (filterTime !== 'all') {
            const d = new Date(n.updated_at);
            const now = new Date();
            const diffMs = now.getTime() - d.getTime();
            const diffHours = diffMs / 3600000;
            if (filterTime === 'hour' && diffHours > 1) return false;
            if (filterTime === 'today' && diffHours > 24) return false;
            if (filterTime === 'week' && diffHours > 168) return false;
            if (filterTime === 'month' && diffHours > 720) return false;
        }
        // User filter
        if (filterUser !== 'all' && n.created_by !== filterUser) return false;
        // Asset filter
        if (filterAsset !== 'all') {
            const hasAsset = n.linked_assets?.some(a => a.id === filterAsset);
            if (!hasAsset) return false;
        }
        return true;
    });

    // ── Build tree ─────────────────────────────────────────────────

    const buildNoteTree = (notes: Note[]): NoteTreeItem[] => {
        const noteIds = new Set(notes.map(n => n.id));
        const map = new Map<string, NoteTreeItem>();
        notes.forEach(n => map.set(n.id, { ...n, children: [] }));
        const roots: NoteTreeItem[] = [];
        notes.forEach(n => {
            const node = map.get(n.id)!;
            // If parent is in the filtered set, nest under it; otherwise treat as root
            if (n.parent_id && noteIds.has(n.parent_id)) {
                map.get(n.parent_id)!.children.push(node);
            } else {
                roots.push(node);
            }
        });
        return roots;
    };

    const noteTree = buildNoteTree(filteredNotes);

    // Collect unique users for filter dropdown
    const uniqueUsers = Array.from(
        new Map(notes.map(n => [n.created_by, n.created_by_username || 'Unknown'])).entries()
    );

    // Collect unique linked assets for filter dropdown
    const uniqueAssets = Array.from(
        new Map(
            notes.flatMap(n => (n.linked_assets || []).map(a => [a.id, a.title]))
        ).entries()
    );

    const formatDate = (dateStr: string) => {
        const d = new Date(dateStr);
        const now = new Date();
        const diff = now.getTime() - d.getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `${days}d ago`;
        return d.toLocaleDateString();
    };

    const clearFilters = () => {
        setFilterTime('all');
        setFilterUser('all');
        setFilterAsset('all');
    };

    if (!canView) {
        return (
            <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                <StickyNote className="h-12 w-12 mb-4 opacity-50" />
                <p className="text-lg font-medium">Access Denied</p>
                <p className="text-sm">You don't have permission to view notes.</p>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-teal-500" />
            </div>
        );
    }

    return (
        <div className="flex h-[calc(100vh-340px)] min-h-[300px] gap-4 animate-in fade-in slide-in-from-bottom-2 duration-500 overflow-hidden">
            <ConfirmDialog />

            {/* Sidebar - Note list */}
            <div className={cn(
                "flex flex-col border border-slate-800/60 rounded-xl bg-slate-950/40 backdrop-blur-md overflow-hidden transition-all duration-300",
                showSidebar ? "w-80 min-w-[280px]" : "w-0 min-w-0 border-0 opacity-0 pointer-events-none"
            )}>
                {/* Sidebar header */}
                <div className="p-3 border-b border-slate-800/60 space-y-2">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                            <StickyNote className="h-4 w-4 text-teal-400" />
                            Notes
                            <Badge variant="secondary" className="bg-teal-500/20 text-teal-400 border-none px-1.5 h-4 text-[10px]">
                                {notes.length}
                            </Badge>
                        </h3>
                        <div className="flex items-center gap-0.5">
                            {/* Filter button */}
                            <Popover open={showFilters} onOpenChange={setShowFilters}>
                                <PopoverTrigger asChild>
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        className={cn(
                                            "h-7 w-7 p-0 relative overflow-visible",
                                            activeFilterCount > 0
                                                ? 'text-amber-400 hover:text-amber-300 hover:bg-amber-500/10'
                                                : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
                                        )}
                                    >
                                        <Filter className="h-3.5 w-3.5" />
                                        {activeFilterCount > 0 && (
                                            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-amber-500 text-[8px] font-bold text-black flex items-center justify-center">
                                                {activeFilterCount}
                                            </span>
                                        )}
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent align="start" className="w-60 p-3 bg-slate-900 border-slate-700 space-y-3">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-semibold text-slate-300">Filters</span>
                                        {activeFilterCount > 0 && (
                                            <button onClick={clearFilters} className="text-[10px] text-slate-500 hover:text-white">
                                                Clear all
                                            </button>
                                        )}
                                    </div>

                                    {/* Time filter */}
                                    <div className="space-y-1">
                                        <label className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                                            <CalendarDays className="h-3 w-3" /> Time
                                        </label>
                                        <select
                                            value={filterTime}
                                            onChange={e => setFilterTime(e.target.value)}
                                            className="w-full h-7 text-xs bg-slate-800 border border-slate-700 rounded-md text-white px-2"
                                        >
                                            <option value="all">All time</option>
                                            <option value="hour">Last hour</option>
                                            <option value="today">Today</option>
                                            <option value="week">This week</option>
                                            <option value="month">This month</option>
                                        </select>
                                    </div>

                                    {/* User filter */}
                                    {uniqueUsers.length > 1 && (
                                        <div className="space-y-1">
                                            <label className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                                                <UserIcon className="h-3 w-3" /> Author
                                            </label>
                                            <select
                                                value={filterUser}
                                                onChange={e => setFilterUser(e.target.value)}
                                                className="w-full h-7 text-xs bg-slate-800 border border-slate-700 rounded-md text-white px-2"
                                            >
                                                <option value="all">All users</option>
                                                {uniqueUsers.map(([id, name]) => (
                                                    <option key={id} value={id}>{name}</option>
                                                ))}
                                            </select>
                                        </div>
                                    )}

                                    {/* Asset filter */}
                                    {uniqueAssets.length > 0 && (
                                        <div className="space-y-1">
                                            <label className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                                                <Server className="h-3 w-3" /> Linked Asset
                                            </label>
                                            <select
                                                value={filterAsset}
                                                onChange={e => setFilterAsset(e.target.value)}
                                                className="w-full h-7 text-xs bg-slate-800 border border-slate-700 rounded-md text-white px-2"
                                            >
                                                <option value="all">All assets</option>
                                                {uniqueAssets.map(([id, name]) => (
                                                    <option key={id} value={id}>{name}</option>
                                                ))}
                                            </select>
                                        </div>
                                    )}
                                </PopoverContent>
                            </Popover>

                            {canCreate && (
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-7 px-2 text-teal-400 hover:text-teal-300 hover:bg-teal-500/10"
                                    onClick={() => { setCreatingParentId(null); setIsCreating(true); }}
                                >
                                    <Plus className="h-4 w-4" />
                                </Button>
                            )}
                        </div>
                    </div>

                    {/* Active filter badges */}
                    {activeFilterCount > 0 && (
                        <div className="flex flex-wrap gap-1">
                            {filterTime !== 'all' && (
                                <Badge className="text-[9px] h-4 px-1.5 bg-amber-500/10 text-amber-400 border-amber-500/20 gap-0.5">
                                    <CalendarDays className="h-2.5 w-2.5" />
                                    {filterTime === 'hour' ? 'Last hour' : filterTime === 'today' ? 'Today' : filterTime === 'week' ? 'This week' : 'This month'}
                                    <button onClick={() => setFilterTime('all')}><X className="h-2 w-2" /></button>
                                </Badge>
                            )}
                            {filterUser !== 'all' && (
                                <Badge className="text-[9px] h-4 px-1.5 bg-amber-500/10 text-amber-400 border-amber-500/20 gap-0.5">
                                    <UserIcon className="h-2.5 w-2.5" />
                                    {uniqueUsers.find(([id]) => id === filterUser)?.[1] || 'User'}
                                    <button onClick={() => setFilterUser('all')}><X className="h-2 w-2" /></button>
                                </Badge>
                            )}
                            {filterAsset !== 'all' && (
                                <Badge className="text-[9px] h-4 px-1.5 bg-amber-500/10 text-amber-400 border-amber-500/20 gap-0.5">
                                    <Server className="h-2.5 w-2.5" />
                                    {uniqueAssets.find(([id]) => id === filterAsset)?.[1] || 'Asset'}
                                    <button onClick={() => setFilterAsset('all')}><X className="h-2 w-2" /></button>
                                </Badge>
                            )}
                        </div>
                    )}

                    {/* Create new note inline */}
                    {isCreating && (
                        <div className="space-y-1">
                            {creatingParentId && (
                                <span className="text-[10px] text-teal-400 flex items-center gap-1">
                                    <CornerDownRight className="h-3 w-3" />
                                    Sub-note of: {notes.find(n => n.id === creatingParentId)?.title || 'Note'}
                                </span>
                            )}
                            <div className="flex gap-1">
                                <Input
                                    value={newTitle}
                                    onChange={(e) => setNewTitle(e.target.value)}
                                    placeholder={creatingParentId ? 'Sub-note title...' : 'Note title...'}
                                    className="h-7 text-xs bg-slate-900/50 border-slate-700 focus:border-teal-500"
                                    autoFocus
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') handleCreate();
                                        if (e.key === 'Escape') { setIsCreating(false); setCreatingParentId(null); setNewTitle(''); }
                                    }}
                                />
                                <Button
                                    size="sm"
                                    className="h-7 px-2 bg-teal-600 hover:bg-teal-700 text-white"
                                    onClick={handleCreate}
                                    disabled={createNote.isPending}
                                >
                                    {createNote.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
                                </Button>
                            </div>
                        </div>
                    )}

                    {/* Search */}
                    {notes.length > 3 && (
                        <div className="relative">
                            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-500" />
                            <Input
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                placeholder="Search notes..."
                                className="h-7 text-xs pl-7 bg-slate-900/50 border-slate-700"
                            />
                        </div>
                    )}
                </div>

                {/* Notes tree */}
                <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
                    {noteTree.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-10 text-slate-500">
                            <FileText className="h-8 w-8 mb-2 opacity-40" />
                            <p className="text-xs">{searchQuery || activeFilterCount > 0 ? 'No matching notes' : 'No notes yet'}</p>
                        </div>
                    ) : (
                        noteTree.map((node) => (
                            <NoteTreeNode
                                key={node.id}
                                node={node}
                                depth={0}
                                selectedNoteId={selectedNoteId}
                                expandedNodes={expandedNodes}
                                onToggleExpand={toggleExpand}
                                onSelect={handleSelectNote}
                                onDelete={handleDelete}
                                onCreateSubNote={handleStartCreateSubNote}
                                engagementId={engagementId}
                                formatDate={formatDate}
                                canCreate={canCreate}
                            />
                        ))
                    )}
                </div>
            </div>

            {/* Main editor panel */}
            <div className="flex-1 flex flex-col border border-slate-800/60 rounded-xl bg-slate-950/40 backdrop-blur-md overflow-hidden min-w-0">
                {selectedNote ? (
                    <>
                        {/* Editor toolbar */}
                        <div className="flex items-center justify-between p-3 border-b border-slate-800/60">
                            <div className="flex items-center gap-2 flex-1">
                                {!showSidebar && (
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        className="h-7 w-7 p-0 text-slate-400"
                                        onClick={() => setShowSidebar(true)}
                                    >
                                        <ChevronLeft className="h-4 w-4 rotate-180" />
                                    </Button>
                                )}
                                <PenLine className="h-4 w-4 text-teal-400 shrink-0" />
                                <Input
                                    value={editTitle}
                                    onChange={(e) => handleTitleChange(e.target.value)}
                                    className="h-8 text-lg font-semibold bg-transparent border-none px-0 focus-visible:ring-0 text-white placeholder:text-slate-600"
                                    placeholder="Untitled note..."
                                    disabled={!canEditNote}
                                />
                            </div>
                            <div className="flex items-center gap-2">
                                {/* Who's viewing this note */}
                                {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}

                                {isTitleSaving && (
                                    <span className="flex items-center gap-1 text-xs text-slate-500">
                                        <Loader2 className="h-3 w-3 animate-spin" />
                                        Saving title...
                                    </span>
                                )}
                                {canDeleteNote && (
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        className="h-7 w-7 p-0 text-slate-500 hover:text-red-400 hover:bg-red-500/10"
                                        onClick={() => handleDelete(selectedNote.id, selectedNote.title)}
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                )}
                                {showSidebar && (
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        className="h-7 w-7 p-0 text-slate-400"
                                        onClick={() => setShowSidebar(false)}
                                    >
                                        <ChevronLeft className="h-4 w-4" />
                                    </Button>
                                )}
                            </div>
                        </div>

                        {/* Note metadata */}
                        <div className="flex items-center gap-4 px-4 py-1.5 border-b border-slate-800/40 text-[11px] text-slate-500">
                            <span className="flex items-center gap-1.5">
                                <TooltipProvider delayDuration={200}>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <div className="w-fit">
                                                <UserAvatar
                                                    user={{
                                                        id: selectedNote.created_by,
                                                        username: selectedNote.created_by_username || 'Unknown',
                                                        profile_photo: selectedNote.created_by_profile_photo,
                                                    }}
                                                    className="h-5 w-5 text-[8px]"
                                                />
                                            </div>
                                        </TooltipTrigger>
                                        <TooltipContent side="bottom">
                                            <span className="text-xs">{selectedNote.created_by_username || 'Unknown'}</span>
                                        </TooltipContent>
                                    </Tooltip>
                                </TooltipProvider>
                            </span>
                            <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                Updated {formatDate(selectedNote.updated_at)}
                            </span>
                            {selectedNote.updated_by_username && (
                                <span className="flex items-center gap-1">
                                    <PenLine className="h-3 w-3" />
                                    Last edited by {selectedNote.updated_by_username}
                                </span>
                            )}
                        </div>

                        {/* Linked Resources */}
                        {selectedNote && (
                            <LinkedResourcesBar
                                note={selectedNote}
                                engagementId={engagementId}
                                canEditNote={canEditNote}
                                onOpenLinkDialog={() => setIsLinkDialogOpen(true)}
                                onUnlink={handleUnlink}
                                router={router}
                                linkedIntelItems={linkedIntel}
                                onUnlinkIntel={async (itemId: string) => {
                                    try {
                                        await unlinkIntel.mutateAsync({ itemId, entityType: 'note', entityId: selectedNote.id });
                                    } catch {}
                                }}
                                linkedInfraItems={linkedInfra}
                                onUnlinkInfra={async (itemId: string) => {
                                    try {
                                        await unlinkInfra.mutateAsync({ itemId, entityType: 'note', entityId: selectedNote.id });
                                    } catch {}
                                }}
                            />
                        )}


                        {/* Collaborative Y.js editor */}
                        <div className="flex-1 overflow-y-auto">
                            <CollaborativeEditor
                                key={selectedNote.id}
                                noteId={selectedNote.id}
                                engagementId={engagementId}
                                placeholder="Start writing your notes..."
                                disabled={!canEditNote}
                                minHeight="calc(100vh - 500px)"
                            />
                        </div>
                    </>
                ) : (
                    /* Empty state */
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-500">
                        <div className="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 mb-4">
                            <StickyNote className="h-10 w-10 text-teal-500/40" />
                        </div>
                        <h3 className="text-lg font-medium text-slate-400 mb-1">
                            {notes.length === 0 ? 'No Notes Yet' : 'Select a Note'}
                        </h3>
                        <p className="text-sm text-slate-600 mb-4">
                            {notes.length === 0
                                ? 'Create your first note to start collaborating'
                                : 'Choose a note from the sidebar to view or edit'}
                        </p>
                        {notes.length === 0 && canCreate && (
                            <Button
                                onClick={() => setIsCreating(true)}
                                className="bg-teal-600 hover:bg-teal-700 text-white"
                            >
                                <Plus className="h-4 w-4 mr-2" />
                                Create First Note
                            </Button>
                        )}
                    </div>
                )}
            </div>

            {/* Link Note Dialog */}
            {selectedNote && (
                <LinkNoteDialog
                    open={isLinkDialogOpen}
                    onOpenChange={setIsLinkDialogOpen}
                    engagementId={engagementId}
                    note={selectedNote}
                    onLink={handleLink}
                    onUnlink={handleUnlink}
                />
            )}
        </div>
    );
}

// ─── Note Tree Node (recursive) ──────────────────────────────────────

type NoteTreeItem = Note & { children: NoteTreeItem[] };

function NoteTreeNode({
    node,
    depth,
    selectedNoteId,
    expandedNodes,
    onToggleExpand,
    onSelect,
    onDelete,
    onCreateSubNote,
    engagementId,
    formatDate,
    canCreate,
}: {
    node: NoteTreeItem;
    depth: number;
    selectedNoteId: string | null;
    expandedNodes: Set<string>;
    onToggleExpand: (id: string) => void;
    onSelect: (id: string) => void;
    onDelete: (id: string, title: string) => void;
    onCreateSubNote: (parentId: string) => void;
    engagementId: string;
    formatDate: (d: string) => string;
    canCreate: boolean;
}) {
    const isSelected = node.id === selectedNoteId;
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children.length > 0;
    const canDeleteThis = useCanDelete(engagementId, 'note', node.created_by);
    const totalLinks =
        (node.linked_findings?.length || 0) +
        (node.linked_testcases?.length || 0) +
        (node.linked_assets?.length || 0) +
        (node.linked_vault_items?.length || 0) +
        (node.linked_cleanup_artifacts?.length || 0);

    return (
        <div>
            <div
                role="button"
                tabIndex={0}
                onClick={() => onSelect(node.id)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(node.id); } }}
                className={cn(
                    "w-full text-left p-2 rounded-lg transition-all duration-200 group relative cursor-pointer",
                    isSelected
                        ? "bg-teal-500/10 border border-teal-500/30 text-white"
                        : "hover:bg-slate-800/60 border border-transparent text-slate-300 hover:text-white"
                )}
                style={{ paddingLeft: `${8 + depth * 16}px` }}
            >
                <div className="flex items-start justify-between gap-1">
                    <div className="flex items-center gap-1 flex-1 min-w-0">
                        {/* Expand/collapse toggle */}
                        {hasChildren ? (
                            <button
                                onClick={(e) => { e.stopPropagation(); onToggleExpand(node.id); }}
                                className="p-0.5 rounded hover:bg-slate-700/50 text-slate-500 hover:text-slate-300 shrink-0"
                            >
                                {isExpanded
                                    ? <ChevronDown className="h-3 w-3" />
                                    : <ChevronRight className="h-3 w-3" />
                                }
                            </button>
                        ) : (
                            <span className="w-4 shrink-0" /> /* spacer for alignment */
                        )}
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{node.title}</p>
                            <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-[10px] text-slate-500 flex items-center gap-0.5">
                                    <Clock className="h-2.5 w-2.5" />
                                    {formatDate(node.updated_at)}
                                </span>
                                <TooltipProvider delayDuration={200}>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <div className="w-fit">
                                                <UserAvatar
                                                    user={{
                                                        id: node.created_by,
                                                        username: node.created_by_username || 'Unknown',
                                                        profile_photo: node.created_by_profile_photo,
                                                    }}
                                                    className="h-4 w-4 text-[6px]"
                                                />
                                            </div>
                                        </TooltipTrigger>
                                        <TooltipContent side="top">
                                            <span className="text-xs">{node.created_by_username || 'Unknown'}</span>
                                        </TooltipContent>
                                    </Tooltip>
                                </TooltipProvider>
                                {totalLinks > 0 && (
                                    <span className="text-[10px] text-teal-500 flex items-center gap-0.5">
                                        <LinkIcon className="h-2.5 w-2.5" />
                                        {totalLinks}
                                    </span>
                                )}
                                {hasChildren && (
                                    <span className="text-[10px] text-slate-600">
                                        {node.children.length} sub
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        {canCreate && (
                            <button
                                onClick={(e) => { e.stopPropagation(); onCreateSubNote(node.id); }}
                                className="p-0.5 rounded hover:bg-teal-500/20 text-slate-500 hover:text-teal-400"
                                title="Add sub-note"
                            >
                                <Plus className="h-3 w-3" />
                            </button>
                        )}
                        {canDeleteThis && (
                            <button
                                onClick={(e) => { e.stopPropagation(); onDelete(node.id, node.title); }}
                                className="p-0.5 rounded hover:bg-red-500/20 text-slate-500 hover:text-red-400"
                            >
                                <Trash2 className="h-3 w-3" />
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Render children when expanded */}
            {hasChildren && isExpanded && (
                <div className="ml-3 border-l border-slate-800/40 pl-0.5">
                    {node.children.map(child => (
                        <NoteTreeNode
                            key={child.id}
                            node={child}
                            depth={depth + 1}
                            selectedNoteId={selectedNoteId}
                            expandedNodes={expandedNodes}
                            onToggleExpand={onToggleExpand}
                            onSelect={onSelect}
                            onDelete={onDelete}
                            onCreateSubNote={onCreateSubNote}
                            engagementId={engagementId}
                            formatDate={formatDate}
                            canCreate={canCreate}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

// ─── Linked Resources Bar ────────────────────────────────────────────

function LinkedResourcesBar({
    note,
    engagementId,
    canEditNote,
    onOpenLinkDialog,
    onUnlink,
    router,
    linkedIntelItems = [],
    onUnlinkIntel,
    linkedInfraItems = [],
    onUnlinkInfra,
}: {
    note: Note;
    engagementId: string;
    canEditNote: boolean;
    onOpenLinkDialog: () => void;
    onUnlink: (type: string, id: string) => void;
    router: any;
    linkedIntelItems?: any[];
    onUnlinkIntel?: (itemId: string) => void;
    linkedInfraItems?: any[];
    onUnlinkInfra?: (itemId: string) => void;
}) {
    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);
    const totalLinks =
        (note.linked_findings?.length || 0) +
        (note.linked_testcases?.length || 0) +
        (note.linked_assets?.length || 0) +
        (note.linked_vault_items?.length || 0) +
        (note.linked_cleanup_artifacts?.length || 0) +
        (linkedIntelItems.length || 0) +
        (linkedInfraItems.length || 0);

    if (totalLinks === 0 && !canEditNote) return null;

    return (
        <div className="flex items-center gap-2 px-4 py-1.5 border-b border-slate-800/40 flex-wrap">
            <span className="text-[11px] text-slate-600 shrink-0 flex items-center gap-1">
                <LinkIcon className="h-3 w-3" />
                Links
            </span>

            {canEditNote && (
                <Button
                    size="sm"
                    variant="ghost"
                    className="h-5 px-1.5 text-[10px] text-teal-400 hover:text-teal-300 hover:bg-teal-500/10 shrink-0"
                    onClick={onOpenLinkDialog}
                >
                    <Plus className="h-3 w-3 mr-0.5" />
                    Link
                </Button>
            )}

            {/* Findings */}
            {note.linked_findings?.map(f => (
                <Badge key={f.id} className="text-[10px] h-5 px-1.5 bg-red-500/10 text-red-400 border-red-500/20 gap-1 shrink-0 cursor-pointer hover:bg-red-500/20"
                    onClick={() => router.push(`/findings/${f.id}?engagementId=${engagementId}`)}
                >
                    <Bug className="h-2.5 w-2.5" />
                    <span className="max-w-[120px] truncate">{f.title}</span>
                    {canEditNote && (
                        <button onClick={(e) => { e.stopPropagation(); onUnlink('findings', f.id); }} className="ml-0.5 hover:text-white">
                            <X className="h-2.5 w-2.5" />
                        </button>
                    )}
                </Badge>
            ))}

            {/* Test Cases */}
            {note.linked_testcases?.map(t => (
                <Badge key={t.id} className="text-[10px] h-5 px-1.5 bg-purple-500/10 text-purple-400 border-purple-500/20 gap-1 shrink-0 cursor-pointer hover:bg-primary/20"
                    onClick={() => router.push(`/testcases/${t.id}?engagementId=${engagementId}`)}
                >
                    <Target className="h-2.5 w-2.5" />
                    <span className="max-w-[120px] truncate">{t.title}</span>
                    {canEditNote && (
                        <button onClick={(e) => { e.stopPropagation(); onUnlink('testcases', t.id); }} className="ml-0.5 hover:text-white">
                            <X className="h-2.5 w-2.5" />
                        </button>
                    )}
                </Badge>
            ))}

            {/* Assets */}
            {note.linked_assets?.map(a => (
                <Badge key={a.id} className="text-[10px] h-5 px-1.5 bg-blue-500/10 text-blue-400 border-blue-500/20 gap-1 shrink-0 cursor-pointer hover:bg-blue-500/20"
                    onClick={() => router.push(`/assets/${a.id}?engagementId=${engagementId}`)}
                >
                    <Server className="h-2.5 w-2.5" />
                    <span className="max-w-[120px] truncate">{a.title}</span>
                    {canEditNote && (
                        <button onClick={(e) => { e.stopPropagation(); onUnlink('assets', a.id); }} className="ml-0.5 hover:text-white">
                            <X className="h-2.5 w-2.5" />
                        </button>
                    )}
                </Badge>
            ))}

            {/* Vault Items */}
            {note.linked_vault_items?.map(v => (
                <Badge key={v.id} className="text-[10px] h-5 px-1.5 bg-amber-500/10 text-amber-400 border-amber-500/20 gap-1 shrink-0">
                    <Key className="h-2.5 w-2.5" />
                    <span className="max-w-[120px] truncate">{v.name}</span>
                    {canEditNote && (
                        <button onClick={() => onUnlink('vault', v.id)} className="ml-0.5 hover:text-white">
                            <X className="h-2.5 w-2.5" />
                        </button>
                    )}
                </Badge>
            ))}

            {/* Cleanup Artifacts */}
            {note.linked_cleanup_artifacts?.map(c => (
                <Badge key={c.id} className="text-[10px] h-5 px-1.5 bg-emerald-500/10 text-emerald-400 border-emerald-500/20 gap-1 shrink-0">
                    <Trash className="h-2.5 w-2.5" />
                    <span className="max-w-[120px] truncate">{c.title}</span>
                    {canEditNote && (
                        <button onClick={() => onUnlink('cleanup', c.id)} className="ml-0.5 hover:text-white">
                            <X className="h-2.5 w-2.5" />
                        </button>
                    )}
                </Badge>
            ))}

            {/* Intel Items */}
            {linkedIntelItems.map(i => (
                <Badge key={i.id} className="text-[10px] h-5 px-1.5 bg-cyan-500/10 text-cyan-400 border-cyan-500/20 gap-1 shrink-0 cursor-pointer hover:bg-cyan-500/20"
                    onClick={() => setIntelDetailId(i.id)}
                >
                    <Radar className="h-2.5 w-2.5" />
                    <span className="max-w-[120px] truncate">{i.title}</span>
                    {canEditNote && onUnlinkIntel && (
                        <button onClick={(e) => { e.stopPropagation(); onUnlinkIntel(i.id); }} className="ml-0.5 hover:text-white">
                            <X className="h-2.5 w-2.5" />
                        </button>
                    )}
                </Badge>
            ))}

            {intelDetailId && <IntelDetailDialog itemId={intelDetailId} onClose={() => setIntelDetailId(null)} />}

            {/* Infrastructure Items */}
            {linkedInfraItems.map(i => (
                <Badge key={i.id} className="text-[10px] h-5 px-1.5 bg-orange-500/10 text-orange-400 border-orange-500/20 gap-1 shrink-0">
                    <Server className="h-2.5 w-2.5" />
                    <span className="max-w-[120px] truncate">{i.name}</span>
                    {canEditNote && onUnlinkInfra && (
                        <button onClick={(e) => { e.stopPropagation(); onUnlinkInfra(i.id); }} className="ml-0.5 hover:text-white">
                            <X className="h-2.5 w-2.5" />
                        </button>
                    )}
                </Badge>
            ))}
        </div>
    );
}

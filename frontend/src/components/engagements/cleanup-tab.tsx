'use client';

import { useState, useMemo, useEffect } from 'react';
import {
    useCleanupArtifacts,
    useCreateCleanupArtifact,
    useUpdateCleanupArtifact,
    useDeleteCleanupArtifact,
    useLinkCleanupToFinding,
    useUnlinkCleanupFromFinding,
    useLinkCleanupToTestCase,
    useUnlinkCleanupFromTestCase,
    useLinkCleanupToAsset,
    useUnlinkCleanupFromAsset,
    CleanupArtifact,
} from '@/lib/hooks/use-cleanup-artifacts';
import { useFindings } from '@/lib/hooks/use-findings';
import { useAssets } from '@/lib/hooks/use-assets';
import { CleanupDetailModal } from './cleanup-detail-modal';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Trash2, Plus, MoreVertical, Loader2, Search,
    Bug, CheckSquare, Link as LinkIcon, X, Pencil, Server,
    Key, FileText, UserCog, ShieldOff, Terminal, Package, HelpCircle,
    CheckCircle2, CheckCircle, Clock, AlertTriangle, MinusCircle, MapPin,
    ArrowUpDown, ArrowUp, ArrowDown,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useCanEdit, useCanDelete, usePermission } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { useNotes } from '@/lib/hooks/use-notes';
import { StickyNote } from 'lucide-react';
import { LinkTooltip } from '@/components/ui/link-tooltip';
import { UserAvatar } from '@/components/ui/user-avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import DiscussionSection from '@/components/discussions/discussion-section';
import { useAuthStore } from '@/stores/auth-store';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import { EntityClassificationField } from '@/components/marking/entity-classification-field';

interface CleanupTabProps {
    engagementId: string;
}

const ARTIFACT_TYPES = [
    { value: 'SSH_KEY', label: 'SSH Key', icon: Key, color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' },
    { value: 'FILE', label: 'File', icon: FileText, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
    { value: 'ACCOUNT', label: 'Account', icon: UserCog, color: 'text-primary', bg: 'bg-primary/10', border: 'border-primary/30' },
    { value: 'PERMISSION', label: 'Permission', icon: ShieldOff, color: 'text-rose-400', bg: 'bg-rose-500/10', border: 'border-rose-500/30' },
    { value: 'BACKDOOR', label: 'Backdoor', icon: Terminal, color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
    { value: 'IMPLANT', label: 'Implant', icon: Package, color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30' },
    { value: 'OTHER', label: 'Other', icon: HelpCircle, color: 'text-slate-400', bg: 'bg-slate-500/10', border: 'border-slate-500/30' },
];

const STATUS_CONFIG: Record<string, { label: string; icon: any; color: string; bg: string; border: string }> = {
    PENDING: { label: 'Pending', icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30' },
    CLEANED: { label: 'Cleaned', icon: CheckCircle2, color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' },
    PARTIALLY_CLEANED: { label: 'Partial', icon: AlertTriangle, color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30' },
    NOT_APPLICABLE: { label: 'N/A', icon: MinusCircle, color: 'text-slate-400', bg: 'bg-slate-500/10', border: 'border-slate-500/30' },
};

function getTypeConfig(type: string) {
    return ARTIFACT_TYPES.find(t => t.value === type) || ARTIFACT_TYPES[ARTIFACT_TYPES.length - 1];
}

const defaultForm = {
    title: '',
    artifact_type: 'SSH_KEY' as CleanupArtifact['artifact_type'],
    status: 'PENDING' as CleanupArtifact['status'],
    location: '',
    description: '',
    cleanup_notes: '',
    classification_level: '' as string,
    classification_suffix: '' as string,
};

export function CleanupTab({ engagementId }: CleanupTabProps) {
    const { data: artifacts = [], isLoading, refetch } = useCleanupArtifacts(engagementId);
    const { data: notes = [] } = useNotes(engagementId);
    const user = useAuthStore((s) => s.user);

    // Compute note count per cleanup artifact
    const noteCountByCleanup = useMemo(() => {
        const map: Record<string, number> = {};
        notes.forEach(n => n.linked_cleanup_artifacts?.forEach(c => { map[c.id] = (map[c.id] || 0) + 1; }));
        return map;
    }, [notes]);
    const { data: findings = [] } = useFindings({ engagement_id: engagementId });
    const { data: testcases = [] } = useTestCases(engagementId);
    const { data: assets = [] } = useAssets(engagementId);

    const createMutation = useCreateCleanupArtifact();
    const updateMutation = useUpdateCleanupArtifact();
    const deleteMutation = useDeleteCleanupArtifact();
    const linkToFinding = useLinkCleanupToFinding();
    const unlinkFromFinding = useUnlinkCleanupFromFinding();
    const linkToTestCase = useLinkCleanupToTestCase();
    const unlinkFromTestCase = useUnlinkCleanupFromTestCase();
    const linkToAsset = useLinkCleanupToAsset();
    const unlinkFromAsset = useUnlinkCleanupFromAsset();

    const canCreate = usePermission(engagementId, 'cleanup_create');
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [searchQuery, setSearchQuery] = useState('');
    const [statusFilter, setStatusFilter] = useState<string>('ALL');
    const [isAddOpen, setIsAddOpen] = useState(false);
    const [isEditOpen, setIsEditOpen] = useState(false);
    const [isLinkOpen, setIsLinkOpen] = useState(false);
    const [viewArtifact, setViewArtifact] = useState<CleanupArtifact | null>(null);
    const [isViewOpen, setIsViewOpen] = useState(false);
    const [linkingArtifact, setLinkingArtifact] = useState<CleanupArtifact | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [form, setForm] = useState({ ...defaultForm });
    const [editId, setEditId] = useState<string | null>(null);

    // Filtered list
    const filtered = artifacts.filter(a => {
        const matchesSearch =
            a.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            a.location?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            a.artifact_type.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesStatus = statusFilter === 'ALL' || a.status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    const [sortField, setSortField] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_sort_cleanup_field') || 'title';
        }
        return 'title';
    });
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') {
            return (localStorage.getItem('redwire_sort_cleanup_order') as 'asc' | 'desc') || 'asc';
        }
        return 'asc';
    });

    useEffect(() => {
        localStorage.setItem('redwire_sort_cleanup_field', sortField);
        localStorage.setItem('redwire_sort_cleanup_order', sortOrder);
    }, [sortField, sortOrder]);

    const SortIcon = ({ field, currentField, order }: { field: string, currentField: string, order: 'asc' | 'desc' }) => {
        if (currentField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
        return order === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
    };

    const sortedArtifacts = useMemo(() => {
        return [...filtered].sort((a, b) => {
            let comparison = 0;
            switch (sortField) {
                case 'title':
                    comparison = a.title.localeCompare(b.title);
                    break;
                case 'artifact_type':
                    comparison = a.artifact_type.localeCompare(b.artifact_type);
                    break;
                case 'status':
                    comparison = a.status.localeCompare(b.status);
                    break;
                case 'created_by_username':
                    comparison = (a.created_by_username || '').localeCompare(b.created_by_username || '');
                    break;
                default:
                    comparison = a.title.localeCompare(b.title);
            }
            return sortOrder === 'asc' ? comparison : -comparison;
        });
    }, [filtered, sortField, sortOrder]);

    // Stats
    const totalCount = artifacts.length;
    const pendingCount = artifacts.filter(a => a.status === 'PENDING').length;
    const cleanedCount = artifacts.filter(a => a.status === 'CLEANED').length;

    // Handlers
    const handleCreate = async () => {
        if (!form.title.trim()) { toast.error('Title is required'); return; }
        setIsSubmitting(true);
        try {
            await createMutation.mutateAsync({ ...form, engagement_id: engagementId, classification_level: form.classification_level || null, classification_suffix: form.classification_suffix || null } as any);
            toast.success('Cleanup artifact created');
            setForm({ ...defaultForm });
            setIsAddOpen(false);
            refetch();
        } catch (e: any) {
            toast.error(getErrorMessage(e, 'Failed to create'));
        } finally { setIsSubmitting(false); }
    };

    const handleEdit = (artifact: CleanupArtifact) => {
        setEditId(artifact.id);
        setForm({
            title: artifact.title,
            artifact_type: artifact.artifact_type,
            status: artifact.status,
            location: artifact.location || '',
            description: artifact.description || '',
            cleanup_notes: artifact.cleanup_notes || '',
            classification_level: artifact.classification_level || '',
            classification_suffix: artifact.classification_suffix || '',
        });
        setIsEditOpen(true);
    };

    const handleUpdate = async () => {
        if (!editId) return;
        setIsSubmitting(true);
        try {
            await updateMutation.mutateAsync({ id: editId, ...form, classification_level: form.classification_level || null, classification_suffix: form.classification_suffix || null });
            toast.success('Cleanup artifact updated');
            setIsEditOpen(false);
            setEditId(null);
            refetch();
        } catch (e: any) {
            toast.error(getErrorMessage(e, 'Failed to update'));
        } finally { setIsSubmitting(false); }
    };

    const handleDelete = async (id: string) => {
        const ok = await confirm({
            title: 'Delete Cleanup Artifact',
            description: 'This will permanently remove the cleanup artifact. Continue?',
        });
        if (!ok) return;
        try {
            await deleteMutation.mutateAsync(id);
            toast.success('Deleted');
            refetch();
        } catch (e: any) {
            toast.error(getErrorMessage(e, 'Failed to delete'));
        }
    };

    const handleStatusToggle = async (artifact: CleanupArtifact) => {
        const nextStatus = artifact.status === 'PENDING' ? 'CLEANED' : 'PENDING';
        try {
            await updateMutation.mutateAsync({ id: artifact.id, status: nextStatus } as any);
            toast.success(`Marked as ${nextStatus === 'CLEANED' ? 'Cleaned' : 'Pending'}`);
            refetch();
        } catch { toast.error('Failed to update status'); }
    };

    const openLinkDialog = (artifact: CleanupArtifact) => {
        setLinkingArtifact(artifact);
        setIsLinkOpen(true);
    };

    // Map LinkResourceType → existing cleanup link/unlink mutations.
    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (!linkingArtifact) return;
        const args = { artifactId: linkingArtifact.id };
        if (type === 'findings') await linkToFinding.mutateAsync({ ...args, findingId: resourceId });
        if (type === 'testcases') await linkToTestCase.mutateAsync({ ...args, testcaseId: resourceId });
        if (type === 'assets') await linkToAsset.mutateAsync({ ...args, assetId: resourceId });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (!linkingArtifact) return;
        const args = { artifactId: linkingArtifact.id };
        if (type === 'findings') await unlinkFromFinding.mutateAsync({ ...args, findingId: resourceId });
        if (type === 'testcases') await unlinkFromTestCase.mutateAsync({ ...args, testcaseId: resourceId });
        if (type === 'assets') await unlinkFromAsset.mutateAsync({ ...args, assetId: resourceId });
    };

    const linkingArtifactLinkedIds: LinkedIdMap = {
        findings: new Set((linkingArtifact?.findings ?? []).map((f: any) => f.id)),
        testcases: new Set((linkingArtifact?.testcases ?? []).map((t: any) => t.id)),
        assets: new Set((linkingArtifact?.assets ?? []).map((a: any) => a.id)),
        vault: new Set(),
        cleanup: new Set(),
        intel: new Set(),
        infra: new Set(),
    };

    const handleViewArtifact = (artifact: CleanupArtifact) => {
        setViewArtifact(artifact);
        setIsViewOpen(true);
    };

    // ============================================================
    // RENDER
    // ============================================================
    return (
        <>
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
                {/* Stats Bar */}
                <div className="grid grid-cols-3 gap-4">
                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs">
                        <CardContent className="p-4 flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                                <Package className="h-4 w-4 text-indigo-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-white">{totalCount}</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Total</p>
                            </div>
                        </CardContent>
                    </Card>
                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs">
                        <CardContent className="p-4 flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                                <Clock className="h-4 w-4 text-yellow-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-white">{pendingCount}</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Pending</p>
                            </div>
                        </CardContent>
                    </Card>
                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs">
                        <CardContent className="p-4 flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-white">{cleanedCount}</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Cleaned</p>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Header / Actions */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex items-center gap-3 flex-1">
                        <div className="relative flex-1 max-w-md">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                            <Input
                                placeholder="Search cleanup artifacts..."
                                className="pl-10 bg-slate-900/50 border-slate-800 text-white h-10 rounded-xl focus:ring-primary/20"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                        </div>
                        <Select value={statusFilter} onValueChange={setStatusFilter}>
                            <SelectTrigger className="w-[160px] bg-slate-900/50 border-slate-800 text-white h-10 rounded-xl">
                                <SelectValue placeholder="Filter status" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                <SelectItem value="ALL">All Statuses</SelectItem>
                                <SelectItem value="PENDING">Pending</SelectItem>
                                <SelectItem value="CLEANED">Cleaned</SelectItem>
                                <SelectItem value="PARTIALLY_CLEANED">Partially Cleaned</SelectItem>
                                <SelectItem value="NOT_APPLICABLE">Not Applicable</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {canCreate && (
                        <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
                            <DialogTrigger asChild>
                                <Button
                                    className="bg-primary hover:bg-primary/90 text-white rounded-xl shadow-lg shadow-primary/20"
                                    onClick={() => setForm({ ...defaultForm })}
                                >
                                    <Plus className="h-4 w-4 mr-2" />
                                    Add Cleanup Item
                                </Button>
                            </DialogTrigger>
                            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[550px]">
                                <DialogHeader>
                                    <DialogTitle>Add Cleanup Artifact</DialogTitle>
                                    <DialogDescription className="text-slate-400">
                                        Document an artifact left behind that requires cleanup.
                                    </DialogDescription>
                                </DialogHeader>
                                <ArtifactForm form={form} setForm={setForm} engagementId={engagementId} />
                                <DialogFooter>
                                    <Button variant="ghost" onClick={() => setIsAddOpen(false)} disabled={isSubmitting}>Cancel</Button>
                                    <Button className="bg-primary hover:bg-primary/90" onClick={handleCreate} disabled={isSubmitting}>
                                        {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create'}
                                    </Button>
                                </DialogFooter>
                            </DialogContent>
                        </Dialog>
                    )}
                </div>

                {/* Table */}
                {isLoading ? (
                    <div className="flex justify-center py-20">
                        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="text-center py-20 bg-slate-900/20 border border-dashed border-slate-800 rounded-3xl">
                        <Package className="h-16 w-16 mx-auto mb-4 text-slate-700 opacity-50" />
                        <h3 className="text-lg font-semibold text-slate-400">No cleanup artifacts</h3>
                        <p className="text-slate-500 text-sm mt-1">Document red team artifacts that require cleanup.</p>
                    </div>
                ) : (
                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs overflow-hidden">
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead>
                                    <tr className="border-b border-slate-800">
                                        <th
                                            className="text-left px-4 py-3 text-[10px] uppercase tracking-wider text-slate-500 font-bold cursor-pointer hover:text-white transition-colors"
                                            onClick={() => {
                                                if (sortField === 'title') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                                                else { setSortField('title'); setSortOrder('asc'); }
                                            }}
                                        >
                                            <div className="flex items-center">
                                                Title <SortIcon field="title" currentField={sortField} order={sortOrder} />
                                            </div>
                                        </th>
                                        <th
                                            className="text-left px-4 py-3 text-[10px] uppercase tracking-wider text-slate-500 font-bold cursor-pointer hover:text-white transition-colors"
                                            onClick={() => {
                                                if (sortField === 'artifact_type') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                                                else { setSortField('artifact_type'); setSortOrder('asc'); }
                                            }}
                                        >
                                            <div className="flex items-center">
                                                Type <SortIcon field="artifact_type" currentField={sortField} order={sortOrder} />
                                            </div>
                                        </th>
                                        <th
                                            className="text-left px-4 py-3 text-[10px] uppercase tracking-wider text-slate-500 font-bold cursor-pointer hover:text-white transition-colors"
                                            onClick={() => {
                                                if (sortField === 'status') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                                                else { setSortField('status'); setSortOrder('asc'); }
                                            }}
                                        >
                                            <div className="flex items-center">
                                                Status <SortIcon field="status" currentField={sortField} order={sortOrder} />
                                            </div>
                                        </th>
                                        <th className="text-left px-4 py-3 text-[10px] uppercase tracking-wider text-slate-500 font-bold">Location</th>
                                        <th className="text-left px-4 py-3 text-[10px] uppercase tracking-wider text-slate-500 font-bold">Links</th>
                                        <th
                                            className="text-left px-4 py-3 text-[10px] uppercase tracking-wider text-slate-500 font-bold cursor-pointer hover:text-white transition-colors"
                                            onClick={() => {
                                                if (sortField === 'created_by_username') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                                                else { setSortField('created_by_username'); setSortOrder('asc'); }
                                            }}
                                        >
                                            <div className="flex items-center">
                                                Created By <SortIcon field="created_by_username" currentField={sortField} order={sortOrder} />
                                            </div>
                                        </th>
                                        <th className="text-right px-4 py-3 text-[10px] uppercase tracking-wider text-slate-500 font-bold">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {sortedArtifacts.map((artifact) => (
                                        <ArtifactRow
                                            key={artifact.id}
                                            artifact={artifact}
                                            engagementId={engagementId}
                                            onEdit={handleEdit}
                                            onDelete={handleDelete}
                                            onLink={openLinkDialog}
                                            onStatusToggle={handleStatusToggle}
                                            onView={handleViewArtifact}
                                            noteCount={noteCountByCleanup[artifact.id] || 0}
                                        />
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                )}

                {/* Cleanup reminder */}
                <div className="bg-amber-500/5 border border-amber-500/20 rounded-2xl p-4 flex gap-4">
                    <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0" />
                    <div>
                        <h4 className="text-sm font-bold text-amber-500">Cleanup Reminder</h4>
                        <p className="text-xs text-amber-500/70 mt-0.5">
                            All artifacts should be cleaned up before engagement close-out.
                            Document any items that could not be fully removed for the client.
                        </p>
                    </div>
                </div>

                {/* Cleanup Discussions */}
                <DiscussionSection
                    engagementId={engagementId}
                    resourceType="cleanup_artifact"
                    resourceId={engagementId}
                    currentUserId={user?.id}
                    isAdmin={user?.role === 'admin'}
                />
            </div>

            {/* Edit Dialog */}
            <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[550px]">
                    <DialogHeader>
                        <DialogTitle>Edit Cleanup Artifact</DialogTitle>
                        <DialogDescription className="text-slate-400">
                            Update the details of this cleanup item.
                        </DialogDescription>
                    </DialogHeader>
                    <ArtifactForm form={form} setForm={setForm} engagementId={engagementId} />
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setIsEditOpen(false)} disabled={isSubmitting}>Cancel</Button>
                        <Button className="bg-primary hover:bg-primary/90" onClick={handleUpdate} disabled={isSubmitting}>
                            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Update'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Link Dialog — unified shared modal */}
            {linkingArtifact && (
                <LinkEntityDialog
                    open={isLinkOpen}
                    onOpenChange={setIsLinkOpen}
                    engagementId={engagementId}
                    entityType="cleanup"
                    entityId={linkingArtifact.id}
                    entityName={linkingArtifact.title}
                    linkedIds={linkingArtifactLinkedIds}
                    onLink={handleEntityLink}
                    onUnlink={handleEntityUnlink}
                />
            )}

            <ConfirmDialog />

            <CleanupDetailModal
                artifact={viewArtifact}
                open={isViewOpen}
                onOpenChange={setIsViewOpen}
            />
        </>
    );
}


// ─── Sub-components ──────────────────────────────────────────────

function ArtifactForm({ form, setForm, engagementId }: { form: typeof defaultForm; setForm: (f: typeof defaultForm) => void; engagementId: string }) {
    return (
        <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                    <Label>Title</Label>
                    <Input
                        value={form.title}
                        onChange={(e) => setForm({ ...form, title: e.target.value })}
                        placeholder="e.g. SSH key on web-server-01"
                        className="bg-slate-950/50 border-slate-800"
                    />
                </div>
                <div className="space-y-2">
                    <Label>Type</Label>
                    <Select
                        value={form.artifact_type}
                        onValueChange={(v: any) => setForm({ ...form, artifact_type: v })}
                    >
                        <SelectTrigger className="bg-slate-950/50 border-slate-800">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                            {ARTIFACT_TYPES.map(t => (
                                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                    <Label>Status</Label>
                    <Select
                        value={form.status}
                        onValueChange={(v: any) => setForm({ ...form, status: v })}
                    >
                        <SelectTrigger className="bg-slate-950/50 border-slate-800">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                            <SelectItem value="PENDING">Pending</SelectItem>
                            <SelectItem value="CLEANED">Cleaned</SelectItem>
                            <SelectItem value="PARTIALLY_CLEANED">Partially Cleaned</SelectItem>
                            <SelectItem value="NOT_APPLICABLE">Not Applicable</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="space-y-2">
                    <Label>Location</Label>
                    <Input
                        value={form.location}
                        onChange={(e) => setForm({ ...form, location: e.target.value })}
                        placeholder="e.g. 192.168.1.100:/root/.ssh"
                        className="bg-slate-950/50 border-slate-800"
                    />
                </div>
            </div>
            <div className="space-y-2">
                <Label>Description</Label>
                <Textarea
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    placeholder="Details of what was left behind and why..."
                    className="bg-slate-950/50 border-slate-800 h-20"
                />
            </div>
            <div className="space-y-2">
                <Label>Cleanup Notes</Label>
                <Textarea
                    value={form.cleanup_notes}
                    onChange={(e) => setForm({ ...form, cleanup_notes: e.target.value })}
                    placeholder="Steps to clean up or steps already taken..."
                    className="bg-slate-950/50 border-slate-800 h-20"
                />
            </div>
            <EntityClassificationField
                engagementId={engagementId}
                level={form.classification_level || null}
                suffix={form.classification_suffix || null}
                inheritLabel="Inherit (engagement default)"
                label="Classification Marking"
                onChange={(lvl, suf) => setForm({ ...form, classification_level: lvl || '', classification_suffix: suf || '' })}
            />
        </div>
    );
}

function ArtifactRow({
    artifact,
    engagementId,
    onEdit,
    onDelete,
    onLink,
    onStatusToggle,
    onView,
    noteCount,
}: {
    artifact: CleanupArtifact;
    engagementId: string;
    onEdit: (a: CleanupArtifact) => void;
    onDelete: (id: string) => void;
    onLink: (a: CleanupArtifact) => void;
    onStatusToggle: (a: CleanupArtifact) => void;
    onView: (a: CleanupArtifact) => void;
    noteCount?: number;
}) {
    const canEditCleanup = useCanEdit(engagementId, 'cleanup', artifact.created_by);
    const canDeleteCleanup = useCanDelete(engagementId, 'cleanup', artifact.created_by);
    const typeConfig = getTypeConfig(artifact.artifact_type);
    const statusCfg = STATUS_CONFIG[artifact.status] || STATUS_CONFIG.PENDING;
    const TypeIcon = typeConfig.icon;
    const StatusIcon = statusCfg.icon;

    const findingsCount = artifact.findings?.length || 0;
    const testcasesCount = artifact.testcases?.length || 0;
    const assetsCount = artifact.assets?.length || 0;
    const nc = noteCount || 0;

    return (
        <tr className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors group cursor-pointer" onClick={() => onView(artifact)}>
            <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                    <div className={cn("p-1.5 rounded-lg border", typeConfig.bg, typeConfig.border)}>
                        <TypeIcon className={cn("h-3.5 w-3.5", typeConfig.color)} />
                    </div>
                    <div className="min-w-0">
                        <p className="text-sm font-medium text-white truncate max-w-[250px]">{artifact.title}</p>
                        {artifact.description && (
                            <p className="text-[10px] text-slate-500 truncate max-w-[250px] mt-0.5">{artifact.description}</p>
                        )}
                    </div>
                </div>
            </td>
            <td className="px-4 py-3">
                <Badge variant="outline" className={cn("text-[10px] border", typeConfig.border, typeConfig.color, typeConfig.bg)}>
                    {typeConfig.label}
                </Badge>
            </td>
            <td className="px-4 py-3">
                <button
                    onClick={(e) => { e.stopPropagation(); onStatusToggle(artifact); }}
                    className={cn(
                        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold border cursor-pointer transition-all hover:scale-105",
                        statusCfg.bg, statusCfg.border, statusCfg.color
                    )}
                >
                    <StatusIcon className="h-3 w-3" />
                    {statusCfg.label}
                </button>
            </td>
            <td className="px-4 py-3">
                {artifact.location ? (
                    <div className="flex items-center gap-1.5 text-xs text-slate-400">
                        <MapPin className="h-3 w-3 text-slate-600" />
                        <span className="truncate max-w-[180px]">{artifact.location}</span>
                    </div>
                ) : (
                    <span className="text-xs text-slate-600">—</span>
                )}
            </td>
            <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                    <LinkTooltip
                        icon={<Bug className="h-3 w-3" />}
                        count={findingsCount}
                        items={(artifact.findings || []).map((f: any) => ({ name: f.title, href: `/findings/${f.id}?engagementId=${engagementId}` }))}
                        label="Findings"
                        colorClass="text-red-400"
                        countClass="text-[10px] font-bold"
                    />
                    <LinkTooltip
                        icon={<CheckSquare className="h-3 w-3" />}
                        count={testcasesCount}
                        items={(artifact.testcases || []).map((t: any) => ({ name: t.title, href: `/testcases/${t.id}?engagementId=${engagementId}` }))}
                        label="Test Cases"
                        colorClass="text-emerald-400"
                        countClass="text-[10px] font-bold"
                    />
                    <LinkTooltip
                        icon={<Server className="h-3 w-3" />}
                        count={assetsCount}
                        items={(artifact.assets || []).map((a: any) => ({ name: a.name, href: `/assets/${a.id}?engagementId=${engagementId}` }))}
                        label="Assets"
                        colorClass="text-primary"
                        countClass="text-[10px] font-bold"
                    />
                    <LinkTooltip
                        icon={<StickyNote className="h-3 w-3" />}
                        count={nc}
                        items={[]}
                        label="Notes"
                        colorClass="text-teal-400"
                        countClass="text-[10px] font-bold"
                    />
                    {findingsCount === 0 && testcasesCount === 0 && assetsCount === 0 && nc === 0 && (
                        <span className="text-[10px] text-slate-600">None</span>
                    )}
                </div>
            </td>
            <td className="px-4 py-3">
                <TooltipProvider delayDuration={200}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <div className="w-fit">
                                <UserAvatar
                                    user={{
                                        id: artifact.created_by,
                                        username: artifact.created_by_username || 'System',
                                        profile_photo: artifact.created_by_profile_photo,
                                    }}
                                    className="h-7 w-7"
                                />
                            </div>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                            <span className="text-xs">{artifact.created_by_username || 'System'}</span>
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </td>
            <td className="px-4 py-3 text-right">
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                            <MoreVertical className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 text-white" align="end">
                        {canEditCleanup && (
                            <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); onEdit(artifact); }}>
                                <Pencil className="h-4 w-4 mr-2" />
                                Edit
                            </DropdownMenuItem>
                        )}
                        <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={(e) => { e.stopPropagation(); onLink(artifact); }}>
                            <LinkIcon className="h-4 w-4 mr-2" />
                            Link Items
                        </DropdownMenuItem>
                        {canDeleteCleanup && (
                            <DropdownMenuItem className="text-red-400 focus:bg-red-500/10 focus:text-red-400" onClick={(e) => { e.stopPropagation(); onDelete(artifact.id); }}>
                                <Trash2 className="h-4 w-4 mr-2" />
                                Delete
                            </DropdownMenuItem>
                        )}
                    </DropdownMenuContent>
                </DropdownMenu>
            </td>
        </tr>
    );
}

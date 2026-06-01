'use client';

import { useState, useMemo, useEffect } from 'react';
import { useColumnVisibility, ColumnDef } from '@/lib/hooks/use-column-visibility';
import { ColumnToggle } from '@/components/ui/column-toggle';
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
import {
    FileIcon,
    Plus,
    Loader2,
    Download,
    Trash2,
    MessageSquare,
    CheckCircle2,
    XCircle,
    FileText,
    Image as ImageIcon,
    FileCode,
    Search,
    MoreVertical,
    ArrowUpDown,
    ArrowUp,
    ArrowDown,
    Bug,
    CheckSquare,
    Link2
} from 'lucide-react';
import { useEngagementEvidence, useUploadEvidence, useUpdateEvidence, useDeleteEvidence, getEvidenceUrl } from '@/lib/hooks/use-evidence';
import { getEvidenceDownloadUrl } from '@/lib/evidence-download';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { useCanEdit, useCanDelete, usePermission } from '@/lib/hooks/use-permissions';
import { useAuthStore } from '@/stores/auth-store';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { UserAvatar } from '@/components/ui/user-avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface AttachmentsTabProps {
    engagementId: string;
}

const ATTACHMENTS_COLUMNS: ColumnDef[] = [
    { key: 'file',      label: 'File',       required: true },
    { key: 'context',   label: 'Context' },
    { key: 'linkedTo',  label: 'Linked To' },
    { key: 'size',      label: 'Size' },
    { key: 'uploaded',  label: 'Uploaded' },
    { key: 'createdBy', label: 'Created By' },
    { key: 'report',    label: 'Report' },
    { key: 'actions',   label: 'Actions',    required: true },
];

const AttachmentRow = ({ item, engagementId, router, getFileIcon, formatSize, handleToggleReportStatus, handleDelete, col = () => true }: any) => {
    const canEdit = useCanEdit(engagementId, 'evidence', item.created_by);
    const canDelete = useCanDelete(engagementId, 'evidence', item.created_by);

    return (
        <TableRow
            key={item.id}
            className="border-slate-800 hover:bg-slate-800/30 group cursor-pointer"
            onClick={() => router.push(`/engagements/${engagementId}/evidence/${item.id}?source=attachments`)}
        >
            <TableCell>
                <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-slate-800 text-slate-400">
                        {getFileIcon(item.mime_type)}
                    </div>
                    <div className="flex flex-col">
                        <span className="font-medium text-slate-200 truncate max-w-[200px]">
                            {item.original_filename}
                        </span>
                        {item.description && (
                            <span className="text-xs text-slate-500 italic truncate max-w-[200px]">
                                {item.description}
                            </span>
                        )}
                        {item.unresolved_thread_count && item.unresolved_thread_count > 0 ? (
                            <div className="flex items-center gap-1.5 mt-1">
                                <Badge variant="secondary" className="bg-amber-500/10 text-amber-500 border-amber-500/20 px-1 py-0 text-[9px] h-4 gap-1">
                                    <MessageSquare className="h-2.5 w-2.5" />
                                    {item.unresolved_thread_count} Unresolved
                                </Badge>
                            </div>
                        ) : null}
                    </div>
                </div>
            </TableCell>
            {col('context') && <TableCell>
                {item.finding_id ? (
                    <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-500 border-amber-500/20">Finding Evidence</Badge>
                ) : item.testcase_id ? (
                    <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-500 border-emerald-500/20">Test Case Evidence</Badge>
                ) : (
                    <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-500 border-blue-500/20">Engagement Attachment</Badge>
                )}
            </TableCell>}
            {col('linkedTo') && <TableCell>
                {item.finding_id && item.finding_title ? (
                    <button
                        className="flex items-center gap-2 text-sm text-red-400 hover:text-red-300 transition-colors group/link"
                        onClick={(e) => {
                            e.stopPropagation();
                            router.push(`/findings/${item.finding_id}?engagementId=${engagementId}`);
                        }}
                    >
                        <Bug className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate max-w-[180px] group-hover/link:underline" title={item.finding_title}>{item.finding_title}</span>
                    </button>
                ) : item.testcase_id && item.testcase_title ? (
                    <button
                        className="flex items-center gap-2 text-sm text-emerald-400 hover:text-emerald-300 transition-colors group/link"
                        onClick={(e) => {
                            e.stopPropagation();
                            router.push(`/testcases/${item.testcase_id}?engagementId=${engagementId}`);
                        }}
                    >
                        <CheckSquare className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate max-w-[180px] group-hover/link:underline" title={item.testcase_title}>{item.testcase_title}</span>
                    </button>
                ) : (
                    <span className="text-slate-600 text-sm">—</span>
                )}
            </TableCell>}
            {col('size') && <TableCell className="text-slate-400 text-xs">{formatSize(item.file_size)}</TableCell>}
            {col('uploaded') && <TableCell className="text-slate-500 text-xs">{formatDistanceToNow(parseUTCDate(item.created_at), { addSuffix: true })}</TableCell>}
            {col('createdBy') && <TableCell>
                <TooltipProvider delayDuration={200}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <div className="w-fit">
                                <UserAvatar
                                    user={{
                                        id: item.created_by,
                                        username: item.created_by_username || 'Unknown',
                                        profile_photo: item.created_by_profile_photo,
                                    }}
                                    className="h-7 w-7"
                                />
                            </div>
                        </TooltipTrigger>
                        <TooltipContent
                            side="top"
                            className="bg-slate-900 border-slate-700 text-white px-3 py-1.5 rounded-lg shadow-xl shadow-black/40"
                        >
                            <span className="text-xs">{item.created_by_username || 'Unknown'}</span>
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </TableCell>}
            {col('report') && <TableCell>
                <Button
                    size="icon"
                    variant="ghost"
                    onClick={(e) => {
                        e.stopPropagation();
                        if (canEdit) handleToggleReportStatus(item);
                    }}
                    disabled={!canEdit}
                    className={cn(
                        "h-8 w-8 rounded-full transition-all",
                        item.include_in_report
                            ? "text-green-500 bg-green-500/10 hover:bg-green-500/20"
                            : "text-slate-600 bg-slate-800/50 hover:bg-slate-800",
                        !canEdit && "opacity-50 cursor-not-allowed"
                    )}
                    title={item.include_in_report ? "Included in Report" : "Excluded from Report"}
                >
                    {item.include_in_report ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
            </Button>
            </TableCell>}
            <TableCell className="text-right">
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-white" onClick={(e) => e.stopPropagation()}>
                            <MoreVertical className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 text-white" align="end">
                        <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={async (e) => {
                            e.stopPropagation();
                            try {
                                const url = await getEvidenceDownloadUrl(item.id);
                                window.open(url, '_blank');
                            } catch {
                                // surface via existing toast/error UI elsewhere
                            }
                        }}>
                            <Download className="h-4 w-4 mr-2" />
                            Download
                        </DropdownMenuItem>
                        {canDelete && (
                            <DropdownMenuItem className="text-red-400 focus:bg-red-500/10 focus:text-red-400" onClick={(e) => {
                                e.stopPropagation();
                                handleDelete(item);
                            }}>
                                <Trash2 className="h-4 w-4 mr-2" />
                                Delete
                            </DropdownMenuItem>
                        )}
                    </DropdownMenuContent>
                </DropdownMenu>
            </TableCell>
        </TableRow>
    );
};

export function AttachmentsTab({ engagementId }: AttachmentsTabProps) {
    const router = useRouter();
    const { data: evidence = [], isLoading } = useEngagementEvidence(engagementId);
    const uploadEvidence = useUploadEvidence({ engagementId });
    const updateEvidence = useUpdateEvidence();
    const deleteEvidence = useDeleteEvidence();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);

    // Permission guards
    const { user } = useAuthStore();
    const canCreateEvidence = usePermission(engagementId, 'evidence_create');

    const [uploadFile, setUploadFile] = useState<File | null>(null);
    const [description, setDescription] = useState('');
    const [searchTerm, setSearchTerm] = useState('');

    const [sortField, setSortField] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_sort_attachments_field') || 'created_at';
        }
        return 'created_at';
    });
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') {
            return (localStorage.getItem('redwire_sort_attachments_order') as 'asc' | 'desc') || 'desc';
        }
        return 'desc';
    });

    const [visibleCols, toggleCol] = useColumnVisibility('redwire_col_attachments', ATTACHMENTS_COLUMNS);
    const col = (key: string) => visibleCols.has(key);

    useEffect(() => {
        localStorage.setItem('redwire_sort_attachments_field', sortField);
        localStorage.setItem('redwire_sort_attachments_order', sortOrder);
    }, [sortField, sortOrder]);


    const SortIcon = ({ field, currentField, order }: { field: string, currentField: string, order: 'asc' | 'desc' }) => {
        if (currentField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
        return order === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
    };

    const filteredEvidence = useMemo(() => {
        const filtered = evidence.filter(item => {
            if (!searchTerm) return true;
            const term = searchTerm.toLowerCase();
            return item.original_filename.toLowerCase().includes(term) ||
                (item.description || '').toLowerCase().includes(term);
        });
        return [...filtered].sort((a, b) => {
            let comparison = 0;
            switch (sortField) {
                case 'original_filename':
                    comparison = a.original_filename.localeCompare(b.original_filename);
                    break;
                case 'context':
                    comparison = (a.finding_id ? 1 : 0) - (b.finding_id ? 1 : 0);
                    break;
                case 'file_size':
                    comparison = a.file_size - b.file_size;
                    break;
                case 'created_at':
                    comparison = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
                    break;
                case 'created_by_username':
                    comparison = (a.created_by_username || '').localeCompare(b.created_by_username || '');
                    break;
                default:
                    comparison = a.original_filename.localeCompare(b.original_filename);
            }
            return sortOrder === 'asc' ? comparison : -comparison;
        });
    }, [evidence, searchTerm, sortField, sortOrder]);

    const handleUpload = async () => {
        if (!uploadFile) return;

        try {
            await uploadEvidence.mutateAsync({
                file: uploadFile,
                description
            });
            toast.success('File uploaded successfully');
            setIsUploadDialogOpen(false);
            setUploadFile(null);
            setDescription('');
        } catch (err) {
            toast.error('Failed to upload file');
        }
    };

    const handleToggleReportStatus = async (item: any) => {
        try {
            await updateEvidence.mutateAsync({
                id: item.id,
                includeInReport: !item.include_in_report
            });
            toast.success('Reporting status updated');
        } catch (err) {
            toast.error('Failed to update reporting status');
        }
    };

    const handleDelete = async (item: any) => {
        const confirmed = await confirm({
            title: 'Delete Attachment',
            description: 'Are you sure you want to delete this attachment?',
        });
        if (!confirmed) return;

        try {
            await deleteEvidence.mutateAsync(item);
            toast.success('Attachment deleted');
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to delete attachment'));
        }
    };

    const getFileIcon = (mimeType?: string) => {
        if (!mimeType) return <FileIcon className="h-4 w-4" />;
        if (mimeType.startsWith('image/')) return <ImageIcon className="h-4 w-4" />;
        if (mimeType.includes('pdf')) return <FileText className="h-4 w-4" />;
        if (mimeType.includes('javascript') || mimeType.includes('json') || mimeType.includes('html')) return <FileCode className="h-4 w-4" />;
        return <FileIcon className="h-4 w-4" />;
    };

    const formatSize = (bytes: number) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="flex flex-row items-center justify-between">
                <div>
                    <CardTitle className="text-white">Engagement Evidence</CardTitle>
                    <CardDescription>All attachments associated with this mission</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative w-64 mr-2">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
                        <Input placeholder="Search attachments..." className="pl-8 bg-slate-900/50 border-slate-700 text-xs h-9" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                    </div>
                    <ColumnToggle columns={ATTACHMENTS_COLUMNS} visible={visibleCols} onToggle={toggleCol} />
                    {canCreateEvidence && (
                        <Button
                            onClick={() => setIsUploadDialogOpen(true)}
                            size="sm"
                            className="bg-primary hover:bg-primary/90"
                        >
                            <Plus className="h-4 w-4 mr-2" />
                            Upload Attachment
                        </Button>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                {isLoading ? (
                    <div className="flex justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                    </div>
                ) : evidence.length === 0 ? (
                    <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                        <FileIcon className="h-12 w-12 mx-auto mb-4 text-slate-600 opacity-20" />
                        <p className="text-slate-500">No attachments found for this engagement.</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <Table>
                            <TableHeader>
                            <TableRow className="border-slate-800 hover:bg-transparent">
                                <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => { if (sortField === 'original_filename') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc'); else { setSortField('original_filename'); setSortOrder('asc'); } }}>
                                    <div className="flex items-center">File <SortIcon field="original_filename" currentField={sortField} order={sortOrder} /></div>
                                </TableHead>
                                {col('context') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => { if (sortField === 'context') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc'); else { setSortField('context'); setSortOrder('asc'); } }}><div className="flex items-center">Context <SortIcon field="context" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('linkedTo') && <TableHead className="text-slate-400"><div className="flex items-center gap-1"><Link2 className="h-3 w-3" />Linked To</div></TableHead>}
                                {col('size') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => { if (sortField === 'file_size') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc'); else { setSortField('file_size'); setSortOrder('asc'); } }}><div className="flex items-center">Size <SortIcon field="file_size" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('uploaded') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => { if (sortField === 'created_at') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc'); else { setSortField('created_at'); setSortOrder('desc'); } }}><div className="flex items-center">Uploaded <SortIcon field="created_at" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('createdBy') && <TableHead className="text-slate-400 cursor-pointer hover:text-white transition-colors" onClick={() => { if (sortField === 'created_by_username') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc'); else { setSortField('created_by_username'); setSortOrder('asc'); } }}><div className="flex items-center">Created By <SortIcon field="created_by_username" currentField={sortField} order={sortOrder} /></div></TableHead>}
                                {col('report') && <TableHead className="text-slate-400">Report</TableHead>}
                                <TableHead className="text-slate-400 text-right">Actions</TableHead>
                            </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredEvidence.map((item) => (
                                    <AttachmentRow
                                        key={item.id}
                                        item={item}
                                        engagementId={engagementId}
                                        router={router}
                                        getFileIcon={getFileIcon}
                                        formatSize={formatSize}
                                        handleToggleReportStatus={handleToggleReportStatus}
                                        handleDelete={handleDelete}
                                        col={col}
                                    />
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                )}
            </CardContent>

            <Dialog open={isUploadDialogOpen} onOpenChange={setIsUploadDialogOpen}>
                <DialogContent className="bg-slate-950 border-slate-800 text-white">
                    <DialogHeader>
                        <DialogTitle>Upload Engagement Attachment</DialogTitle>
                        <DialogDescription>
                            Attach a file directly to this engagement (e.g., Scope, RoE, notes).
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="file">File</Label>
                            <Input
                                id="file"
                                type="file"
                                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                                className="bg-slate-900 border-slate-700 text-white"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="description">Description (Optional)</Label>
                            <Textarea
                                id="description"
                                placeholder="Describe this attachment..."
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                className="bg-slate-900 border-slate-700 text-white"
                                rows={3}
                            />
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setIsUploadDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button
                            onClick={handleUpload}
                            disabled={!uploadFile || uploadEvidence.isPending}
                            className="bg-primary hover:bg-primary/90"
                        >
                            {uploadEvidence.isPending ? (
                                <>
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    Uploading...
                                </>
                            ) : (
                                'Upload'
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            <ConfirmDialog />
        </Card >
    );
}

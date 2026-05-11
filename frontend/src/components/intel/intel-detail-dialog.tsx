'use client';

import { useRef } from 'react';
import { MarkdownPreview } from '@/components/ui/markdown-editor';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import {
    Bug,
    Shield,
    Newspaper,
    BookOpen,
    Zap,
    FileText,
    ExternalLink,
    Link2,
    Loader2,
    Trash2,
    Paperclip,
    Download,
    Upload,
} from 'lucide-react';
import { useIntelItem, useUnlinkIntel, useUploadIntelAttachment, useDeleteIntelAttachment } from '@/lib/hooks/use-intel';
import { toast } from 'sonner';
import api from '@/lib/api';

// ── Constants ───────────────────────────────────────────────────

export const INTEL_TYPE_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
    CVE: { label: 'CVE', color: 'bg-red-500/15 text-red-400 border-red-500/30', icon: Bug },
    ADVISORY: { label: 'Advisory', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', icon: Shield },
    ARTICLE: { label: 'Article', color: 'bg-blue-500/15 text-blue-400 border-blue-500/30', icon: Newspaper },
    ZINE: { label: 'Zine', color: 'bg-purple-500/15 text-purple-400 border-purple-500/30', icon: BookOpen },
    EXPLOIT: { label: 'Exploit', color: 'bg-rose-500/15 text-rose-400 border-rose-500/30', icon: Zap },
    OTHER: { label: 'Other', color: 'bg-slate-500/15 text-slate-400 border-slate-500/30', icon: FileText },
};

export const INTEL_SEVERITY_CONFIG: Record<string, { label: string; color: string }> = {
    CRITICAL: { label: 'Critical', color: 'bg-red-600/20 text-red-400 border-red-500/40' },
    HIGH: { label: 'High', color: 'bg-orange-500/20 text-orange-400 border-orange-500/40' },
    MEDIUM: { label: 'Medium', color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40' },
    LOW: { label: 'Low', color: 'bg-blue-500/20 text-blue-400 border-blue-500/40' },
    INFO: { label: 'Info', color: 'bg-slate-500/20 text-slate-400 border-slate-500/40' },
};

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

// ── Component ───────────────────────────────────────────────────

interface IntelDetailDialogProps {
    itemId: string;
    onClose: () => void;
}

export function IntelDetailDialog({ itemId, onClose }: IntelDetailDialogProps) {
    const { data: item, isLoading } = useIntelItem(itemId);
    const unlinkIntel = useUnlinkIntel();
    const uploadAttachment = useUploadIntelAttachment();
    const deleteAttachment = useDeleteIntelAttachment();
    const fileInputRef = useRef<HTMLInputElement>(null);

    if (!item && isLoading) {
        return (
            <Dialog open onOpenChange={() => onClose()}>
                <DialogContent className="bg-slate-900 border-slate-700 text-white">
                    <DialogHeader>
                        <DialogTitle className="sr-only">Loading intel item</DialogTitle>
                    </DialogHeader>
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
                    </div>
                </DialogContent>
            </Dialog>
        );
    }

    if (!item) return null;

    const typeConf = INTEL_TYPE_CONFIG[item.item_type] || INTEL_TYPE_CONFIG.OTHER;
    const TypeIcon = typeConf.icon;
    const allLinked = [...(item.linked_findings || []), ...(item.linked_testcases || []), ...(item.linked_notes || [])];

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        try {
            await uploadAttachment.mutateAsync({ itemId, files: Array.from(files) });
            toast.success(`${files.length} file(s) uploaded`);
        } catch {
            toast.error('Upload failed');
        }
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleDownload = async (attachmentId: string) => {
        try {
            const { data } = await api.get(`/intel/items/${itemId}/attachments/${attachmentId}/download`);
            window.open(data.url, '_blank');
        } catch {
            toast.error('Download failed');
        }
    };

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    return (
        <Dialog open onOpenChange={() => onClose()}>
            <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-2xl max-h-[80vh] overflow-y-auto">
                <div className="w-full min-w-0" style={{ overflowWrap: 'anywhere' }}>
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-lg min-w-0 pr-6">
                        <div className={`p-1.5 rounded-lg border shrink-0 ${typeConf.color}`}>
                            <TypeIcon className="h-4 w-4" />
                        </div>
                        <span className="truncate min-w-0" title={item.title}>{item.title}</span>
                    </DialogTitle>
                    <DialogDescription className="sr-only">Intel item details</DialogDescription>
                    <div className="flex items-center gap-3 pt-1 flex-wrap">
                        {item.cve_id && (
                            <Badge className="text-xs bg-red-500/10 text-red-400 border-red-500/30 font-mono">
                                {item.cve_id}
                            </Badge>
                        )}
                        {item.severity && INTEL_SEVERITY_CONFIG[item.severity] && (
                            <Badge className={`text-xs ${INTEL_SEVERITY_CONFIG[item.severity].color}`}>
                                {INTEL_SEVERITY_CONFIG[item.severity].label}
                            </Badge>
                        )}
                        <Badge className={`text-xs ${typeConf.color}`}>
                            {typeConf.label}
                        </Badge>
                        {item.source && <span className="text-xs text-slate-500">via {item.source}</span>}
                    </div>
                </DialogHeader>

                <div className="space-y-5 mt-2">
                    {/* Content */}
                    {item.content && (
                        <div className="rounded-lg bg-slate-950/50 border border-slate-800 p-4" style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
                            <MarkdownPreview value={item.content} theme="dark" />
                        </div>
                    )}

                    {/* Source URL */}
                    {item.source_url && (
                        <a
                            href={item.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2 text-sm text-cyan-400 hover:text-cyan-300 transition-colors min-w-0"
                        >
                            <ExternalLink className="h-4 w-4 shrink-0" />
                            <span className="truncate">{item.source_url}</span>
                        </a>
                    )}

                    {/* Attachments */}
                    {((item.attachments && item.attachments.length > 0) || item.source === 'manual') && (
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                                    <Paperclip className="h-4 w-4 text-cyan-400" />
                                    Attachments
                                    <span className="text-xs text-slate-500">({item.attachments?.length || 0})</span>
                                </h4>
                                <div>
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        multiple
                                        className="hidden"
                                        onChange={handleFileUpload}
                                    />
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 text-xs text-slate-400 hover:text-cyan-400 gap-1"
                                        onClick={() => fileInputRef.current?.click()}
                                        disabled={uploadAttachment.isPending}
                                    >
                                        {uploadAttachment.isPending ? (
                                            <Loader2 className="h-3 w-3 animate-spin" />
                                        ) : (
                                            <Upload className="h-3 w-3" />
                                        )}
                                        Upload
                                    </Button>
                                </div>
                            </div>
                            {item.attachments && item.attachments.length > 0 ? (
                                <div className="space-y-1">
                                    {item.attachments.map(att => (
                                        <div key={att.id} className="flex items-center justify-between rounded-lg bg-slate-950/50 border border-slate-800 px-3 py-2 min-w-0">
                                            <div className="flex items-center gap-2 min-w-0 flex-1">
                                                <FileText className="h-4 w-4 text-slate-500 shrink-0" />
                                                <span className="text-sm text-slate-300 truncate">{att.original_filename}</span>
                                                <span className="text-[10px] text-slate-600 shrink-0">{formatFileSize(att.file_size)}</span>
                                            </div>
                                            <div className="flex items-center gap-1 shrink-0">
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6 text-slate-500 hover:text-cyan-400"
                                                    onClick={() => handleDownload(att.id)}
                                                >
                                                    <Download className="h-3 w-3" />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6 text-slate-600 hover:text-red-400"
                                                    onClick={async () => {
                                                        await deleteAttachment.mutateAsync({ itemId, attachmentId: att.id });
                                                        toast.success('Attachment deleted');
                                                    }}
                                                >
                                                    <Trash2 className="h-3 w-3" />
                                                </Button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-xs text-slate-500 italic py-2">No files attached yet. Click Upload to add files.</p>
                            )}
                        </div>
                    )}

                    {/* Linked Entities */}
                    <div className="space-y-2">
                        <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                            <Link2 className="h-4 w-4 text-cyan-400" />
                            Linked Entities
                            <span className="text-xs text-slate-500">({allLinked.length})</span>
                        </h4>
                        {allLinked.length === 0 ? (
                            <p className="text-xs text-slate-500 italic py-2">No linked findings, test cases, or notes yet.</p>
                        ) : (
                            <div className="space-y-1">
                                {allLinked.map(entity => (
                                    <div key={`${entity.type}-${entity.id}`} className="flex items-center justify-between rounded-lg bg-slate-950/50 border border-slate-800 px-3 py-2 min-w-0">
                                        <div className="flex items-center gap-2 min-w-0 flex-1">
                                            <Badge className="text-[10px] py-0 bg-slate-800 text-slate-400 border-slate-700 capitalize shrink-0">
                                                {entity.type}
                                            </Badge>
                                            <span className="text-sm text-slate-300 truncate">{entity.title}</span>
                                        </div>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-6 w-6 text-slate-600 hover:text-red-400 shrink-0"
                                            onClick={async () => {
                                                await unlinkIntel.mutateAsync({ itemId, entityType: entity.type, entityId: entity.id });
                                                toast.success('Unlinked');
                                            }}
                                        >
                                            <Trash2 className="h-3 w-3" />
                                        </Button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Meta */}
                    <div className="flex items-center gap-4 text-xs text-slate-500 border-t border-slate-800 pt-3">
                        <span>Created {formatTimeAgo(item.created_at)}</span>
                        {item.published_at && <span>Published {formatTimeAgo(item.published_at)}</span>}
                    </div>
                </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}

/**
 * engagements/[id]/evidence/[eid]/page.tsx — Evidence Detail Page
 *
 * View and manage a single evidence attachment. Features:
 *  - Image preview with lightbox and inline ImageEditor (crop/annotate)
 *  - Editable description, toggle "include in report" status
 *  - File metadata sidebar (uploader, date, size, MIME type)
 *  - Linked-items cards (finding, test case, engagement)
 *  - Discussion section (threaded comments per evidence)
 *  - Real-time presence indicator via WebSocket
 *
 * Supports context-aware back navigation via ?source= query param.
 */
'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useParams } from '@/lib/hooks/use-params';
import DashboardLayout from '@/components/layout/dashboard-layout';
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    CardDescription
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import {
    ArrowLeft,
    Loader2,
    FileIcon,
    Download,
    Trash2,
    Shield,
    User,
    Calendar,
    HardDrive,
    ExternalLink,
    CheckCircle2,
    XCircle,
    MessageSquare,
    Image as ImageIcon,
    FileText,
    Bug,
    CheckSquare,
    ClipboardCheck,
    Link2,
    ImageOff,
    Camera
} from 'lucide-react';
import { useEvidence, getEvidenceUrl, useDeleteEvidence, useUpdateEvidence, useReplaceEvidenceFile, useEvidenceExif, useStripExif } from '@/lib/hooks/use-evidence';
import { getEvidenceDownloadUrl } from '@/lib/evidence-download';
import { useUsers } from '@/lib/hooks/use-users';
import ImageEditor from '@/components/ui/image-editor';
import { UserAvatar } from '@/components/ui/user-avatar';
import { useEngagement } from '@/lib/hooks/use-engagements';
import DiscussionSection from '@/components/discussions/discussion-section';
import { ResourceType } from '@/lib/hooks/use-discussions';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Textarea } from '@/components/ui/textarea';
import { Pencil, Save, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { EntityClassificationField } from '@/components/marking/entity-classification-field';

export default function EvidenceDetailPage({ params }: { params: Promise<{ id: string; eid: string }> }) {
    const { id, eid } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const source = searchParams?.get('source');
    const { data: evidence, isLoading: isLoadingEvidence, error: evidenceError } = useEvidence(eid);
    const { data: engagement, isLoading: isLoadingEngagement } = useEngagement(id);

    useEffect(() => {
        if (evidenceError && (evidenceError as any).response?.status === 403) {
            router.push('/unauthorized');
        }
    }, [evidenceError, router]);

    const { activeUsers } = useCollaboration({
        resourceType: 'evidence',
        resourceId: eid,
        enabled: !!evidence
    });

    const deleteEvidence = useDeleteEvidence();
    const updateEvidence = useUpdateEvidence();
    const replaceFile = useReplaceEvidenceFile();
    const stripExif = useStripExif();
    const { data: users } = useUsers();
    const queryClient = useQueryClient();

    const { data: exifData, isLoading: isLoadingExif } = useEvidenceExif(eid, evidence?.mime_type);

    const [isEditorOpen, setIsEditorOpen] = useState(false);
    const [isLightboxOpen, setIsLightboxOpen] = useState(false);

    const [fileUrl, setFileUrl] = useState<string | null>(null);
    const [isEditingDescription, setIsEditingDescription] = useState(false);
    const [description, setDescription] = useState('');

    useEffect(() => {
        if (evidence) {
            setDescription(evidence.description || '');
        }
    }, [evidence]);

    useEffect(() => {
        if (!eid) return;
        let cancelled = false;
        getEvidenceDownloadUrl(eid).then((url) => {
            if (!cancelled) setFileUrl(url);
        }).catch(() => {});
        return () => { cancelled = true; };
    }, [eid]);

    const handleDelete = async () => {
        if (!evidence) return;
        if (confirm('Are you sure you want to delete this attachment?')) {
            try {
                await deleteEvidence.mutateAsync(evidence);
                toast.success('Attachment deleted');
                router.push(`/engagements/${id}?tab=attachments`);
            } catch (err) {
                toast.error('Failed to delete attachment');
            }
        }
    };

    const handleToggleReport = async () => {
        if (!evidence) return;
        try {
            await updateEvidence.mutateAsync({
                id: evidence.id,
                includeInReport: !evidence.include_in_report
            });
            toast.success('Reporting status updated');
        } catch (err) {
            toast.error('Failed to update reporting status');
        }
    };

    const handleClassificationChange = async (level: string | null, suffix: string | null) => {
        if (!evidence) return;
        try {
            await updateEvidence.mutateAsync({
                id: evidence.id,
                classificationLevel: level,
                classificationSuffix: suffix,
            });
            toast.success('Classification updated');
        } catch (err) {
            toast.error('Failed to update classification');
        }
    };

    const handleBack = () => {
        if (source === 'attachments') {
            router.push(`/engagements/${id}?tab=attachments`);
        } else if (source === 'finding' && evidence?.finding_id) {
            // Reconstruct the return path with context
            const returnEngagementId = searchParams?.get('returnEngagementId');
            const returnTab = searchParams?.get('returnTab');

            const queryParams = new URLSearchParams();
            if (returnEngagementId) queryParams.set('engagementId', returnEngagementId);
            if (returnTab) queryParams.set('tab', returnTab);

            const query = queryParams.toString();
            router.push(`/findings/${evidence.finding_id}${query ? `?${query}` : ''}`);
        } else {
            // Fallback logic
            if (evidence?.finding_id) {
                router.push(`/findings/${evidence.finding_id}`);
            } else {
                router.push(`/engagements/${id}?tab=attachments`);
            }
        }
    };

    if (isLoadingEvidence || isLoadingEngagement) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    if (!evidence) {
        return (
            <DashboardLayout>
                <div className="p-6 text-center text-slate-400">
                    Evidence not found
                </div>
            </DashboardLayout>
        );
    }

    const isImage = evidence.mime_type?.startsWith('image/');
    const isPDF = evidence.mime_type?.includes('pdf');

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 max-w-7xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={handleBack}
                            className="text-slate-400 hover:text-white hover:bg-slate-800"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-2xl font-bold text-white max-w-md truncate">
                                {evidence.original_filename}
                            </h1>
                            <p className="text-slate-400 text-sm mt-0.5">
                                {engagement?.name}
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-4 relative z-30">
                        {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}
                        <div className="h-8 w-[1px] bg-slate-800" />
                        <div className="flex items-center gap-2">
                            {isImage && (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-9 border-primary/30 bg-primary/5 text-primary hover:bg-primary/10 hover:text-primary/80"
                                    onClick={() => setIsEditorOpen(true)}
                                >
                                    <Pencil className="h-4 w-4 mr-2" />
                                    Edit Image
                                </Button>
                            )}
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-9 border-slate-700 text-slate-400 hover:text-white"
                                onClick={() => fileUrl && window.open(fileUrl, '_blank')}
                            >
                                <Download className="h-4 w-4 mr-2" />
                                Download
                            </Button>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-9 w-9 text-slate-500 hover:text-red-400 hover:bg-red-400/10"
                                onClick={handleDelete}
                            >
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Main Content: Preview */}
                    <div className="lg:col-span-2 space-y-6">
                        <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-sm overflow-hidden min-h-[500px] flex flex-col">
                            <CardHeader className="border-b border-slate-800 bg-slate-900/60 flex flex-row items-center justify-between py-3">
                                <div className="flex items-center gap-2">
                                    {isImage ? <ImageIcon className="h-4 w-4 text-primary" /> : <FileText className="h-4 w-4 text-blue-400" />}
                                    <span className="text-sm font-medium text-slate-300">File Preview</span>
                                </div>
                            </CardHeader>
                            <CardContent className="flex-1 p-0 flex items-center justify-center bg-slate-950/50">
                                {fileUrl ? (
                                    isImage ? (
                                        <div
                                            className="cursor-zoom-in w-full h-full flex items-center justify-center"
                                            onClick={() => setIsLightboxOpen(true)}
                                        >
                                            <img
                                                src={fileUrl}
                                                alt={evidence.original_filename}
                                                className="max-w-full max-h-full object-contain p-4"
                                            />
                                        </div>
                                    ) : (
                                        <div className="flex flex-col items-center gap-4 text-slate-500 py-20 px-6 max-w-md text-center">
                                            <div className="h-20 w-20 rounded-2xl bg-slate-900 flex items-center justify-center border border-slate-800">
                                                <FileIcon className="h-10 w-10 opacity-40" />
                                            </div>
                                            <div className="space-y-1">
                                                <p className="font-semibold text-slate-300">Preview Not Available</p>
                                                <p className="text-sm">Previews are currently limited to image files. Please download this attachment to view its contents.</p>
                                            </div>
                                            <Button
                                                variant="outline"
                                                className="mt-4 border-slate-800"
                                                onClick={() => window.open(fileUrl, '_blank')}
                                            >
                                                <Download className="h-4 w-4 mr-2" />
                                                Download {evidence.original_filename}
                                            </Button>
                                        </div>
                                    )
                                ) : (
                                    <Loader2 className="h-8 w-8 animate-spin text-slate-700" />
                                )}
                            </CardContent>
                        </Card>

                        {/* Discussion Section */}
                        <div className="bg-slate-900/30 rounded-xl border border-slate-800/50 p-6">
                            <DiscussionSection
                                engagementId={id}
                                resourceType={"evidence" as ResourceType}
                                resourceId={eid}
                            />
                        </div>
                    </div>

                    {/* Sidebar: Metadata */}
                    <div className="space-y-6">
                        <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-sm sticky top-6">
                            <CardHeader>
                                <CardTitle className="text-lg text-white">Attachment Details</CardTitle>
                                <CardDescription>Operational metadata and context</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                {/* Context & Report Status */}
                                <div className="flex items-center gap-2 flex-wrap">
                                    <Badge variant="outline" className="text-[10px] uppercase tracking-wider bg-slate-800 text-slate-400 border-slate-700">
                                        {evidence.finding_id ? 'Finding Attachment' : evidence.testcase_id ? 'Test Case Attachment' : 'Mission Attachment'}
                                    </Badge>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className={cn(
                                            "h-7 text-xs border-slate-700",
                                            evidence.include_in_report ? "text-green-400 bg-green-400/5 hover:bg-green-400/10" : "text-slate-400 hover:text-white"
                                        )}
                                        onClick={handleToggleReport}
                                    >
                                        {evidence.include_in_report ? <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> : <XCircle className="h-3.5 w-3.5 mr-1.5" />}
                                        {evidence.include_in_report ? 'In Report' : 'Excluded'}
                                    </Button>
                                </div>

                                {/* Description */}
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-slate-400 text-[10px] uppercase font-bold tracking-wider">Description</Label>
                                        {!isEditingDescription ? (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-6 w-6 p-0 text-slate-500 hover:text-white"
                                                onClick={() => setIsEditingDescription(true)}
                                            >
                                                <Pencil className="h-3 w-3" />
                                            </Button>
                                        ) : (
                                            <div className="flex items-center gap-1">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-6 w-6 p-0 text-green-400 hover:text-green-300"
                                                    onClick={async () => {
                                                        try {
                                                            await updateEvidence.mutateAsync({
                                                                id: evidence.id,
                                                                description: description
                                                            });
                                                            // Explicitly invalidate the engagement evidence list to ensure freshness on return
                                                            queryClient.invalidateQueries({ queryKey: ['engagements', id, 'evidence'] });
                                                            toast.success('Description updated');
                                                            setIsEditingDescription(false);
                                                        } catch (err) {
                                                            toast.error('Failed to update description');
                                                        }
                                                    }}
                                                >
                                                    <Save className="h-3 w-3" />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-6 w-6 p-0 text-slate-500 hover:text-slate-300"
                                                    onClick={() => {
                                                        setDescription(evidence.description || '');
                                                        setIsEditingDescription(false);
                                                    }}
                                                >
                                                    <X className="h-3 w-3" />
                                                </Button>
                                            </div>
                                        )}
                                    </div>

                                    {isEditingDescription ? (
                                        <Textarea
                                            value={description}
                                            onChange={(e) => setDescription(e.target.value)}
                                            className="min-h-[100px] bg-slate-950 border-slate-700 text-sm text-slate-200 resize-none focus-visible:ring-primary"
                                            placeholder="Add a description..."
                                        />
                                    ) : (
                                        <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/50 text-sm text-slate-200">
                                            {evidence.description || (
                                                <span className="text-slate-500 italic">No description provided.</span>
                                            )}
                                        </div>
                                    )}
                                </div>

                                {/* Classification (portion marking) */}
                                <div className="space-y-1.5">
                                    <EntityClassificationField
                                        engagementId={id}
                                        level={evidence.classification_level || null}
                                        suffix={evidence.classification_suffix || null}
                                        inheritLabel="Inherit (from finding / engagement)"
                                        label="Classification"
                                        onChange={handleClassificationChange}
                                    />
                                </div>

                                {/* Metadata Grid */}
                                <div className="space-y-4">
                                    <div className="flex items-center gap-4">
                                        <UserAvatar
                                            user={users?.find(u => u.id === evidence.created_by) as any}
                                            userId={evidence.created_by}
                                            username={evidence.created_by_username}
                                            className="h-10 w-10"
                                        />
                                        <div>
                                            <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Uploaded By</p>
                                            <p className="text-sm text-slate-200">{evidence.created_by_username || evidence.created_by}</p>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-4">
                                        <div className="h-10 w-10 rounded-lg bg-slate-800 flex items-center justify-center text-slate-400 shrink-0">
                                            <Calendar className="h-5 w-5" />
                                        </div>
                                        <div>
                                            <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Date Added</p>
                                            <p className="text-sm text-slate-200">
                                                {format(new Date(evidence.created_at), 'PPPp')}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-4">
                                        <div className="h-10 w-10 rounded-lg bg-slate-800 flex items-center justify-center text-slate-400 shrink-0">
                                            <HardDrive className="h-5 w-5" />
                                        </div>
                                        <div>
                                            <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">File Size</p>
                                            <p className="text-sm text-slate-200">
                                                {(evidence.file_size / 1024).toFixed(2)} KB
                                            </p>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-4">
                                        <div className="h-10 w-10 rounded-lg bg-slate-800 flex items-center justify-center text-slate-400 shrink-0">
                                            <Shield className="h-5 w-5" />
                                        </div>
                                        <div>
                                            <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">MIME Type</p>
                                            <p className="text-sm text-slate-200">{evidence.mime_type || 'Unknown'}</p>
                                        </div>
                                    </div>
                                </div>

                                {/* EXIF Metadata */}
                                {isImage && (
                                    <div className="pt-4 border-t border-slate-800 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <Label className="text-slate-400 text-[10px] uppercase font-bold tracking-wider">EXIF Data</Label>
                                            {exifData?.has_exif && (
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    className="h-6 text-[10px] bg-red-500/10 text-red-400 border-red-500/20 hover:bg-red-500/20 hover:text-red-300"
                                                    disabled={stripExif.isPending}
                                                    onClick={async () => {
                                                        if (confirm('This will permanently remove all EXIF metadata except Date Taken. Continue?')) {
                                                            try {
                                                                await stripExif.mutateAsync(eid);
                                                                toast.success('EXIF data stripped successfully');
                                                                // The URL will auto-update if we add a cache buster, or we can just let it be since EXIF doesn't affect pixels
                                                            } catch (err) {
                                                                toast.error('Failed to strip EXIF data');
                                                            }
                                                        }
                                                    }}
                                                >
                                                    {stripExif.isPending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <ImageOff className="h-3 w-3 mr-1" />}
                                                    Strip EXIF
                                                </Button>
                                            )}
                                        </div>

                                        {isLoadingExif ? (
                                            <div className="flex items-center gap-2 text-slate-500 text-sm">
                                                <Loader2 className="h-3 w-3 animate-spin" />
                                                Loading EXIF...
                                            </div>
                                        ) : exifData?.has_exif ? (
                                            <div className="grid grid-cols-1 gap-2 bg-slate-950/50 p-3 rounded-lg border border-slate-800">
                                                {/* Prioritize important fields first */}
                                                {(exifData.exif.DateTimeOriginal || exifData.exif.DateTime) && (
                                                    <div className="flex flex-col gap-0.5">
                                                        <span className="text-[9px] uppercase font-bold text-slate-500">Date Taken</span>
                                                        <span className="text-xs text-slate-300">{exifData.exif.DateTimeOriginal || exifData.exif.DateTime}</span>
                                                    </div>
                                                )}
                                                {exifData.exif.Make && (
                                                    <div className="flex flex-col gap-0.5">
                                                        <span className="text-[9px] uppercase font-bold text-slate-500">Camera</span>
                                                        <span className="text-xs text-slate-300">{exifData.exif.Make} {exifData.exif.Model}</span>
                                                    </div>
                                                )}
                                                {exifData.exif.Software && (
                                                    <div className="flex flex-col gap-0.5">
                                                        <span className="text-[9px] uppercase font-bold text-slate-500">Software</span>
                                                        <span className="text-xs text-slate-300">{exifData.exif.Software}</span>
                                                    </div>
                                                )}
                                                {/* Hidden bucket for the rest to keep UI clean, could add an expander but keep it simple for now */}
                                                <div className="flex flex-col gap-0.5 mt-2 pt-2 border-t border-slate-800/50">
                                                    <span className="text-[9px] uppercase font-bold text-slate-500 mb-1">Other Tags ({Object.keys(exifData.exif).length})</span>
                                                    <div className="max-h-24 overflow-y-auto text-[10px] text-slate-400 font-mono scrollbar-thin scrollbar-thumb-slate-700">
                                                        {Object.entries(exifData.exif)
                                                            .filter(([k]) => !['DateTimeOriginal', 'DateTime', 'Make', 'Model', 'Software'].includes(k))
                                                            .map(([k, v]) => (
                                                                <div key={k} className="flex gap-2">
                                                                    <span className="text-slate-500 min-w-[80px]">{k}:</span>
                                                                    <span className="truncate" title={String(v)}>{String(v)}</span>
                                                                </div>
                                                            ))
                                                        }
                                                    </div>
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="text-xs text-slate-500 italic p-3 bg-slate-900/30 rounded-lg border border-slate-800/50">
                                                No EXIF data found.
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Linked Items */}
                                {(evidence.finding_id || evidence.testcase_id || evidence.engagement_id) && (
                                    <div className="pt-4 border-t border-slate-800 space-y-3">
                                        <Label className="text-slate-400 text-[10px] uppercase font-bold tracking-wider">Linked Items</Label>
                                        <div className="space-y-2">
                                            {evidence.finding_id && (
                                                <button
                                                    className="w-full flex items-center gap-3 p-3 rounded-lg bg-red-500/5 border border-red-500/10 hover:bg-red-500/10 hover:border-red-500/20 transition-all group text-left"
                                                    onClick={() => router.push(`/findings/${evidence.finding_id}?engagementId=${id}`)}
                                                >
                                                    <div className="h-8 w-8 rounded-lg bg-red-500/10 flex items-center justify-center text-red-400 shrink-0">
                                                        <Bug className="h-4 w-4" />
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-[10px] uppercase font-bold text-red-500/60 tracking-wider">Finding</p>
                                                        <p className="text-sm text-red-400 group-hover:text-red-300 truncate">
                                                            {evidence.finding_title || 'View Finding'}
                                                        </p>
                                                    </div>
                                                    <ExternalLink className="h-3.5 w-3.5 text-red-500/30 ml-auto shrink-0 group-hover:text-red-400" />
                                                </button>
                                            )}
                                            {evidence.testcase_id && (
                                                <button
                                                    className="w-full flex items-center gap-3 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/10 hover:bg-emerald-500/10 hover:border-emerald-500/20 transition-all group text-left"
                                                    onClick={() => router.push(`/testcases/${evidence.testcase_id}?engagementId=${id}`)}
                                                >
                                                    <div className="h-8 w-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-400 shrink-0">
                                                        <CheckSquare className="h-4 w-4" />
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-[10px] uppercase font-bold text-emerald-500/60 tracking-wider">Test Case</p>
                                                        <p className="text-sm text-emerald-400 group-hover:text-emerald-300 truncate">
                                                            {evidence.testcase_title || 'View Test Case'}
                                                        </p>
                                                    </div>
                                                    <ExternalLink className="h-3.5 w-3.5 text-emerald-500/30 ml-auto shrink-0 group-hover:text-emerald-400" />
                                                </button>
                                            )}
                                            {evidence.engagement_id && engagement && (
                                                <button
                                                    className="w-full flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/10 hover:bg-primary/10 hover:border-primary/20 transition-all group text-left"
                                                    onClick={() => router.push(`/engagements/${evidence.engagement_id}`)}
                                                >
                                                    <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary shrink-0">
                                                        <ClipboardCheck className="h-4 w-4" />
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-[10px] uppercase font-bold text-primary/60 tracking-wider">Engagement</p>
                                                        <p className="text-sm text-primary group-hover:text-primary/80 truncate">
                                                            {engagement.name}
                                                        </p>
                                                    </div>
                                                    <ExternalLink className="h-3.5 w-3.5 text-primary/30 ml-auto shrink-0 group-hover:text-primary" />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>
                </div>

                {/* Image Editor Modal */}
                {isImage && fileUrl && (
                    <ImageEditor
                        open={isEditorOpen}
                        onClose={() => setIsEditorOpen(false)}
                        imageUrl={fileUrl}
                        filename={evidence.original_filename}
                        onSave={async (blob) => {
                            await replaceFile.mutateAsync({ id: evidence.id, file: blob });
                            const url = await getEvidenceDownloadUrl(eid, true);
                            setFileUrl(url);
                            setIsEditorOpen(false);
                            toast.success('Image saved successfully');
                        }}
                    />
                )}

                {/* Lightbox Modal */}
                {isImage && fileUrl && (
                    <Dialog open={isLightboxOpen} onOpenChange={setIsLightboxOpen}>
                        <DialogContent className="max-w-[95vw] w-[95vw] max-h-[95vh] h-[95vh] p-0 bg-black/95 border-slate-800 overflow-hidden flex items-center justify-center">
                            <button
                                onClick={() => setIsLightboxOpen(false)}
                                className="absolute top-4 right-4 z-50 h-10 w-10 rounded-full bg-slate-900/80 hover:bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center transition-colors"
                            >
                                <X className="h-5 w-5" />
                            </button>
                            <img
                                src={fileUrl}
                                alt={evidence.original_filename}
                                className="max-w-full max-h-full object-contain p-4"
                            />
                        </DialogContent>
                    </Dialog>
                )}
            </div>
        </DashboardLayout>
    );
}

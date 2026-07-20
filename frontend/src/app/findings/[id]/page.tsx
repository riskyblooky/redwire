/**
 * findings/[id]/page.tsx — Finding Detail Page
 *
 * Comprehensive read-only view of a single finding. Layout:
 *  - Main column: executive summary (Markdown), technical analysis
 *    (impact, steps to reproduce, payload), mitigations, references,
 *    and an evidence gallery with upload capability.
 *  - Sidebar: CVSS 3.1 score widget, status control dropdown,
 *    affected-assets list with per-asset remediation checkboxes
 *    and a progress bar, linked test cases, vault items, cleanup
 *    artifacts, notes, and intel items.
 *  - Full-width discussion section at the bottom.
 *
 * Includes two remediation prompt dialogs:
 *  1. Triggered when the last asset checkbox is ticked (auto-suggest REMEDIATED).
 *  2. Triggered when selecting REMEDIATED status with unremediated assets
 *     (bulk-remediate all assets first).
 *
 * Real-time presence via WebSocket; version history panel; permission-gated
 * edit/delete actions with context-aware back navigation.
 */
'use client';

import { useParams } from '@/lib/hooks/use-params';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog';
import {
    ArrowLeft, Edit, Trash2, Bug, Calendar, User,
    ShieldAlert, AlertTriangle, AlertCircle, Info,
    ExternalLink, CheckCircle2, XCircle, Clock, Loader2, Target,
    Terminal, FileText, Shield, Layers, BookOpen, Share2, Plus, Lock, Key, Sparkles, StickyNote, ClipboardCheck, Radar,
    ChevronDown, ChevronRight,
    Circle, Eye, Wrench, Copy, Check
} from 'lucide-react';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useFinding, useUpdateFinding, useDeleteFinding } from '@/lib/hooks/use-findings';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { useEngagement } from '@/lib/hooks/use-engagements';
import { useAuthStore } from '@/stores/auth-store';
import Link from 'next/link';
import { EvidenceUpload } from '@/components/findings/evidence-upload';
import { EvidenceCard } from '@/components/findings/evidence-card';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { cn } from '@/lib/utils';
import DiscussionSection from '@/components/discussions/discussion-section';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { VersionHistoryPanel } from '@/components/ui/version-history-panel';
import { UserAvatar } from '@/components/ui/user-avatar';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { toast } from 'sonner';
import { CleanupDetailModal } from '@/components/engagements/cleanup-detail-modal';
import { useNotes } from '@/lib/hooks/use-notes';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';
import { LinkEntityDialog, LinkedIdMap } from '@/components/ui/link-entity-dialog';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { CustomFieldsDisplay } from '@/components/custom-fields/custom-fields-display';
import { ChainLinksSection } from '@/components/engagements/chain-links-section';
import { TECHNIQUE_MAP } from '@/lib/attack-data';
import {
    useLinkFindingToTestCase, useUnlinkFindingFromTestCase,
    useLinkFindingToVaultItem, useUnlinkFindingFromVaultItem,
    useLinkFindingToCleanup, useUnlinkFindingFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { Link as LinkIcon } from 'lucide-react';

const severityColors: Record<string, string> = {
    CRITICAL: 'bg-red-500/10 text-red-500 border-red-500/20',
    HIGH: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
    MEDIUM: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
    LOW: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    INFO: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

const statusColors: Record<string, string> = {
    OPEN: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    IN_REVIEW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    VERIFIED: 'bg-green-500/10 text-green-400 border-green-500/20',
    REMEDIATED: 'bg-teal-500/10 text-teal-400 border-teal-500/20',
    CLOSED: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

const statusOptions: { value: string; label: string; Icon: React.ComponentType<{ className?: string }>; iconClass: string }[] = [
    { value: 'OPEN', label: 'Open', Icon: Circle, iconClass: 'text-primary' },
    { value: 'IN_REVIEW', label: 'In Review', Icon: Eye, iconClass: 'text-blue-400' },
    { value: 'VERIFIED', label: 'Verified', Icon: CheckCircle2, iconClass: 'text-green-400' },
    { value: 'REMEDIATED', label: 'Remediated', Icon: Wrench, iconClass: 'text-teal-400' },
    { value: 'CLOSED', label: 'Closed', Icon: Lock, iconClass: 'text-slate-400' },
];

const assetTypeColors: Record<string, string> = {
    IP_ADDRESS: 'text-blue-400 border-blue-500/30 bg-blue-500/10',
    DOMAIN: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
    URL: 'text-purple-400 border-purple-500/30 bg-purple-500/10',
    CLOUD_RESOURCE: 'text-sky-400 border-sky-500/30 bg-sky-500/10',
    OTHER: 'text-slate-400 border-slate-500/30 bg-slate-500/10',
};

export default function FindingDetailPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const returnEngagementId = searchParams?.get('engagementId');
    const returnTab = searchParams?.get('tab') || 'findings';
    const { user } = useAuthStore();

    const { data: finding, isLoading, error } = useFinding(id);
    const { data: engagement } = useEngagement(finding?.engagement_id || '');
    const updateFinding = useUpdateFinding();
    const deleteFinding = useDeleteFinding();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const [viewCleanup, setViewCleanup] = useState<any>(null);
    const [isEvidenceCollapsed, setIsEvidenceCollapsed] = useState(false);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);
    const [copiedCvss, setCopiedCvss] = useState(false);

    const copyCvssVector = async (vector: string) => {
        try {
            await navigator.clipboard.writeText(vector);
            setCopiedCvss(true);
            toast.success('CVSS vector copied');
            setTimeout(() => setCopiedCvss(false), 1500);
        } catch {
            toast.error('Failed to copy');
        }
    };

    // Link/unlink hooks for finding
    const linkTC = useLinkFindingToTestCase();
    const unlinkTC = useUnlinkFindingFromTestCase();
    const linkVault = useLinkFindingToVaultItem();
    const unlinkVault = useUnlinkFindingFromVaultItem();
    const linkCleanup = useLinkFindingToCleanup();
    const unlinkCleanup = useUnlinkFindingFromCleanup();

    const handleEntityLink = async (type: import('@/components/ui/link-entity-dialog').LinkResourceType, resourceId: string) => {
        if (type === 'testcases') await linkTC.mutateAsync({ entityId: id, resourceId });
        if (type === 'vault') await linkVault.mutateAsync({ entityId: id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: id, resourceId });
    };
    const handleEntityUnlink = async (type: import('@/components/ui/link-entity-dialog').LinkResourceType, resourceId: string) => {
        if (type === 'testcases') await unlinkTC.mutateAsync({ entityId: id, resourceId });
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: id, resourceId });
    };
    const queryClient = useQueryClient();

    // Remediation prompt dialog (from last-asset check)
    const [showRemediatePrompt, setShowRemediatePrompt] = useState(false);
    // Remediation prompt dialog (from status dropdown)
    const [showStatusRemediatePrompt, setShowStatusRemediatePrompt] = useState(false);

    // Toggle asset remediation with optimistic updates
    const toggleRemediation = useMutation({
        mutationFn: async ({ findingId, assetId }: { findingId: string; assetId: string }) => {
            const { data } = await api.patch(`/findings/${findingId}/assets/${assetId}/remediate`);
            return data;
        },
        onMutate: async ({ assetId }) => {
            // Cancel any outgoing refetches so they don't overwrite our optimistic update
            await queryClient.cancelQueries({ queryKey: ['findings', id] });

            // Snapshot previous value
            const previousFinding = queryClient.getQueryData(['findings', id]);

            // Optimistically update the cache immediately
            queryClient.setQueryData(['findings', id], (old: any) => {
                if (!old) return old;
                const updatedAssets = (old.assets || []).map((a: any) =>
                    a.id === assetId ? { ...a, remediated: !a.remediated } : a
                );
                return { ...old, assets: updatedAssets };
            });

            return { previousFinding };
        },
        onSuccess: (data) => {
            // Sync with server data
            queryClient.invalidateQueries({ queryKey: ['findings', id] });
            toast.success(data.remediated ? 'Asset marked as remediated' : 'Asset remediation reverted');

            // Check if ALL assets are now remediated using latest cache data
            const cached: any = queryClient.getQueryData(['findings', id]);
            if (cached && data.remediated) {
                const allRemediated = (cached.assets || []).every((a: any) => a.remediated);
                const totalAssets = (cached.assets || []).length;
                if (allRemediated && totalAssets > 0 && cached.status !== 'REMEDIATED') {
                    setShowRemediatePrompt(true);
                }
            }
        },
        onError: (_err, _vars, context) => {
            // Rollback on error
            if (context?.previousFinding) {
                queryClient.setQueryData(['findings', id], context.previousFinding);
            }
            toast.error('Failed to update remediation status');
        },
    });

    // Mark finding as REMEDIATED (just status)
    const markRemediated = useMutation({
        mutationFn: async () => {
            await updateFinding.mutateAsync({ id, status: 'REMEDIATED' });
        },
        onSuccess: () => {
            toast.success('Finding marked as Remediated');
            setShowRemediatePrompt(false);
        },
        onError: () => {
            toast.error('Failed to update finding status');
        },
    });

    // Mark ALL assets remediated + set finding status to REMEDIATED
    const markAllAssetsAndRemediate = useMutation({
        mutationFn: async () => {
            const unremediated = (finding?.assets || []).filter((a: any) => !a.remediated);
            for (const asset of unremediated) {
                await api.patch(`/findings/${id}/assets/${asset.id}/remediate`);
            }
            await updateFinding.mutateAsync({ id, status: 'REMEDIATED' });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['findings', id] });
            toast.success('All assets remediated and finding marked as Remediated');
            setShowStatusRemediatePrompt(false);
        },
        onError: () => {
            toast.error('Failed to update remediation status');
        },
    });

    // Get notes linked to this finding
    const { data: allNotes = [] } = useNotes(finding?.engagement_id || '');
    const linkedNotes = allNotes.filter(n => n.linked_findings?.some(f => f.id === id));

    // Get intel items linked to this finding
    const { data: linkedIntel = [] } = useIntelByEntity('finding', id);
    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);

    const { activeUsers } = useCollaboration({
        resourceType: 'finding',
        resourceId: id,
        enabled: !!finding
    });

    // Check permissions for edit/delete
    const canEdit = useCanEdit(finding?.engagement_id, 'finding', finding?.created_by);
    const canDelete = useCanDelete(finding?.engagement_id, 'finding', finding?.created_by);

    const handleStatusChange = async (newStatus: string) => {
        // If selecting REMEDIATED and there are unremediated assets, prompt
        if (newStatus === 'REMEDIATED' && finding) {
            const unremediated = (finding.assets || []).filter((a: any) => !a.remediated);
            if (unremediated.length > 0) {
                setShowStatusRemediatePrompt(true);
                return;
            }
        }
        // Warn before verifying a finding that still has unresolved discussion threads
        if (newStatus === 'VERIFIED' && finding && (finding.unresolved_thread_count || 0) > 0) {
            const count = finding.unresolved_thread_count!;
            const ok = await confirm({
                title: 'Verify finding with unresolved comments?',
                description: `This finding has ${count} unresolved discussion ${count === 1 ? 'thread' : 'threads'}. Marking it Verified now will leave ${count === 1 ? 'that thread' : 'those threads'} open. Continue anyway?`,
                confirmLabel: 'Verify anyway',
                variant: 'warning',
            });
            if (!ok) return;
        }
        try {
            await updateFinding.mutateAsync({ id: id, status: newStatus });
            toast.success(`Status updated to ${newStatus.replace('_', ' ')}`);
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to update finding status'));
        }
    };

    const handleDelete = async () => {
        const confirmed = await confirm({
            title: 'Delete Finding',
            description: 'Are you sure you want to delete this finding? This cannot be undone.',
        });
        if (!confirmed) return;

        try {
            await deleteFinding.mutateAsync(id);
            const redirectPath = returnEngagementId
                ? `/engagements/${returnEngagementId}?tab=${returnTab}`
                : '/findings';
            router.push(redirectPath);
        } catch (error: any) {
            console.error('Failed to delete finding:', error);
            toast.error(getErrorMessage(error, 'Failed to delete finding'));
        }
    };

    if (isLoading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-red-500" />
                </div>
            </DashboardLayout>
        );
    }

    if (error || !finding) {
        return (
            <DashboardLayout>
                <div className="p-6 text-center text-red-400">Finding not found.</div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                                const backPath = returnEngagementId
                                    ? `/engagements/${returnEngagementId}?tab=${returnTab}`
                                    : '/findings';
                                router.push(backPath);
                            }}
                            className="text-slate-400 hover:text-white"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <div className="flex items-center gap-3">
                                <h1 className="text-3xl font-bold text-white tracking-tight">{finding.title}</h1>
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                                <Badge className={cn("px-2 py-0.5", severityColors[finding.severity])}>{finding.severity}</Badge>
                                <Badge variant="outline" className={cn("px-2 py-0.5", statusColors[finding.status])}>{finding.status.replace('_', ' ')}</Badge>
                                {finding.category && (
                                    <Badge variant="secondary" className="bg-slate-800 text-slate-400 border-none font-medium px-2 py-0.5">{finding.category}</Badge>
                                )}
                                {finding.tags?.map(tag => (
                                    <Badge
                                        key={tag.id}
                                        variant="outline"
                                        className="px-2 py-0.5 border-none font-bold text-[10px] uppercase tracking-wider"
                                        style={{ backgroundColor: `${tag.color}20`, color: tag.color }}
                                    >
                                        {tag.name}
                                    </Badge>
                                ))}
                                {engagement && (
                                    <Link href={`/engagements/${engagement.id}?tab=${returnTab}`} className="text-sm text-primary hover:underline flex items-center gap-1 ml-2">
                                        <Target className="h-3 w-3" /> {engagement.name}
                                    </Link>
                                )}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-4 relative z-30">
                        {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}
                        <VersionHistoryPanel entityType="finding" entityId={id} currentData={finding} />
                        <div className="h-8 w-px bg-slate-800" />
                        <div className="flex gap-2">
                            {canEdit && (
                                <Button
                                    onClick={() => {
                                        const query = returnEngagementId ? `?engagementId=${returnEngagementId}&tab=${returnTab}` : '';
                                        router.push(`/findings/${id}/edit${query}`);
                                    }}
                                    variant="outline"
                                    className="border-slate-700 text-slate-300"
                                >
                                    <Edit className="h-4 w-4 mr-2" /> Edit
                                </Button>
                            )}
                            {canDelete && (
                                <Button onClick={handleDelete} variant="outline" className="border-red-500/20 text-red-400 hover:bg-red-500/10">
                                    <Trash2 className="h-4 w-4 mr-2" /> Delete
                                </Button>
                            )}
                        </div>
                    </div>
                </div>

                <div className="grid gap-6 lg:grid-cols-4">
                    <div className="lg:col-span-3 space-y-6">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs overflow-hidden">
                            <div className={cn("h-1.5 w-full",
                                finding.severity === 'CRITICAL' ? 'bg-red-600' :
                                    finding.severity === 'HIGH' ? 'bg-orange-500' :
                                        finding.severity === 'MEDIUM' ? 'bg-amber-500' : 'bg-blue-500'
                            )} />
                            <CardContent className="p-0">
                                <div className="p-8 space-y-10">
                                    {/* Description Section */}
                                    <section>
                                        <div className="flex items-center gap-2 mb-4 text-white">
                                            <FileText className="h-5 w-5 text-red-400" />
                                            <h3 className="text-xl font-bold tracking-tight">Executive Summary</h3>
                                        </div>
                                        <div className="prose prose-invert max-w-none prose-slate">
                                            <MarkdownPreview value={finding.description} theme="dark" />
                                        </div>
                                    </section>

                                    <Separator className="bg-slate-800/60" />

                                    {/* Tech Details Section */}
                                    <section className="space-y-8">
                                        <div className="flex items-center gap-2 mb-2 text-white">
                                            <Terminal className="h-5 w-5 text-blue-400" />
                                            <h3 className="text-xl font-bold tracking-tight">Technical Analysis</h3>
                                        </div>

                                        <div className="space-y-6">
                                            {finding.impact && (
                                                <div className="space-y-2">
                                                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                                                        <ShieldAlert className="h-3 w-3" /> Potential Impact
                                                    </h4>
                                                    <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-4 rounded-lg border border-slate-800/50">
                                                        <MarkdownPreview value={finding.impact} theme="dark" />
                                                    </div>
                                                </div>
                                            )}

                                            {finding.steps_to_reproduce && (
                                                <div className="space-y-2">
                                                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Steps to Reproduce</h4>
                                                    <div className="bg-slate-950 p-2 rounded-xl border border-slate-800 shadow-inner overflow-hidden">
                                                        <MarkdownPreview value={finding.steps_to_reproduce} theme="dark" />
                                                    </div>
                                                </div>
                                            )}

                                            {finding.technical_details && (
                                                <div className="space-y-2">
                                                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Additional Evidence / Payload</h4>
                                                    <div className="bg-slate-950 p-2 rounded-xl border border-slate-800 shadow-inner overflow-hidden">
                                                        <MarkdownPreview value={finding.technical_details} theme="dark" />
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </section>

                                    <Separator className="bg-slate-800/60" />

                                    {/* Remediation Section */}
                                    <section>
                                        <div className="flex items-center gap-2 mb-4 text-white">
                                            <Shield className="h-5 w-5 text-green-400" />
                                            <h3 className="text-xl font-bold tracking-tight">Mitigation & Remediation</h3>
                                        </div>
                                        <div className="bg-green-500/5 border border-green-500/20 p-2 rounded-xl shadow-[0_0_20px_rgba(34,197,94,0.03)] overflow-hidden">
                                            <MarkdownPreview value={finding.mitigations || ''} theme="dark" />
                                        </div>
                                    </section>

                                    {finding.references && (
                                        <>
                                            <Separator className="bg-slate-800/60" />
                                            <section>
                                                <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">External References</h3>
                                                <div className="bg-slate-950/40 p-2 rounded-lg border border-slate-800/40 overflow-hidden">
                                                    <MarkdownPreview value={finding.references || ''} theme="dark" />
                                                </div>
                                            </section>
                                        </>
                                    )}
                                    <CustomFieldsDisplay
                                        entity="finding"
                                        value={finding.custom_fields}
                                        className="pt-2"
                                    />
                                </div>
                            </CardContent>
                        </Card>

                        {/* Evidence */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader
                                className="pb-3 border-b border-slate-800/60 cursor-pointer select-none hover:bg-slate-800/30 transition-colors"
                                onClick={() => setIsEvidenceCollapsed(!isEvidenceCollapsed)}
                            >
                                <div className="flex items-center justify-between">
                                    <CardTitle className="text-white text-lg flex items-center gap-2">
                                        {isEvidenceCollapsed ? <ChevronRight className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
                                        <Layers className="h-4 w-4 text-primary" />
                                        Evidence
                                    </CardTitle>
                                    <Badge variant="outline" className="bg-primary/10 text-primary border-none px-1.5 h-5 text-[10px]">
                                        {finding.evidence?.length || 0} files
                                    </Badge>
                                </div>
                            </CardHeader>
                            {!isEvidenceCollapsed && (
                                <CardContent className="space-y-4 pt-4">
                                    {canEdit && (
                                        <EvidenceUpload findingId={finding.id} />
                                    )}
                                    {finding.evidence && finding.evidence.length > 0 ? (
                                        <div className="space-y-3">
                                            {finding.evidence.map((ev: any) => (
                                                <EvidenceCard key={ev.id} evidence={ev} findingId={finding.id} />
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="text-center py-8 text-slate-500 border border-dashed border-slate-800 rounded-xl bg-slate-950/20">
                                            <Plus className="h-8 w-8 mx-auto mb-2 opacity-20" />
                                            <p className="text-xs">No evidence attached</p>
                                        </div>
                                    )}
                                </CardContent>
                            )}
                        </Card>
                    </div>

                    {/* Right Sidebar */}
                    <div className="flex flex-col">
                        <Card className="border-slate-800 bg-slate-900/50 overflow-hidden relative flex-1 flex flex-col">
                            <div className="absolute top-0 right-0 p-4 opacity-5">
                                <Bug className="h-24 w-24" />
                            </div>
                            <CardHeader className="pb-4">
                                <CardTitle className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Risk Assessment</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-8">
                                <div className="flex flex-col items-center justify-center p-6 bg-slate-950/50 rounded-2xl border border-slate-800/50 shadow-inner">
                                    <span className={cn("text-5xl font-black italic tracking-tighter transition-all hover:scale-110 cursor-default",
                                        (finding.cvss_score || 0) >= 9 ? 'text-red-600 drop-shadow-[0_0_10px_rgba(220,38,38,0.3)]' :
                                            (finding.cvss_score || 0) >= 7 ? 'text-orange-500 drop-shadow-[0_0_10px_rgba(249,115,22,0.3)]' :
                                                (finding.cvss_score || 0) >= 4 ? 'text-amber-500' : 'text-blue-500'
                                    )}>
                                        {finding.cvss_score?.toFixed(1) || '0.0'}
                                    </span>
                                    <span className="text-[9px] text-slate-500 font-black uppercase mt-2 tracking-widest">CVSS v3.1 BASE</span>
                                    {finding.cvss_vector && (
                                        <button
                                            type="button"
                                            onClick={() => copyCvssVector(finding.cvss_vector!)}
                                            title="Click to copy"
                                            className="mt-3 group w-full flex items-center justify-center gap-2 text-xs text-slate-300 font-mono bg-slate-950 px-3 py-2 rounded border border-slate-800/50 hover:border-primary/40 hover:bg-slate-950/80 transition-colors break-all leading-snug"
                                        >
                                            <span className="flex-1 text-center">{finding.cvss_vector}</span>
                                            {copiedCvss
                                                ? <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                                                : <Copy className="h-3.5 w-3.5 text-slate-500 group-hover:text-primary shrink-0 transition-colors" />}
                                        </button>
                                    )}
                                </div>

                                <div className="space-y-6">
                                    <div className="space-y-3">
                                        <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Status Control</h4>
                                        <Select
                                            value={finding.status}
                                            onValueChange={handleStatusChange}
                                            disabled={!canEdit}
                                        >
                                            <SelectTrigger
                                                className={cn(
                                                    "w-full h-10 bg-slate-950/50 border-slate-800 hover:border-slate-700 focus:border-blue-500 text-xs font-semibold tracking-wide",
                                                    statusColors[finding.status],
                                                    !canEdit && "opacity-50 cursor-not-allowed"
                                                )}
                                            >
                                                <SelectValue>
                                                    {(() => {
                                                        const opt = statusOptions.find(o => o.value === finding.status);
                                                        if (!opt) return finding.status;
                                                        const I = opt.Icon;
                                                        return (
                                                            <span className="flex items-center gap-2">
                                                                <I className={cn("h-3.5 w-3.5", opt.iconClass)} />
                                                                <span className="uppercase tracking-wider">{opt.label}</span>
                                                            </span>
                                                        );
                                                    })()}
                                                </SelectValue>
                                            </SelectTrigger>
                                            <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                {statusOptions.map(({ value, label, Icon, iconClass }) => (
                                                    <SelectItem key={value} value={value} className="text-xs font-semibold focus:bg-slate-800">
                                                        <span className="flex items-center gap-2">
                                                            <Icon className={cn("h-3.5 w-3.5", iconClass)} />
                                                            <span className="uppercase tracking-wider">{label}</span>
                                                        </span>
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    <div>
                                        <div className="flex items-center justify-between mb-3">
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Affected Targets</h4>
                                            {finding.assets && finding.assets.length > 0 && (
                                                <span className={cn(
                                                    "text-[10px] font-bold tabular-nums",
                                                    (() => {
                                                        const rem = finding.assets.filter((a: any) => a.remediated).length;
                                                        const tot = finding.assets.length;
                                                        const pct = tot > 0 ? Math.round((rem / tot) * 100) : 0;
                                                        return pct === 100 ? 'text-green-400' : pct > 0 ? 'text-amber-400' : 'text-slate-500';
                                                    })()
                                                )}>
                                                    {finding.assets.filter((a: any) => a.remediated).length}/{finding.assets.length} remediated
                                                </span>
                                            )}
                                        </div>
                                        {finding.assets && finding.assets.length > 0 && (
                                            <Progress
                                                value={finding.assets.length > 0 ? Math.round((finding.assets.filter((a: any) => a.remediated).length / finding.assets.length) * 100) : 0}
                                                className={cn("h-1.5 bg-slate-800 mb-3", finding.assets.filter((a: any) => a.remediated).length === finding.assets.length && '[&>div]:bg-green-500')}
                                            />
                                        )}
                                        <div className="space-y-2">
                                            {finding.assets && finding.assets.length > 0 ? (
                                                finding.assets.map((asset: any) => {
                                                    const selectedPorts = asset.port_ids && asset.ports
                                                        ? asset.ports.filter((p: any) => asset.port_ids.includes(p.id))
                                                        : [];
                                                    return (
                                                        <div key={asset.id} className="space-y-1">
                                                            <div className={cn(
                                                                "flex items-center gap-2 p-2 rounded-lg border transition-all",
                                                                asset.remediated
                                                                    ? "bg-green-500/5 border-green-500/20"
                                                                    : "bg-slate-950/40 border-slate-800/60"
                                                            )}>
                                                                <Checkbox
                                                                    checked={asset.remediated}
                                                                    onCheckedChange={() => toggleRemediation.mutate({ findingId: id, assetId: asset.id })}
                                                                    className={cn("shrink-0", asset.remediated && "data-[state=checked]:bg-green-500 data-[state=checked]:border-green-500")}
                                                                    disabled={!canEdit}
                                                                />
                                                                <Link href={`/assets/${asset.id}`} className="flex-1 min-w-0 group" onClick={(e) => e.stopPropagation()}>
                                                                    <div className="flex items-center justify-between">
                                                                        <span className={cn(
                                                                            "text-xs font-bold truncate group-hover:text-primary transition-colors",
                                                                            asset.remediated ? "text-green-300 line-through opacity-70" : "text-white"
                                                                        )} title={asset.name}>{asset.name}</span>
                                                                        <Badge variant="outline" className={cn("text-[8px] px-1 py-0 h-4 border-none uppercase", assetTypeColors[asset.asset_type] || 'text-slate-400')}>
                                                                            {asset.asset_type?.split('_')[0]}
                                                                        </Badge>
                                                                    </div>
                                                                    <span className="text-[9px] text-slate-500 font-mono mt-0.5 block">{asset.identifier}</span>
                                                                </Link>
                                                                {asset.remediated && (
                                                                    <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                                                                )}
                                                            </div>
                                                            {selectedPorts.length > 0 && (
                                                                <div className="ml-8 flex flex-wrap gap-1">
                                                                    {selectedPorts.map((port: any) => (
                                                                        <Badge
                                                                            key={port.id}
                                                                            variant="outline"
                                                                            className={cn(
                                                                                "text-[11px] px-2 py-0.5 h-5 border-none font-mono font-bold",
                                                                                port.state === 'OPEN' ? 'bg-green-500/10 text-green-400' :
                                                                                    port.state === 'FILTERED' ? 'bg-yellow-500/10 text-yellow-400' :
                                                                                        'bg-cyan-500/10 text-cyan-400'
                                                                            )}
                                                                        >
                                                                            {port.port_number}/{port.protocol}
                                                                        </Badge>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })
                                            ) : (
                                                <div className="text-[10px] text-slate-500 italic p-3 text-center border border-dashed border-slate-800 rounded-lg">
                                                    No specific assets linked
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* ATT&CK Techniques */}
                                    {(canEdit || (finding.attack_technique_ids?.length ?? 0) > 0) && (
                                        <div className="mb-4">
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">
                                                ATT&amp;CK Techniques
                                                {(finding.attack_technique_ids?.length ?? 0) > 0 && (
                                                    <span className="text-slate-600 ml-1">({finding.attack_technique_ids?.length})</span>
                                                )}
                                            </h4>
                                            {canEdit ? (
                                                <TechniquePicker
                                                    value={finding.attack_technique_ids || []}
                                                    onChange={async (ids) => {
                                                        try {
                                                            await updateFinding.mutateAsync({ id: finding.id, attack_technique_ids: ids });
                                                        } catch (e: any) {
                                                            toast.error(getErrorMessage(e, 'Failed to update techniques'));
                                                        }
                                                    }}
                                                    placeholder="Map ATT&CK techniques…"
                                                />
                                            ) : (
                                                <div className="flex flex-wrap gap-1.5">
                                                    {(finding.attack_technique_ids || []).map((id: string) => {
                                                        const tech = TECHNIQUE_MAP.get(id);
                                                        return (
                                                            <Badge
                                                                key={id}
                                                                variant="secondary"
                                                                className="bg-purple-500/15 text-purple-400 border-purple-500/30 gap-1 text-xs"
                                                            >
                                                                <Shield className="h-3 w-3 shrink-0" />
                                                                {tech ? `${tech.id} ${tech.name}` : id}
                                                            </Badge>
                                                        );
                                                    })}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Attack Chain */}
                                    <div className="mb-4">
                                        <ChainLinksSection
                                            engagementId={finding.engagement_id}
                                            entityType="finding"
                                            entityId={finding.id}
                                            entityName={finding.title}
                                            canEdit={canEdit}
                                        />
                                    </div>
                                    <Separator className="bg-slate-800/60 mb-4" />

                                    {/* Linked Resources header with + Link button */}
                                    <div className="flex items-center justify-between mb-3">
                                        <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Linked Resources</h4>
                                        {canEdit && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-6 px-2 text-[10px] text-indigo-400 hover:text-indigo-300 hover:bg-primary/90/10 gap-1"
                                                onClick={() => setLinkDialogOpen(true)}
                                            >
                                                <LinkIcon className="h-3 w-3" />
                                                + Link
                                            </Button>
                                        )}
                                    </div>

                                    {finding.testcases && finding.testcases.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Test Cases</h4>
                                            <div className="space-y-2">
                                                {finding.testcases.map((tc: any) => (
                                                    <Link href={`/testcases/${tc.id}`} key={tc.id} className="flex items-center justify-between p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-primary/30 transition-colors group cursor-pointer hover:bg-slate-900/60">
                                                        <div className="flex items-center gap-2 min-w-0">
                                                            <ClipboardCheck className="h-3.5 w-3.5 text-blue-400 shrink-0" />
                                                            <span className="text-xs font-bold text-white group-hover:text-primary transition-colors truncate" title={tc.title}>{tc.title}</span>
                                                        </div>
                                                        <Badge variant="outline" className={cn(
                                                            "text-[8px] px-1 py-0 h-4 border-none uppercase font-bold shrink-0 ml-2",
                                                            tc.is_executed
                                                                ? (tc.is_successful ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400')
                                                                : 'bg-slate-500/10 text-slate-400'
                                                        )}>
                                                            {tc.is_executed ? (tc.is_successful ? 'Pass' : 'Fail') : 'Pending'}
                                                        </Badge>
                                                    </Link>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {finding.vault_items && finding.vault_items.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Vault Items</h4>
                                            <div className="space-y-2">
                                                {finding.vault_items.map((vi: any) => {
                                                    const icon = vi.item_type === 'CREDENTIAL' ? <Lock className="h-3.5 w-3.5 text-amber-400 shrink-0" /> :
                                                        vi.item_type === 'KEY' ? <Key className="h-3.5 w-3.5 text-primary shrink-0" /> :
                                                            <Shield className="h-3.5 w-3.5 text-emerald-400 shrink-0" />;
                                                    return (
                                                        <div key={vi.id} className="flex items-center gap-2 p-2 bg-slate-950/40 rounded-lg border border-slate-800/60">
                                                            {icon}
                                                            <span className="text-xs font-bold text-white truncate" title={vi.name}>{vi.name}</span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    )}

                                    {finding.cleanup_artifacts && finding.cleanup_artifacts.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Cleanup Artifacts</h4>
                                            <div className="space-y-2">
                                                {finding.cleanup_artifacts.map((ca: any) => (
                                                    <div key={ca.id} className="flex items-center justify-between p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 cursor-pointer hover:border-lime-500/30 hover:bg-lime-500/5 transition-colors" onClick={() => setViewCleanup(ca)}>
                                                        <div className="flex items-center gap-2 min-w-0">
                                                            <Sparkles className="h-3.5 w-3.5 text-lime-400 shrink-0" />
                                                            <span className="text-xs font-bold text-white truncate" title={ca.title}>{ca.title}</span>
                                                        </div>
                                                        <Badge variant="outline" className={cn(
                                                            "text-[8px] px-1 py-0 h-4 border-none uppercase font-bold shrink-0 ml-2",
                                                            ca.status === 'CLEANED' ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'
                                                        )}>
                                                            {ca.status}
                                                        </Badge>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {linkedNotes.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Notes</h4>
                                            <div className="space-y-2">
                                                {linkedNotes.map(note => (
                                                    <Link
                                                        key={note.id}
                                                        href={`/engagements/${finding.engagement_id}?tab=notes&noteId=${note.id}`}
                                                        className="flex items-center gap-2 p-2 rounded-lg bg-slate-950/40 border border-slate-800/60 hover:border-teal-500/30 transition-colors group"
                                                    >
                                                        <StickyNote className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                                                        <span className="text-xs font-medium text-slate-300 group-hover:text-teal-300 truncate" title={note.title}>{note.title}</span>
                                                    </Link>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {linkedIntel.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Intel</h4>
                                            <div className="space-y-2">
                                                {linkedIntel.map(item => (
                                                    <div key={item.id} className="flex items-center gap-2 p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-cyan-500/30 transition-colors group cursor-pointer"
                                                        onClick={() => setIntelDetailId(item.id)}
                                                    >
                                                        <Radar className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                                                        <div className="flex-1 min-w-0">
                                                            <span className="text-xs font-bold text-white truncate block" title={item.title}>{item.title}</span>
                                                            {item.cve_id && <span className="text-[9px] font-mono text-red-400">{item.cve_id}</span>}
                                                        </div>
                                                        {/* GHSA-7f5w-xj7p-cjj4: scheme gate defends in depth against
                                                            a legacy javascript:/data: URI that predates the backend
                                                            Pydantic validator on IntelItemCreate/Update.source_url. */}
                                                        {item.source_url && /^https?:\/\//i.test(item.source_url) && (
                                                            <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-cyan-400 transition-colors" onClick={(e) => e.stopPropagation()}>
                                                                <ExternalLink className="h-3 w-3" />
                                                            </a>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {intelDetailId && <IntelDetailDialog itemId={intelDetailId} onClose={() => setIntelDetailId(null)} />}

                                </div>
                            </CardContent>
                            <div className="mt-auto border-t border-slate-800/40 px-6 py-4 space-y-3">
                                <div className="flex items-center justify-between text-[10px]">
                                    <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                        <User className="h-3 w-3" /> Reporter
                                    </span>
                                    <div className="flex items-center gap-2">
                                        <UserAvatar
                                            user={{ id: finding.created_by, username: finding.created_by_username || finding.created_by, profile_photo: finding.created_by_profile_photo }}
                                            userId={finding.created_by}
                                            username={finding.created_by_username || finding.created_by}
                                            className="h-5 w-5"
                                        />
                                        <span className="text-slate-300 font-mono">
                                            {engagement?.assigned_users?.find((u: any) => u.id === finding.created_by)?.username || finding.created_by_username || finding.created_by.slice(0, 8)}
                                        </span>
                                    </div>
                                </div>
                                <div className="flex items-center justify-between text-[10px]">
                                    <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                        <Clock className="h-3 w-3" /> Logged
                                    </span>
                                    <span className="text-slate-300">{new Date(finding.created_at).toLocaleString()}</span>
                                </div>
                            </div>
                        </Card>



                    </div>
                </div>

                {/* Discussions - Full Width */}
                <DiscussionSection
                    engagementId={finding.engagement_id}
                    resourceType="finding"
                    resourceId={id}
                    currentUserId={user?.id}
                    isAdmin={user?.role === 'admin'}
                    users={engagement?.assigned_users}
                />

                {/* Remediation Threads - Full Width */}
                <DiscussionSection
                    engagementId={finding.engagement_id}
                    resourceType="finding_remediation"
                    resourceId={id}
                    currentUserId={user?.id}
                    isAdmin={user?.role === 'admin'}
                    users={engagement?.assigned_users}
                    title="Remediation Threads"
                    description="Track remediation progress and coordinate fixes with your team"
                />
            </div>
            <ConfirmDialog />
            <CleanupDetailModal
                artifact={viewCleanup}
                open={!!viewCleanup}
                onOpenChange={(open) => !open && setViewCleanup(null)}
            />
            <LinkEntityDialog
                open={linkDialogOpen}
                onOpenChange={setLinkDialogOpen}
                engagementId={finding.engagement_id}
                entityType="finding"
                entityId={id}
                entityName={finding.title}
                linkedIds={{
                    findings:  new Set(),
                    testcases: new Set(finding.testcases?.map((t: any) => t.id) ?? []),
                    assets:    new Set(finding.assets?.map((a: any) => a.id) ?? []),
                    vault:     new Set(finding.vault_items?.map((v: any) => v.id) ?? []),
                    cleanup:   new Set(finding.cleanup_artifacts?.map((c: any) => c.id) ?? []),
                    intel:     new Set(),
                    infra:     new Set(),
                }}
                onLink={handleEntityLink}
                onUnlink={handleEntityUnlink}
            />

            {/* Remediation Prompt Dialog — from last-asset checkbox */}
            <Dialog open={showRemediatePrompt} onOpenChange={setShowRemediatePrompt}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <CheckCircle2 className="h-5 w-5 text-green-400" />
                            All Assets Remediated
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">
                            All assets for <span className="text-white font-semibold">{finding?.title}</span> have been marked as remediated. Would you like to update the finding status to <span className="text-green-400 font-semibold">REMEDIATED</span>?
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="gap-2 sm:gap-0">
                        <Button
                            variant="ghost"
                            className="text-slate-400 hover:text-white"
                            onClick={() => setShowRemediatePrompt(false)}
                        >
                            Not Now
                        </Button>
                        <Button
                            className="bg-green-600 hover:bg-green-500 text-white"
                            onClick={() => markRemediated.mutate()}
                            disabled={markRemediated.isPending}
                        >
                            {markRemediated.isPending ? (
                                <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Updating...</>
                            ) : (
                                'Mark as Remediated'
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Remediation Prompt Dialog — from status dropdown */}
            <Dialog open={showStatusRemediatePrompt} onOpenChange={setShowStatusRemediatePrompt}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <AlertTriangle className="h-5 w-5 text-amber-400" />
                            Unremediated Assets
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">
                            There {(finding?.assets || []).filter((a: any) => !a.remediated).length === 1 ? 'is' : 'are'} <span className="text-white font-semibold">{(finding?.assets || []).filter((a: any) => !a.remediated).length}</span> unremediated asset{(finding?.assets || []).filter((a: any) => !a.remediated).length === 1 ? '' : 's'} on this finding. Marking the finding as <span className="text-green-400 font-semibold">REMEDIATED</span> will also mark all assets as remediated.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="gap-2 sm:gap-0">
                        <Button
                            variant="ghost"
                            className="text-slate-400 hover:text-white"
                            onClick={() => setShowStatusRemediatePrompt(false)}
                        >
                            Cancel
                        </Button>
                        <Button
                            className="bg-green-600 hover:bg-green-500 text-white"
                            onClick={() => markAllAssetsAndRemediate.mutate()}
                            disabled={markAllAssetsAndRemediate.isPending}
                        >
                            {markAllAssetsAndRemediate.isPending ? (
                                <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Remediating...</>
                            ) : (
                                'Mark All & Remediate'
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </DashboardLayout >
    );
}

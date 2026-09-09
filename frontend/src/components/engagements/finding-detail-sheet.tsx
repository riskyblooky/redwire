'use client';

import { useState, useEffect } from 'react';
import { UserName } from '@/components/ui/user-name';
import { UserAvatar } from '@/components/ui/user-avatar';
import { useRouter } from 'next/navigation';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
    Edit, Trash2, FileText, Loader2, Server, StickyNote, Bug,
    Sparkles, Lock, CheckSquare, User, Clock, Radar, Layers, Plus,
    ExternalLink, AlertTriangle, ShieldAlert, Link as LinkIcon,
    Circle, Eye, CheckCircle2, Wrench, Target, Copy, Check,
} from 'lucide-react';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useFinding, useDeleteFinding, useUpdateFinding, useTags } from '@/lib/hooks/use-findings';
import { useFindingReviews } from '@/lib/hooks/use-finding-reviews';
import { FindingPeerReview } from '@/components/findings/finding-peer-review';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { useNotes } from '@/lib/hooks/use-notes';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { useInfraByEntity } from '@/lib/hooks/use-infra';
import { useEngagement } from '@/lib/hooks/use-engagements';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { CustomFieldsDisplay } from '@/components/custom-fields/custom-fields-display';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import { ChainLinksSection } from '@/components/engagements/chain-links-section';
import { CleanupDetailModal } from '@/components/engagements/cleanup-detail-modal';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { TECHNIQUE_MAP } from '@/lib/attack-data';
import { Shield } from 'lucide-react';
import { InlineMarkdownField } from '@/components/ui/inline/inline-markdown-field';
import { InlineSelectField, InlineSelectOption } from '@/components/ui/inline/inline-select-field';
import { InlineComboboxField, InlineComboboxOption } from '@/components/ui/inline/inline-combobox-field';
import { InlineTagsField } from '@/components/ui/inline/inline-tags-field';
import { InlineTextField } from '@/components/ui/inline/inline-text-field';
import { InlineCvssField } from '@/components/ui/inline/inline-cvss-field';
import { CollapsibleSection } from '@/components/ui/collapsible-section';
import { VersionHistoryPanel } from '@/components/ui/version-history-panel';
import { EvidenceUpload } from '@/components/findings/evidence-upload';
import { EvidenceCard } from '@/components/findings/evidence-card';
import DiscussionSection from '@/components/discussions/discussion-section';
import { EntityClassificationField } from '@/components/marking/entity-classification-field';
import { severityRating } from '@/lib/cvss31';
import { buildFindingContext } from '@/lib/ai-entity-context';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { useAuthStore } from '@/stores/auth-store';
import {
    useLinkFindingToTestCase, useUnlinkFindingFromTestCase,
    useLinkFindingToVaultItem, useUnlinkFindingFromVaultItem,
    useLinkFindingToCleanup, useUnlinkFindingFromCleanup,
    useLinkAssetToFinding, useUnlinkAssetFromFinding,
} from '@/lib/hooks/use-entity-links';
import { toast } from 'sonner';
import { cn, parseUTCDate } from '@/lib/utils';
import Link from 'next/link';

// ── colour maps ──────────────────────────────────────────────────────

const severityAccent: Record<string, string> = {
    CRITICAL: 'bg-red-500',
    HIGH: 'bg-orange-500',
    MEDIUM: 'bg-amber-500',
    LOW: 'bg-blue-500',
    INFO: 'bg-slate-500',
};

const severityBadge: Record<string, string> = {
    CRITICAL: 'bg-red-500/10 text-red-400 border-red-500/20',
    HIGH: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    MEDIUM: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    LOW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    INFO: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

const statusBadge: Record<string, string> = {
    OPEN: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    IN_REVIEW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    VERIFIED: 'bg-green-500/10 text-green-400 border-green-500/20',
    CLOSED: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
    FALSE_POSITIVE: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
    REMEDIATED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
};

const assetTypeColors: Record<string, string> = {
    IP_ADDRESS: 'text-blue-400',
    DOMAIN: 'text-emerald-400',
    URL: 'text-purple-400',
    CLOUD_RESOURCE: 'text-sky-400',
    OTHER: 'text-slate-400',
};

const statusOptions: { value: string; label: string; Icon: React.ComponentType<{ className?: string }>; iconClass: string }[] = [
    { value: 'OPEN', label: 'Open', Icon: Circle, iconClass: 'text-primary' },
    { value: 'IN_REVIEW', label: 'In Review', Icon: Eye, iconClass: 'text-blue-400' },
    { value: 'VERIFIED', label: 'Verified', Icon: CheckCircle2, iconClass: 'text-green-400' },
    { value: 'REMEDIATED', label: 'Remediated', Icon: Wrench, iconClass: 'text-emerald-400' },
    { value: 'CLOSED', label: 'Closed', Icon: Lock, iconClass: 'text-slate-400' },
];

// ── props ────────────────────────────────────────────────────────────

interface FindingDetailSheetProps {
    findingId: string | null;
    engagementId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    nonModal?: boolean;
}

// ── component ────────────────────────────────────────────────────────

export function FindingDetailSheet({ findingId, engagementId, open, onOpenChange, nonModal }: FindingDetailSheetProps) {
    const router = useRouter();
    const fid = findingId || '';

    // Radix Dialog locks body scroll even with modal={false}. Continuously clear it
    // while the non-modal panel is open using a 50ms interval to beat Radix's scheduler.
    useEffect(() => {
        if (!nonModal || !open) return;
        const unlock = () => {
            if (document.body.style.overflow) document.body.style.removeProperty('overflow');
            if (document.body.style.paddingRight) document.body.style.removeProperty('padding-right');
        };
        unlock();
        const id = setInterval(unlock, 50);
        return () => clearInterval(id);
    }, [nonModal, open]);

    const { data: finding, isLoading } = useFinding(fid);
    const { data: engagement } = useEngagement(finding?.engagement_id || '');
    const { data: allNotes = [] } = useNotes(engagementId);
    const { data: intelItems = [] } = useIntelByEntity('finding', fid);
    const { data: infraItems = [] } = useInfraByEntity('finding', fid);
    const { data: reviewSummary } = useFindingReviews(fid);
    const { data: allTags = [] } = useTags('finding');
    const { data: findingTypes = [] } = useConfigurableTypes('finding');
    const { user } = useAuthStore();

    const deleteFinding = useDeleteFinding();
    const updateFinding = useUpdateFinding();
    const queryClient = useQueryClient();
    const canEdit = useCanEdit(engagementId, 'finding', finding?.created_by);
    const canDelete = useCanDelete(engagementId, 'finding', finding?.created_by);
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // Live presence + content refresh when a teammate edits this finding.
    const { activeUsers } = useCollaboration({ resourceType: 'finding', resourceId: fid, enabled: !!finding });
    useCollaboration({
        resourceType: 'dashboard',
        resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log' && (data.resource_type || '').toLowerCase() === 'finding' && data.resource_id === fid) {
                queryClient.invalidateQueries({ queryKey: ['findings', fid] });
            }
        },
    });

    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);
    const [viewCleanup, setViewCleanup] = useState<any>(null);
    const [copiedCvss, setCopiedCvss] = useState(false);
    const [showRemediatePrompt, setShowRemediatePrompt] = useState(false);
    const [showStatusRemediatePrompt, setShowStatusRemediatePrompt] = useState(false);

    // Single-field patch through the update hook (PUT is a partial patch).
    const saveField = async (patch: Record<string, any>) => {
        await updateFinding.mutateAsync({ id: fid, ...patch } as any);
    };

    const SEVERITY_OPTIONS: InlineSelectOption[] = [
        { value: 'CRITICAL', label: 'CRITICAL', badgeClass: severityBadge.CRITICAL },
        { value: 'HIGH', label: 'HIGH', badgeClass: severityBadge.HIGH },
        { value: 'MEDIUM', label: 'MEDIUM', badgeClass: severityBadge.MEDIUM },
        { value: 'LOW', label: 'LOW', badgeClass: severityBadge.LOW },
        { value: 'INFO', label: 'INFO', badgeClass: severityBadge.INFO },
    ];
    const categoryOptions: InlineComboboxOption[] = findingTypes.map((t: any) => ({ value: t.name, label: t.name, color: t.color }));

    const scoreToSeverity = (score: number) =>
        (({ None: 'INFO', Low: 'LOW', Medium: 'MEDIUM', High: 'HIGH', Critical: 'CRITICAL' } as Record<string, string>)[severityRating(score)] || 'INFO');

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

    // Toggle asset remediation with optimistic updates.
    const toggleRemediation = useMutation({
        mutationFn: async ({ assetId }: { assetId: string }) => {
            const { data } = await api.patch(`/findings/${fid}/assets/${assetId}/remediate`);
            return data;
        },
        onMutate: async ({ assetId }) => {
            await queryClient.cancelQueries({ queryKey: ['findings', fid] });
            const previousFinding = queryClient.getQueryData(['findings', fid]);
            queryClient.setQueryData(['findings', fid], (old: any) => {
                if (!old) return old;
                const updatedAssets = (old.assets || []).map((a: any) =>
                    a.id === assetId ? { ...a, remediated: !a.remediated } : a
                );
                return { ...old, assets: updatedAssets };
            });
            return { previousFinding };
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['findings', fid] });
            toast.success(data.remediated ? 'Asset marked as remediated' : 'Asset remediation reverted');
            const cached: any = queryClient.getQueryData(['findings', fid]);
            if (cached && data.remediated) {
                const allRemediated = (cached.assets || []).every((a: any) => a.remediated);
                const totalAssets = (cached.assets || []).length;
                if (allRemediated && totalAssets > 0 && cached.status !== 'REMEDIATED') {
                    setShowRemediatePrompt(true);
                }
            }
        },
        onError: (_err, _vars, context) => {
            if (context?.previousFinding) {
                queryClient.setQueryData(['findings', fid], context.previousFinding);
            }
            toast.error('Failed to update remediation status');
        },
    });

    const markRemediated = useMutation({
        mutationFn: async () => { await updateFinding.mutateAsync({ id: fid, status: 'REMEDIATED' }); },
        onSuccess: () => { toast.success('Finding marked as Remediated'); setShowRemediatePrompt(false); },
        onError: () => { toast.error('Failed to update finding status'); },
    });

    const markAllAssetsAndRemediate = useMutation({
        mutationFn: async () => {
            const unremediated = (finding?.assets || []).filter((a: any) => !a.remediated);
            for (const asset of unremediated) {
                await api.patch(`/findings/${fid}/assets/${asset.id}/remediate`);
            }
            await updateFinding.mutateAsync({ id: fid, status: 'REMEDIATED' });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['findings', fid] });
            toast.success('All assets remediated and finding marked as Remediated');
            setShowStatusRemediatePrompt(false);
        },
        onError: () => { toast.error('Failed to update remediation status'); },
    });

    const handleStatusChange = async (newStatus: string) => {
        if (!finding || newStatus === finding.status) return;
        // Selecting REMEDIATED with unremediated assets → prompt to bulk-remediate.
        if (newStatus === 'REMEDIATED') {
            const unremediated = (finding.assets || []).filter((a: any) => !a.remediated);
            if (unremediated.length > 0) {
                setShowStatusRemediatePrompt(true);
                return;
            }
        }
        // Peer-review gate: block the verify early (backend also enforces this).
        if (newStatus === 'VERIFIED' && reviewSummary && reviewSummary.required && !reviewSummary.satisfied) {
            const remaining = reviewSummary.min_approvals - reviewSummary.approvals;
            toast.error(
                `Peer review required: this finding needs ${remaining} more approval${remaining === 1 ? '' : 's'} ` +
                `(${reviewSummary.approvals}/${reviewSummary.min_approvals}) before it can be verified.`
            );
            return;
        }
        // Warn before verifying with unresolved discussion threads.
        if (newStatus === 'VERIFIED' && (finding.unresolved_thread_count || 0) > 0) {
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
            await updateFinding.mutateAsync({ id: fid, status: newStatus });
            toast.success(`Status updated to ${newStatus.replace('_', ' ')}`);
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to update finding status'));
        }
    };

    // Link/unlink hooks
    const linkTC = useLinkFindingToTestCase();
    const unlinkTC = useUnlinkFindingFromTestCase();
    const linkVault = useLinkFindingToVaultItem();
    const unlinkVault = useUnlinkFindingFromVaultItem();
    const linkCleanup = useLinkFindingToCleanup();
    const unlinkCleanup = useUnlinkFindingFromCleanup();
    const linkAsset = useLinkAssetToFinding();   // asset↔finding, reversed direction
    const unlinkAsset = useUnlinkAssetFromFinding();

    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (!finding) return;
        if (type === 'testcases') await linkTC.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'vault') await linkVault.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'assets') await linkAsset.mutateAsync({ entityId: resourceId, resourceId: finding.id });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (!finding) return;
        if (type === 'testcases') await unlinkTC.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'assets') await unlinkAsset.mutateAsync({ entityId: resourceId, resourceId: finding.id });
    };

    const linkedIds: LinkedIdMap = {
        findings: new Set(),
        testcases: new Set((finding?.testcases ?? []).map((t: any) => t.id)),
        assets: new Set((finding?.assets ?? []).map((a: any) => a.id)),
        vault: new Set((finding?.vault_items ?? []).map((v: any) => v.id)),
        cleanup: new Set((finding?.cleanup_artifacts ?? []).map((c: any) => c.id)),
        intel: new Set(intelItems.map((i: any) => i.id)),
        infra: new Set(infraItems.map((i: any) => i.id)),
    };

    const linkedNotes = finding
        ? allNotes.filter((n: any) => n.linked_findings?.some((f: any) => f.id === finding.id))
        : [];

    const handleDelete = async () => {
        if (!finding) return;
        const confirmed = await confirm({
            title: 'Delete Finding',
            description: 'Are you sure you want to delete this finding? This action cannot be undone.',
        });
        if (!confirmed) return;
        try {
            await deleteFinding.mutateAsync(finding.id);
            onOpenChange(false);
            toast.success('Finding deleted');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to delete finding'));
        }
    };

    const remediatedCount = (finding?.assets || []).filter((a: any) => a.remediated).length;
    const assetCount = (finding?.assets || []).length;
    const remediatedPct = assetCount > 0 ? Math.round((remediatedCount / assetCount) * 100) : 0;

    return (
        <>
            <ConfirmDialog />
            <Sheet open={open} onOpenChange={onOpenChange} modal={!nonModal}>
                <SheetContent
                    side="right"
                    nonModal={nonModal}
                    className="w-full sm:max-w-[40vw] bg-slate-950 border-slate-800 p-0 overflow-y-auto"
                >
                    {isLoading || !finding ? (
                        <div className="flex items-center justify-center h-full">
                            <VisuallyHidden><SheetTitle>Loading finding details</SheetTitle></VisuallyHidden>
                            <Loader2 className="h-8 w-8 animate-spin text-red-400" />
                        </div>
                    ) : (
                        <div className="flex flex-col h-full">
                            {/* Accent bar */}
                            <div className={cn('h-1.5 w-full shrink-0', severityAccent[finding.severity] || 'bg-slate-500')} />

                            {/* Header */}
                            <SheetHeader className="p-5 pb-0">
                                <div className="flex items-start gap-3 pr-8">
                                    <div className="min-w-0 flex-1">
                                        <VisuallyHidden><SheetTitle>{finding.title}</SheetTitle></VisuallyHidden>
                                        <InlineTextField
                                            value={finding.title}
                                            canEdit={canEdit}
                                            onSave={(v) => saveField({ title: v })}
                                            className="text-xl font-bold text-white tracking-tight leading-tight"
                                            placeholder="Finding title"
                                        />
                                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                                            <InlineSelectField
                                                value={finding.severity}
                                                options={SEVERITY_OPTIONS}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ severity: v })}
                                                renderRead={(_opt, val) => (
                                                    <Badge className={cn('px-2 py-0.5 text-[10px] font-bold uppercase border', severityBadge[val] || severityBadge.INFO)}>{val}</Badge>
                                                )}
                                            />
                                            <Select
                                                value={finding.status}
                                                onValueChange={handleStatusChange}
                                                disabled={!canEdit}
                                            >
                                                <SelectTrigger
                                                    className={cn(
                                                        'h-6 w-auto gap-1.5 px-2 py-0 text-[10px] font-bold uppercase tracking-wider border rounded-md [&>svg]:h-3 [&>svg]:w-3 [&>svg]:opacity-60',
                                                        statusBadge[finding.status] || statusBadge.OPEN,
                                                        !canEdit && 'opacity-60 cursor-not-allowed'
                                                    )}
                                                >
                                                    <SelectValue>
                                                        {(() => {
                                                            const opt = statusOptions.find(o => o.value === finding.status);
                                                            if (!opt) return finding.status?.replace('_', ' ');
                                                            const I = opt.Icon;
                                                            return (
                                                                <span className="flex items-center gap-1.5">
                                                                    <I className={cn('h-3 w-3', opt.iconClass)} />
                                                                    <span>{opt.label}</span>
                                                                </span>
                                                            );
                                                        })()}
                                                    </SelectValue>
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                    {statusOptions.map(({ value, label, Icon, iconClass }) => (
                                                        <SelectItem key={value} value={value} className="text-xs font-semibold focus:bg-slate-800">
                                                            <span className="flex items-center gap-2">
                                                                <Icon className={cn('h-3.5 w-3.5', iconClass)} />
                                                                <span className="uppercase tracking-wider">{label}</span>
                                                            </span>
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            {(finding.category || canEdit) && (
                                                <InlineComboboxField
                                                    value={finding.category || ''}
                                                    options={categoryOptions}
                                                    canEdit={canEdit}
                                                    onSave={(v) => saveField({ category: v })}
                                                    placeholder="Search categories…"
                                                    emptyLabel="no category"
                                                />
                                            )}
                                            {finding.cvss_score != null && (
                                                <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">
                                                    CVSS {finding.cvss_score}
                                                </Badge>
                                            )}
                                            {engagement && (
                                                <Link
                                                    href={`/engagements/${engagement.id}?tab=findings`}
                                                    onClick={() => onOpenChange(false)}
                                                    className="text-xs text-primary hover:underline flex items-center gap-1"
                                                >
                                                    <Target className="h-3 w-3" /> {engagement.name}
                                                </Link>
                                            )}
                                        </div>
                                        <div className="mt-2">
                                            <InlineTagsField
                                                tags={finding.tags}
                                                allTags={allTags}
                                                selectedIds={(finding.tags || []).map((t: any) => t.id)}
                                                canEdit={canEdit}
                                                onSave={(ids) => saveField({ tag_ids: ids })}
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* Action bar */}
                                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-800/60">
                                    <Button
                                        size="sm" variant="outline"
                                        className="border-slate-700 text-slate-300 text-xs h-8"
                                        onClick={() => { onOpenChange(false); router.push(`/findings/${finding.id}?engagementId=${engagementId}&tab=findings`); }}
                                    >
                                        <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> Full Page
                                    </Button>
                                    {canEdit && (
                                        <Button
                                            size="sm" variant="outline"
                                            className="border-slate-700 text-slate-300 text-xs h-8"
                                            onClick={() => { onOpenChange(false); router.push(`/findings/${finding.id}/edit?engagementId=${engagementId}&tab=findings`); }}
                                        >
                                            <Edit className="h-3.5 w-3.5 mr-1.5" /> Edit
                                        </Button>
                                    )}
                                    <div className="ml-auto flex items-center gap-2">
                                        {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}
                                        <VersionHistoryPanel entityType="finding" entityId={finding.id} currentData={finding} />
                                        {canDelete && (
                                            <Button
                                                size="sm" variant="outline"
                                                className="border-red-500/20 text-red-400 hover:bg-red-500/10 text-xs h-8"
                                                onClick={handleDelete}
                                            >
                                                <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Delete
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </SheetHeader>

                            {/* Content */}
                            <div className="flex-1 p-5 space-y-5 overflow-y-auto">

                                {/* Description */}
                                {(finding.description || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Description" icon={FileText} iconColor="text-primary">
                                            <InlineMarkdownField
                                                value={finding.description || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ description: v })}
                                                engagementId={finding.engagement_id}
                                                fieldContext={{ resourceType: 'finding', fieldName: 'description', entityContext: buildFindingContext(finding) }}
                                                previewWrapperClassName="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50"
                                                emptyText="Double-click to add a description…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Impact */}
                                {(finding.impact || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Impact" icon={AlertTriangle} iconColor="text-orange-400">
                                            <InlineMarkdownField
                                                value={finding.impact || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ impact: v })}
                                                engagementId={finding.engagement_id}
                                                fieldContext={{ resourceType: 'finding', fieldName: 'impact', entityContext: buildFindingContext(finding) }}
                                                previewWrapperClassName="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50"
                                                emptyText="Double-click to add potential impact…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Steps to Reproduce */}
                                {(finding.steps_to_reproduce || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Steps to Reproduce" icon={FileText} iconColor="text-blue-400">
                                            <InlineMarkdownField
                                                value={finding.steps_to_reproduce || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ steps_to_reproduce: v })}
                                                engagementId={finding.engagement_id}
                                                fieldContext={{ resourceType: 'finding', fieldName: 'steps_to_reproduce', entityContext: buildFindingContext(finding) }}
                                                previewWrapperClassName="bg-slate-950 p-2 rounded-lg border border-slate-800 shadow-inner overflow-hidden"
                                                emptyText="Double-click to add reproduction steps…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Technical Details */}
                                {(finding.technical_details || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Technical Details" icon={Bug} iconColor="text-red-400">
                                            <InlineMarkdownField
                                                value={finding.technical_details || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ technical_details: v })}
                                                engagementId={finding.engagement_id}
                                                fieldContext={{ resourceType: 'finding', fieldName: 'technical_details', entityContext: buildFindingContext(finding) }}
                                                previewWrapperClassName="bg-slate-900/40 p-3 rounded-lg border border-slate-800/60 overflow-hidden"
                                                emptyText="Double-click to add technical details…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Remediation */}
                                {(finding.mitigations || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Remediation" icon={ShieldAlert} iconColor="text-emerald-400">
                                            <InlineMarkdownField
                                                value={finding.mitigations || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ mitigations: v })}
                                                engagementId={finding.engagement_id}
                                                fieldContext={{ resourceType: 'finding', fieldName: 'mitigations', entityContext: buildFindingContext(finding) }}
                                                previewWrapperClassName="bg-green-500/5 border border-green-500/20 p-2 rounded-lg overflow-hidden"
                                                emptyText="Double-click to add remediation guidance…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* External References */}
                                {(finding.references || canEdit) && (
                                    <>
                                        <CollapsibleSection title="External References" icon={ExternalLink} iconColor="text-slate-400">
                                            <InlineMarkdownField
                                                value={finding.references || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ references: v })}
                                                engagementId={finding.engagement_id}
                                                fieldContext={{ resourceType: 'finding', fieldName: 'references', entityContext: buildFindingContext(finding) }}
                                                previewWrapperClassName="bg-slate-950/40 p-2 rounded-lg border border-slate-800/40 overflow-hidden"
                                                emptyText="Double-click to add external references…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* CVSS */}
                                <CollapsibleSection title="Risk Assessment" icon={AlertTriangle} iconColor="text-amber-400">
                                    <InlineCvssField
                                        vector={finding.cvss_vector}
                                        canEdit={canEdit}
                                        onSave={(score, vector) => saveField({ cvss_score: score, cvss_vector: vector, severity: scoreToSeverity(score) })}
                                    >
                                        <div className="flex flex-col items-center justify-center p-4 bg-slate-950/50 rounded-2xl border border-slate-800/50 shadow-inner">
                                            <span className={cn('text-4xl font-black italic tracking-tighter cursor-default',
                                                (finding.cvss_score || 0) >= 9 ? 'text-red-600' :
                                                    (finding.cvss_score || 0) >= 7 ? 'text-orange-500' :
                                                        (finding.cvss_score || 0) >= 4 ? 'text-amber-500' : 'text-blue-500'
                                            )}>
                                                {finding.cvss_score?.toFixed(1) || '0.0'}
                                            </span>
                                            <span className="text-[9px] text-slate-500 font-black uppercase mt-1 tracking-widest">CVSS v3.1 BASE</span>
                                            {finding.cvss_vector && (
                                                <button
                                                    type="button"
                                                    onClick={(e) => { e.stopPropagation(); copyCvssVector(finding.cvss_vector!); }}
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
                                    </InlineCvssField>
                                </CollapsibleSection>
                                <Separator className="bg-slate-800/60" />

                                {/* Peer Review */}
                                <FindingPeerReview findingId={finding.id} />
                                <Separator className="bg-slate-800/60" />

                                {/* Affected Targets */}
                                <CollapsibleSection
                                    title="Affected Targets"
                                    icon={Target}
                                    iconColor="text-cyan-400"
                                    right={assetCount > 0 ? (
                                        <span className={cn(
                                            'text-[10px] font-bold tabular-nums',
                                            remediatedPct === 100 ? 'text-green-400' : remediatedPct > 0 ? 'text-amber-400' : 'text-slate-500'
                                        )}>
                                            {remediatedCount}/{assetCount} remediated
                                        </span>
                                    ) : undefined}
                                >
                                    {assetCount > 0 && (
                                        <Progress
                                            value={remediatedPct}
                                            className={cn('h-1.5 bg-slate-800 mb-3', remediatedCount === assetCount && '[&>div]:bg-green-500')}
                                        />
                                    )}
                                    <div className="space-y-2">
                                        {assetCount > 0 ? (
                                            (finding.assets as any[]).map((asset: any) => {
                                                const selectedPorts = asset.port_ids && asset.ports
                                                    ? asset.ports.filter((p: any) => asset.port_ids.includes(p.id))
                                                    : [];
                                                return (
                                                    <div key={asset.id} className="space-y-1">
                                                        <div className={cn(
                                                            'flex items-center gap-2 p-2 rounded-lg border transition-all',
                                                            asset.remediated ? 'bg-green-500/5 border-green-500/20' : 'bg-slate-950/40 border-slate-800/60'
                                                        )}>
                                                            <Checkbox
                                                                checked={asset.remediated}
                                                                onCheckedChange={() => toggleRemediation.mutate({ assetId: asset.id })}
                                                                className={cn('shrink-0', asset.remediated && 'data-[state=checked]:bg-green-500 data-[state=checked]:border-green-500')}
                                                                disabled={!canEdit}
                                                            />
                                                            <Link href={`/assets/${asset.id}`} className="flex-1 min-w-0 group" onClick={() => onOpenChange(false)}>
                                                                <div className="flex items-center justify-between gap-2">
                                                                    <span className={cn(
                                                                        'text-xs font-bold truncate group-hover:text-primary transition-colors',
                                                                        asset.remediated ? 'text-green-300 line-through opacity-70' : 'text-white'
                                                                    )} title={asset.name}>{asset.name}</span>
                                                                    <Badge variant="outline" className={cn('text-[8px] px-1 py-0 h-4 border-none uppercase shrink-0', assetTypeColors[asset.asset_type] || 'text-slate-400')}>
                                                                        {asset.asset_type?.split('_')[0]}
                                                                    </Badge>
                                                                </div>
                                                                {asset.identifier && <span className="text-[9px] text-slate-500 font-mono mt-0.5 block truncate">{asset.identifier}</span>}
                                                            </Link>
                                                            {asset.remediated && <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />}
                                                        </div>
                                                        {selectedPorts.length > 0 && (
                                                            <div className="ml-8 flex flex-wrap gap-1">
                                                                {selectedPorts.map((port: any) => (
                                                                    <Badge
                                                                        key={port.id}
                                                                        variant="outline"
                                                                        className={cn(
                                                                            'text-[11px] px-2 py-0.5 h-5 border-none font-mono font-bold',
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
                                </CollapsibleSection>
                                <Separator className="bg-slate-800/60" />

                                {/* Classification (portion marking) */}
                                {canEdit && (
                                    <>
                                        <CollapsibleSection title="Classification Marking" icon={Shield} iconColor="text-slate-400">
                                            <EntityClassificationField
                                                engagementId={finding.engagement_id}
                                                level={finding.classification_level || null}
                                                suffix={finding.classification_suffix || null}
                                                inheritLabel="Inherit (engagement default)"
                                                label=""
                                                onChange={async (lvl, suf) => {
                                                    try {
                                                        await updateFinding.mutateAsync({ id: finding.id, classification_level: lvl, classification_suffix: suf });
                                                    } catch (e: any) {
                                                        toast.error(getErrorMessage(e, 'Failed to update classification'));
                                                    }
                                                }}
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* ATT&CK Techniques */}
                                {(canEdit || (finding.attack_technique_ids?.length ?? 0) > 0) && (
                                    <>
                                        <CollapsibleSection
                                            title="ATT&CK Techniques"
                                            icon={Shield}
                                            iconColor="text-purple-400"
                                            right={(finding.attack_technique_ids?.length ?? 0) > 0 ? (
                                                <span className="text-[10px] font-bold tabular-nums text-slate-500">{finding.attack_technique_ids?.length}</span>
                                            ) : undefined}
                                        >
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
                                                    {(finding.attack_technique_ids || []).map(id => {
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
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Linked Resources — the colored icon carries the type */}
                                <CollapsibleSection
                                    title="Linked Resources"
                                    icon={LinkIcon}
                                    iconColor="text-indigo-400"
                                    right={canEdit ? (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 px-2 text-[10px] text-indigo-400 hover:text-indigo-300 hover:bg-primary/90/10 gap-1"
                                            onClick={() => setLinkDialogOpen(true)}
                                        >
                                            <LinkIcon className="h-3 w-3" />
                                            + Link
                                        </Button>
                                    ) : undefined}
                                >
                                    {((finding.assets?.length ?? 0) + (finding.testcases?.length ?? 0) + (finding.vault_items?.length ?? 0) + (finding.cleanup_artifacts?.length ?? 0) + intelItems.length + infraItems.length) > 0 ? (
                                    <div className="space-y-1.5 max-h-72 overflow-y-auto">
                                        {(finding.assets ?? []).map((asset: any) => (
                                            <Link
                                                key={asset.id}
                                                href={`/assets/${asset.id}?engagementId=${engagementId}&tab=findings`}
                                                className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-cyan-500/30 transition-colors group"
                                                onClick={() => onOpenChange(false)}
                                            >
                                                <Server className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                                                <span className="text-xs font-medium text-white group-hover:text-cyan-300 truncate">{asset.name}</span>
                                                {asset.identifier && <span className="text-[10px] text-slate-500 font-mono truncate ml-auto shrink-0">{asset.identifier}</span>}
                                            </Link>
                                        ))}
                                        {(finding.testcases ?? []).map((tc: any) => (
                                            <Link
                                                key={tc.id}
                                                href={`/testcases/${tc.id}?engagementId=${engagementId}&tab=findings`}
                                                className="flex items-center justify-between gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-emerald-500/30 transition-colors group"
                                                onClick={() => onOpenChange(false)}
                                            >
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <CheckSquare className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                                                    <span className="text-xs font-medium text-white group-hover:text-emerald-300 truncate">{tc.title}</span>
                                                </div>
                                                <Badge variant="outline" className={cn(
                                                    'text-[8px] px-1 py-0 h-4 border-none uppercase font-bold shrink-0',
                                                    tc.is_executed
                                                        ? (tc.is_successful ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400')
                                                        : 'bg-slate-500/10 text-slate-400'
                                                )}>
                                                    {tc.is_executed ? (tc.is_successful ? 'Pass' : 'Fail') : 'Pending'}
                                                </Badge>
                                            </Link>
                                        ))}
                                        {(finding.vault_items ?? []).map((vi: any) => (
                                            <Link
                                                key={vi.id}
                                                href={`/engagements/${engagementId}?tab=vault`}
                                                onClick={() => onOpenChange(false)}
                                                className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-amber-500/30 transition-colors group"
                                            >
                                                <Lock className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                                                <span className="text-xs font-medium text-white group-hover:text-amber-300 truncate">{vi.name}</span>
                                            </Link>
                                        ))}
                                        {(finding.cleanup_artifacts ?? []).map((ca: any) => (
                                            <button
                                                key={ca.id}
                                                onClick={() => setViewCleanup(ca)}
                                                className="w-full flex items-center justify-between gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-lime-500/30 hover:bg-lime-500/5 transition-colors text-left"
                                            >
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <Sparkles className="h-3.5 w-3.5 text-lime-400 shrink-0" />
                                                    <span className="text-xs font-medium text-white truncate">{ca.title}</span>
                                                </div>
                                                <Badge variant="outline" className={cn(
                                                    'text-[8px] px-1 py-0 h-4 border-none uppercase font-bold shrink-0',
                                                    ca.status === 'CLEANED' ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'
                                                )}>
                                                    {ca.status}
                                                </Badge>
                                            </button>
                                        ))}
                                        {intelItems.map((item: any) => (
                                            <div
                                                key={item.id}
                                                onClick={() => setIntelDetailId(item.id)}
                                                className="w-full flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-violet-500/30 transition-colors group text-left cursor-pointer"
                                            >
                                                <Radar className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                                                <div className="flex-1 min-w-0">
                                                    <span className="text-xs font-medium text-white group-hover:text-violet-300 truncate block">{item.title || item.value}</span>
                                                    {item.cve_id && <span className="text-[9px] font-mono text-red-400">{item.cve_id}</span>}
                                                </div>
                                                {/* scheme gate defends against a legacy javascript:/data: URI */}
                                                {item.source_url && /^https?:\/\//i.test(item.source_url) && (
                                                    <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-violet-400 transition-colors shrink-0" onClick={(e) => e.stopPropagation()}>
                                                        <ExternalLink className="h-3 w-3" />
                                                    </a>
                                                )}
                                            </div>
                                        ))}
                                        {infraItems.map((item: any) => (
                                            <div key={item.id} className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60">
                                                <Server className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                                                <span className="text-xs font-medium text-white truncate">{item.name}</span>
                                            </div>
                                        ))}
                                    </div>
                                    ) : (
                                        <div className="text-[10px] text-slate-500 italic p-3 text-center border border-dashed border-slate-800 rounded-lg">
                                            Nothing linked yet
                                        </div>
                                    )}
                                </CollapsibleSection>

                                <Separator className="bg-slate-800/60" />

                                <CustomFieldsDisplay entity="finding" value={finding.custom_fields} />

                                {/* Attack Chain */}
                                <ChainLinksSection
                                    engagementId={engagementId}
                                    entityType="finding"
                                    entityId={finding.id}
                                    entityName={finding.title}
                                    canEdit={canEdit}
                                />
                                <Separator className="bg-slate-800/60" />

                                {/* Linked Notes */}
                                {linkedNotes.length > 0 && (
                                    <>
                                        <div className="space-y-1.5">
                                            {linkedNotes.map((note: any) => (
                                                <Link
                                                    key={note.id}
                                                    href={`/engagements/${engagementId}?tab=notes&noteId=${note.id}`}
                                                    className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-teal-500/30 transition-colors group"
                                                    onClick={() => onOpenChange(false)}
                                                >
                                                    <StickyNote className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                                                    <span className="text-xs font-medium text-slate-300 group-hover:text-teal-300 truncate">{note.title}</span>
                                                </Link>
                                            ))}
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Evidence — collapsed by default (matches full page) */}
                                <CollapsibleSection
                                    title="Evidence"
                                    icon={Layers}
                                    iconColor="text-primary"
                                    defaultOpen={false}
                                    right={(
                                        <Badge variant="outline" className="bg-primary/10 text-primary border-none px-1.5 h-5 text-[10px]">
                                            {finding.evidence?.length || 0} files
                                        </Badge>
                                    )}
                                >
                                    <div className="space-y-3">
                                        {canEdit && <EvidenceUpload findingId={finding.id} />}
                                        {finding.evidence && finding.evidence.length > 0 ? (
                                            <div className="space-y-3">
                                                {finding.evidence.map((ev: any) => (
                                                    <EvidenceCard key={ev.id} evidence={ev} findingId={finding.id} />
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="text-center py-6 text-slate-500 border border-dashed border-slate-800 rounded-xl bg-slate-950/20">
                                                <Plus className="h-6 w-6 mx-auto mb-1.5 opacity-20" />
                                                <p className="text-xs">No evidence attached</p>
                                            </div>
                                        )}
                                    </div>
                                </CollapsibleSection>
                                <Separator className="bg-slate-800/60" />

                                {/* Metadata */}
                                <CollapsibleSection title="Metadata" icon={User} iconColor="text-slate-400" contentClassName="space-y-3">
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
                                            <UserName
                                                className="text-slate-300"
                                                user={engagement?.assigned_users?.find((u: any) => u.id === finding.created_by)}
                                                name={finding.created_by_full_name}
                                                username={finding.created_by_username}
                                                fallback={finding.created_by?.slice(0, 8)}
                                            />
                                        </div>
                                    </div>
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <Clock className="h-3 w-3" /> Created
                                        </span>
                                        <span className="text-slate-300">{parseUTCDate(finding.created_at).toLocaleString()}</span>
                                    </div>
                                    {finding.updated_at && (
                                        <div className="flex items-center justify-between text-[10px]">
                                            <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                                <Clock className="h-3 w-3" /> Updated
                                            </span>
                                            <span className="text-slate-300">{parseUTCDate(finding.updated_at).toLocaleString()}</span>
                                        </div>
                                    )}
                                </CollapsibleSection>
                                <Separator className="bg-slate-800/60" />

                                {/* Discussion */}
                                <DiscussionSection
                                    engagementId={finding.engagement_id}
                                    resourceType="finding"
                                    resourceId={finding.id}
                                    currentUserId={user?.id}
                                    isAdmin={user?.role === 'admin'}
                                    users={engagement?.assigned_users}
                                />

                                {/* Remediation Threads */}
                                <DiscussionSection
                                    engagementId={finding.engagement_id}
                                    resourceType="finding_remediation"
                                    resourceId={finding.id}
                                    currentUserId={user?.id}
                                    isAdmin={user?.role === 'admin'}
                                    users={engagement?.assigned_users}
                                    title="Remediation Threads"
                                    description="Track remediation progress and coordinate fixes with your team"
                                />
                            </div>
                        </div>
                    )}
                </SheetContent>
            </Sheet>

            {intelDetailId && <IntelDetailDialog itemId={intelDetailId} onClose={() => setIntelDetailId(null)} />}

            <CleanupDetailModal
                artifact={viewCleanup}
                open={!!viewCleanup}
                onOpenChange={(o) => !o && setViewCleanup(null)}
            />

            {finding && (
                <LinkEntityDialog
                    open={linkDialogOpen}
                    onOpenChange={setLinkDialogOpen}
                    engagementId={engagementId}
                    entityType="finding"
                    entityId={finding.id}
                    entityName={finding.title}
                    linkedIds={linkedIds}
                    onLink={handleEntityLink}
                    onUnlink={handleEntityUnlink}
                />
            )}

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
                        <Button variant="ghost" className="text-slate-400 hover:text-white" onClick={() => setShowRemediatePrompt(false)}>
                            Not Now
                        </Button>
                        <Button className="bg-green-600 hover:bg-green-500 text-white" onClick={() => markRemediated.mutate()} disabled={markRemediated.isPending}>
                            {markRemediated.isPending ? (<><Loader2 className="h-4 w-4 animate-spin mr-2" /> Updating...</>) : 'Mark as Remediated'}
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
                        <Button variant="ghost" className="text-slate-400 hover:text-white" onClick={() => setShowStatusRemediatePrompt(false)}>
                            Cancel
                        </Button>
                        <Button className="bg-green-600 hover:bg-green-500 text-white" onClick={() => markAllAssetsAndRemediate.mutate()} disabled={markAllAssetsAndRemediate.isPending}>
                            {markAllAssetsAndRemediate.isPending ? (<><Loader2 className="h-4 w-4 animate-spin mr-2" /> Remediating...</>) : 'Mark All & Remediate'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}

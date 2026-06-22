'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
    Edit, Trash2, FileText, Loader2, Server, StickyNote, Bug,
    Sparkles, Lock, CheckSquare, User, Clock, Radar, Package,
    ExternalLink, AlertTriangle, ShieldAlert, Link as LinkIcon,
    Circle, Eye, CheckCircle2, Wrench,
} from 'lucide-react';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useFinding, useDeleteFinding, useUpdateFinding } from '@/lib/hooks/use-findings';
import { useNotes } from '@/lib/hooks/use-notes';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { useInfraByEntity } from '@/lib/hooks/use-infra';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { TECHNIQUE_MAP } from '@/lib/attack-data';
import { Shield } from 'lucide-react';
import {
    useLinkFindingToTestCase, useUnlinkFindingFromTestCase,
    useLinkFindingToVaultItem, useUnlinkFindingFromVaultItem,
    useLinkFindingToCleanup, useUnlinkFindingFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import Link from 'next/link';
import { EntityClassificationField } from '@/components/marking/entity-classification-field';

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

const statusOptions: { value: string; label: string; Icon: React.ComponentType<{ className?: string }>; iconClass: string }[] = [
    { value: 'OPEN', label: 'Open', Icon: Circle, iconClass: 'text-primary' },
    { value: 'IN_REVIEW', label: 'In Review', Icon: Eye, iconClass: 'text-blue-400' },
    { value: 'VERIFIED', label: 'Verified', Icon: CheckCircle2, iconClass: 'text-green-400' },
    { value: 'REMEDIATED', label: 'Remediated', Icon: Wrench, iconClass: 'text-emerald-400' },
    { value: 'CLOSED', label: 'Closed', Icon: Lock, iconClass: 'text-slate-400' },
];

// ── sub-section ──────────────────────────────────────────────────────

function Section({ title, icon: Icon, iconColor, children }: {
    title: string; icon: any; iconColor: string; children: React.ReactNode;
}) {
    return (
        <div>
            <div className="flex items-center gap-2 mb-2">
                <Icon className={cn('h-4 w-4', iconColor)} />
                <h4 className="text-sm font-bold text-white">{title}</h4>
            </div>
            {children}
        </div>
    );
}

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
    const { data: finding, isLoading } = useFinding(findingId || '');
    const { data: allNotes = [] } = useNotes(engagementId);
    const { data: intelItems = [] } = useIntelByEntity('finding', findingId || '');
    const { data: infraItems = [] } = useInfraByEntity('finding', findingId || '');

    const deleteFinding = useDeleteFinding();
    const updateFinding = useUpdateFinding();
    const canEdit = useCanEdit(engagementId, 'finding', finding?.created_by);
    const canDelete = useCanDelete(engagementId, 'finding', finding?.created_by);
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const handleStatusChange = async (newStatus: string) => {
        if (!finding || newStatus === finding.status) return;
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
            await updateFinding.mutateAsync({ id: finding.id, status: newStatus });
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to update finding status'));
        }
    };
    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);

    // Link/unlink hooks
    const linkTC = useLinkFindingToTestCase();
    const unlinkTC = useUnlinkFindingFromTestCase();
    const linkVault = useLinkFindingToVaultItem();
    const unlinkVault = useUnlinkFindingFromVaultItem();
    const linkCleanup = useLinkFindingToCleanup();
    const unlinkCleanup = useUnlinkFindingFromCleanup();

    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (!finding) return;
        if (type === 'testcases') await linkTC.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'vault') await linkVault.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: finding.id, resourceId });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (!finding) return;
        if (type === 'testcases') await unlinkTC.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: finding.id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: finding.id, resourceId });
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

    return (
        <>
            <ConfirmDialog />
            <Sheet open={open} onOpenChange={onOpenChange} modal={!nonModal}>
                <SheetContent
                    side="right"
                    nonModal={nonModal}
                    className="w-full sm:max-w-2xl bg-slate-950 border-slate-800 p-0 overflow-y-auto"
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
                                        <SheetTitle className="text-xl font-bold text-white tracking-tight leading-tight">
                                            {finding.title}
                                        </SheetTitle>
                                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                                            <Badge className={cn('px-2 py-0.5 text-[10px] font-bold uppercase border', severityBadge[finding.severity] || severityBadge.INFO)}>
                                                {finding.severity}
                                            </Badge>
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
                                            {finding.category && (
                                                <span className="text-xs text-slate-500">{finding.category}</span>
                                            )}
                                            {finding.cvss_score != null && (
                                                <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">
                                                    CVSS {finding.cvss_score}
                                                </Badge>
                                            )}
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
                                    {canDelete && (
                                        <Button
                                            size="sm" variant="outline"
                                            className="border-red-500/20 text-red-400 hover:bg-red-500/10 text-xs h-8 ml-auto"
                                            onClick={handleDelete}
                                        >
                                            <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Delete
                                        </Button>
                                    )}
                                </div>
                            </SheetHeader>

                            {/* Content */}
                            <div className="flex-1 p-5 space-y-5 overflow-y-auto">

                                {/* Description */}
                                {finding.description && (
                                    <>
                                        <Section title="Description" icon={FileText} iconColor="text-primary">
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50">
                                                <MarkdownPreview value={finding.description} theme="dark" />
                                            </div>
                                        </Section>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Impact */}
                                {finding.impact && (
                                    <>
                                        <Section title="Impact" icon={AlertTriangle} iconColor="text-orange-400">
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50">
                                                <MarkdownPreview value={finding.impact} theme="dark" />
                                            </div>
                                        </Section>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Technical Details */}
                                {finding.technical_details && (
                                    <>
                                        <Section title="Technical Details" icon={Bug} iconColor="text-red-400">
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-900/40 p-3 rounded-lg border border-slate-800/60">
                                                <MarkdownPreview value={finding.technical_details} theme="dark" />
                                            </div>
                                        </Section>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Remediation */}
                                {finding.mitigations && (
                                    <>
                                        <Section title="Remediation" icon={ShieldAlert} iconColor="text-emerald-400">
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50">
                                                <MarkdownPreview value={finding.mitigations} theme="dark" />
                                            </div>
                                        </Section>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Classification (portion marking) */}
                                {canEdit && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Classification Marking</h4>
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
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* ATT&CK Techniques */}
                                {(canEdit || (finding.attack_technique_ids?.length ?? 0) > 0) && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
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
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Linked Resources header */}
                                <div className="flex items-center justify-between">
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

                                {/* Linked Assets */}
                                <div>
                                    <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                        Linked Assets {(finding.assets?.length ?? 0) > 0 && <span className="text-slate-600 ml-1">({finding.assets?.length})</span>}
                                    </h4>
                                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                                        {(finding.assets ?? []).length > 0 ? (
                                            (finding.assets ?? []).map((asset: any) => (
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
                                            ))
                                        ) : (
                                            <div className="text-[10px] text-slate-500 italic p-3 text-center border border-dashed border-slate-800 rounded-lg">
                                                No assets linked
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <Separator className="bg-slate-800/60" />

                                {/* Linked Test Cases */}
                                {finding.testcases && finding.testcases.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Linked Test Cases <span className="text-slate-600 ml-1">({finding.testcases.length})</span>
                                            </h4>
                                            <div className="space-y-1.5 max-h-40 overflow-y-auto">
                                                {finding.testcases.map((tc: any) => (
                                                    <Link
                                                        key={tc.id}
                                                        href={`/testcases/${tc.id}?engagementId=${engagementId}&tab=findings`}
                                                        className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-emerald-500/30 transition-colors group"
                                                        onClick={() => onOpenChange(false)}
                                                    >
                                                        <CheckSquare className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                                                        <span className="text-xs font-medium text-white group-hover:text-emerald-300 truncate">{tc.title}</span>
                                                    </Link>
                                                ))}
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Vault Items */}
                                {finding.vault_items && finding.vault_items.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Vault Items <span className="text-slate-600 ml-1">({finding.vault_items.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {finding.vault_items.map((vi: any) => (
                                                    <div key={vi.id} className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60">
                                                        <Lock className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                                                        <span className="text-xs font-medium text-white truncate">{vi.name}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Cleanup Artifacts */}
                                {finding.cleanup_artifacts && finding.cleanup_artifacts.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Cleanup Artifacts <span className="text-slate-600 ml-1">({finding.cleanup_artifacts.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {finding.cleanup_artifacts.map((ca: any) => (
                                                    <div key={ca.id} className="flex items-center justify-between p-2 bg-slate-900/40 rounded-lg border border-slate-800/60">
                                                        <div className="flex items-center gap-2">
                                                            <Sparkles className="h-3.5 w-3.5 text-lime-400 shrink-0" />
                                                            <span className="text-xs font-medium text-white truncate">{ca.title}</span>
                                                        </div>
                                                        <Badge variant="outline" className={cn(
                                                            'text-[8px] px-1 py-0 h-4 border-none uppercase font-bold',
                                                            ca.status === 'CLEANED' ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'
                                                        )}>
                                                            {ca.status}
                                                        </Badge>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Intel */}
                                {intelItems.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Intel <span className="text-slate-600 ml-1">({intelItems.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {intelItems.map((item: any) => (
                                                    <button
                                                        key={item.id}
                                                        onClick={() => setIntelDetailId(item.id)}
                                                        className="w-full flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-violet-500/30 transition-colors group text-left"
                                                    >
                                                        <Radar className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                                                        <span className="text-xs font-medium text-white group-hover:text-violet-300 truncate">{item.title || item.value}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Infrastructure */}
                                {infraItems.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Infrastructure <span className="text-slate-600 ml-1">({infraItems.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {infraItems.map((item: any) => (
                                                    <div key={item.id} className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60">
                                                        <Server className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                                                        <span className="text-xs font-medium text-white truncate">{item.name}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Linked Notes */}
                                {linkedNotes.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Linked Notes <span className="text-slate-600 ml-1">({linkedNotes.length})</span>
                                            </h4>
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
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Metadata */}
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <User className="h-3 w-3" /> Created By
                                        </span>
                                        <span className="text-slate-300 font-mono">{finding.created_by_username || finding.created_by?.slice(0, 8)}</span>
                                    </div>
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <Clock className="h-3 w-3" /> Created
                                        </span>
                                        <span className="text-slate-300">{new Date(finding.created_at).toLocaleString()}</span>
                                    </div>
                                    {finding.updated_at && (
                                        <div className="flex items-center justify-between text-[10px]">
                                            <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                                <Clock className="h-3 w-3" /> Updated
                                            </span>
                                            <span className="text-slate-300">{new Date(finding.updated_at).toLocaleString()}</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </SheetContent>
            </Sheet>
            {intelDetailId && <IntelDetailDialog itemId={intelDetailId} onClose={() => setIntelDetailId(null)} />}
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
        </>
    );
}

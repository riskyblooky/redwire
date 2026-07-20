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
    Sparkles, Lock, User, Clock, Radar, Package, Paperclip,
    ExternalLink, CheckCircle, XCircle, Circle, CheckSquare,
    Globe, Zap, Flag, ArrowUpCircle, Layout, Link as LinkIcon,
} from 'lucide-react';
import { useTestCase, useDeleteTestCase, useUpdateTestCase } from '@/lib/hooks/use-testcases';
import { useNotes } from '@/lib/hooks/use-notes';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { useInfraByEntity } from '@/lib/hooks/use-infra';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { CustomFieldsDisplay } from '@/components/custom-fields/custom-fields-display';
import { ChainLinksSection } from '@/components/engagements/chain-links-section';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { EntityClassificationField } from '@/components/marking/entity-classification-field';
import { TECHNIQUE_MAP } from '@/lib/attack-data';
import { Shield } from 'lucide-react';
import {
    useLinkTestCaseToFinding, useUnlinkTestCaseFromFinding,
    useLinkTestCaseToAsset, useUnlinkTestCaseFromAsset,
    useLinkTestCaseToVaultItem, useUnlinkTestCaseFromVaultItem,
    useLinkTestCaseToCleanup, useUnlinkTestCaseFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { toast } from 'sonner';
import { cn, parseUTCDate } from '@/lib/utils';
import Link from 'next/link';

// ── colour maps ──────────────────────────────────────────────────────

const categoryStyles: Record<string, { color: string; accent: string; icon: any }> = {
    RECONNAISSANCE:      { color: 'bg-blue-500/10 text-blue-400 border-blue-500/20',          accent: 'bg-blue-500',   icon: Globe },
    SCANNING:            { color: 'bg-purple-500/10 text-purple-400 border-purple-500/20',     accent: 'bg-primary', icon: Radar },
    EXPLOITATION:        { color: 'bg-red-500/10 text-red-400 border-red-500/20',              accent: 'bg-red-500',    icon: Zap },
    POST_EXPLOITATION:   { color: 'bg-orange-500/10 text-orange-400 border-orange-500/20',     accent: 'bg-orange-500', icon: Flag },
    PRIVILEGE_ESCALATION:{ color: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',    accent: 'bg-yellow-500', icon: ArrowUpCircle },
    WEB_APPLICATION:     { color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',           accent: 'bg-cyan-500',   icon: Layout },
    OTHER:               { color: 'bg-slate-500/10 text-slate-400 border-slate-500/20',        accent: 'bg-slate-500',  icon: Circle },
};

const severityBadge: Record<string, string> = {
    CRITICAL: 'bg-red-500/10 text-red-400 border-red-500/20',
    HIGH: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    MEDIUM: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    LOW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    INFO: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

// ── props ────────────────────────────────────────────────────────────

interface TestCaseDetailSheetProps {
    testcaseId: string | null;
    engagementId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    nonModal?: boolean;
}

// ── component ────────────────────────────────────────────────────────

export function TestCaseDetailSheet({ testcaseId, engagementId, open, onOpenChange, nonModal }: TestCaseDetailSheetProps) {
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
    const { data: testcase, isLoading } = useTestCase(testcaseId || '');
    const { data: allNotes = [] } = useNotes(engagementId);
    const { data: intelItems = [] } = useIntelByEntity('testcase', testcaseId || '');
    const { data: infraItems = [] } = useInfraByEntity('testcase', testcaseId || '');

    const deleteTestCase = useDeleteTestCase();
    const updateTestCase = useUpdateTestCase();
    const canEdit = useCanEdit(engagementId, 'testcase', testcase?.created_by);
    const canDelete = useCanDelete(engagementId, 'testcase', testcase?.created_by);
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);

    // Link/unlink hooks
    const linkFinding = useLinkTestCaseToFinding();
    const unlinkFinding = useUnlinkTestCaseFromFinding();
    const linkAsset = useLinkTestCaseToAsset();
    const unlinkAsset = useUnlinkTestCaseFromAsset();
    const linkVault = useLinkTestCaseToVaultItem();
    const unlinkVault = useUnlinkTestCaseFromVaultItem();
    const linkCleanup = useLinkTestCaseToCleanup();
    const unlinkCleanup = useUnlinkTestCaseFromCleanup();

    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (!testcase) return;
        if (type === 'findings') await linkFinding.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'assets') await linkAsset.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'vault') await linkVault.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: testcase.id, resourceId });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (!testcase) return;
        if (type === 'findings') await unlinkFinding.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'assets') await unlinkAsset.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: testcase.id, resourceId });
    };

    const linkedIds: LinkedIdMap = {
        findings: new Set((testcase?.findings ?? []).map((f: any) => f.id)),
        testcases: new Set(),
        assets: new Set((testcase?.assets ?? []).map((a: any) => a.id)),
        vault: new Set((testcase?.vault_items ?? []).map((v: any) => v.id)),
        cleanup: new Set((testcase?.cleanup_artifacts ?? []).map((c: any) => c.id)),
        intel: new Set(intelItems.map((i: any) => i.id)),
        infra: new Set(infraItems.map((i: any) => i.id)),
    };

    const linkedNotes = testcase
        ? allNotes.filter((n: any) => n.linked_testcases?.some((t: any) => t.id === testcase.id))
        : [];

    const catStyle = testcase ? (categoryStyles[testcase.category] || categoryStyles.OTHER) : categoryStyles.OTHER;
    const CatIcon = catStyle.icon;

    const handleDelete = async () => {
        if (!testcase) return;
        const confirmed = await confirm({
            title: 'Delete Test Case',
            description: 'Are you sure you want to delete this test case? This action cannot be undone.',
        });
        if (!confirmed) return;
        try {
            await deleteTestCase.mutateAsync({ id: testcase.id });
            onOpenChange(false);
            toast.success('Test case deleted');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to delete test case'));
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
                    {isLoading || !testcase ? (
                        <div className="flex items-center justify-center h-full">
                            <VisuallyHidden><SheetTitle>Loading test case details</SheetTitle></VisuallyHidden>
                            <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
                        </div>
                    ) : (
                        <div className="flex flex-col h-full">
                            {/* Accent bar */}
                            <div className={cn('h-1.5 w-full shrink-0', catStyle.accent)} />

                            {/* Header */}
                            <SheetHeader className="p-5 pb-0">
                                <div className="flex items-start gap-3 pr-8">
                                    <div className="min-w-0 flex-1">
                                        <SheetTitle className="text-xl font-bold text-white tracking-tight leading-tight">
                                            {testcase.title}
                                        </SheetTitle>
                                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                                            <Badge className={cn('gap-1.5 px-2 py-0.5 text-[10px] font-bold uppercase border', catStyle.color)}>
                                                <CatIcon className="h-3 w-3" />
                                                {testcase.category?.replace('_', ' ')}
                                            </Badge>
                                            {/* Execution status */}
                                            {testcase.is_executed ? (
                                                <Badge className={cn('px-2 py-0.5 text-[10px] border gap-1.5',
                                                    testcase.is_successful
                                                        ? 'bg-green-500/10 text-green-400 border-green-500/20'
                                                        : 'bg-red-500/10 text-red-400 border-red-500/20'
                                                )}>
                                                    {testcase.is_successful
                                                        ? <><CheckCircle className="h-3 w-3" /> Passed</>
                                                        : <><XCircle className="h-3 w-3" /> Failed</>
                                                    }
                                                </Badge>
                                            ) : (
                                                <Badge className="px-2 py-0.5 text-[10px] border bg-slate-500/10 text-slate-400 border-slate-500/20">
                                                    Pending
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
                                        onClick={() => { onOpenChange(false); router.push(`/testcases/${testcase.id}?engagementId=${engagementId}&tab=testcases`); }}
                                    >
                                        <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> Full Page
                                    </Button>
                                    {canEdit && (
                                        <Button
                                            size="sm" variant="outline"
                                            className="border-slate-700 text-slate-300 text-xs h-8"
                                            onClick={() => { onOpenChange(false); router.push(`/testcases/${testcase.id}/edit?engagementId=${engagementId}&tab=testcases`); }}
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
                                {testcase.description && (
                                    <>
                                        <div>
                                            <div className="flex items-center gap-2 mb-2">
                                                <FileText className="h-4 w-4 text-primary" />
                                                <h4 className="text-sm font-bold text-white">Description</h4>
                                            </div>
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50">
                                                <MarkdownPreview value={testcase.description} theme="dark" />
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Steps */}
                                {testcase.steps && (
                                    <>
                                        <div>
                                            <div className="flex items-center gap-2 mb-2">
                                                <CheckSquare className="h-4 w-4 text-emerald-400" />
                                                <h4 className="text-sm font-bold text-white">Steps</h4>
                                            </div>
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-900/40 p-3 rounded-lg border border-slate-800/60">
                                                <MarkdownPreview value={testcase.steps} theme="dark" />
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Expected result */}
                                {testcase.expected_result && (
                                    <>
                                        <div>
                                            <div className="flex items-center gap-2 mb-2">
                                                <CheckCircle className="h-4 w-4 text-green-400" />
                                                <h4 className="text-sm font-bold text-white">Expected Result</h4>
                                            </div>
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50">
                                                <MarkdownPreview value={testcase.expected_result} theme="dark" />
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Actual result (if executed) */}
                                {testcase.is_executed && testcase.actual_result && (
                                    <>
                                        <div>
                                            <div className="flex items-center gap-2 mb-2">
                                                {testcase.is_successful
                                                    ? <CheckCircle className="h-4 w-4 text-green-400" />
                                                    : <XCircle className="h-4 w-4 text-red-400" />}
                                                <h4 className="text-sm font-bold text-white">Actual Result</h4>
                                            </div>
                                            <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50">
                                                <MarkdownPreview value={testcase.actual_result} theme="dark" />
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Classification (portion marking) */}
                                {canEdit && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Classification Marking</h4>
                                            <EntityClassificationField
                                                engagementId={testcase.engagement_id}
                                                level={testcase.classification_level || null}
                                                suffix={testcase.classification_suffix || null}
                                                inheritLabel="Inherit (engagement default)"
                                                label=""
                                                onChange={async (lvl, suf) => {
                                                    try {
                                                        await updateTestCase.mutateAsync({ id: testcase.id, classification_level: lvl, classification_suffix: suf });
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
                                {(canEdit || (testcase.attack_technique_ids?.length ?? 0) > 0) && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                ATT&amp;CK Techniques
                                                {(testcase.attack_technique_ids?.length ?? 0) > 0 && (
                                                    <span className="text-slate-600 ml-1">({testcase.attack_technique_ids?.length})</span>
                                                )}
                                            </h4>
                                            {canEdit ? (
                                                <TechniquePicker
                                                    value={testcase.attack_technique_ids || []}
                                                    onChange={async (ids) => {
                                                        try {
                                                            await updateTestCase.mutateAsync({ id: testcase.id, attack_technique_ids: ids });
                                                        } catch (e: any) {
                                                            toast.error(getErrorMessage(e, 'Failed to update techniques'));
                                                        }
                                                    }}
                                                    placeholder="Map ATT&CK techniques…"
                                                />
                                            ) : (
                                                <div className="flex flex-wrap gap-1.5">
                                                    {(testcase.attack_technique_ids || []).map((tid: string) => {
                                                        const tech = TECHNIQUE_MAP.get(tid);
                                                        return (
                                                            <Badge
                                                                key={tid}
                                                                variant="secondary"
                                                                className="bg-purple-500/15 text-purple-400 border-purple-500/30 gap-1 text-xs"
                                                            >
                                                                <Shield className="h-3 w-3 shrink-0" />
                                                                {tech ? `${tech.id} ${tech.name}` : tid}
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

                                {/* Linked Findings */}
                                <div>
                                    <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                        Linked Findings {(testcase.findings?.length ?? 0) > 0 && <span className="text-slate-600 ml-1">({testcase.findings?.length})</span>}
                                    </h4>
                                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                                        {(testcase.findings ?? []).length > 0 ? (
                                            (testcase.findings ?? []).map((f: any) => (
                                                <Link
                                                    key={f.id}
                                                    href={`/findings/${f.id}?engagementId=${engagementId}&tab=testcases`}
                                                    className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-red-500/30 transition-colors group"
                                                    onClick={() => onOpenChange(false)}
                                                >
                                                    <Bug className="h-3.5 w-3.5 text-red-400 shrink-0" />
                                                    <span className="text-xs font-medium text-white group-hover:text-red-300 truncate">{f.title}</span>
                                                    {f.severity && (
                                                        <Badge className={cn('text-[8px] px-1 py-0 h-4 border ml-auto shrink-0 uppercase font-bold', severityBadge[f.severity] || severityBadge.INFO)}>
                                                            {f.severity}
                                                        </Badge>
                                                    )}
                                                </Link>
                                            ))
                                        ) : (
                                            <div className="text-[10px] text-slate-500 italic p-3 text-center border border-dashed border-slate-800 rounded-lg">
                                                No findings linked
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <Separator className="bg-slate-800/60" />

                                {/* Linked Assets */}
                                {testcase.assets && testcase.assets.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Linked Assets <span className="text-slate-600 ml-1">({testcase.assets.length})</span>
                                            </h4>
                                            <div className="space-y-1.5 max-h-40 overflow-y-auto">
                                                {testcase.assets.map((asset: any) => (
                                                    <Link
                                                        key={asset.id}
                                                        href={`/assets/${asset.id}?engagementId=${engagementId}&tab=testcases`}
                                                        className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-cyan-500/30 transition-colors group"
                                                        onClick={() => onOpenChange(false)}
                                                    >
                                                        <Server className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                                                        <span className="text-xs font-medium text-white group-hover:text-cyan-300 truncate">{asset.name}</span>
                                                        {asset.identifier && <span className="text-[10px] text-slate-500 font-mono truncate ml-auto shrink-0">{asset.identifier}</span>}
                                                    </Link>
                                                ))}
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Evidence */}
                                {testcase.evidence && testcase.evidence.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Evidence <span className="text-slate-600 ml-1">({testcase.evidence.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {testcase.evidence.map((ev: any) => (
                                                    <div key={ev.id} className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60">
                                                        <Paperclip className="h-3.5 w-3.5 text-pink-400 shrink-0" />
                                                        <span className="text-xs font-medium text-white truncate">{ev.original_filename}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Vault Items */}
                                {testcase.vault_items && testcase.vault_items.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Vault Items <span className="text-slate-600 ml-1">({testcase.vault_items.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {testcase.vault_items.map((vi: any) => (
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
                                {testcase.cleanup_artifacts && testcase.cleanup_artifacts.length > 0 && (
                                    <>
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">
                                                Cleanup Artifacts <span className="text-slate-600 ml-1">({testcase.cleanup_artifacts.length})</span>
                                            </h4>
                                            <div className="space-y-1.5">
                                                {testcase.cleanup_artifacts.map((ca: any) => (
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

                                <CustomFieldsDisplay entity="testcase" value={testcase.custom_fields} />

                                {/* Attack Chain */}
                                <ChainLinksSection
                                    engagementId={engagementId}
                                    entityType="testcase"
                                    entityId={testcase.id}
                                    entityName={testcase.title}
                                    canEdit={canEdit}
                                />
                                <Separator className="bg-slate-800/60" />

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
                                        <span className="text-slate-300 font-mono">{testcase.created_by_username || testcase.created_by?.slice(0, 8)}</span>
                                    </div>
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <Clock className="h-3 w-3" /> Created
                                        </span>
                                        <span className="text-slate-300">{parseUTCDate(testcase.created_at).toLocaleString()}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </SheetContent>
            </Sheet>
            {intelDetailId && <IntelDetailDialog itemId={intelDetailId} onClose={() => setIntelDetailId(null)} />}
            {testcase && (
                <LinkEntityDialog
                    open={linkDialogOpen}
                    onOpenChange={setLinkDialogOpen}
                    engagementId={engagementId}
                    entityType="testcase"
                    entityId={testcase.id}
                    entityName={testcase.title}
                    linkedIds={linkedIds}
                    onLink={handleEntityLink}
                    onUnlink={handleEntityUnlink}
                />
            )}
        </>
    );
}

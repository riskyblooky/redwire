'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
    Edit, Trash2, FileText, Loader2, Server, StickyNote, Bug,
    Sparkles, Lock, Key, User, Clock, Radar, Terminal,
    ExternalLink, CheckCircle, XCircle, MinusCircle, Circle, X,
    Globe, Zap, Flag, ArrowUpCircle, Layout, Play, Save, Plus, Layers,
    ClipboardCheck, Link as LinkIcon,
} from 'lucide-react';
import { useTestCase, useDeleteTestCase, useUpdateTestCase, useUnlinkFinding, useUnlinkAsset } from '@/lib/hooks/use-testcases';
import { useEngagement } from '@/lib/hooks/use-engagements';
import { useNotes } from '@/lib/hooks/use-notes';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { useInfraByEntity } from '@/lib/hooks/use-infra';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { MarkdownEditor, MarkdownPreview } from '@/components/ui/markdown-editor';
import { CustomFieldsDisplay } from '@/components/custom-fields/custom-fields-display';
import { ChainLinksSection } from '@/components/engagements/chain-links-section';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';
import { CleanupDetailModal } from '@/components/engagements/cleanup-detail-modal';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { EntityClassificationField } from '@/components/marking/entity-classification-field';
import { EvidenceUpload } from '@/components/findings/evidence-upload';
import { EvidenceCard } from '@/components/findings/evidence-card';
import DiscussionSection from '@/components/discussions/discussion-section';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { VersionHistoryPanel } from '@/components/ui/version-history-panel';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/auth-store';
import { useTags } from '@/lib/hooks/use-findings';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { buildTestcaseContext } from '@/lib/ai-entity-context';
import { InlineTextField } from '@/components/ui/inline/inline-text-field';
import { InlineMarkdownField } from '@/components/ui/inline/inline-markdown-field';
import { InlineComboboxField, InlineComboboxOption } from '@/components/ui/inline/inline-combobox-field';
import { InlineTagsField } from '@/components/ui/inline/inline-tags-field';
import { TagList } from '@/components/ui/tag-list';
import { CollapsibleSection } from '@/components/ui/collapsible-section';
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
import { UserName } from '@/components/ui/user-name';
import { UserAvatar } from '@/components/ui/user-avatar';
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
    const { user } = useAuthStore();
    const queryClient = useQueryClient();

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

    const { data: testcase, isLoading, refetch } = useTestCase(testcaseId || '');
    const { data: engagement } = useEngagement(testcase?.engagement_id || '');
    const { data: allNotes = [] } = useNotes(engagementId);
    const { data: intelItems = [] } = useIntelByEntity('testcase', testcaseId || '');
    const { data: infraItems = [] } = useInfraByEntity('testcase', testcaseId || '');

    // Real-time presence + live content refresh (mirrors the full page).
    const { activeUsers } = useCollaboration({
        resourceType: 'testcase',
        resourceId: testcaseId || '',
        enabled: !!testcase && open,
    });
    useCollaboration({
        resourceType: 'dashboard',
        resourceId: 'global',
        enabled: !!testcase && open,
        onMessage: (data) => {
            if (data.type === 'activity_log' && (data.resource_type || '').toLowerCase() === 'testcase' && data.resource_id === testcaseId) {
                queryClient.invalidateQueries({ queryKey: ['testcases', testcaseId] });
            }
        },
    });

    const deleteTestCase = useDeleteTestCase();
    const updateTestCase = useUpdateTestCase();
    const canEdit = useCanEdit(engagementId, 'testcase', testcase?.created_by);
    const canDelete = useCanDelete(engagementId, 'testcase', testcase?.created_by);
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);
    const [viewCleanup, setViewCleanup] = useState<any>(null);

    // Execution recording state
    const [actualResult, setActualResult] = useState('');
    const [isExecuting, setIsExecuting] = useState(false);

    // Inline-edit data sources
    const { data: allTags = [] } = useTags('testcase');
    const { data: testcaseTypes = [] } = useConfigurableTypes('testcase');
    const categoryOptions: InlineComboboxOption[] = testcaseTypes.map((t: any) => ({ value: t.name, label: t.name, color: t.color }));

    const unlinkFinding = useUnlinkFinding();
    const unlinkAsset = useUnlinkAsset();

    // Link/unlink hooks (link dialog)
    const linkFinding = useLinkTestCaseToFinding();
    const unlinkFindingHook = useUnlinkTestCaseFromFinding();
    const linkAsset = useLinkTestCaseToAsset();
    const unlinkAssetHook = useUnlinkTestCaseFromAsset();
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
        if (type === 'findings') await unlinkFindingHook.mutateAsync({ entityId: testcase.id, resourceId });
        if (type === 'assets') await unlinkAssetHook.mutateAsync({ entityId: testcase.id, resourceId });
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

    // Single-field patch through the update hook (PUT is a partial patch).
    const saveField = async (patch: Record<string, any>) => {
        if (!testcase) return;
        await updateTestCase.mutateAsync({ id: testcase.id, ...patch } as any);
    };

    const handleExecute = async (success: boolean | null) => {
        if (!testcase) return;
        try {
            await updateTestCase.mutateAsync({
                id: testcase.id,
                actual_result: actualResult || (testcase.actual_result || ''),
                is_executed: true,
                is_successful: success,
            });
            setIsExecuting(false);
            toast.success(success === true ? 'Marked as passed' : success === false ? 'Marked as failed' : 'Result recorded (no verdict)');
            refetch();
        } catch (error) {
            toast.error('Failed to update test case result');
        }
    };

    const handleSaveResult = async () => {
        if (!testcase) return;
        try {
            await updateTestCase.mutateAsync({ id: testcase.id, actual_result: actualResult });
            setIsExecuting(false);
            toast.success('Result saved');
            refetch();
        } catch (error) {
            toast.error('Failed to save result');
        }
    };

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
                                            <InlineTextField
                                                value={testcase.title}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ title: v })}
                                                className="text-xl font-bold text-white tracking-tight"
                                                placeholder="Test case title"
                                            />
                                        </SheetTitle>
                                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                                            {canEdit ? (
                                                <InlineComboboxField
                                                    value={testcase.category || ''}
                                                    options={categoryOptions}
                                                    canEdit={canEdit}
                                                    onSave={(v) => saveField({ category: v })}
                                                    placeholder="Search categories…"
                                                    emptyLabel="no category"
                                                />
                                            ) : (
                                                <Badge className={cn('gap-1.5 px-2 py-0.5 text-[10px] font-bold uppercase border', catStyle.color)}>
                                                    <CatIcon className="h-3 w-3" />
                                                    {testcase.category?.replace('_', ' ')}
                                                </Badge>
                                            )}
                                            {/* Execution status */}
                                            {testcase.is_executed ? (
                                                <Badge className={cn('px-2 py-0.5 text-[10px] border gap-1.5',
                                                    testcase.is_successful === true
                                                        ? 'bg-green-500/10 text-green-400 border-green-500/20'
                                                        : testcase.is_successful === false
                                                            ? 'bg-red-500/10 text-red-400 border-red-500/20'
                                                            : 'bg-slate-500/10 text-slate-300 border-slate-500/20'
                                                )}>
                                                    {testcase.is_successful === true
                                                        ? <><CheckCircle className="h-3 w-3" /> Passed</>
                                                        : testcase.is_successful === false
                                                            ? <><XCircle className="h-3 w-3" /> Failed</>
                                                            : <><MinusCircle className="h-3 w-3" /> Executed</>
                                                    }
                                                </Badge>
                                            ) : (
                                                <Badge className="px-2 py-0.5 text-[10px] border bg-slate-500/10 text-slate-400 border-slate-500/20">
                                                    Pending
                                                </Badge>
                                            )}
                                            {engagement && (
                                                <Link href={`/engagements/${engagement.id}?tab=testcases`} className="text-xs text-primary hover:underline flex items-center gap-1" onClick={() => onOpenChange(false)}>
                                                    <ClipboardCheck className="h-3 w-3" /> {engagement.name}
                                                </Link>
                                            )}
                                        </div>
                                        {canEdit ? (
                                            <div className="mt-2">
                                                <InlineTagsField
                                                    tags={testcase.tags}
                                                    allTags={allTags}
                                                    selectedIds={(testcase.tags || []).map((t: any) => t.id)}
                                                    canEdit={canEdit}
                                                    onSave={(ids) => saveField({ tag_ids: ids })}
                                                />
                                            </div>
                                        ) : (
                                            <TagList tags={testcase.tags} className="mt-2" />
                                        )}
                                    </div>
                                </div>

                                {/* Action bar */}
                                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-800/60">
                                    {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}
                                    <VersionHistoryPanel entityType="testcase" entityId={testcase.id} currentData={testcase} />
                                    <Button
                                        size="sm" variant="outline"
                                        className="border-slate-700 text-slate-300 text-xs h-8"
                                        onClick={() => { onOpenChange(false); router.push(`/testcases/${testcase.id}?engagementId=${engagementId}&tab=testcases`); }}
                                    >
                                        <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> Full Page
                                    </Button>
                                    <Button
                                        size="sm" variant="outline"
                                        className="border-primary/30 text-primary hover:bg-primary/10 text-xs h-8"
                                        onClick={() => { onOpenChange(false); router.push(`/findings/new?engagementId=${testcase.engagement_id}&testCaseId=${testcase.id}`); }}
                                    >
                                        <Bug className="h-3.5 w-3.5 mr-1.5" /> Add Finding
                                    </Button>
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
                                {(testcase.description || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Description" icon={FileText} iconColor="text-primary">
                                            <InlineMarkdownField
                                                value={testcase.description || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ description: v })}
                                                engagementId={testcase.engagement_id}
                                                fieldContext={{ resourceType: 'testcase', fieldName: 'description', entityContext: buildTestcaseContext(testcase) }}
                                                previewWrapperClassName="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50"
                                                emptyText="Double-click to add a description…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Steps */}
                                {(testcase.steps || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Execution Steps" icon={Terminal} iconColor="text-blue-400">
                                            <InlineMarkdownField
                                                value={testcase.steps || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ steps: v })}
                                                engagementId={testcase.engagement_id}
                                                fieldContext={{ resourceType: 'testcase', fieldName: 'steps', entityContext: buildTestcaseContext(testcase) }}
                                                previewWrapperClassName="bg-slate-900/40 p-2 rounded-lg border border-slate-800/60 overflow-hidden"
                                                emptyText="Double-click to add execution steps…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Expected result */}
                                {(testcase.expected_result || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Expected Result" icon={CheckCircle} iconColor="text-green-400">
                                            <InlineMarkdownField
                                                value={testcase.expected_result || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ expected_result: v })}
                                                engagementId={testcase.engagement_id}
                                                fieldContext={{ resourceType: 'testcase', fieldName: 'expected_result', entityContext: buildTestcaseContext(testcase) }}
                                                previewWrapperClassName="bg-green-500/5 border border-green-500/20 p-2 rounded-lg overflow-hidden"
                                                emptyText="Double-click to add the expected result…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Execution Result — record pass/fail/no-verdict + actual result */}
                                <CollapsibleSection
                                    title="Execution Result"
                                    icon={Play}
                                    iconColor="text-blue-400"
                                    right={testcase.is_executed && (
                                        <Badge className={cn('text-[10px] px-2 py-0.5', testcase.is_successful === true ? 'bg-green-500/10 text-green-400 border-green-500/20' : testcase.is_successful === false ? 'bg-red-500/10 text-red-400 border-red-500/20' : 'bg-slate-500/10 text-slate-300 border-slate-500/20')}>
                                            {testcase.is_successful === true ? 'Passed' : testcase.is_successful === false ? 'Failed' : 'No verdict'}
                                        </Badge>
                                    )}
                                    className={cn('rounded-lg border border-l-2 p-3',
                                        testcase.is_executed
                                            ? (testcase.is_successful === true ? 'bg-green-500/[0.04] border-l-green-500/60 border-slate-800'
                                                : testcase.is_successful === false ? 'bg-red-500/[0.04] border-l-red-500/60 border-slate-800'
                                                    : 'bg-slate-500/[0.04] border-l-slate-500/60 border-slate-800')
                                            : 'bg-slate-900/40 border-l-blue-500/50 border-slate-800')}
                                    contentClassName="mt-3"
                                >
                                    {!testcase.is_executed && !testcase.actual_result && !isExecuting ? (
                                        <div className="text-center py-4">
                                            <p className="text-slate-400 mb-3 text-xs">Not executed yet.</p>
                                            {canEdit && (
                                                <Button onClick={() => setIsExecuting(true)} size="sm" className="bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 border border-blue-500/30 hover:border-blue-500/50 text-xs">
                                                    <Play className="h-3.5 w-3.5 mr-1.5 fill-current" /> Record Result
                                                </Button>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            <Label className="text-slate-300 text-xs">Actual Result / Evidence</Label>
                                            {isExecuting ? (
                                                <MarkdownEditor
                                                    value={actualResult}
                                                    onChange={(val) => setActualResult(val)}
                                                    placeholder="Describe what happened during testing…"
                                                    minHeight="220px"
                                                />
                                            ) : (
                                                <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800 min-h-[80px] overflow-hidden">
                                                    <MarkdownPreview value={testcase.actual_result || 'No result recorded'} theme="dark" />
                                                </div>
                                            )}

                                            {isExecuting ? (
                                                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800">
                                                    <Button onClick={() => handleExecute(true)} size="sm" className="flex-1 min-w-[100px] h-9 bg-green-500/10 hover:bg-green-500/20 text-green-300 border border-green-500/30 hover:border-green-500/50 font-semibold text-xs">
                                                        <CheckCircle className="h-4 w-4 mr-1.5" /> Pass
                                                    </Button>
                                                    <Button onClick={() => handleExecute(false)} size="sm" className="flex-1 min-w-[100px] h-9 bg-red-500/10 hover:bg-red-500/20 text-red-300 border border-red-500/30 hover:border-red-500/50 font-semibold text-xs">
                                                        <XCircle className="h-4 w-4 mr-1.5" /> Fail
                                                    </Button>
                                                    <Button onClick={() => handleExecute(null)} variant="outline" size="sm" className="h-9 px-3 bg-slate-800/40 hover:bg-slate-800 text-slate-300 border border-slate-700 hover:border-slate-600 hover:text-white text-xs">
                                                        <MinusCircle className="h-4 w-4 mr-1.5" /> No Verdict
                                                    </Button>
                                                    <Button onClick={handleSaveResult} variant="outline" size="sm" className="h-9 px-3 bg-blue-500/5 hover:bg-blue-500/15 text-blue-300/90 border border-blue-500/25 hover:border-blue-500/40 text-xs">
                                                        <Save className="h-4 w-4 mr-1.5" /> Save
                                                    </Button>
                                                    <Button variant="ghost" size="sm" onClick={() => setIsExecuting(false)} className="h-9 text-slate-400 hover:text-white text-xs">
                                                        Cancel
                                                    </Button>
                                                </div>
                                            ) : (
                                                canEdit && (
                                                    <div className="flex justify-end">
                                                        <Button variant="outline" size="sm" onClick={() => { setActualResult(testcase.actual_result || ''); setIsExecuting(true); }} className="border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800 text-xs h-8">
                                                            <Edit className="h-3.5 w-3.5 mr-1.5" /> Update Result
                                                        </Button>
                                                    </div>
                                                )
                                            )}
                                        </div>
                                    )}
                                </CollapsibleSection>

                                <Separator className="bg-slate-800/60" />

                                {/* Notes (the test case's own notes field) */}
                                {(testcase.notes || canEdit) && (
                                    <>
                                        <CollapsibleSection title="Notes" icon={StickyNote} iconColor="text-teal-400">
                                            <InlineMarkdownField
                                                value={testcase.notes || ''}
                                                canEdit={canEdit}
                                                onSave={(v) => saveField({ notes: v })}
                                                engagementId={testcase.engagement_id}
                                                fieldContext={{ resourceType: 'testcase', fieldName: 'notes', entityContext: buildTestcaseContext(testcase) }}
                                                previewWrapperClassName="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-3 rounded-lg border border-slate-800/50"
                                                emptyText="Double-click to add notes…"
                                            />
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Evidence gallery */}
                                <CollapsibleSection
                                    title="Evidence"
                                    icon={Layers}
                                    iconColor="text-primary"
                                    defaultOpen={false}
                                    right={<Badge variant="outline" className="bg-primary/10 text-primary border-none px-1.5 h-5 text-[10px]">{testcase.evidence?.length || 0} files</Badge>}
                                    contentClassName="space-y-3"
                                >
                                    {canEdit && <EvidenceUpload testcaseId={testcase.id} />}
                                    {testcase.evidence && testcase.evidence.length > 0 ? (
                                        <div className="space-y-2">
                                            {testcase.evidence.map((ev: any) => (
                                                <EvidenceCard key={ev.id} evidence={ev} findingId={testcase.id} />
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="text-center py-4 text-slate-500 border border-dashed border-slate-800 rounded-lg bg-slate-950/20">
                                            <Plus className="h-6 w-6 mx-auto mb-1 opacity-20" />
                                            <p className="text-[11px]">No evidence attached</p>
                                        </div>
                                    )}
                                </CollapsibleSection>

                                <Separator className="bg-slate-800/60" />

                                {/* Classification (portion marking) */}
                                {canEdit && (
                                    <>
                                        <CollapsibleSection title="Classification Marking" icon={Shield} iconColor="text-slate-400">
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
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* ATT&CK Techniques */}
                                {(canEdit || (testcase.attack_technique_ids?.length ?? 0) > 0) && (
                                    <>
                                        <CollapsibleSection
                                            title="ATT&CK Techniques"
                                            icon={Shield}
                                            iconColor="text-purple-400"
                                            right={(testcase.attack_technique_ids?.length ?? 0) > 0 ? (
                                                <span className="text-[10px] text-slate-600">({testcase.attack_technique_ids?.length})</span>
                                            ) : undefined}
                                        >
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
                                        </CollapsibleSection>
                                        <Separator className="bg-slate-800/60" />
                                    </>
                                )}

                                {/* Linked Resources — the colored icon carries the type */}
                                <CollapsibleSection
                                    title="Linked Resources"
                                    icon={LinkIcon}
                                    iconColor="text-indigo-400"
                                    right={canEdit && (
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
                                >
                                {((testcase.findings?.length ?? 0) + (testcase.assets?.length ?? 0) + (testcase.vault_items?.length ?? 0) + (testcase.cleanup_artifacts?.length ?? 0) + intelItems.length + infraItems.length) > 0 ? (
                                    <div className="space-y-1.5 max-h-72 overflow-y-auto">
                                        {(testcase.findings ?? []).map((f: any) => (
                                            <div key={f.id} className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-red-500/30 transition-colors group">
                                                <Bug className="h-3.5 w-3.5 text-red-400 shrink-0" />
                                                <Link
                                                    href={`/findings/${f.id}?engagementId=${engagementId}&tab=testcases`}
                                                    className="text-xs font-medium text-white group-hover:text-red-300 truncate"
                                                    onClick={() => onOpenChange(false)}
                                                >
                                                    {f.title}
                                                </Link>
                                                {f.severity && (
                                                    <Badge className={cn('text-[8px] px-1 py-0 h-4 border ml-auto shrink-0 uppercase font-bold', severityBadge[f.severity] || severityBadge.INFO)}>
                                                        {f.severity}
                                                    </Badge>
                                                )}
                                                {canEdit && (
                                                    <Button
                                                        variant="ghost" size="icon"
                                                        className="h-6 w-6 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                                                        onClick={async () => {
                                                            const confirmed = await confirm({ title: 'Unlink Finding', description: `Remove the link between this test case and "${f.title}"?` });
                                                            if (confirmed) unlinkFinding.mutate({ testcaseId: testcase.id, findingId: f.id });
                                                        }}
                                                    >
                                                        <X className="h-3.5 w-3.5" />
                                                    </Button>
                                                )}
                                            </div>
                                        ))}
                                        {(testcase.assets ?? []).map((asset: any) => (
                                            <div key={asset.id}>
                                                <div className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-cyan-500/30 transition-colors group">
                                                    <Server className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                                                    <Link
                                                        href={`/assets/${asset.id}?engagementId=${engagementId}&tab=testcases`}
                                                        className="text-xs font-medium text-white group-hover:text-cyan-300 truncate"
                                                        onClick={() => onOpenChange(false)}
                                                    >
                                                        {asset.name}
                                                    </Link>
                                                    {asset.identifier && <span className="text-[10px] text-slate-500 font-mono truncate ml-auto shrink-0">{asset.identifier}</span>}
                                                    {canEdit && (
                                                        <Button
                                                            variant="ghost" size="icon"
                                                            className="h-6 w-6 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                                                            onClick={async () => {
                                                                const confirmed = await confirm({ title: 'Unlink Asset', description: `Remove the link between this test case and "${asset.name}"?` });
                                                                if (confirmed) unlinkAsset.mutate({ testcaseId: testcase.id, assetId: asset.id });
                                                            }}
                                                        >
                                                            <X className="h-3.5 w-3.5" />
                                                        </Button>
                                                    )}
                                                </div>
                                                {asset.linked_ports && asset.linked_ports.length > 0 && (
                                                    <div className="ml-6 mt-1 flex flex-wrap gap-1">
                                                        {asset.linked_ports.map((port: any) => (
                                                            <Badge
                                                                key={port.id}
                                                                variant="outline"
                                                                className={cn(
                                                                    'text-[10px] px-1.5 py-0 h-5 border-none font-mono font-bold',
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
                                        ))}
                                        {(testcase.vault_items ?? []).map((vi: any) => {
                                            const icon = vi.item_type === 'CREDENTIAL' ? <Lock className="h-3.5 w-3.5 text-amber-400 shrink-0" /> :
                                                vi.item_type === 'KEY' ? <Key className="h-3.5 w-3.5 text-primary shrink-0" /> :
                                                    <Shield className="h-3.5 w-3.5 text-emerald-400 shrink-0" />;
                                            return (
                                                <Link
                                                    key={vi.id}
                                                    href={`/engagements/${engagementId}?tab=vault`}
                                                    className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-amber-500/30 transition-colors group"
                                                    onClick={() => onOpenChange(false)}
                                                >
                                                    {icon}
                                                    <span className="text-xs font-medium text-white group-hover:text-amber-300 truncate">{vi.name}</span>
                                                </Link>
                                            );
                                        })}
                                        {(testcase.cleanup_artifacts ?? []).map((ca: any) => (
                                            <div key={ca.id} className="flex items-center justify-between p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 cursor-pointer hover:border-lime-500/30 hover:bg-lime-500/5 transition-colors" onClick={() => setViewCleanup(ca)}>
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <Sparkles className="h-3.5 w-3.5 text-lime-400 shrink-0" />
                                                    <span className="text-xs font-medium text-white truncate">{ca.title}</span>
                                                </div>
                                                <Badge variant="outline" className={cn(
                                                    'text-[8px] px-1 py-0 h-4 border-none uppercase font-bold shrink-0 ml-2',
                                                    ca.status === 'CLEANED' ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'
                                                )}>
                                                    {ca.status}
                                                </Badge>
                                            </div>
                                        ))}
                                        {intelItems.map((item: any) => (
                                            <button
                                                key={item.id}
                                                onClick={() => setIntelDetailId(item.id)}
                                                className="w-full flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-violet-500/30 transition-colors group text-left"
                                            >
                                                <Radar className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                                                <div className="flex-1 min-w-0">
                                                    <span className="text-xs font-medium text-white group-hover:text-violet-300 truncate block">{item.title || item.value}</span>
                                                    {item.cve_id && <span className="text-[9px] font-mono text-red-400">{item.cve_id}</span>}
                                                </div>
                                                {item.source_url && /^https?:\/\//i.test(item.source_url) && (
                                                    <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-violet-400 transition-colors shrink-0" onClick={(e) => e.stopPropagation()}>
                                                        <ExternalLink className="h-3 w-3" />
                                                    </a>
                                                )}
                                            </button>
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

                                {/* Metadata */}
                                <CollapsibleSection title="Metadata" icon={Clock} iconColor="text-slate-400" contentClassName="space-y-3">
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <User className="h-3 w-3" /> Created By
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <UserAvatar
                                                user={engagement?.assigned_users?.find((u: any) => u.id === testcase.created_by)}
                                                userId={testcase.created_by}
                                                username={testcase.created_by_username || testcase.created_by}
                                                className="h-5 w-5"
                                            />
                                            <UserName
                                                className="text-slate-300"
                                                user={engagement?.assigned_users?.find((u: any) => u.id === testcase.created_by)}
                                                name={testcase.created_by_full_name}
                                                username={testcase.created_by_username}
                                                fallback={testcase.created_by?.slice(0, 8)}
                                            />
                                        </div>
                                    </div>
                                    <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                            <Clock className="h-3 w-3" /> Created
                                        </span>
                                        <span className="text-slate-300">{parseUTCDate(testcase.created_at).toLocaleString()}</span>
                                    </div>
                                </CollapsibleSection>

                                <Separator className="bg-slate-800/60" />

                                {/* Discussion */}
                                <DiscussionSection
                                    engagementId={testcase.engagement_id}
                                    resourceType="testcase"
                                    resourceId={testcase.id}
                                    currentUserId={user?.id}
                                    isAdmin={user?.role === 'admin'}
                                    users={engagement?.assigned_users}
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
                onOpenChange={(open) => !open && setViewCleanup(null)}
            />
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

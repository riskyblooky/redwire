/**
 * testcases/[id]/page.tsx — Test Case Detail Page
 *
 * Comprehensive view of a single security test case. Layout:
 *  - Main column: description (Markdown), execution steps, expected
 *    result, execution result card (record pass/fail with actual result
 *    via Markdown editor), and evidence gallery with upload.
 *  - Sidebar: execution status widget (PASS/FAIL/PENDING), tags, linked
 *    findings (with severity badges and unlink capability), linked assets
 *    (with port details), vault items, cleanup artifacts, notes, intel
 *    items, and creation metadata.
 *  - Full-width discussion section at the bottom.
 *
 * Real-time presence via WebSocket; version history panel; permission-gated
 * edit/delete actions; "Add Finding" shortcut to create a finding linked
 * to this test case, with context-aware back navigation.
 */
'use client';

import { useParams } from '@/lib/hooks/use-params';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Label } from '@/components/ui/label';
import { ArrowLeft, Edit, Trash2, CheckSquare, Loader2, Play, CheckCircle2, XCircle, Zap, Flag, Layout, Circle, ArrowUpCircle, Globe, Radar, Calendar, Bug, X, Lock, Key, Shield, Sparkles, StickyNote, FileText, Terminal, User, Clock, ClipboardCheck, Target, Server, Layers, Plus, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react';
import { EvidenceUpload } from '@/components/findings/evidence-upload';
import { EvidenceCard } from '@/components/findings/evidence-card';
import { useTestCase, useUpdateTestCase, useDeleteTestCase, useUnlinkFinding, useUnlinkAsset } from '@/lib/hooks/use-testcases';
import { useEngagement } from '@/lib/hooks/use-engagements';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import Link from 'next/link';
import DiscussionSection from '@/components/discussions/discussion-section';
import { MarkdownEditor, MarkdownPreview } from '@/components/ui/markdown-editor';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { cn, parseUTCDate } from '@/lib/utils';
import { UserAvatar } from '@/components/ui/user-avatar';
import { VersionHistoryPanel } from '@/components/ui/version-history-panel';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
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
    useLinkTestCaseToFinding, useUnlinkTestCaseFromFinding,
    useLinkTestCaseToAsset, useUnlinkTestCaseFromAsset,
    useLinkTestCaseToVaultItem, useUnlinkTestCaseFromVaultItem,
    useLinkTestCaseToCleanup, useUnlinkTestCaseFromCleanup,
} from '@/lib/hooks/use-entity-links';
import { Link as LinkIcon } from 'lucide-react';

const categoryLabels: Record<string, string> = {
    RECONNAISSANCE: 'Reconnaissance',
    SCANNING: 'Scanning',
    EXPLOITATION: 'Exploitation',
    POST_EXPLOITATION: 'Post Exploitation',
    PRIVILEGE_ESCALATION: 'Privilege Escalation',
    WEB_APPLICATION: 'Web App',
    OTHER: 'Other',
};

const testCaseCategoryStyles: Record<string, { color: string; icon: any; accent: string }> = {
    RECONNAISSANCE: { color: 'bg-blue-500/10 text-blue-400 border-blue-500/20', icon: Globe, accent: 'bg-blue-500' },
    SCANNING: { color: 'bg-purple-500/10 text-purple-400 border-purple-500/20', icon: Radar, accent: 'bg-primary' },
    EXPLOITATION: { color: 'bg-red-500/10 text-red-400 border-red-500/20', icon: Zap, accent: 'bg-red-500' },
    POST_EXPLOITATION: { color: 'bg-orange-500/10 text-orange-400 border-orange-500/20', icon: Flag, accent: 'bg-orange-500' },
    PRIVILEGE_ESCALATION: { color: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20', icon: ArrowUpCircle, accent: 'bg-yellow-500' },
    WEB_APPLICATION: { color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20', icon: Layout, accent: 'bg-cyan-500' },
    OTHER: { color: 'bg-slate-500/10 text-slate-400 border-slate-500/20', icon: Circle, accent: 'bg-slate-500' },
};

const severityColors: Record<string, string> = {
    CRITICAL: 'bg-red-500/10 text-red-400 border-red-500/20',
    HIGH: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    MEDIUM: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    LOW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    INFO: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

export default function TestCaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const returnEngagementId = searchParams?.get('engagementId');
    const returnTab = searchParams?.get('tab') || 'testcases';
    const { user } = useAuthStore();

    const { data: testcase, isLoading: isLoadingTC, error, refetch } = useTestCase(id);
    const { data: engagement } = useEngagement(testcase?.engagement_id || '');

    const { activeUsers } = useCollaboration({
        resourceType: 'testcase',
        resourceId: id,
        enabled: !!testcase
    });
    const updateTestCase = useUpdateTestCase();
    const deleteTestCase = useDeleteTestCase();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const unlinkFinding = useUnlinkFinding();
    const unlinkAsset = useUnlinkAsset();
    const [viewCleanup, setViewCleanup] = useState<any>(null);
    const [isEvidenceCollapsed, setIsEvidenceCollapsed] = useState(false);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);

    // Link/unlink hooks
    const linkFinding = useLinkTestCaseToFinding();
    const unlinkFindingHook = useUnlinkTestCaseFromFinding();
    const linkAsset = useLinkTestCaseToAsset();
    const unlinkAssetHook = useUnlinkTestCaseFromAsset();
    const linkVault = useLinkTestCaseToVaultItem();
    const unlinkVault = useUnlinkTestCaseFromVaultItem();
    const linkCleanup = useLinkTestCaseToCleanup();
    const unlinkCleanup = useUnlinkTestCaseFromCleanup();

    const handleEntityLink = async (type: import('@/components/ui/link-entity-dialog').LinkResourceType, resourceId: string) => {
        if (type === 'findings') await linkFinding.mutateAsync({ entityId: id, resourceId });
        if (type === 'assets') await linkAsset.mutateAsync({ entityId: id, resourceId });
        if (type === 'vault') await linkVault.mutateAsync({ entityId: id, resourceId });
        if (type === 'cleanup') await linkCleanup.mutateAsync({ entityId: id, resourceId });
    };
    const handleEntityUnlink = async (type: import('@/components/ui/link-entity-dialog').LinkResourceType, resourceId: string) => {
        if (type === 'findings') await unlinkFindingHook.mutateAsync({ entityId: id, resourceId });
        if (type === 'assets') await unlinkAssetHook.mutateAsync({ entityId: id, resourceId });
        if (type === 'vault') await unlinkVault.mutateAsync({ entityId: id, resourceId });
        if (type === 'cleanup') await unlinkCleanup.mutateAsync({ entityId: id, resourceId });
    };

    // Get notes linked to this test case
    const { data: allNotes = [] } = useNotes(testcase?.engagement_id || '');
    const linkedNotes = allNotes.filter(n => n.linked_testcases?.some(t => t.id === id));

    // Get intel items linked to this test case
    const { data: linkedIntel = [] } = useIntelByEntity('testcase', id);
    const [intelDetailId, setIntelDetailId] = useState<string | null>(null);

    const [actualResult, setActualResult] = useState('');
    const [isExecuting, setIsExecuting] = useState(false);

    // Check permissions for edit/delete
    const canEdit = useCanEdit(testcase?.engagement_id, 'testcase', testcase?.created_by);
    const canDelete = useCanDelete(testcase?.engagement_id, 'testcase', testcase?.created_by);

    const handleExecute = async (success: boolean) => {
        try {
            await updateTestCase.mutateAsync({
                id: id,
                actual_result: actualResult || (testcase?.actual_result || ''),
                is_executed: true,
                is_successful: success,
            });
            setIsExecuting(false);
            refetch();
        } catch (error) {
            console.error('Failed to update test case result:', error);
            toast.error('Failed to update test case result');
        }
    };

    const handleDelete = async () => {
        const confirmed = await confirm({
            title: 'Delete Test Case',
            description: 'Are you sure you want to delete this test case?',
        });
        if (!confirmed) return;

        try {
            await deleteTestCase.mutateAsync({ id });
            const redirectPath = returnEngagementId
                ? `/engagements/${returnEngagementId}?tab=${returnTab}`
                : '/testcases';
            router.push(redirectPath);
        } catch (error: any) {
            console.error('Failed to delete test case:', error);
            toast.error(getErrorMessage(error, 'Failed to delete test case'));
        }
    };

    if (isLoadingTC) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    if (error || !testcase) {
        return (
            <DashboardLayout>
                <div className="p-6 text-center text-red-400">Test case not found.</div>
            </DashboardLayout>
        );
    }

    const categoryStyle = testCaseCategoryStyles[testcase.category] || testCaseCategoryStyles.OTHER;
    const CategoryIcon = categoryStyle.icon;

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                                const backPath = returnEngagementId
                                    ? `/engagements/${returnEngagementId}?tab=${returnTab}`
                                    : '/testcases';
                                router.push(backPath);
                            }}
                            className="text-slate-400 hover:text-white"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <div className="flex items-center gap-3">
                                <h1 className="text-3xl font-bold text-white tracking-tight">{testcase.title}</h1>
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                                <Badge className={cn("gap-1.5 py-0.5 px-2 font-bold text-[10px] uppercase tracking-wider border", categoryStyle.color)}>
                                    <CategoryIcon className="h-3 w-3" />
                                    {testcase.category.replace('_', ' ')}
                                </Badge>
                                {testcase.is_executed ? (
                                    <Badge className={cn(testcase.is_successful ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20')}>
                                        {testcase.is_successful ? 'Pass' : 'Fail'}
                                    </Badge>
                                ) : (
                                    <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20">Pending</Badge>
                                )}
                                {engagement && (
                                    <Link href={`/engagements/${engagement.id}?tab=${returnTab}`} className="text-sm text-primary hover:underline flex items-center gap-1 ml-2">
                                        <ClipboardCheck className="h-3 w-3" /> {engagement.name}
                                    </Link>
                                )}
                                {testcase.tags && testcase.tags.length > 0 && testcase.tags.map(tag => (
                                    <Badge
                                        key={tag.id}
                                        variant="outline"
                                        className="px-2 py-0.5 border-none font-bold text-[10px] uppercase tracking-wider"
                                        style={{ backgroundColor: `${tag.color}20`, color: tag.color }}
                                    >
                                        {tag.name}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-4 relative z-30">
                        {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}
                        <VersionHistoryPanel entityType="testcase" entityId={id} currentData={testcase} />
                        <div className="h-8 w-px bg-slate-800" />
                        <div className="flex gap-2">
                            {canEdit && (
                                <Button
                                    onClick={() => {
                                        const query = returnEngagementId ? `?engagementId=${returnEngagementId}&tab=${returnTab}` : '';
                                        router.push(`/testcases/${id}/edit${query}`);
                                    }}
                                    variant="outline"
                                    className="border-slate-700 text-slate-300"
                                >
                                    <Edit className="h-4 w-4 mr-2" /> Edit
                                </Button>
                            )}
                            <Button
                                onClick={() => {
                                    router.push(`/findings/new?engagementId=${testcase.engagement_id}&testCaseId=${id}`);
                                }}
                                variant="outline"
                                className="border-primary/30 text-primary hover:bg-primary/10"
                            >
                                <Bug className="h-4 w-4 mr-2" />
                                Add Finding
                            </Button>
                            {canDelete && (
                                <Button onClick={handleDelete} variant="outline" className="border-red-500/20 text-red-400 hover:bg-red-500/10">
                                    <Trash2 className="h-4 w-4 mr-2" /> Delete
                                </Button>
                            )}
                        </div>
                    </div>
                </div>

                {/* Main Grid: 4-col like findings */}
                <div className="grid gap-6 lg:grid-cols-4">
                    {/* Main Content - 3 cols */}
                    <div className="lg:col-span-3 space-y-6">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs overflow-hidden">
                            <div className={cn("h-1.5 w-full", categoryStyle.accent)} />
                            <CardContent className="p-0">
                                <div className="p-8 space-y-10">
                                    {/* Description Section */}
                                    <section>
                                        <div className="flex items-center gap-2 mb-4 text-white">
                                            <FileText className="h-5 w-5 text-primary" />
                                            <h3 className="text-xl font-bold tracking-tight">Description</h3>
                                        </div>
                                        <div className="prose prose-invert prose-sm max-w-none bg-slate-950/30 p-4 rounded-lg border border-slate-800/50">
                                            <MarkdownPreview value={testcase.description} theme="dark" />
                                        </div>
                                    </section>

                                    <Separator className="bg-slate-800/60" />

                                    {/* Execution Steps Section */}
                                    <section>
                                        <div className="flex items-center gap-2 mb-4 text-white">
                                            <Terminal className="h-5 w-5 text-blue-400" />
                                            <h3 className="text-xl font-bold tracking-tight">Execution Steps</h3>
                                        </div>
                                        <div className="bg-slate-950 p-2 rounded-xl border border-slate-800 shadow-inner overflow-hidden">
                                            <MarkdownPreview value={testcase.steps || 'No steps defined'} theme="dark" />
                                        </div>
                                    </section>

                                    <Separator className="bg-slate-800/60" />

                                    {/* Expected Result Section */}
                                    <section>
                                        <div className="flex items-center gap-2 mb-4 text-white">
                                            <CheckCircle2 className="h-5 w-5 text-green-400" />
                                            <h3 className="text-xl font-bold tracking-tight">Expected Result</h3>
                                        </div>
                                        <div className="bg-green-500/5 border border-green-500/20 p-2 rounded-xl shadow-[0_0_20px_rgba(34,197,94,0.03)] overflow-hidden">
                                            <MarkdownPreview value={testcase.expected_result || 'None'} theme="dark" />
                                        </div>
                                    </section>
                                    <CustomFieldsDisplay entity="testcase" value={testcase.custom_fields} className="pt-2" />
                                </div>
                            </CardContent>
                        </Card>

                        {/* Execution Result Card - Below main card, still in 3-col area */}
                        <Card className={cn("border-slate-800 backdrop-blur-xs", testcase.is_executed ? (testcase.is_successful ? 'bg-green-500/5' : 'bg-red-500/5') : 'bg-slate-900/50')}>
                            <CardHeader className="pb-3 border-b border-slate-800/60 mb-4">
                                <div className="flex items-center justify-between">
                                    <CardTitle className="text-white text-lg flex items-center gap-2">
                                        <Play className="h-4 w-4 text-blue-400" />
                                        Execution Result
                                    </CardTitle>
                                    {testcase.is_executed && (
                                        <Badge className={cn("text-sm px-3 py-1", testcase.is_successful ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20')}>
                                            {testcase.is_successful ? 'SUCCESS (PASS)' : 'FAILED (FAIL)'}
                                        </Badge>
                                    )}
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                {!testcase.is_executed && !isExecuting ? (
                                    <div className="text-center py-8">
                                        <p className="text-slate-400 mb-6 text-lg">This test case has not been executed yet.</p>
                                        {canEdit && (
                                            <Button onClick={() => setIsExecuting(true)} size="lg" className="bg-blue-600 hover:bg-blue-700 text-base px-8">
                                                <Play className="h-5 w-5 mr-2 fill-current" />
                                                Record Execution Result
                                            </Button>
                                        )}
                                    </div>
                                ) : (
                                    <div className="space-y-6">
                                        <div className="space-y-3">
                                            <Label className="text-slate-300 text-base">Actual Result / Evidence</Label>
                                            {isExecuting ? (
                                                <MarkdownEditor
                                                    value={actualResult}
                                                    onChange={(val) => setActualResult(val)}
                                                    placeholder="Describe exactly what happened during testing. Paste screenshots directly here..."
                                                    minHeight="400px"
                                                />
                                            ) : (
                                                <div className="bg-slate-950/50 p-6 rounded-xl border border-slate-800 min-h-[150px] overflow-hidden">
                                                    <MarkdownPreview value={testcase.actual_result || 'No result recorded'} theme="dark" />
                                                </div>
                                            )}
                                        </div>

                                        {isExecuting ? (
                                            <div className="flex gap-4 pt-4 border-t border-slate-800">
                                                <Button onClick={() => handleExecute(true)} size="lg" className="bg-green-600 hover:bg-green-700 flex-1 h-14 text-lg">
                                                    <CheckCircle2 className="h-6 w-6 mr-3" /> Pass Test
                                                </Button>
                                                <Button onClick={() => handleExecute(false)} size="lg" className="bg-red-600 hover:bg-red-700 flex-1 h-14 text-lg">
                                                    <XCircle className="h-6 w-6 mr-3" /> Fail Test
                                                </Button>
                                                <Button variant="ghost" size="lg" onClick={() => setIsExecuting(false)} className="text-slate-400 h-14">
                                                    Cancel
                                                </Button>
                                            </div>
                                        ) : (
                                            <div className="flex justify-end pt-2">
                                                {canEdit && (
                                                    <Button variant="outline" onClick={() => {
                                                        setActualResult(testcase.actual_result || '');
                                                        setIsExecuting(true);
                                                    }} className="border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800">
                                                        <Edit className="h-4 w-4 mr-2" />
                                                        Update Result
                                                    </Button>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )}
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
                                        {testcase.evidence?.length || 0} files
                                    </Badge>
                                </div>
                            </CardHeader>
                            {!isEvidenceCollapsed && (
                                <CardContent className="space-y-4 pt-4">
                                    {canEdit && (
                                        <EvidenceUpload testcaseId={testcase.id} />
                                    )}
                                    {testcase.evidence && testcase.evidence.length > 0 ? (
                                        <div className="space-y-3">
                                            {testcase.evidence.map((ev: any) => (
                                                <EvidenceCard key={ev.id} evidence={ev} findingId={testcase.id} />
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

                    {/* Sidebar - 1 col */}
                    <div className="space-y-6">
                        <Card className="border-slate-800 bg-slate-900/50 overflow-hidden relative">
                            <div className="absolute top-0 right-0 p-4 opacity-5">
                                <CheckSquare className="h-24 w-24" />
                            </div>
                            <CardHeader className="pb-4">
                                <CardTitle className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Test Details</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-8">
                                {/* Execution Status */}
                                <div className="flex flex-col items-center justify-center p-6 bg-slate-950/50 rounded-2xl border border-slate-800/50 shadow-inner">
                                    {testcase.is_executed ? (
                                        testcase.is_successful ? (
                                            <>
                                                <CheckCircle2 className="h-12 w-12 text-green-400 drop-shadow-[0_0_10px_rgba(34,197,94,0.3)] mb-2" />
                                                <span className="text-2xl font-black text-green-400 tracking-tight">PASS</span>
                                            </>
                                        ) : (
                                            <>
                                                <XCircle className="h-12 w-12 text-red-400 drop-shadow-[0_0_10px_rgba(239,68,68,0.3)] mb-2" />
                                                <span className="text-2xl font-black text-red-400 tracking-tight">FAIL</span>
                                            </>
                                        )
                                    ) : (
                                        <>
                                            <Play className="h-12 w-12 text-amber-400 opacity-40 mb-2" />
                                            <span className="text-2xl font-black text-amber-400/60 tracking-tight">PENDING</span>
                                        </>
                                    )}
                                    <span className="text-[9px] text-slate-500 font-black uppercase mt-2 tracking-widest">Execution Status</span>
                                </div>

                                <div className="space-y-6">
                                    {/* Tags */}
                                    {testcase.tags && testcase.tags.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Tags</h4>
                                            <div className="flex flex-wrap gap-1.5">
                                                {testcase.tags.map(tag => (
                                                    <Badge
                                                        key={tag.id}
                                                        variant="outline"
                                                        className="px-2 py-0.5 border-none font-bold text-[10px] uppercase tracking-wider"
                                                        style={{ backgroundColor: `${tag.color}20`, color: tag.color }}
                                                    >
                                                        {tag.name}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* ATT&CK Techniques */}
                                    {(canEdit || (testcase.attack_technique_ids?.length ?? 0) > 0) && (
                                        <div className="mb-4">
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">
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
                                    )}

                                    {/* Attack Chain */}
                                    <div className="mb-4">
                                        <ChainLinksSection
                                            engagementId={testcase.engagement_id}
                                            entityType="testcase"
                                            entityId={testcase.id}
                                            entityName={testcase.title}
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

                                    {/* Linked Findings */}
                                    {testcase.findings && testcase.findings.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Findings</h4>
                                            <div className="space-y-2">
                                                {testcase.findings.map((finding) => (
                                                    <div key={finding.id} className="flex items-center justify-between p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-slate-700 transition-colors group">
                                                        <div className="flex items-center gap-2 min-w-0">
                                                            <Badge className={cn('text-[8px] uppercase font-bold border px-1 py-0 h-4 shrink-0', severityColors[finding.severity] || severityColors.INFO)}>
                                                                {finding.severity}
                                                            </Badge>
                                                            <Link href={`/findings/${finding.id}?engagementId=${testcase.engagement_id}&tab=testcases`} className="text-xs font-bold text-white group-hover:text-primary transition-colors truncate">
                                                                {finding.title}
                                                            </Link>
                                                        </div>
                                                        {canEdit && (
                                                            <Button
                                                                variant="ghost"
                                                                size="icon"
                                                                className="h-6 w-6 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                                                                onClick={async () => {
                                                                    const confirmed = await confirm({
                                                                        title: 'Unlink Finding',
                                                                        description: `Remove the link between this test case and "${finding.title}"?`,
                                                                    });
                                                                    if (confirmed) {
                                                                        unlinkFinding.mutate({ testcaseId: id, findingId: finding.id });
                                                                    }
                                                                }}
                                                            >
                                                                <X className="h-3.5 w-3.5" />
                                                            </Button>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Linked Assets */}
                                    {testcase.assets && testcase.assets.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Assets</h4>
                                            <div className="space-y-2">
                                                {testcase.assets.map((asset: any) => (
                                                    <div key={asset.id}>
                                                        <div className="flex items-center justify-between p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-cyan-500/30 transition-colors group">
                                                            <div className="flex items-center gap-2 min-w-0">
                                                                <Server className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                                                                <Link href={`/assets/${asset.id}?engagementId=${testcase.engagement_id}&tab=testcases`} className="text-xs font-bold text-white group-hover:text-cyan-400 transition-colors truncate">
                                                                    {asset.name}
                                                                </Link>
                                                            </div>
                                                            {canEdit && (
                                                                <Button
                                                                    variant="ghost"
                                                                    size="icon"
                                                                    className="h-6 w-6 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                                                                    onClick={async () => {
                                                                        const confirmed = await confirm({
                                                                            title: 'Unlink Asset',
                                                                            description: `Remove the link between this test case and "${asset.name}"?`,
                                                                        });
                                                                        if (confirmed) {
                                                                            unlinkAsset.mutate({ testcaseId: id, assetId: asset.id });
                                                                        }
                                                                    }}
                                                                >
                                                                    <X className="h-3.5 w-3.5" />
                                                                </Button>
                                                            )}
                                                        </div>
                                                        {/* Show linked ports */}
                                                        {asset.linked_ports && asset.linked_ports.length > 0 && (
                                                            <div className="ml-6 mt-1 flex flex-wrap gap-1">
                                                                {asset.linked_ports.map((port: any) => (
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
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Linked Vault Items */}
                                    {testcase.vault_items && testcase.vault_items.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Vault Items</h4>
                                            <div className="space-y-2">
                                                {testcase.vault_items.map((vi: any) => {
                                                    const icon = vi.item_type === 'CREDENTIAL' ? <Lock className="h-3.5 w-3.5 text-amber-400 shrink-0" /> :
                                                        vi.item_type === 'KEY' ? <Key className="h-3.5 w-3.5 text-primary shrink-0" /> :
                                                            <Shield className="h-3.5 w-3.5 text-emerald-400 shrink-0" />;
                                                    return (
                                                        <Link href={`/engagements/${testcase.engagement_id}?tab=vault`} key={vi.id} className="flex items-center gap-2 p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-amber-500/30 transition-colors group">
                                                            {icon}
                                                            <span className="text-xs font-bold text-white group-hover:text-amber-300 truncate">{vi.name}</span>
                                                        </Link>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    )}

                                    {/* Linked Cleanup Artifacts */}
                                    {testcase.cleanup_artifacts && testcase.cleanup_artifacts.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Cleanup Artifacts</h4>
                                            <div className="space-y-2">
                                                {testcase.cleanup_artifacts.map((ca: any) => (
                                                    <div key={ca.id} className="flex items-center justify-between p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 cursor-pointer hover:border-lime-500/30 hover:bg-lime-500/5 transition-colors" onClick={() => setViewCleanup(ca)}>
                                                        <div className="flex items-center gap-2">
                                                            <Sparkles className="h-3.5 w-3.5 text-lime-400 shrink-0" />
                                                            <span className="text-xs font-bold text-white truncate">{ca.title}</span>
                                                        </div>
                                                        <Badge variant="outline" className={cn(
                                                            "text-[8px] px-1 py-0 h-4 border-none uppercase font-bold",
                                                            ca.status === 'CLEANED' ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'
                                                        )}>
                                                            {ca.status}
                                                        </Badge>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Linked Notes */}
                                    {linkedNotes.length > 0 && (
                                        <div>
                                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Linked Notes</h4>
                                            <div className="space-y-2">
                                                {linkedNotes.map(note => (
                                                    <Link
                                                        key={note.id}
                                                        href={`/engagements/${testcase.engagement_id}?tab=notes&noteId=${note.id}`}
                                                        className="flex items-center gap-2 p-2 rounded-lg bg-slate-950/40 border border-slate-800/60 hover:border-teal-500/30 transition-colors group"
                                                    >
                                                        <StickyNote className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                                                        <span className="text-xs font-medium text-slate-300 group-hover:text-teal-300 truncate">{note.title}</span>
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
                                                        {item.source_url && (
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

                                    <Separator className="bg-slate-800/40" />

                                    {/* Metadata */}
                                    <div className="space-y-4">
                                        {testcase.notes && (
                                            <div>
                                                <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Notes</h4>
                                                <p className="text-[11px] text-slate-400 leading-relaxed">{testcase.notes}</p>
                                            </div>
                                        )}
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
                                                <span className="text-slate-300 font-mono">
                                                    {engagement?.assigned_users?.find((u: any) => u.id === testcase.created_by)?.username || testcase.created_by_username || testcase.created_by?.slice(0, 8)}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="flex items-center justify-between text-[10px]">
                                            <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                                                <Clock className="h-3 w-3" /> Created
                                            </span>
                                            <span className="text-slate-300">{parseUTCDate(testcase.created_at).toLocaleString()}</span>
                                        </div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>

                {/* Discussions - Full Width */}
                <DiscussionSection
                    engagementId={testcase.engagement_id}
                    resourceType="testcase"
                    resourceId={id}
                    currentUserId={user?.id}
                    isAdmin={user?.role === 'admin'}
                    users={engagement?.assigned_users}
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
            engagementId={testcase.engagement_id}
            entityType="testcase"
            entityId={id}
            entityName={testcase.title}
            linkedIds={{
                findings:  new Set(testcase.findings?.map((f: any) => f.id) ?? []),
                testcases: new Set(),
                assets:    new Set(testcase.assets?.map((a: any) => a.id) ?? []),
                vault:     new Set(testcase.vault_items?.map((v: any) => v.id) ?? []),
                cleanup:   new Set(testcase.cleanup_artifacts?.map((c: any) => c.id) ?? []),
                intel:     new Set(),
                infra:     new Set(),
            }}
            onLink={handleEntityLink}
            onUnlink={handleEntityUnlink}
        />
        </DashboardLayout>
    );
}

/**
 * page.tsx — Engagement Detail Page (Controller)
 *
 * Top-level page for viewing and managing a single engagement. Acts as
 * the controller in a controller/view pattern:
 *
 *  - Fetches the engagement entity, manages global state (active tab,
 *    dialog visibility, selected items for cross-tab linking), and
 *    passes callbacks down to each tab component.
 *
 *  - Tab components (overview-tab, findings-tab, assets-tab, testcases-tab,
 *    team-tab, vault-tab, cleanup-tab, reporting-tab, notes-tab,
 *    attachments-tab) are lazy-loaded and handle their own data fetching.
 *
 *  - Page-level dialogs (Vault Create & Link, Link Asset to Test Case,
 *    Client Detail Modal, Team Management) are rendered here because
 *    they can be triggered from multiple tabs.
 *
 * Tab selection is synced to the URL search param `?tab=X` so that
 * deep links and browser back/forward work correctly.
 */
'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useParams } from '@/lib/hooks/use-params';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { PluginSlot, type PluginExtension } from '@/components/plugin-slot';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    ArrowLeft,
    FileText,
    Bug,
    Target,
    Loader2,
    Server,
    CheckSquare,
    Users,
    Paperclip,
    History,
    Lock,
    Shield,
    StickyNote,
    Sparkles,
} from 'lucide-react';



import { toast } from 'sonner';
import { useEngagement, useDeleteEngagement, useEngagementCounts } from '@/lib/hooks/use-engagements';
import { EngagementStatusControl } from '@/components/engagements/engagement-status-control';
import { AccessDenied } from '@/components/ui/access-denied';
import { useQueryClient as useQC } from '@tanstack/react-query';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { TeamManagementDialog } from '@/components/engagements/team-management-dialog';
import { AttachmentsTab } from '@/components/engagements/attachments-tab';
import { ActivityTab } from '@/components/engagements/activity-tab';
import { ReportingTab } from '@/components/engagements/reporting-tab';
import { EngagementMarkingBanner } from '@/components/marking/engagement-marking-banner';
import { VaultTab } from '@/components/engagements/vault-tab';
import { NotesTab } from '@/components/engagements/notes-tab';
import { CleanupTab } from '@/components/engagements/cleanup-tab';
import { OverviewTab } from '@/components/engagements/overview-tab';
import { FindingsTab } from '@/components/engagements/findings-tab';
import { AssetsTab } from '@/components/engagements/assets-tab';
import { TestCasesTab } from '@/components/engagements/testcases-tab';
import { TeamTab } from '@/components/engagements/team-tab';
import { AttackTab } from '@/components/engagements/attack-tab';
import { useAttackCoverage } from '@/lib/hooks/use-attack';
import { AssetImportDialog } from '@/components/engagements/asset-import-dialog';
import { AssetDetailSheet } from '@/components/engagements/asset-detail-sheet';
import { QuickCreateVaultDialog, QuickCreateCleanupDialog, type QuickLinkTarget } from '@/components/engagements/quick-create-dialogs';
import { useClients, useClientTypes } from '@/lib/hooks/use-clients';
import { ClientDetailModal } from '@/components/clients/client-detail-modal';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';



export default function EngagementDetailPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const [activeTab, setActiveTab] = useState('overview');

    const [isTeamDialogOpen, setIsTeamDialogOpen] = useState(false);
    const [viewClientDetail, setViewClientDetail] = useState(false);

    useEffect(() => {
        const tab = searchParams?.get('tab') || 'overview';
        setActiveTab(tab);
    }, [searchParams]);

    const handleTabChange = (tab: string) => {
        const params = new URLSearchParams(searchParams?.toString() || "");
        params.set('tab', tab);
        router.push(`?${params.toString()}`, { scroll: false });
    };

    const { data: engagement, isLoading: isLoadingEngagement, error } = useEngagement(id as string);
    // Cheap per-resource counts drive the tab badges so the detail page doesn't
    // have to load every asset/finding/test case list up front. Each tab's own
    // child component fetches its list lazily when the tab is opened.
    const { data: counts } = useEngagementCounts(id as string);

    // ── Live updates via WebSocket ──────────────────────────────
    const queryClient = useQC();
    useCollaboration({
        resourceType: 'engagement',
        resourceId: id as string,
        enabled: !!id,
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                const rt = (data.resource_type || '').toLowerCase();
                if (rt === 'finding')   queryClient.invalidateQueries({ queryKey: ['findings'] });
                if (rt === 'asset')     queryClient.invalidateQueries({ queryKey: ['assets'] });
                if (rt === 'testcase')  queryClient.invalidateQueries({ queryKey: ['testcases'] });
                if (rt === 'evidence')  queryClient.invalidateQueries({ queryKey: ['engagements', id, 'evidence'] });
                if (rt === 'engagement') queryClient.invalidateQueries({ queryKey: ['engagements', id] });
                // Any resource change can move a tab badge — refresh the counts.
                queryClient.invalidateQueries({ queryKey: ['engagements', id, 'counts'] });
                // Refresh activity log tab
                queryClient.invalidateQueries({ queryKey: ['engagement-logs', id] });
                queryClient.invalidateQueries({ queryKey: ['activity'] });
                // Refresh cleanup artifacts
                if (rt === 'cleanup_artifact') queryClient.invalidateQueries({ queryKey: ['cleanup-artifacts'] });
            }
            if (data.type === 'discussion_update') {
                queryClient.invalidateQueries({ queryKey: ['threads'] });
                queryClient.invalidateQueries({ queryKey: ['comments'] });
            }
        },
    });
    // ATT&CK coverage is heavy (loads all findings/test cases + their technique
    // maps) — only fetch it when the ATT&CK tab is open. The always-visible tab
    // badge uses the cheap counts.attack_techniques instead.
    const { data: coverage } = useAttackCoverage(id as string, activeTab === 'attack');
    // Clients + client types only feed the on-demand client-detail modal.
    const { data: engAllClients } = useClients(viewClientDetail);
    const { data: engClientTypes } = useClientTypes(viewClientDetail);
    const deleteEngagement = useDeleteEngagement();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // Quick-create a vault item / cleanup artifact linked to a row.
    const [vaultTarget, setVaultTarget] = useState<QuickLinkTarget | null>(null);
    const [vaultDialogOpen, setVaultDialogOpen] = useState(false);
    const [cleanupTarget, setCleanupTarget] = useState<QuickLinkTarget | null>(null);
    const [cleanupDialogOpen, setCleanupDialogOpen] = useState(false);
    const handleOpenVaultCreate = (target: QuickLinkTarget) => { setVaultTarget(target); setVaultDialogOpen(true); };
    const handleOpenCleanupCreate = (target: QuickLinkTarget) => { setCleanupTarget(target); setCleanupDialogOpen(true); };

    // Permission checks for engagement operations
    const canEditEngagement = useCanEdit(id, 'engagement' as any, engagement?.created_by);
    const canDeleteEngagement = useCanDelete(id, 'engagement' as any, engagement?.created_by);

    const handleEdit = () => {
        router.push(`/engagements/${id}/edit`);
    };

    const handleDelete = async () => {
        const confirmed = await confirm({
            title: 'Delete Engagement',
            description: 'Are you sure you want to delete this engagement? All associated findings, test cases, and data will be permanently removed.',
        });
        if (!confirmed) return;

        try {
            await deleteEngagement.mutateAsync(id);
            router.push('/engagements');
        } catch (error: any) {
            console.error('Failed to delete engagement:', error);
            toast.error(getErrorMessage(error, 'Failed to delete engagement'));
        }
    };

    const [showAssetImport, setShowAssetImport] = useState(false);
    const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

    if (isLoadingEngagement) {
        return (
            <DashboardLayout>
                <div className="flex h-full items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    if (error || !engagement) {
        // Handle unauthorized access explicitly
        const isForbidden = (error as any)?.response?.status === 403;

        if (isForbidden) {
            return (
                <DashboardLayout>
                    <div className="flex h-[calc(100vh-200px)] items-center justify-center">
                        <AccessDenied />
                    </div>
                </DashboardLayout>
            );
        }

        return (
            <DashboardLayout>
                <div className="p-6">
                    <div className="text-center">
                        <h2 className="text-2xl font-bold text-white">Engagement not found</h2>
                        <p className="text-slate-400 mt-2">The requested engagement could not be loaded.</p>
                        <Button onClick={() => router.push('/engagements')} className="mt-4">
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back to Engagements
                        </Button>
                    </div>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                <EngagementMarkingBanner engagement={engagement} />
                <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => router.push('/engagements')}
                            className="text-slate-400 hover:text-white"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-3xl font-bold text-white tracking-tight">{engagement.name}</h1>
                            <div className="flex items-center gap-2 mt-1">
                                <EngagementStatusControl engagement={engagement} canEdit={canEditEngagement} />
                                <Separator orientation="vertical" className="h-4 bg-slate-800" />
                                <span className="text-sm text-slate-400">{engagement.client_name}</span>
                            </div>
                        </div>
                    </div>

                    {/* Meta tabs (Overview / Team / Logs) — share the same Tabs parent as the main work tabs below */}
                    <TabsList className="bg-slate-950/40 border border-slate-800/60 p-1 h-auto rounded-lg gap-0.5">
                        <TabsTrigger
                            value="overview"
                            className="px-3 h-8 rounded-md text-xs font-semibold border border-transparent data-[state=active]:bg-indigo-500/10 data-[state=active]:text-indigo-400 data-[state=active]:border-indigo-500/30 hover:text-indigo-400/80 transition-colors"
                        >
                            <Target className="h-3.5 w-3.5 mr-1.5" />
                            Overview
                        </TabsTrigger>
                        <TabsTrigger
                            value="team"
                            className="px-3 h-8 rounded-md text-xs font-semibold border border-transparent data-[state=active]:bg-fuchsia-500/10 data-[state=active]:text-fuchsia-400 data-[state=active]:border-fuchsia-500/30 hover:text-fuchsia-400/80 transition-colors"
                        >
                            <Users className="h-3.5 w-3.5 mr-1.5" />
                            Team
                            {(engagement?.assigned_users?.length || 0) > 0 && (
                                <Badge variant="secondary" className="ml-1.5 bg-fuchsia-500/20 text-fuchsia-400 border-none px-1.5 h-4 text-[10px]">
                                    {engagement.assigned_users.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="logs"
                            className="px-3 h-8 rounded-md text-xs font-semibold border border-transparent data-[state=active]:bg-orange-500/10 data-[state=active]:text-orange-400 data-[state=active]:border-orange-500/30 hover:text-orange-400/80 transition-colors"
                        >
                            <History className="h-3.5 w-3.5 mr-1.5" />
                            Activity
                        </TabsTrigger>
                    </TabsList>
                </div>

                {/* Main work tabs */}
                    <TabsList className="bg-slate-950/40 border border-slate-800/60 p-1.5 h-auto flex-wrap justify-start gap-1 rounded-xl backdrop-blur-md">
                        <TabsTrigger
                            value="assets"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-blue-500/10 data-[state=active]:text-blue-400 data-[state=active]:border-blue-500/30 hover:border-blue-500/20 hover:text-blue-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Server className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Assets</span>
                            {(counts?.assets ?? 0) > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-blue-500/20 text-blue-400 border-none px-1.5 h-4 text-[10px]">
                                    {counts?.assets}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="testcases"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-400 data-[state=active]:border-emerald-500/30 hover:border-emerald-500/20 hover:text-emerald-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <CheckSquare className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Test Cases</span>
                            {(counts?.testcases ?? 0) > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-emerald-500/20 text-emerald-400 border-none px-1.5 h-4 text-[10px]">
                                    {counts?.testcases}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="findings"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-red-500/10 data-[state=active]:text-red-400 data-[state=active]:border-red-500/30 hover:border-red-500/20 hover:text-red-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Bug className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Findings</span>
                            {(counts?.findings ?? 0) > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-red-500/20 text-red-400 border-none px-1.5 h-4 text-[10px]">
                                    {counts?.findings}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="attack"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-violet-500/10 data-[state=active]:text-violet-400 data-[state=active]:border-violet-500/30 hover:border-violet-500/20 hover:text-violet-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Shield className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">ATT&amp;CK</span>
                            {(counts?.attack_techniques ?? 0) > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-violet-500/20 text-violet-400 border-none px-1.5 h-4 text-[10px]">
                                    {counts?.attack_techniques}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="notes"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-teal-500/10 data-[state=active]:text-teal-400 data-[state=active]:border-teal-500/30 hover:border-teal-500/20 hover:text-teal-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <StickyNote className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Notes</span>
                            {(counts?.notes ?? 0) > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-teal-500/20 text-teal-400 border-none px-1.5 h-4 text-[10px]">
                                    {counts?.notes}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="vault"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-amber-500/10 data-[state=active]:text-amber-400 data-[state=active]:border-amber-500/30 hover:border-amber-500/20 hover:text-amber-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Lock className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Vault</span>
                            {(counts?.vault ?? 0) > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-amber-500/20 text-amber-400 border-none px-1.5 h-4 text-[10px]">
                                    {counts?.vault}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="attachments"
                            className="flex-1 min-w-[150px] rounded-lg py-2.5 data-[state=active]:bg-pink-500/10 data-[state=active]:text-pink-400 data-[state=active]:border-pink-500/30 hover:border-pink-500/20 hover:text-pink-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Paperclip className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Attachments</span>
                            {(counts?.attachments ?? 0) > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-pink-500/20 text-pink-400 border-none px-1.5 h-4 text-[10px]">
                                    {counts?.attachments}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="cleanup"
                            className="flex-1 min-w-[150px] rounded-lg py-2.5 data-[state=active]:bg-lime-500/10 data-[state=active]:text-lime-400 data-[state=active]:border-lime-500/30 hover:border-lime-500/20 hover:text-lime-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Sparkles className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Cleanup</span>
                            {(counts?.cleanup ?? 0) > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-lime-500/20 text-lime-400 border-none px-1.5 h-4 text-[10px]">
                                    {counts?.cleanup}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="reporting"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-cyan-500/10 data-[state=active]:text-cyan-400 data-[state=active]:border-cyan-500/30 hover:border-cyan-500/20 hover:text-cyan-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <FileText className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Reporting</span>
                        </TabsTrigger>
                        {/* Plugin-registered tabs. Each entry from
                            /plugins/extensions/engagement.tabs renders as a
                            TabsTrigger; the matching TabsContent below picks
                            up the same value. The wrapper handles the styling
                            so plugins don't need to know about the tab shell. */}
                        <PluginSlot
                            slot="engagement.tabs"
                            engagementId={id}
                            renderWrapper={(entry: PluginExtension) => (
                                <TabsTrigger
                                    key={`plugin-tab-${entry.plugin_slug}-${entry.component}`}
                                    value={`plugin:${entry.plugin_slug}:${entry.component}`}
                                    className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-400 data-[state=active]:border-emerald-500/30 hover:border-emerald-500/20 hover:text-emerald-400/80 border border-transparent transition-all duration-300 group"
                                >
                                    <span className="font-semibold">{entry.label ?? entry.component}</span>
                                </TabsTrigger>
                            )}
                        />
                    </TabsList>

                    <TabsContent value="logs" className="mt-6 focus-visible:outline-hidden focus-visible:ring-0">
                        <ActivityTab engagementId={id} />
                    </TabsContent>

                    <TabsContent value="reporting" className="mt-8 focus-visible:outline-hidden focus-visible:ring-0">
                        <ReportingTab engagementId={id} engagementName={engagement.name} />
                    </TabsContent>

                    <TabsContent value="vault" className="mt-8 focus-visible:outline-hidden focus-visible:ring-0">
                        <VaultTab engagementId={id} />
                    </TabsContent>

                    <TabsContent value="cleanup" className="mt-8 focus-visible:outline-hidden focus-visible:ring-0">
                        <CleanupTab engagementId={id} />
                    </TabsContent>

                    <TabsContent value="notes" className="mt-8 focus-visible:outline-hidden focus-visible:ring-0">
                        <NotesTab engagementId={id} initialNoteId={searchParams?.get('noteId')} />
                    </TabsContent>

                    {/* Overview Tab */}
                    <TabsContent value="overview" className="mt-8 focus-visible:outline-hidden focus-visible:ring-0">
                        <OverviewTab
                            engagement={engagement}
                            engagementId={id}
                            onTabChange={handleTabChange}
                            onEdit={handleEdit}
                            onDelete={handleDelete}
                            canEditEngagement={canEditEngagement}
                            canDeleteEngagement={canDeleteEngagement}
                            onViewClientDetail={() => setViewClientDetail(true)}
                        />
                    </TabsContent>

                    {/* Findings Tab */}
                    <TabsContent value="findings" className="mt-6 focus-visible:outline-hidden focus-visible:ring-0">
                        <FindingsTab
                            engagementId={id}
                            onAddVaultItem={handleOpenVaultCreate}
                            onAddCleanup={handleOpenCleanupCreate}
                        />
                    </TabsContent>

                    {/* ATT&CK Tab — heatmap split between findings and testcases */}
                    <TabsContent value="attack" className="mt-6 focus-visible:outline-hidden focus-visible:ring-0">
                        <Tabs defaultValue="findings" className="space-y-4">
                            <TabsList className="bg-slate-950/40 border border-slate-800/60 p-1 h-auto rounded-lg gap-0.5 w-fit">
                                <TabsTrigger
                                    value="findings"
                                    className="px-3 h-8 rounded-md text-xs font-semibold border border-transparent data-[state=active]:bg-red-500/10 data-[state=active]:text-red-400 data-[state=active]:border-red-500/30 hover:text-red-400/80 transition-colors"
                                >
                                    <Bug className="h-3.5 w-3.5 mr-1.5" />
                                    Findings
                                    {coverage && coverage.mapped_findings > 0 && (
                                        <Badge variant="secondary" className="ml-1.5 bg-red-500/20 text-red-400 border-none px-1.5 h-4 text-[10px]">
                                            {coverage.mapped_findings}
                                        </Badge>
                                    )}
                                </TabsTrigger>
                                <TabsTrigger
                                    value="testcases"
                                    className="px-3 h-8 rounded-md text-xs font-semibold border border-transparent data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-400 data-[state=active]:border-emerald-500/30 hover:text-emerald-400/80 transition-colors"
                                >
                                    <CheckSquare className="h-3.5 w-3.5 mr-1.5" />
                                    Test Cases
                                    {coverage && coverage.mapped_testcases > 0 && (
                                        <Badge variant="secondary" className="ml-1.5 bg-emerald-500/20 text-emerald-400 border-none px-1.5 h-4 text-[10px]">
                                            {coverage.mapped_testcases}
                                        </Badge>
                                    )}
                                </TabsTrigger>
                            </TabsList>

                            <TabsContent value="findings" className="focus-visible:outline-hidden focus-visible:ring-0">
                                <AttackTab engagementId={id} source="finding" />
                            </TabsContent>

                            <TabsContent value="testcases" className="focus-visible:outline-hidden focus-visible:ring-0">
                                <AttackTab engagementId={id} source="testcase" />
                            </TabsContent>
                        </Tabs>
                    </TabsContent>

                    {/* Assets Tab */}
                    <TabsContent value="assets" className="mt-6">
                        <AssetsTab
                            engagementId={id}
                            onAddCleanup={handleOpenCleanupCreate}
                            onAddVaultItem={handleOpenVaultCreate}
                        />
                    </TabsContent>

                    {/* Test Cases Tab */}
                    <TabsContent value="testcases" className="mt-6">
                        <TestCasesTab
                            engagementId={id}
                            onAddVaultItem={handleOpenVaultCreate}
                            onAddCleanup={handleOpenCleanupCreate}
                        />
                    </TabsContent>

                    {/* Team Tab */}
                    <TabsContent value="team" className="mt-6">
                        <TeamTab
                            engagement={engagement}
                            canManageMembers={canEditEngagement}
                            onOpenTeamDialog={() => setIsTeamDialogOpen(true)}
                        />
                    </TabsContent>


                    <TabsContent value="attachments" className="mt-6 focus-visible:outline-hidden focus-visible:ring-0">
                        <AttachmentsTab engagementId={id} />
                    </TabsContent>
                    {/* Plugin-registered tab content. The wrapper picks
                        the value that matches the TabsTrigger above so
                        Radix routes the selection here when a plugin tab
                        is clicked. Each extension component receives
                        engagementId as a prop plus its own manifest entry. */}
                    <PluginSlot
                        slot="engagement.tabs"
                        engagementId={id}
                        props={{ engagementId: id }}
                        renderWrapper={(entry: PluginExtension, node) => (
                            <TabsContent
                                key={`plugin-content-${entry.plugin_slug}-${entry.component}`}
                                value={`plugin:${entry.plugin_slug}:${entry.component}`}
                                className="mt-6 focus-visible:outline-hidden focus-visible:ring-0"
                            >
                                {node}
                            </TabsContent>
                        )}
                    />
                </Tabs>

                {engagement && (
                    <TeamManagementDialog
                        engagement={engagement}
                        open={isTeamDialogOpen}
                        onOpenChange={setIsTeamDialogOpen}
                    />
                )}
                <ConfirmDialog />

                <QuickCreateVaultDialog
                    engagementId={id}
                    target={vaultTarget}
                    open={vaultDialogOpen}
                    onOpenChange={setVaultDialogOpen}
                />
            </div>

            <QuickCreateCleanupDialog
                engagementId={id}
                target={cleanupTarget}
                open={cleanupDialogOpen}
                onOpenChange={setCleanupDialogOpen}
            />

            {/* Client Detail View Modal */}
            {(engagement as any)?.client && (
                <ClientDetailModal
                    client={(engagement as any).client}
                    open={viewClientDetail}
                    onOpenChange={setViewClientDetail}
                    clientTypes={engClientTypes || []}
                    allClients={engAllClients || []}
                />
            )}

            {/* Asset Import Dialog */}
            <AssetImportDialog
                open={showAssetImport}
                onOpenChange={setShowAssetImport}
                engagementId={id}
            />

            {/* Asset Detail Sheet */}
            <AssetDetailSheet
                assetId={selectedAssetId}
                engagementId={id}
                open={!!selectedAssetId}
                onOpenChange={(open) => !open && setSelectedAssetId(null)}
                nonModal
            />

        </DashboardLayout>
    );
}

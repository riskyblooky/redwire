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

import { useState, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useParams } from '@/lib/hooks/use-params';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { PluginSlot, type PluginExtension } from '@/components/plugin-slot';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
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
    Key,
    Sparkles,
} from 'lucide-react';



import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useEngagement, useDeleteEngagement, useUpdateEngagement, useEngagementCounts } from '@/lib/hooks/use-engagements';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { useLinkVaultToFinding, useLinkVaultToTestCase, useLinkVaultToAsset } from '@/lib/hooks/use-vault';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/hooks/use-auth';
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
import { useCreateCleanupArtifact, useLinkCleanupToFinding, useLinkCleanupToTestCase, useLinkCleanupToAsset, CleanupArtifact } from '@/lib/hooks/use-cleanup-artifacts';
import { useClients, useClientTypes } from '@/lib/hooks/use-clients';
import { useEngagementTypes } from '@/lib/hooks/use-engagement-types';
import { ClientDetailModal } from '@/components/clients/client-detail-modal';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import api from '@/lib/api';

const statusColors: Record<string, string> = {
    PLANNING: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    IN_PROGRESS: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    REPORTING: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    COMPLETED: 'bg-green-500/10 text-green-400 border-green-500/20',
    ON_HOLD: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};



const engagementStatuses = [
    { value: 'PLANNING', label: 'Planning' },
    { value: 'SCOPING', label: 'Scoping' },
    { value: 'IN_PROGRESS', label: 'In Progress' },
    { value: 'REPORTING', label: 'Reporting' },
    { value: 'COMPLETED', label: 'Completed' },
    { value: 'ON_HOLD', label: 'On Hold' },
];


export default function EngagementDetailPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const [activeTab, setActiveTab] = useState('overview');

    // Sorting state
    const [sortFieldFindings] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_sort_engagement_findings_field') || 'created_at';
        }
        return 'created_at';
    });
    const [sortOrderFindings] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') {
            return (localStorage.getItem('redwire_sort_engagement_findings_order') as 'asc' | 'desc') || 'desc';
        }
        return 'desc';
    });
    const [sortFieldAssets] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_sort_engagement_assets_field') || 'name';
        }
        return 'name';
    });
    const [sortOrderAssets] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') {
            return (localStorage.getItem('redwire_sort_engagement_assets_order') as 'asc' | 'desc') || 'asc';
        }
        return 'asc';
    });
    const [sortFieldTestCases] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_sort_engagement_testcases_field') || 'title';
        }
        return 'title';
    });
    const [sortOrderTestCases] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') {
            return (localStorage.getItem('redwire_sort_engagement_testcases_order') as 'asc' | 'desc') || 'asc';
        }
        return 'asc';
    });

    const [isTeamDialogOpen, setIsTeamDialogOpen] = useState(false);
    const [viewClientDetail, setViewClientDetail] = useState(false);

    // Dynamic engagement type labels
    const { data: engagementTypes = [] } = useEngagementTypes();
    const typeLabels: Record<string, string> = {};
    engagementTypes.forEach(t => { typeLabels[t.name] = t.description || t.name; });

    // Save preferences to localStorage when they change
    useEffect(() => {
        localStorage.setItem('redwire_sort_engagement_findings_field', sortFieldFindings);
        localStorage.setItem('redwire_sort_engagement_findings_order', sortOrderFindings);
    }, [sortFieldFindings, sortOrderFindings]);

    useEffect(() => {
        localStorage.setItem('redwire_sort_engagement_assets_field', sortFieldAssets);
        localStorage.setItem('redwire_sort_engagement_assets_order', sortOrderAssets);
    }, [sortFieldAssets, sortOrderAssets]);

    useEffect(() => {
        localStorage.setItem('redwire_sort_engagement_testcases_field', sortFieldTestCases);
        localStorage.setItem('redwire_sort_engagement_testcases_order', sortOrderTestCases);
    }, [sortFieldTestCases, sortOrderTestCases]);

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
    const [assetsSearch] = useState('');
    const debouncedAssetsSearch = useDebounce(assetsSearch, 500);
    const [, setCurrentPageAssets] = useState(1);

    // Reset asset page when search or sort changes
    useEffect(() => {
        setCurrentPageAssets(1);
    }, [debouncedAssetsSearch, sortFieldAssets, sortOrderAssets]);

    // Findings and test cases are only consumed by the link dialogs, which are
    // reachable from the Findings / Test Cases tabs — load them lazily so the
    // default (Overview) landing doesn't pull both full lists up front.
    const needsFindingTestcaseLists = activeTab === 'findings' || activeTab === 'testcases';
    const { data: testcases = [] } = useTestCases(id, needsFindingTestcaseLists);
    // ATT&CK coverage is heavy (loads all findings/test cases + their technique
    // maps) — only fetch it when the ATT&CK tab is open. The always-visible tab
    // badge uses the cheap counts.attack_techniques instead.
    const { data: coverage } = useAttackCoverage(id as string, activeTab === 'attack');
    // Clients + client types only feed the on-demand client-detail modal.
    const { data: engAllClients } = useClients(viewClientDetail);
    const { data: engClientTypes } = useClientTypes(viewClientDetail);
    const deleteEngagement = useDeleteEngagement();
    const updateEngagement = useUpdateEngagement();
    const linkVaultToFinding = useLinkVaultToFinding();
    const linkVaultToTestCase = useLinkVaultToTestCase();
    const linkVaultToAsset = useLinkVaultToAsset();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const { user: currentUser } = useAuthStore();

    // Vault creation + linking state
    const [isVaultCreateDialogOpen, setIsVaultCreateDialogOpen] = useState(false);
    const [vaultLinkTarget, setVaultLinkTarget] = useState<{ type: 'finding' | 'testcase' | 'asset'; id: string; name: string } | null>(null);
    const [newVaultItem, setNewVaultItem] = useState({ name: '', item_type: 'CREDENTIAL' as string, username: '', password: '', note: '', description: '' });
    const [isCreatingVault, setIsCreatingVault] = useState(false);

    // Cleanup artifact quick-create state
    const createCleanupArtifact = useCreateCleanupArtifact();
    const linkCleanupToFinding = useLinkCleanupToFinding();
    const linkCleanupToTestCase = useLinkCleanupToTestCase();
    const linkCleanupToAsset = useLinkCleanupToAsset();
    const [isCleanupCreateDialogOpen, setIsCleanupCreateDialogOpen] = useState(false);
    const [cleanupLinkTarget, setCleanupLinkTarget] = useState<{ type: 'finding' | 'testcase' | 'asset'; id: string; name: string } | null>(null);
    const [newCleanupItem, setNewCleanupItem] = useState({ title: '', artifact_type: 'SSH_KEY' as string, location: '', description: '' });
    const [isCreatingCleanup, setIsCreatingCleanup] = useState(false);

    const handleOpenVaultCreate = (target: { type: 'finding' | 'testcase' | 'asset'; id: string; name: string }) => {
        setVaultLinkTarget(target);
        setNewVaultItem({ name: '', item_type: 'CREDENTIAL', username: '', password: '', note: '', description: '' });
        setIsVaultCreateDialogOpen(true);
    };

    const handleCreateAndLinkVault = async () => {
        if (!vaultLinkTarget || !newVaultItem.name) return;
        setIsCreatingVault(true);
        try {
            const res = await api.post('/vault', { ...newVaultItem, engagement_id: id });
            const createdId = res.data.id;
            if (vaultLinkTarget.type === 'finding') {
                await linkVaultToFinding.mutateAsync({ vaultItemId: createdId, findingId: vaultLinkTarget.id });
            } else if (vaultLinkTarget.type === 'testcase') {
                await linkVaultToTestCase.mutateAsync({ vaultItemId: createdId, testcaseId: vaultLinkTarget.id });
            } else {
                await linkVaultToAsset.mutateAsync({ vaultItemId: createdId, assetId: vaultLinkTarget.id });
            }
            const label = vaultLinkTarget.type === 'finding' ? 'finding' : vaultLinkTarget.type === 'testcase' ? 'test case' : 'asset';
            toast.success(`Vault item created and linked to ${label}`);
            setIsVaultCreateDialogOpen(false);
            queryClient.invalidateQueries({ queryKey: ['engagements', id, 'vault'] });
            queryClient.invalidateQueries({ queryKey: ['engagements', id, 'counts'] });
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to create vault item'));
        } finally {
            setIsCreatingVault(false);
        }
    };

    const handleOpenCleanupCreate = (target: { type: 'finding' | 'testcase' | 'asset'; id: string; name: string }) => {
        setCleanupLinkTarget(target);
        setNewCleanupItem({ title: '', artifact_type: 'SSH_KEY', location: '', description: '' });
        setIsCleanupCreateDialogOpen(true);
    };

    const handleCreateAndLinkCleanup = async () => {
        if (!cleanupLinkTarget || !newCleanupItem.title) return;
        setIsCreatingCleanup(true);
        try {
            const created = await createCleanupArtifact.mutateAsync({
                engagement_id: id,
                title: newCleanupItem.title,
                artifact_type: newCleanupItem.artifact_type as CleanupArtifact['artifact_type'],
                status: 'PENDING',
                location: newCleanupItem.location || undefined,
                description: newCleanupItem.description || undefined,
            } as any);
            if (cleanupLinkTarget.type === 'finding') {
                await linkCleanupToFinding.mutateAsync({ artifactId: created.id, findingId: cleanupLinkTarget.id });
            } else if (cleanupLinkTarget.type === 'testcase') {
                await linkCleanupToTestCase.mutateAsync({ artifactId: created.id, testcaseId: cleanupLinkTarget.id });
            } else {
                await linkCleanupToAsset.mutateAsync({ artifactId: created.id, assetId: cleanupLinkTarget.id });
            }
            const typeLabel = cleanupLinkTarget.type === 'finding' ? 'finding' : cleanupLinkTarget.type === 'testcase' ? 'test case' : 'asset';
            toast.success(`Cleanup artifact created and linked to ${typeLabel}`);
            setIsCleanupCreateDialogOpen(false);
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to create cleanup artifact'));
        } finally {
            setIsCreatingCleanup(false);
        }
    };

    // Permission checks for engagement operations
    const canEditEngagement = useCanEdit(id, 'engagement' as any, engagement?.created_by);
    const canDeleteEngagement = useCanDelete(id, 'engagement' as any, engagement?.created_by);

    const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);

    const handleStatusChange = async (newStatus: string) => {
        setIsUpdatingStatus(true);
        try {
            await updateEngagement.mutateAsync({
                id: id,
                status: newStatus
            });
        } catch (error) {
            console.error('Failed to update status:', error);
            alert('Failed to update engagement status');
        } finally {
            setIsUpdatingStatus(false);
        }
    };

    const tcStorageKey = `redwire_tc_expanded_${id}`;
    const [tcExpandedIds, setTcExpandedIds] = useState<Set<string>>(new Set());
    const tcInitialized = useRef(false);

    // Load saved state from localStorage on mount, or auto-expand if no saved state
    useEffect(() => {
        if (tcInitialized.current || testcases.length === 0) return;
        tcInitialized.current = true;

        const saved = localStorage.getItem(tcStorageKey);
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed)) {
                    setTcExpandedIds(new Set(parsed));
                    return;
                }
            } catch { /* ignore */ }
        }
        // No saved state — auto-expand all parents
        const parentIds = new Set(
            testcases.filter(tc => testcases.some(child => child.parent_id === tc.id)).map(tc => tc.id)
        );
        setTcExpandedIds(parentIds);
    }, [testcases, tcStorageKey]);

    // Persist expanded state (only after initialization)
    useEffect(() => {
        if (!tcInitialized.current) return;
        localStorage.setItem(tcStorageKey, JSON.stringify([...tcExpandedIds]));
    }, [tcExpandedIds, tcStorageKey]);


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
                                {(currentUser?.role === UserRole.ADMIN || currentUser?.role === UserRole.TEAM_LEAD) ? (
                                    <Select
                                        value={engagement.status}
                                        onValueChange={handleStatusChange}
                                        disabled={isUpdatingStatus}
                                    >
                                        <SelectTrigger className={cn(
                                            "h-7 w-fit min-w-[100px] px-2 py-0 border-none shadow-none focus:ring-0 text-[11px] font-bold uppercase",
                                            statusColors[engagement.status] || statusColors.PLANNING
                                        )}>
                                            {isUpdatingStatus ? (
                                                <Loader2 className="h-3 w-3 animate-spin mr-1" />
                                            ) : (
                                                <SelectValue />
                                            )}
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {engagementStatuses.map((s) => (
                                                <SelectItem
                                                    key={s.value}
                                                    value={s.value}
                                                    className={cn("my-1 mx-1 rounded-md font-medium text-[11px]", statusColors[s.value])}
                                                >
                                                    {s.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                ) : (
                                    <Badge className={cn("px-2 py-0.5", statusColors[engagement.status])}>
                                        {engagement.status.replace('_', ' ')}
                                    </Badge>
                                )}
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

                {/* Vault Create & Link Dialog */}
                <Dialog open={isVaultCreateDialogOpen} onOpenChange={setIsVaultCreateDialogOpen}>
                    <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[480px]">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Lock className="h-5 w-5 text-amber-400" />
                                Create & Link Vault Item
                            </DialogTitle>
                            <DialogDescription className="text-slate-400">
                                Create a new vault item linked to <span className="text-white font-semibold">{vaultLinkTarget?.name}</span>
                            </DialogDescription>
                        </DialogHeader>

                        <div className="space-y-4 py-2">
                            <div className="space-y-2">
                                <Label>Name</Label>
                                <Input
                                    value={newVaultItem.name}
                                    onChange={(e) => setNewVaultItem(p => ({ ...p, name: e.target.value }))}
                                    placeholder="e.g. Admin Credentials"
                                    className="bg-slate-950 border-slate-700 text-white"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Type</Label>
                                <Select value={newVaultItem.item_type} onValueChange={(v) => setNewVaultItem(p => ({ ...p, item_type: v }))}>
                                    <SelectTrigger className="bg-slate-950 border-slate-700 text-white">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-900 border-slate-700 text-white">
                                        <SelectItem value="CREDENTIAL"><div className="flex items-center gap-2"><Lock className="h-3.5 w-3.5 text-amber-400" /> Credential</div></SelectItem>
                                        <SelectItem value="KEY"><div className="flex items-center gap-2"><Key className="h-3.5 w-3.5 text-primary" /> API Key / Token</div></SelectItem>
                                        <SelectItem value="NOTE"><div className="flex items-center gap-2"><Shield className="h-3.5 w-3.5 text-emerald-400" /> Secure Note</div></SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            {newVaultItem.item_type === 'CREDENTIAL' && (
                                <>
                                    <div className="space-y-2">
                                        <Label>Username</Label>
                                        <Input
                                            value={newVaultItem.username}
                                            onChange={(e) => setNewVaultItem(p => ({ ...p, username: e.target.value }))}
                                            placeholder="admin"
                                            className="bg-slate-950 border-slate-700 text-white"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Password</Label>
                                        <Input
                                            type="password"
                                            value={newVaultItem.password}
                                            onChange={(e) => setNewVaultItem(p => ({ ...p, password: e.target.value }))}
                                            placeholder="••••••••"
                                            className="bg-slate-950 border-slate-700 text-white"
                                        />
                                    </div>
                                </>
                            )}
                            {(newVaultItem.item_type === 'KEY' || newVaultItem.item_type === 'NOTE') && (
                                <div className="space-y-2">
                                    <Label>{newVaultItem.item_type === 'KEY' ? 'Key / Token' : 'Note Content'}</Label>
                                    <Textarea
                                        value={newVaultItem.note}
                                        onChange={(e) => setNewVaultItem(p => ({ ...p, note: e.target.value }))}
                                        placeholder={newVaultItem.item_type === 'KEY' ? 'Paste API key or token...' : 'Enter secure note...'}
                                        className="bg-slate-950 border-slate-700 text-white font-mono text-xs"
                                        rows={3}
                                    />
                                </div>
                            )}
                            <div className="space-y-2">
                                <Label>Description (optional)</Label>
                                <Textarea
                                    value={newVaultItem.description}
                                    onChange={(e) => setNewVaultItem(p => ({ ...p, description: e.target.value }))}
                                    placeholder="Brief description..."
                                    className="bg-slate-950 border-slate-700 text-white text-xs"
                                    rows={2}
                                />
                            </div>
                        </div>

                        <DialogFooter>
                            <Button variant="ghost" onClick={() => setIsVaultCreateDialogOpen(false)}>Cancel</Button>
                            <Button
                                onClick={handleCreateAndLinkVault}
                                disabled={!newVaultItem.name || isCreatingVault}
                                className="bg-amber-600 hover:bg-amber-500 text-white"
                            >
                                {isCreatingVault ? (
                                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Creating...</>
                                ) : (
                                    <><Lock className="h-4 w-4 mr-2" /> Create & Link</>
                                )}
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </div>

            {/* Quick-Create Cleanup Artifact Dialog */}
            <Dialog open={isCleanupCreateDialogOpen} onOpenChange={setIsCleanupCreateDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[500px]">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Sparkles className="h-5 w-5 text-lime-400" />
                            Quick Add Cleanup Artifact
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">
                            Create a cleanup item and link it to{' '}
                            <span className="text-white font-semibold">{cleanupLinkTarget?.name}</span>
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 pt-2">
                        <div>
                            <label className="text-xs font-medium text-slate-400 block mb-1.5">Title *</label>
                            <Input
                                placeholder="e.g. Remove SSH key from target"
                                value={newCleanupItem.title}
                                onChange={(e) => setNewCleanupItem({ ...newCleanupItem, title: e.target.value })}
                                className="bg-slate-800/50 border-slate-700 text-white"
                            />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-slate-400 block mb-1.5">Type</label>
                            <Select
                                value={newCleanupItem.artifact_type}
                                onValueChange={(v) => setNewCleanupItem({ ...newCleanupItem, artifact_type: v })}
                            >
                                <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-800 border-slate-700">
                                    <SelectItem value="SSH_KEY">SSH Key</SelectItem>
                                    <SelectItem value="FILE">File</SelectItem>
                                    <SelectItem value="ACCOUNT">Account</SelectItem>
                                    <SelectItem value="PERMISSION">Permission</SelectItem>
                                    <SelectItem value="BACKDOOR">Backdoor</SelectItem>
                                    <SelectItem value="IMPLANT">Implant</SelectItem>
                                    <SelectItem value="OTHER">Other</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-slate-400 block mb-1.5">Location</label>
                            <Input
                                placeholder="e.g. /home/user/.ssh/authorized_keys"
                                value={newCleanupItem.location}
                                onChange={(e) => setNewCleanupItem({ ...newCleanupItem, location: e.target.value })}
                                className="bg-slate-800/50 border-slate-700 text-white"
                            />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-slate-400 block mb-1.5">Description</label>
                            <Textarea
                                placeholder="Brief description of the artifact..."
                                value={newCleanupItem.description}
                                onChange={(e) => setNewCleanupItem({ ...newCleanupItem, description: e.target.value })}
                                className="bg-slate-800/50 border-slate-700 text-white h-20 resize-none"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setIsCleanupCreateDialogOpen(false)} disabled={isCreatingCleanup}>Cancel</Button>
                        <Button
                            className="bg-lime-600 hover:bg-lime-500 text-white"
                            onClick={handleCreateAndLinkCleanup}
                            disabled={!newCleanupItem.title || isCreatingCleanup}
                        >
                            {isCreatingCleanup ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create & Link'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

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


// ═══════════════════════════════════════════════════════════════════
//  ENGAGEMENT SKILLS OVERVIEW CARD
// ═══════════════════════════════════════════════════════════════════

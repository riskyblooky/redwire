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

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useParams } from '@/lib/hooks/use-params';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { PluginSlot, type PluginExtension } from '@/components/plugin-slot';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    ArrowLeft, Edit, Trash2, Calendar, FileText, Bug, Target, Loader2, Server, Plus, CheckSquare, Play, AlertCircle, Users,
    Skull, Radar, EyeOff, CheckCircle, Globe, Link as LinkIcon, Monitor, Network as NetworkIcon, Box, MessageSquare,
    ArrowUpDown, ArrowUp, ArrowDown, Paperclip, History, Lock, ClipboardList, Files, ClipboardCheck, Folder,
    Zap, Flag, Layout, Circle, ArrowUpCircle, Search, TrendingUp, Activity as ActivityIcon, Clock, History as HistoryIcon,
    AlertTriangle, CheckCircle2, Shield, StickyNote, ChevronRight, ChevronDown, ChevronLeft, ChevronsLeft, ChevronsRight, CornerDownRight, Key, GitBranch,
    Building2, Mail, User, Eye, Sparkles, FolderTree, MoreVertical, GripVertical, TreePine, Table2, Upload, Filter, X, Download
} from 'lucide-react';

import {
    DndContext,
    closestCenter,
    PointerSensor,
    useSensor,
    useSensors,
    DragEndEvent,
    DragOverlay,
    DragStartEvent,
} from '@dnd-kit/core';
import {
    SortableContext,
    useSortable,
    verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer
} from 'recharts';

import { cn, getAvatarUrl } from '@/lib/utils';
import { toast } from 'sonner';
import { useEngagement, useDeleteEngagement, useUpdateEngagement } from '@/lib/hooks/use-engagements';
import { useAssets, useUpdateAsset, useDeleteAsset, useAssetPortFilters } from '@/lib/hooks/use-assets';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { useTestCases, useDeleteTestCase, useUpdateTestCase, buildTestCaseTree, flattenTree, TestCaseTreeNode, useLinkFinding, useUnlinkFinding, useLinkAsset, useUnlinkAsset } from '@/lib/hooks/use-testcases';
import { MoveTestCaseDialog } from '@/components/ui/move-testcase-dialog';
import { useFindings, useDeleteFinding, useUpdateFinding } from '@/lib/hooks/use-findings';
import { useVaultItems, useLinkVaultToFinding, useLinkVaultToTestCase, useLinkVaultToAsset } from '@/lib/hooks/use-vault';
import { useEngagementEvidence } from '@/lib/hooks/use-evidence';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/hooks/use-auth';
import { useFindingsTimeline } from '@/lib/hooks/use-stats';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { api as activityApi } from '@/lib/api';
import { ActivityLog } from '@/lib/types';
import { UserAvatar } from '@/components/ui/user-avatar';
import { AccessDenied } from '@/components/ui/access-denied';
import { LinkTooltip } from '@/components/ui/link-tooltip';
import { useQuery, useQueryClient as useQC } from '@tanstack/react-query';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { TeamManagementDialog } from '@/components/engagements/team-management-dialog';
import { AttachmentsTab } from '@/components/engagements/attachments-tab';
import { LogsTab } from '@/components/engagements/logs-tab';
import { ReportingTab } from '@/components/engagements/reporting-tab';
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
import { IntelLinkDialog } from '@/components/intel/intel-link-dialog';
import { IntelDetailDialog } from '@/components/intel/intel-detail-dialog';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { InfraLinkDialog } from '@/components/infra/infra-link-dialog';
import { useInfraByEntity } from '@/lib/hooks/use-infra';
import { useCleanupArtifacts, useCreateCleanupArtifact, useLinkCleanupToFinding, useLinkCleanupToTestCase, useLinkCleanupToAsset, CleanupArtifact } from '@/lib/hooks/use-cleanup-artifacts';
import { useNotes } from '@/lib/hooks/use-notes';
import { useClients, useClientTypes } from '@/lib/hooks/use-clients';
import { useEngagementTypes } from '@/lib/hooks/use-engagement-types';
import { ClientDetailModal } from '@/components/clients/client-detail-modal';
import { useRunbooks, useApplyRunbook, Runbook } from '@/lib/hooks/use-runbooks';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { usePermission, useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { relevanceComparator } from '@/lib/search-relevance';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import api from '@/lib/api';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Tooltip as RadixTooltip,
    TooltipContent as RadixTooltipContent,
    TooltipProvider as RadixTooltipProvider,
    TooltipTrigger as RadixTooltipTrigger,
} from '@/components/ui/tooltip';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import { useEngagementSkills, SKILL_LEVELS } from '@/lib/hooks/use-skills';
import { SkillsRadarChart, buildRadarData } from '@/components/ui/skills-radar-chart';

// Parse smart search syntax: port:80, service:http, etc.
function parseAssetSearch(input: string): { search: string; port?: number; service?: string } {
    let port: number | undefined;
    let service: string | undefined;
    let remaining = input;

    // Extract port:N
    const portMatch = remaining.match(/\bport:(\d+)/i);
    if (portMatch) {
        port = parseInt(portMatch[1], 10);
        remaining = remaining.replace(portMatch[0], '');
    }

    // Extract service:name
    const serviceMatch = remaining.match(/\bservice:(\S+)/i);
    if (serviceMatch) {
        service = serviceMatch[1];
        remaining = remaining.replace(serviceMatch[0], '');
    }

    return { search: remaining.trim(), port, service };
}

const statusColors: Record<string, string> = {
    PLANNING: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    IN_PROGRESS: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    REPORTING: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    COMPLETED: 'bg-green-500/10 text-green-400 border-green-500/20',
    ON_HOLD: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};



const engagementStatuses = [
    { value: 'PLANNING', label: 'Planning' },
    { value: 'IN_PROGRESS', label: 'In Progress' },
    { value: 'REPORTING', label: 'Reporting' },
    { value: 'COMPLETED', label: 'Completed' },
    { value: 'ON_HOLD', label: 'On Hold' },
];

const assetTypeLabels: Record<string, string> = {
    IP_ADDRESS: 'IP',
    DOMAIN: 'Domain',
    URL: 'URL',
    APPLICATION: 'App',
    SERVER: 'Server',
    NETWORK: 'Network',
    OTHER: 'Other',
};

const assetTypeStyles: Record<string, { color: string, icon: any }> = {
    IP_ADDRESS: { color: 'bg-blue-500/10 text-blue-400 border-blue-500/20', icon: Target },
    DOMAIN: { color: 'bg-green-500/10 text-green-400 border-green-500/20', icon: Globe },
    URL: { color: 'bg-purple-500/10 text-purple-400 border-purple-500/20', icon: LinkIcon },
    APPLICATION: { color: 'bg-pink-500/10 text-pink-400 border-pink-500/20', icon: Box },
    SERVER: { color: 'bg-orange-500/10 text-orange-400 border-orange-500/20', icon: Monitor },
    NETWORK: { color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20', icon: NetworkIcon },
    OTHER: { color: 'bg-slate-500/10 text-slate-400 border-slate-500/20', icon: Server },
};

const severityColors: any = {
    CRITICAL: 'bg-red-500/20 text-red-500 border-red-500/30',
    HIGH: 'bg-orange-500/20 text-orange-500 border-orange-500/30',
    MEDIUM: 'bg-amber-500/20 text-amber-500 border-amber-500/30',
    LOW: 'bg-blue-500/20 text-blue-500 border-blue-500/30',
    INFO: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

const severityOrder: Record<string, number> = {
    CRITICAL: 0,
    HIGH: 1,
    MEDIUM: 2,
    LOW: 3,
    INFO: 4,
};

const categoryColors: any = {
};

const testCaseCategoryStyles: Record<string, { color: string; icon: any }> = {
    RECONNAISSANCE: { color: 'bg-blue-500/10 text-blue-400 border-blue-500/20', icon: Globe },
    SCANNING: { color: 'bg-purple-500/10 text-purple-400 border-purple-500/20', icon: Radar },
    EXPLOITATION: { color: 'bg-red-500/10 text-red-400 border-red-500/20', icon: Zap },
    POST_EXPLOITATION: { color: 'bg-orange-500/10 text-orange-400 border-orange-500/20', icon: Flag },
    PRIVILEGE_ESCALATION: { color: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20', icon: ArrowUpCircle },
    WEB_APPLICATION: { color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20', icon: Layout },
    OTHER: { color: 'bg-slate-500/10 text-slate-400 border-slate-500/20', icon: Circle },
};

const findingStatusColors: Record<string, string> = {
    OPEN: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    IN_REVIEW: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    VERIFIED: 'bg-green-500/10 text-green-400 border-green-500/20',
    CLOSED: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
    FALSE_POSITIVE: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
};

const resourceTypeIcons: Record<string, any> = {
    engagement: Target,
    finding: Bug,
    asset: Server,
    testcase: CheckSquare,
    evidence: FileText,
    comment: MessageSquare,
};

const resourceTypeColors: Record<string, string> = {
    engagement: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    finding: 'bg-red-500/10 text-red-400 border-red-500/20',
    asset: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    testcase: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    evidence: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    comment: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

const getResourceLink = (activity: any) => {
    const type = activity.resource_type?.toLowerCase() || activity.type?.toLowerCase();
    const resourceId = activity.resource_id;
    const engagementId = activity.engagement_id;

    switch (type) {
        case 'engagement': return `/engagements/${resourceId}`;
        case 'finding': return `/findings/${resourceId}?engagementId=${engagementId}`;
        case 'asset': return `/assets/edit/${resourceId}?engagementId=${engagementId}`;
        case 'testcase': return `/testcases/${resourceId}?engagementId=${engagementId}`;
        case 'evidence': return `/engagements/${engagementId}?tab=attachments`;
        case 'comment': return `/findings/${activity.finding_id || resourceId}?engagementId=${engagementId}#discussion`;
        default: return null;
    }
};

export default function EngagementDetailPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const [activeTab, setActiveTab] = useState('overview');

    // Sorting state
    const [sortFieldFindings, setSortFieldFindings] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_sort_engagement_findings_field') || 'created_at';
        }
        return 'created_at';
    });
    const [sortOrderFindings, setSortOrderFindings] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') {
            return (localStorage.getItem('redwire_sort_engagement_findings_order') as 'asc' | 'desc') || 'desc';
        }
        return 'desc';
    });
    const [sortFieldAssets, setSortFieldAssets] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_sort_engagement_assets_field') || 'name';
        }
        return 'name';
    });
    const [sortOrderAssets, setSortOrderAssets] = useState<'asc' | 'desc'>(() => {
        if (typeof window !== 'undefined') {
            return (localStorage.getItem('redwire_sort_engagement_assets_order') as 'asc' | 'desc') || 'asc';
        }
        return 'asc';
    });
    const [sortFieldTestCases, setSortFieldTestCases] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('redwire_sort_engagement_testcases_field') || 'title';
        }
        return 'title';
    });
    const [sortOrderTestCases, setSortOrderTestCases] = useState<'asc' | 'desc'>(() => {
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
    const ASSET_PAGE_SIZE = 25;
    const [assetsSearch, setAssetsSearch] = useState('');
    const debouncedAssetsSearch = useDebounce(assetsSearch, 500);
    const [currentPageAssets, setCurrentPageAssets] = useState(1);
    const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
    const [showExportDialog, setShowExportDialog] = useState(false);
    const [exportColumns, setExportColumns] = useState<{ name: boolean; identifier: boolean; type: boolean }>({ name: true, identifier: true, type: false });
    const [isExporting, setIsExporting] = useState(false);

    // Parse smart search syntax
    const parsedSearch = useMemo(() => parseAssetSearch(debouncedAssetsSearch), [debouncedAssetsSearch]);

    // Fetch port filter options for dropdowns
    const { data: portFilterOptions } = useAssetPortFilters(id);

    // Reset asset page when search or sort changes
    useEffect(() => {
        setCurrentPageAssets(1);
    }, [debouncedAssetsSearch, sortFieldAssets, sortOrderAssets]);

    const { data: assets = [], isLoading: isLoadingAssets, refetch: refetchAssets, total: totalAssets } = useAssets({
        engagementId: id,
        search: parsedSearch.search || undefined,
        port: parsedSearch.port,
        service: parsedSearch.service,
        sortBy: sortFieldAssets,
        sortOrder: sortOrderAssets,
        skip: (currentPageAssets - 1) * ASSET_PAGE_SIZE,
        limit: ASSET_PAGE_SIZE,
    });
    const totalPagesAssets = Math.max(1, Math.ceil(totalAssets / ASSET_PAGE_SIZE));
    const { data: testcases = [], isLoading: isLoadingTestCases } = useTestCases(id);
    const findingsParams = useMemo(() => ({ engagement_id: id }), [id]);
    const { data: findings = [], isLoading: isLoadingFindings } = useFindings(findingsParams);
    const { data: vaultItems = [], refetch: refetchVault } = useVaultItems(id as string);
    const { data: evidence = [] } = useEngagementEvidence(id as string);
    const { data: notes = [] } = useNotes(id as string);
    const { data: coverage } = useAttackCoverage(id as string);

    // Build reverse-lookup maps: notes linked to each resource (with details for clickable links)
    const notesByFinding = useMemo(() => {
        const map: Record<string, { id: string; title: string }[]> = {};
        notes.forEach(n => n.linked_findings?.forEach(f => {
            if (!map[f.id]) map[f.id] = [];
            map[f.id].push({ id: n.id, title: n.title });
        }));
        return map;
    }, [notes]);
    const notesByTestCase = useMemo(() => {
        const map: Record<string, { id: string; title: string }[]> = {};
        notes.forEach(n => n.linked_testcases?.forEach(t => {
            if (!map[t.id]) map[t.id] = [];
            map[t.id].push({ id: n.id, title: n.title });
        }));
        return map;
    }, [notes]);
    const notesByAsset = useMemo(() => {
        const map: Record<string, { id: string; title: string }[]> = {};
        notes.forEach(n => n.linked_assets?.forEach(a => {
            if (!map[a.id]) map[a.id] = [];
            map[a.id].push({ id: n.id, title: n.title });
        }));
        return map;
    }, [notes]);
    const findingsByAsset = useMemo(() => {
        const map: Record<string, { count: number; items: { id: string; name: string }[] }> = {};
        findings.forEach(f => {
            const assetIds = f.asset_ids || (f.assets || []).map((a: any) => a.id);
            assetIds.forEach((aid: string) => {
                if (!map[aid]) map[aid] = { count: 0, items: [] };
                map[aid].count++;
                map[aid].items.push({ id: f.id, name: f.title });
            });
        });
        return map;
    }, [findings]);
    const testcasesByAsset = useMemo(() => {
        const map: Record<string, { count: number; items: { id: string; name: string }[] }> = {};
        (testcases || []).forEach((tc: any) => {
            (tc.assets || []).forEach((a: any) => {
                if (!map[a.id]) map[a.id] = { count: 0, items: [] };
                map[a.id].count++;
                map[a.id].items.push({ id: tc.id, name: tc.title });
            });
        });
        return map;
    }, [testcases]);

    const { data: cleanupArtifacts = [] } = useCleanupArtifacts(id as string);
    const { data: engAllClients } = useClients();
    const { data: engClientTypes } = useClientTypes();
    const deleteEngagement = useDeleteEngagement();
    const updateEngagement = useUpdateEngagement();
    const updateAsset = useUpdateAsset();
    const deleteAsset = useDeleteAsset();
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

    // Finding-link dialog state
    const linkFinding = useLinkFinding();
    const unlinkFinding = useUnlinkFinding();
    const [isFindingLinkDialogOpen, setIsFindingLinkDialogOpen] = useState(false);
    const [findingLinkTarget, setFindingLinkTarget] = useState<{ testcaseId: string; testcaseTitle: string } | null>(null);
    const [findingSearchTerm, setFindingSearchTerm] = useState('');
    const [selectedFindingIds, setSelectedFindingIds] = useState<Set<string>>(new Set());
    const [lastClickedFindingIndex, setLastClickedFindingIndex] = useState<number | null>(null);
    const [isApplyingFindingLinks, setIsApplyingFindingLinks] = useState(false);
    const [findingSeverityFilter, setFindingSeverityFilter] = useState<Set<string>>(new Set());

    // Asset-link dialog state
    const linkAsset = useLinkAsset();
    const unlinkAsset = useUnlinkAsset();
    const [isAssetLinkDialogOpen, setIsAssetLinkDialogOpen] = useState(false);
    const [assetLinkTarget, setAssetLinkTarget] = useState<{ testcaseId?: string; testcaseTitle?: string; findingId?: string; findingTitle?: string } | null>(null);
    const [assetSearchTerm, setAssetSearchTerm] = useState('');
    const [selectedAssetIds, setSelectedAssetIds] = useState<Set<string>>(new Set());
    const [selectedPortIds, setSelectedPortIds] = useState<Map<string, Set<string>>>(new Map());
    const [lastClickedAssetIndex, setLastClickedAssetIndex] = useState<number | null>(null);
    const [isApplyingAssetLinks, setIsApplyingAssetLinks] = useState(false);
    const [assetTypeFilter, setAssetTypeFilter] = useState<Set<string>>(new Set());

    // Intel link dialog state
    const [isIntelLinkDialogOpen, setIsIntelLinkDialogOpen] = useState(false);
    const [intelLinkTarget, setIntelLinkTarget] = useState<{ entityType: 'finding' | 'testcase'; entityId: string } | null>(null);

    const handleOpenIntelLink = (target: { entityType: 'finding' | 'testcase'; entityId: string }) => {
        setIntelLinkTarget(target);
        setIsIntelLinkDialogOpen(true);
    };

    // Infra link dialog state
    const [isInfraLinkDialogOpen, setIsInfraLinkDialogOpen] = useState(false);
    const [infraLinkTarget, setInfraLinkTarget] = useState<{ entityType: 'finding' | 'testcase'; entityId: string } | null>(null);

    const handleOpenInfraLink = (target: { entityType: 'finding' | 'testcase'; entityId: string }) => {
        setInfraLinkTarget(target);
        setIsInfraLinkDialogOpen(true);
    };
    const updateFindingForAssetLink = useUpdateFinding();

    // Fetch ALL assets for the link dialog (unpaginated) — only when dialog is open
    const { data: allAssets = [] } = useAssets({
        engagementId: id,
        limit: 500,
    });

    // Runbook import state
    const { data: runbooksList = [] } = useRunbooks();
    const applyRunbook = useApplyRunbook();
    const [isImportRunbookOpen, setIsImportRunbookOpen] = useState(false);
    const [importingRunbookId, setImportingRunbookId] = useState<string | null>(null);

    // Move test case dialog state
    const updateTestCase = useUpdateTestCase();
    const [isMoveDialogOpen, setIsMoveDialogOpen] = useState(false);
    const [moveTarget, setMoveTarget] = useState<{ id: string; title: string; parent_id: string | null } | null>(null);

    const handleOpenMove = (target: { id: string; title: string; parent_id: string | null }) => {
        setMoveTarget(target);
        setIsMoveDialogOpen(true);
    };

    const handleMove = async (testcaseId: string, newParentId: string | null) => {
        try {
            await updateTestCase.mutateAsync({ id: testcaseId, parent_id: newParentId });
            toast.success('Test case moved successfully');
            setIsMoveDialogOpen(false);
            setMoveTarget(null);
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to move test case'));
        }
    };

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
            refetchVault();
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

    const handleOpenFindingLink = (target: { testcaseId: string; testcaseTitle: string }) => {
        setFindingLinkTarget(target);
        setFindingSearchTerm('');
        // Pre-populate selection with already-linked findings
        const tc = testcases.find((tc: any) => tc.id === target.testcaseId);
        const alreadyLinked = new Set((tc?.findings || []).map((f: any) => f.id) as string[]);
        setSelectedFindingIds(alreadyLinked);
        setLastClickedFindingIndex(null);
        setFindingSeverityFilter(new Set());
        setIsFindingLinkDialogOpen(true);
    };

    const handleToggleFindingSelect = (findingId: string, index: number, shiftKey: boolean, filteredFindings: any[]) => {
        setSelectedFindingIds(prev => {
            const next = new Set(prev);
            if (shiftKey && lastClickedFindingIndex !== null) {
                const start = Math.min(lastClickedFindingIndex, index);
                const end = Math.max(lastClickedFindingIndex, index);
                const shouldSelect = !prev.has(findingId);
                for (let i = start; i <= end; i++) {
                    if (filteredFindings[i]) {
                        if (shouldSelect) {
                            next.add(filteredFindings[i].id);
                        } else {
                            next.delete(filteredFindings[i].id);
                        }
                    }
                }
            } else {
                if (next.has(findingId)) {
                    next.delete(findingId);
                } else {
                    next.add(findingId);
                }
            }
            return next;
        });
        setLastClickedFindingIndex(index);
    };

    const handleApplyFindingLinks = async () => {
        if (!findingLinkTarget) return;
        setIsApplyingFindingLinks(true);
        const tc = testcases.find((tc: any) => tc.id === findingLinkTarget.testcaseId);
        const currentlyLinked = new Set((tc?.findings || []).map((f: any) => f.id) as string[]);
        const toLink = [...selectedFindingIds].filter(id => !currentlyLinked.has(id));
        const toUnlink = [...currentlyLinked].filter(id => !selectedFindingIds.has(id));

        let linked = 0, unlinked = 0, errors = 0;
        for (const findingId of toLink) {
            try {
                await linkFinding.mutateAsync({ testcaseId: findingLinkTarget.testcaseId, findingId });
                linked++;
            } catch { errors++; }
        }
        for (const findingId of toUnlink) {
            try {
                await unlinkFinding.mutateAsync({ testcaseId: findingLinkTarget.testcaseId, findingId });
                unlinked++;
            } catch { errors++; }
        }

        const parts: string[] = [];
        if (linked > 0) parts.push(`${linked} linked`);
        if (unlinked > 0) parts.push(`${unlinked} unlinked`);
        if (errors > 0) parts.push(`${errors} failed`);
        if (parts.length > 0) {
            toast.success(`Findings: ${parts.join(', ')}`);
        } else {
            toast.info('No changes to apply');
        }
        setIsApplyingFindingLinks(false);
        setIsFindingLinkDialogOpen(false);
    };

    const handleOpenAssetLink = (target: { testcaseId: string; testcaseTitle: string }) => {
        setAssetLinkTarget(target);
        setAssetSearchTerm('');
        // Pre-populate selection with already-linked assets
        const tc = testcases.find((tc: any) => tc.id === target.testcaseId);
        const linkedAssets: any[] = tc?.assets || [];
        const alreadyLinked = new Set(linkedAssets.map((a: any) => a.id) as string[]);
        setSelectedAssetIds(alreadyLinked);
        // Pre-populate port selections from existing data
        const portMap = new Map<string, Set<string>>();
        for (const asset of linkedAssets) {
            if (asset.port_ids && asset.port_ids.length > 0) {
                portMap.set(asset.id, new Set(asset.port_ids));
            }
        }
        setSelectedPortIds(portMap);
        setLastClickedAssetIndex(null);
        setAssetTypeFilter(new Set());
        setIsAssetLinkDialogOpen(true);
    };

    const handleOpenAssetLinkForFinding = (target: { findingId: string; findingTitle: string }) => {
        setAssetLinkTarget(target);
        setAssetSearchTerm('');
        const finding = findings?.find((f: any) => f.id === target.findingId);
        const linkedAssets: any[] = finding?.assets || [];
        const alreadyLinked = new Set(linkedAssets.map((a: any) => a.id) as string[]);
        setSelectedAssetIds(alreadyLinked);
        // Pre-populate port selections from existing data
        const portMap = new Map<string, Set<string>>();
        for (const asset of linkedAssets) {
            if (asset.port_ids && asset.port_ids.length > 0) {
                portMap.set(asset.id, new Set(asset.port_ids));
            }
        }
        setSelectedPortIds(portMap);
        setLastClickedAssetIndex(null);
        setAssetTypeFilter(new Set());
        setIsAssetLinkDialogOpen(true);
    };

    const handleToggleAssetSelect = (assetId: string, index: number, shiftKey: boolean, filteredAssets: any[]) => {
        setSelectedAssetIds(prev => {
            const next = new Set(prev);
            if (shiftKey && lastClickedAssetIndex !== null) {
                const start = Math.min(lastClickedAssetIndex, index);
                const end = Math.max(lastClickedAssetIndex, index);
                const shouldSelect = !prev.has(assetId);
                for (let i = start; i <= end; i++) {
                    if (filteredAssets[i]) {
                        if (shouldSelect) {
                            next.add(filteredAssets[i].id);
                        } else {
                            next.delete(filteredAssets[i].id);
                        }
                    }
                }
            } else {
                if (next.has(assetId)) {
                    next.delete(assetId);
                } else {
                    next.add(assetId);
                }
            }
            return next;
        });
        setLastClickedAssetIndex(index);
    };

    const handleApplyAssetLinks = async () => {
        if (!assetLinkTarget) return;
        setIsApplyingAssetLinks(true);

        if (assetLinkTarget.findingId) {
            // Finding asset linking — use update finding API
            try {
                const portMap: Record<string, string[]> = {};
                selectedPortIds.forEach((ports, assetId) => {
                    if (ports.size > 0) portMap[assetId] = [...ports];
                });
                await updateFindingForAssetLink.mutateAsync({
                    id: assetLinkTarget.findingId,
                    asset_ids: [...selectedAssetIds],
                    asset_port_ids: Object.keys(portMap).length > 0 ? portMap : undefined,
                } as any);
                toast.success('Finding assets updated');
            } catch (error: any) {
                toast.error('Failed to update finding assets');
            }
        } else if (assetLinkTarget.testcaseId) {
            // Test case asset linking — use link/unlink APIs
            const tc = testcases.find((tc: any) => tc.id === assetLinkTarget.testcaseId);
            const currentlyLinked = new Set((tc?.assets || []).map((a: any) => a.id) as string[]);
            const toLink = [...selectedAssetIds].filter(id => !currentlyLinked.has(id));
            const toUnlink = [...currentlyLinked].filter(id => !selectedAssetIds.has(id));

            let linked = 0, unlinked = 0, errors = 0;
            for (const assetId of toLink) {
                try {
                    await linkAsset.mutateAsync({ testcaseId: assetLinkTarget.testcaseId, assetId, portIds: selectedPortIds.has(assetId) ? [...selectedPortIds.get(assetId)!] : undefined });
                    linked++;
                } catch { errors++; }
            }
            for (const assetId of toUnlink) {
                try {
                    await unlinkAsset.mutateAsync({ testcaseId: assetLinkTarget.testcaseId, assetId });
                    unlinked++;
                } catch { errors++; }
            }
            // Update port selections for assets that are still linked
            const stillLinked = [...selectedAssetIds].filter(id => currentlyLinked.has(id) && selectedPortIds.has(id) && selectedPortIds.get(id)!.size > 0);
            for (const assetId of stillLinked) {
                try {
                    await linkAsset.mutateAsync({ testcaseId: assetLinkTarget.testcaseId, assetId, portIds: [...selectedPortIds.get(assetId)!] });
                } catch { /* silently ignore port update errors */ }
            }

            const parts: string[] = [];
            if (linked > 0) parts.push(`${linked} linked`);
            if (unlinked > 0) parts.push(`${unlinked} unlinked`);
            if (errors > 0) parts.push(`${errors} failed`);
            if (parts.length > 0) {
                toast.success(`Assets: ${parts.join(', ')}`);
            } else {
                toast.info('No changes to apply');
            }
        }
        setIsApplyingAssetLinks(false);
        setIsAssetLinkDialogOpen(false);
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
    const canManageMembers = usePermission(id, 'engagement_manage_members');
    const canCreateFinding = usePermission(id, 'finding_create');
    const canCreateAsset = usePermission(id, 'asset_create');
    const canCreateTestCase = usePermission(id, 'testcase_create');
    const canGenerateReport = usePermission(id, 'report_generate');

    const { data: timelineData } = useFindingsTimeline({ engagementId: id, days: 30 });

    const { data: activities = [] } = useQuery({
        queryKey: ['engagement-recent-activity', id],
        queryFn: async () => {
            const response = await activityApi.get<{ items: ActivityLog[]; total: number }>(`/discussions/activity?engagement_id=${id}&limit=5`);
            return response.data?.items ?? response.data ?? [];
        }
    });

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

    const [findingsSearch, setFindingsSearch] = useState('');
    const [testCasesSearch, setTestCasesSearch] = useState('');

    const sortedFindings = [...findings]
        .filter(f => {
            if (!findingsSearch) return true;
            const term = findingsSearch.toLowerCase();
            return f.title.toLowerCase().includes(term) ||
                f.description.toLowerCase().includes(term) ||
                f.status.toLowerCase().includes(term) ||
                f.severity.toLowerCase().includes(term);
        })
        .sort(relevanceComparator(
            findingsSearch,
            [item => item.title, item => item.description],
            (a, b) => {
                let comparison = 0;
                if (sortFieldFindings === 'severity') {
                    comparison = severityOrder[a.severity] - severityOrder[b.severity];
                } else if (sortFieldFindings === 'created_at') {
                    comparison = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
                } else if (sortFieldFindings === 'unresolved_thread_count') {
                    comparison = (a.unresolved_thread_count || 0) - (b.unresolved_thread_count || 0);
                } else if (sortFieldFindings === 'created_by_username') {
                    comparison = (a.created_by_username || '').localeCompare(b.created_by_username || '');
                } else {
                    comparison = String((a as any)[sortFieldFindings]).localeCompare(String((b as any)[sortFieldFindings]));
                }
                return sortOrderFindings === 'asc' ? comparison : -comparison;
            }
        ));

    // Build test case tree
    const testCaseTree = useMemo(() => buildTestCaseTree(testcases), [testcases]);
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

    // Filter tree for search
    const filteredTestCaseTree = useMemo(() => {
        if (!testCasesSearch) return testCaseTree;
        const term = testCasesSearch.toLowerCase();
        function matchesSearch(node: TestCaseTreeNode): boolean {
            return node.title.toLowerCase().includes(term) ||
                node.category.toLowerCase().includes(term) ||
                node.description.toLowerCase().includes(term);
        }
        function filterNodes(nodes: TestCaseTreeNode[]): TestCaseTreeNode[] {
            const result: TestCaseTreeNode[] = [];
            for (const node of nodes) {
                const filteredChildren = filterNodes(node.children);
                if (matchesSearch(node) || filteredChildren.length > 0) {
                    result.push({ ...node, children: filteredChildren });
                }
            }
            return result;
        }
        return filterNodes(testCaseTree);
    }, [testCaseTree, testCasesSearch]);

    // Sort + flatten for display
    const displayTestCases = useMemo(() => {
        // Sort tree nodes at each level
        function sortNodes(nodes: TestCaseTreeNode[]): TestCaseTreeNode[] {
            const sorted = [...nodes].sort((a, b) => {
                let comparison = 0;
                switch (sortFieldTestCases) {
                    case 'title':
                        comparison = a.title.localeCompare(b.title);
                        break;
                    case 'category':
                        comparison = a.category.localeCompare(b.category);
                        break;
                    case 'is_executed':
                        comparison = (a.is_executed ? 1 : 0) - (b.is_executed ? 1 : 0);
                        break;
                    case 'result':
                        const resultA = a.is_executed ? (a.is_successful ? 2 : 1) : 0;
                        const resultB = b.is_executed ? (b.is_successful ? 2 : 1) : 0;
                        comparison = resultA - resultB;
                        break;
                    case 'created_at':
                        comparison = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
                        break;
                    case 'unresolved_thread_count':
                        comparison = (a.unresolved_thread_count || 0) - (b.unresolved_thread_count || 0);
                        break;
                    case 'created_by_username':
                        comparison = (a.created_by_username || '').localeCompare(b.created_by_username || '');
                        break;
                    default:
                        comparison = a.title.localeCompare(b.title);
                }
                return sortOrderTestCases === 'desc' ? -comparison : comparison;
            });
            return sorted.map(node => ({
                ...node,
                children: sortNodes(node.children),
            }));
        }
        const sortedTree = sortNodes(filteredTestCaseTree);
        return flattenTree(sortedTree, testCasesSearch ? new Set(testcases.map(tc => tc.id)) : tcExpandedIds);
    }, [filteredTestCaseTree, tcExpandedIds, testCasesSearch, testcases, sortFieldTestCases, sortOrderTestCases]);

    const toggleTcExpand = (id: string) => {
        setTcExpandedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const expandAllTc = () => {
        const allParentIds = new Set(
            testcases.filter(tc => testcases.some(child => child.parent_id === tc.id)).map(tc => tc.id)
        );
        setTcExpandedIds(allParentIds);
    };

    const collapseAllTc = () => {
        setTcExpandedIds(new Set());
    };

    // Smart dual view: tree when default state, table when searching/sorting
    const isTreeView = !testCasesSearch && sortFieldTestCases === 'title' && sortOrderTestCases === 'asc';

    // DnD for tree view
    const tcDndSensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
    );
    const [activeDragId, setActiveDragId] = useState<string | null>(null);

    const handleTcDragStart = useCallback((event: DragStartEvent) => {
        setActiveDragId(event.active.id as string);
    }, []);

    const handleTcDragEnd = useCallback(async (event: DragEndEvent) => {
        setActiveDragId(null);
        const { active, over } = event;
        if (!over || active.id === over.id) return;

        const draggedId = active.id as string;
        const targetId = over.id as string;

        // Don't allow dropping onto self or own children
        const draggedTc = testcases.find(tc => tc.id === draggedId);
        if (!draggedTc) return;

        // Prevent circular: check if target is a descendant of dragged
        function isDescendant(parentId: string, targetId: string): boolean {
            const children = testcases.filter(tc => tc.parent_id === parentId);
            for (const child of children) {
                if (child.id === targetId) return true;
                if (isDescendant(child.id, targetId)) return true;
            }
            return false;
        }

        if (isDescendant(draggedId, targetId)) {
            toast.error('Cannot move a test case into its own child');
            return;
        }

        try {
            await updateTestCase.mutateAsync({ id: draggedId, parent_id: targetId });
            toast.success('Test case moved successfully');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to move test case'));
        }
    }, [testcases, updateTestCase]);

    const userAssignment = engagement?.assignment_details?.find(a => a.user_id === currentUser?.id);
    const isLead = currentUser?.role === UserRole.ADMIN ||
        currentUser?.role === UserRole.TEAM_LEAD ||
        userAssignment?.role?.name === 'Engagement Lead';

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

    const handleEditAsset = (asset: any) => {
        router.push(`/assets/${asset.id}/edit`);
    };

    const handleToggleAssetStatus = async (asset: any, field: 'is_pwned' | 'is_scanned' | 'in_scope') => {
        try {
            await updateAsset.mutateAsync({
                id: asset.id,
                [field]: !asset[field]
            });
        } catch (error) {
            console.error(`Failed to update asset ${field}:`, error);
        }
    };

    const [showAssetImport, setShowAssetImport] = useState(false);
    const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

    const handleAddAsset = () => {
        router.push(`/assets/new?engagementId=${id}`);
    };

    const handleAddTestCase = () => {
        router.push(`/testcases/new?engagementId=${id}`);
    };

    const SortIcon = ({ field, currentField, order }: { field: string, currentField: string, order: 'asc' | 'desc' }) => {
        if (currentField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
        return order === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
    };

    const handleAddFinding = () => {
        router.push(`/findings/new?engagementId=${id}`);
    };

    // Calculate duration and stats
    const getDuration = () => {
        if (!engagement?.start_date || !engagement?.end_date) return 'N/A';
        const start = new Date(engagement.start_date);
        const end = new Date(engagement.end_date);
        const days = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
        return `${days} days`;
    };

    const findingStats = {
        critical: findings.filter(f => f.severity === 'CRITICAL').length,
        high: findings.filter(f => f.severity === 'HIGH').length,
        medium: findings.filter(f => f.severity === 'MEDIUM').length,
        low: findings.filter(f => f.severity === 'LOW').length,
        total: findings.length,
    };

    const testCaseStats = {
        total: testcases.length,
        executed: testcases.filter(tc => tc.is_executed).length,
        passed: testcases.filter(tc => tc.is_executed && tc.is_successful).length,
        failed: testcases.filter(tc => tc.is_executed && !tc.is_successful).length,
    };

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
                            Logs
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
                            {assets.length > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-blue-500/20 text-blue-400 border-none px-1.5 h-4 text-[10px]">
                                    {assets.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="testcases"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-400 data-[state=active]:border-emerald-500/30 hover:border-emerald-500/20 hover:text-emerald-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <CheckSquare className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Test Cases</span>
                            {testCaseStats.total > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-emerald-500/20 text-emerald-400 border-none px-1.5 h-4 text-[10px]">
                                    {testCaseStats.total}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="findings"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-red-500/10 data-[state=active]:text-red-400 data-[state=active]:border-red-500/30 hover:border-red-500/20 hover:text-red-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Bug className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Findings</span>
                            {findingStats.total > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-red-500/20 text-red-400 border-none px-1.5 h-4 text-[10px]">
                                    {findingStats.total}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="attack"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-violet-500/10 data-[state=active]:text-violet-400 data-[state=active]:border-violet-500/30 hover:border-violet-500/20 hover:text-violet-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Shield className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">ATT&amp;CK</span>
                            {coverage && coverage.mapped_techniques.length > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-violet-500/20 text-violet-400 border-none px-1.5 h-4 text-[10px]">
                                    {coverage.mapped_techniques.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="notes"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-teal-500/10 data-[state=active]:text-teal-400 data-[state=active]:border-teal-500/30 hover:border-teal-500/20 hover:text-teal-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <StickyNote className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Notes</span>
                            {notes.length > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-teal-500/20 text-teal-400 border-none px-1.5 h-4 text-[10px]">
                                    {notes.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="vault"
                            className="flex-1 min-w-[130px] rounded-lg py-2.5 data-[state=active]:bg-amber-500/10 data-[state=active]:text-amber-400 data-[state=active]:border-amber-500/30 hover:border-amber-500/20 hover:text-amber-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Lock className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Vault</span>
                            {vaultItems.length > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-amber-500/20 text-amber-400 border-none px-1.5 h-4 text-[10px]">
                                    {vaultItems.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="attachments"
                            className="flex-1 min-w-[150px] rounded-lg py-2.5 data-[state=active]:bg-pink-500/10 data-[state=active]:text-pink-400 data-[state=active]:border-pink-500/30 hover:border-pink-500/20 hover:text-pink-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Paperclip className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Attachments</span>
                            {evidence.length > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-pink-500/20 text-pink-400 border-none px-1.5 h-4 text-[10px]">
                                    {evidence.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger
                            value="cleanup"
                            className="flex-1 min-w-[150px] rounded-lg py-2.5 data-[state=active]:bg-lime-500/10 data-[state=active]:text-lime-400 data-[state=active]:border-lime-500/30 hover:border-lime-500/20 hover:text-lime-400/80 border border-transparent transition-all duration-300 group"
                        >
                            <Sparkles className="h-4 w-4 mr-2 shrink-0 group-data-[state=active]:scale-110 transition-transform" />
                            <span className="font-semibold">Cleanup</span>
                            {cleanupArtifacts.filter((a: any) => a.status === 'PENDING').length > 0 && (
                                <Badge variant="secondary" className="ml-2 bg-lime-500/20 text-lime-400 border-none px-1.5 h-4 text-[10px]">
                                    {cleanupArtifacts.filter((a: any) => a.status === 'PENDING').length}
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
                        <LogsTab engagementId={id} />
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
                            onLinkAsset={handleOpenAssetLink}
                            onLinkIntel={handleOpenIntelLink}
                            onLinkInfra={handleOpenInfraLink}
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
                            onAddFinding={handleOpenFindingLink}
                            onLinkAsset={handleOpenAssetLink}
                            onLinkIntel={handleOpenIntelLink}
                            onLinkInfra={handleOpenInfraLink}
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

            {/* Link Finding to Test Case Dialog */}
            <Dialog open={isFindingLinkDialogOpen} onOpenChange={setIsFindingLinkDialogOpen}>
                <DialogContent className="sm:max-w-lg bg-slate-900 border-slate-800">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Bug className="h-5 w-5 text-primary" />
                            Link Findings
                        </DialogTitle>
                        <DialogDescription>
                            Select findings to link to <span className="text-white font-medium">"{findingLinkTarget?.testcaseTitle}"</span>.
                            Use <kbd className="px-1 py-0.5 bg-slate-700 rounded text-[10px] font-mono">Shift+Click</kbd> to select a range.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        {/* Create New Finding button */}
                        <Button
                            variant="outline"
                            className="w-full border-primary/30 text-primary hover:bg-primary/10 hover:text-primary/80"
                            onClick={() => {
                                setIsFindingLinkDialogOpen(false);
                                router.push(`/findings/new?engagementId=${id}&testCaseId=${findingLinkTarget?.testcaseId}`);
                            }}
                        >
                            <Plus className="h-4 w-4 mr-2" />
                            Create New Finding
                        </Button>

                        <div className="relative">
                            <div className="absolute inset-0 flex items-center">
                                <span className="w-full border-t border-slate-700" />
                            </div>
                            <div className="relative flex justify-center text-xs uppercase">
                                <span className="bg-slate-900 px-2 text-slate-500">or link existing</span>
                            </div>
                        </div>

                        {/* Search */}
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-500" />
                            <Input
                                placeholder="Search findings..."
                                value={findingSearchTerm}
                                onChange={(e) => setFindingSearchTerm(e.target.value)}
                                className="pl-10 bg-slate-800/50 border-slate-700 text-white"
                            />
                        </div>

                        {/* Severity filter pills */}
                        <div className="flex flex-wrap gap-1.5">
                            {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] as const).map(sev => {
                                const isActive = findingSeverityFilter.has(sev);
                                return (
                                    <button
                                        key={sev}
                                        onClick={() => setFindingSeverityFilter(prev => {
                                            const next = new Set(prev);
                                            if (next.has(sev)) next.delete(sev); else next.add(sev);
                                            return next;
                                        })}
                                        className={cn(
                                            'text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors',
                                            isActive
                                                ? severityColors[sev]
                                                : 'border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-400'
                                        )}
                                    >
                                        {sev}
                                    </button>
                                );
                            })}
                        </div>

                        {/* Findings list */}
                        <div className="max-h-64 overflow-y-auto space-y-1.5 pr-1">
                            {findings.length === 0 ? (
                                <div className="text-center py-6 text-slate-500 text-sm">
                                    No findings in this engagement yet.
                                </div>
                            ) : (() => {
                                const filtered = findings.filter((f: any) => {
                                    const matchesSearch = f.title.toLowerCase().includes(findingSearchTerm.toLowerCase()) ||
                                        (f.category?.toLowerCase().includes(findingSearchTerm.toLowerCase()) ?? false);
                                    const matchesSeverity = findingSeverityFilter.size === 0 || findingSeverityFilter.has(f.severity);
                                    return matchesSearch && matchesSeverity;
                                });

                                if (filtered.length === 0) {
                                    return (
                                        <div className="text-center py-6 text-slate-500 text-sm">
                                            No findings match your search.
                                        </div>
                                    );
                                }

                                return filtered.map((finding: any, idx: number) => {
                                    const isSelected = selectedFindingIds.has(finding.id);
                                    return (
                                        <button
                                            key={finding.id}
                                            className={cn(
                                                "w-full flex items-center justify-between px-3 py-2.5 rounded-lg border text-left transition-colors cursor-pointer select-none",
                                                isSelected
                                                    ? "bg-primary/10 border-primary/30"
                                                    : "bg-slate-800/50 border-slate-700/50 hover:bg-slate-800 hover:border-slate-600"
                                            )}
                                            onClick={(e) => handleToggleFindingSelect(finding.id, idx, e.shiftKey, filtered)}
                                        >
                                            <div className="flex items-center gap-2.5 flex-1 min-w-0">
                                                <div className={cn(
                                                    "h-4 w-4 rounded border shrink-0 flex items-center justify-center transition-colors",
                                                    isSelected ? "bg-primary border-primary" : "border-slate-600 bg-slate-800"
                                                )}>
                                                    {isSelected && <CheckCircle className="h-3 w-3 text-white" />}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-sm font-medium text-white truncate">{finding.title}</span>
                                                    </div>
                                                    {finding.category && (
                                                        <span className="text-xs text-slate-500 truncate block">{finding.category}</span>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2 ml-3 shrink-0">
                                                <Badge className={cn("text-[10px] py-0 px-1.5 border", severityColors[finding.severity] || 'bg-slate-500/20 text-slate-400')}>
                                                    {finding.severity}
                                                </Badge>
                                            </div>
                                        </button>
                                    );
                                });
                            })()}
                        </div>
                    </div>
                    <DialogFooter className="flex items-center justify-between sm:justify-between">
                        <span className="text-xs text-slate-500">
                            {selectedFindingIds.size} selected
                        </span>
                        <div className="flex gap-2">
                            <Button variant="outline" className="border-slate-700 text-slate-400 hover:text-white" onClick={() => setIsFindingLinkDialogOpen(false)}>
                                Cancel
                            </Button>
                            <Button
                                className="bg-primary hover:bg-primary/90 text-white"
                                onClick={handleApplyFindingLinks}
                                disabled={isApplyingFindingLinks}
                            >
                                {isApplyingFindingLinks ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Applying...</> : 'Apply'}
                            </Button>
                        </div>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Link Asset to Test Case Dialog */}
            <Dialog open={isAssetLinkDialogOpen} onOpenChange={setIsAssetLinkDialogOpen}>
                <DialogContent className="sm:max-w-2xl bg-slate-900 border-slate-800">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Server className="h-5 w-5 text-cyan-400" />
                            Link Assets
                        </DialogTitle>
                        <DialogDescription>
                            Select assets to link to <span className="text-white font-medium">"{assetLinkTarget?.testcaseTitle || assetLinkTarget?.findingTitle}"</span>.
                            Use <kbd className="px-1 py-0.5 bg-slate-700 rounded text-[10px] font-mono">Shift+Click</kbd> to select a range.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        {/* Search */}
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-500" />
                            <Input
                                placeholder="Search assets..."
                                value={assetSearchTerm}
                                onChange={(e) => setAssetSearchTerm(e.target.value)}
                                className="pl-10 bg-slate-800/50 border-slate-700 text-white"
                            />
                        </div>

                        {/* Asset type filter pills */}
                        {(() => {
                            const uniqueTypes = [...new Set(allAssets.map((a: any) => a.asset_type))] as string[];
                            if (uniqueTypes.length <= 1) return null;
                            return (
                                <div className="flex flex-wrap gap-1.5">
                                    {uniqueTypes.map(type => {
                                        const isActive = assetTypeFilter.has(type);
                                        const style = assetTypeStyles[type] || assetTypeStyles.OTHER;
                                        const TypeIcon = style.icon;
                                        return (
                                            <button
                                                key={type}
                                                onClick={() => setAssetTypeFilter(prev => {
                                                    const next = new Set(prev);
                                                    if (next.has(type)) next.delete(type); else next.add(type);
                                                    return next;
                                                })}
                                                className={cn(
                                                    'text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors flex items-center gap-1',
                                                    isActive
                                                        ? style.color
                                                        : 'border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-400'
                                                )}
                                            >
                                                <TypeIcon className="h-2.5 w-2.5" />
                                                {assetTypeLabels[type] || type}
                                            </button>
                                        );
                                    })}
                                </div>
                            );
                        })()}

                        {/* Assets list */}
                        <div className="max-h-[28rem] overflow-y-auto space-y-1.5 pr-1">
                            {allAssets.length === 0 ? (
                                <div className="text-center py-6 text-slate-500 text-sm">
                                    No assets in this engagement yet.
                                </div>
                            ) : (() => {
                                const filtered = allAssets.filter((a: any) => {
                                    const matchesSearch = a.name.toLowerCase().includes(assetSearchTerm.toLowerCase()) ||
                                        a.identifier.toLowerCase().includes(assetSearchTerm.toLowerCase());
                                    const matchesType = assetTypeFilter.size === 0 || assetTypeFilter.has(a.asset_type);
                                    return matchesSearch && matchesType;
                                });

                                if (filtered.length === 0) {
                                    return (
                                        <div className="text-center py-6 text-slate-500 text-sm">
                                            No assets match your search.
                                        </div>
                                    );
                                }

                                return filtered.map((asset: any, idx: number) => {
                                    const isSelected = selectedAssetIds.has(asset.id);
                                    const style = assetTypeStyles[asset.asset_type] || assetTypeStyles.OTHER;
                                    return (
                                        <div key={asset.id}>
                                            <button
                                                className={cn(
                                                    "w-full flex items-center justify-between px-3 py-2.5 rounded-lg border text-left transition-colors cursor-pointer select-none",
                                                    isSelected
                                                        ? "bg-cyan-500/10 border-cyan-500/30"
                                                        : "bg-slate-800/50 border-slate-700/50 hover:bg-slate-800 hover:border-slate-600"
                                                )}
                                                onClick={(e) => handleToggleAssetSelect(asset.id, idx, e.shiftKey, filtered)}
                                            >
                                                <div className="flex items-center gap-2.5 flex-1 min-w-0">
                                                    <div className={cn(
                                                        "h-4 w-4 rounded border shrink-0 flex items-center justify-center transition-colors",
                                                        isSelected ? "bg-cyan-500 border-cyan-500" : "border-slate-600 bg-slate-800"
                                                    )}>
                                                        {isSelected && <CheckCircle className="h-3 w-3 text-white" />}
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-sm font-medium text-white truncate">{asset.name}</span>
                                                        </div>
                                                        <span className="text-xs text-slate-500 truncate block font-mono">{asset.identifier}</span>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-2 ml-3 shrink-0">
                                                    <Badge className={cn("text-[10px] py-0 px-1.5 border", style.color)}>
                                                        {assetTypeLabels[asset.asset_type] || asset.asset_type}
                                                    </Badge>
                                                    {asset.ports && asset.ports.length > 0 && (
                                                        <span className="text-[9px] font-mono text-cyan-400/60">
                                                            {asset.ports.length}p
                                                        </span>
                                                    )}
                                                </div>
                                            </button>
                                            {/* Port selection for selected assets with ports */}
                                            {isSelected && asset.ports && asset.ports.length > 0 && (
                                                <div className="ml-8 mt-1 mb-2 space-y-1">
                                                    <div className="text-[9px] text-slate-500 uppercase font-bold tracking-wider mb-1">Select ports:</div>
                                                    {asset.ports
                                                        .sort((a: any, b: any) => a.port_number - b.port_number)
                                                        .map((port: any) => {
                                                            const isPortSelected = selectedPortIds.get(asset.id)?.has(port.id) || false;
                                                            return (
                                                                <button
                                                                    key={port.id}
                                                                    className={cn(
                                                                        "w-full flex items-center gap-2 px-2 py-1 rounded text-left transition-colors text-[11px]",
                                                                        isPortSelected
                                                                            ? "bg-cyan-500/15 text-cyan-300"
                                                                            : "bg-slate-800/30 text-slate-400 hover:bg-slate-800/60"
                                                                    )}
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        setSelectedPortIds(prev => {
                                                                            const next = new Map(prev);
                                                                            const portSet = new Set(next.get(asset.id) || []);
                                                                            if (portSet.has(port.id)) {
                                                                                portSet.delete(port.id);
                                                                            } else {
                                                                                portSet.add(port.id);
                                                                            }
                                                                            next.set(asset.id, portSet);
                                                                            return next;
                                                                        });
                                                                    }}
                                                                >
                                                                    <div className={cn(
                                                                        "h-3 w-3 rounded-sm border shrink-0 flex items-center justify-center",
                                                                        isPortSelected ? "bg-cyan-500 border-cyan-500" : "border-slate-600 bg-slate-800"
                                                                    )}>
                                                                        {isPortSelected && <CheckCircle className="h-2 w-2 text-white" />}
                                                                    </div>
                                                                    <span className="font-mono font-bold text-cyan-400">{port.port_number}</span>
                                                                    <span className="text-slate-500 uppercase text-[9px]">{port.protocol}</span>
                                                                    {port.service_name && <span className="text-slate-400">{port.service_name}</span>}
                                                                    <Badge
                                                                        variant="outline"
                                                                        className={cn(
                                                                            "text-[7px] px-1 py-0 h-3 border-none uppercase font-bold ml-auto",
                                                                            port.state === 'OPEN' ? 'bg-green-500/10 text-green-400' :
                                                                                port.state === 'FILTERED' ? 'bg-yellow-500/10 text-yellow-400' :
                                                                                    'bg-red-500/10 text-red-400'
                                                                        )}
                                                                    >
                                                                        {port.state}
                                                                    </Badge>
                                                                </button>
                                                            );
                                                        })}
                                                </div>
                                            )}
                                        </div>
                                    );
                                });
                            })()}
                        </div>
                    </div>
                    <DialogFooter className="flex items-center justify-between sm:justify-between">
                        <span className="text-xs text-slate-500">
                            {selectedAssetIds.size} asset{selectedAssetIds.size !== 1 ? 's' : ''} selected
                            {(() => {
                                let portCount = 0;
                                selectedPortIds.forEach(s => portCount += s.size);
                                return portCount > 0 ? ` · ${portCount} port${portCount !== 1 ? 's' : ''}` : '';
                            })()}
                        </span>
                        <div className="flex gap-2">
                            <Button variant="outline" className="border-slate-700 text-slate-400 hover:text-white" onClick={() => setIsAssetLinkDialogOpen(false)}>
                                Cancel
                            </Button>
                            <Button
                                className="bg-cyan-600 hover:bg-cyan-500 text-white"
                                onClick={handleApplyAssetLinks}
                                disabled={isApplyingAssetLinks}
                            >
                                {isApplyingAssetLinks ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Applying...</> : 'Apply'}
                            </Button>
                        </div>
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

            {/* Intel Link Dialog */}
            {intelLinkTarget && (
                <IntelLinkDialog
                    open={isIntelLinkDialogOpen}
                    onOpenChange={setIsIntelLinkDialogOpen}
                    entityType={intelLinkTarget.entityType}
                    entityId={intelLinkTarget.entityId}
                />
            )}

            {/* Infra Link Dialog */}
            {infraLinkTarget && (
                <InfraLinkDialog
                    open={isInfraLinkDialogOpen}
                    onOpenChange={setIsInfraLinkDialogOpen}
                    entityType={infraLinkTarget.entityType}
                    entityId={infraLinkTarget.entityId}
                />
            )}
        </DashboardLayout>
    );
}


// ═══════════════════════════════════════════════════════════════════
//  ENGAGEMENT SKILLS OVERVIEW CARD
// ═══════════════════════════════════════════════════════════════════

function EngagementSkillsOverviewCard({ engagementId }: { engagementId: string }) {
    const { data: engagementSkills = [] } = useEngagementSkills(engagementId);

    if (engagementSkills.length === 0) return null;

    const radarData = buildRadarData(engagementSkills, 'min_level');

    return (
        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
            <CardHeader className="pb-3 border-b border-slate-800/50">
                <CardTitle className="text-sm font-medium text-slate-400 flex items-center gap-2">
                    <Radar className="h-4 w-4" />
                    Required Skills
                </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
                <SkillsRadarChart
                    data={radarData}
                    series={[{ key: 'min_level', label: 'Required', color: '#ec4899' }]}
                    height={240}
                />
                <div className="space-y-1.5 mt-3">
                    {engagementSkills.map((es) => (
                        <div key={es.skill_id} className="flex items-center justify-between text-xs px-2">
                            <span className="text-slate-400">{es.skill_name}</span>
                            <Badge
                                variant="outline"
                                className={cn(
                                    'text-[10px] py-0',
                                    es.min_level === 1 ? 'border-blue-500/30 text-blue-400 bg-blue-500/10' :
                                    es.min_level === 2 ? 'border-amber-500/30 text-amber-400 bg-amber-500/10' :
                                    'border-emerald-500/30 text-emerald-400 bg-emerald-500/10'
                                )}
                            >
                                {SKILL_LEVELS.find(l => l.value === es.min_level)?.label}+
                            </Badge>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}

/**
 * planning/page.tsx — Engagement Planning & Scheduling Page
 *
 * Gantt-chart-based planning view for scheduling and tracking engagements.
 * Two tabs:
 *
 * **Timeline tab**
 *  - 3-month sliding Gantt chart with month / week header markers, a
 *    red "today" line, and engagement type filter chips.
 *  - Each engagement row shows name, client, type badge, and a
 *    multi-segment phase bar (Scoping → Planning → In Progress →
 *    Reporting). Proposed engagements render a single dashed bar.
 *  - Phase health indicators: completed (faded), on-time (green badge),
 *    late (red ring + ⚠ icon) based on current status vs. planned dates.
 *  - Inspector sidebar: status badge, date range, team badges, and an
 *    editable phase breakdown with inline date inputs and Save/Cancel.
 *  - Metrics strip: Proposed, In Planning, Active, Behind Schedule.
 *  - Promote (PROPOSED → PLANNING), Edit, and Delete actions with
 *    confirmation dialogs.
 *
 * **Scheduling tab**
 *  - Delegated to `<SchedulingAssistant>` component.
 *
 * Helpers: `getPhaseHealth`, `getOverallHealth`, `getPosition` (bar
 * positioning), phase and status colour maps.
 */
'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    ChevronLeft, ChevronRight, Plus, Loader2, Target,
    Clock, GanttChart, Users, CalendarDays,
    Sparkles, MoreHorizontal,
    Edit, Trash2, Play, AlertTriangle, CheckCircle2,
    Mail, Check,
} from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    useAllEngagementsIncludingProposed,
    useProposedEngagements,
    useCreateEngagement,
    useUpdateEngagement,
    useDeleteEngagement,
    useUpdateEngagementPhases,
} from '@/lib/hooks/use-engagements';
import type { EngagementPhase } from '@/lib/hooks/use-engagements';
import { useEngagementTypes } from '@/lib/hooks/use-engagement-types';
import { useClients } from '@/lib/hooks/use-clients';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
    format, startOfMonth, endOfMonth, addMonths, subMonths,
    parseISO, differenceInDays, eachWeekOfInterval,
    max as dateMax, min as dateMin,
    isAfter,
} from 'date-fns';

import { SchedulingAssistant } from '@/components/calendar/scheduling-assistant';
import { useAuthStore } from '@/stores/auth-store';
import { useFocusFit } from '@/lib/hooks/use-skills';
import { UserRole } from '@/lib/types';

// ── Phase colors (distinct from status colors) ─────────────────
const PHASE_COLORS: Record<string, { bg: string; label: string; border: string }> = {
    SCOPING: { bg: 'bg-cyan-500', label: 'Scoping', border: 'border-cyan-500/40' },
    PLANNING: { bg: 'bg-amber-500', label: 'Planning', border: 'border-amber-500/40' },
    IN_PROGRESS: { bg: 'bg-purple-500', label: 'In Progress', border: 'border-purple-500/40' },
    REPORTING: { bg: 'bg-blue-500', label: 'Reporting', border: 'border-blue-500/40' },
};

// Status-to-phase index mapping for on-time/late calculation
const STATUS_PHASE_INDEX: Record<string, number> = {
    PROPOSED: -1,
    SCOPING: 0,
    PLANNING: 1,
    IN_PROGRESS: 2,
    REPORTING: 3,
    COMPLETED: 4,
    ON_HOLD: -1,
};

const STATUS_BADGE_COLORS: Record<string, string> = {
    PROPOSED: 'bg-teal-500/10 text-teal-400 border-teal-500/20',
    PLANNING: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    IN_PROGRESS: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    REPORTING: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    COMPLETED: 'bg-green-500/10 text-green-400 border-green-500/20',
    ON_HOLD: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

type TabType = 'timeline' | 'scheduling';

// ── Helpers ────────────────────────────────────────────────────
function getPhaseHealth(phase: EngagementPhase, engagementStatus: string): 'on-time' | 'late' | 'completed' | 'future' {
    const now = new Date();
    const phaseIdx = STATUS_PHASE_INDEX[phase.phase_name] ?? -1;
    const statusIdx = STATUS_PHASE_INDEX[engagementStatus] ?? -1;

    // If the engagement has progressed past this phase, it's completed
    if (statusIdx > phaseIdx) return 'completed';

    // If no planned end, can't determine
    if (!phase.planned_end) return 'future';

    const plannedEnd = parseISO(phase.planned_end);

    // If we're currently in or before this phase and past its end date → late
    if (statusIdx <= phaseIdx && isAfter(now, plannedEnd)) return 'late';

    // If the status hasn't reached this phase yet → future
    if (statusIdx < phaseIdx) return 'future';

    return 'on-time';
}

function getOverallHealth(phases: EngagementPhase[], status: string): { late: number; onTime: number; completed: number } {
    let late = 0, onTime = 0, completed = 0;
    for (const p of phases) {
        const h = getPhaseHealth(p, status);
        if (h === 'late') late++;
        else if (h === 'on-time') onTime++;
        else if (h === 'completed') completed++;
    }
    return { late, onTime, completed };
}

export default function PlanningPage() {
    const router = useRouter();
    const { user: currentUser } = useAuthStore();
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [activeTab, setActiveTab] = useState<TabType>('timeline');
    const [selectedEngagement, setSelectedEngagement] = useState<any>(null);
    const [createDialogOpen, setCreateDialogOpen] = useState(false);
    const [filterUserIds, setFilterUserIds] = useState<string[]>([]);
    const [filterTypes, setFilterTypes] = useState<string[]>([]);
    const [growthFitOnly, setGrowthFitOnly] = useState(false);
    const [editingPhases, setEditingPhases] = useState<Record<string, { start: string; end: string }>>({});
    const [inspectorEmailsCopied, setInspectorEmailsCopied] = useState(false);

    const handleCopyInspectorEmails = async () => {
        const users = selectedEngagement?.assigned_users ?? [];
        const emails = users.map((u: any) => u.email).filter(Boolean);
        if (emails.length === 0) return;
        await navigator.clipboard.writeText(emails.join(', '));
        toast.success(`${emails.length} email${emails.length === 1 ? '' : 's'} copied to clipboard`);
        setInspectorEmailsCopied(true);
        setTimeout(() => setInspectorEmailsCopied(false), 1500);
    };

    // Data hooks
    const { data: allEngagements = [], isLoading } = useAllEngagementsIncludingProposed();
    const { data: proposedEngagements = [] } = useProposedEngagements();
    const { data: engagementTypes = [] } = useEngagementTypes();
    const { data: clients = [] } = useClients();
    const { data: focusFit = [] } = useFocusFit();
    const isManageRole = currentUser?.role === UserRole.ADMIN || currentUser?.role === UserRole.TEAM_LEAD;

    // Map: engagement_id -> matches (scoped to current user for operators, all users for managers)
    const focusFitByEngagement = useMemo(() => {
        const map = new Map<string, typeof focusFit[number]['matches']>();
        for (const item of focusFit) {
            map.set(item.engagement_id, item.matches);
        }
        return map;
    }, [focusFit]);

    // For operators: which engagements are growth fits for ME?
    const myFocusEngagementIds = useMemo(() => {
        if (!currentUser?.id) return new Set<string>();
        const ids = new Set<string>();
        for (const item of focusFit) {
            if (item.matches.some(m => m.user_id === currentUser.id)) {
                ids.add(item.engagement_id);
            }
        }
        return ids;
    }, [focusFit, currentUser?.id]);

    // Count of forward-looking growth fits (PROPOSED + PLANNING + ACTIVE)
    const growthFitCount = useMemo(() => {
        if (isManageRole) {
            return focusFit.filter(item => {
                const eng = allEngagements.find(e => e.id === item.engagement_id);
                return eng && eng.status !== 'COMPLETED' && eng.status !== 'CANCELLED';
            }).length;
        }
        return allEngagements.filter(e =>
            myFocusEngagementIds.has(e.id) && e.status !== 'COMPLETED' && e.status !== 'CANCELLED'
        ).length;
    }, [focusFit, allEngagements, myFocusEngagementIds, isManageRole]);
    const createEngagement = useCreateEngagement();
    const updateEngagement = useUpdateEngagement();
    const deleteEngagement = useDeleteEngagement();
    const updatePhases = useUpdateEngagementPhases();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // Date range for the Gantt view (3-month window centered on current month)
    const viewStart = startOfMonth(subMonths(currentMonth, 1));
    const viewEnd = endOfMonth(addMonths(currentMonth, 1));
    const totalDays = Math.max(differenceInDays(viewEnd, viewStart), 1);

    // Week markers for the timeline header
    const weekMarkers = useMemo(() => {
        return eachWeekOfInterval({ start: viewStart, end: viewEnd }, { weekStartsOn: 1 });
    }, [viewStart, viewEnd]);

    // Month labels for the header
    const monthLabels = useMemo(() => {
        const labels: { label: string; left: number; width: number }[] = [];
        let cursor = viewStart;
        while (cursor < viewEnd) {
            const mStart = dateMax([startOfMonth(cursor), viewStart]);
            const mEnd = dateMin([endOfMonth(cursor), viewEnd]);
            const leftDays = differenceInDays(mStart, viewStart);
            const widthDays = differenceInDays(mEnd, mStart) + 1;
            labels.push({
                label: format(cursor, 'MMMM yyyy'),
                left: (leftDays / totalDays) * 100,
                width: (widthDays / totalDays) * 100,
            });
            cursor = addMonths(startOfMonth(cursor), 1);
        }
        return labels;
    }, [viewStart, viewEnd, totalDays]);

    // Sort engagements: proposed first, then by start date
    const sortedEngagements = useMemo(() => {
        return [...allEngagements]
            .filter(e => {
                if (!e.start_date) return false;
                const start = parseISO(e.start_date);
                const end = e.end_date ? parseISO(e.end_date) : start;
                return start <= viewEnd && end >= viewStart;
            })
            .sort((a, b) => {
                if (a.status === 'PROPOSED' && b.status !== 'PROPOSED') return -1;
                if (a.status !== 'PROPOSED' && b.status === 'PROPOSED') return 1;
                return new Date(a.start_date).getTime() - new Date(b.start_date).getTime();
            });
    }, [allEngagements, viewStart, viewEnd]);

    // Build a lookup map: type name -> EngagementType (for color, etc.)
    const typeMap = useMemo(() => {
        const m: Record<string, { name: string; color: string }> = {};
        for (const t of engagementTypes) {
            m[t.name] = { name: t.name, color: t.color };
        }
        return m;
    }, [engagementTypes]);

    // Unique engagement types present in the current view
    const visibleTypes = useMemo(() => {
        const types = new Set<string>();
        for (const e of sortedEngagements) {
            if (e.engagement_type) types.add(e.engagement_type);
        }
        return Array.from(types).sort();
    }, [sortedEngagements]);

    // Filter by engagement type
    const filteredEngagements = useMemo(() => {
        let rows = sortedEngagements;
        if (filterTypes.length > 0) {
            rows = rows.filter(e => filterTypes.includes(e.engagement_type));
        }
        if (growthFitOnly) {
            if (isManageRole) {
                rows = rows.filter(e => focusFitByEngagement.has(e.id));
            } else {
                rows = rows.filter(e => myFocusEngagementIds.has(e.id));
            }
        }
        return rows;
    }, [sortedEngagements, filterTypes, growthFitOnly, isManageRole, focusFitByEngagement, myFocusEngagementIds]);

    const toggleTypeFilter = (type: string) => {
        setFilterTypes(prev =>
            prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
        );
    };

    // Metrics
    const metrics = useMemo(() => {
        let lateCount = 0;
        for (const e of allEngagements) {
            if (e.phases?.length > 0) {
                const h = getOverallHealth(e.phases, e.status);
                if (h.late > 0) lateCount++;
            }
        }
        return {
            proposed: proposedEngagements.length,
            active: allEngagements.filter(e => e.status === 'IN_PROGRESS').length,
            planning: allEngagements.filter(e => e.status === 'PLANNING').length,
            late: lateCount,
        };
    }, [allEngagements, proposedEngagements]);

    // ── Create form state ──────────────────────────────────────
    const [newEngagement, setNewEngagement] = useState({
        name: '', client_name: '', client_id: '', engagement_type: '',
        start_date: format(new Date(), 'yyyy-MM-dd'),
        end_date: format(addMonths(new Date(), 1), 'yyyy-MM-dd'),
        description: '',
    });

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            const result = await createEngagement.mutateAsync({
                ...newEngagement,
                client_id: newEngagement.client_id || undefined,
                status: 'PROPOSED',
                start_date: newEngagement.start_date ? new Date(newEngagement.start_date).toISOString() : undefined,
                end_date: newEngagement.end_date ? new Date(newEngagement.end_date).toISOString() : undefined,
            });
            toast.success('Proposed engagement created');
            setCreateDialogOpen(false);
            setNewEngagement({
                name: '', client_name: '', client_id: '', engagement_type: '',
                start_date: format(new Date(), 'yyyy-MM-dd'),
                end_date: format(addMonths(new Date(), 1), 'yyyy-MM-dd'),
                description: '',
            });
            setSelectedEngagement(result);
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to create proposed engagement'));
        }
    };

    const handlePromote = async (id: string) => {
        try {
            await updateEngagement.mutateAsync({ id, status: 'PLANNING' });
            toast.success('Engagement promoted to Planning — phases auto-created');
            setSelectedEngagement(null);
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to promote engagement'));
        }
    };

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Proposed Engagement',
            description: 'Are you sure? This cannot be undone.',
        });
        if (!confirmed) return;
        try {
            await deleteEngagement.mutateAsync(id);
            toast.success('Engagement deleted');
            if (selectedEngagement?.id === id) setSelectedEngagement(null);
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to delete engagement'));
        }
    };

    const handleSavePhases = async (engId: string, phases: EngagementPhase[]) => {
        try {
            const updates = phases.map(p => ({
                id: p.id,
                planned_start: editingPhases[p.id]?.start
                    ? new Date(editingPhases[p.id].start).toISOString()
                    : undefined,
                planned_end: editingPhases[p.id]?.end
                    ? new Date(editingPhases[p.id].end).toISOString()
                    : undefined,
            })).filter(p => p.planned_start || p.planned_end);
            if (updates.length === 0) return;
            await updatePhases.mutateAsync({ engagementId: engId, phases: updates });
            toast.success('Phase dates updated');
            setEditingPhases({});
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to update phases'));
        }
    };

    // ── Gantt bar positioning ──────────────────────────────────
    const getPosition = (startDate: string | null, endDate: string | null) => {
        if (!startDate) return { left: 0, width: 0 };
        const eStart = parseISO(startDate);
        const eEnd = endDate ? parseISO(endDate) : eStart;
        const clampedStart = dateMax([eStart, viewStart]);
        const clampedEnd = dateMin([eEnd, viewEnd]);
        const leftDays = differenceInDays(clampedStart, viewStart);
        const widthDays = Math.max(differenceInDays(clampedEnd, clampedStart), 1);
        return {
            left: Math.max(0, Math.min((leftDays / totalDays) * 100, 100)),
            width: Math.max(0.5, Math.min((widthDays / totalDays) * 100, 100 - (leftDays / totalDays) * 100)),
        };
    };

    // "Today" marker position
    const todayPosition = useMemo(() => {
        const today = new Date();
        if (today < viewStart || today > viewEnd) return null;
        return (differenceInDays(today, viewStart) / totalDays) * 100;
    }, [viewStart, viewEnd, totalDays]);

    const nextMonth = () => setCurrentMonth(addMonths(currentMonth, 1));
    const prevMonth = () => setCurrentMonth(subMonths(currentMonth, 1));

    // Start editing phase dates (pre-populate with current values)
    const startEditPhases = (phases: EngagementPhase[]) => {
        const edits: Record<string, { start: string; end: string }> = {};
        for (const p of phases) {
            edits[p.id] = {
                start: p.planned_start ? format(parseISO(p.planned_start), 'yyyy-MM-dd') : '',
                end: p.planned_end ? format(parseISO(p.planned_end), 'yyyy-MM-dd') : '',
            };
        }
        setEditingPhases(edits);
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-lg">
                            <GanttChart className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-white tracking-tight">Planning</h1>
                            <p className="text-slate-400 text-sm">Schedule and plan engagements before committing resources</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="flex bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                            <Button variant="ghost" size="icon" onClick={prevMonth} className="text-slate-400 hover:text-white border-r border-slate-800 rounded-none h-9 w-9">
                                <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <div className="px-4 flex items-center justify-center font-medium text-white min-w-[150px] text-sm">
                                {format(currentMonth, 'MMMM yyyy')}
                            </div>
                            <Button variant="ghost" size="icon" onClick={nextMonth} className="text-slate-400 hover:text-white border-l border-slate-800 rounded-none h-9 w-9">
                                <ChevronRight className="h-4 w-4" />
                            </Button>
                        </div>
                        <Button onClick={() => setCreateDialogOpen(true)} className="bg-primary hover:bg-primary/90 text-white gap-2">
                            <Plus className="h-4 w-4" />
                            Propose Engagement
                        </Button>
                    </div>
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                    {[
                        { label: 'Proposed', value: metrics.proposed, sub: 'pending approval', icon: Sparkles, iconBg: 'bg-teal-500/10', iconColor: 'text-teal-400', clickable: false },
                        { label: 'In Planning', value: metrics.planning, sub: 'being prepared', icon: CalendarDays, iconBg: 'bg-amber-500/10', iconColor: 'text-amber-400', clickable: false },
                        { label: 'Active', value: metrics.active, sub: 'in progress', icon: Target, iconBg: 'bg-purple-500/10', iconColor: 'text-purple-400', clickable: false },
                        { label: 'Behind Schedule', value: metrics.late, sub: 'need attention', icon: AlertTriangle, iconBg: metrics.late > 0 ? 'bg-red-500/10' : 'bg-slate-800', iconColor: metrics.late > 0 ? 'text-red-400' : 'text-slate-500', clickable: false },
                        {
                            label: 'Growth Fit',
                            value: growthFitCount,
                            sub: isManageRole ? 'matches across team' : 'matches your focus',
                            icon: Target,
                            iconBg: growthFitCount > 0 ? 'bg-fuchsia-500/10' : 'bg-slate-800',
                            iconColor: growthFitCount > 0 ? 'text-fuchsia-400' : 'text-slate-500',
                            clickable: growthFitCount > 0,
                            active: growthFitOnly,
                        },
                    ].map(m => {
                        const Wrapper: React.ElementType = m.clickable ? 'button' : 'div';
                        return (
                            <Wrapper
                                key={m.label}
                                onClick={m.clickable ? () => setGrowthFitOnly(v => !v) : undefined}
                                className={cn(
                                    "relative overflow-hidden rounded-xl border bg-slate-900/60 backdrop-blur-md p-4 text-left transition-colors",
                                    m.clickable && "cursor-pointer hover:bg-slate-900/80",
                                    m.active ? "border-fuchsia-500/50 ring-1 ring-fuchsia-500/30" : "border-slate-800",
                                )}
                            >
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{m.label}</p>
                                        <p className={cn("text-2xl font-black mt-1", m.label === 'Behind Schedule' && m.value > 0 ? 'text-red-400' : 'text-white')}>{m.value}</p>
                                        <p className="text-[10px] text-slate-600 mt-0.5">
                                            {m.active ? 'click to clear filter' : m.sub}
                                        </p>
                                    </div>
                                    <div className={cn("h-10 w-10 rounded-lg flex items-center justify-center", m.iconBg)}>
                                        <m.icon className={cn("h-5 w-5", m.iconColor)} />
                                    </div>
                                </div>
                            </Wrapper>
                        );
                    })}
                </div>

                {/* Tabs */}
                <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-1 w-fit">
                    {([
                        { id: 'timeline' as TabType, label: 'Timeline', icon: GanttChart },
                        { id: 'scheduling' as TabType, label: 'Scheduling', icon: Users },
                    ]).map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={cn(
                                'flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                                activeTab === tab.id
                                    ? 'bg-primary/15 text-primary'
                                    : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                            )}
                        >
                            <tab.icon className="h-4 w-4" />
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* ═══════ TIMELINE TAB ═══════ */}
                {activeTab === 'timeline' && (
                    <div className="grid lg:grid-cols-4 gap-6">
                        {/* Gantt Chart */}
                        <div className="lg:col-span-3">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
                                {isLoading && (
                                    <div className="absolute inset-0 bg-slate-950/20 backdrop-blur-xs z-10 flex items-center justify-center">
                                        <Loader2 className="h-10 w-10 animate-spin text-primary" />
                                    </div>
                                )}
                                <CardContent className="p-0">
                                    {/* Month labels header */}
                                    <div className="relative h-8 border-b border-slate-800 bg-slate-800/30">
                                        {monthLabels.map((m, i) => (
                                            <div key={i}
                                                className="absolute top-0 h-full flex items-center px-3 text-xs font-bold text-white/70 uppercase tracking-wider border-r border-slate-700/30"
                                                style={{ left: `${m.left}%`, width: `${m.width}%` }}
                                            >{m.label}</div>
                                        ))}
                                    </div>

                                    {/* Week tick marks */}
                                    <div className="relative h-6 border-b border-slate-800/80 bg-slate-900/30">
                                        {weekMarkers.map((w, i) => {
                                            const pct = (differenceInDays(w, viewStart) / totalDays) * 100;
                                            if (pct < 0 || pct > 100) return null;
                                            return (
                                                <div key={i} className="absolute top-0 h-full border-l border-slate-700/30 flex items-center pl-1.5"
                                                    style={{ left: `${pct}%` }}>
                                                    <span className="text-[9px] text-slate-600 font-medium">{format(w, 'MMM d')}</span>
                                                </div>
                                            );
                                        })}
                                        {todayPosition !== null && (
                                            <div className="absolute top-0 h-full w-0.5 bg-red-500 z-10" style={{ left: `${todayPosition}%` }} />
                                        )}
                                    </div>

                                    {/* Engagement type filter chips */}
                                    {visibleTypes.length > 0 && (
                                        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-800/50 bg-slate-800/10">
                                            <span className="text-[10px] text-slate-600 uppercase tracking-wider font-medium shrink-0">Type</span>
                                            <div className="flex items-center gap-1.5 flex-wrap">
                                                {visibleTypes.map(type => {
                                                    const isActive = filterTypes.includes(type);
                                                    const typeInfo = typeMap[type];
                                                    const color = typeInfo?.color || '#6366f1';
                                                    return (
                                                        <button
                                                            key={type}
                                                            onClick={() => toggleTypeFilter(type)}
                                                            className={cn(
                                                                'px-2.5 py-1 rounded-full text-[10px] font-medium transition-all border',
                                                                isActive
                                                                    ? 'border-transparent text-white shadow-sm'
                                                                    : 'border-slate-700 text-slate-400 hover:text-white hover:border-slate-500'
                                                            )}
                                                            style={isActive ? {
                                                                backgroundColor: color + '30',
                                                                color: color,
                                                                borderColor: color + '50',
                                                            } : {}}
                                                        >
                                                            <span
                                                                className="inline-block w-1.5 h-1.5 rounded-full mr-1.5"
                                                                style={{ backgroundColor: color }}
                                                            />
                                                            {type}
                                                        </button>
                                                    );
                                                })}
                                                {filterTypes.length > 0 && (
                                                    <button
                                                        onClick={() => setFilterTypes([])}
                                                        className="text-[10px] text-slate-500 hover:text-white px-1.5 py-1 transition-colors"
                                                    >
                                                        Clear
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {/* Engagement rows */}
                                    <TooltipProvider delayDuration={200}>
                                        <div className="divide-y divide-slate-800/50">
                                            {filteredEngagements.length === 0 && !isLoading ? (
                                                <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
                                                    <GanttChart className="h-10 w-10 text-slate-700" />
                                                    <p className="text-sm text-slate-500">No engagements in this time range</p>
                                                    <Button variant="outline" size="sm" onClick={() => setCreateDialogOpen(true)}
                                                        className="border-primary/30 text-primary hover:bg-primary/10">
                                                        <Plus className="h-3.5 w-3.5 mr-1.5" /> Propose Engagement
                                                    </Button>
                                                </div>
                                            ) : (
                                                filteredEngagements.map(eng => {
                                                    const isProposed = eng.status === 'PROPOSED';
                                                    const isSelected = selectedEngagement?.id === eng.id;
                                                    const hasPhases = eng.phases && eng.phases.length > 0;
                                                    const health = hasPhases ? getOverallHealth(eng.phases, eng.status) : null;
                                                    const isLate = health && health.late > 0;
                                                    const matches = focusFitByEngagement.get(eng.id) ?? [];
                                                    const myMatch = matches.find(m => m.user_id === currentUser?.id);
                                                    const isGrowthFitForMe = !!myMatch;
                                                    const hasTeamFit = isManageRole && matches.length > 0;

                                                    return (
                                                        <div
                                                            key={eng.id}
                                                            className={cn(
                                                                'flex items-center gap-3 px-3 py-2.5 transition-colors cursor-pointer group',
                                                                isSelected ? 'bg-primary/5 border-l-2 border-l-primary'
                                                                    : isLate ? 'hover:bg-red-500/5 border-l-2 border-l-red-500/50'
                                                                    : 'hover:bg-slate-800/30 border-l-2 border-l-transparent'
                                                            )}
                                                            onClick={() => setSelectedEngagement(eng)}
                                                        >
                                                            {/* Name column */}
                                                            <div className="w-[200px] shrink-0 min-w-0">
                                                                <div className="flex items-center gap-1.5">
                                                                    {isProposed && <Sparkles className="h-3 w-3 text-teal-400 shrink-0" />}
                                                                    {isLate && <AlertTriangle className="h-3 w-3 text-red-400 shrink-0" />}
                                                                    {(isGrowthFitForMe || hasTeamFit) && (
                                                                        <Tooltip>
                                                                            <TooltipTrigger asChild>
                                                                                <span className="inline-flex items-center shrink-0" onClick={e => e.stopPropagation()}>
                                                                                    <Target className="h-3 w-3 text-fuchsia-400" />
                                                                                </span>
                                                                            </TooltipTrigger>
                                                                            <TooltipContent side="top" className="bg-slate-800 border-slate-700 text-xs max-w-xs">
                                                                                {isManageRole ? (
                                                                                    <div className="space-y-1.5">
                                                                                        <div className="font-medium text-fuchsia-300">Growth fit for {matches.length} team member{matches.length !== 1 ? 's' : ''}</div>
                                                                                        {matches.slice(0, 5).map(m => (
                                                                                            <div key={m.user_id} className="text-slate-300">
                                                                                                <span className="text-white">{m.full_name || m.username}</span>
                                                                                                <span className="text-slate-500"> — {m.matching_skills.map(s => s.name).join(', ')}</span>
                                                                                            </div>
                                                                                        ))}
                                                                                        {matches.length > 5 && <div className="text-slate-500 italic">+{matches.length - 5} more</div>}
                                                                                    </div>
                                                                                ) : (
                                                                                    <div>
                                                                                        <div className="font-medium text-fuchsia-300 mb-0.5">Matches your growth focus</div>
                                                                                        <div className="text-slate-300">{myMatch?.matching_skills.map(s => s.name).join(', ')}</div>
                                                                                    </div>
                                                                                )}
                                                                            </TooltipContent>
                                                                        </Tooltip>
                                                                    )}
                                                                    <span className="text-sm font-medium text-white truncate">{eng.name}</span>
                                                                </div>
                                                                <span className="text-[10px] text-slate-600 truncate block">{eng.client_name}</span>
                                                                {eng.engagement_type && (
                                                                    <span
                                                                        className="text-[9px] font-medium px-1.5 py-0.5 rounded-full inline-flex items-center gap-1 mt-0.5 w-fit"
                                                                        style={{
                                                                            backgroundColor: (typeMap[eng.engagement_type]?.color || '#6366f1') + '20',
                                                                            color: typeMap[eng.engagement_type]?.color || '#6366f1',
                                                                        }}
                                                                    >
                                                                        <span
                                                                            className="w-1 h-1 rounded-full"
                                                                            style={{ backgroundColor: typeMap[eng.engagement_type]?.color || '#6366f1' }}
                                                                        />
                                                                        {eng.engagement_type}
                                                                    </span>
                                                                )}
                                                            </div>

                                                            {/* Timeline bar */}
                                                            <div className="flex-1 relative h-8 bg-slate-800/20 rounded overflow-hidden border border-slate-800/40">
                                                                {todayPosition !== null && (
                                                                    <div className="absolute top-0 h-full w-px bg-red-500/40 z-[5]"
                                                                        style={{ left: `${todayPosition}%` }} />
                                                                )}

                                                                {hasPhases ? (
                                                                    // Multi-segment phase bars
                                                                    eng.phases.map((phase: EngagementPhase) => {
                                                                        if (!phase.planned_start || !phase.planned_end) return null;
                                                                        const pos = getPosition(phase.planned_start, phase.planned_end);
                                                                        const phaseColor = PHASE_COLORS[phase.phase_name];
                                                                        const phaseHealth = getPhaseHealth(phase, eng.status);
                                                                        if (!phaseColor) return null;

                                                                        return (
                                                                            <Tooltip key={phase.id}>
                                                                                <TooltipTrigger asChild>
                                                                                    <div
                                                                                        className={cn(
                                                                                            'absolute top-1 bottom-1 rounded-sm transition-opacity',
                                                                                            phaseColor.bg,
                                                                                            phaseHealth === 'late' ? 'opacity-90 ring-1 ring-red-500/60' :
                                                                                            phaseHealth === 'completed' ? 'opacity-30' :
                                                                                            phaseHealth === 'on-time' ? 'opacity-70' : 'opacity-40',
                                                                                            'hover:opacity-100'
                                                                                        )}
                                                                                        style={{ left: `${pos.left}%`, width: `${pos.width}%`, minWidth: '2px' }}
                                                                                    />
                                                                                </TooltipTrigger>
                                                                                <TooltipContent side="top" className="bg-slate-800 border-slate-700 text-xs">
                                                                                    <div className="flex items-center gap-1.5">
                                                                                        <div className={cn('w-2 h-2 rounded-full', phaseColor.bg)} />
                                                                                        <span className="font-semibold text-white">{phaseColor.label}</span>
                                                                                        {phaseHealth === 'late' && (
                                                                                            <Badge variant="outline" className="text-[8px] py-0 border-red-500/40 text-red-400 ml-1">LATE</Badge>
                                                                                        )}
                                                                                        {phaseHealth === 'completed' && (
                                                                                            <CheckCircle2 className="h-3 w-3 text-green-500 ml-1" />
                                                                                        )}
                                                                                    </div>
                                                                                    <div className="text-slate-500 mt-0.5">
                                                                                        {format(parseISO(phase.planned_start), 'MMM d')} – {format(parseISO(phase.planned_end), 'MMM d')}
                                                                                    </div>
                                                                                </TooltipContent>
                                                                            </Tooltip>
                                                                        );
                                                                    })
                                                                ) : (
                                                                    // Fallback: single bar for proposed (no phases yet)
                                                                    (() => {
                                                                        const pos = getPosition(eng.start_date, eng.end_date);
                                                                        return (
                                                                            <Tooltip>
                                                                                <TooltipTrigger asChild>
                                                                                    <div
                                                                                        className="absolute top-1 bottom-1 rounded-sm bg-teal-500 opacity-50 border border-dashed border-teal-400/60 hover:opacity-80 transition-opacity"
                                                                                        style={{ left: `${pos.left}%`, width: `${pos.width}%`, minWidth: '4px' }}
                                                                                    />
                                                                                </TooltipTrigger>
                                                                                <TooltipContent side="top" className="bg-slate-800 border-slate-700 text-xs">
                                                                                    <p className="font-semibold text-white">{eng.name}</p>
                                                                                    <p className="text-teal-400 text-[9px]">Proposed — no phases yet</p>
                                                                                </TooltipContent>
                                                                            </Tooltip>
                                                                        );
                                                                    })()
                                                                )}
                                                            </div>
                                                        </div>
                                                    );
                                                })
                                            )}
                                        </div>
                                    </TooltipProvider>
                                </CardContent>
                            </Card>

                            {/* Legend */}
                            <div className="flex items-center gap-5 mt-3 px-1">
                                {Object.entries(PHASE_COLORS).map(([key, val]) => (
                                    <div key={key} className="flex items-center gap-1.5 text-[10px] text-slate-600">
                                        <div className={cn('w-3 h-2 rounded-sm', val.bg)} />
                                        <span>{val.label}</span>
                                    </div>
                                ))}
                                <div className="flex items-center gap-1.5 text-[10px] text-slate-600">
                                    <div className="w-3 h-2 rounded-sm bg-teal-500 opacity-50 border border-dashed border-teal-400/60" />
                                    <span>Proposed</span>
                                </div>
                                <div className="flex items-center gap-1.5 text-[10px] text-slate-600">
                                    <div className="w-3 h-0.5 bg-red-500 rounded" />
                                    <span>Today</span>
                                </div>
                                <div className="flex items-center gap-1.5 text-[10px] text-red-400">
                                    <AlertTriangle className="h-3 w-3" />
                                    <span>Late</span>
                                </div>
                            </div>
                        </div>

                        {/* Inspector Panel */}
                        <div className="lg:col-span-1">
                            <Card className="border-slate-800 bg-slate-900 border-l-4 border-l-primary sticky top-6">
                                <CardContent className="p-6">
                                    {!selectedEngagement ? (
                                        <div className="text-center py-10 space-y-3">
                                            <Target className="h-10 w-10 text-slate-700 mx-auto" />
                                            <p className="text-slate-500 text-sm italic">Select an engagement from the timeline</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-5">
                                            <div>
                                                <Badge className={STATUS_BADGE_COLORS[selectedEngagement.status] || ''}>
                                                    {selectedEngagement.status.replace('_', ' ')}
                                                </Badge>
                                                <h3 className="text-lg font-bold text-white mt-2 leading-tight">{selectedEngagement.name}</h3>
                                                <p className="text-sm text-slate-400 mt-0.5">{selectedEngagement.client_name}</p>
                                            </div>

                                            <div className="space-y-2 text-sm">
                                                <div className="flex items-center gap-2 text-slate-400">
                                                    <Clock className="h-4 w-4 shrink-0" />
                                                    <span>
                                                        {selectedEngagement.start_date ? format(parseISO(selectedEngagement.start_date), 'MMM d, yyyy') : '?'}
                                                        {' – '}
                                                        {selectedEngagement.end_date ? format(parseISO(selectedEngagement.end_date), 'MMM d, yyyy') : 'Ongoing'}
                                                    </span>
                                                </div>
                                                {selectedEngagement.engagement_type && (
                                                    <div className="flex items-center gap-2 text-slate-400">
                                                        <Target className="h-4 w-4 shrink-0" />
                                                        <span>{selectedEngagement.engagement_type}</span>
                                                    </div>
                                                )}
                                                {selectedEngagement.assigned_users?.length > 0 && (
                                                    <div className="space-y-1.5">
                                                        <div className="flex items-center justify-between">
                                                            <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium uppercase tracking-wider">
                                                                <Users className="h-3 w-3" /> Team ({selectedEngagement.assigned_users.length})
                                                            </div>
                                                            <button
                                                                onClick={handleCopyInspectorEmails}
                                                                className="flex items-center gap-1 text-[10px] text-primary hover:text-primary/80 transition-colors"
                                                            >
                                                                {inspectorEmailsCopied
                                                                    ? <><Check className="h-3 w-3" />Copied!</>
                                                                    : <><Mail className="h-3 w-3" />Copy Emails</>}
                                                            </button>
                                                        </div>
                                                        <div className="flex flex-wrap gap-1.5">
                                                            {selectedEngagement.assigned_users.map((u: any) => (
                                                                <Badge key={u.id} variant="outline" className="border-slate-800 text-[10px] py-0.5 bg-slate-900/50">
                                                                    {u.full_name || u.username}
                                                                </Badge>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Phase breakdown */}
                                            {selectedEngagement.phases?.length > 0 && (
                                                <div className="space-y-2">
                                                    <div className="flex items-center justify-between">
                                                        <p className="text-xs text-slate-500 font-medium uppercase tracking-wider">Phases</p>
                                                        {Object.keys(editingPhases).length === 0 ? (
                                                            <button
                                                                onClick={() => startEditPhases(selectedEngagement.phases)}
                                                                className="text-[10px] text-primary hover:text-primary/80"
                                                            >
                                                                Edit Dates
                                                            </button>
                                                        ) : (
                                                            <div className="flex gap-1.5">
                                                                <button
                                                                    onClick={() => setEditingPhases({})}
                                                                    className="text-[10px] text-slate-500 hover:text-slate-300"
                                                                >Cancel</button>
                                                                <button
                                                                    onClick={() => handleSavePhases(selectedEngagement.id, selectedEngagement.phases)}
                                                                    className="text-[10px] text-primary hover:text-primary/80 font-semibold"
                                                                >Save</button>
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        {selectedEngagement.phases.map((phase: EngagementPhase) => {
                                                            const phaseColor = PHASE_COLORS[phase.phase_name];
                                                            const health = getPhaseHealth(phase, selectedEngagement.status);
                                                            const isEditing = !!editingPhases[phase.id];

                                                            return (
                                                                <div key={phase.id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-2.5">
                                                                    <div className="flex items-center justify-between mb-1">
                                                                        <div className="flex items-center gap-1.5">
                                                                            <div className={cn('w-2 h-2 rounded-full', phaseColor?.bg || 'bg-slate-500')} />
                                                                            <span className="text-xs font-medium text-white">{phaseColor?.label || phase.phase_name}</span>
                                                                        </div>
                                                                        {health === 'late' && (
                                                                            <Badge variant="outline" className="text-[8px] py-0 border-red-500/40 text-red-400 gap-0.5">
                                                                                <AlertTriangle className="h-2.5 w-2.5" /> LATE
                                                                            </Badge>
                                                                        )}
                                                                        {health === 'on-time' && (
                                                                            <Badge variant="outline" className="text-[8px] py-0 border-green-500/40 text-green-400">
                                                                                ON TIME
                                                                            </Badge>
                                                                        )}
                                                                        {health === 'completed' && (
                                                                            <CheckCircle2 className="h-3 w-3 text-green-500" />
                                                                        )}
                                                                    </div>
                                                                    {isEditing ? (
                                                                        <div className="grid grid-cols-2 gap-1.5 mt-1">
                                                                            <Input
                                                                                type="date"
                                                                                value={editingPhases[phase.id]?.start || ''}
                                                                                onChange={e => setEditingPhases({
                                                                                    ...editingPhases,
                                                                                    [phase.id]: { ...editingPhases[phase.id], start: e.target.value },
                                                                                })}
                                                                                className="bg-slate-800 border-slate-700 text-[10px] h-7 px-1.5"
                                                                            />
                                                                            <Input
                                                                                type="date"
                                                                                value={editingPhases[phase.id]?.end || ''}
                                                                                onChange={e => setEditingPhases({
                                                                                    ...editingPhases,
                                                                                    [phase.id]: { ...editingPhases[phase.id], end: e.target.value },
                                                                                })}
                                                                                className="bg-slate-800 border-slate-700 text-[10px] h-7 px-1.5"
                                                                            />
                                                                        </div>
                                                                    ) : (
                                                                        <p className="text-[10px] text-slate-500">
                                                                            {phase.planned_start ? format(parseISO(phase.planned_start), 'MMM d') : '?'}
                                                                            {' – '}
                                                                            {phase.planned_end ? format(parseISO(phase.planned_end), 'MMM d, yyyy') : '?'}
                                                                        </p>
                                                                    )}
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Actions */}
                                            <div className="pt-3 space-y-2">
                                                {selectedEngagement.status === 'PROPOSED' && (
                                                    <Button
                                                        onClick={() => handlePromote(selectedEngagement.id)}
                                                        className="w-full bg-amber-600 hover:bg-amber-700 text-white gap-2"
                                                        disabled={updateEngagement.isPending}
                                                    >
                                                        {updateEngagement.isPending ? (
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                            <Play className="h-4 w-4" />
                                                        )}
                                                        Promote to Planning
                                                    </Button>
                                                )}
                                                <div className="flex gap-2">
                                                    <Button variant="outline"
                                                        onClick={() => router.push(`/engagements/${selectedEngagement.id}`)}
                                                        className="flex-1 border-slate-700 text-slate-300 hover:text-white">
                                                        View Details
                                                    </Button>
                                                    {selectedEngagement.status !== 'PROPOSED' && (
                                                        <Button variant="outline"
                                                            onClick={() => router.push(`/engagements/${selectedEngagement.id}/edit?from=planning`)}
                                                            className="flex-1 border-primary/30 text-primary hover:bg-primary/10 gap-1.5">
                                                            <Edit className="h-3.5 w-3.5" /> Edit
                                                        </Button>
                                                    )}
                                                    {selectedEngagement.status === 'PROPOSED' && (
                                                        <DropdownMenu>
                                                            <DropdownMenuTrigger asChild>
                                                                <Button variant="outline" size="icon" className="border-slate-700 text-slate-400 hover:text-white">
                                                                    <MoreHorizontal className="h-4 w-4" />
                                                                </Button>
                                                            </DropdownMenuTrigger>
                                                            <DropdownMenuContent align="end" className="w-40">
                                                                <DropdownMenuItem onClick={() => router.push(`/engagements/${selectedEngagement.id}`)}>
                                                                    <Edit className="h-4 w-4 mr-2" /> Edit
                                                                </DropdownMenuItem>
                                                                <DropdownMenuSeparator />
                                                                <DropdownMenuItem onClick={() => handleDelete(selectedEngagement.id)} className="text-red-400 focus:text-red-400">
                                                                    <Trash2 className="h-4 w-4 mr-2" /> Delete
                                                                </DropdownMenuItem>
                                                            </DropdownMenuContent>
                                                        </DropdownMenu>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    </div>
                )}

                {/* ═══════ SCHEDULING TAB ═══════ */}
                {activeTab === 'scheduling' && (
                    <Card className="border-slate-800 bg-slate-900/50 border-t-4 border-t-indigo-500">
                        <CardContent className="p-5">
                            <SchedulingAssistant
                                defaultStart={startOfMonth(currentMonth)}
                                defaultEnd={endOfMonth(currentMonth)}
                                onSelectUsers={setFilterUserIds}
                                selectedUserIds={filterUserIds}
                            />
                        </CardContent>
                    </Card>
                )}

                <ConfirmDialog />

                {/* ═══════ CREATE DIALOG ═══════ */}
                <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                    <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[500px]">
                        <form onSubmit={handleCreate}>
                            <DialogHeader>
                                <DialogTitle className="flex items-center gap-2">
                                    <Sparkles className="h-5 w-5 text-teal-400" />
                                    Propose Engagement
                                </DialogTitle>
                            </DialogHeader>
                            <div className="grid gap-4 py-4">
                                <div className="space-y-2">
                                    <Label>Engagement Name</Label>
                                    <Input
                                        value={newEngagement.name}
                                        onChange={e => setNewEngagement({ ...newEngagement, name: e.target.value })}
                                        placeholder="e.g., Annual Pentest — Acme Corp"
                                        className="bg-slate-800 border-slate-700" required
                                    />
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label>Client</Label>
                                        <Select value={newEngagement.client_id}
                                            onValueChange={(val) => {
                                                const c = clients.find((c: any) => c.id === val);
                                                setNewEngagement({ ...newEngagement, client_id: val, client_name: c?.name || '' });
                                            }}>
                                            <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue placeholder="Select client..." /></SelectTrigger>
                                            <SelectContent className="bg-slate-800 border-slate-700">
                                                {clients.map((c: any) => (
                                                    <SelectItem key={c.id} value={c.id} className="text-white">{c.name}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Type</Label>
                                        <Select value={newEngagement.engagement_type}
                                            onValueChange={(val) => setNewEngagement({ ...newEngagement, engagement_type: val })}>
                                            <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue placeholder="Select type..." /></SelectTrigger>
                                            <SelectContent className="bg-slate-800 border-slate-700">
                                                {engagementTypes.map((t: any) => (
                                                    <SelectItem key={t.name} value={t.name} className="text-white">{t.description || t.name}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label>Proposed Start</Label>
                                        <Input type="date" value={newEngagement.start_date}
                                            onChange={e => setNewEngagement({ ...newEngagement, start_date: e.target.value })}
                                            className="bg-slate-800 border-slate-700 text-sm" required />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Proposed End</Label>
                                        <Input type="date" value={newEngagement.end_date}
                                            onChange={e => setNewEngagement({ ...newEngagement, end_date: e.target.value })}
                                            className="bg-slate-800 border-slate-700 text-sm" required />
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <Label>Description <span className="text-slate-500">(optional)</span></Label>
                                    <Input value={newEngagement.description}
                                        onChange={e => setNewEngagement({ ...newEngagement, description: e.target.value })}
                                        placeholder="Brief scope or notes..." className="bg-slate-800 border-slate-700" />
                                </div>
                            </div>
                            <DialogFooter>
                                <Button type="button" variant="outline" onClick={() => setCreateDialogOpen(false)} className="border-slate-700">Cancel</Button>
                                <Button type="submit" className="bg-primary hover:bg-primary/90" disabled={createEngagement.isPending}>
                                    {createEngagement.isPending
                                        ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Creating...</>
                                        : <><Sparkles className="h-4 w-4 mr-2" /> Create Proposal</>}
                                </Button>
                            </DialogFooter>
                        </form>
                    </DialogContent>
                </Dialog>
            </div>
        </DashboardLayout>
    );
}

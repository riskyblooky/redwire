'use client';

import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from '@/components/ui/command';
import { cn } from '@/lib/utils';
import {
    Users, Loader2, Clock,
    Target,
    Sparkles, Calendar as CalendarIcon, ArrowRight,
    Check, ChevronsUpDown,
    ArrowUpDown, SortAsc, UserMinus, UserPlus, CircleDot,
    Save, Shield, Settings, Radar,
} from 'lucide-react';
import { useTeamAvailability } from '@/lib/hooks/use-calendar';
import { useEngagements, useUpdateEngagement } from '@/lib/hooks/use-engagements';
import { useEngagementRoles } from '@/lib/hooks/use-rbac';
import { useEngagementSkills, useFocusFit, SKILL_LEVELS, type EngagementSkill } from '@/lib/hooks/use-skills';
import { AuthedImg } from '@/lib/hooks/use-authed-image';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import {
    format, parseISO, differenceInDays,
    max as dateMax, min as dateMin,
} from 'date-fns';

// Percentage of the scheduling window a member's OoO covers (0–100). Uses
// parseISO to stay consistent with getBarStyle's date handling. Overlapping
// OoO blocks may double-count, so the result is clamped to 100.
function oooOverlapPct(oooEvents: any[] | undefined, winStart: Date, winEnd: Date): number {
    const winMs = Math.max(1, winEnd.getTime() - winStart.getTime());
    let overlapMs = 0;
    for (const o of oooEvents || []) {
        if (!o?.start_time || !o?.end_time) continue;
        const s = Math.max(winStart.getTime(), parseISO(o.start_time).getTime());
        const e = Math.min(winEnd.getTime(), parseISO(o.end_time).getTime());
        if (e > s) overlapMs += e - s;
    }
    return Math.min(100, (overlapMs / winMs) * 100);
}

interface SchedulingAssistantProps {
    defaultStart: Date;
    defaultEnd: Date;
    onSelectUsers?: (userIds: string[]) => void;
    onSelectEngagement?: (engagementId: string) => void;
    selectedUserIds?: string[];
    selectedEvent?: any;
}

export function SchedulingAssistant({
    defaultStart,
    defaultEnd,
    onSelectUsers,
    onSelectEngagement,
    selectedUserIds = [],
    selectedEvent,
}: SchedulingAssistantProps) {
    const [showAutoAssign, setShowAutoAssign] = useState(false);
    const [autoAssignCount, setAutoAssignCount] = useState(3);
    const [excludeBusy, setExcludeBusy] = useState(true);
    const [dateMode, setDateMode] = useState<'month' | 'custom' | 'engagement'>('month');
    const [customStart, setCustomStart] = useState(format(defaultStart, "yyyy-MM-dd"));
    const [customEnd, setCustomEnd] = useState(format(defaultEnd, "yyyy-MM-dd"));
    const [selectedEngagementId, setSelectedEngagementId] = useState<string | null>(null);
    const [engagementPickerOpen, setEngagementPickerOpen] = useState(false);
    const [sortMode, setSortMode] = useState<'alpha' | 'availability' | 'best-match'>('alpha');
    // Track role assignments per user: { userId: roleId }
    const lastAppliedEngRef = useRef<string | null>(null);
    const [userRoles, setUserRoles] = useState<Record<string, string>>({});
    const [excludeOoo, setExcludeOoo] = useState(true);
    // Exclude a member only when their OoO covers at least this % of the
    // window — so a brief appointment doesn't drop someone from suggestions.
    const [oooThreshold, setOooThreshold] = useState(50);
    const [prioritizeSkills, setPrioritizeSkills] = useState(true);

    const { data: allEngagements = [] } = useEngagements();
    const { data: engagementRoles = [] } = useEngagementRoles();
    const updateEngagement = useUpdateEngagement();

    // Fetch engagement skills when in engagement mode
    const { data: engagementSkills = [] } = useEngagementSkills(
        dateMode === 'engagement' ? (selectedEngagementId || undefined) : undefined
    );

    // Growth-focus matches per engagement (manage roles see all team focuses; operators see their own)
    const { data: focusFit = [] } = useFocusFit();
    const focusFitForSelectedEng = useMemo(() => {
        if (dateMode !== 'engagement' || !selectedEngagementId) return null;
        const item = focusFit.find(f => f.engagement_id === selectedEngagementId);
        return item ? new Map(item.matches.map(m => [m.user_id, m.matching_skills])) : null;
    }, [focusFit, dateMode, selectedEngagementId]);

    // Determine the effective date range based on mode
    const { rangeStart, rangeEnd } = useMemo(() => {
        if (dateMode === 'custom') {
            return { rangeStart: new Date(customStart), rangeEnd: new Date(customEnd) };
        }
        if (dateMode === 'engagement' && selectedEngagementId) {
            const eng = allEngagements.find(e => e.id === selectedEngagementId);
            if (eng) {
                return {
                    rangeStart: new Date(eng.start_date),
                    rangeEnd: eng.end_date ? new Date(eng.end_date) : defaultEnd,
                };
            }
        }
        return { rangeStart: defaultStart, rangeEnd: defaultEnd };
    }, [dateMode, customStart, customEnd, selectedEngagementId, allEngagements, defaultStart, defaultEnd]);

    const effectiveStart = rangeStart;
    const effectiveEnd = rangeEnd;

    const { data: availability = [], isLoading } = useTeamAvailability(effectiveStart, effectiveEnd);

    const totalDays = Math.max(differenceInDays(effectiveEnd, effectiveStart), 1);

    // Get the selected engagement object with assignment_details
    const selectedEng = useMemo(() => {
        if (dateMode === 'engagement' && selectedEngagementId) {
            return allEngagements.find(e => e.id === selectedEngagementId) || null;
        }
        return null;
    }, [dateMode, selectedEngagementId, allEngagements]);

    // Determine assigned user IDs
    const assignedUserIds = useMemo(() => {
        if (dateMode === 'engagement' && selectedEngagementId) {
            const eng = allEngagements.find(e => e.id === selectedEngagementId);
            if (eng?.assigned_users) {
                return new Set<string>(eng.assigned_users.map((u: any) => u.id));
            }
        }
        if (selectedEvent?.assigned_users) {
            return new Set<string>(selectedEvent.assigned_users.map((u: any) => u.id));
        }
        return new Set<string>();
    }, [dateMode, selectedEngagementId, allEngagements, selectedEvent]);

    const hasAssignmentContext = assignedUserIds.size > 0;

    // Auto-select assigned users and pre-populate roles when engagement changes
    // Guarded by ref so onSelectUsers only fires once per engagement switch
    useEffect(() => {
        const key = dateMode === 'engagement' ? selectedEngagementId : null;
        if (key === lastAppliedEngRef.current) return;
        lastAppliedEngRef.current = key;

        if (dateMode === 'engagement' && selectedEngagementId) {
            const eng = allEngagements.find(e => e.id === selectedEngagementId);
            if (eng?.assigned_users && onSelectUsers) {
                onSelectUsers(eng.assigned_users.map((u: any) => u.id));
            }
            if (eng?.assignment_details) {
                const roles: Record<string, string> = {};
                for (const detail of eng.assignment_details) {
                    if (detail.role_id) {
                        roles[detail.user_id] = detail.role_id;
                    }
                }
                setUserRoles(roles);
            } else {
                setUserRoles({});
            }
        } else {
            setUserRoles({});
        }
        // Notify parent to sync engagement to the inspector pane
        if (dateMode === 'engagement' && selectedEngagementId && onSelectEngagement) {
            onSelectEngagement(selectedEngagementId);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedEngagementId, dateMode, allEngagements]);

    const stats = useMemo(() => {
        const busy = availability.filter(a => a.engagement_count > 0).length;
        const available = availability.filter(a => a.engagement_count === 0).length;
        const ooo = availability.filter(a => a.ooo_events && a.ooo_events.length > 0).length;
        return { total: availability.length, busy, available, ooo };
    }, [availability]);

    // ── Composite Scoring ──────────────────────────────────────────
    const computeScore = useCallback((member: any): number => {
        let score = 0;

        // Availability score (0-40): fewer engagements = higher
        const maxEng = Math.max(1, ...availability.map(a => a.engagement_count));
        const availScore = (1 - member.engagement_count / maxEng) * 40;
        score += availScore;

        // Skill match score (0-40): only when engagement mode with required skills
        if (prioritizeSkills && engagementSkills.length > 0 && member.user_skills) {
            const userSkillMap: Record<string, number> = {};
            for (const us of member.user_skills) {
                userSkillMap[us.skill_id] = us.level;
            }
            let matched = 0;
            for (const req of engagementSkills) {
                const userLevel = userSkillMap[req.skill_id] ?? 0;
                if (userLevel >= req.min_level) matched++;
            }
            const matchPct = matched / engagementSkills.length;
            score += matchPct * 40;
        }

        // OoO penalty (-20): if user has any OoO during the range
        if (member.ooo_events && member.ooo_events.length > 0) {
            score -= 20;
        }

        return Math.round(score * 10) / 10;
    }, [availability, engagementSkills, prioritizeSkills]);

    // Compute skill match percentage per user (for badge display)
    const getSkillMatchPct = useCallback((member: any): number | null => {
        if (engagementSkills.length === 0 || !member.user_skills) return null;
        const userSkillMap: Record<string, number> = {};
        for (const us of member.user_skills) {
            userSkillMap[us.skill_id] = us.level;
        }
        let matched = 0;
        for (const req of engagementSkills) {
            const userLevel = userSkillMap[req.skill_id] ?? 0;
            if (userLevel >= req.min_level) matched++;
        }
        return Math.round((matched / engagementSkills.length) * 100);
    }, [engagementSkills]);

    // Sort the availability list, with assigned users at top when engagement context exists
    const { assignedGroup, otherGroup } = useMemo(() => {
        const arr = [...availability];
        const sortFn = sortMode === 'alpha'
            ? (a: any, b: any) => (a.user.full_name || a.user.username).toLowerCase().localeCompare((b.user.full_name || b.user.username).toLowerCase())
            : sortMode === 'best-match'
                ? (a: any, b: any) => computeScore(b) - computeScore(a)
                : (a: any, b: any) => a.engagement_count - b.engagement_count;

        if (hasAssignmentContext) {
            const assigned = arr.filter(m => assignedUserIds.has(m.user.id)).sort(sortFn);
            const others = arr.filter(m => !assignedUserIds.has(m.user.id)).sort(sortFn);
            return { assignedGroup: assigned, otherGroup: others };
        }
        return { assignedGroup: [] as typeof arr, otherGroup: arr.sort(sortFn) };
    }, [availability, sortMode, hasAssignmentContext, assignedUserIds, computeScore]);

    const toggleUserSelection = (userId: string) => {
        if (!onSelectUsers) return;
        const newSelected = selectedUserIds.includes(userId)
            ? selectedUserIds.filter(id => id !== userId)
            : [...selectedUserIds, userId];
        onSelectUsers(newSelected);
    };

    const applySuggestions = useCallback(() => {
        if (!onSelectUsers) return;
        // Keep already-assigned users, then add scored candidates up to the total headcount
        const alreadyAssigned = Array.from(assignedUserIds);
        const slotsToFill = Math.max(0, autoAssignCount - alreadyAssigned.length);
        const candidates = [...availability]
            .filter(m => !assignedUserIds.has(m.user.id))
            .filter(m => excludeBusy ? m.engagement_count === 0 : true)
            .filter(m => excludeOoo ? oooOverlapPct(m.ooo_events, effectiveStart, effectiveEnd) < oooThreshold : true)
            .sort((a, b) => computeScore(b) - computeScore(a))
            .slice(0, slotsToFill)
            .map(m => m.user.id);

        if (candidates.length === 0) {
            toast.error('No available members', { description: 'No additional team members match the current criteria.' });
            return;
        }
        const merged = [...new Set([...alreadyAssigned, ...candidates])];
        onSelectUsers(merged);

        const hasSkills = engagementSkills.length > 0;
        toast.success(`Added ${candidates.length} suggested members`, {
            description: hasSkills
                ? 'Ranked by skill match + availability'
                : excludeBusy ? 'Free members only' : 'Prioritized by least busy',
        });
    }, [availability, autoAssignCount, excludeBusy, excludeOoo, oooThreshold, effectiveStart, effectiveEnd, onSelectUsers, assignedUserIds, computeScore, engagementSkills]);

    const setUserRole = useCallback((userId: string, roleId: string) => {
        setUserRoles(prev => ({ ...prev, [userId]: roleId }));
    }, []);

    // Check if there are unsaved changes
    const hasChanges = useMemo(() => {
        if (!hasAssignmentContext || !selectedEngagementId) return false;
        // Check if user selection differs from assigned users
        const currentSelected = new Set(selectedUserIds);
        if (currentSelected.size !== assignedUserIds.size) return true;
        for (const uid of assignedUserIds) {
            if (!currentSelected.has(uid)) return true;
        }
        // Check if roles differ
        if (selectedEng?.assignment_details) {
            for (const detail of selectedEng.assignment_details) {
                const currentRole = userRoles[detail.user_id];
                if ((detail.role_id || '') !== (currentRole || '')) return true;
            }
        }
        // Check if newly added users have roles
        for (const uid of selectedUserIds) {
            if (!assignedUserIds.has(uid) && userRoles[uid]) return true;
        }
        return false;
    }, [hasAssignmentContext, selectedEngagementId, selectedUserIds, assignedUserIds, userRoles, selectedEng]);

    const handleSaveAssignments = async () => {
        if (!selectedEngagementId) return;

        const assignments = selectedUserIds.map(uid => ({
            user_id: uid,
            ...(userRoles[uid] ? { role_id: userRoles[uid] } : {}),
        }));

        try {
            await updateEngagement.mutateAsync({
                id: selectedEngagementId,
                assignments,
            });
            toast.success('Team assignments saved', {
                description: `Updated ${assignments.length} assignments for the engagement.`,
            });
        } catch (error: any) {
            toast.error('Failed to save assignments', {
                description: apiErrorMessage(error, 'An error occurred.'),
            });
        }
    };

    const getBarStyle = (engStart: string | null, engEnd: string | null) => {
        if (!engStart) return { left: '0%', width: '0%' };
        const eStart = parseISO(engStart);
        const eEnd = engEnd ? parseISO(engEnd) : effectiveEnd;
        const clampedStart = dateMax([eStart, effectiveStart]);
        const clampedEnd = dateMin([eEnd, effectiveEnd]);
        const leftDays = differenceInDays(clampedStart, effectiveStart);
        const widthDays = Math.max(differenceInDays(clampedEnd, clampedStart), 1);
        const left = (leftDays / totalDays) * 100;
        const width = (widthDays / totalDays) * 100;
        return {
            left: `${Math.max(0, Math.min(left, 100))}%`,
            width: `${Math.max(1, Math.min(width, 100 - left))}%`,
        };
    };

    const statusColor = (status: string) => {
        switch (status) {
            case 'SCOPING': return 'bg-cyan-500';
            case 'IN_PROGRESS': return 'bg-primary';
            case 'PLANNING': return 'bg-amber-500';
            case 'REPORTING': return 'bg-blue-500';
            case 'ON_HOLD': return 'bg-slate-500';
            case 'COMPLETED': return 'bg-green-500';
            default: return 'bg-primary';
        }
    };

    const getRowDiffStyle = (userId: string) => {
        if (!hasAssignmentContext) {
            const isSelected = selectedUserIds.includes(userId);
            if (isSelected) return 'border-indigo-500/30 bg-indigo-500/5';
            return 'border-transparent hover:bg-slate-800/40';
        }

        const isSelected = selectedUserIds.includes(userId);
        const isAssigned = assignedUserIds.has(userId);

        if (isAssigned && isSelected) return 'border-blue-500/40 bg-blue-500/8';
        if (!isAssigned && isSelected) return 'border-green-500/40 bg-green-500/8';
        if (isAssigned && !isSelected) return 'border-red-500/40 bg-red-500/8';
        return 'border-transparent hover:bg-slate-800/40';
    };

    const getRowDiffIcon = (userId: string) => {
        if (!hasAssignmentContext) return null;

        const isSelected = selectedUserIds.includes(userId);
        const isAssigned = assignedUserIds.has(userId);

        if (isAssigned && isSelected)
            return <CircleDot className="h-3.5 w-3.5 text-blue-400 shrink-0" />;
        if (!isAssigned && isSelected)
            return <UserPlus className="h-3.5 w-3.5 text-green-400 shrink-0" />;
        if (isAssigned && !isSelected)
            return <UserMinus className="h-3.5 w-3.5 text-red-400 shrink-0" />;
        return null;
    };

    return (
        <TooltipProvider delayDuration={200}>
            <div className="space-y-4">
                {/* Header Row */}
                <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3 flex-wrap">
                        <div className="flex items-center gap-2">
                            <Users className="h-5 w-5 text-indigo-400" />
                            <span className="text-sm font-semibold text-white">Team Availability</span>
                        </div>

                        {/* Mode toggles — always in fixed position */}
                        <div className="flex items-center bg-slate-800/60 rounded-lg overflow-hidden border border-slate-700/50">
                            {(['month', 'custom', 'engagement'] as const).map((mode) => (
                                <button
                                    key={mode}
                                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${dateMode === mode
                                        ? 'bg-indigo-500/20 text-indigo-400'
                                        : 'text-slate-500 hover:text-slate-300'}`}
                                    onClick={() => setDateMode(mode)}
                                >
                                    {mode === 'month' ? 'This Month' : mode === 'custom' ? 'Custom Dates' : 'By Engagement'}
                                </button>
                            ))}
                        </div>

                        {/* Conditional controls appear RIGHT of toggles */}
                        {dateMode === 'custom' && (
                            <div className="flex items-center gap-2">
                                <Input
                                    type="date" value={customStart}
                                    onChange={e => setCustomStart(e.target.value)}
                                    className="h-8 bg-slate-800 border-slate-700 text-xs text-white w-[135px]"
                                />
                                <ArrowRight className="h-3.5 w-3.5 text-slate-600" />
                                <Input
                                    type="date" value={customEnd}
                                    onChange={e => setCustomEnd(e.target.value)}
                                    className="h-8 bg-slate-800 border-slate-700 text-xs text-white w-[135px]"
                                />
                            </div>
                        )}

                        {dateMode === 'engagement' && (() => {
                            // Command popover instead of a plain Radix Select so the
                            // dropdown is searchable — with hundreds of engagements
                            // the flat list was unusable. Mirrors the calendar page's
                            // "Find engagement" popover.
                            const selectedEng = selectedEngagementId
                                ? allEngagements.find(e => e.id === selectedEngagementId)
                                : null;
                            return (
                                <Popover open={engagementPickerOpen} onOpenChange={setEngagementPickerOpen}>
                                    <PopoverTrigger asChild>
                                        <Button
                                            variant="outline"
                                            role="combobox"
                                            aria-expanded={engagementPickerOpen}
                                            className="h-8 bg-slate-800 border-slate-700 text-xs text-white w-[240px] justify-between font-normal hover:bg-slate-800/80"
                                        >
                                            {selectedEng ? (
                                                <span className="flex items-center gap-1.5 truncate">
                                                    <Target className="h-3 w-3 text-primary shrink-0" />
                                                    <span className="truncate">{selectedEng.name}</span>
                                                    <span className="text-slate-500 shrink-0">({selectedEng.client_name})</span>
                                                </span>
                                            ) : (
                                                <span className="text-slate-400">Select engagement...</span>
                                            )}
                                            <ChevronsUpDown className="h-3 w-3 shrink-0 opacity-50 ml-1" />
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="w-[300px] p-0 bg-slate-900 border-slate-700">
                                        <Command className="bg-slate-900">
                                            <CommandInput placeholder="Search engagements..." className="text-white" />
                                            <CommandList>
                                                <CommandEmpty>No engagement found.</CommandEmpty>
                                                <CommandGroup>
                                                    {allEngagements.map(eng => (
                                                        <CommandItem
                                                            key={eng.id}
                                                            value={`${eng.name} ${eng.client_name}`}
                                                            onSelect={() => {
                                                                setSelectedEngagementId(eng.id);
                                                                setEngagementPickerOpen(false);
                                                            }}
                                                            className="text-slate-300"
                                                        >
                                                            <Check className={cn('mr-2 h-3.5 w-3.5', selectedEngagementId === eng.id ? 'opacity-100' : 'opacity-0')} />
                                                            <Target className="h-3 w-3 text-primary mr-1.5" />
                                                            <span className="truncate">{eng.name}</span>
                                                            <span className="text-slate-500 ml-1.5">({eng.client_name})</span>
                                                        </CommandItem>
                                                    ))}
                                                </CommandGroup>
                                            </CommandList>
                                        </Command>
                                    </PopoverContent>
                                </Popover>
                            );
                        })()}
                    </div>

                    {/* Right: Stats + Sort */}
                    <div className="flex items-center gap-3">
                        <div className="flex items-center bg-slate-800/60 rounded-lg overflow-hidden border border-slate-700/50">
                            <button
                                className={`px-2.5 py-1.5 text-xs font-medium transition-colors flex items-center gap-1 ${sortMode === 'alpha' ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
                                onClick={() => setSortMode('alpha')}
                            >
                                <SortAsc className="h-3 w-3" /> A–Z
                            </button>
                            <button
                                className={`px-2.5 py-1.5 text-xs font-medium transition-colors flex items-center gap-1 ${sortMode === 'availability' ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
                                onClick={() => setSortMode('availability')}
                            >
                                <ArrowUpDown className="h-3 w-3" /> Most Free
                            </button>
                            <button
                                className={`px-2.5 py-1.5 text-xs font-medium transition-colors flex items-center gap-1 ${sortMode === 'best-match' ? 'bg-amber-500/20 text-amber-400' : 'text-slate-500 hover:text-slate-300'}`}
                                onClick={() => setSortMode('best-match')}
                            >
                                <Sparkles className="h-3 w-3" /> Best Match
                            </button>
                        </div>

                        <div className="flex items-center gap-2">
                            <div className="flex items-center gap-1 bg-slate-800/40 rounded px-2.5 py-1">
                                <span className="text-xs text-slate-500">Team</span>
                                <span className="text-sm font-bold text-white">{stats.total}</span>
                            </div>
                            <div className="flex items-center gap-1 bg-green-500/5 border border-green-500/10 rounded px-2.5 py-1">
                                <span className="text-xs text-green-500/70">Free</span>
                                <span className="text-sm font-bold text-green-400">{stats.available}</span>
                            </div>
                            <div className="flex items-center gap-1 bg-amber-500/5 border border-amber-500/10 rounded px-2.5 py-1">
                                <span className="text-xs text-amber-500/70">Busy</span>
                                <span className="text-sm font-bold text-amber-400">{stats.busy}</span>
                            </div>
                            {stats.ooo > 0 && (
                                <div className="flex items-center gap-1 bg-red-500/5 border border-red-500/10 rounded px-2.5 py-1">
                                    <span className="text-xs text-red-500/70">OoO</span>
                                    <span className="text-sm font-bold text-red-400">{stats.ooo}</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Engagement context banner */}
                {dateMode === 'engagement' && selectedEng && (
                    <div className="flex items-center gap-3 bg-primary/5 border border-primary/10 rounded-lg px-3 py-2">
                        <Target className="h-4 w-4 text-primary shrink-0" />
                        <div className="flex-1 min-w-0">
                            <span className="text-xs font-medium text-primary">{selectedEng.name}</span>
                            <span className="text-xs text-slate-500 ml-2">{selectedEng.client_name}</span>
                        </div>
                        <div className="text-xs text-slate-500 flex items-center gap-1">
                            <CalendarIcon className="h-3.5 w-3.5" />
                            {selectedEng.start_date ? format(parseISO(selectedEng.start_date), 'MMM d') : '?'}
                            {' – '}
                            {selectedEng.end_date ? format(parseISO(selectedEng.end_date), 'MMM d, yyyy') : 'Ongoing'}
                        </div>
                        {assignedUserIds.size > 0 && (
                            <Badge variant="outline" className="text-[10px] border-primary/20 text-primary">
                                {assignedUserIds.size} assigned
                            </Badge>
                        )}
                    </div>
                )}

                {/* Date range labels */}
                <div className="flex items-center justify-between text-xs text-slate-600 px-1">
                    <span>{format(effectiveStart, 'MMM d, yyyy')}</span>
                    <div className="flex-1 mx-3 h-px bg-slate-800" />
                    <span>{format(effectiveEnd, 'MMM d, yyyy')}</span>
                </div>

                {/* Availability Grid */}
                {isLoading ? (
                    <div className="flex items-center justify-center py-6">
                        <Loader2 className="h-5 w-5 text-indigo-400 animate-spin" />
                    </div>
                ) : (
                    <div className="space-y-1">
                        {/* Render user rows: assigned group first, then separator, then others */}
                        {([...assignedGroup, ...(assignedGroup.length > 0 && otherGroup.length > 0 ? [null as any] : []), ...otherGroup] as any[]).map((member: any, idx: number) => {
                            if (member === null) {
                                return (
                                    <div key="__sep__" className="flex items-center gap-3 py-1.5">
                                        <div className="flex-1 h-px bg-slate-700/50" />
                                        <span className="text-[10px] text-slate-600 font-medium uppercase tracking-wider">Other Team Members</span>
                                        <div className="flex-1 h-px bg-slate-700/50" />
                                    </div>
                                );
                            }
                            const isSelected = selectedUserIds.includes(member.user.id);
                            return (
                                <div
                                    key={member.user.id}
                                    className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-all cursor-pointer group border
                                    ${getRowDiffStyle(member.user.id)}`}
                                    onClick={() => toggleUserSelection(member.user.id)}
                                >
                                    {/* Profile Photo / Avatar */}
                                    {member.user.profile_photo ? (
                                        <AuthedImg
                                            src={member.user.profile_photo}
                                            alt={member.user.full_name || member.user.username}
                                            className="h-8 w-8 rounded-full object-cover shrink-0 ring-1 ring-slate-700"
                                        />
                                    ) : (
                                        <div className="h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 bg-slate-700 text-slate-300 ring-1 ring-slate-600">
                                            {(member.user.full_name || member.user.username).charAt(0).toUpperCase()}
                                        </div>
                                    )}

                                    {/* Name */}
                                    <div className="w-[160px] shrink-0 min-w-0">
                                        <div className="flex items-center gap-1.5">
                                            <span className="text-sm font-medium text-white truncate">
                                                {member.user.full_name || member.user.username}
                                            </span>
                                            {member.ooo_events && member.ooo_events.length > 0 && (
                                                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-red-500/15 text-red-400 border border-red-500/20 shrink-0">OoO</span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2 mt-0.5">
                                            <span className="text-[11px] text-slate-500 truncate">
                                                {member.user.role}
                                            </span>
                                            {(() => {
                                                const matchPct = getSkillMatchPct(member);
                                                if (matchPct === null) return null;
                                                const palette =
                                                    matchPct >= 80 ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' :
                                                    matchPct >= 50 ? 'bg-amber-500/15  text-amber-300  border-amber-500/30'  :
                                                                     'bg-red-500/15    text-red-300    border-red-500/30';
                                                return (
                                                    <span
                                                        title="Match against this engagement's required skills"
                                                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-[11px] font-bold tabular-nums shrink-0 ${palette}`}
                                                    >
                                                        <Radar className="h-3 w-3" />
                                                        Skills {matchPct}%
                                                    </span>
                                                );
                                            })()}
                                            {(() => {
                                                const focusMatches = focusFitForSelectedEng?.get(member.user.id);
                                                if (!focusMatches || focusMatches.length === 0) return null;
                                                const skillNames = focusMatches.map(s => s.name).join(', ');
                                                return (
                                                    <Tooltip>
                                                        <TooltipTrigger asChild>
                                                            <span
                                                                className="inline-flex items-center justify-center h-5 w-5 mr-1 rounded-md border shrink-0 bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30"
                                                                aria-label="Growth fit"
                                                            >
                                                                <Target className="h-3 w-3" />
                                                            </span>
                                                        </TooltipTrigger>
                                                        <TooltipContent side="top" className="bg-slate-800 border-slate-700 text-xs max-w-xs">
                                                            <div className="font-medium text-fuchsia-300 mb-0.5">Growth fit</div>
                                                            <div className="text-slate-300">Targeting: {skillNames}</div>
                                                        </TooltipContent>
                                                    </Tooltip>
                                                );
                                            })()}
                                        </div>
                                    </div>

                                    {/* Role selector — only when engagement context + user is selected */}
                                    {hasAssignmentContext && isSelected && engagementRoles.length > 0 && (
                                        <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
                                            <Select
                                                value={userRoles[member.user.id] || 'none'}
                                                onValueChange={(val: string) => setUserRole(member.user.id, val === 'none' ? '' : val)}
                                            >
                                                <SelectTrigger className="h-7 bg-slate-800/80 border-slate-700 text-[11px] text-white w-[130px]">
                                                    <div className="flex items-center gap-1">
                                                        <Shield className="h-3 w-3 text-slate-500" />
                                                        <SelectValue placeholder="Role..." />
                                                    </div>
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-800 border-slate-700">
                                                    <SelectItem value="none" className="text-[11px] text-slate-400">
                                                        No role
                                                    </SelectItem>
                                                    {engagementRoles.map((role: any) => (
                                                        <SelectItem key={role.id} value={role.id} className="text-[11px] text-white">
                                                            {role.name}
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    )}

                                    {/* Timeline */}
                                    <div className="flex-1 relative h-8 bg-slate-800/30 rounded overflow-hidden border border-slate-800/50">
                                        {/* OoO bars — always render, even when available */}
                                        {member.ooo_events && member.ooo_events.map((ooo: any) => {
                                            const style = getBarStyle(ooo.start_time, ooo.end_time);
                                            return (
                                                <Tooltip key={ooo.id}>
                                                    <TooltipTrigger asChild>
                                                        <div
                                                            className="absolute top-0 bottom-0 z-10 opacity-80 hover:opacity-100 transition-opacity"
                                                            style={{
                                                                left: style.left,
                                                                width: style.width,
                                                                minWidth: '4px',
                                                                // Render ABOVE the engagement bars (z-10) so overlapping
                                                                // engagements can't bury OoO. The hatch stays translucent
                                                                // so the engagement underneath still reads through it.
                                                                background: 'repeating-linear-gradient(135deg, transparent, transparent 2px, rgba(239,68,68,0.5) 2px, rgba(239,68,68,0.5) 4px)',
                                                                borderLeft: '2px solid rgba(239,68,68,0.85)',
                                                                borderRight: '2px solid rgba(239,68,68,0.85)',
                                                            }}
                                                        />
                                                    </TooltipTrigger>
                                                    <TooltipContent side="top" className="bg-slate-800 border-slate-700 text-xs max-w-[220px]">
                                                        <p className="font-semibold text-red-400">Out of Office</p>
                                                        <p className="text-slate-400">{ooo.title}</p>
                                                        <div className="flex items-center gap-1 mt-1 text-slate-500">
                                                            <Clock className="h-3 w-3" />
                                                            {format(parseISO(ooo.start_time), 'MMM d')}
                                                            {' – '}
                                                            {format(parseISO(ooo.end_time), 'MMM d')}
                                                        </div>
                                                    </TooltipContent>
                                                </Tooltip>
                                            );
                                        })}
                                        {member.engagement_count === 0 && !(member.ooo_events && member.ooo_events.length > 0) ? (
                                            <div className="absolute inset-0 bg-green-500/3 flex items-center justify-center">
                                                <span className="text-[10px] text-green-500/40 font-medium tracking-wider">AVAILABLE</span>
                                            </div>
                                        ) : (
                                            member.engagements.map((eng: any) => {
                                                const style = getBarStyle(eng.start_date, eng.end_date);
                                                return (
                                                    <Tooltip key={eng.id}>
                                                        <TooltipTrigger asChild>
                                                            <div
                                                                className={`absolute top-0.5 bottom-0.5 rounded-sm ${statusColor(eng.status)} opacity-60 hover:opacity-100 transition-opacity flex items-center justify-center overflow-hidden`}
                                                                style={{ left: style.left, width: style.width, minWidth: '4px' }}
                                                            >
                                                                <span className="text-[8px] text-white/80 font-medium px-1 truncate">
                                                                    {eng.name}
                                                                </span>
                                                            </div>
                                                        </TooltipTrigger>
                                                        <TooltipContent side="top" className="bg-slate-800 border-slate-700 text-xs max-w-[220px]">
                                                            <p className="font-semibold text-white">{eng.name}</p>
                                                            <p className="text-slate-400">{eng.client_name}</p>
                                                            <div className="flex items-center gap-1 mt-1 text-slate-500">
                                                                <Clock className="h-3 w-3" />
                                                                {eng.start_date ? format(parseISO(eng.start_date), 'MMM d') : '?'}
                                                                {' – '}
                                                                {eng.end_date ? format(parseISO(eng.end_date), 'MMM d') : 'Ongoing'}
                                                            </div>
                                                            <Badge className="mt-1 text-[8px]" variant="outline">{eng.status.replace('_', ' ')}</Badge>
                                                        </TooltipContent>
                                                    </Tooltip>
                                                );
                                            })
                                        )}
                                    </div>

                                    {/* Diff indicator icon */}
                                    {getRowDiffIcon(member.user.id)}
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Footer */}
                <div className="flex items-center justify-between flex-wrap gap-3 pt-2 border-t border-slate-800/50">
                    <div className="flex items-center gap-4">
                        {/* Diff legend — only when we have assignment context */}
                        {hasAssignmentContext && (
                            <div className="flex items-center gap-3">
                                <div className="flex items-center gap-1 text-[10px] text-blue-400">
                                    <CircleDot className="h-3 w-3" /> Assigned
                                </div>
                                <div className="flex items-center gap-1 text-[10px] text-green-400">
                                    <UserPlus className="h-3 w-3" /> Adding
                                </div>
                                <div className="flex items-center gap-1 text-[10px] text-red-400">
                                    <UserMinus className="h-3 w-3" /> Removing
                                </div>
                            </div>
                        )}

                        {/* Filter info */}
                        {selectedUserIds.length > 0 && (
                            <div className="flex items-center gap-2 bg-indigo-500/5 border border-indigo-500/10 rounded-lg px-2.5 py-1">
                                <span className="text-xs text-indigo-400">
                                    {selectedUserIds.length} selected
                                </span>
                                <Button
                                    variant="ghost" size="sm"
                                    className="h-4 text-[10px] text-indigo-400 hover:text-white px-1"
                                    onClick={(e) => { e.stopPropagation(); onSelectUsers?.([]); }}
                                >
                                    Clear
                                </Button>
                            </div>
                        )}

                        {/* Status Legend */}
                        <div className="flex items-center gap-3">
                            {[
                                { label: 'In Progress', color: 'bg-primary' },
                                { label: 'Planning', color: 'bg-amber-500' },
                                { label: 'Reporting', color: 'bg-blue-500' },
                                { label: 'Completed', color: 'bg-green-500' },
                            ].map(item => (
                                <div key={item.label} className="flex items-center gap-1 text-[10px] text-slate-600">
                                    <div className={`w-2 h-2 rounded-sm ${item.color}`} />
                                    <span>{item.label}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        {/* Save assignments button — only when engagement context and changes exist */}
                        {hasAssignmentContext && selectedEngagementId && (
                            <Button
                                variant="outline" size="sm"
                                className={`text-xs gap-1.5 h-8 transition-all ${hasChanges
                                    ? 'border-green-500/30 text-green-400 hover:bg-green-500/10 hover:text-green-300 animate-in fade-in'
                                    : 'border-slate-700 text-slate-500 hover:bg-slate-800'
                                    }`}
                                onClick={handleSaveAssignments}
                                disabled={updateEngagement.isPending}
                            >
                                {updateEngagement.isPending ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                    <Save className="h-3.5 w-3.5" />
                                )}
                                Save Assignments
                            </Button>
                        )}

                        {/* Suggestions — immediate apply + config popover */}
                        <Popover>
                            <PopoverTrigger asChild>
                                <Button
                                    variant="ghost" size="sm"
                                    className="h-8 w-8 p-0 text-slate-500 hover:text-amber-400 hover:bg-amber-500/10"
                                >
                                    <Settings className="h-3.5 w-3.5" />
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent
                                side="top" align="end"
                                className="w-56 bg-slate-900 border-slate-700 p-3 space-y-3"
                            >
                                <div className="text-xs font-semibold text-white flex items-center gap-1.5">
                                    <Sparkles className="h-3 w-3 text-amber-400" />
                                    Suggestion Settings
                                </div>
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-[11px] text-slate-400">Headcount</Label>
                                        <Input
                                            type="number" min={1} max={20}
                                            value={autoAssignCount}
                                            onChange={e => setAutoAssignCount(Number(e.target.value))}
                                            className="h-7 w-16 bg-slate-800 border-slate-700 text-xs text-white"
                                        />
                                    </div>
                                    <label className="flex items-center justify-between cursor-pointer">
                                        <span className="text-[11px] text-slate-400">Free members only</span>
                                        <input
                                            type="checkbox" checked={excludeBusy}
                                            onChange={e => setExcludeBusy(e.target.checked)}
                                            className="rounded border-slate-600 bg-slate-800 text-amber-500 focus:ring-amber-500/20 h-3.5 w-3.5"
                                        />
                                    </label>
                                    <label className="flex items-center justify-between cursor-pointer">
                                        <span className="text-[11px] text-slate-400">Exclude OoO</span>
                                        <input
                                            type="checkbox" checked={excludeOoo}
                                            onChange={e => setExcludeOoo(e.target.checked)}
                                            className="rounded border-slate-600 bg-slate-800 text-red-500 focus:ring-red-500/20 h-3.5 w-3.5"
                                        />
                                    </label>
                                    {excludeOoo && (
                                        <div className="flex items-center justify-between gap-2 pl-3">
                                            <span className="text-[10px] text-slate-500">…if OoO ≥</span>
                                            <div className="flex items-center gap-1.5 flex-1">
                                                <input
                                                    type="range" min={5} max={100} step={5}
                                                    value={oooThreshold}
                                                    onChange={e => setOooThreshold(Number(e.target.value))}
                                                    className="flex-1 h-1 accent-red-500 cursor-pointer"
                                                    title="Only exclude members whose Out-of-Office covers at least this % of the window"
                                                />
                                                <span className="text-[10px] text-slate-400 tabular-nums w-8 text-right">{oooThreshold}%</span>
                                            </div>
                                        </div>
                                    )}
                                    <label className="flex items-center justify-between cursor-pointer">
                                        <span className="text-[11px] text-slate-400">Prioritize skill match</span>
                                        <input
                                            type="checkbox" checked={prioritizeSkills}
                                            onChange={e => setPrioritizeSkills(e.target.checked)}
                                            className="rounded border-slate-600 bg-slate-800 text-emerald-500 focus:ring-emerald-500/20 h-3.5 w-3.5"
                                        />
                                    </label>
                                </div>
                                <p className="text-[10px] text-slate-600">
                                    {prioritizeSkills && engagementSkills.length > 0
                                        ? `Skill match + availability · Top ${autoAssignCount}`
                                        : `${excludeBusy ? 'Only free members' : 'Least busy first'} · Top ${autoAssignCount}`
                                    }
                                </p>
                            </PopoverContent>
                        </Popover>

                        <Button
                            variant="outline" size="sm"
                            className="border-amber-500/20 text-amber-400 hover:bg-amber-500/10 hover:text-amber-300 text-xs gap-1.5 h-8"
                            onClick={applySuggestions}
                        >
                            <Sparkles className="h-3.5 w-3.5" />
                            Suggestions
                        </Button>
                    </div>
                </div>
            </div>
        </TooltipProvider>
    );
}

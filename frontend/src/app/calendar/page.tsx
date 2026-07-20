/**
 * calendar/page.tsx — Ops Calendar Page
 *
 * Monthly calendar showing engagement timelines, custom ops events, and
 * out-of-office (OOO) blocks. Features:
 *  - Grid calendar with days colour-coded by event type (purple =
 *    engagement, blue = ops event, red = OOO).
 *  - Management metric strip: active engagements, team utilisation %
 *    (with progress bar), available operators, and "ending soon" alerts.
 *  - "My Calendar" toggle to filter events to the current user only.
 *  - Team filter badges for multi-user views.
 *  - Inspector sidebar: shows event details, assigned operators / OOO
 *    creator, and a "Go to Engagement" or "Delete Event" action.
 *  - New Event dialog: toggleable EVENT / OOO type with auto-title for
 *    OOO entries.
 *  - Engagement search popover: jumps the calendar to the selected
 *    engagement's start month and opens it in the inspector.
 *  - Live updates via WebSocket (invalidates calendar/engagement queries
 *    on activity_log events).
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
import { Textarea } from '@/components/ui/textarea';
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import {
    ChevronLeft, ChevronRight, Plus, Calendar as CalendarIcon,
    Loader2, Target, Clock, Trash2, Info, Users, Search, Eye,
    UserCheck, AlertTriangle, Activity, TreePalm, GanttChart, LayoutGrid,
} from 'lucide-react';
import { PersonalGanttView } from '@/components/calendar/personal-gantt';
import { DayView } from '@/components/calendar/day-view';
import { WeekView } from '@/components/calendar/week-view';
import { DayEventsPopover } from '@/components/calendar/day-events-popover';
import { cn } from '@/lib/utils';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { toast } from 'sonner';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from "@/components/ui/command";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";

import {
    format, startOfMonth, endOfMonth, startOfWeek, endOfWeek,
    startOfDay, endOfDay,
    eachDayOfInterval, isSameMonth, isSameDay, addMonths, subMonths,
    parseISO, isWithinInterval, isAfter, isBefore, addDays, subDays,
} from 'date-fns';
import { useCalendarFeed, useCreateCalendarEvent, useDeleteCalendarEvent, useTeamAvailability } from '@/lib/hooks/use-calendar';
import { useAuthStore } from '@/stores/auth-store';

// Phase styling — kept consistent with the planning page gantt
// Month cells cap event tiles at this count; overflow rolls into the
// "+N more…" popover. Chosen to match a 120px cell without wrapping.
const MONTH_CAP = 3;

const PHASE_STYLE: Record<string, { label: string; tile: string; sidebar: string }> = {
    SCOPING:     { label: 'Scoping',     tile: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300 border-l-cyan-500',         sidebar: 'bg-cyan-500/20 text-cyan-300' },
    PLANNING:    { label: 'Planning',    tile: 'bg-amber-500/10 border-amber-500/20 text-amber-300 border-l-amber-500',     sidebar: 'bg-amber-500/20 text-amber-300' },
    IN_PROGRESS: { label: 'In Progress', tile: 'bg-purple-500/10 border-purple-500/20 text-purple-300 border-l-purple-500', sidebar: 'bg-purple-500/20 text-purple-300' },
    REPORTING:   { label: 'Reporting',   tile: 'bg-blue-500/10 border-blue-500/20 text-blue-300 border-l-blue-500',         sidebar: 'bg-blue-500/20 text-blue-300' },
};
const ENGAGEMENT_DEFAULT_TILE = 'bg-purple-500/10 border-purple-500/20 text-purple-400 border-l-purple-500';
import { UserAvatar } from '@/components/ui/user-avatar';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { useQueryClient } from '@tanstack/react-query';

export default function CalendarPage() {
    const router = useRouter();
    const { user: currentUser } = useAuthStore();
    const queryClient = useQueryClient();

    // ── Live updates via WebSocket ───────────────────────────────
    useCollaboration({
        resourceType: 'dashboard', resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                queryClient.invalidateQueries({ queryKey: ['calendar-feed'] });
                queryClient.invalidateQueries({ queryKey: ['engagements'] });
                queryClient.invalidateQueries({ queryKey: ['team-availability'] });
            }
        },
    });
    // `currentMonth` is a legacy name kept for the metrics strip that
    // computes on a whole-month window regardless of the active view.
    // `currentDate` is the reference date used for the visible view.
    // On a weekend, default to the upcoming Monday: the week view is Mon–Fri,
    // so a Sat/Sun visit would otherwise land on the just-ended work week and
    // hide anything scheduled for the week ahead (e.g. an OoO starting today).
    const [currentDate, setCurrentDate] = useState(() => {
        const now = new Date();
        const dow = now.getDay(); // 0 = Sun, 6 = Sat
        return dow === 0 ? addDays(now, 1) : dow === 6 ? addDays(now, 2) : now;
    });
    const currentMonth = currentDate;
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [selectedEvent, setSelectedEvent] = useState<any>(null);
    const [filterUserIds, setFilterUserIds] = useState<string[]>([]);
    const [isMyCalendar, setIsMyCalendar] = useState(false);
    const [viewMode, setViewMode] = useState<'day' | 'week' | 'month' | 'gantt'>('week');
    // ISO date of the currently-open "+N more" popover in Month view. Only
    // one popover open at a time; keying on the day string means Popover
    // instances stay stable across the days.map() call.
    const [popoverDayKey, setPopoverDayKey] = useState<string | null>(null);

    // Feed range adapts to the visible view.
    //   day   → single day
    //   week  → Mon-Fri (Work Week)
    //   month → Sun-Sat spanning current month
    //   gantt → 3-month sliding window
    const viewStart = viewMode === 'day'
        ? startOfDay(currentDate)
        : viewMode === 'week'
            ? startOfWeek(currentDate, { weekStartsOn: 1 })
            : viewMode === 'month'
                ? startOfWeek(startOfMonth(currentDate))
                : startOfMonth(subMonths(currentDate, 1));
    const viewEnd = viewMode === 'day'
        ? endOfDay(currentDate)
        : viewMode === 'week'
            ? endOfDay(addDays(startOfWeek(currentDate, { weekStartsOn: 1 }), 4))
            : viewMode === 'month'
                ? endOfWeek(endOfMonth(currentDate))
                : endOfMonth(addMonths(currentDate, 1));

    // Compute effective filter: if "My Calendar" is active, override filter
    const effectiveFilterIds = isMyCalendar && currentUser?.id
        ? [currentUser.id]
        : filterUserIds.length > 0 ? filterUserIds : undefined;

    const { data: feed = [], isLoading } = useCalendarFeed(
        viewStart, viewEnd, effectiveFilterIds
    );
    const { data: allEngagements = [] } = useEngagements();
    const createEvent = useCreateCalendarEvent();
    const deleteEvent = useDeleteCalendarEvent();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const [isSearchOpen, setIsSearchOpen] = useState(false);

    // Team availability for metrics
    const monthStart = startOfMonth(currentMonth);
    const monthEnd = endOfMonth(currentMonth);
    const { data: teamAvailability = [] } = useTeamAvailability(monthStart, monthEnd);

    // Management Metrics
    const metrics = useMemo(() => {
        const now = new Date();
        const soon = addDays(now, 7);

        // Active engagements (in_progress)
        const active = allEngagements.filter(e => e.status === 'in_progress');

        // Engagements ending within 7 days
        const endingSoon = allEngagements.filter(e => {
            if (!e.end_date || e.status === 'completed' || e.status === 'cancelled') return false;
            const end = parseISO(e.end_date);
            return isAfter(end, now) && isBefore(end, soon);
        });

        // Team utilization from availability data
        const totalMembers = teamAvailability.length;
        const busyMembers = teamAvailability.filter(m => m.engagement_count > 0).length;
        const oooMembers = teamAvailability.filter(m => (m.ooo_events?.length || 0) > 0).length;
        const freeMembers = totalMembers - busyMembers - oooMembers + teamAvailability.filter(m => m.engagement_count > 0 && (m.ooo_events?.length || 0) > 0).length;
        const unavailable = new Set([...teamAvailability.filter(m => m.engagement_count > 0).map(m => m.user.id), ...teamAvailability.filter(m => (m.ooo_events?.length || 0) > 0).map(m => m.user.id)]);
        const availableCount = totalMembers - unavailable.size;
        const utilization = totalMembers > 0 ? Math.round((unavailable.size / totalMembers) * 100) : 0;

        // Engagements this month (overlap with current visible month).
        // Proposed engagements can land in the list with a null start_date —
        // treat them as not-yet-scheduled and skip.
        const thisMonthEngs = allEngagements.filter(e => {
            if (e.status === 'completed' || e.status === 'cancelled') return false;
            if (!e.start_date) return false;
            const start = parseISO(e.start_date);
            const end = e.end_date ? parseISO(e.end_date) : addDays(now, 365);
            return isBefore(start, monthEnd) && isAfter(end, monthStart);
        });

        return { active, endingSoon, totalMembers, busyMembers, availableCount, utilization, thisMonthEngs, oooMembers };
    }, [allEngagements, teamAvailability, monthStart, monthEnd]);

    const [newEvent, setNewEvent] = useState({
        title: '',
        description: '',
        start_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
        end_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
        event_type: 'EVENT' as 'EVENT' | 'OOO',
    });

    const days = eachDayOfInterval({ start: viewStart, end: viewEnd });

    // Prev/next step matches the visible view: day → 1 day, week → 7 days,
    // month/gantt → 1 month.
    const nextMonth = () => {
        if (viewMode === 'day') setCurrentDate(addDays(currentDate, 1));
        else if (viewMode === 'week') setCurrentDate(addDays(currentDate, 7));
        else setCurrentDate(addMonths(currentDate, 1));
    };
    const prevMonth = () => {
        if (viewMode === 'day') setCurrentDate(subDays(currentDate, 1));
        else if (viewMode === 'week') setCurrentDate(subDays(currentDate, 7));
        else setCurrentDate(subMonths(currentDate, 1));
    };
    const setCurrentMonth = (d: Date) => setCurrentDate(d);

    // Header label — what the "Month nav" chip in the header says.
    const navLabel = viewMode === 'day'
        ? format(currentDate, 'MMM d, yyyy')
        : viewMode === 'week'
            ? (() => {
                const mon = startOfWeek(currentDate, { weekStartsOn: 1 });
                const fri = addDays(mon, 4);
                return isSameMonth(mon, fri)
                    ? `${format(mon, 'MMM d')} – ${format(fri, 'd, yyyy')}`
                    : `${format(mon, 'MMM d')} – ${format(fri, 'MMM d, yyyy')}`;
            })()
            : format(currentDate, 'MMMM yyyy');

    const handleCreateEvent = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createEvent.mutateAsync(newEvent);
            setIsDialogOpen(false);
            setNewEvent({
                title: '',
                description: '',
                start_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
                end_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
                event_type: 'EVENT',
            });
        } catch (error) {
            console.error('Failed to create event:', error);
            toast.error('Failed to create event');
        }
    };

    const handleDeleteEvent = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Event',
            description: 'Are you sure you want to delete this event?',
        });
        if (!confirmed) return;

        await deleteEvent.mutateAsync(id);
        setSelectedEvent(null);
    };

    const handleToggleMyCalendar = () => {
        setIsMyCalendar(!isMyCalendar);
        if (!isMyCalendar) {
            // When turning on My Calendar, clear team filter
            setFilterUserIds([]);
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-lg">
                            <CalendarIcon className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-white tracking-tight">Calendar</h1>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        {/* View mode: Day | Week | Month | Gantt */}
                        <div className="flex bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                            {([
                                { id: 'day' as const, label: 'Day', icon: CalendarIcon },
                                { id: 'week' as const, label: 'Week', icon: LayoutGrid },
                                { id: 'month' as const, label: 'Month', icon: LayoutGrid },
                                { id: 'gantt' as const, label: 'Gantt', icon: GanttChart },
                            ]).map((mode, i) => (
                                <button
                                    key={mode.id}
                                    onClick={() => setViewMode(mode.id)}
                                    className={cn(
                                        'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors',
                                        i > 0 && 'border-l border-slate-800',
                                        viewMode === mode.id
                                            ? 'bg-primary/15 text-primary'
                                            : 'text-slate-400 hover:text-white',
                                    )}
                                >
                                    <mode.icon className="h-3.5 w-3.5" />
                                    {mode.label}
                                </button>
                            ))}
                        </div>

                        {/* View My Calendar button */}
                        <Button
                            variant={isMyCalendar ? 'default' : 'outline'}
                            size="sm"
                            className={isMyCalendar
                                ? 'bg-primary hover:bg-primary/90 text-white gap-1.5'
                                : 'border-slate-800 bg-slate-900 text-slate-300 hover:text-white gap-1.5'}
                            onClick={handleToggleMyCalendar}
                        >
                            <Eye className="h-3.5 w-3.5" />
                            My Calendar
                        </Button>

                        {/* Team filter badge */}
                        {filterUserIds.length > 0 && !isMyCalendar && (
                            <Badge
                                className="bg-indigo-500/10 text-indigo-400 border-indigo-500/20 gap-1 cursor-pointer hover:bg-indigo-500/20 transition-colors"
                                onClick={() => setFilterUserIds([])}
                            >
                                <Users className="h-3 w-3" />
                                {filterUserIds.length} filtered
                                <span className="ml-1 text-indigo-300">×</span>
                            </Badge>
                        )}

                        {/* Range nav — label + step scales with view */}
                        <div className="flex bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                            <Button variant="ghost" size="icon" onClick={prevMonth} className="text-slate-400 hover:text-white border-r border-slate-800 rounded-none h-9 w-9">
                                <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <button
                                onClick={() => setCurrentDate(new Date())}
                                className="px-4 flex items-center justify-center font-medium text-white min-w-[180px] text-sm hover:bg-slate-800/50 transition-colors"
                                title="Jump to today"
                            >
                                {navLabel}
                            </button>
                            <Button variant="ghost" size="icon" onClick={nextMonth} className="text-slate-400 hover:text-white border-l border-slate-800 rounded-none h-9 w-9">
                                <ChevronRight className="h-4 w-4" />
                            </Button>
                        </div>

                        {/* New Event */}
                        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                            <DialogTrigger asChild>
                                <Button size="sm" className="bg-primary hover:bg-primary/90">
                                    <Plus className="h-4 w-4 mr-2" /> New Event
                                </Button>
                            </DialogTrigger>
                            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[425px]">
                                <form onSubmit={handleCreateEvent}>
                                    <DialogHeader>
                                        <DialogTitle>Create Calendar Event</DialogTitle>
                                    </DialogHeader>
                                    <div className="grid gap-4 py-4">
                                        {/* Event Type Toggle */}
                                        <div className="space-y-2">
                                            <Label>Event Type</Label>
                                            <div className="flex gap-2">
                                                <Button
                                                    type="button"
                                                    size="sm"
                                                    variant={newEvent.event_type === 'EVENT' ? 'default' : 'outline'}
                                                    className={newEvent.event_type === 'EVENT'
                                                        ? 'bg-primary hover:bg-primary/90 text-white flex-1'
                                                        : 'border-slate-700 text-slate-400 hover:text-white flex-1'}
                                                    onClick={() => setNewEvent({ ...newEvent, event_type: 'EVENT', title: newEvent.event_type === 'OOO' ? '' : newEvent.title })}
                                                >
                                                    <Clock className="h-3.5 w-3.5 mr-1.5" />
                                                    Ops Event
                                                </Button>
                                                <Button
                                                    type="button"
                                                    size="sm"
                                                    variant={newEvent.event_type === 'OOO' ? 'default' : 'outline'}
                                                    className={newEvent.event_type === 'OOO'
                                                        ? 'bg-red-600 hover:bg-red-700 text-white flex-1'
                                                        : 'border-slate-700 text-slate-400 hover:text-white flex-1'}
                                                    onClick={() => setNewEvent({ ...newEvent, event_type: 'OOO', title: `${currentUser?.full_name || currentUser?.username || ''} - OoO` })}
                                                >
                                                    <TreePalm className="h-3.5 w-3.5 mr-1.5" />
                                                    Out of Office
                                                </Button>
                                            </div>
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Title</Label>
                                            <Input value={newEvent.title} onChange={e => setNewEvent({ ...newEvent, title: e.target.value })} placeholder={newEvent.event_type === 'OOO' ? 'Out of Office' : 'e.g., Daily Standup'} className="bg-slate-800 border-slate-700" required />
                                        </div>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="space-y-2">
                                                <Label>Start</Label>
                                                <Input type="datetime-local" value={newEvent.start_time} onChange={e => setNewEvent({ ...newEvent, start_time: e.target.value })} className="bg-slate-800 border-slate-700 text-xs" required />
                                            </div>
                                            <div className="space-y-2">
                                                <Label>End</Label>
                                                <Input type="datetime-local" value={newEvent.end_time} onChange={e => setNewEvent({ ...newEvent, end_time: e.target.value })} className="bg-slate-800 border-slate-700 text-xs" required />
                                            </div>
                                        </div>
                                        {newEvent.event_type === 'EVENT' && (
                                            <div className="space-y-2">
                                                <Label>Description</Label>
                                                <Textarea value={newEvent.description} onChange={e => setNewEvent({ ...newEvent, description: e.target.value })} placeholder="Notes..." className="bg-slate-800 border-slate-700" />
                                            </div>
                                        )}
                                    </div>
                                    <DialogFooter>
                                        <Button type="submit" className={newEvent.event_type === 'OOO' ? 'bg-red-600 hover:bg-red-700' : 'bg-primary hover:bg-primary/90'} disabled={createEvent.isPending}>
                                            {newEvent.event_type === 'OOO' ? 'Add OOO' : 'Add Event'}
                                        </Button>
                                    </DialogFooter>
                                </form>
                            </DialogContent>
                        </Dialog>

                        {/* Find Engagement */}
                        <Popover open={isSearchOpen} onOpenChange={setIsSearchOpen}>
                            <PopoverTrigger asChild>
                                <Button
                                    variant="outline" role="combobox"
                                    aria-expanded={isSearchOpen}
                                    className="w-[200px] justify-between border-slate-800 bg-slate-900 text-slate-300 hover:text-white"
                                >
                                    <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
                                    Find Engagement...
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-[300px] p-0 bg-slate-900 border-slate-800">
                                <Command className="bg-slate-900 border-none">
                                    <CommandInput placeholder="Search engagements..." className="text-white bg-slate-900" />
                                    <CommandList>
                                        <CommandEmpty>No engagement found.</CommandEmpty>
                                        <CommandGroup>
                                            {allEngagements.map((eng) => (
                                                <CommandItem
                                                    key={eng.id}
                                                    value={`${eng.name} ${eng.client_name}`}
                                                    onSelect={() => {
                                                        if (eng.start_date) {
                                                            setCurrentMonth(parseISO(eng.start_date));
                                                        }
                                                        setSelectedEvent({
                                                            id: eng.id,
                                                            title: `${eng.name} (${eng.client_name})`,
                                                            description: eng.description,
                                                            start: eng.start_date,
                                                            end: eng.end_date,
                                                            type: 'engagement',
                                                            color: 'purple',
                                                            status: eng.status,
                                                            assigned_users: eng.assigned_users
                                                        });
                                                        setIsSearchOpen(false);
                                                    }}
                                                    className="text-slate-300 hover:text-white hover:bg-slate-800 cursor-pointer p-2 flex flex-col items-start gap-1"
                                                >
                                                    <div className="flex items-center gap-2">
                                                        <Target className="h-3.5 w-3.5 text-purple-400" />
                                                        <span className="font-bold">{eng.name}</span>
                                                    </div>
                                                    <span className="text-[10px] text-slate-500 ml-5">{eng.client_name}</span>
                                                </CommandItem>
                                            ))}
                                        </CommandGroup>
                                    </CommandList>
                                </Command>
                            </PopoverContent>
                        </Popover>
                    </div>
                </div>

                {/* Management Metrics Strip */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    {/* Active Engagements */}
                    <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Active Engagements</p>
                                <p className="text-2xl font-black text-white mt-1">{metrics.active.length}</p>
                                <p className="text-[10px] text-slate-600 mt-0.5">{metrics.thisMonthEngs.length} this month</p>
                            </div>
                            <div className="h-10 w-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                                <Target className="h-5 w-5 text-purple-400" />
                            </div>
                        </div>
                    </div>

                    {/* Team Utilization */}
                    <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Team Utilization</p>
                                <p className="text-2xl font-black text-white mt-1">{metrics.utilization}%</p>
                                <p className="text-[10px] text-slate-600 mt-0.5">{metrics.busyMembers} of {metrics.totalMembers} assigned</p>
                            </div>
                            <div className="h-10 w-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                                <Activity className="h-5 w-5 text-blue-400" />
                            </div>
                        </div>
                        {/* Utilization bar */}
                        <div className="mt-3 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full transition-all duration-500 ${metrics.utilization > 85 ? 'bg-red-500' :
                                    metrics.utilization > 60 ? 'bg-amber-500' : 'bg-blue-500'
                                    }`}
                                style={{ width: `${metrics.utilization}%` }}
                            />
                        </div>
                    </div>

                    {/* Available Operators */}
                    <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Available Operators</p>
                                <p className="text-2xl font-black text-white mt-1">{metrics.availableCount}</p>
                                <p className="text-[10px] text-slate-600 mt-0.5">
                                    {metrics.oooMembers > 0 ? `${metrics.oooMembers} OOO · ` : ''}ready for assignment
                                </p>
                            </div>
                            <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${metrics.availableCount === 0 ? 'bg-red-500/10' : 'bg-green-500/10'
                                }`}>
                                <UserCheck className={`h-5 w-5 ${metrics.availableCount === 0 ? 'text-red-400' : 'text-green-400'
                                    }`} />
                            </div>
                        </div>
                    </div>

                    {/* Ending Soon */}
                    <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Ending Soon</p>
                                <p className="text-2xl font-black text-white mt-1">{metrics.endingSoon.length}</p>
                                <p className="text-[10px] text-slate-600 mt-0.5">within 7 days</p>
                            </div>
                            <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${metrics.endingSoon.length > 0 ? 'bg-amber-500/10' : 'bg-slate-800'
                                }`}>
                                <AlertTriangle className={`h-5 w-5 ${metrics.endingSoon.length > 0 ? 'text-amber-400' : 'text-slate-600'
                                    }`} />
                            </div>
                        </div>
                        {metrics.endingSoon.length > 0 && (
                            <div className="mt-2 space-y-1">
                                {metrics.endingSoon.slice(0, 2).map(e => (
                                    <div key={e.id} className="text-[10px] text-slate-500 truncate">
                                        <span className="text-amber-400/70">•</span> {e.name}
                                        {e.end_date && <span className="text-slate-600"> — {format(parseISO(e.end_date), 'MMM d')}</span>}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                <div className="grid lg:grid-cols-4 gap-6">
                    <div className="lg:col-span-3">
                        <div className="relative">
                            {isLoading && (
                                <div className="absolute inset-0 bg-slate-950/20 backdrop-blur-xs z-10 flex items-center justify-center rounded-lg">
                                    <Loader2 className="h-10 w-10 animate-spin text-blue-500" />
                                </div>
                            )}
                            {viewMode === 'day' && (
                                <DayView
                                    currentDate={currentDate}
                                    feed={feed}
                                    onSelect={setSelectedEvent}
                                    selectedId={selectedEvent?.id ?? null}
                                />
                            )}
                            {viewMode === 'week' && (
                                <WeekView
                                    currentDate={currentDate}
                                    feed={feed}
                                    onSelect={setSelectedEvent}
                                    onJumpToDay={(d) => { setCurrentDate(d); setViewMode('day'); }}
                                />
                            )}
                            {viewMode === 'gantt' && (
                                <PersonalGanttView
                                    currentMonth={currentDate}
                                    feed={feed}
                                    onSelect={setSelectedEvent}
                                    selectedId={selectedEvent?.id ?? null}
                                />
                            )}
                            {viewMode === 'month' && (
                                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
                                    <CardContent className="p-0">
                                        <div className="grid grid-cols-7 border-b border-slate-800 bg-slate-800/30">
                                            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
                                                <div key={day} className="py-2 text-center text-xs font-bold text-slate-500 uppercase tracking-widest">{day}</div>
                                            ))}
                                        </div>
                                        <div className="grid grid-cols-7 border-slate-800 bg-slate-900/30">
                                            {days.map((day) => {
                                                const dayEvents = feed.filter(e => {
                                                    // Feed items can arrive with null start/end for
                                                    // proposed engagements or half-created OOO blocks —
                                                    // skip them instead of blowing up parseISO.
                                                    if (!e.start || !e.end) return false;
                                                    const start = parseISO(e.start.toString());
                                                    const end = parseISO(e.end.toString());
                                                    return isSameDay(start, day) || isWithinInterval(day, { start, end });
                                                });
                                                const shown = dayEvents.slice(0, MONTH_CAP);
                                                const hidden = dayEvents.length - shown.length;
                                                const isToday = isSameDay(day, new Date());
                                                const dayKey = day.toISOString();
                                                const popoverIsOpen = popoverDayKey === dayKey;

                                                return (
                                                    <div key={day.toString()} className={`min-h-[120px] p-2 border-r border-b border-slate-800 transition-colors hover:bg-slate-800/20 ${!isSameMonth(day, currentMonth) ? 'bg-slate-950/40 opacity-30 shadow-inner' : ''}`}>
                                                        <div className="flex justify-between items-start mb-2">
                                                            <button
                                                                onClick={() => { setCurrentDate(day); setViewMode('day'); }}
                                                                title="Jump to day view"
                                                                className={`text-sm font-black transition-transform hover:scale-110 ${isToday ? 'bg-primary text-primary-foreground h-6 w-6 rounded-full flex items-center justify-center shadow-lg shadow-primary/40' : 'text-slate-500 hover:text-white'}`}
                                                            >
                                                                {format(day, 'd')}
                                                            </button>
                                                        </div>
                                                        <div className="space-y-1.5">
                                                            {shown.map(event => {
                                                                const phaseStyle = event.type === 'engagement' && event.phase ? PHASE_STYLE[event.phase] : null;
                                                                const tileClasses = event.type === 'engagement'
                                                                    ? (phaseStyle?.tile ?? ENGAGEMENT_DEFAULT_TILE)
                                                                    : event.type === 'ooo'
                                                                        ? 'bg-red-500/10 border-red-500/20 text-red-400 border-l-red-500'
                                                                        : 'bg-blue-500/10 border-blue-500/20 text-blue-400 border-l-blue-500';
                                                                return (
                                                                    <div
                                                                        key={event.id}
                                                                        onClick={() => setSelectedEvent(event)}
                                                                        title={event.type === 'engagement' && event.phase ? `${event.title} — ${phaseStyle?.label ?? event.phase}` : event.title}
                                                                        className={`text-[10px] p-1.5 rounded-md border cursor-pointer hover:brightness-125 transition-all border-l-[3px] shadow-md ${tileClasses} truncate font-bold flex items-center gap-1.5`}
                                                                    >
                                                                        {event.type === 'engagement' ? <Target className="h-2.5 w-2.5 shrink-0" /> : event.type === 'ooo' ? <TreePalm className="h-2.5 w-2.5 shrink-0" /> : <Clock className="h-2.5 w-2.5 shrink-0" />}
                                                                        <span className="truncate">{event.title}</span>
                                                                        {event.type === 'engagement' && event.phase && phaseStyle && (
                                                                            <span className="ml-auto shrink-0 text-[8px] uppercase tracking-wider opacity-70">{phaseStyle.label}</span>
                                                                        )}
                                                                    </div>
                                                                );
                                                            })}
                                                            {hidden > 0 && (
                                                                <DayEventsPopover
                                                                    open={popoverIsOpen}
                                                                    onOpenChange={o => setPopoverDayKey(o ? dayKey : null)}
                                                                    day={day}
                                                                    events={dayEvents}
                                                                    onSelect={event => {
                                                                        setSelectedEvent(event);
                                                                        setPopoverDayKey(null);
                                                                    }}
                                                                >
                                                                    <button className="w-full text-[10px] text-slate-400 hover:text-white bg-slate-800/40 hover:bg-slate-800 rounded-md py-1 transition-colors">
                                                                        +{hidden} more…
                                                                    </button>
                                                                </DayEventsPopover>
                                                            )}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </CardContent>
                                </Card>
                            )}
                        </div>
                    </div>

                    {/* Inspector Sidebar */}
                    <div className="lg:col-span-1 space-y-4">
                        <Card className="border-slate-800 bg-slate-900 border-l-4 border-l-primary">
                            <CardContent className="p-6">
                                {!selectedEvent ? (
                                    <div className="text-center py-10 space-y-3">
                                        <Info className="h-10 w-10 text-slate-700 mx-auto" />
                                        <p className="text-slate-500 text-sm italic">Select an event to see details</p>
                                    </div>
                                ) : (
                                    <div className="space-y-6">
                                        <div>
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <Badge className={selectedEvent.type === 'engagement' ? 'bg-purple-500/20 text-purple-300' : selectedEvent.type === 'ooo' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'}>
                                                    {selectedEvent.type === 'ooo' ? 'OUT OF OFFICE' : selectedEvent.type.toUpperCase()}
                                                </Badge>
                                                {selectedEvent.type === 'engagement' && selectedEvent.phase && PHASE_STYLE[selectedEvent.phase] && (
                                                    <Badge className={`${PHASE_STYLE[selectedEvent.phase].sidebar} uppercase tracking-wider`}>
                                                        {PHASE_STYLE[selectedEvent.phase].label} phase
                                                    </Badge>
                                                )}
                                            </div>
                                            <h3 className="text-xl font-bold text-white mt-2 leading-tight">{selectedEvent.title}</h3>
                                        </div>

                                        <div className="space-y-3 text-sm">
                                            <div className="flex items-center gap-2 text-slate-400">
                                                <Clock className="h-4 w-4" />
                                                <span>{format(parseISO(selectedEvent.start), 'MMM d, HH:mm')} - {format(parseISO(selectedEvent.end), 'MMM d, HH:mm')}</span>
                                            </div>
                                            {selectedEvent.description && (
                                                <p className="text-slate-400 bg-slate-950 p-3 rounded border border-slate-800 leading-relaxed">
                                                    {selectedEvent.description}
                                                </p>
                                            )}

                                            {selectedEvent.type === 'engagement' && selectedEvent.assigned_users && (
                                                <div className="space-y-3">
                                                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                                                        <Users className="h-3 w-3" />
                                                        Assigned Operators
                                                    </h4>
                                                    <div className="flex flex-wrap gap-2">
                                                        {selectedEvent.assigned_users.length > 0 ? (
                                                            selectedEvent.assigned_users.map((u: any) => (
                                                                <Badge key={u.id} variant="outline" className="border-slate-800 text-[10px] py-1 bg-slate-900/50">
                                                                    {u.full_name || u.username}
                                                                </Badge>
                                                            ))
                                                        ) : (
                                                            <span className="text-xs text-slate-600 italic">No operators assigned</span>
                                                        )}
                                                    </div>
                                                </div>
                                            )}

                                            {/* OOO Creator Info */}
                                            {selectedEvent.type === 'ooo' && selectedEvent.creator && (
                                                <div className="space-y-3">
                                                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                                                        <Users className="h-3 w-3" />
                                                        Operator
                                                    </h4>
                                                    <div className="flex items-center gap-3 p-3 bg-slate-950 rounded-lg border border-slate-800">
                                                        <UserAvatar
                                                            user={{
                                                                id: selectedEvent.creator.id,
                                                                username: selectedEvent.creator.username,
                                                                full_name: selectedEvent.creator.full_name,
                                                                profile_photo: selectedEvent.creator.profile_photo,
                                                            }}
                                                        />
                                                        <div>
                                                            <p className="text-sm font-semibold text-white">
                                                                {selectedEvent.creator.full_name || selectedEvent.creator.username}
                                                            </p>
                                                            <p className="text-[10px] text-slate-500">@{selectedEvent.creator.username}</p>
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>

                                        <div className="pt-4 flex gap-2">
                                            {selectedEvent.type === 'engagement' ? (
                                                <Button onClick={() => router.push(`/engagements/${selectedEvent.engagement_id ?? selectedEvent.id}`)} className="w-full bg-primary hover:bg-primary/90">
                                                    Go to Engagement
                                                </Button>
                                            ) : (
                                                <Button variant="outline" onClick={() => handleDeleteEvent(selectedEvent.id)} className={`w-full ${selectedEvent.type === 'ooo' ? 'border-red-500/20 text-red-500 hover:bg-red-500/10' : 'border-red-500/20 text-red-500 hover:bg-red-500/10'}`}>
                                                    <Trash2 className="h-4 w-4 mr-2" /> Delete {selectedEvent.type === 'ooo' ? 'OOO' : 'Event'}
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Calendar Legend */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardContent className="p-4 space-y-2">
                                <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Legend</h4>
                                <div className="flex items-center gap-3 text-xs text-slate-400">
                                    <div className="w-3 h-3 rounded-full bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.5)]" />
                                    <span>Engagements</span>
                                </div>
                                <div className="flex items-center gap-3 text-xs text-slate-400">
                                    <div className="w-3 h-3 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
                                    <span>Ops Events</span>
                                </div>
                                <div className="flex items-center gap-3 text-xs text-slate-400">
                                    <div className="w-3 h-3 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]" />
                                    <span>Out of Office</span>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </div>
            <ConfirmDialog />
        </DashboardLayout>
    );
}

/**
 * overview-tab.tsx — Engagement Overview Tab
 *
 * Renders the "Overview" tab on the engagement detail page. Displays:
 *  - Stats cards (findings count, test cases, assets, evidence)
 *  - Finding timeline sparkline chart (via Recharts AreaChart)
 *  - Engagement metadata (type, status, scope, dates, client info)
 *  - Team preview with avatar carousel
 *  - Recent activity feed (latest engagement actions)
 *  - Skills radar card (delegated to EngagementSkillsOverviewCard)
 *
 * Props are injected by the parent page.tsx, which acts as the controller
 * for all cross-tab state (edit/delete callbacks, client detail modal, etc).
 */
'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import {
    Target, Bug, CheckSquare, Server, FileText, MessageSquare,
    Edit, Trash2, Users, Calendar, Flag, AlertCircle,
    TrendingUp, Building2, Eye, Clock, Mail, User,
    Activity as ActivityIcon, History as HistoryIcon,
    Upload,
} from 'lucide-react';
import { cn, parseUTCDate } from '@/lib/utils';
import { useFindings } from '@/lib/hooks/use-findings';
import { useFindingsTimeline } from '@/lib/hooks/use-stats';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { useEngagementTypes } from '@/lib/hooks/use-engagement-types';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { ClientEditDialog } from '@/components/clients/client-edit-dialog';
import { CustomFieldsDisplay } from '@/components/custom-fields/custom-fields-display';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { useDeleteEngagement } from '@/lib/hooks/use-engagements';
import { UserAvatar } from '@/components/ui/user-avatar';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { EngagementSkillsOverviewCard } from '@/components/engagements/engagement-skills-overview-card';

import { formatDistanceToNow } from 'date-fns';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
    ResponsiveContainer,
    AreaChart,
    Area,
    Tooltip,
} from 'recharts';

// Types
interface ActivityLog {
    id: string;
    action: string;
    resource_type: string;
    resource_id: string;
    resource_name?: string;
    engagement_id: string;
    user_id: string;
    user_name: string;
    details: string;
    created_at: string;
    finding_id?: string;
}

/** Icon and color mappings for activity log resource types. */
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

/** Builds a client-side route for an activity log entry based on its resource type. */
const getResourceLink = (activity: any) => {
    const type = activity.resource_type?.toLowerCase() || activity.type?.toLowerCase();
    const resourceId = activity.resource_id;
    const engagementId = activity.engagement_id;
    switch (type) {
        case 'engagement': return `/engagements/${resourceId}`;
        case 'finding': return `/findings/${resourceId}?engagementId=${engagementId}`;
        case 'asset': return `/assets/${resourceId}?engagementId=${engagementId}`;
        case 'testcase': return `/testcases/${resourceId}?engagementId=${engagementId}`;
        case 'vault': return `/engagements/${engagementId}?tab=vault`;
        case 'cleanup_artifact': return `/engagements/${engagementId}?tab=cleanup`;
        case 'note': return `/engagements/${engagementId}?tab=notes&noteId=${resourceId}`;
        case 'evidence': return `/engagements/${engagementId}?tab=attachments`;
        case 'comment': return `/findings/${activity.finding_id || resourceId}?engagementId=${engagementId}#discussion`;
        default: return null;
    }
};

/**
 * OverviewTab — Main component for the engagement overview.
 *
 * Fetches its own data (findings, test cases, activity logs, timeline)
 * and renders a dashboard-style layout. Cross-tab actions like edit,
 * delete, and view-client-detail are delegated to the parent via callbacks.
 */
interface OverviewTabProps {
    engagement: any;
    engagementId: string;
    onTabChange: (tab: string) => void;
    onEdit: () => void;
    onDelete: () => void;
    canEditEngagement: boolean;
    canDeleteEngagement: boolean;
    onViewClientDetail?: () => void;
}

const PHASE_LABELS: Record<string, string> = {
    SCOPING: 'Scoping', PLANNING: 'Planning', IN_PROGRESS: 'In Progress', REPORTING: 'Reporting',
};

export function OverviewTab({ engagement, engagementId, onTabChange, onEdit, onDelete, canEditEngagement, canDeleteEngagement, onViewClientDetail }: OverviewTabProps) {
    const router = useRouter();

    const [clientEditOpen, setClientEditOpen] = useState(false);

    // Data hooks
    const findingsParams = useMemo(() => ({ engagement_id: engagementId }), [engagementId]);
    const { data: findings = [] } = useFindings(findingsParams);
    const { data: testcases = [] } = useTestCases(engagementId);
    const { data: timelineData } = useFindingsTimeline({ engagementId, days: 30 });
    const { data: engagementTypes = [] } = useEngagementTypes();

    const typeLabels: Record<string, string> = {};
    engagementTypes.forEach((t: any) => { typeLabels[t.name] = t.description || t.name; });

    const { data: activities = [] } = useQuery({
        queryKey: ['engagement-recent-activity', engagementId],
        queryFn: async () => {
            const response = await api.get<{ items: ActivityLog[]; total: number }>(`/discussions/activity?engagement_id=${engagementId}&limit=5`);
            return response.data?.items ?? response.data ?? [];
        }
    });

    // Stats
    const getDuration = () => {
        if (!engagement?.start_date || !engagement?.end_date) return 'N/A';
        const start = new Date(engagement.start_date);
        const end = new Date(engagement.end_date);
        const days = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
        return `${days} days`;
    };

    const findingStats = {
        critical: findings.filter((f: any) => f.severity === 'CRITICAL').length,
        total: findings.length,
    };

    const testCaseStats = {
        total: testcases.length,
        executed: testcases.filter((tc: any) => tc.is_executed).length,
    };

    return (
        <>
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            {/* Header Actions */}
            <div className="flex items-center justify-between bg-slate-900/40 p-4 rounded-xl border border-slate-800 backdrop-blur-xs">
                <div className="flex items-center gap-4">
                    <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
                        <Target className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                        <h3 className="text-lg font-semibold text-white">Engagement Overview</h3>
                        <p className="text-sm text-slate-400">View and manage engagement metadata</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    {/* Import scanner output pre-scoped to this engagement.
                        Opens the wizard at /imports?engagement=<id>, which
                        pre-fills the target and hides the engagement
                        selector. Any authenticated engagement viewer sees
                        this — the wizard itself enforces write permissions
                        at commit time. */}
                    <Button
                        onClick={() => router.push(`/imports?engagement=${engagementId}`)}
                        variant="outline"
                        className="border-slate-700 bg-slate-800/50 hover:bg-slate-800 text-slate-300"
                    >
                        <Upload className="h-4 w-4 mr-2" />
                        Import
                    </Button>
                    {canEditEngagement && (
                        <Button onClick={onEdit} variant="outline" className="border-slate-700 bg-slate-800/50 hover:bg-slate-800 text-slate-300">
                            <Edit className="h-4 w-4 mr-2" />Edit Engagement
                        </Button>
                    )}
                    {canDeleteEngagement && (
                        <Button onClick={onDelete} variant="outline" className="border-red-500/30 bg-red-500/5 hover:bg-red-500/10 text-red-400">
                            <Trash2 className="h-4 w-4 mr-2" />Delete
                        </Button>
                    )}
                </div>
            </div>

            {/* Top Stats Hub */}
            <div className="grid gap-6 md:grid-cols-4">
                <Card className="border-slate-800 bg-linear-to-br from-slate-900 to-slate-950 shadow-xl overflow-hidden relative">
                    <div className="absolute top-0 right-0 w-24 h-24 bg-red-500/5 rounded-full blur-3xl -mr-12 -mt-12" />
                    <CardHeader className="pb-2">
                        <CardDescription className="flex items-center gap-2"><AlertCircle className="h-3 w-3 text-red-500" />Critical Findings</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-bold text-white">{findingStats.critical}</div>
                        <p className="text-xs text-slate-500 mt-1">Requires immediate attention</p>
                    </CardContent>
                </Card>

                <Card className="border-slate-800 bg-linear-to-br from-slate-900 to-slate-950 shadow-xl overflow-hidden relative">
                    <CardHeader className="pb-0">
                        <div className="flex items-center justify-between">
                            <CardDescription className="flex items-center gap-2"><TrendingUp className="h-3 w-3 text-primary" />Finding Discovery</CardDescription>
                            <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-none">LAST 30 DAYS</Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0 h-[80px] mt-4">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={timelineData?.timeline || []} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#a855f7" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <Area type="monotone" dataKey="count" stroke="#a855f7" fillOpacity={1} fill="url(#colorCount)" strokeWidth={2} isAnimationActive={true} />
                                <Tooltip content={({ active, payload }) => {
                                    if (active && payload && payload.length) {
                                        return (<div className="bg-slate-900 border border-slate-800 p-2 rounded-lg shadow-xl text-xs"><p className="text-slate-400 font-medium">{payload[0].payload.date}</p><p className="text-white font-bold">{payload[0].value} findings</p></div>);
                                    }
                                    return null;
                                }} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                <Card className="border-slate-800 bg-linear-to-br from-slate-900 to-slate-950 shadow-xl overflow-hidden relative">
                    <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 rounded-full blur-3xl -mr-12 -mt-12" />
                    <CardHeader className="pb-2">
                        <CardDescription className="flex items-center gap-2"><CheckSquare className="h-3 w-3 text-blue-500" />Test Progress</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-bold text-white">{testCaseStats.total > 0 ? Math.round((testCaseStats.executed / testCaseStats.total) * 100) : 0}%</div>
                        <div className="w-full bg-slate-800 h-1 mt-3 rounded-full overflow-hidden">
                            <div className="bg-blue-500 h-full rounded-full transition-all duration-500" style={{ width: `${testCaseStats.total > 0 ? (testCaseStats.executed / testCaseStats.total) * 100 : 0}%` }} />
                        </div>
                    </CardContent>
                </Card>

                <Card className="border-slate-800 bg-linear-to-br from-slate-900 to-slate-950 shadow-xl overflow-hidden relative">
                    <div className="absolute top-0 right-0 w-24 h-24 bg-green-500/5 rounded-full blur-3xl -mr-12 -mt-12" />
                    <CardHeader className="pb-2">
                        <CardDescription className="flex items-center gap-2"><Calendar className="h-3 w-3 text-green-500" />Time Remaining</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-bold text-white">{getDuration()}</div>
                        <p className="text-xs text-slate-500 mt-1">Assessment window</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-6 md:grid-cols-3">
                {/* Left Column: Metadata */}
                <div className="md:col-span-1 space-y-6">
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardHeader className="pb-3 border-b border-slate-800/50">
                            <CardTitle className="text-sm font-medium text-slate-400 flex items-center gap-2"><FileText className="h-4 w-4" />Engagement Specs</CardTitle>
                        </CardHeader>
                        <CardContent className="pt-4 space-y-5">
                            <div className="flex items-center justify-between">
                                <span className="text-sm text-slate-500">Assessment Type</span>
                                <span className="text-sm text-white font-medium">{typeLabels[engagement.engagement_type] || engagement.engagement_type}</span>
                            </div>
                            <Separator className="bg-slate-800/50" />
                            <div className="space-y-3">
                                <div className="flex items-center gap-3">
                                    <div className="p-1.5 rounded-md bg-green-500/10"><Calendar className="h-3.5 w-3.5 text-green-500" /></div>
                                    <div><p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Start Date</p><p className="text-sm text-white">{engagement.start_date ? new Date(engagement.start_date).toLocaleDateString(undefined, { dateStyle: 'long' }) : 'N/A'}</p></div>
                                </div>
                                <div className="flex items-center gap-3">
                                    <div className="p-1.5 rounded-md bg-red-500/10"><Calendar className="h-3.5 w-3.5 text-red-500" /></div>
                                    <div><p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">End Date</p><p className="text-sm text-white">{engagement.end_date ? new Date(engagement.end_date).toLocaleDateString(undefined, { dateStyle: 'long' }) : 'N/A'}</p></div>
                                </div>
                            </div>
                            {engagement.phases && engagement.phases.length > 0 && (
                                <>
                                    <Separator className="bg-slate-800/50" />
                                    <div className="space-y-2">
                                        <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Phases</p>
                                        {[...engagement.phases].sort((a, b) => a.sort_order - b.sort_order).map(ph => (
                                            <div key={ph.id} className="flex items-center justify-between gap-2">
                                                <span className="text-sm text-white">{PHASE_LABELS[ph.phase_name] || ph.phase_name}</span>
                                                <span className="text-xs text-slate-400 tabular-nums whitespace-nowrap">
                                                    {ph.planned_start ? new Date(ph.planned_start).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'}
                                                    {' – '}
                                                    {ph.planned_end ? new Date(ph.planned_end).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </CardContent>
                    </Card>

                    {/* Client Information */}
                    {engagement.client_name && (
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-3 border-b border-slate-800/50">
                                <CardTitle className="text-sm font-medium text-slate-400 flex items-center justify-between">
                                    <div className="flex items-center gap-2"><Building2 className="h-4 w-4" />Client Information</div>
                                    {(engagement as any).client && (
                                        <div className="flex items-center gap-1">
                                            {canEditEngagement && (
                                                <Button variant="ghost" size="icon" className="h-6 w-6 text-slate-500 hover:text-white" onClick={() => setClientEditOpen(true)} title="Edit client">
                                                    <Edit className="h-3.5 w-3.5" />
                                                </Button>
                                            )}
                                            <Button variant="ghost" size="icon" className="h-6 w-6 text-slate-500 hover:text-primary" onClick={() => onViewClientDetail?.()} title="View client">
                                                <Eye className="h-3.5 w-3.5" />
                                            </Button>
                                        </div>
                                    )}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-4 space-y-4">
                                <div className={`flex items-center gap-3 ${(engagement as any).client ? 'cursor-pointer group' : ''}`} onClick={() => (engagement as any).client && onViewClientDetail?.()}>
                                    <div className="p-1.5 rounded-md bg-indigo-500/10"><Building2 className="h-3.5 w-3.5 text-indigo-400" /></div>
                                    <div><p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Client</p><p className="text-sm text-white font-medium group-hover:text-primary transition-colors">{engagement.client_name}</p></div>
                                </div>
                                {(engagement as any).client?.client_type && (
                                    <div className="flex items-center gap-3">
                                        <div className="p-1.5 rounded-md bg-primary/10"><Flag className="h-3.5 w-3.5 text-primary" /></div>
                                        <div><p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Type</p>
                                            <Badge className="mt-0.5 text-[10px] font-bold uppercase tracking-wider border" style={{ backgroundColor: `${(engagement as any).client.client_type.color}15`, color: (engagement as any).client.client_type.color, borderColor: `${(engagement as any).client.client_type.color}30` }}>
                                                {(engagement as any).client.client_type.name}
                                            </Badge>
                                        </div>
                                    </div>
                                )}
                                {(engagement as any).client?.description && (
                                    <div className="flex items-start gap-3">
                                        <div className="p-1.5 rounded-md bg-slate-500/10 mt-0.5"><FileText className="h-3.5 w-3.5 text-slate-400" /></div>
                                        <div><p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Description</p><p className="text-sm text-slate-300 leading-relaxed line-clamp-3">{(engagement as any).client.description}</p></div>
                                    </div>
                                )}
                                {(engagement as any).client?.contact_name && (
                                    <div className="flex items-center gap-3">
                                        <div className="p-1.5 rounded-md bg-blue-500/10"><User className="h-3.5 w-3.5 text-blue-400" /></div>
                                        <div><p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Contact</p><p className="text-sm text-white">{(engagement as any).client.contact_name}</p></div>
                                    </div>
                                )}
                                {(engagement as any).client?.contact_email && (
                                    <div className="flex items-center gap-3">
                                        <div className="p-1.5 rounded-md bg-teal-500/10"><Mail className="h-3.5 w-3.5 text-teal-400" /></div>
                                        <div><p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Email</p><a href={`mailto:${(engagement as any).client.contact_email}`} className="text-sm text-teal-400 hover:text-teal-300 transition-colors">{(engagement as any).client.contact_email}</a></div>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}

                    {/* Team Assignments */}
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardHeader className="pb-3 border-b border-slate-800/50">
                            <CardTitle className="text-sm font-medium text-slate-400 flex items-center justify-between">
                                <div className="flex items-center gap-2"><Users className="h-4 w-4" />Team Assignments</div>
                                <Badge variant="outline" className="text-[10px] h-5 bg-slate-800 border-slate-700 text-slate-400">{engagement.assigned_users?.length || 0}</Badge>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-4">
                            {(!engagement.assignment_details || engagement.assignment_details.length === 0) ? (
                                <p className="text-xs text-slate-500 italic text-center py-2">No personnel assigned</p>
                            ) : (
                                <div className="space-y-4">
                                    {engagement.assignment_details.slice(0, 4).map((assignment: any) => {
                                        const u = engagement.assigned_users?.find((user: any) => user.id === assignment.user_id);
                                        const displayName = u?.full_name || u?.username || `User ${assignment.user_id.slice(0, 8)}`;
                                        const initials = u?.full_name ? u.full_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2) : u?.username?.slice(0, 2).toUpperCase() || 'U';
                                        const isLeadRole = assignment.role?.name === 'Engagement Lead' || u?.role === 'admin' || u?.role === 'team_lead';
                                        return (
                                            <div key={assignment.user_id} className="flex items-center gap-3">
                                                <UserAvatar user={u} className="h-8 w-8 border border-slate-700" />
                                                <div className="overflow-hidden">
                                                    <p className="text-sm text-white font-medium truncate">{displayName}</p>
                                                    <p className="text-[11px] text-slate-500 truncate flex items-center gap-1.5">
                                                        {assignment.role?.name || 'Operator'}
                                                        {isLeadRole && <span className="text-amber-500 text-[10px] bg-amber-500/10 px-1 rounded">LEAD</span>}
                                                    </p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                    {(engagement.assignment_details.length > 4) && (
                                        <div className="pt-2 border-t border-slate-800/50 text-center">
                                            <Button variant="link" className="text-xs text-primary h-auto p-0 hover:text-primary/80" onClick={() => onTabChange('team')}>
                                                View {engagement.assignment_details.length - 4} more members
                                            </Button>
                                        </div>
                                    )}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    <EngagementSkillsOverviewCard engagementId={engagement.id} />
                </div>

                {/* Main Content Area */}
                <div className="md:col-span-2 space-y-6">
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs overflow-hidden border-l-4 border-l-primary/40">
                        <CardHeader><CardTitle className="text-lg font-bold text-white">Project Description</CardTitle></CardHeader>
                        <CardContent>
                            {engagement.description
                                ? <MarkdownPreview value={engagement.description} />
                                : <p className="text-slate-400 text-sm italic">No description provided for this engagement.</p>}
                        </CardContent>
                    </Card>

                    <div className="grid gap-6 md:grid-cols-2">
                        <Card className="border-slate-800 bg-slate-900/50 border-t-2 border-t-blue-500/20">
                            <CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-blue-400 uppercase tracking-tight">Scope</CardTitle></CardHeader>
                            <CardContent>
                                {engagement.scope
                                    ? <MarkdownPreview value={engagement.scope} />
                                    : <p className="text-slate-500 text-xs italic">No specific scope defined.</p>}
                            </CardContent>
                        </Card>
                        <Card className="border-slate-800 bg-slate-900/50 border-t-2 border-t-green-500/20">
                            <CardHeader className="pb-2"><CardTitle className="text-sm font-bold text-green-400 uppercase tracking-tight">Objectives</CardTitle></CardHeader>
                            <CardContent>
                                {engagement.objectives
                                    ? <MarkdownPreview value={engagement.objectives} />
                                    : <p className="text-slate-500 text-xs italic">No objectives defined.</p>}
                            </CardContent>
                        </Card>
                    </div>

                    {/* Custom Fields */}
                    <CustomFieldsDisplay entity="engagement" value={engagement.custom_fields} />

                    {/* Tags */}
                    {engagement.tags && engagement.tags.length > 0 && (
                        <Card className="border-slate-800 bg-slate-900/50 border-t-2 border-t-purple-500/20">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-bold text-purple-400 uppercase tracking-tight">Tags</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="flex flex-wrap gap-1.5">
                                    {engagement.tags.map((tag: { id: string; name: string; color: string | null }) => (
                                        <Badge
                                            key={tag.id}
                                            variant="outline"
                                            className="text-[10px] font-medium border py-0.5"
                                            style={{
                                                backgroundColor: tag.color ? `${tag.color}18` : undefined,
                                                borderColor: tag.color ? `${tag.color}40` : undefined,
                                                color: tag.color ?? undefined,
                                            }}
                                        >
                                            <span
                                                className="inline-block w-1.5 h-1.5 rounded-full mr-1.5"
                                                style={{ backgroundColor: tag.color ?? undefined }}
                                            />
                                            {tag.name}
                                        </Badge>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Recent Activity */}
                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-l-4 border-l-blue-500/30">
                        <CardHeader className="pb-3 flex flex-row items-center justify-between">
                            <div>
                                <CardTitle className="text-md font-bold text-white flex items-center gap-2"><ActivityIcon className="h-4 w-4 text-blue-400" />Recent Engagement Activity</CardTitle>
                                <CardDescription>Latest updates for this project</CardDescription>
                            </div>
                            <Button variant="ghost" size="sm" className="h-8 text-[11px] text-slate-500 hover:text-white" onClick={() => onTabChange('logs')}>View All</Button>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                {activities.length > 0 ? activities.map((activity: ActivityLog) => {
                                    const type = activity.resource_type?.toLowerCase();
                                    const Icon = resourceTypeIcons[type] || HistoryIcon;
                                    const link = getResourceLink(activity);
                                    return (
                                        <div key={activity.id} className={cn("flex items-start gap-4 pb-4 border-b border-slate-800/50 last:border-0 last:pb-0 group transition-all duration-200", link && "cursor-pointer hover:bg-slate-800/20 -mx-2 px-2 rounded-lg")} onClick={() => link && router.push(link)}>
                                            <div className={`w-8 h-8 rounded-md flex items-center justify-center border shrink-0 ${resourceTypeColors[type] || 'bg-slate-800 text-slate-400 border-slate-700'}`}><Icon className="h-4 w-4" /></div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between gap-2">
                                                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider truncate">{activity.action?.replace('_', ' ')}</p>
                                                    <span className="flex items-center gap-1 text-[9px] text-slate-600 shrink-0"><Clock className="h-2.5 w-2.5" />{formatDistanceToNow(parseUTCDate(activity.created_at), { addSuffix: true })}</span>
                                                </div>
                                                <p className="text-sm font-medium text-slate-200 group-hover:text-blue-400 transition-colors truncate">{activity.details}</p>
                                                <div className="flex items-center gap-2 mt-1">
                                                    <UserAvatar user={engagement?.assigned_users?.find((u: any) => u.id === activity.user_id)} userId={activity.user_id} username={activity.user_name} className="h-4 w-4" />
                                                    <span className="text-[11px] text-slate-500">{activity.user_name}</span>
                                                    {activity.resource_name && (<><span className="text-slate-700 mx-1">•</span><span className="text-[11px] text-slate-600 truncate italic">{activity.resource_name}</span></>)}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                }) : (
                                    <div className="text-center py-6 border border-dashed border-slate-800 rounded-lg"><p className="text-xs text-slate-500 italic">No recent activity recorded</p></div>
                                )}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
        <ClientEditDialog
            open={clientEditOpen}
            onOpenChange={setClientEditOpen}
            clientId={(engagement as any).client?.id ?? null}
        />
        </>
    );
}

/**
 * engagements/new/page.tsx — Create Engagement Page
 *
 * Mirrors the structure of the edit page (engagements/[id]/edit/page.tsx) so the
 * UX is consistent across create and edit flows:
 *  - Sticky top header with title + unsaved indicator
 *  - Tabbed body (Details / Timeline / Team / Skills) with the same underline tabs
 *  - Sticky bottom action bar with Cancel + Create
 *  - Navigation guard prompts on dirty leave
 *
 * Tabs other than Details show informative placeholders — phases, role-based team
 * assignments, and required skills can only be configured after the engagement
 * is created. The Team tab still allows simple operator assignment at create time.
 */
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { MarkdownEditor } from '@/components/ui/markdown-editor';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    ArrowLeft, Save, Loader2, Users, Radar, CalendarRange, FileText, Info,
} from 'lucide-react';
import { useCreateEngagement } from '@/lib/hooks/use-engagements';
import { useClients } from '@/lib/hooks/use-clients';
import { useEngagementTypes } from '@/lib/hooks/use-engagement-types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { UserAssignmentField } from '@/components/engagements/user-assignment-field';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { useNavigationGuard } from '@/lib/hooks/use-navigation-guard';

const ENGAGEMENT_STATUSES = [
    { value: 'PLANNING',    label: 'Planning'    },
    { value: 'IN_PROGRESS', label: 'In Progress' },
    { value: 'REPORTING',   label: 'Reporting'   },
    { value: 'COMPLETED',   label: 'Completed'   },
    { value: 'ON_HOLD',     label: 'On Hold'     },
];

function SectionDivider({ label }: { label: string }) {
    return (
        <div className="flex items-center gap-3 pt-2">
            <span className="text-[10px] uppercase tracking-widest font-semibold text-slate-500">{label}</span>
            <div className="flex-1 h-px bg-slate-800" />
        </div>
    );
}

const initialForm = {
    name: '',
    client_name: '',
    client_id: '',
    description: '',
    engagement_type: '',
    status: 'PLANNING',
    start_date: '',
    end_date: '',
    scope: '',
    objectives: '',
    assigned_user_ids: [] as string[],
};

export default function NewEngagementPage() {
    const router = useRouter();
    const createEngagement = useCreateEngagement();
    const { data: clients = [] }         = useClients();
    const { data: engagementTypes = [] } = useEngagementTypes();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [formData, setFormData] = useState(initialForm);
    const [detailsDirty, setDetailsDirty] = useState(false);

    const isCreating = createEngagement.isPending;
    const hasUnsaved = detailsDirty;

    const { navigateWithGuard } = useNavigationGuard(hasUnsaved, confirm);

    const handleChange = (field: string, value: any) => {
        setFormData(prev => ({ ...prev, [field]: value }));
        setDetailsDirty(true);
    };

    const handleSubmit = async (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!formData.name || !formData.engagement_type || !formData.start_date) {
            toast.error('Name, type, and start date are required');
            return;
        }
        try {
            const payload = {
                ...formData,
                client_id:  formData.client_id  || undefined,
                start_date: formData.start_date ? `${formData.start_date}T00:00:00` : undefined,
                end_date:   formData.end_date   ? `${formData.end_date}T23:59:59`   : undefined,
            };
            const created: any = await createEngagement.mutateAsync(payload);
            setDetailsDirty(false);
            toast.success('Engagement created');
            // Land on the engagement detail so phases/skills can be configured immediately.
            if (created?.id) router.push(`/engagements/${created.id}`);
            else router.push('/engagements');
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to create engagement');
        }
    };

    const tabBase = 'relative flex items-center gap-2 px-5 py-3 text-sm font-semibold rounded-none bg-transparent text-slate-400 hover:text-slate-200 transition-colors border-b-2 border-transparent';

    return (
        <DashboardLayout>
        <div className="flex flex-col min-h-full">
        <Tabs defaultValue="details" className="flex flex-col flex-1">
            {/* ── Sticky page header + tab list ── */}
            <div className="sticky top-0 z-20 bg-slate-950/90 backdrop-blur-md border-b border-slate-800/50">
                <div className="flex items-center gap-4 px-6 pt-5 pb-3 max-w-7xl">
                    <Button
                        variant="ghost" size="icon"
                        onClick={() => navigateWithGuard('/engagements')}
                        className="text-slate-400 hover:text-white hover:bg-slate-800 shrink-0"
                    >
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div className="min-w-0 flex-1">
                        <h1 className="text-2xl font-bold text-white tracking-tight">New Engagement</h1>
                        <p className="text-slate-400 text-sm mt-0.5 truncate">Define a new security testing engagement</p>
                    </div>
                    {hasUnsaved && (
                        <span className="text-xs text-amber-400 flex items-center gap-1.5 shrink-0">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                            Unsaved changes
                        </span>
                    )}
                </div>
                <TabsList className="flex w-full justify-start bg-transparent border-0 rounded-none p-0 h-auto px-6 gap-0">
                    <TabsTrigger value="details" className={cn(tabBase, 'data-[state=active]:text-primary data-[state=active]:border-primary')}>
                        <FileText className="h-4 w-4" />
                        Details
                        {detailsDirty && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                    </TabsTrigger>
                    <TabsTrigger value="timeline" className={cn(tabBase, 'data-[state=active]:text-teal-400 data-[state=active]:border-teal-400')}>
                        <CalendarRange className="h-4 w-4" />
                        Timeline
                    </TabsTrigger>
                    <TabsTrigger value="team" className={cn(tabBase, 'data-[state=active]:text-indigo-400 data-[state=active]:border-indigo-400')}>
                        <Users className="h-4 w-4" />
                        Team
                    </TabsTrigger>
                    <TabsTrigger value="skills" className={cn(tabBase, 'data-[state=active]:text-pink-400 data-[state=active]:border-pink-400')}>
                        <Radar className="h-4 w-4" />
                        Skills
                    </TabsTrigger>
                </TabsList>
            </div>

            {/* ═══ Tab content ═══ */}
            <div className="px-6 py-6 pb-24 max-w-7xl flex-1">
                <form onSubmit={handleSubmit}>

                {/* ── DETAILS ── */}
                <TabsContent value="details">
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardContent className="pt-6 space-y-6">
                            <SectionDivider label="Identity" />
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="space-y-2">
                                    <Label htmlFor="name" className="text-slate-200 text-sm">
                                        Name <span className="text-red-400">*</span>
                                    </Label>
                                    <Input
                                        id="name" value={formData.name}
                                        onChange={e => handleChange('name', e.target.value)}
                                        placeholder="e.g., Q1 2024 External Pentest"
                                        required className="bg-slate-800/50 border-slate-700 text-white"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="client" className="text-slate-200 text-sm">
                                        Client <span className="text-red-400">*</span>
                                    </Label>
                                    {clients.length > 0 ? (
                                        <Select
                                            value={formData.client_id}
                                            onValueChange={value => {
                                                const selected = clients.find(c => c.id === value);
                                                handleChange('client_id', value);
                                                if (selected) handleChange('client_name', selected.name);
                                            }}
                                        >
                                            <SelectTrigger id="client" className="bg-slate-800/50 border-slate-700 text-white">
                                                <SelectValue placeholder="Select a client" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {clients.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    ) : (
                                        <Input
                                            id="client_name" value={formData.client_name}
                                            onChange={e => handleChange('client_name', e.target.value)}
                                            placeholder="e.g., Acme Corporation"
                                            required
                                            className="bg-slate-800/50 border-slate-700 text-white"
                                        />
                                    )}
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-2">
                                        <Label htmlFor="engagement_type" className="text-slate-200 text-sm">
                                            Type <span className="text-red-400">*</span>
                                        </Label>
                                        <Select
                                            value={formData.engagement_type}
                                            onValueChange={v => handleChange('engagement_type', v)}
                                        >
                                            <SelectTrigger id="engagement_type" className="bg-slate-800/50 border-slate-700 text-white">
                                                <SelectValue placeholder="Type" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {engagementTypes.map(type => (
                                                    <SelectItem key={type.name} value={type.name}>
                                                        {type.description || type.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="status" className="text-slate-200 text-sm">Initial Status</Label>
                                        <Select
                                            value={formData.status}
                                            onValueChange={v => handleChange('status', v)}
                                        >
                                            <SelectTrigger id="status" className="bg-slate-800/50 border-slate-700 text-white">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {ENGAGEMENT_STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </div>

                            <SectionDivider label="Schedule" />
                            <div className="flex flex-wrap items-end gap-4">
                                <div className="space-y-2 w-44">
                                    <Label htmlFor="start_date" className="text-slate-200 text-sm">
                                        Start Date <span className="text-red-400">*</span>
                                    </Label>
                                    <Input id="start_date" type="date" value={formData.start_date}
                                        onChange={e => handleChange('start_date', e.target.value)}
                                        required className="bg-slate-800/50 border-slate-700 text-white" />
                                </div>
                                <div className="space-y-2 w-44">
                                    <Label htmlFor="end_date" className="text-slate-200 text-sm">End Date</Label>
                                    <Input id="end_date" type="date" value={formData.end_date}
                                        onChange={e => handleChange('end_date', e.target.value)}
                                        className="bg-slate-800/50 border-slate-700 text-white" />
                                </div>
                                <div className="flex-1 min-w-[280px] flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-slate-800/30 border border-slate-700/40 mt-1">
                                    <Info className="h-3.5 w-3.5 text-teal-400 mt-0.5 shrink-0" />
                                    <p className="text-xs text-slate-400">
                                        Phases (Scoping → Planning → In Progress → Reporting) will be auto-generated from this date range after creation.
                                    </p>
                                </div>
                            </div>

                            <SectionDivider label="Overview" />
                            <div className="space-y-2">
                                <Label className="text-slate-200 text-sm">Description</Label>
                                <MarkdownEditor id="description" value={formData.description}
                                    onChange={val => handleChange('description', val)}
                                    placeholder="Brief description of the engagement..."
                                    minHeight="130px"
                                    fieldContext={{ resourceType: 'engagement', fieldName: 'Description' }}
                                />
                            </div>

                            <SectionDivider label="Scope" />
                            <div className="space-y-1.5">
                                <p className="text-xs text-slate-500">Systems, networks, and applications included in this engagement</p>
                                <MarkdownEditor id="scope" value={formData.scope}
                                    onChange={val => handleChange('scope', val)}
                                    placeholder="Define what is in scope (IP ranges, domains, apps, exclusions)..."
                                    minHeight="220px"
                                    fieldContext={{ resourceType: 'engagement', fieldName: 'Scope' }}
                                />
                            </div>

                            <SectionDivider label="Objectives" />
                            <div className="space-y-1.5">
                                <p className="text-xs text-slate-500">Goals, success criteria, and deliverables</p>
                                <MarkdownEditor id="objectives" value={formData.objectives}
                                    onChange={val => handleChange('objectives', val)}
                                    placeholder="What are the goals and success criteria for this engagement?"
                                    minHeight="220px"
                                    fieldContext={{ resourceType: 'engagement', fieldName: 'Objectives' }}
                                />
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* ── TIMELINE (placeholder) ── */}
                <TabsContent value="timeline">
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardHeader>
                            <CardTitle className="text-white flex items-center gap-2">
                                <CalendarRange className="h-5 w-5 text-teal-400" /> Phase Timeline
                            </CardTitle>
                            <CardDescription>Phases are auto-generated from your start and end dates after the engagement is created</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex flex-col items-center justify-center py-10 text-center gap-3">
                                <CalendarRange className="h-10 w-10 text-slate-700" />
                                <p className="text-sm text-slate-400 max-w-md">
                                    Once you create this engagement, the Scoping → Planning → In Progress → Reporting phases will be generated automatically based on the date range you set in the <span className="text-teal-400">Details</span> tab. You can fine-tune each phase's start and end dates from the engagement edit page.
                                </p>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* ── TEAM ── */}
                <TabsContent value="team">
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardHeader>
                            <CardTitle className="text-white flex items-center gap-2">
                                <Users className="h-5 w-5 text-indigo-400" /> Assigned Operators
                            </CardTitle>
                            <CardDescription>Operators will see this engagement on their dashboard and calendar</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <UserAssignmentField
                                selectedUserIds={formData.assigned_user_ids}
                                onChange={ids => {
                                    setFormData(prev => ({ ...prev, assigned_user_ids: ids }));
                                    setDetailsDirty(true);
                                }}
                            />
                            <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-slate-800/30 border border-slate-700/40">
                                <Info className="h-3.5 w-3.5 text-indigo-400 mt-0.5 shrink-0" />
                                <p className="text-xs text-slate-400">
                                    You can assign per-engagement <span className="text-indigo-400">roles</span> (Lead, Operator, Reviewer, etc.) from the engagement edit page after creation.
                                </p>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* ── SKILLS (placeholder) ── */}
                <TabsContent value="skills">
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardHeader>
                            <CardTitle className="text-white flex items-center gap-2">
                                <Radar className="h-5 w-5 text-pink-500" /> Required Skills
                            </CardTitle>
                            <CardDescription>Specify the skills operators need for this engagement</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex flex-col items-center justify-center py-10 text-center gap-3">
                                <Radar className="h-10 w-10 text-slate-700" />
                                <p className="text-sm text-slate-400 max-w-md">
                                    Required skills can be configured after the engagement is created. Open the engagement edit page and switch to the <span className="text-pink-400">Skills</span> tab to set the categories, individual skills, and minimum proficiency levels.
                                </p>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                </form>
            </div>{/* end tab content */}

            {/* ── Sticky bottom action bar ── */}
            <div className="sticky bottom-0 z-30 border-t border-slate-800 bg-slate-950/95 backdrop-blur-md">
                <div className="px-6 py-3 flex items-center justify-between gap-4 max-w-7xl">
                    <div className="flex items-center gap-2 text-sm">
                        {hasUnsaved ? (
                            <span className="text-amber-400 flex items-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                                Unsaved changes
                            </span>
                        ) : (
                            <span className="text-slate-500">Fill in the required fields to create</span>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="ghost" size="sm" onClick={() => navigateWithGuard('/engagements')}
                            className="text-slate-400 hover:text-white" disabled={isCreating}>
                            Cancel
                        </Button>
                        <Button size="sm" onClick={() => handleSubmit()} disabled={isCreating}
                            className="bg-primary hover:bg-primary/90 text-white gap-2">
                            {isCreating
                                ? <><Loader2 className="h-4 w-4 animate-spin" /> Creating...</>
                                : <><Save className="h-4 w-4" /> Create Engagement</>}
                        </Button>
                    </div>
                </div>
            </div>

            <ConfirmDialog />
        </Tabs>
        </div>
        </DashboardLayout>
    );
}

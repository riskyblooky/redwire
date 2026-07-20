/**
 * engagements/[id]/edit/page.tsx — Edit Engagement Page
 *
 * Layout:
 *  - Sticky top-0 header (page title + unsaved indicator)
 *  - Sticky top-[72px] tab bar (Details / Timeline / Team / Skills) with underline style
 *  - Normal-flow tab content (scrolls with the page)
 *  - Sticky bottom-0 unified save bar (appears only when details or phases are dirty)
 *  - Skills tab has its own save button (separate API concern)
 */
'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useParams } from '@/lib/hooks/use-params';
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
    ArrowLeft, Save, Loader2, Users, Shield, AlertTriangle,
    CheckCircle2, Plus, Radar, CalendarRange, FileText, Info,
} from 'lucide-react';
import {
    useEngagement, useUpdateEngagement, useUpdateEngagementPhases,
    useGenerateEngagementPhases,
} from '@/lib/hooks/use-engagements';
import type { EngagementPhase } from '@/lib/hooks/use-engagements';
import { useMarkingProfiles } from '@/lib/hooks/use-marking-profiles';
import { ClassificationPicker } from '@/components/marking/classification-picker';
import { useClients } from '@/lib/hooks/use-clients';
import { useEngagementTypes } from '@/lib/hooks/use-engagement-types';
import { TeamManagementDialog } from '@/components/engagements/team-management-dialog';
import { TagPickerField } from '@/components/engagements/tag-picker-field';
import { CustomFieldsForm } from '@/components/custom-fields/custom-fields-form';
import { UserAvatar } from '@/components/ui/user-avatar';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { format, parseISO, differenceInDays, isAfter } from 'date-fns';
import { useSkillCategories, useEngagementSkills, useSetEngagementSkills, SKILL_LEVELS } from '@/lib/hooks/use-skills';
import { useCanEdit } from '@/lib/hooks/use-permissions';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { useNavigationGuard } from '@/lib/hooks/use-navigation-guard';
import { apiErrorMessage } from '@/lib/api';

// ── Phase colors ────────────────────────────────────────────────────
const PHASE_COLORS: Record<string, { bg: string; text: string; label: string }> = {
    SCOPING:     { bg: 'bg-cyan-500',   text: 'text-cyan-400',   label: 'Scoping'     },
    PLANNING:    { bg: 'bg-amber-500',  text: 'text-amber-400',  label: 'Planning'    },
    IN_PROGRESS: { bg: 'bg-primary', text: 'text-primary', label: 'In Progress' },
    REPORTING:   { bg: 'bg-blue-500',   text: 'text-blue-400',   label: 'Reporting'   },
};

const STATUS_PHASE_INDEX: Record<string, number> = {
    PROPOSED: -1, PLANNING: 0, SCOPING: 1, IN_PROGRESS: 2, REPORTING: 3, COMPLETED: 4, ON_HOLD: -1,
};

function getPhaseHealth(phase: EngagementPhase, engagementStatus: string): 'on-time' | 'late' | 'completed' | 'future' {
    const now       = new Date();
    const phaseIdx  = STATUS_PHASE_INDEX[phase.phase_name] ?? -1;
    const statusIdx = STATUS_PHASE_INDEX[engagementStatus]  ?? -1;
    if (statusIdx > phaseIdx)  return 'completed';
    if (!phase.planned_end)    return 'future';
    const plannedEnd = parseISO(phase.planned_end);
    if (statusIdx <= phaseIdx && isAfter(now, plannedEnd)) return 'late';
    if (statusIdx  < phaseIdx) return 'future';
    return 'on-time';
}

const ENGAGEMENT_STATUSES = [
    { value: 'PLANNING',    label: 'Planning'    },
    { value: 'SCOPING',     label: 'Scoping'     },
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

// ── Underline-style tab trigger ─────────────────────────────────────
function UlTabTrigger({ value, activeColor, dotted, children }: {
    value: string; activeColor: string; dotted?: boolean; children: React.ReactNode;
}) {
    return (
        <TabsTrigger
            value={value}
            className={cn(
                'relative flex items-center gap-2 px-5 py-3 text-sm font-semibold rounded-none',
                'text-slate-400 hover:text-slate-200 transition-colors bg-transparent',
                'data-[state=active]:bg-transparent',
                `data-[state=active]:${activeColor}`,
                'after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5',
                'after:bg-transparent data-[state=active]:after:bg-current',
                'after:transition-all after:rounded-full'
            )}
        >
            {children}
            {dotted && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />}
        </TabsTrigger>
    );
}

// ══════════════════════════════════════════════════════════════════
export default function EditEngagementPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const fromPlanning = searchParams?.get('from') === 'planning';
    const returnUrl = fromPlanning ? '/planning' : `/engagements/${id}`;

    const { data: engagement, isLoading } = useEngagement(id);
    const updateEngagement  = useUpdateEngagement();
    const updatePhases      = useUpdateEngagementPhases();
    const generatePhases    = useGenerateEngagementPhases();
    const { data: clients = [] }         = useClients();
    const { data: engagementTypes = [] } = useEngagementTypes();
    const canEdit = useCanEdit(id, 'engagement' as any, engagement?.created_by);
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [formData, setFormData] = useState({
        name: '', client_name: '', client_id: '', description: '',
        // NOTE: keep raw value — do NOT toUpperCase, must match API type.name
        engagement_type: '',
        status: 'PLANNING',
        start_date: '', end_date: '', scope: '', objectives: '',
        marking_profile_id: '', default_classification_level: '',
        default_classification_suffix: '', ceiling_classification_level: '',
        tag_ids: [] as string[],
        custom_fields: {} as Record<string, unknown>,
    });
    const [detailsDirty, setDetailsDirty] = useState(false);
    const [isTeamDialogOpen, setIsTeamDialogOpen] = useState(false);
    const [editingPhases, setEditingPhases] = useState<Record<string, { start: string; end: string }>>({});
    const [phasesEdited, setPhasesEdited] = useState(false);
    const [skillsDirty, setSkillsDirty] = useState(false);
    const skillsSaveRef = useRef<(() => Promise<void>) | null>(null);
    const { data: markingProfiles = [] } = useMarkingProfiles();
    const activeMarkingProfile = markingProfiles.find(p => p.id === formData.marking_profile_id);

    const isSaving   = updateEngagement.isPending || updatePhases.isPending;
    const hasUnsaved = detailsDirty || phasesEdited || skillsDirty;

    const { navigateWithGuard } = useNavigationGuard(hasUnsaved, confirm);

    // Permission guard
    useEffect(() => {
        if (!isLoading && engagement && !canEdit) {
            toast.error('You do not have permission to edit this engagement');
            router.replace(`/engagements/${id}`);
        }
    }, [engagement, canEdit, isLoading, router, id]);

    // Normalize a stored engagement_type string against the loaded types list
    // (handles old SCREAMING_SNAKE_CASE values like RED_TEAM vs current "Red Team")
    const normalizeType = (raw: string, types: { name: string }[]) => {
        if (!raw || !types.length) return raw;
        const normalize = (s: string) => s.toLowerCase().replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
        const match = types.find(t => normalize(t.name) === normalize(raw));
        return match ? match.name : raw;
    };

    // Populate form from engagement data
    useEffect(() => {
        if (engagement) {
            const rawType = (engagement.engagement_type as string) || '';
            setFormData({
                name:            engagement.name || '',
                client_name:     engagement.client_name || '',
                client_id:       engagement.client_id || '',
                description:     engagement.description || '',
                engagement_type: normalizeType(rawType, engagementTypes),
                status:          (engagement.status as string)?.toUpperCase().trim() || 'PLANNING',
                start_date:      engagement.start_date ? engagement.start_date.split('T')[0] : '',
                end_date:        engagement.end_date   ? engagement.end_date.split('T')[0]   : '',
                scope:           engagement.scope      || '',
                objectives:      engagement.objectives || '',
                marking_profile_id:            engagement.marking_profile_id || '',
                default_classification_level:  engagement.default_classification_level || '',
                default_classification_suffix: engagement.default_classification_suffix || '',
                ceiling_classification_level:  engagement.ceiling_classification_level || '',
                tag_ids:                       (engagement.tags || []).map(t => t.id),
                custom_fields:                 (engagement.custom_fields as Record<string, unknown>) || {},
            });
            setDetailsDirty(false);
        }
    }, [engagement, engagementTypes]);

    // Re-normalize type when types load AFTER engagement (async race)
    useEffect(() => {
        if (engagement && engagementTypes.length > 0) {
            setFormData(prev => ({
                ...prev,
                engagement_type: normalizeType((engagement.engagement_type as string) || '', engagementTypes),
            }));
        }
    }, [engagementTypes]);

    // Init phase editors
    useEffect(() => {
        if (engagement?.phases?.length) {
            const edits: Record<string, { start: string; end: string }> = {};
            for (const p of engagement.phases) {
                edits[p.id] = {
                    start: p.planned_start ? format(parseISO(p.planned_start), 'yyyy-MM-dd') : '',
                    end:   p.planned_end   ? format(parseISO(p.planned_end),   'yyyy-MM-dd') : '',
                };
            }
            setEditingPhases(edits);
            setPhasesEdited(false);
        }
    }, [engagement?.id, engagement?.phases]);

    if (isLoading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    if (!canEdit || !engagement) return null;

    const handleChange = (field: string, value: any) => {
        setFormData(prev => ({ ...prev, [field]: value }));
        setDetailsDirty(true);
    };

    const handlePhaseChange = (phaseId: string, field: 'start' | 'end', value: string) => {
        setEditingPhases(prev => ({ ...prev, [phaseId]: { ...prev[phaseId], [field]: value } }));
        setPhasesEdited(true);
    };

    // ── Unified save ──────────────────────────────────────────────
    const handleSaveAll = async () => {
        const saves: Promise<any>[] = [];

        if (detailsDirty) {
            saves.push(updateEngagement.mutateAsync({
                id,
                ...formData,
                client_id:  formData.client_id  || undefined,
                start_date: formData.start_date ? `${formData.start_date}T00:00:00` : undefined,
                end_date:   formData.end_date   ? `${formData.end_date}T23:59:59`   : undefined,
                marking_profile_id:            formData.marking_profile_id || null,
                default_classification_level:  formData.default_classification_level || null,
                default_classification_suffix: formData.default_classification_suffix || null,
                ceiling_classification_level:  formData.ceiling_classification_level || null,
            }));
        }

        if (phasesEdited) {
            const updates = Object.entries(editingPhases)
                .map(([pid, dates]) => ({
                    id: pid,
                    planned_start: dates.start ? new Date(dates.start).toISOString() : undefined,
                    planned_end:   dates.end   ? new Date(dates.end).toISOString()   : undefined,
                }))
                .filter(p => p.planned_start || p.planned_end);
            if (updates.length > 0) {
                saves.push(updatePhases.mutateAsync({ engagementId: engagement.id, phases: updates }));
            }
        }

        if (skillsDirty && skillsSaveRef.current) {
            saves.push(skillsSaveRef.current());
        }

        if (saves.length === 0) return;

        try {
            await Promise.all(saves);
            toast.success('Changes saved');
            setDetailsDirty(false);
            setPhasesEdited(false);
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to save changes'));
        }
    };

    const handleSaveAndBack = async () => {
        await handleSaveAll();
        router.push(returnUrl);
    };

    // ── Underline tab classes ─────────────────────────────────────
    const tabBase = 'relative flex items-center gap-2 px-5 py-3 text-sm font-semibold rounded-none bg-transparent text-slate-400 hover:text-slate-200 transition-colors border-b-2 border-transparent';
    const tabActive = (color: string) => `${tabBase} data-[state=active]:${color} data-[state=active]:border-current`;

    return (
        <DashboardLayout>
        <div className="flex flex-col min-h-full">
        <Tabs defaultValue="details" className="flex flex-col flex-1">
            {/* ── Sticky: page header + tab list ONLY ── */}
            <div className="sticky top-0 z-20 bg-slate-950/90 backdrop-blur-md border-b border-slate-800/50">
                <div className="flex items-center gap-4 px-6 pt-5 pb-3 max-w-7xl">
                    <Button
                        variant="ghost" size="icon"
                        onClick={() => navigateWithGuard(returnUrl)}
                        className="text-slate-400 hover:text-white hover:bg-slate-800 shrink-0"
                    >
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div className="min-w-0 flex-1">
                        <h1 className="text-2xl font-bold text-white tracking-tight">Edit Engagement</h1>
                        <p className="text-slate-400 text-sm mt-0.5 truncate">{engagement.name}</p>
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
                        {phasesEdited && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                    </TabsTrigger>
                    <TabsTrigger value="team" className={cn(tabBase, 'data-[state=active]:text-indigo-400 data-[state=active]:border-indigo-400')}>
                        <Users className="h-4 w-4" />
                        Team
                    </TabsTrigger>
                    <TabsTrigger value="skills" className={cn(tabBase, 'data-[state=active]:text-pink-400 data-[state=active]:border-pink-400')}>
                        <Radar className="h-4 w-4" />
                        Skills
                        {skillsDirty && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                    </TabsTrigger>
                </TabsList>
            </div>

            {/* ═══ Tab content — normal flow, scrolls naturally ═══ */}
            <div className="px-6 py-6 pb-24 max-w-7xl flex-1">

                        {/* ── DETAILS ── */}
                        <TabsContent value="details">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardContent className="pt-6 space-y-6">
                                    <SectionDivider label="Identity" />
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div className="space-y-2">
                                            <Label htmlFor="name" className="text-slate-200 text-sm">Name <span className="text-red-400">*</span></Label>
                                            <Input
                                                id="name" value={formData.name}
                                                onChange={e => handleChange('name', e.target.value)}
                                                placeholder="e.g., Q1 2024 External Pentest"
                                                required className="bg-slate-800/50 border-slate-700 text-white"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="client" className="text-slate-200 text-sm">Client <span className="text-red-400">*</span></Label>
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
                                                    className="bg-slate-800/50 border-slate-700 text-white"
                                                />
                                            )}
                                        </div>
                                        <div className="grid grid-cols-2 gap-3">
                                            <div className="space-y-2">
                                                <Label htmlFor="engagement_type" className="text-slate-200 text-sm">Type <span className="text-red-400">*</span></Label>
                                                <Select
                                                    key={`type-${engagement.id}-${formData.engagement_type}-${engagementTypes.length}`}
                                                    value={formData.engagement_type}
                                                    onValueChange={v => handleChange('engagement_type', v)}
                                                >
                                                    <SelectTrigger id="engagement_type" className="bg-slate-800/50 border-slate-700 text-white">
                                                        <SelectValue placeholder="Type" />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {engagementTypes.map(type => (
                                                            <SelectItem key={type.name} value={type.name}>{type.description || type.name}</SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div className="space-y-2">
                                                <Label htmlFor="status" className="text-slate-200 text-sm">Status</Label>
                                                <Select
                                                    key={`status-${engagement.id}`}
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
                                            <Label htmlFor="start_date" className="text-slate-200 text-sm">Start Date <span className="text-red-400">*</span></Label>
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

                                    <SectionDivider label="Tags" />
                                    <TagPickerField
                                        selected={formData.tag_ids}
                                        onChange={ids => {
                                            setFormData(prev => ({ ...prev, tag_ids: ids }));
                                            setDetailsDirty(true);
                                        }}
                                    />

                                    <CustomFieldsForm
                                        entity="engagement"
                                        value={formData.custom_fields}
                                        onChange={(cf) => { setFormData(prev => ({ ...prev, custom_fields: cf })); setDetailsDirty(true); }}
                                    />

                                    <SectionDivider label="Classification Marking" />
                                    <div className="space-y-4">
                                        <p className="text-xs text-slate-500">
                                            Portion-marking policy for generated reports. The <span className="text-slate-400">default</span> is
                                            inherited by any unmarked item; the <span className="text-slate-400">ceiling</span> caps the level any
                                            item may be set to. The page banner is computed from the highest mark present.
                                        </p>
                                        <div className="space-y-1.5">
                                            <Label className="text-slate-300">Marking profile</Label>
                                            <Select
                                                value={formData.marking_profile_id || '_none'}
                                                onValueChange={v => handleChange('marking_profile_id', v === '_none' ? '' : v)}
                                            >
                                                <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white">
                                                    <SelectValue placeholder="No marking" />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                    <SelectItem value="_none">No marking</SelectItem>
                                                    {markingProfiles.map(p => (
                                                        <SelectItem key={p.id} value={p.id}>{p.name}{p.is_builtin ? ' (built-in)' : ''}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        {activeMarkingProfile && (
                                            <>
                                                <div className="space-y-1.5">
                                                    <Label className="text-slate-300">Default classification</Label>
                                                    <ClassificationPicker
                                                        levels={activeMarkingProfile.levels}
                                                        level={formData.default_classification_level || null}
                                                        suffix={formData.default_classification_suffix || null}
                                                        inheritLabel="None (no marking)"
                                                        onChange={(lvl, suf) => {
                                                            handleChange('default_classification_level', lvl || '');
                                                            handleChange('default_classification_suffix', suf || '');
                                                        }}
                                                    />
                                                </div>
                                                <div className="space-y-1.5">
                                                    <Label className="text-slate-300">Ceiling (max any item may be marked)</Label>
                                                    <ClassificationPicker
                                                        levels={activeMarkingProfile.levels}
                                                        level={formData.ceiling_classification_level || null}
                                                        showSuffix={false}
                                                        inheritLabel="No ceiling"
                                                        onChange={(lvl) => handleChange('ceiling_classification_level', lvl || '')}
                                                    />
                                                </div>
                                            </>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* ── TIMELINE ── */}
                        <TabsContent value="timeline">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader>
                                    <CardTitle className="text-white flex items-center gap-2">
                                        <CalendarRange className="h-5 w-5 text-teal-400" /> Phase Timeline
                                    </CardTitle>
                                    <CardDescription>Set the planned start and end date for each phase</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-5">
                                    {engagement.status === 'PROPOSED' ? (
                                        <div className="flex items-start gap-3 p-4 rounded-xl border border-slate-700/50 bg-slate-900/20 text-slate-400">
                                            <Info className="h-4 w-4 text-teal-400 mt-0.5 shrink-0" />
                                            <p className="text-sm">Phases will be auto-created when this engagement is promoted from Proposed to Planning.</p>
                                        </div>
                                    ) : engagement.phases?.length > 0 ? (
                                        <>
                                            {engagement.start_date && engagement.end_date && (
                                                <div className="relative h-8 rounded-lg bg-slate-800/50 border border-slate-700/50 overflow-hidden">
                                                    {engagement.phases.map((phase: EngagementPhase) => {
                                                        if (!phase.planned_start || !phase.planned_end) return null;
                                                        const engStart  = parseISO(engagement.start_date);
                                                        const engEnd    = parseISO(engagement.end_date!);
                                                        const totalDays = Math.max(differenceInDays(engEnd, engStart), 1);
                                                        const pStart    = parseISO(phase.planned_start);
                                                        const pEnd      = parseISO(phase.planned_end);
                                                        const leftPct   = Math.max(0, (differenceInDays(pStart, engStart) / totalDays) * 100);
                                                        const widthPct  = Math.max(1, (differenceInDays(pEnd, pStart) / totalDays) * 100);
                                                        const color     = PHASE_COLORS[phase.phase_name];
                                                        const health    = getPhaseHealth(phase, engagement.status);
                                                        if (!color) return null;
                                                        return (
                                                            <div
                                                                key={phase.id}
                                                                className={cn(
                                                                    'absolute top-1 bottom-1 rounded-sm transition-all', color.bg,
                                                                    health === 'late'      ? 'opacity-90 ring-1 ring-red-500/60' :
                                                                    health === 'completed' ? 'opacity-30' :
                                                                    health === 'on-time'   ? 'opacity-70' : 'opacity-40',
                                                                )}
                                                                style={{ left: `${leftPct}%`, width: `${widthPct}%`, minWidth: '4px' }}
                                                                title={`${color.label}: ${format(pStart, 'MMM d')} – ${format(pEnd, 'MMM d')}`}
                                                            />
                                                        );
                                                    })}
                                                </div>
                                            )}
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                {engagement.phases.map((phase: EngagementPhase) => {
                                                    const color   = PHASE_COLORS[phase.phase_name];
                                                    const health  = getPhaseHealth(phase, engagement.status);
                                                    const editing = editingPhases[phase.id];
                                                    return (
                                                        <div key={phase.id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                                                            <div className="flex items-center justify-between mb-3">
                                                                <div className="flex items-center gap-2">
                                                                    <div className={cn('w-2.5 h-2.5 rounded-full', color?.bg || 'bg-slate-500')} />
                                                                    <span className="text-sm font-semibold text-white">{color?.label || phase.phase_name}</span>
                                                                </div>
                                                                <div>
                                                                    {health === 'late'      && <Badge className="text-[10px] border-red-500/40 text-red-400 bg-red-500/10 gap-1"><AlertTriangle className="h-3 w-3" /> Late</Badge>}
                                                                    {health === 'on-time'   && <Badge className="text-[10px] border-green-500/40 text-green-400 bg-green-500/10">On Time</Badge>}
                                                                    {health === 'completed' && <Badge className="text-[10px] border-green-500/40 text-green-400 bg-green-500/10 gap-1"><CheckCircle2 className="h-3 w-3" /> Completed</Badge>}
                                                                    {health === 'future'    && <Badge className="text-[10px] border-slate-600 text-slate-500 bg-slate-800">Upcoming</Badge>}
                                                                </div>
                                                            </div>
                                                            <div className="grid grid-cols-2 gap-3">
                                                                <div className="space-y-1">
                                                                    <Label className="text-xs text-slate-500 uppercase tracking-wider">Start</Label>
                                                                    <Input type="date" value={editing?.start || ''}
                                                                        onChange={e => handlePhaseChange(phase.id, 'start', e.target.value)}
                                                                        className="bg-slate-800/50 border-slate-700 text-white text-sm h-9" />
                                                                </div>
                                                                <div className="space-y-1">
                                                                    <Label className="text-xs text-slate-500 uppercase tracking-wider">End</Label>
                                                                    <Input type="date" value={editing?.end || ''}
                                                                        onChange={e => handlePhaseChange(phase.id, 'end', e.target.value)}
                                                                        className="bg-slate-800/50 border-slate-700 text-white text-sm h-9" />
                                                                </div>
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </>
                                    ) : (
                                        <div className="flex flex-col items-center justify-center py-12 text-center gap-3">
                                            <CalendarRange className="h-10 w-10 text-slate-700" />
                                            <p className="text-sm text-slate-500 italic">No phases configured yet.</p>
                                            <Button
                                                onClick={async () => {
                                                    try {
                                                        await generatePhases.mutateAsync(engagement.id);
                                                        toast.success('Phases generated!');
                                                    } catch (error: any) {
                                                        toast.error(apiErrorMessage(error, 'Failed to generate phases'));
                                                    }
                                                }}
                                                disabled={generatePhases.isPending}
                                                className="bg-teal-600 hover:bg-teal-500 text-white gap-2 mt-1" size="sm"
                                            >
                                                {generatePhases.isPending
                                                    ? <><Loader2 className="h-4 w-4 animate-spin" /> Generating...</>
                                                    : <><Plus className="h-4 w-4" /> Generate Phases</>}
                                            </Button>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* ── TEAM ── */}
                        <TabsContent value="team">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader>
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <CardTitle className="text-white flex items-center gap-2">
                                                <Users className="h-5 w-5 text-indigo-400" /> Assigned Personnel
                                            </CardTitle>
                                            <CardDescription>Operators and their roles on this engagement</CardDescription>
                                        </div>
                                        <Button type="button" variant="outline" size="sm"
                                            onClick={() => setIsTeamDialogOpen(true)}
                                            className="border-indigo-500/30 bg-indigo-500/10 text-indigo-400 hover:bg-primary/90/20 gap-2">
                                            <Users className="h-4 w-4" /> Manage Team
                                        </Button>
                                    </div>
                                </CardHeader>
                                <CardContent>
                                    {engagement.assignment_details?.length > 0 ? (
                                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                                            {engagement.assignment_details.map((assignment: any, idx: number) => {
                                                const user = engagement.assigned_users?.find((u: any) => u.id === assignment.user_id);
                                                return (
                                                    <div key={idx} className="flex items-center gap-3 p-3 rounded-xl border border-slate-800 bg-slate-950/50 hover:border-indigo-500/30 transition-all">
                                                        <UserAvatar
                                                            user={user ? { id: user.id, username: user.username, full_name: user.full_name, profile_photo: user.profile_photo } : undefined}
                                                            userId={assignment.user_id}
                                                            username={user?.username}
                                                            className="h-9 w-9 shrink-0 ring-1 ring-indigo-500/20"
                                                        />
                                                        <div className="min-w-0">
                                                            <p className="text-sm font-semibold text-white truncate">{user?.full_name || user?.username || 'Unknown'}</p>
                                                            {assignment.role && <p className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">{assignment.role.name}</p>}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    ) : (
                                        <div className="flex flex-col items-center justify-center py-14 text-center gap-3">
                                            <Shield className="h-10 w-10 text-slate-700" />
                                            <p className="text-sm text-slate-500 italic">No personnel assigned.</p>
                                            <Button type="button" variant="outline" size="sm"
                                                onClick={() => setIsTeamDialogOpen(true)}
                                                className="border-indigo-500/30 bg-indigo-500/10 text-indigo-400 hover:bg-primary/90/20 gap-2 mt-1">
                                                <Users className="h-4 w-4" /> Add Team Members
                                            </Button>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* ── SKILLS ── */}
                        <TabsContent value="skills">
                            <RequiredSkillsCard
                                engagementId={engagement.id}
                                onDirtyChange={setSkillsDirty}
                                saveRef={skillsSaveRef}
                            />
                        </TabsContent>

                    </div>{/* end tab content */}

            {/* ── Sticky save bar ── */}
            <div className={cn(
                'sticky bottom-0 z-30 border-t transition-all duration-200',
                hasUnsaved
                    ? 'border-amber-500/30 bg-slate-950/95 backdrop-blur-md'
                    : 'h-0 overflow-hidden border-transparent opacity-0 pointer-events-none'
            )}>
                <div className="px-6 py-3 flex items-center justify-between gap-4 max-w-7xl">
                    <div className="flex items-center gap-2 text-sm text-amber-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                        <span>
                            {[detailsDirty && 'Details', phasesEdited && 'Timeline', skillsDirty && 'Skills'].filter(Boolean).join(' + ')} has unsaved changes
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="ghost" size="sm" onClick={() => navigateWithGuard(returnUrl)}
                            className="text-slate-400 hover:text-white">
                            Discard
                        </Button>
                        <Button size="sm" onClick={handleSaveAll} disabled={isSaving}
                            className="bg-primary hover:bg-primary/90 text-white gap-2">
                            {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                            Save Changes
                        </Button>
                        <Button size="sm" onClick={handleSaveAndBack} disabled={isSaving}
                            variant="outline" className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-2">
                            Save &amp; Close
                        </Button>
                    </div>
                </div>
            </div>

            {/* Team dialog */}
            <TeamManagementDialog
                engagement={engagement as any}
                open={isTeamDialogOpen}
                onOpenChange={setIsTeamDialogOpen}
            />
          <ConfirmDialog />
        </Tabs>
        </div>
        </DashboardLayout>
    );
}


// ═══════════════════════════════════════════════════════════════════
//  REQUIRED SKILLS CARD
// ═══════════════════════════════════════════════════════════════════

function RequiredSkillsCard({ engagementId, onDirtyChange, saveRef }: {
    engagementId: string;
    onDirtyChange?: (dirty: boolean) => void;
    saveRef?: React.MutableRefObject<(() => Promise<void>) | null>;
}) {
    const { data: categories = [] }       = useSkillCategories();
    const { data: engagementSkills = [] } = useEngagementSkills(engagementId);
    const setEngagementSkills             = useSetEngagementSkills();

    const [localSkills, setLocalSkills] = useState<Record<string, number>>({});
    const [hasChanges, setHasChanges]   = useState(false);

    useEffect(() => {
        if (engagementSkills.length > 0) {
            const map: Record<string, number> = {};
            engagementSkills.forEach(es => { map[es.skill_id] = es.min_level; });
            setLocalSkills(map);
            setHasChanges(false);
        }
    }, [engagementSkills]);

    const markDirty = (dirty: boolean) => {
        setHasChanges(dirty);
        onDirtyChange?.(dirty);
    };

    const handleSave = async () => {
        const skills = Object.entries(localSkills).map(([skill_id, min_level]) => ({ skill_id, min_level }));
        try {
            await setEngagementSkills.mutateAsync({ engagementId, skills });
            markDirty(false);
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to save skills'));
        }
    };

    // Expose save function to parent via ref
    useEffect(() => {
        if (saveRef) saveRef.current = handleSave;
        return () => { if (saveRef) saveRef.current = null; };
    });

    if (categories.length === 0) {
        return (
            <Card className="border-slate-800 bg-slate-900/50">
                <CardContent className="flex flex-col items-center justify-center py-14 gap-2">
                    <Radar className="h-10 w-10 text-slate-700" />
                    <p className="text-sm text-slate-500 italic">No skill categories configured.</p>
                </CardContent>
            </Card>
        );
    }

    // Set required level for a skill. Level 0 = not required (removed from
    // the payload on save). Matches the profile SkillsTab UX so the two
    // pickers behave the same across the app.
    const setLevel = (skillId: string, level: number) => {
        setLocalSkills(prev => {
            if (level === 0) {
                const next = { ...prev };
                delete next[skillId];
                return next;
            }
            return { ...prev, [skillId]: level };
        });
        markDirty(true);
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-2">
                <Radar className="h-5 w-5 text-pink-500" />
                <h2 className="text-lg font-semibold text-white">Required Skills</h2>
                <p className="text-sm text-slate-400 ml-2">Skills needed for operators on this engagement</p>
            </div>

            {categories.map((cat) => (
                <Card key={cat.id} className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <div
                                className="w-3 h-3 rounded-full"
                                style={{ backgroundColor: cat.color || '#6366f1' }}
                            />
                            {cat.name}
                            <span className="text-xs text-slate-600 font-normal">
                                {cat.skills?.length ?? 0} skills
                            </span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        {cat.skills?.map((skill) => {
                            const level = localSkills[skill.id] ?? 0;
                            return (
                                <div
                                    key={skill.id}
                                    className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-slate-800/40 transition-colors"
                                >
                                    <div className="min-w-0 flex-1">
                                        <span className="text-sm text-white font-medium">{skill.name}</span>
                                        {skill.description && (
                                            <p className="text-xs text-slate-600 truncate">{skill.description}</p>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-1 shrink-0 ml-4">
                                        {SKILL_LEVELS.map((lvl) => {
                                            const isActive = level === lvl.value;
                                            return (
                                                <button
                                                    key={lvl.value}
                                                    type="button"
                                                    onClick={() => setLevel(skill.id, lvl.value)}
                                                    className={cn(
                                                        'px-2.5 py-1 rounded-md text-xs font-medium transition-all border',
                                                        isActive
                                                            ? lvl.value === 0
                                                                ? 'bg-slate-700 border-slate-600 text-slate-300'
                                                                : lvl.value === 1
                                                                    ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                                                                    : lvl.value === 2
                                                                        ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
                                                                        : 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                                                            : 'bg-transparent border-slate-800 text-slate-600 hover:text-slate-400 hover:border-slate-700'
                                                    )}
                                                >
                                                    {lvl.label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })}
                    </CardContent>
                </Card>
            ))}
        </div>
    );
}

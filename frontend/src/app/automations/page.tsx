/**
 * automations/page.tsx — Automation Rules Page
 *
 * IFTTT-style event-driven automation builder. Users create rules with:
 *  - Trigger: event type (finding created, engagement status changed, etc.)
 *  - Conditions (optional AND): field + operator + value comparisons
 *    (severity, status, resource type, etc.)
 *  - Actions: notify users, notify by role, fire a webhook, or send email.
 *
 * The page renders a searchable list of `RuleCard` components that show
 * a WHEN → IF → THEN flow visualisation, trigger count, and last-fired
 * timestamp. Each rule can be toggled on/off, edited via a 3-step wizard
 * dialog (`RuleEditor`), or deleted with confirmation.
 *
 * Helper components:
 *  - `EmptyState`: onboarding prompt when no rules exist.
 *  - `RuleCard`: compact card with flow badges and inline actions.
 *  - `ConditionValueInput`: renders a dropdown for known fields
 *    (severity, status, resource_type) or a free-text input otherwise.
 *  - `RuleEditor`: 3-step dialog (Trigger → Conditions → Actions) with
 *    dynamic field lists based on the selected trigger type.
 */
'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import DashboardLayout from '@/components/layout/dashboard-layout';
import {
    Zap, Plus, Trash2, Search, ArrowRight, Bell, Globe, Mail, Users, Shield,
    Settings, Activity, FileText, AlertTriangle, CheckCircle, Pencil, X, Play,
    Tag as TagIcon, Server, Lock, Trash,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import {
    useAutomations,
    useMyPersonalAutomations,
    useTriggerTypes,
    useCreateAutomation,
    useUpdateAutomation,
    useDeleteAutomation,
    useToggleAutomation,
    useTriggerAutomation,
    AutomationRule,
    AutomationCondition,
    AutomationAction,
    TriggerType,
} from '@/lib/hooks/use-automations';
import { PersonalRuleEditor } from '@/components/automations/personal-rule-editor';
import { useUsers } from '@/lib/hooks/use-users';
import { useTags } from '@/lib/hooks/use-tags';

// Value dropdowns are shared with the personal-rule editor — see
// frontend/src/lib/automation-known-values.ts to avoid drift.
import { AUTOMATION_KNOWN_VALUES as KNOWN_VALUES } from '@/lib/automation-known-values';

// Numeric fields use number input + numeric operators
const NUMERIC_FIELDS = new Set(['cvss_score']);
// Multi-value fields show a multi-tag picker and use list operators
const MULTI_VALUE_FIELDS = new Set(['tags']);

// ── trigger icons ────────────────────────────────────────────────────

const TRIGGER_ICONS: Record<string, any> = {
    created_finding: AlertTriangle,
    updated_finding: Pencil,
    finding_status_changed: Activity,
    created_engagement: FileText,
    updated_engagement: Pencil,
    engagement_status_changed: Activity,
    created_testcase: CheckCircle,
    updated_testcase: Pencil,
    executed_testcase: CheckCircle,
    created_asset: Server,
    updated_asset: Server,
    uploaded_evidence: FileText,
    created_comment: FileText,
    created_note: FileText,
    created_vault_item: Lock,
    created_cleanup_artifact: Trash,
    updated_cleanup_artifact: Trash,
    cleanup_status_changed: Activity,
    assigned_user: Users,
    removed_user: Users,
    manual: Play,
};

const ACTION_ICONS: Record<string, any> = {
    notify_users: Bell,
    notify_role: Shield,
    webhook: Globe,
    email: Mail,
    add_tags: TagIcon,
};

const ACTION_LABELS: Record<string, string> = {
    notify_users: 'Notify Users',
    notify_role: 'Notify by Role',
    webhook: 'Webhook',
    email: 'Send Email',
    add_tags: 'Add Tags',
};

// Operators available for each field type. Scalar fields get the original
// set; numeric/list fields get specialised options.
const SCALAR_OPERATORS: Record<string, string> = {
    equals: 'equals',
    not_equals: 'does not equal',
    contains: 'contains',
    in: 'is one of',
};

const NUMERIC_OPERATORS: Record<string, string> = {
    equals: 'equals',
    not_equals: 'does not equal',
    gt: 'greater than',
    gte: 'greater than or equal',
    lt: 'less than',
    lte: 'less than or equal',
};

const LIST_OPERATORS: Record<string, string> = {
    has_any: 'has any of',
    has_all: 'has all of',
    has_none: 'has none of',
};

function operatorsForField(field: string): Record<string, string> {
    if (NUMERIC_FIELDS.has(field)) return NUMERIC_OPERATORS;
    if (MULTI_VALUE_FIELDS.has(field)) return LIST_OPERATORS;
    return SCALAR_OPERATORS;
}

function defaultOperatorForField(field: string): string {
    if (NUMERIC_FIELDS.has(field)) return 'gte';
    if (MULTI_VALUE_FIELDS.has(field)) return 'has_any';
    return 'equals';
}

const FIELD_LABELS: Record<string, string> = {
    severity: 'Severity',
    status: 'Status',
    cvss_score: 'CVSS Score',
    tags: 'Tags',
    asset_type: 'Asset Type',
    engagement_id: 'Engagement ID',
    resource_name: 'Resource Name',
    resource_type: 'Resource Type',
};

// ── empty state ──────────────────────────────────────────────────────

function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
    return (
        <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="relative mb-6">
                <div className="h-20 w-20 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                    <Zap className="h-10 w-10 text-primary" />
                </div>
                <div className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-primary flex items-center justify-center">
                    <Plus className="h-3 w-3 text-primary-foreground" />
                </div>
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">No automation rules yet</h3>
            <p className="text-slate-400 max-w-md mb-6">
                Create rules to automate notifications, webhooks and more. When events happen in RedWire,
                your rules will fire automatically.
            </p>
            <Button onClick={onCreateClick} className="bg-primary hover:bg-primary/90 text-white gap-2">
                <Plus className="h-4 w-4" />
                Create Your First Rule
            </Button>
        </div>
    );
}

// ── rule card ────────────────────────────────────────────────────────

function RuleCard({
    rule,
    triggers,
    onEdit,
    onToggle,
    onDelete,
    onRun,
    isRunning,
}: {
    rule: AutomationRule;
    triggers: TriggerType[];
    onEdit: () => void;
    onToggle: () => void;
    onDelete: () => void;
    onRun: () => void;
    isRunning: boolean;
}) {
    const trigger = triggers.find(t => t.value === rule.trigger_type);
    const TriggerIcon = TRIGGER_ICONS[rule.trigger_type] || Zap;

    return (
        <div className={`group relative rounded-xl border transition-all ${rule.is_enabled
                ? 'border-slate-700/50 bg-slate-800/40 hover:border-primary/30 hover:bg-slate-800/60'
                : 'border-slate-800/50 bg-slate-900/30 opacity-60'
            }`}>
            <div className="p-5">
                {/* Header */}
                <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                        <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${rule.is_enabled
                                ? 'bg-primary/15 text-primary'
                                : 'bg-slate-700/30 text-slate-500'
                            }`}>
                            <TriggerIcon className="h-5 w-5" />
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-white">{rule.name}</h3>
                            {rule.description && (
                                <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{rule.description}</p>
                            )}
                        </div>
                    </div>
                    <Switch
                        checked={rule.is_enabled}
                        onCheckedChange={onToggle}
                    />
                </div>

                {/* Flow visualization */}
                <div className="flex items-center gap-2 flex-wrap text-xs mb-3">
                    {rule.trigger_type === 'manual' ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-violet-500/10 text-violet-400 border border-violet-500/20 font-medium">
                            <Play className="h-3 w-3" /> MANUAL ONLY
                        </span>
                    ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20 font-medium">
                            WHEN {trigger?.label || rule.trigger_type}
                        </span>
                    )}
                    {rule.conditions.length > 0 && (
                        <>
                            <ArrowRight className="h-3 w-3 text-slate-500 shrink-0" />
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-purple-500/10 text-purple-400 border border-purple-500/20 font-medium">
                                IF {rule.conditions.length} condition{rule.conditions.length > 1 ? 's' : ''}
                            </span>
                        </>
                    )}
                    <ArrowRight className="h-3 w-3 text-slate-500 shrink-0" />
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-green-500/10 text-green-400 border border-green-500/20 font-medium">
                        THEN {rule.actions.length} action{rule.actions.length > 1 ? 's' : ''}
                    </span>
                </div>

                {/* Stats + Actions */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 text-xs text-slate-500">
                        <span className="flex items-center gap-1">
                            <Activity className="h-3 w-3" />
                            {rule.trigger_count} trigger{rule.trigger_count !== 1 ? 's' : ''}
                        </span>
                        {rule.last_triggered_at && (
                            <span>
                                Last: {formatDistanceToNow(parseUTCDate(rule.last_triggered_at), { addSuffix: true })}
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                            variant="ghost" size="sm" onClick={onRun} disabled={isRunning}
                            className="h-7 w-7 p-0 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
                            title="Run now"
                        >
                            <Play className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={onEdit} className="h-7 w-7 p-0 text-slate-400 hover:text-white">
                            <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={onDelete} className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10">
                            <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ── condition value input ────────────────────────────────────────────

function ConditionValueInput({
    field,
    value,
    onChange,
}: {
    field: string;
    value: string;
    onChange: (v: string) => void;
}) {
    const { data: allTags } = useTags();

    // Tag picker — value is comma-separated lowercased tag names
    if (field === 'tags') {
        const selected = new Set(value.split(',').map(s => s.trim().toLowerCase()).filter(Boolean));
        const toggle = (name: string) => {
            const lower = name.toLowerCase();
            if (selected.has(lower)) selected.delete(lower);
            else selected.add(lower);
            onChange(Array.from(selected).join(','));
        };
        return (
            <div className="flex-1 flex flex-wrap gap-1 bg-slate-800 border border-slate-700 rounded-md p-1.5 min-h-[2rem]">
                {(allTags || []).length === 0 ? (
                    <span className="text-xs text-slate-500 px-1">No tags defined yet</span>
                ) : (
                    (allTags || []).map(t => {
                        const isSelected = selected.has(t.name.toLowerCase());
                        return (
                            <button
                                key={t.id}
                                type="button"
                                onClick={() => toggle(t.name)}
                                className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
                                    isSelected
                                        ? 'bg-primary/20 border-primary/40 text-primary'
                                        : 'bg-slate-900/40 border-slate-700/60 text-slate-400 hover:text-white'
                                }`}
                                style={t.color && isSelected ? { borderColor: t.color, color: t.color } : undefined}
                            >
                                {t.name}
                            </button>
                        );
                    })
                )}
            </div>
        );
    }

    // Numeric input
    if (NUMERIC_FIELDS.has(field)) {
        return (
            <Input
                type="number"
                step="0.1"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder="0.0"
                className="flex-1 bg-slate-800 border-slate-700 text-white text-xs h-8"
            />
        );
    }

    const options = KNOWN_VALUES[field];

    if (options) {
        return (
            <Select value={value} onValueChange={onChange}>
                <SelectTrigger className="flex-1 bg-slate-800 border-slate-700 text-white text-xs h-8">
                    <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                    {options.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
        );
    }

    return (
        <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Value..."
            className="flex-1 bg-slate-800 border-slate-700 text-white text-xs h-8"
        />
    );
}

// ── add_tags action config ───────────────────────────────────────────

const TAG_COMPATIBLE_TRIGGERS = new Set([
    'created_finding', 'updated_finding', 'finding_status_changed',
    'created_testcase', 'updated_testcase', 'executed_testcase',
]);

function AddTagsActionConfig({
    tagIds,
    onChange,
    triggerType,
}: {
    tagIds: string[];
    onChange: (ids: string[]) => void;
    triggerType: string;
}) {
    const { data: allTags } = useTags();
    const compatible = TAG_COMPATIBLE_TRIGGERS.has(triggerType);
    const selected = new Set(tagIds);
    const toggle = (id: string) => {
        const next = new Set(selected);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        onChange(Array.from(next));
    };

    return (
        <div>
            <Label className="text-slate-400 text-xs">Tags to apply</Label>
            {!compatible && (
                <p className="text-[11px] text-yellow-400/90 mt-1 mb-1">
                    This action only takes effect for finding/test case triggers — pick a compatible trigger above.
                </p>
            )}
            <div className="flex flex-wrap gap-1.5 mt-1">
                {(allTags || []).length === 0 ? (
                    <span className="text-xs text-slate-500">No tags defined yet — create tags from the Tags page first.</span>
                ) : (
                    (allTags || []).map(t => {
                        const isSelected = selected.has(t.id);
                        return (
                            <button
                                key={t.id}
                                type="button"
                                onClick={() => toggle(t.id)}
                                className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-colors ${
                                    isSelected
                                        ? 'bg-primary/20 border-primary/40 text-primary'
                                        : 'bg-slate-700/30 border-slate-700/50 text-slate-400 hover:text-white'
                                }`}
                                style={t.color && isSelected ? { borderColor: t.color, color: t.color } : undefined}
                            >
                                {t.name}
                            </button>
                        );
                    })
                )}
            </div>
        </div>
    );
}

// ── rule editor dialog ───────────────────────────────────────────────

function RuleEditor({
    open,
    onClose,
    editRule,
    triggers,
}: {
    open: boolean;
    onClose: () => void;
    editRule: AutomationRule | null;
    triggers: TriggerType[];
}) {
    const createRule = useCreateAutomation();
    const updateRule = useUpdateAutomation();
    const { data: users } = useUsers();

    const [name, setName] = useState(editRule?.name || '');
    const [description, setDescription] = useState(editRule?.description || '');
    const [triggerType, setTriggerType] = useState(editRule?.trigger_type || '');
    const [conditions, setConditions] = useState<AutomationCondition[]>(editRule?.conditions || []);
    const [actions, setActions] = useState<AutomationAction[]>(editRule?.actions || []);
    const [step, setStep] = useState(0); // 0=trigger, 1=conditions, 2=actions
    const isEditing = !!editRule;

    const selectedTrigger = triggers.find(t => t.value === triggerType);

    const handleSave = async () => {
        if (!name.trim()) { toast.error('Give your rule a name'); return; }
        if (!triggerType) { toast.error('Select a trigger'); return; }
        if (actions.length === 0) { toast.error('Add at least one action'); return; }

        try {
            if (isEditing) {
                await updateRule.mutateAsync({
                    id: editRule.id, name, description: description || undefined,
                    trigger_type: triggerType, conditions, actions,
                });
                toast.success('Rule updated');
            } else {
                await createRule.mutateAsync({
                    name, description: description || undefined,
                    trigger_type: triggerType, conditions, actions,
                });
                toast.success('Rule created');
            }
            onClose();
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to save rule'));
        }
    };

    const addCondition = () => {
        const firstField = selectedTrigger?.fields?.[0] || 'severity';
        setConditions([
            ...conditions,
            { field: firstField, operator: defaultOperatorForField(firstField), value: '' },
        ]);
    };
    const updateCondition = (idx: number, updates: Partial<AutomationCondition>) => {
        setConditions(conditions.map((c, i) => i === idx ? { ...c, ...updates } : c));
    };
    const removeCondition = (idx: number) => setConditions(conditions.filter((_, i) => i !== idx));

    const addAction = (type: string) => {
        const base: AutomationAction = { type };
        if (type === 'notify_users') base.user_ids = [];
        if (type === 'notify_role') base.role = 'admin';
        if (type === 'webhook') { base.url = ''; base.method = 'POST'; }
        if (type === 'email') { base.recipients = []; base.subject = ''; }
        if (type === 'add_tags') base.tag_ids = [];
        setActions([...actions, base]);
    };
    const updateAction = (idx: number, updates: Partial<AutomationAction>) => {
        setActions(actions.map((a, i) => i === idx ? { ...a, ...updates } : a));
    };
    const removeAction = (idx: number) => setActions(actions.filter((_, i) => i !== idx));

    const steps = [
        { label: 'Trigger', icon: Zap },
        { label: 'Conditions', icon: Settings },
        { label: 'Actions', icon: Bell },
    ];

    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto bg-slate-900 border-slate-700">
                <DialogHeader>
                    <DialogTitle className="text-white flex items-center gap-2">
                        <Zap className="h-5 w-5 text-primary" />
                        {isEditing ? 'Edit Rule' : 'Create Automation Rule'}
                    </DialogTitle>
                </DialogHeader>

                {/* Name + Description */}
                <div className="space-y-3 mb-4">
                    <div>
                        <Label className="text-slate-300 text-xs">Rule Name</Label>
                        <Input value={name} onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. Alert on critical verified findings"
                            className="bg-slate-800 border-slate-700 text-white" />
                    </div>
                    <div>
                        <Label className="text-slate-300 text-xs">Description (optional)</Label>
                        <Input value={description} onChange={(e) => setDescription(e.target.value)}
                            placeholder="Briefly describe what this rule does"
                            className="bg-slate-800 border-slate-700 text-white" />
                    </div>
                </div>

                {/* Step tabs */}
                <div className="flex items-center gap-1 mb-4 bg-slate-800/50 rounded-lg p-1">
                    {steps.map((s, i) => {
                        const Icon = s.icon;
                        return (
                            <button key={i} onClick={() => setStep(i)}
                                className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-xs font-medium transition-all ${step === i
                                        ? 'bg-primary/15 text-primary border border-primary/30'
                                        : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                                    }`}>
                                <Icon className="h-3.5 w-3.5" />
                                {s.label}
                                {i === 1 && conditions.length > 0 && (
                                    <span className="ml-1 bg-purple-500/20 text-purple-400 px-1.5 rounded text-[10px]">{conditions.length}</span>
                                )}
                                {i === 2 && actions.length > 0 && (
                                    <span className="ml-1 bg-green-500/20 text-green-400 px-1.5 rounded text-[10px]">{actions.length}</span>
                                )}
                            </button>
                        );
                    })}
                </div>

                {/* Step 0: Trigger */}
                {step === 0 && (
                    <div className="space-y-2">
                        <Label className="text-slate-300 text-xs font-medium">When this event happens:</Label>
                        <div className="grid grid-cols-2 gap-2 max-h-[300px] overflow-y-auto pr-1">
                            {triggers.map(t => {
                                const Icon = TRIGGER_ICONS[t.value] || Zap;
                                const selected = triggerType === t.value;
                                return (
                                    <button key={t.value}
                                        onClick={() => { setTriggerType(t.value); setConditions([]); }}
                                        className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-all text-sm ${selected
                                                ? 'border-primary/50 bg-primary/10 text-primary'
                                                : 'border-slate-700/50 bg-slate-800/30 text-slate-400 hover:border-slate-600 hover:text-white'
                                            }`}>
                                        <span className="text-lg">{t.icon}</span>
                                        <span className="font-medium">{t.label}</span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Step 1: Conditions */}
                {step === 1 && (
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <Label className="text-slate-300 text-xs font-medium">Only if these conditions match (AND):</Label>
                            <Button variant="ghost" size="sm" onClick={addCondition}
                                className="text-primary hover:text-primary/80 gap-1 text-xs h-7" disabled={!selectedTrigger}>
                                <Plus className="h-3 w-3" /> Add Condition
                            </Button>
                        </div>
                        {conditions.length === 0 && (
                            <div className="text-center py-8 text-slate-500 text-sm">
                                No conditions — rule fires for every {selectedTrigger?.label || 'event'}
                            </div>
                        )}
                        {conditions.map((cond, i) => (
                            <div key={i} className="flex items-center gap-2 bg-slate-800/40 rounded-lg p-3 border border-slate-700/30">
                                <Select
                                    value={cond.field}
                                    onValueChange={(v) =>
                                        updateCondition(i, { field: v, value: '', operator: defaultOperatorForField(v) })
                                    }
                                >
                                    <SelectTrigger className="w-[140px] bg-slate-800 border-slate-700 text-white text-xs h-8">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {(selectedTrigger?.fields || []).map(f => (
                                            <SelectItem key={f} value={f}>{FIELD_LABELS[f] || f}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <Select value={cond.operator} onValueChange={(v) => updateCondition(i, { operator: v })}>
                                    <SelectTrigger className="w-[160px] bg-slate-800 border-slate-700 text-white text-xs h-8">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {Object.entries(operatorsForField(cond.field)).map(([k, v]) => (
                                            <SelectItem key={k} value={k}>{v}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <ConditionValueInput
                                    field={cond.field}
                                    value={cond.value}
                                    onChange={(v) => updateCondition(i, { value: v })}
                                />
                                <Button variant="ghost" size="sm" onClick={() => removeCondition(i)}
                                    className="h-7 w-7 p-0 text-red-400 hover:text-red-300">
                                    <X className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                        ))}
                    </div>
                )}

                {/* Step 2: Actions */}
                {step === 2 && (
                    <div className="space-y-3">
                        <Label className="text-slate-300 text-xs font-medium">Then do these actions:</Label>

                        {actions.map((action, i) => {
                            const ActionIcon = ACTION_ICONS[action.type] || Bell;
                            return (
                                <div key={i} className="bg-slate-800/40 rounded-lg p-4 border border-slate-700/30 space-y-3">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2 text-sm font-medium text-green-400">
                                            <ActionIcon className="h-4 w-4" />
                                            {ACTION_LABELS[action.type] || action.type}
                                        </div>
                                        <Button variant="ghost" size="sm" onClick={() => removeAction(i)}
                                            className="h-7 w-7 p-0 text-red-400">
                                            <X className="h-3.5 w-3.5" />
                                        </Button>
                                    </div>

                                    {action.type === 'notify_users' && (
                                        <>
                                            <div>
                                                <Label className="text-slate-400 text-xs">Select Users</Label>
                                                <div className="flex flex-wrap gap-1.5 mt-1.5">
                                                    {(users || []).map((u: any) => {
                                                        const selected = (action.user_ids || []).includes(u.id);
                                                        return (
                                                            <button key={u.id}
                                                                onClick={() => {
                                                                    const ids = action.user_ids || [];
                                                                    updateAction(i, {
                                                                        user_ids: selected ? ids.filter(id => id !== u.id) : [...ids, u.id],
                                                                    });
                                                                }}
                                                                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${selected
                                                                        ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                                                                        : 'bg-slate-700/30 text-slate-400 border border-slate-700/50 hover:text-white'
                                                                    }`}>
                                                                {u.username}
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                            <div>
                                                <Label className="text-slate-400 text-xs">Message</Label>
                                                <Input value={action.message || ''} onChange={(e) => updateAction(i, { message: e.target.value })}
                                                    placeholder="Custom notification message..."
                                                    className="bg-slate-800 border-slate-700 text-white text-xs h-8 mt-1" />
                                            </div>
                                        </>
                                    )}

                                    {action.type === 'notify_role' && (
                                        <>
                                            <div>
                                                <Label className="text-slate-400 text-xs">Role</Label>
                                                <Select value={action.role || 'admin'} onValueChange={(v) => updateAction(i, { role: v })}>
                                                    <SelectTrigger className="bg-slate-800 border-slate-700 text-white text-xs h-8 mt-1">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        <SelectItem value="admin">Admin</SelectItem>
                                                        <SelectItem value="team_lead">Team Lead</SelectItem>
                                                        <SelectItem value="operator">Operator</SelectItem>
                                                        <SelectItem value="viewer">Viewer</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div>
                                                <Label className="text-slate-400 text-xs">Message</Label>
                                                <Input value={action.message || ''} onChange={(e) => updateAction(i, { message: e.target.value })}
                                                    placeholder="Custom notification message..."
                                                    className="bg-slate-800 border-slate-700 text-white text-xs h-8 mt-1" />
                                            </div>
                                        </>
                                    )}

                                    {action.type === 'webhook' && (
                                        <>
                                            <div className="flex gap-2">
                                                <div className="w-24">
                                                    <Label className="text-slate-400 text-xs">Method</Label>
                                                    <Select value={action.method || 'POST'} onValueChange={(v) => updateAction(i, { method: v })}>
                                                        <SelectTrigger className="bg-slate-800 border-slate-700 text-white text-xs h-8 mt-1">
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            <SelectItem value="POST">POST</SelectItem>
                                                            <SelectItem value="GET">GET</SelectItem>
                                                            <SelectItem value="PUT">PUT</SelectItem>
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                                <div className="flex-1">
                                                    <Label className="text-slate-400 text-xs">URL</Label>
                                                    <Input value={action.url || ''} onChange={(e) => updateAction(i, { url: e.target.value })}
                                                        placeholder="https://hooks.slack.com/services/..."
                                                        className="bg-slate-800 border-slate-700 text-white text-xs h-8 mt-1" />
                                                </div>
                                            </div>
                                            <div>
                                                <Label className="text-slate-400 text-xs">
                                                    Body Template (use {'{{variable}}'} for dynamic values)
                                                </Label>
                                                <Textarea value={action.body_template || ''} onChange={(e) => updateAction(i, { body_template: e.target.value })}
                                                    placeholder={'{"text": "{{action}} on {{resource_name}} in engagement {{engagement_id}}"}'}
                                                    className="bg-slate-800 border-slate-700 text-white text-xs mt-1 min-h-[60px]" />
                                                <p className="text-[10px] text-slate-500 mt-1">
                                                    Variables: {'{{action}}, {{resource_type}}, {{resource_name}}, {{engagement_id}}, {{details}}, {{user_id}}'}
                                                </p>
                                            </div>
                                        </>
                                    )}

                                    {action.type === 'email' && (
                                        <>
                                            <div>
                                                <Label className="text-slate-400 text-xs">Recipients (comma-separated)</Label>
                                                <Input value={(action.recipients || []).join(', ')}
                                                    onChange={(e) => updateAction(i, { recipients: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                                                    placeholder="admin@example.com, security@example.com"
                                                    className="bg-slate-800 border-slate-700 text-white text-xs h-8 mt-1" />
                                            </div>
                                            <div>
                                                <Label className="text-slate-400 text-xs">Subject</Label>
                                                <Input value={action.subject || ''} onChange={(e) => updateAction(i, { subject: e.target.value })}
                                                    placeholder="Automation Alert: ..."
                                                    className="bg-slate-800 border-slate-700 text-white text-xs h-8 mt-1" />
                                            </div>
                                        </>
                                    )}

                                    {action.type === 'add_tags' && (
                                        <AddTagsActionConfig
                                            tagIds={action.tag_ids || []}
                                            onChange={(ids) => updateAction(i, { tag_ids: ids })}
                                            triggerType={triggerType}
                                        />
                                    )}
                                </div>
                            );
                        })}

                        {/* Add action buttons */}
                        <div className="flex flex-wrap gap-2 pt-2">
                            {Object.entries(ACTION_LABELS).map(([key, label]) => {
                                const Icon = ACTION_ICONS[key] || Bell;
                                return (
                                    <button key={key} onClick={() => addAction(key)}
                                        className="flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-slate-600/50 text-slate-400 hover:text-green-400 hover:border-green-500/30 hover:bg-green-500/5 transition-all text-xs">
                                        <Plus className="h-3 w-3" />
                                        <Icon className="h-3.5 w-3.5" />
                                        {label}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                <DialogFooter className="mt-4 flex items-center justify-between gap-2">
                    <div className="flex gap-2">
                        {step > 0 && (
                            <Button variant="outline" onClick={() => setStep(step - 1)} className="border-slate-700 text-slate-300">
                                Back
                            </Button>
                        )}
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={onClose} className="border-slate-700 text-slate-300">Cancel</Button>
                        {step < 2 ? (
                            <Button onClick={() => setStep(step + 1)} className="bg-primary hover:bg-primary/90 text-white gap-1">
                                Next <ArrowRight className="h-3.5 w-3.5" />
                            </Button>
                        ) : (
                            <Button onClick={handleSave} disabled={createRule.isPending || updateRule.isPending}
                                className="bg-primary hover:bg-primary/90 text-white gap-1">
                                <Zap className="h-3.5 w-3.5" />
                                {isEditing ? 'Save Changes' : 'Create Rule'}
                            </Button>
                        )}
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ── main page ────────────────────────────────────────────────────────

export default function AutomationsPage() {
    const { data: orgRules, isLoading: orgLoading } = useAutomations();
    const { data: personalRules, isLoading: personalLoading } = useMyPersonalAutomations();
    const { data: triggers } = useTriggerTypes();
    const toggleRule = useToggleAutomation();
    const deleteRule = useDeleteAutomation();
    const triggerRule = useTriggerAutomation();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [scope, setScope] = useState<'org' | 'personal'>('org');
    const [editorOpen, setEditorOpen] = useState(false);
    const [personalEditorOpen, setPersonalEditorOpen] = useState(false);
    const [editingRule, setEditingRule] = useState<AutomationRule | null>(null);
    const [search, setSearch] = useState('');

    const rules = scope === 'personal' ? personalRules : orgRules;
    const isLoading = scope === 'personal' ? personalLoading : orgLoading;

    const filteredRules = (rules || []).filter(r =>
        r.name.toLowerCase().includes(search.toLowerCase()) ||
        r.trigger_type.toLowerCase().includes(search.toLowerCase()) ||
        (r.description || '').toLowerCase().includes(search.toLowerCase())
    );

    const enabledCount = (rules || []).filter(r => r.is_enabled).length;

    const handleCreate = () => {
        setEditingRule(null);
        if (scope === 'personal') setPersonalEditorOpen(true);
        else setEditorOpen(true);
    };
    const handleEdit = (rule: AutomationRule) => {
        setEditingRule(rule);
        if (rule.is_personal || rule.owner_user_id) setPersonalEditorOpen(true);
        else setEditorOpen(true);
    };

    const handleToggle = async (rule: AutomationRule) => {
        try {
            await toggleRule.mutateAsync(rule.id);
            toast.success(rule.is_enabled ? 'Rule disabled' : 'Rule enabled');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to toggle rule'));
        }
    };

    const handleRun = async (rule: AutomationRule) => {
        try {
            await triggerRule.mutateAsync(rule.id);
            toast.success(`"${rule.name}" executed successfully`);
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to run rule'));
        }
    };

    const handleDelete = async (rule: AutomationRule) => {
        const confirmed = await confirm({
            title: 'Delete Rule',
            description: `Are you sure you want to delete "${rule.name}"? This cannot be undone.`,
        });
        if (!confirmed) return;
        try {
            await deleteRule.mutateAsync(rule.id);
            toast.success('Rule deleted');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to delete rule'));
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 max-w-6xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                            <Zap className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold text-white">Automations</h1>
                            <p className="text-sm text-slate-400">
                                {(rules || []).length} rule{(rules || []).length !== 1 ? 's' : ''} • {enabledCount} active
                            </p>
                        </div>
                    </div>
                    <Button onClick={handleCreate} className="bg-primary hover:bg-primary/90 text-white gap-2">
                        <Plus className="h-4 w-4" />
                        {scope === 'personal' ? 'New Personal Rule' : 'New Rule'}
                    </Button>
                </div>

                {/* Scope tabs */}
                <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-1 w-fit mb-4">
                    <button
                        onClick={() => { setScope('org'); setSearch(''); }}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${scope === 'org'
                            ? 'bg-primary/15 text-primary'
                            : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                            }`}
                    >
                        <Shield className="h-4 w-4" />
                        Org Rules
                        <span className="text-[10px] text-slate-500">({(orgRules || []).length})</span>
                    </button>
                    <button
                        onClick={() => { setScope('personal'); setSearch(''); }}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${scope === 'personal'
                            ? 'bg-primary/15 text-primary'
                            : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                            }`}
                    >
                        <Bell className="h-4 w-4" />
                        My Rules
                        <span className="text-[10px] text-slate-500">({(personalRules || []).length})</span>
                    </button>
                </div>

                {/* Search */}
                {(rules || []).length > 0 && (
                    <div className="relative mb-4">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                        <Input value={search} onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search rules..."
                            className="pl-10 bg-slate-800/50 border-slate-700 text-white" />
                    </div>
                )}

                {/* Rules list */}
                {isLoading ? (
                    <div className="text-center py-20 text-slate-500">Loading rules...</div>
                ) : (rules || []).length === 0 ? (
                    <EmptyState onCreateClick={handleCreate} />
                ) : filteredRules.length === 0 ? (
                    <div className="text-center py-20 text-slate-500">No rules match your search</div>
                ) : (
                    <div className="grid gap-3">
                        {filteredRules.map(rule => (
                            <RuleCard key={rule.id} rule={rule} triggers={triggers || []}
                                onEdit={() => handleEdit(rule)}
                                onToggle={() => handleToggle(rule)}
                                onDelete={() => handleDelete(rule)}
                                onRun={() => handleRun(rule)}
                                isRunning={triggerRule.isPending} />
                        ))}
                    </div>
                )}

                {editorOpen && (
                    <RuleEditor open={editorOpen}
                        onClose={() => { setEditorOpen(false); setEditingRule(null); }}
                        editRule={editingRule} triggers={triggers || []} />
                )}
                {personalEditorOpen && (
                    <PersonalRuleEditor open={personalEditorOpen}
                        onClose={() => { setPersonalEditorOpen(false); setEditingRule(null); }}
                        editRule={editingRule} triggers={triggers || []} />
                )}

                <ConfirmDialog />
            </div>
        </DashboardLayout>
    );
}

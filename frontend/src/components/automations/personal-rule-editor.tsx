'use client';

/**
 * personal-rule-editor.tsx — 2-step editor for a user's personal automation rule.
 *
 * Personal rules always notify the owner and never anyone else — so this
 * editor skips the org editor's Actions step entirely. Fields:
 *   - Rule Name + Description
 *   - Step 1: Trigger (event to subscribe to)
 *   - Step 2: Conditions (optional; AND'd — mirrors org editor's UX)
 *   - Optional custom notification message
 *
 * On save it POSTs / PUTs to /automations with is_personal=true; the
 * backend forces the actions list to a single notify-self and stores
 * owner_user_id = current_user.id. See routers/automations.py create_rule
 * for the personal-rule branch.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Zap, Bell, Settings, Plus, X, User } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage } from '@/components/ui/confirm-dialog';
import {
    useCreateAutomation,
    useUpdateAutomation,
    AutomationRule,
    AutomationCondition,
    TriggerType,
} from '@/lib/hooks/use-automations';
import { AUTOMATION_KNOWN_VALUES } from '@/lib/automation-known-values';

// Personal rules only make sense for triggers where "I did the thing" is a
// natural filter. Excluded triggers are the ones that fire on foreign
// activity (comment on someone else's thread, etc.); when we grow the
// engine to track participation lists these can move back in.
const PERSONAL_TRIGGER_ALLOWLIST = new Set([
    'created_finding',
    'updated_finding',
    'finding_status_changed',
    'created_testcase',
    'updated_testcase',
    'executed_testcase',
    'created_asset',
    'updated_asset',
    'uploaded_evidence',
    'created_comment',
    'created_note',
    'created_vault_item',
    'created_cleanup_artifact',
    'updated_cleanup_artifact',
    'cleanup_status_changed',
]);

const OPERATOR_LABELS: Record<string, string> = {
    equals: 'equals',
    not_equals: 'not equals',
    contains: 'contains',
    in: 'is one of',
    has_any: 'has any of',
    has_all: 'has all of',
    has_none: 'has none of',
    gt: '>',
    gte: '≥',
    lt: '<',
    lte: '≤',
};

const NUMERIC_FIELDS = new Set(['cvss_score']);
const LIST_FIELDS = new Set(['tags']);

function operatorsForField(field: string): string[] {
    if (NUMERIC_FIELDS.has(field)) return ['equals', 'gt', 'gte', 'lt', 'lte'];
    if (LIST_FIELDS.has(field)) return ['has_any', 'has_all', 'has_none', 'contains'];
    return ['equals', 'not_equals', 'contains', 'in'];
}

export function PersonalRuleEditor({
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

    const [name, setName] = useState(editRule?.name || '');
    const [description, setDescription] = useState(editRule?.description || '');
    const [triggerType, setTriggerType] = useState(editRule?.trigger_type || '');
    const [conditions, setConditions] = useState<AutomationCondition[]>(editRule?.conditions || []);
    const [message, setMessage] = useState(editRule?.actions?.[0]?.message || '');
    const [step, setStep] = useState<0 | 1>(0);

    const isEditing = !!editRule;
    const availableTriggers = triggers.filter(t => PERSONAL_TRIGGER_ALLOWLIST.has(t.value));
    const selectedTrigger = availableTriggers.find(t => t.value === triggerType);

    const addCondition = () => {
        const firstField = selectedTrigger?.fields?.[0] || 'severity';
        const ops = operatorsForField(firstField);
        setConditions([...conditions, { field: firstField, operator: ops[0], value: '' }]);
    };
    const updateCondition = (idx: number, updates: Partial<AutomationCondition>) => {
        setConditions(conditions.map((c, i) => (i === idx ? { ...c, ...updates } : c)));
    };
    const removeCondition = (idx: number) => setConditions(conditions.filter((_, i) => i !== idx));

    const handleSave = async () => {
        if (!name.trim()) { toast.error('Give your rule a name'); return; }
        if (!triggerType) { toast.error('Pick a trigger'); return; }

        // Personal action shape: message is optional; the backend fills in
        // user_ids = [me] and enforces the notify_users type.
        const actions = [{ type: 'notify_users', ...(message ? { message } : {}) }];

        try {
            if (isEditing) {
                await updateRule.mutateAsync({
                    id: editRule.id,
                    name,
                    description: description || undefined,
                    trigger_type: triggerType,
                    conditions,
                    actions,
                });
                toast.success('Personal rule updated');
            } else {
                await createRule.mutateAsync({
                    name,
                    description: description || undefined,
                    trigger_type: triggerType,
                    conditions,
                    actions,
                    is_personal: true,
                });
                toast.success('Personal rule created');
            }
            onClose();
        } catch (error: unknown) {
            toast.error(getErrorMessage(error, 'Failed to save personal rule'));
        }
    };

    return (
        <Dialog open={open} onOpenChange={v => !v && onClose()}>
            <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto bg-slate-900 border-slate-700">
                <DialogHeader>
                    <DialogTitle className="text-white flex items-center gap-2">
                        <User className="h-5 w-5 text-primary" />
                        {isEditing ? 'Edit Personal Rule' : 'New Personal Rule'}
                    </DialogTitle>
                    <p className="text-xs text-slate-500 mt-1">
                        Notifies you when the trigger fires on activity you caused. No one else sees it.
                    </p>
                </DialogHeader>

                {/* Name + description */}
                <div className="space-y-3 mb-4">
                    <div>
                        <Label className="text-slate-300 text-xs">Rule Name</Label>
                        <Input
                            value={name}
                            onChange={e => setName(e.target.value)}
                            placeholder="e.g. Ping me when my finding gets verified"
                            className="bg-slate-800 border-slate-700 text-white"
                        />
                    </div>
                    <div>
                        <Label className="text-slate-300 text-xs">Description (optional)</Label>
                        <Input
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            placeholder="Optional note about what this rule is for"
                            className="bg-slate-800 border-slate-700 text-white"
                        />
                    </div>
                </div>

                {/* Step tabs */}
                <div className="flex items-center gap-1 mb-4 bg-slate-800/50 rounded-lg p-1">
                    {([
                        { i: 0 as const, label: 'Trigger', icon: Zap },
                        { i: 1 as const, label: 'Conditions', icon: Settings },
                    ]).map(s => {
                        const Icon = s.icon;
                        return (
                            <button
                                key={s.i}
                                onClick={() => setStep(s.i)}
                                className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-xs font-medium transition-all ${step === s.i
                                    ? 'bg-primary/15 text-primary border border-primary/30'
                                    : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                                    }`}
                            >
                                <Icon className="h-3.5 w-3.5" />
                                {s.label}
                                {s.i === 1 && conditions.length > 0 && (
                                    <span className="ml-1 bg-purple-500/20 text-purple-400 px-1.5 rounded text-[10px]">
                                        {conditions.length}
                                    </span>
                                )}
                            </button>
                        );
                    })}
                </div>

                {/* Step 0: trigger picker */}
                {step === 0 && (
                    <div className="space-y-2">
                        <Label className="text-slate-300 text-xs font-medium">
                            Fire when I do something like:
                        </Label>
                        <div className="grid grid-cols-2 gap-2 max-h-[300px] overflow-y-auto pr-1">
                            {availableTriggers.map(t => {
                                const selected = triggerType === t.value;
                                return (
                                    <button
                                        key={t.value}
                                        onClick={() => {
                                            setTriggerType(t.value);
                                            setConditions([]);
                                        }}
                                        className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-all text-sm ${selected
                                            ? 'border-primary/50 bg-primary/10 text-primary'
                                            : 'border-slate-700/50 bg-slate-800/30 text-slate-400 hover:border-slate-600 hover:text-white'
                                            }`}
                                    >
                                        <span className="text-lg">{t.icon}</span>
                                        <span className="font-medium">{t.label}</span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Step 1: conditions */}
                {step === 1 && (
                    <div className="space-y-3">
                        {!selectedTrigger ? (
                            <p className="text-xs text-slate-500 italic">
                                Pick a trigger first — it decides which fields you can filter on.
                            </p>
                        ) : (
                            <>
                                <div className="flex items-center justify-between">
                                    <Label className="text-slate-300 text-xs font-medium">
                                        Only fire if all of these match:
                                    </Label>
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={addCondition}
                                        className="h-7 text-xs text-primary hover:text-primary/80"
                                    >
                                        <Plus className="h-3 w-3 mr-1" /> Add condition
                                    </Button>
                                </div>
                                {conditions.length === 0 && (
                                    <p className="text-[11px] text-slate-600 italic">
                                        No conditions means the rule fires on every matching event.
                                    </p>
                                )}
                                {conditions.map((cond, idx) => {
                                    const ops = operatorsForField(cond.field);
                                    return (
                                        <div key={idx} className="flex items-center gap-2 p-2 rounded-lg border border-slate-700 bg-slate-800/40">
                                            <Select value={cond.field} onValueChange={v => updateCondition(idx, { field: v, operator: operatorsForField(v)[0] })}>
                                                <SelectTrigger className="bg-slate-800 border-slate-700 text-xs h-8 flex-1">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-800 border-slate-700">
                                                    {(selectedTrigger.fields || []).map(f => (
                                                        <SelectItem key={f} value={f} className="text-white text-xs">
                                                            {f}
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            <Select value={cond.operator} onValueChange={v => updateCondition(idx, { operator: v })}>
                                                <SelectTrigger className="bg-slate-800 border-slate-700 text-xs h-8 w-28">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-800 border-slate-700">
                                                    {ops.map(op => (
                                                        <SelectItem key={op} value={op} className="text-white text-xs">
                                                            {OPERATOR_LABELS[op] || op}
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            {AUTOMATION_KNOWN_VALUES[cond.field] ? (
                                                <Select
                                                    value={cond.value}
                                                    onValueChange={v => updateCondition(idx, { value: v })}
                                                >
                                                    <SelectTrigger className="bg-slate-800 border-slate-700 text-xs h-8 flex-1">
                                                        <SelectValue placeholder="value" />
                                                    </SelectTrigger>
                                                    <SelectContent className="bg-slate-800 border-slate-700">
                                                        {AUTOMATION_KNOWN_VALUES[cond.field].map(opt => (
                                                            <SelectItem key={opt.value} value={opt.value} className="text-white text-xs">
                                                                {opt.label}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            ) : (
                                                <Input
                                                    value={cond.value}
                                                    onChange={e => updateCondition(idx, { value: e.target.value })}
                                                    placeholder="value"
                                                    className="bg-slate-800 border-slate-700 text-white text-xs h-8 flex-1"
                                                />
                                            )}
                                            <Button size="icon" variant="ghost" onClick={() => removeCondition(idx)} className="h-7 w-7 text-slate-500 hover:text-red-400">
                                                <X className="h-3.5 w-3.5" />
                                            </Button>
                                        </div>
                                    );
                                })}
                            </>
                        )}
                    </div>
                )}

                {/* Message override */}
                <div className="mt-4 pt-4 border-t border-slate-800">
                    <Label className="text-slate-300 text-xs font-medium flex items-center gap-1.5">
                        <Bell className="h-3.5 w-3.5" /> Notification message (optional)
                    </Label>
                    <Textarea
                        value={message}
                        onChange={e => setMessage(e.target.value)}
                        placeholder="Leave blank to use the default — you can reference {{resource_name}}, {{severity}}, etc."
                        className="bg-slate-800 border-slate-700 text-white text-xs mt-1"
                        rows={2}
                    />
                </div>

                <DialogFooter className="mt-4">
                    <Button variant="outline" onClick={onClose} className="border-slate-700">
                        Cancel
                    </Button>
                    <Button
                        onClick={handleSave}
                        disabled={createRule.isPending || updateRule.isPending}
                        className="bg-primary hover:bg-primary/90"
                    >
                        {isEditing ? 'Save changes' : 'Create rule'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

'use client';

/**
 * CustomFieldsManagement — admin console tab for defining custom fields on
 * assets, testcases, findings, and clients. An entity selector across the top;
 * for the selected entity, a reorderable list of field definitions with a
 * create/edit dialog. Mirrors the configurable-types admin conventions.
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog';
import {
    Plus, Pencil, Trash2, Loader2, ChevronUp, ChevronDown, ListPlus,
    Server, ClipboardCheck, Bug, Building2, Briefcase, EyeOff,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import {
    useCustomFieldDefs, useCreateCustomFieldDef, useUpdateCustomFieldDef,
    useDeleteCustomFieldDef, useReorderCustomFieldDefs,
    type CustomFieldEntity, type CustomFieldDef, type CustomFieldType,
} from '@/lib/hooks/use-custom-fields';

const ENTITIES: { key: CustomFieldEntity; label: string; icon: React.ElementType }[] = [
    { key: 'engagement', label: 'Engagements', icon: Briefcase },
    { key: 'finding', label: 'Findings', icon: Bug },
    { key: 'asset', label: 'Assets', icon: Server },
    { key: 'testcase', label: 'Test Cases', icon: ClipboardCheck },
    { key: 'client', label: 'Clients', icon: Building2 },
];

const FIELD_TYPES: { value: CustomFieldType; label: string }[] = [
    { value: 'text', label: 'Text' },
    { value: 'textarea', label: 'Text area' },
    { value: 'number', label: 'Number' },
    { value: 'date', label: 'Date' },
    { value: 'boolean', label: 'Yes / No' },
    { value: 'select', label: 'Dropdown' },
    { value: 'multiselect', label: 'Multi-select' },
    { value: 'url', label: 'URL / link' },
];

const OPTION_TYPES = new Set<CustomFieldType>(['select', 'multiselect']);

interface DraftState {
    id?: string;
    label: string;
    field_type: CustomFieldType;
    optionsText: string;   // one option per line
    required: boolean;
    help_text: string;
    placeholder: string;
    show_in_list: boolean;
    show_in_report: boolean;
    is_active: boolean;
}

const emptyDraft = (): DraftState => ({
    label: '', field_type: 'text', optionsText: '', required: false,
    help_text: '', placeholder: '', show_in_list: false, show_in_report: false, is_active: true,
});

export default function CustomFieldsManagement() {
    const [entity, setEntity] = useState<CustomFieldEntity>('finding');
    const [dialogOpen, setDialogOpen] = useState(false);
    const [draft, setDraft] = useState<DraftState>(emptyDraft());
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const { data: defs = [], isLoading } = useCustomFieldDefs(entity, true);
    const createDef = useCreateCustomFieldDef(entity);
    const updateDef = useUpdateCustomFieldDef(entity);
    const deleteDef = useDeleteCustomFieldDef(entity);
    const reorderDefs = useReorderCustomFieldDefs(entity);

    const sorted = [...defs].sort((a, b) => a.position - b.position);

    const openCreate = () => { setDraft(emptyDraft()); setDialogOpen(true); };
    const openEdit = (d: CustomFieldDef) => {
        setDraft({
            id: d.id, label: d.label, field_type: d.field_type,
            optionsText: (d.options || []).join('\n'), required: d.required,
            help_text: d.help_text || '', placeholder: d.placeholder || '',
            show_in_list: d.show_in_list, show_in_report: d.show_in_report, is_active: d.is_active,
        });
        setDialogOpen(true);
    };

    const submit = async () => {
        const label = draft.label.trim();
        if (!label) return;
        const options = OPTION_TYPES.has(draft.field_type)
            ? draft.optionsText.split('\n').map(s => s.trim()).filter(Boolean)
            : undefined;
        if (OPTION_TYPES.has(draft.field_type) && (!options || options.length === 0)) {
            toast.error('Dropdown / multi-select fields need at least one option.');
            return;
        }
        const payload = {
            label,
            field_type: draft.field_type,
            options,
            required: draft.required,
            help_text: draft.help_text.trim() || undefined,
            placeholder: draft.placeholder.trim() || undefined,
            show_in_list: draft.show_in_list,
            show_in_report: draft.show_in_report,
        };
        try {
            if (draft.id) {
                await updateDef.mutateAsync({ id: draft.id, ...payload, is_active: draft.is_active });
                toast.success('Field updated');
            } else {
                await createDef.mutateAsync(payload);
                toast.success('Field created');
            }
            setDialogOpen(false);
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to save field'));
        }
    };

    const remove = async (d: CustomFieldDef) => {
        const ok = await confirm({
            title: 'Delete custom field',
            description: `Delete "${d.label}"? New records won't show it. Values already saved on existing records stay in the database but won't be displayed.`,
            confirmLabel: 'Delete field',
            variant: 'destructive',
        });
        if (!ok) return;
        try {
            await deleteDef.mutateAsync(d.id);
            toast.success(`Deleted "${d.label}"`);
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to delete field'));
        }
    };

    const move = async (index: number, dir: -1 | 1) => {
        const target = index + dir;
        if (target < 0 || target >= sorted.length) return;
        const reordered = [...sorted];
        [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
        try {
            await reorderDefs.mutateAsync(reordered.map((d, i) => ({ id: d.id, position: i })));
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to reorder'));
        }
    };

    const busy = createDef.isPending || updateDef.isPending;

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-white flex items-center gap-2">
                            <ListPlus className="h-5 w-5 text-primary" /> Custom Fields
                        </CardTitle>
                        <CardDescription className="text-slate-400">
                            Define extra fields that appear on the add/edit forms and detail views for each entity.
                        </CardDescription>
                    </div>
                    <Button onClick={openCreate} className="bg-primary hover:bg-primary/90 gap-1.5">
                        <Plus className="h-4 w-4" /> New Field
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Entity selector */}
                <div className="flex flex-wrap gap-2">
                    {ENTITIES.map(e => {
                        const Icon = e.icon;
                        const active = entity === e.key;
                        return (
                            <button
                                key={e.key}
                                onClick={() => setEntity(e.key)}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                                    active ? 'bg-primary/15 text-primary' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                                }`}
                            >
                                <Icon className="h-3.5 w-3.5" /> {e.label}
                            </button>
                        );
                    })}
                </div>

                {/* Field list */}
                {isLoading ? (
                    <div className="py-10 text-center"><Loader2 className="h-5 w-5 animate-spin mx-auto text-slate-600" /></div>
                ) : sorted.length === 0 ? (
                    <p className="text-sm text-slate-500 text-center py-10 border border-dashed border-slate-800 rounded-lg">
                        No custom fields for {ENTITIES.find(e => e.key === entity)?.label} yet.
                    </p>
                ) : (
                    <div className="space-y-1.5">
                        {sorted.map((d, i) => (
                            <div key={d.id} className="flex items-center gap-3 p-3 rounded-lg border border-slate-800 bg-slate-950/40">
                                <div className="flex flex-col">
                                    <button onClick={() => move(i, -1)} disabled={i === 0}
                                        className="text-slate-600 hover:text-slate-300 disabled:opacity-30"><ChevronUp className="h-3.5 w-3.5" /></button>
                                    <button onClick={() => move(i, 1)} disabled={i === sorted.length - 1}
                                        className="text-slate-600 hover:text-slate-300 disabled:opacity-30"><ChevronDown className="h-3.5 w-3.5" /></button>
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="text-sm font-medium text-white">{d.label}</span>
                                        <code className="text-[10px] text-slate-500">{d.field_key}</code>
                                        {!d.is_active && <Badge variant="outline" className="text-[9px] border-slate-700 text-slate-500 gap-1"><EyeOff className="h-2.5 w-2.5" /> Hidden</Badge>}
                                    </div>
                                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                                        <Badge variant="outline" className="text-[9px] border-slate-700 text-slate-400">
                                            {FIELD_TYPES.find(t => t.value === d.field_type)?.label || d.field_type}
                                        </Badge>
                                        {d.required && <Badge className="text-[9px] bg-red-500/10 text-red-400 border-red-500/30">Required</Badge>}
                                        {d.show_in_list && <Badge className="text-[9px] bg-blue-500/10 text-blue-400 border-blue-500/30">In list</Badge>}
                                        {d.show_in_report && <Badge className="text-[9px] bg-emerald-500/10 text-emerald-400 border-emerald-500/30">In report</Badge>}
                                    </div>
                                </div>
                                <Button size="icon" variant="ghost" className="h-8 w-8 text-slate-500 hover:text-white" onClick={() => openEdit(d)}>
                                    <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                <Button size="icon" variant="ghost" className="h-8 w-8 text-slate-500 hover:text-red-400" onClick={() => remove(d)}>
                                    <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>

            {/* Create / edit dialog */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[520px] max-h-[85vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>{draft.id ? 'Edit Custom Field' : 'New Custom Field'}</DialogTitle>
                        <DialogDescription className="text-slate-400">
                            On {ENTITIES.find(e => e.key === entity)?.label}. {draft.id ? 'The field key is fixed once created.' : 'A stable key is generated from the label.'}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-2">
                        <div className="space-y-1.5">
                            <Label className="text-xs text-slate-400">Label</Label>
                            <Input value={draft.label} onChange={e => setDraft({ ...draft, label: e.target.value })}
                                placeholder="e.g. Business Owner" className="bg-slate-950 border-slate-700 text-white" autoFocus />
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                                <Label className="text-xs text-slate-400">Type</Label>
                                <Select value={draft.field_type} onValueChange={(v) => setDraft({ ...draft, field_type: v as CustomFieldType })}>
                                    <SelectTrigger className="bg-slate-950 border-slate-700 text-white"><SelectValue /></SelectTrigger>
                                    <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                        {FIELD_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="flex items-end pb-1">
                                <label className="flex items-center gap-2 text-sm text-slate-300">
                                    <Switch checked={draft.required} onCheckedChange={v => setDraft({ ...draft, required: v })} />
                                    Required
                                </label>
                            </div>
                        </div>

                        {OPTION_TYPES.has(draft.field_type) && (
                            <div className="space-y-1.5">
                                <Label className="text-xs text-slate-400">Options (one per line)</Label>
                                <Textarea value={draft.optionsText} onChange={e => setDraft({ ...draft, optionsText: e.target.value })}
                                    placeholder={'Production\nStaging\nDevelopment'} className="bg-slate-950 border-slate-700 text-white min-h-[90px]" />
                            </div>
                        )}

                        <div className="space-y-1.5">
                            <Label className="text-xs text-slate-400">Help text <span className="text-slate-600">(optional)</span></Label>
                            <Input value={draft.help_text} onChange={e => setDraft({ ...draft, help_text: e.target.value })}
                                placeholder="Shown under the field" className="bg-slate-950 border-slate-700 text-white" />
                        </div>

                        {draft.field_type !== 'boolean' && draft.field_type !== 'multiselect' && (
                            <div className="space-y-1.5">
                                <Label className="text-xs text-slate-400">Placeholder <span className="text-slate-600">(optional)</span></Label>
                                <Input value={draft.placeholder} onChange={e => setDraft({ ...draft, placeholder: e.target.value })}
                                    className="bg-slate-950 border-slate-700 text-white" />
                            </div>
                        )}

                        <div className="space-y-2 pt-1">
                            <label className="flex items-center justify-between text-sm text-slate-300">
                                Show as a column in the list view
                                <Switch checked={draft.show_in_list} onCheckedChange={v => setDraft({ ...draft, show_in_list: v })} />
                            </label>
                            <label className="flex items-center justify-between text-sm text-slate-300">
                                Include in generated reports
                                <Switch checked={draft.show_in_report} onCheckedChange={v => setDraft({ ...draft, show_in_report: v })} />
                            </label>
                            {draft.id && (
                                <label className="flex items-center justify-between text-sm text-slate-300">
                                    Active (uncheck to hide without deleting)
                                    <Switch checked={draft.is_active} onCheckedChange={v => setDraft({ ...draft, is_active: v })} />
                                </label>
                            )}
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setDialogOpen(false)} disabled={busy}>Cancel</Button>
                        <Button onClick={submit} disabled={!draft.label.trim() || busy}
                            className="bg-primary hover:bg-primary/90 text-primary-foreground">
                            {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
                            {draft.id ? 'Save' : 'Create'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <ConfirmDialog />
        </Card>
    );
}

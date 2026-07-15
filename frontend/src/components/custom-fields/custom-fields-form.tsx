'use client';

/**
 * CustomFieldsForm — renders the admin-defined custom fields for an entity as
 * form inputs. Drop into any create/edit form: it fetches the active
 * definitions for `entity`, renders an input per field by type, and reports
 * changes through `onChange` as a { field_key: value } dict. Renders nothing
 * when the entity has no active custom fields.
 */

import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import {
    useCustomFieldDefs, type CustomFieldEntity, type CustomFieldDef, type CustomFieldValues,
} from '@/lib/hooks/use-custom-fields';

interface CustomFieldsFormProps {
    entity: CustomFieldEntity;
    value: CustomFieldValues | undefined | null;
    onChange: (next: CustomFieldValues) => void;
    disabled?: boolean;
    /** Hide the "Custom Fields" heading (e.g. when embedded in a titled card). */
    hideHeading?: boolean;
    className?: string;
}

export function CustomFieldsForm({
    entity, value, onChange, disabled, hideHeading, className,
}: CustomFieldsFormProps) {
    const { data: defs = [] } = useCustomFieldDefs(entity);
    const values = value || {};

    if (defs.length === 0) return null;

    const setField = (fieldKey: string, v: unknown) => {
        onChange({ ...values, [fieldKey]: v });
    };

    return (
        <div className={cn('space-y-4', className)}>
            {!hideHeading && (
                <h3 className="text-sm font-semibold text-slate-200 tracking-wide uppercase">Custom Fields</h3>
            )}
            <div className="space-y-4">
                {defs.map(def => (
                    <FieldInput
                        key={def.id}
                        def={def}
                        value={values[def.field_key]}
                        onChange={(v) => setField(def.field_key, v)}
                        disabled={disabled}
                    />
                ))}
            </div>
        </div>
    );
}

function FieldInput({ def, value, onChange, disabled }: {
    def: CustomFieldDef; value: unknown; onChange: (v: unknown) => void; disabled?: boolean;
}) {
    const labelEl = (
        <Label className="text-slate-300 text-sm flex items-center gap-1">
            {def.label}
            {def.required && <span className="text-red-400">*</span>}
        </Label>
    );
    const help = def.help_text ? (
        <p className="text-[11px] text-slate-500">{def.help_text}</p>
    ) : null;

    // Boolean renders label + switch on one row.
    if (def.field_type === 'boolean') {
        return (
            <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                    {labelEl}
                    <Switch checked={!!value} onCheckedChange={onChange} disabled={disabled} />
                </div>
                {help}
            </div>
        );
    }

    let control: React.ReactNode;
    switch (def.field_type) {
        case 'textarea':
            control = (
                <Textarea
                    value={(value as string) ?? ''}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={def.placeholder ?? ''}
                    disabled={disabled}
                    className="bg-slate-950 border-slate-700 text-white min-h-[80px]"
                />
            );
            break;
        case 'number':
            control = (
                <Input
                    type="number"
                    value={(value as number | string) ?? ''}
                    onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
                    placeholder={def.placeholder ?? ''}
                    disabled={disabled}
                    className="bg-slate-950 border-slate-700 text-white"
                />
            );
            break;
        case 'date':
            control = (
                <Input
                    type="date"
                    value={(value as string) ?? ''}
                    onChange={(e) => onChange(e.target.value)}
                    disabled={disabled}
                    className="bg-slate-950 border-slate-700 text-white w-48"
                />
            );
            break;
        case 'url':
            control = (
                <Input
                    type="url"
                    value={(value as string) ?? ''}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={def.placeholder ?? 'https://…'}
                    disabled={disabled}
                    className="bg-slate-950 border-slate-700 text-white"
                />
            );
            break;
        case 'select':
            control = (
                <Select
                    value={(value as string) || ''}
                    onValueChange={(v) => onChange(v === '__clear__' ? '' : v)}
                    disabled={disabled}
                >
                    <SelectTrigger className="bg-slate-950 border-slate-700 text-white">
                        <SelectValue placeholder={def.placeholder || 'Select…'} />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-900 border-slate-800 text-white">
                        {!def.required && <SelectItem value="__clear__" className="text-slate-500">— None —</SelectItem>}
                        {(def.options || []).map(opt => (
                            <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            );
            break;
        case 'multiselect': {
            const selected: string[] = Array.isArray(value) ? (value as string[]) : [];
            const toggle = (opt: string) => {
                onChange(selected.includes(opt) ? selected.filter(o => o !== opt) : [...selected, opt]);
            };
            control = (
                <div className="flex flex-wrap gap-1.5">
                    {(def.options || []).map(opt => {
                        const on = selected.includes(opt);
                        return (
                            <button
                                type="button"
                                key={opt}
                                onClick={() => toggle(opt)}
                                disabled={disabled}
                                className={cn(
                                    'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                                    on
                                        ? 'bg-primary/15 border-primary/40 text-primary'
                                        : 'bg-slate-950 border-slate-700 text-slate-400 hover:border-slate-600',
                                )}
                            >
                                {opt}
                            </button>
                        );
                    })}
                </div>
            );
            break;
        }
        default: // text
            control = (
                <Input
                    value={(value as string) ?? ''}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={def.placeholder ?? ''}
                    disabled={disabled}
                    className="bg-slate-950 border-slate-700 text-white"
                />
            );
    }

    return (
        <div className="space-y-1.5">
            {labelEl}
            {control}
            {help}
        </div>
    );
}

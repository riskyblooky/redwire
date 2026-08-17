'use client';

/**
 * CustomFieldsDisplay — read-only render of an entity's custom field values on
 * a detail/view page. Fetches the active definitions for `entity` so labels
 * and types are right, and only shows fields that actually have a value.
 * Renders nothing when the entity has no active fields or no values set.
 */

import { useState } from 'react';
import { ExternalLink, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import {
    useCustomFieldDefs, type CustomFieldEntity, type CustomFieldDef, type CustomFieldValues,
} from '@/lib/hooks/use-custom-fields';

interface CustomFieldsDisplayProps {
    entity: CustomFieldEntity;
    value: CustomFieldValues | undefined | null;
    /** Section heading text; pass null to omit. */
    heading?: string | null;
    className?: string;
    /** Make the heading a collapse toggle (shows a count + chevron). */
    collapsible?: boolean;
    /** When collapsible, start collapsed. */
    defaultCollapsed?: boolean;
}

function hasValue(v: unknown): boolean {
    if (v === null || v === undefined || v === '') return false;
    if (Array.isArray(v) && v.length === 0) return false;
    return true;
}

export function CustomFieldsDisplay({
    entity, value, heading = 'Custom Fields', className, collapsible, defaultCollapsed,
}: CustomFieldsDisplayProps) {
    const { data: defs = [] } = useCustomFieldDefs(entity);
    const values = value || {};
    const [open, setOpen] = useState(!defaultCollapsed);

    const shown = defs.filter(d => hasValue(values[d.field_key]));
    if (shown.length === 0) return null;

    const grid = (
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
            {shown.map(def => (
                <div key={def.id} className="space-y-0.5">
                    <dt className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{def.label}</dt>
                    <dd className="text-sm text-slate-200"><FieldValue def={def} value={values[def.field_key]} /></dd>
                </div>
            ))}
        </dl>
    );

    if (collapsible && heading) {
        return (
            <div className={cn('space-y-3', className)}>
                <button
                    type="button"
                    onClick={() => setOpen(o => !o)}
                    className="flex w-full items-center gap-1.5 text-xs font-bold text-slate-400 tracking-widest uppercase hover:text-slate-200 transition-colors"
                >
                    <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-90')} />
                    {heading}
                    <span className="ml-1 text-[10px] font-medium text-slate-600 normal-case tracking-normal">
                        {shown.length} field{shown.length === 1 ? '' : 's'}
                    </span>
                </button>
                {open && grid}
            </div>
        );
    }

    return (
        <div className={cn('space-y-3', className)}>
            {heading && (
                <h3 className="text-xs font-bold text-slate-400 tracking-widest uppercase">{heading}</h3>
            )}
            {grid}
        </div>
    );
}

function FieldValue({ def, value }: { def: CustomFieldDef; value: unknown }) {
    switch (def.field_type) {
        case 'boolean':
            return <span>{value ? 'Yes' : 'No'}</span>;
        case 'url': {
            const url = String(value);
            return (
                <a href={url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-primary hover:underline break-all">
                    {url}
                    <ExternalLink className="h-3 w-3 shrink-0" />
                </a>
            );
        }
        case 'multiselect': {
            const items: string[] = Array.isArray(value) ? (value as string[]) : [];
            return (
                <span className="flex flex-wrap gap-1">
                    {items.map(i => (
                        <span key={i} className="px-2 py-0.5 rounded-full text-xs bg-slate-800 text-slate-300 border border-slate-700">{i}</span>
                    ))}
                </span>
            );
        }
        case 'text':
        case 'textarea':
            // Authored with the rich editor — render as Markdown.
            return <div className="text-sm"><MarkdownPreview value={String(value)} /></div>;
        default:
            return <span className="whitespace-pre-wrap break-words">{String(value)}</span>;
    }
}

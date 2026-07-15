'use client';

/**
 * Reusable table fragments for showing custom fields flagged `show_in_list`
 * as columns in an entity's list view. Drop <CustomFieldListHeads> into the
 * header row and <CustomFieldListCells> into each body row — both are
 * fragments of <TableHead>/<TableCell> so they slot straight into a shadcn
 * <TableRow>. Render nothing when no field opts into the list.
 */

import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import { TableHead, TableCell } from '@/components/ui/table';
import { cn } from '@/lib/utils';
import {
    useCustomFieldDefs, type CustomFieldEntity, type CustomFieldDef, type CustomFieldValues,
} from '@/lib/hooks/use-custom-fields';
import type { ColumnDef } from '@/lib/hooks/use-column-visibility';

/** Column key for a custom field in the column-visibility / sort systems. */
export const cfColumnKey = (fieldKey: string) => `cf:${fieldKey}`;

/** Comparator for two custom-field values — numeric when both parse as
 *  numbers, else case-insensitive string; nulls/empties sort last. */
export function compareCustomFieldValues(a: unknown, b: unknown): number {
    const empty = (v: unknown) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
    if (empty(a) && empty(b)) return 0;
    if (empty(a)) return 1;
    if (empty(b)) return -1;
    const an = Number(a), bn = Number(b);
    if (!Number.isNaN(an) && !Number.isNaN(bn)) return an - bn;
    return String(a).localeCompare(String(b));
}

function listDefs(defs: CustomFieldDef[]): CustomFieldDef[] {
    return defs.filter(d => d.show_in_list);
}

/** Active show_in_list custom-field definitions for an entity. */
export function useCustomFieldListDefs(entity: CustomFieldEntity): CustomFieldDef[] {
    const { data: defs = [] } = useCustomFieldDefs(entity);
    return listDefs(defs);
}

/** ColumnDef entries for an entity's list custom fields — merge into a tab's
 *  column array so they show up in the ColumnToggle. */
export function customFieldColumnDefs(defs: CustomFieldDef[]): ColumnDef[] {
    return defs.map(d => ({ key: cfColumnKey(d.field_key), label: d.label }));
}

// `isVisible`, when passed, gates each custom column by the tab's column
// toggle. `onSort`/`sortField`/`sortOrder`, when passed, make the headers
// clickable to sort (key is the cf column key). Omit both on standalone list
// pages with no toggle/sort.
export function CustomFieldListHeads({ entity, isVisible, sortField, sortOrder, onSort }: {
    entity: CustomFieldEntity;
    isVisible?: (key: string) => boolean;
    sortField?: string;
    sortOrder?: 'asc' | 'desc';
    onSort?: (key: string) => void;
}) {
    const defs = useCustomFieldListDefs(entity);
    return (
        <>
            {defs.filter(d => !isVisible || isVisible(cfColumnKey(d.field_key))).map(d => {
                const key = cfColumnKey(d.field_key);
                const active = sortField === key;
                return (
                    <TableHead
                        key={d.id}
                        onClick={onSort ? () => onSort(key) : undefined}
                        className={cn(
                            'text-slate-300 font-semibold whitespace-nowrap',
                            onSort && 'cursor-pointer hover:text-white transition-colors',
                        )}
                    >
                        <div className="flex items-center gap-1">
                            {d.label}
                            {onSort && (
                                active
                                    ? (sortOrder === 'asc'
                                        ? <ChevronUp className="h-3.5 w-3.5" />
                                        : <ChevronDown className="h-3.5 w-3.5" />)
                                    : <ChevronsUpDown className="h-3.5 w-3.5 opacity-30" />
                            )}
                        </div>
                    </TableHead>
                );
            })}
        </>
    );
}

function renderCell(def: CustomFieldDef, value: unknown): React.ReactNode {
    if (value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)) {
        return <span className="text-slate-600">—</span>;
    }
    if (def.field_type === 'boolean') return value ? 'Yes' : 'No';
    if (def.field_type === 'url') {
        const url = String(value);
        return (
            <a href={url} target="_blank" rel="noopener noreferrer"
                className="text-primary hover:underline truncate inline-block max-w-[160px] align-bottom">
                {url}
            </a>
        );
    }
    if (Array.isArray(value)) return value.join(', ');
    return String(value);
}

export function CustomFieldListCells({ entity, value, isVisible }: {
    entity: CustomFieldEntity; value: CustomFieldValues | undefined | null;
    isVisible?: (key: string) => boolean;
}) {
    const defs = useCustomFieldListDefs(entity);
    const cf = value || {};
    return (
        <>
            {defs.filter(d => !isVisible || isVisible(cfColumnKey(d.field_key))).map(d => (
                <TableCell key={d.id} className="text-slate-400 text-sm max-w-[200px] truncate">
                    {renderCell(d, cf[d.field_key])}
                </TableCell>
            ))}
        </>
    );
}

/** Number of list columns for an entity — for colSpan on empty-state rows. */
export function useCustomFieldListCount(entity: CustomFieldEntity): number {
    const { data: defs = [] } = useCustomFieldDefs(entity);
    return listDefs(defs).length;
}

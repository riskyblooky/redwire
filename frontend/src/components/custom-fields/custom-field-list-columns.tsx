'use client';

/**
 * Reusable table fragments for showing custom fields flagged `show_in_list`
 * as columns in an entity's list view. Drop <CustomFieldListHeads> into the
 * header row and <CustomFieldListCells> into each body row — both are
 * fragments of <TableHead>/<TableCell> so they slot straight into a shadcn
 * <TableRow>. Render nothing when no field opts into the list.
 */

import { TableHead, TableCell } from '@/components/ui/table';
import {
    useCustomFieldDefs, type CustomFieldEntity, type CustomFieldDef, type CustomFieldValues,
} from '@/lib/hooks/use-custom-fields';

function listDefs(defs: CustomFieldDef[]): CustomFieldDef[] {
    return defs.filter(d => d.show_in_list);
}

export function CustomFieldListHeads({ entity }: { entity: CustomFieldEntity }) {
    const { data: defs = [] } = useCustomFieldDefs(entity);
    return (
        <>
            {listDefs(defs).map(d => (
                <TableHead key={d.id} className="text-slate-300 font-semibold whitespace-nowrap">
                    {d.label}
                </TableHead>
            ))}
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

export function CustomFieldListCells({ entity, value }: {
    entity: CustomFieldEntity; value: CustomFieldValues | undefined | null;
}) {
    const { data: defs = [] } = useCustomFieldDefs(entity);
    const cf = value || {};
    return (
        <>
            {listDefs(defs).map(d => (
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

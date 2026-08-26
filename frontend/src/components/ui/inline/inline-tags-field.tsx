'use client';

import { useState, useEffect } from 'react';
import { TagList, TagListTag } from '@/components/ui/tag-list';
import { Button } from '@/components/ui/button';
import { Loader2, Pencil, Check, Tag as TagIcon } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface InlineTagsFieldProps {
    /** Current tags, for the read view. */
    tags?: TagListTag[];
    /** All selectable tags for this entity type. */
    allTags: { id: string; name: string; color?: string | null }[];
    selectedIds: string[];
    onSave: (ids: string[]) => Promise<void>;
    canEdit?: boolean;
    max?: number;
}

/**
 * Tags that read as a TagList and, on double-click (for editors), expand into a
 * compact chip picker with Save/Cancel. Toggling chips stages the selection;
 * Save commits the full tag_ids set via the caller's onSave.
 */
export function InlineTagsField({
    tags = [],
    allTags,
    selectedIds,
    onSave,
    canEdit = false,
    max = 6,
}: InlineTagsFieldProps) {
    const [editing, setEditing] = useState(false);
    const [saving, setSaving] = useState(false);
    const [selected, setSelected] = useState<Set<string>>(new Set(selectedIds));

    useEffect(() => {
        if (editing) setSelected(new Set(selectedIds));
    }, [editing]); // eslint-disable-line react-hooks/exhaustive-deps

    const toggle = (id: string) => {
        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const save = async () => {
        setSaving(true);
        try {
            await onSave([...selected]);
            setEditing(false);
            toast.success('Tags updated');
        } catch (e: any) {
            toast.error(e?.response?.data?.detail || e?.message || 'Failed to update tags');
        } finally {
            setSaving(false);
        }
    };

    if (editing && canEdit) {
        return (
            <div className="rounded-lg border border-slate-700 bg-slate-950/40 p-2 space-y-2 max-w-md">
                <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
                    {allTags.length === 0 && <span className="text-xs text-slate-500 italic p-1">No tags defined for this type.</span>}
                    {allTags.map(t => {
                        const on = selected.has(t.id);
                        const color = t.color || '#64748b';
                        return (
                            <button
                                key={t.id}
                                type="button"
                                onClick={() => toggle(t.id)}
                                className={cn(
                                    'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border transition-colors',
                                    on ? 'text-white' : 'text-slate-400 border-slate-700 hover:border-slate-600'
                                )}
                                style={on ? { backgroundColor: `${color}25`, borderColor: `${color}80`, color } : undefined}
                            >
                                {on && <Check className="h-3 w-3" />}
                                {t.name}
                            </button>
                        );
                    })}
                </div>
                <div className="flex items-center justify-end gap-2 pt-1 border-t border-slate-800/60">
                    <Button variant="ghost" size="sm" className="h-6 text-slate-400 hover:text-white" onClick={() => setEditing(false)} disabled={saving}>Cancel</Button>
                    <Button size="sm" className="h-6 bg-primary hover:bg-primary/90 text-white" onClick={save} disabled={saving}>
                        {saving ? <><Loader2 className="h-3 w-3 animate-spin mr-1" /> Saving</> : 'Save'}
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <span
            className="group/inline relative inline-flex items-center gap-1"
            onDoubleClick={() => canEdit && setEditing(true)}
            title={canEdit ? 'Double-click to edit tags' : undefined}
        >
            {tags.length > 0
                ? <TagList tags={tags} max={max} />
                : canEdit && <span className="text-xs text-slate-600 italic">no tags</span>}
            {canEdit && (
                <button
                    type="button"
                    onClick={() => setEditing(true)}
                    className="p-0.5 rounded opacity-0 group-hover/inline:opacity-100 text-slate-500 hover:text-white transition-opacity"
                    title="Edit tags"
                    aria-label="Edit tags"
                >
                    <Pencil className="h-3 w-3" />
                </button>
            )}
        </span>
    );
}

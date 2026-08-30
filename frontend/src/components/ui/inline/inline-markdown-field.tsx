'use client';

import { useState, KeyboardEvent } from 'react';
import { MarkdownEditor, MarkdownPreview } from '@/components/ui/markdown-editor';
import { Button } from '@/components/ui/button';
import { Loader2, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { EditorFieldContext } from '@/lib/types';

interface InlineMarkdownFieldProps {
    value: string;
    onSave: (value: string) => Promise<void>;
    canEdit?: boolean;
    /** Passed to the editor for image paste/drop upload + version context. */
    engagementId?: string;
    fieldContext?: EditorFieldContext;
    /** Classes for the wrapper around the read-only MarkdownPreview (e.g. prose). */
    previewWrapperClassName?: string;
    /** Shown (muted) in the read view when the value is empty and editing is allowed. */
    emptyText?: string;
    placeholder?: string;
    minHeight?: string;
}

/**
 * A markdown field that reads as rendered markdown and, on double-click (for
 * users who can edit), swaps to the shared MarkdownEditor with Save/Cancel.
 * Esc cancels, ⌘/Ctrl+Enter saves. Saves a single field via the caller's
 * onSave; on failure it stays in edit mode so the draft isn't lost.
 */
export function InlineMarkdownField({
    value,
    onSave,
    canEdit = false,
    engagementId,
    fieldContext,
    previewWrapperClassName,
    emptyText = 'Double-click to add…',
    placeholder,
    minHeight = '180px',
}: InlineMarkdownFieldProps) {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState('');
    const [saving, setSaving] = useState(false);

    const start = () => {
        if (!canEdit || saving) return;
        setDraft(value || '');
        setEditing(true);
    };

    const cancel = () => {
        if (saving) return;
        setEditing(false);
    };

    const save = async () => {
        if (saving) return;
        setSaving(true);
        try {
            await onSave(draft);
            setEditing(false);
            toast.success('Saved');
        } catch (e: any) {
            toast.error(e?.response?.data?.detail || e?.message || 'Failed to save');
            // Stay in edit mode so the draft survives.
        } finally {
            setSaving(false);
        }
    };

    const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Escape') { e.preventDefault(); cancel(); }
        else if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); save(); }
    };

    if (editing) {
        return (
            <div onKeyDown={onKeyDown}>
                <div className="rounded-lg border border-slate-700 overflow-hidden">
                    <MarkdownEditor
                        value={draft}
                        onChange={setDraft}
                        engagementId={engagementId}
                        fieldContext={fieldContext}
                        placeholder={placeholder}
                        minHeight={minHeight}
                        resizable
                        disabled={saving}
                    />
                </div>
                <div className="flex items-center justify-between mt-2">
                    <span className="text-[10px] text-slate-500">Drag the bottom edge to resize · ⌘/Ctrl+Enter to save · Esc to cancel</span>
                    <div className="flex gap-2">
                        <Button variant="ghost" size="sm" className="h-7 text-slate-400 hover:text-white" onClick={cancel} disabled={saving}>Cancel</Button>
                        <Button size="sm" className="h-7 bg-primary hover:bg-primary/90 text-white" onClick={save} disabled={saving}>
                            {saving ? <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> Saving</> : 'Save'}
                        </Button>
                    </div>
                </div>
            </div>
        );
    }

    const hasValue = !!(value && value.trim());

    return (
        <div
            className={cn('group/inline relative', canEdit && 'rounded-md transition-colors hover:bg-slate-800/20')}
            onDoubleClick={start}
            title={canEdit ? 'Double-click to edit' : undefined}
        >
            {canEdit && (
                <button
                    type="button"
                    onClick={start}
                    className="absolute top-1 right-1 z-10 p-1 rounded opacity-0 group-hover/inline:opacity-100 bg-slate-800/80 text-slate-400 hover:text-white transition-opacity"
                    title="Edit"
                    aria-label="Edit"
                >
                    <Pencil className="h-3 w-3" />
                </button>
            )}
            {hasValue ? (
                <div className={previewWrapperClassName}>
                    <MarkdownPreview value={value} theme="dark" />
                </div>
            ) : (
                <p className="text-sm text-slate-600 italic select-none py-1">
                    {canEdit ? emptyText : '—'}
                </p>
            )}
        </div>
    );
}

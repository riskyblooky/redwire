'use client';

import { useEffect, useRef, useState, KeyboardEvent } from 'react';
import { MarkdownEditor, MarkdownPreview } from '@/components/ui/markdown-editor';
import { Button } from '@/components/ui/button';
import { Loader2, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { EditorFieldContext } from '@/lib/types';
import { AnnotatableMarkdownField } from '@/components/discussions/annotatable-markdown-field';
import type { ResourceType } from '@/lib/hooks/use-discussions';
import type { EditorChangeMeta } from '@/components/ui/tiptap-editor';
import { isLiveField } from '@/lib/collab-fields';
import { collabFieldPath } from '@/components/discussions/annotation-surface';

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
    /** Opt-in: enable anchored peer-review comments on this field. Requires
     *  resourceType/resourceId/field/engagementId. Absent → plain behaviour. */
    annotatable?: boolean;
    resourceType?: ResourceType;
    resourceId?: string;
    field?: string;
    /** Live co-editing. Defaults on whenever resourceType/resourceId/field
     *  name a live field (lib/collab-fields.ts) — the editor then shares the
     *  full edit page's room for that field. Pass false to opt out. */
    collaborative?: boolean;
}

/**
 * A markdown field that reads as rendered markdown and, on double-click (for
 * users who can edit), swaps to the shared MarkdownEditor with Save/Cancel.
 * Esc cancels, ⌘/Ctrl+Enter saves. Saves a single field via the caller's
 * onSave; on failure it stays in edit mode so the draft isn't lost.
 *
 * For live fields the editor joins the field's room instead: edits sync with
 * the edit page and other inline editors and save themselves as you type,
 * and the bar shows Done (the REST onSave only covers edits made offline).
 */
export function InlineMarkdownField(props: InlineMarkdownFieldProps) {
    const live = props.collaborative !== false && !!props.resourceId && isLiveField(props.resourceType, props.field);
    // Anchored peer-review comments are a self-contained superset; delegate to it
    // when the caller opts in. Kept as a separate component (not an early return
    // inside the body) so the plain path's hooks are never conditional.
    if (props.annotatable && props.resourceType && props.resourceId && props.field && props.engagementId) {
        return (
            <AnnotatableMarkdownField
                value={props.value}
                onSave={props.onSave}
                canEdit={props.canEdit}
                engagementId={props.engagementId}
                resourceType={props.resourceType}
                resourceId={props.resourceId}
                field={props.field}
                fieldContext={props.fieldContext}
                previewWrapperClassName={props.previewWrapperClassName}
                emptyText={props.emptyText}
                placeholder={props.placeholder}
                minHeight={props.minHeight}
                collaborative={live}
            />
        );
    }
    return <PlainInlineMarkdownField {...props} collaborative={live} />;
}

function PlainInlineMarkdownField({
    value,
    onSave,
    canEdit = false,
    engagementId,
    fieldContext,
    previewWrapperClassName,
    emptyText = 'Double-click to add…',
    placeholder,
    minHeight = '180px',
    resourceType,
    resourceId,
    field,
    collaborative = false,
}: InlineMarkdownFieldProps) {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState('');
    const [saving, setSaving] = useState(false);
    // Live mode (see AnnotatableMarkdownField): offline edits need the REST
    // save on Done; show the just-written text until the record refetches.
    const unsyncedRef = useRef(false);
    const [shownAfterClose, setShownAfterClose] = useState<string | null>(null);
    useEffect(() => { setShownAfterClose(null); }, [value]);
    const shown = shownAfterClose ?? value;

    const start = () => {
        if (!canEdit || saving) return;
        setDraft(shown || '');
        unsyncedRef.current = false;
        setEditing(true);
    };

    const onDraftChange = (val: string, meta?: EditorChangeMeta) => {
        setDraft(val);
        if (!meta?.autosaved) unsyncedRef.current = true;
    };

    const done = async () => {
        if (saving) return;
        if (unsyncedRef.current && draft !== (shown || '')) {
            setSaving(true);
            try {
                await onSave(draft);
            } catch (e: any) {
                toast.error(e?.response?.data?.detail || e?.message || 'Failed to save');
                return;
            } finally {
                setSaving(false);
            }
        }
        setShownAfterClose(draft);
        setEditing(false);
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
        if (e.key === 'Escape') { e.preventDefault(); if (collaborative) done(); else cancel(); }
        else if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); if (collaborative) done(); else save(); }
    };

    if (editing && collaborative && resourceType && resourceId && field) {
        return (
            <div onKeyDown={onKeyDown}>
                <div className="rounded-lg border border-slate-700 overflow-hidden">
                    <MarkdownEditor
                        value={draft}
                        onChange={onDraftChange}
                        engagementId={engagementId}
                        fieldContext={fieldContext}
                        placeholder={placeholder}
                        minHeight={minHeight}
                        resizable
                        disabled={saving}
                        collab={{ path: collabFieldPath(resourceType, resourceId, field) }}
                    />
                </div>
                <div className="flex items-center justify-between mt-2">
                    <span className="text-[10px] text-slate-500">Live — saves as you type and syncs with anyone else editing this field · Esc or ⌘/Ctrl+Enter to finish</span>
                    <Button size="sm" className="h-7 bg-primary hover:bg-primary/90 text-white" onClick={done} disabled={saving}>
                        {saving ? <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> Saving</> : 'Done'}
                    </Button>
                </div>
            </div>
        );
    }

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

    const hasValue = !!(shown && shown.trim());

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
                    <MarkdownPreview value={shown} theme="dark" />
                </div>
            ) : (
                <p className="text-sm text-slate-600 italic select-none py-1">
                    {canEdit ? emptyText : '—'}
                </p>
            )}
        </div>
    );
}

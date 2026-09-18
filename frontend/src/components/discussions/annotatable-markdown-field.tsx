'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { Button } from '@/components/ui/button';
import { Loader2, Pencil, MessageSquare } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { EditorFieldContext } from '@/lib/types';
import { useThreads, type ResourceType } from '@/lib/hooks/use-discussions';
import { useAnchoredComments } from './anchored-comments-context';
import { AnnotationSurface, type AnnotationSurfaceHandle } from './annotation-surface';

export interface AnnotatableMarkdownFieldProps {
    value: string;
    onSave: (value: string) => Promise<void>;
    canEdit?: boolean;
    engagementId: string;
    resourceType: ResourceType;
    resourceId: string;
    field: string;
    fieldContext?: EditorFieldContext;
    previewWrapperClassName?: string;
    emptyText?: string;
    placeholder?: string;
    minHeight?: string;
}

/**
 * A markdown field with anchored peer-review comments. In view mode it reads as
 * rendered markdown (with a comment-count chip); double-clicking — or clicking
 * the chip — enters "annotation mode" (the shared AnnotationSurface: a TipTap
 * editor with comment highlights beside a comment rail). Editable for those who
 * can edit the field, read-only (but still comment-able) for reviewers who can't.
 * Anchors are refreshed on Save. See docs/anchored-comments-peer-review.md.
 */
export function AnnotatableMarkdownField({
    value, onSave, canEdit = false, engagementId, resourceType, resourceId, field,
    fieldContext, previewWrapperClassName, emptyText = 'Double-click to add…', placeholder, minHeight = '260px',
}: AnnotatableMarkdownFieldProps) {
    const [mode, setMode] = useState<'view' | 'annotate'>('view');
    const [draft, setDraft] = useState('');
    const [saving, setSaving] = useState(false);
    const [pendingActive, setPendingActive] = useState<string | null>(null);
    const surfaceRef = useRef<AnnotationSurfaceHandle>(null);

    const { data: allThreads = [] } = useThreads({ engagement_id: engagementId, resource_type: resourceType, resource_id: resourceId });
    const anchored = useAnchoredComments();

    const fieldThreads = useMemo(
        () => allThreads.filter((t) => t.anchor && t.anchor.field === field),
        [allThreads, field],
    );
    const unresolvedCount = fieldThreads.filter((t) => !t.is_resolved).length;

    const enterAnnotate = useCallback((focusId?: string) => {
        setDraft(value || '');
        setPendingActive(focusId ?? null);
        setMode('annotate');
    }, [value]);

    // Let the page-level rail open this field.
    useEffect(() => anchored.registerOpener(field, (threadId) => enterAnnotate(threadId)), [anchored, field, enterAnnotate]);

    const save = async () => {
        if (saving) return;
        setSaving(true);
        try {
            await onSave(draft);
            surfaceRef.current?.refreshAnchors();
            setMode('view');
            toast.success('Saved');
        } catch (e: any) {
            toast.error(e?.response?.data?.detail || e?.message || 'Failed to save');
        } finally {
            setSaving(false);
        }
    };

    // ── View mode ────────────────────────────────────────────────────────
    if (mode === 'view') {
        const hasValue = !!(value && value.trim());
        return (
            <div
                className={cn('group/inline relative', 'rounded-md transition-colors hover:bg-slate-800/20')}
                onDoubleClick={() => enterAnnotate()}
                title="Double-click to open"
            >
                <div className="absolute top-1 right-1 z-10 flex items-center gap-1">
                    {fieldThreads.length > 0 && (
                        <button
                            type="button"
                            onClick={() => enterAnnotate(fieldThreads[0]?.id)}
                            className={cn(
                                'flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold transition-colors',
                                unresolvedCount > 0 ? 'bg-amber-500/15 text-amber-300 hover:bg-amber-500/25' : 'bg-slate-700/50 text-slate-300 hover:bg-slate-700',
                            )}
                            title={`${fieldThreads.length} comment${fieldThreads.length === 1 ? '' : 's'} (${unresolvedCount} open)`}
                        >
                            <MessageSquare className="h-3 w-3" />
                            {unresolvedCount > 0 ? unresolvedCount : fieldThreads.length}
                        </button>
                    )}
                    {canEdit && (
                        <button
                            type="button"
                            onClick={() => enterAnnotate()}
                            className="p-1 rounded opacity-0 group-hover/inline:opacity-100 bg-slate-800/80 text-slate-400 hover:text-white transition-opacity"
                            title="Edit"
                            aria-label="Edit"
                        >
                            <Pencil className="h-3 w-3" />
                        </button>
                    )}
                </div>
                {hasValue ? (
                    <div className={previewWrapperClassName}><MarkdownPreview value={value} theme="dark" /></div>
                ) : (
                    <p className="text-sm text-slate-600 italic select-none py-1">{canEdit ? emptyText : '—'}</p>
                )}
            </div>
        );
    }

    // ── Annotation mode ──────────────────────────────────────────────────
    return (
        <AnnotationSurface
            ref={surfaceRef}
            value={draft}
            onChange={setDraft}
            canEdit={canEdit}
            engagementId={engagementId}
            resourceType={resourceType}
            resourceId={resourceId}
            field={field}
            fieldContext={fieldContext}
            minHeight={minHeight}
            placeholder={placeholder}
            focusThreadId={pendingActive}
            footer={
                <div className="flex items-center justify-between mt-2">
                    <span className="text-[10px] text-slate-500">
                        {canEdit ? 'Select text to comment · ' : 'Read-only — select text to comment · '}
                        highlights show anchored review comments
                    </span>
                    <div className="flex gap-2">
                        <Button variant="ghost" size="sm" className="h-7 text-slate-400 hover:text-white" onClick={() => setMode('view')} disabled={saving}>
                            {canEdit ? 'Cancel' : 'Close'}
                        </Button>
                        {canEdit && (
                            <Button size="sm" className="h-7 bg-primary hover:bg-primary/90 text-white" onClick={save} disabled={saving}>
                                {saving ? <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> Saving</> : 'Save'}
                            </Button>
                        )}
                    </div>
                </div>
            }
        />
    );
}

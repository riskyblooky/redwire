'use client';

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import type { Editor } from '@tiptap/react';
import { MarkdownEditor } from '@/components/ui/markdown-editor';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, MessageSquarePlus, MessageSquare, X } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { EditorFieldContext } from '@/lib/types';
import {
    useThreads, useCreateThread, useCreateComment, useUpdateThread,
    type Thread, type ResourceType,
} from '@/lib/hooks/use-discussions';
import {
    anchorFromRange, computeAnchorRanges, type AnchoredThreadLite,
} from '@/components/ui/comment-highlight-extension';
import { CommentThreadList } from './comment-thread-list';
import { CommentHoverCard } from './comment-hover-card';
import { nextThreadTitle } from './field-labels';

export interface AnnotationSurfaceHandle {
    /** Persist any anchors that have drifted from their stored quote/context.
     *  Call only after a real save; awaitable so an edit form can flush before
     *  it navigates away. */
    refreshAnchors: () => Promise<void>;
}

export interface AnnotationSurfaceProps {
    value: string;
    onChange: (v: string) => void;
    canEdit?: boolean;
    engagementId: string;
    resourceType: ResourceType;
    resourceId: string;
    field: string;
    fieldContext?: EditorFieldContext;
    minHeight?: string;
    placeholder?: string;
    /** Focus (and scroll to) this thread's highlight once the editor mounts. */
    focusThreadId?: string | null;
    /** Rendered in a footer row under the editor (e.g. a Save/Cancel bar). */
    footer?: React.ReactNode;
    outerClassName?: string;
}

const toLite = (t: Thread): AnchoredThreadLite => ({
    id: t.id,
    anchor: {
        quote: t.anchor?.quote || '',
        prefix: t.anchor?.prefix ?? null,
        suffix: t.anchor?.suffix ?? null,
        occurrence: t.anchor?.occurrence ?? 0,
    },
    resolved: t.is_resolved,
});

/**
 * The always-on annotation editor: a TipTap editor showing comment highlights,
 * a floating "Add comment" affordance on selection, a composer, a hover peek, and
 * a per-field comment rail. It does NOT own a Save button or a view/preview
 * toggle — the host decides how (and when) `value` is persisted. Used by both the
 * detail-page AnnotatableMarkdownField (which wraps it with a Save/Cancel bar)
 * and the full edit pages (which call refreshAnchors() from the form submit). See
 * docs/anchored-comments-peer-review.md.
 */
export const AnnotationSurface = forwardRef<AnnotationSurfaceHandle, AnnotationSurfaceProps>(function AnnotationSurface({
    value, onChange, canEdit = false, engagementId, resourceType, resourceId, field,
    fieldContext, minHeight = '260px', placeholder, focusThreadId, footer, outerClassName,
}, ref) {
    const [editor, setEditor] = useState<Editor | null>(null);
    const [activeId, setActiveId] = useState<string | null>(null);

    const [selBtn, setSelBtn] = useState<{ from: number; to: number; left: number; top: number } | null>(null);
    const [composer, setComposer] = useState<{ from: number; to: number; quote: string; left: number; top: number } | null>(null);
    const [composerText, setComposerText] = useState('');

    const [hover, setHover] = useState<{ thread: Thread; rect: DOMRect } | null>(null);
    const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const { data: allThreads = [] } = useThreads({ engagement_id: engagementId, resource_type: resourceType, resource_id: resourceId });
    const createThread = useCreateThread();
    const createComment = useCreateComment();
    const updateThread = useUpdateThread();

    const fieldThreads = useMemo(
        () => allThreads.filter((t) => t.anchor && t.anchor.field === field),
        [allThreads, field],
    );
    const lite = useMemo(() => fieldThreads.map(toLite), [fieldThreads]);
    const byId = useMemo(() => new Map(fieldThreads.map((t) => [t.id, t])), [fieldThreads]);

    const orphanedIds = useMemo(() => {
        if (!editor) return new Set<string>();
        const set = new Set<string>();
        for (const r of computeAnchorRanges(editor.state.doc, lite)) if (r.orphaned) set.add(r.id);
        return set;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [editor, lite, value]);

    // Focus a thread's highlight once the editor is ready.
    useEffect(() => {
        if (editor && focusThreadId) setActiveId(focusThreadId);
    }, [editor, focusThreadId]);

    // Track selection → floating "add comment" button.
    useEffect(() => {
        if (!editor) return;
        const update = () => {
            const { from, to, empty } = editor.state.selection;
            if (empty || composer) { setSelBtn(null); return; }
            try {
                const coords = editor.view.coordsAtPos(to);
                setSelBtn({ from, to, left: coords.left, top: coords.bottom });
            } catch { setSelBtn(null); }
        };
        editor.on('selectionUpdate', update);
        return () => { editor.off('selectionUpdate', update); };
    }, [editor, composer]);

    // Scroll the active highlight into view.
    useEffect(() => {
        if (!editor || !activeId) return;
        const el = editor.view.dom.querySelector(`.rw-comment-highlight[data-thread-id="${activeId}"]`);
        el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, [editor, activeId]);

    // Persist any anchors that the just-saved text moved, so they aren't orphaned
    // on next open. Called only after a real save (the detail field's Save button,
    // or the edit form's submit) — never on blur/unmount, so cancelling an edit
    // never rewrites an anchor to match discarded text. Awaitable so the edit form
    // can flush before it navigates away.
    const refreshAnchors = useCallback(async () => {
        if (!editor) return;
        const writes: Promise<unknown>[] = [];
        for (const r of computeAnchorRanges(editor.state.doc, lite)) {
            if (r.orphaned) continue;
            const t = byId.get(r.id);
            if (!t?.anchor) continue;
            const fresh = anchorFromRange(editor.state.doc, r.from, r.to);
            const cur = t.anchor;
            if (
                cur.quote !== fresh.quote ||
                (cur.prefix || '') !== (fresh.prefix || '') ||
                (cur.suffix || '') !== (fresh.suffix || '') ||
                (cur.occurrence || 0) !== fresh.occurrence
            ) {
                writes.push(updateThread.mutateAsync({ id: r.id, anchor: { field, quote: fresh.quote, prefix: fresh.prefix, suffix: fresh.suffix, occurrence: fresh.occurrence } }));
            }
        }
        await Promise.allSettled(writes);
    }, [editor, lite, byId, field, updateThread]);

    useImperativeHandle(ref, () => ({ refreshAnchors }), [refreshAnchors]);

    const openComposer = () => {
        if (!editor || !selBtn) return;
        const a = anchorFromRange(editor.state.doc, selBtn.from, selBtn.to);
        setComposer({ from: selBtn.from, to: selBtn.to, quote: a.quote, left: selBtn.left, top: selBtn.top });
        setSelBtn(null);
    };

    const submitComposer = async () => {
        if (!editor || !composer) return;
        const body = composerText.trim();
        if (!body) { toast.error('Add a comment first'); return; }
        try {
            const a = anchorFromRange(editor.state.doc, composer.from, composer.to);
            const thread = await createThread.mutateAsync({
                engagement_id: engagementId, resource_type: resourceType, resource_id: resourceId,
                title: nextThreadTitle(resourceType, field, fieldThreads.map((t) => t.title)),
                anchor: { field, quote: a.quote, prefix: a.prefix, suffix: a.suffix, occurrence: a.occurrence },
            });
            await createComment.mutateAsync({ thread_id: thread.id, content: body });
            setComposer(null); setComposerText(''); setActiveId(thread.id);
        } catch (e: any) {
            toast.error(e?.response?.data?.detail || 'Failed to add comment');
        }
    };

    const onHover = (id: string | null, rect?: DOMRect) => {
        if (hoverTimer.current) { clearTimeout(hoverTimer.current); hoverTimer.current = null; }
        if (id && rect) {
            const t = byId.get(id);
            if (t) setHover({ thread: t, rect });
        } else {
            hoverTimer.current = setTimeout(() => setHover(null), 200);
        }
    };

    const showRail = fieldThreads.length > 0;

    return (
        <div className={cn('rounded-lg border border-slate-700 bg-slate-950/30 p-2', outerClassName)}>
            <div className={cn('grid gap-2', showRail && 'lg:grid-cols-[1fr_17rem]')}>
                <div className="min-w-0">
                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                        <MarkdownEditor
                            value={value}
                            onChange={onChange}
                            engagementId={engagementId}
                            fieldContext={fieldContext}
                            placeholder={placeholder}
                            minHeight={minHeight}
                            resizable
                            disabled={!canEdit}
                            commentThreads={lite}
                            activeCommentId={activeId}
                            onEditorReady={setEditor}
                            onCommentClick={(id) => {
                                setActiveId(id);
                                document.querySelector(`[data-thread-item="${id}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                            }}
                            onCommentHover={onHover}
                        />
                    </div>
                    {footer}
                </div>

                {showRail && (
                    <div className="lg:border-l lg:border-slate-800 lg:pl-2 min-w-0">
                        <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-black text-slate-500 uppercase tracking-widest">
                            <MessageSquare className="h-3 w-3" /> Comments
                        </div>
                        <CommentThreadList
                            threads={fieldThreads}
                            activeId={activeId}
                            orphanedIds={orphanedIds}
                            showQuote
                            onActivate={setActiveId}
                        />
                    </div>
                )}
            </div>

            {selBtn && (
                <button
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); openComposer(); }}
                    className="fixed z-50 flex items-center gap-1 px-2 py-1 rounded-md bg-amber-600 hover:bg-amber-500 text-white text-[11px] font-semibold shadow-lg"
                    style={{ left: selBtn.left, top: selBtn.top + 6 }}
                >
                    <MessageSquarePlus className="h-3.5 w-3.5" /> Add comment
                </button>
            )}

            {composer && (
                <div
                    className="fixed z-50 w-72 rounded-lg border border-slate-700 bg-slate-900 shadow-xl p-2.5"
                    style={{ left: Math.min(composer.left, window.innerWidth - 300), top: composer.top + 6 }}
                >
                    <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">New comment</span>
                        <button type="button" onClick={() => { setComposer(null); setComposerText(''); }} className="text-slate-500 hover:text-white"><X className="h-3.5 w-3.5" /></button>
                    </div>
                    <p className="text-[11px] italic text-amber-300/80 line-clamp-2 mb-1.5">“{composer.quote}”</p>
                    <Textarea
                        autoFocus
                        value={composerText}
                        onChange={(e) => setComposerText(e.target.value)}
                        placeholder="Add your review comment…"
                        rows={3}
                        className="text-xs bg-slate-950/60 border-slate-800 resize-none"
                        onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submitComposer(); } }}
                    />
                    <div className="flex justify-end gap-2 mt-2">
                        <Button variant="ghost" size="sm" className="h-7 text-slate-400" onClick={() => { setComposer(null); setComposerText(''); }}>Cancel</Button>
                        <Button size="sm" className="h-7 bg-amber-600 hover:bg-amber-500 text-white" onClick={submitComposer} disabled={createThread.isPending || createComment.isPending}>
                            {(createThread.isPending || createComment.isPending) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Comment'}
                        </Button>
                    </div>
                </div>
            )}

            {hover && (
                <div onMouseEnter={() => { if (hoverTimer.current) clearTimeout(hoverTimer.current); }} onMouseLeave={() => setHover(null)}>
                    <CommentHoverCard
                        thread={hover.thread}
                        rect={hover.rect}
                        onOpen={() => { setActiveId(hover.thread.id); setHover(null); }}
                    />
                </div>
            )}
        </div>
    );
});

'use client';

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import type { Editor } from '@tiptap/react';
import { MarkdownEditor } from '@/components/ui/markdown-editor';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, MessageSquarePlus, MessageSquare, X, Eye, EyeOff } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { EditorFieldContext } from '@/lib/types';
import {
    useThreads, useCreateThread, useCreateComment, useUpdateThread,
    type Thread, type ResourceType,
} from '@/lib/hooks/use-discussions';
import { useFindingReviews, useSubmitFindingReview } from '@/lib/hooks/use-finding-reviews';
import {
    anchorFromRange, computeAnchorRanges, type AnchoredThreadLite,
} from '@/components/ui/comment-highlight-extension';
import { CommentThreadList } from './comment-thread-list';
import { CommentHoverCard } from './comment-hover-card';
import { nextThreadTitle } from './field-labels';
import { RightPaneCollapseButton, RightPaneExpandTab } from '@/components/ui/right-pane-collapse';

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
    const rootRef = useRef<HTMLDivElement>(null);

    // Popup positions are stored relative to the surface container (rootRef), not
    // the viewport: an ancestor card uses backdrop-filter, which makes position:
    // fixed resolve against that card, so we position:absolute within rootRef and
    // clamp to its width so the button/composer never overflow or hide off-screen.
    const [selBtn, setSelBtn] = useState<{ from: number; to: number; left: number; top: number } | null>(null);
    const [composer, setComposer] = useState<{ from: number; to: number; quote: string; left: number; top: number } | null>(null);
    const [composerText, setComposerText] = useState('');

    // Selection end → position within the container, clamped to fit `width` px.
    const anchorPos = useCallback((width: number) => {
        if (!editor || !rootRef.current) return null;
        const coords = editor.view.coordsAtPos(editor.state.selection.to);
        const rect = rootRef.current.getBoundingClientRect();
        const left = Math.max(6, Math.min(coords.left - rect.left, rect.width - width - 6));
        const top = coords.bottom - rect.top + 6;
        return { left, top };
    }, [editor]);

    const [hover, setHover] = useState<{ thread: Thread; rect: DOMRect } | null>(null);
    const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Hide resolved threads from the rail by default (they also lose their
    // highlight); the header toggle brings them back.
    const [hideResolved, setHideResolved] = useState(true);

    // Collapse the whole comments rail (editor takes the full width), persisted.
    const [railCollapsed, setRailCollapsed] = useState(false);
    useEffect(() => {
        try { if (localStorage.getItem('rw-comment-rail-collapsed') === '1') setRailCollapsed(true); } catch { /* ignore */ }
    }, []);
    const setRailCollapsedPersist = (v: boolean) => {
        setRailCollapsed(v);
        try { localStorage.setItem('rw-comment-rail-collapsed', v ? '1' : '0'); } catch { /* ignore */ }
    };

    // Draggable rail width (lg+ only), persisted per session.
    const RAIL_MIN = 200, RAIL_MAX = 640, RAIL_DEFAULT = 272;
    const [railWidth, setRailWidth] = useState(RAIL_DEFAULT);
    const railDragRef = useRef<{ startX: number; startW: number } | null>(null);
    useEffect(() => {
        try {
            const v = parseInt(localStorage.getItem('rw-comment-rail-width') || '', 10);
            if (!Number.isNaN(v)) setRailWidth(Math.min(RAIL_MAX, Math.max(RAIL_MIN, v)));
        } catch { /* ignore */ }
    }, []);
    const onRailDragMove = useCallback((e: MouseEvent) => {
        const d = railDragRef.current;
        if (!d) return;
        // Dragging the handle left widens the rail (editor shrinks).
        const w = Math.min(RAIL_MAX, Math.max(RAIL_MIN, d.startW - (e.clientX - d.startX)));
        setRailWidth(w);
    }, []);
    const onRailDragEnd = useCallback(() => {
        railDragRef.current = null;
        window.removeEventListener('mousemove', onRailDragMove);
        window.removeEventListener('mouseup', onRailDragEnd);
        document.body.style.userSelect = '';
        try { localStorage.setItem('rw-comment-rail-width', String(railWidthRef.current)); } catch { /* ignore */ }
    }, [onRailDragMove]);
    const railWidthRef = useRef(railWidth);
    useEffect(() => { railWidthRef.current = railWidth; }, [railWidth]);
    const startRailDrag = useCallback((e: React.MouseEvent) => {
        railDragRef.current = { startX: e.clientX, startW: railWidthRef.current };
        window.addEventListener('mousemove', onRailDragMove);
        window.addEventListener('mouseup', onRailDragEnd);
        document.body.style.userSelect = 'none';
        e.preventDefault();
    }, [onRailDragMove, onRailDragEnd]);

    const { data: allThreads = [] } = useThreads({ engagement_id: engagementId, resource_type: resourceType, resource_id: resourceId });
    // Findings only: leaving an anchored comment records the commenter's own
    // peer review as "changes requested".
    const isFinding = resourceType === 'finding';
    const { data: reviewSummary } = useFindingReviews(isFinding ? resourceId : undefined);
    const submitReview = useSubmitFindingReview(resourceId);
    const createThread = useCreateThread();
    const createComment = useCreateComment();
    const updateThread = useUpdateThread();

    const fieldThreads = useMemo(
        () => allThreads.filter((t) => t.anchor && t.anchor.field === field),
        [allThreads, field],
    );
    const resolvedCount = useMemo(() => fieldThreads.filter((t) => t.is_resolved).length, [fieldThreads]);
    const visibleThreads = useMemo(
        () => (hideResolved ? fieldThreads.filter((t) => !t.is_resolved) : fieldThreads),
        [fieldThreads, hideResolved],
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
                const p = anchorPos(140);
                if (p) setSelBtn({ from, to, left: p.left, top: p.top });
            } catch { setSelBtn(null); }
        };
        editor.on('selectionUpdate', update);
        return () => { editor.off('selectionUpdate', update); };
    }, [editor, composer, anchorPos]);

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
        // Re-anchor for the wider composer so it stays inside the container.
        const p = anchorPos(288) ?? { left: selBtn.left, top: selBtn.top };
        setComposer({ from: selBtn.from, to: selBtn.to, quote: a.quote, left: p.left, top: p.top });
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

            // On a finding, a review comment is a change request: record the
            // commenter's own peer review as CHANGES_REQUESTED (skip the author,
            // who can't review their own finding, and no-op if already set).
            if (
                isFinding && reviewSummary && !reviewSummary.is_author &&
                reviewSummary.my_review?.status !== 'CHANGES_REQUESTED'
            ) {
                try {
                    await submitReview.mutateAsync({ status: 'CHANGES_REQUESTED' });
                    toast.info('Your review was set to “changes requested”.');
                } catch { /* non-fatal: the comment already posted */ }
            }
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
    const railOpen = showRail && !railCollapsed;

    return (
        <div ref={rootRef} className={cn('relative rounded-lg border border-slate-700 bg-slate-950/30 p-2', outerClassName)}>
            <div
                className={cn('grid gap-2 items-start',
                    railOpen && 'lg:grid-cols-[minmax(0,1fr)_var(--rail-w)]',
                    showRail && !railOpen && 'lg:grid-cols-[1fr_auto]',
                )}
                style={railOpen ? ({ ['--rail-w' as string]: `${railWidth}px` } as React.CSSProperties) : undefined}
            >
                {/* The editor keeps its own (user-resizable) height in all layouts;
                    the comments rail sizes independently beside it. */}
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

                {railOpen && (
                    <div className="relative lg:border-l lg:border-slate-800 lg:pl-2 min-w-0">
                        {/* Drag handle — resize the comments rail horizontally (lg+). */}
                        <div
                            onMouseDown={startRailDrag}
                            title="Drag to resize the comments panel"
                            className="hidden lg:block absolute -left-1.5 top-0 bottom-0 w-3 cursor-col-resize group/raildrag z-10"
                        >
                            <div className="absolute left-1 top-0 bottom-0 w-px bg-transparent group-hover/raildrag:bg-primary/50 transition-colors" />
                        </div>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                            <span className="flex items-center gap-1.5 text-[10px] font-black text-slate-500 uppercase tracking-widest">
                                <MessageSquare className="h-3 w-3" /> Comments
                            </span>
                            <span className="flex items-center gap-1.5">
                                {resolvedCount > 0 && (
                                    <button
                                        type="button"
                                        onClick={() => setHideResolved((v) => !v)}
                                        className={cn(
                                            'flex items-center gap-1 text-[10px] font-semibold transition-colors',
                                            hideResolved ? 'text-slate-500 hover:text-slate-300' : 'text-emerald-400 hover:text-emerald-300',
                                        )}
                                        title={hideResolved ? `Show ${resolvedCount} resolved` : 'Hide resolved'}
                                    >
                                        {hideResolved ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                        {hideResolved ? `Resolved (${resolvedCount})` : 'Hide resolved'}
                                    </button>
                                )}
                                <RightPaneCollapseButton onClick={() => setRailCollapsedPersist(true)} />
                            </span>
                        </div>
                        <CommentThreadList
                            threads={visibleThreads}
                            activeId={activeId}
                            orphanedIds={orphanedIds}
                            showQuote
                            onActivate={setActiveId}
                            emptyText={hideResolved && resolvedCount > 0 ? 'All comments resolved.' : undefined}
                        />
                    </div>
                )}

                {showRail && railCollapsed && (
                    <RightPaneExpandTab onClick={() => setRailCollapsedPersist(false)} label="Comments" />
                )}
            </div>

            {selBtn && (
                <button
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); openComposer(); }}
                    className="absolute z-50 flex items-center gap-1 px-2 py-1 rounded-md bg-amber-600 hover:bg-amber-500 text-white text-[11px] font-semibold shadow-lg"
                    style={{ left: selBtn.left, top: selBtn.top }}
                >
                    <MessageSquarePlus className="h-3.5 w-3.5" /> Add comment
                </button>
            )}

            {composer && (
                <div
                    className="absolute z-50 w-72 rounded-lg border border-slate-700 bg-slate-900 shadow-xl p-2.5"
                    style={{ left: composer.left, top: composer.top }}
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

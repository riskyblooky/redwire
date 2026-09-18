'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Editor } from '@tiptap/react';
import { MarkdownEditor, MarkdownPreview } from '@/components/ui/markdown-editor';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, Pencil, MessageSquarePlus, MessageSquare, X } from 'lucide-react';
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
import { useAnchoredComments } from './anchored-comments-context';
import { CommentThreadList } from './comment-thread-list';
import { CommentHoverCard } from './comment-hover-card';
import { nextThreadTitle } from './field-labels';

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
 * Markdown field with anchored peer-review comments. In view mode it reads as
 * rendered markdown (with a comment-count chip); double-clicking — or clicking
 * the chip — enters "annotation mode", a TipTap editor with comment highlights
 * beside a comment rail. Editable for those who can edit the field, read-only
 * (but still comment-able) for reviewers who can't. See
 * docs/anchored-comments-peer-review.md.
 */
export function AnnotatableMarkdownField({
    value, onSave, canEdit = false, engagementId, resourceType, resourceId, field,
    fieldContext, previewWrapperClassName, emptyText = 'Double-click to add…', placeholder, minHeight = '260px',
}: AnnotatableMarkdownFieldProps) {
    const [mode, setMode] = useState<'view' | 'annotate'>('view');
    const [draft, setDraft] = useState('');
    const [saving, setSaving] = useState(false);
    const [editor, setEditor] = useState<Editor | null>(null);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [pendingActive, setPendingActive] = useState<string | null>(null);

    // Floating "add comment" affordance + composer.
    const [selBtn, setSelBtn] = useState<{ from: number; to: number; left: number; top: number } | null>(null);
    const [composer, setComposer] = useState<{ from: number; to: number; quote: string; left: number; top: number } | null>(null);
    const [composerText, setComposerText] = useState('');

    // Hover popover.
    const [hover, setHover] = useState<{ thread: Thread; rect: DOMRect } | null>(null);
    const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const { data: allThreads = [] } = useThreads({ engagement_id: engagementId, resource_type: resourceType, resource_id: resourceId });
    const createThread = useCreateThread();
    const createComment = useCreateComment();
    const updateThread = useUpdateThread();
    const anchored = useAnchoredComments();

    const fieldThreads = useMemo(
        () => allThreads.filter((t) => t.anchor && t.anchor.field === field),
        [allThreads, field],
    );
    const lite = useMemo(() => fieldThreads.map(toLite), [fieldThreads]);
    const byId = useMemo(() => new Map(fieldThreads.map((t) => [t.id, t])), [fieldThreads]);
    const unresolvedCount = fieldThreads.filter((t) => !t.is_resolved).length;

    // Orphaned set (only meaningful once the editor is mounted).
    const orphanedIds = useMemo(() => {
        if (!editor) return new Set<string>();
        const set = new Set<string>();
        for (const r of computeAnchorRanges(editor.state.doc, lite)) if (r.orphaned) set.add(r.id);
        return set;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [editor, lite, draft]);

    const enterAnnotate = useCallback((focusId?: string) => {
        setDraft(value || '');
        setMode('annotate');
        if (focusId) setPendingActive(focusId);
    }, [value]);

    // Let the page-level rail open this field.
    useEffect(() => anchored.registerOpener(field, (threadId) => enterAnnotate(threadId)), [anchored, field, enterAnnotate]);

    // Track the selection to show the floating "add comment" button.
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

    // Apply a pending focus once the editor exists.
    useEffect(() => {
        if (editor && pendingActive) { setActiveId(pendingActive); setPendingActive(null); }
    }, [editor, pendingActive]);

    // Scroll the active highlight into view.
    useEffect(() => {
        if (!editor || !activeId) return;
        const el = editor.view.dom.querySelector(`.rw-comment-highlight[data-thread-id="${activeId}"]`);
        el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, [editor, activeId]);

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

    // Auto-refresh anchors from the live doc after a save (silent). Runs before
    // the editor unmounts.
    const refreshAnchors = useCallback(() => {
        if (!editor) return;
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
                updateThread.mutate({ id: r.id, anchor: { field, quote: fresh.quote, prefix: fresh.prefix, suffix: fresh.suffix, occurrence: fresh.occurrence } });
            }
        }
    }, [editor, lite, byId, field, updateThread]);

    const save = async () => {
        if (saving) return;
        setSaving(true);
        try {
            await onSave(draft);
            refreshAnchors();
            setMode('view');
            toast.success('Saved');
        } catch (e: any) {
            toast.error(e?.response?.data?.detail || e?.message || 'Failed to save');
        } finally {
            setSaving(false);
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
        <div className="rounded-lg border border-slate-700 bg-slate-950/30 p-2">
            <div className="grid gap-2 lg:grid-cols-[1fr_17rem]">
                {/* Editor / read-only annotation surface */}
                <div className="min-w-0">
                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                        <MarkdownEditor
                            value={draft}
                            onChange={setDraft}
                            engagementId={engagementId}
                            fieldContext={fieldContext}
                            placeholder={placeholder}
                            minHeight={minHeight}
                            resizable
                            disabled={!canEdit || saving}
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
                    <div className="flex items-center justify-between mt-2">
                        <span className="text-[10px] text-slate-500">
                            {canEdit ? 'Select text to comment · ⌘/Ctrl+Enter saves · ' : 'Read-only — select text to comment · '}
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
                </div>

                {/* Comment rail for this field */}
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
                        emptyText="Select text on the left, then Add comment."
                    />
                </div>
            </div>

            {/* Floating "add comment" button by the selection */}
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

            {/* Composer */}
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

            {/* Hover peek */}
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
}

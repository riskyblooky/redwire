/**
 * Comment-highlight decorations for anchored peer-review comments.
 * See docs/anchored-comments-peer-review.md §7.1–7.4.
 *
 * Highlights are ProseMirror *decorations*, never stored marks — they are a
 * presentation layer that never mutates the document, so the saved markdown (and
 * therefore report generation) is untouched. Decorations are seeded by relocating
 * each thread's stored quote in the current doc, then mapped through transactions
 * so they stay glued to the text as the author edits (the Google-Docs feel). When
 * the thread list changes, dispatch a transaction carrying the plugin key's meta
 * (see `rebuildCommentHighlights`) to rebuild.
 *
 * Whole-document replaces can't be mapped through — a collaborator's change
 * arriving over Y.js (y-prosemirror re-renders the doc as one replace step) or
 * content loaded into an empty editor. Those relocate every highlight instead,
 * from its text as it stood just before the change (so a local edit inside a
 * quote keeps its highlight), falling back to the stored anchor.
 *
 * The offset↔position helpers and `anchorFromSelection` are also used by the
 * React layer to create anchors from a selection and to auto-refresh anchors on
 * save.
 */
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import type { Node as PMNode } from '@tiptap/pm/model';
import type { Editor } from '@tiptap/react';
import { ySyncPluginKey } from '@tiptap/y-tiptap';
import { relocateAnchor, occurrenceIndexAt, type StoredAnchor } from '@/lib/anchor-relocate';

export const commentHighlightKey = new PluginKey('rwCommentHighlight');

/** Context window (chars) captured on each side of a new/refreshed anchor. */
const CONTEXT = 48;

export interface AnchoredThreadLite {
    id: string;
    anchor: StoredAnchor;
    resolved?: boolean;
}

interface TextSegment {
    off: number; // start offset in the concatenated plain text
    pos: number; // ProseMirror position of the first char
    len: number;
}

interface TextIndex {
    text: string;
    segments: TextSegment[];
}

/**
 * Concatenate the doc's text-node contents and remember where each run sits in
 * the ProseMirror position space. No block separators are inserted, so a quote is
 * matched against visible text only (markdown syntax never appears in it).
 */
export function buildTextIndex(doc: PMNode): TextIndex {
    const segments: TextSegment[] = [];
    let text = '';
    doc.descendants((node, pos) => {
        if (node.isText && node.text) {
            segments.push({ off: text.length, pos, len: node.text.length });
            text += node.text;
        }
        return true;
    });
    return { text, segments };
}

/** Plain-text offset → ProseMirror position. */
export function offsetToPos(index: TextIndex, offset: number): number | null {
    for (const s of index.segments) {
        if (offset >= s.off && offset <= s.off + s.len) return s.pos + (offset - s.off);
    }
    const last = index.segments[index.segments.length - 1];
    return last ? last.pos + last.len : null;
}

/** ProseMirror position → plain-text offset. */
export function posToOffset(index: TextIndex, pos: number): number {
    for (const s of index.segments) {
        if (pos >= s.pos && pos <= s.pos + s.len) return s.off + (pos - s.pos);
    }
    // Clamp to the end of the last run.
    const last = index.segments[index.segments.length - 1];
    return last ? last.off + last.len : 0;
}

/**
 * Derive a fresh anchor (quote + context + occurrence) from a ProseMirror range.
 * Used both when creating a comment from the current selection and when
 * auto-refreshing an anchor on save from its live mapped range.
 */
export function anchorFromRange(doc: PMNode, from: number, to: number): StoredAnchor & { occurrence: number } {
    const index = buildTextIndex(doc);
    const so = posToOffset(index, from);
    const eo = posToOffset(index, to);
    const quote = index.text.slice(so, eo);
    return {
        quote,
        prefix: index.text.slice(Math.max(0, so - CONTEXT), so),
        suffix: index.text.slice(eo, eo + CONTEXT),
        occurrence: occurrenceIndexAt(index.text, quote, so),
    };
}

export interface AnchorRange {
    id: string;
    from: number;
    to: number;
    resolved: boolean;
    orphaned: boolean;
}

/**
 * For each anchored thread, relocate its quote in the current doc and return the
 * ProseMirror range (or orphaned=true when the quote is gone). Reused by the
 * decoration builder, the comment rail (scroll/flash), and save-refresh.
 */
export function computeAnchorRanges(doc: PMNode, threads: AnchoredThreadLite[]): AnchorRange[] {
    const index = buildTextIndex(doc);
    const out: AnchorRange[] = [];
    for (const t of threads) {
        if (!t.anchor || !t.anchor.quote) continue;
        const range = relocateAnchor(index.text, t.anchor);
        if (!range) {
            out.push({ id: t.id, from: 0, to: 0, resolved: !!t.resolved, orphaned: true });
            continue;
        }
        const from = offsetToPos(index, range.start);
        const to = offsetToPos(index, range.end);
        if (from == null || to == null || to <= from) {
            out.push({ id: t.id, from: 0, to: 0, resolved: !!t.resolved, orphaned: true });
            continue;
        }
        out.push({ id: t.id, from, to, resolved: !!t.resolved, orphaned: false });
    }
    return out;
}

function buildDecorationSet(doc: PMNode, threads: AnchoredThreadLite[], activeId: string | null): DecorationSet {
    return decorationSetFromRanges(doc, computeAnchorRanges(doc, threads), activeId);
}

/** Relocate after a whole-doc replace: each highlight's pre-change text first,
 *  then (for those that no longer match) the thread's stored anchor. */
function relocateDecorationSet(
    oldDoc: PMNode, oldSet: DecorationSet, doc: PMNode,
    threads: AnchoredThreadLite[], activeId: string | null,
): DecorationSet {
    const live = new Map<string, StoredAnchor>();
    for (const d of oldSet.find()) {
        const id = (d.spec as { threadId?: string }).threadId;
        if (id && d.to > d.from) live.set(id, anchorFromRange(oldDoc, d.from, d.to));
    }
    const ranges = computeAnchorRanges(doc, threads.map((t) => {
        const a = live.get(t.id);
        return a ? { ...t, anchor: a } : t;
    }));
    const retry = threads.filter((t) => live.has(t.id) && ranges.some((r) => r.id === t.id && r.orphaned));
    const fallback = new Map(computeAnchorRanges(doc, retry).map((r) => [r.id, r]));
    return decorationSetFromRanges(doc, ranges.map((r) => fallback.get(r.id) ?? r), activeId);
}

function decorationSetFromRanges(doc: PMNode, ranges: AnchorRange[], activeId: string | null): DecorationSet {
    const decos: Decoration[] = [];
    for (const r of ranges) {
        if (r.orphaned) continue;
        if (r.resolved) continue; // resolved threads drop their highlight
        const cls = ['rw-comment-highlight'];
        if (activeId && r.id === activeId) cls.push('rw-comment-active');
        decos.push(
            Decoration.inline(r.from, r.to, {
                class: cls.join(' '),
                'data-thread-id': r.id,
            }, { threadId: r.id }),
        );
    }
    return DecorationSet.create(doc, decos);
}

/**
 * Dispatch a no-op transaction that tells the plugin to rebuild its decorations
 * from the current thread list / active id. Call after the thread list changes
 * (new comment, resolve, delete) or the active highlight changes.
 */
export function rebuildCommentHighlights(editor: Editor | null): void {
    if (!editor) return;
    const tr = editor.state.tr.setMeta(commentHighlightKey, { rebuild: true });
    editor.view.dispatch(tr);
}

export function createCommentHighlightExtension(opts: {
    getThreads: () => AnchoredThreadLite[];
    getActiveId?: () => string | null;
}) {
    const getActiveId = opts.getActiveId || (() => null);
    return Extension.create({
        name: 'rwCommentHighlight',
        addProseMirrorPlugins() {
            return [
                new Plugin({
                    key: commentHighlightKey,
                    state: {
                        init: (_config, state) =>
                            buildDecorationSet(state.doc, opts.getThreads(), getActiveId()),
                        apply(tr, set, oldState, newState) {
                            if (tr.getMeta(commentHighlightKey)?.rebuild) {
                                return buildDecorationSet(newState.doc, opts.getThreads(), getActiveId());
                            }
                            if (tr.docChanged && (
                                tr.getMeta(ySyncPluginKey)?.isChangeOrigin ||
                                oldState.doc.textContent.length === 0
                            )) {
                                return relocateDecorationSet(oldState.doc, set, newState.doc, opts.getThreads(), getActiveId());
                            }
                            // Keep highlights glued to the text as it changes.
                            return set.map(tr.mapping, tr.doc);
                        },
                    },
                    props: {
                        decorations(state) {
                            return commentHighlightKey.getState(state);
                        },
                    },
                }),
            ];
        },
    });
}

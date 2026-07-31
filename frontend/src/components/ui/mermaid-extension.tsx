'use client';

import { Node, mergeAttributes } from '@tiptap/core';
import {
    ReactNodeViewRenderer,
    NodeViewWrapper,
    NodeViewProps,
} from '@tiptap/react';
import { useEffect, useState } from 'react';
import { Pencil, Check } from 'lucide-react';
import { MermaidDiagram } from './mermaid-diagram';
import { cn } from '@/lib/utils';

/**
 * Obsidian-style live Mermaid block. The diagram renders inline in the editor;
 * an Edit affordance swaps it for a source textarea, and clicking away (blur)
 * re-renders. Source lives in the `content` attribute (atom node), so the
 * NodeView owns the edit UX rather than ProseMirror text.
 *
 * Why the Edit button works now: TipTap's default node-view `stopEvent` returns
 * true for events targeting BUTTON / TEXTAREA (so the DOM handles them) EXCEPT
 * for drag events. The first cut set `draggable: true` + a drag handle on the
 * whole node, so a mousedown on the button started a drag instead of a click.
 * This node is NOT draggable — button clicks and textarea typing just work.
 *
 * Markdown round-trip:
 *   serialize → a ```mermaid fenced block (plain markdown on disk / for the
 *               view-page renderer).
 *   parse     → markdown-it's `fence` renderer is overridden so a ```mermaid
 *               block becomes this node — on document load AND on paste (paste
 *               goes through the same markdown-it pipeline), which is what makes
 *               pasting a fenced diagram render instead of erroring.
 */

declare module '@tiptap/core' {
    interface Commands<ReturnType> {
        mermaid: {
            insertMermaid: (content?: string) => ReturnType;
        };
    }
}

const STARTER = `graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Do this]
    B -->|No| D[Do that]`;

function MermaidNodeView({ node, updateAttributes, editor, selected }: NodeViewProps) {
    const content: string = node.attrs.content || '';
    const editable = editor.isEditable;
    const [editing, setEditing] = useState<boolean>(editable && !content.trim());
    const [draft, setDraft] = useState<string>(content);

    useEffect(() => {
        setDraft(node.attrs.content || '');
    }, [node.attrs.content]);

    const startEdit = () => {
        setDraft(node.attrs.content || '');
        setEditing(true);
    };
    const finishEdit = () => {
        if (draft !== content) updateAttributes({ content: draft });
        setEditing(false);
    };

    // Read-only surfaces (disabled editor) just render the diagram.
    if (!editable) {
        return (
            <NodeViewWrapper className="my-3">
                <MermaidDiagram chart={content} />
            </NodeViewWrapper>
        );
    }

    if (editing) {
        return (
            <NodeViewWrapper className="mermaid-node my-3 rounded-lg border border-indigo-500/40 bg-slate-900/40">
                <div className="flex items-center justify-between border-b border-slate-800/60 px-2 py-1">
                    <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
                        Editing mermaid — click away to render
                    </span>
                    <button
                        type="button"
                        onClick={finishEdit}
                        className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-slate-800 hover:text-slate-100"
                    >
                        <Check className="h-3 w-3" /> Done
                    </button>
                </div>
                <textarea
                    autoFocus
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onBlur={finishEdit}
                    onKeyDown={(e) => {
                        if (e.key === 'Escape') {
                            e.preventDefault();
                            finishEdit();
                        }
                    }}
                    spellCheck={false}
                    rows={Math.max(4, draft.split('\n').length + 1)}
                    placeholder="graph TD; A --> B"
                    className="w-full resize-y bg-transparent px-3 py-2 font-mono text-[12px] leading-relaxed text-slate-200 outline-none"
                />
            </NodeViewWrapper>
        );
    }

    return (
        <NodeViewWrapper
            className={cn(
                'mermaid-node group relative my-3 rounded-lg border bg-slate-900/40',
                selected ? 'border-indigo-500/60' : 'border-transparent hover:border-slate-700/60',
            )}
        >
            <button
                type="button"
                onClick={startEdit}
                title="Edit diagram"
                className="absolute left-2 top-2 z-10 flex items-center gap-1 rounded bg-slate-800/90 px-1.5 py-0.5 text-[11px] text-slate-300 opacity-0 shadow transition-opacity hover:bg-slate-700 hover:text-slate-100 group-hover:opacity-100"
            >
                <Pencil className="h-3 w-3" /> Edit
            </button>
            <div className="p-2" onDoubleClick={startEdit} title="Double-click to edit">
                {content.trim() ? (
                    <MermaidDiagram chart={content} />
                ) : (
                    <div className="py-6 text-center text-xs text-slate-500">Empty diagram — click Edit</div>
                )}
            </div>
        </NodeViewWrapper>
    );
}

export const Mermaid = Node.create({
    name: 'mermaid',
    group: 'block',
    atom: true,
    draggable: false, // critical: a draggable node would turn the Edit button's mousedown into a drag
    selectable: true,

    addAttributes() {
        return {
            content: {
                default: '',
                parseHTML: (element) =>
                    element.getAttribute('data-content') ?? element.textContent ?? '',
                renderHTML: (attributes) => ({ 'data-content': attributes.content }),
            },
        };
    },

    parseHTML() {
        return [{ tag: 'div[data-type="mermaid"]' }];
    },

    renderHTML({ HTMLAttributes, node }) {
        return [
            'div',
            mergeAttributes(HTMLAttributes, { 'data-type': 'mermaid' }),
            node.attrs.content || '',
        ];
    },

    addNodeView() {
        return ReactNodeViewRenderer(MermaidNodeView);
    },

    addCommands() {
        return {
            insertMermaid:
                (content?: string) =>
                ({ commands }) =>
                    commands.insertContent({
                        type: this.name,
                        attrs: { content: content ?? STARTER },
                    }),
        };
    },

    addStorage() {
        return {
            markdown: {
                serialize(state: any, node: any) {
                    state.write('```mermaid\n');
                    state.text(node.attrs.content || '', false);
                    state.ensureNewLine();
                    state.write('```');
                    state.closeBlock(node);
                },
                parse: {
                    setup(markdownit: any) {
                        const defaultFence =
                            markdownit.renderer.rules.fence ||
                            function (tokens: any[], idx: number, options: any, _env: any, self: any) {
                                return self.renderToken(tokens, idx, options);
                            };
                        markdownit.renderer.rules.fence = (
                            tokens: any[],
                            idx: number,
                            options: any,
                            env: any,
                            self: any,
                        ) => {
                            const token = tokens[idx];
                            const info = (token.info || '').trim().toLowerCase();
                            if (info === 'mermaid') {
                                const src = (token.content || '').replace(/\n$/, '');
                                const escaped = markdownit.utils.escapeHtml(src);
                                return `<div data-type="mermaid" data-content="${escaped}">${escaped}</div>`;
                            }
                            return defaultFence(tokens, idx, options, env, self);
                        };
                    },
                },
            },
        };
    },
});

export default Mermaid;

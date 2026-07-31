'use client';

import { Node, mergeAttributes } from '@tiptap/core';
import {
    ReactNodeViewRenderer,
    NodeViewWrapper,
    NodeViewProps,
} from '@tiptap/react';
import { useEffect, useState } from 'react';
import { Pencil, Check, Workflow } from 'lucide-react';
import { MermaidDiagram } from './mermaid-diagram';
import { cn } from '@/lib/utils';

/**
 * A TipTap block node for Mermaid diagrams. It's an atom node — the diagram
 * source lives in the `content` attribute rather than as editable ProseMirror
 * text — so the NodeView owns the editing experience (a source textarea) and
 * the live preview.
 *
 * Markdown round-trip:
 *   - serialize → a ```mermaid fenced block, so notes/findings stay plain
 *     markdown on disk and render as diagrams anywhere the markdown viewer runs.
 *   - parse     → we override markdown-it's `fence` renderer so a ```mermaid
 *     block becomes `<div data-type="mermaid">…</div>`, which this node's
 *     parseHTML picks up. All other fences fall through to the default code
 *     block (CodeBlockLowlight).
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

    // Keep the local draft in sync when the node's content changes from
    // elsewhere (collab peers, external setContent).
    useEffect(() => {
        setDraft(node.attrs.content || '');
    }, [node.attrs.content]);

    const commit = () => {
        if (draft !== content) updateAttributes({ content: draft });
        setEditing(false);
    };

    return (
        <NodeViewWrapper
            className={cn(
                'mermaid-node my-3 rounded-lg border bg-slate-900/40 transition-colors',
                selected ? 'border-indigo-500/60' : 'border-slate-700/60',
            )}
            data-drag-handle
        >
            {editable && (
                <div className="flex items-center justify-between border-b border-slate-800/60 px-2 py-1">
                    <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                        <Workflow className="h-3 w-3" />
                        Mermaid diagram
                    </span>
                    <button
                        type="button"
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={() => (editing ? commit() : setEditing(true))}
                        className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                    >
                        {editing ? (
                            <>
                                <Check className="h-3 w-3" /> Done
                            </>
                        ) : (
                            <>
                                <Pencil className="h-3 w-3" /> Edit
                            </>
                        )}
                    </button>
                </div>
            )}

            {editing && editable ? (
                <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onBlur={commit}
                    // Keep ProseMirror from intercepting keystrokes/selection
                    // while the user edits the diagram source.
                    onKeyDown={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                    autoFocus
                    spellCheck={false}
                    rows={Math.max(4, draft.split('\n').length + 1)}
                    placeholder="graph TD; A --> B"
                    className="w-full resize-y bg-transparent px-3 py-2 font-mono text-[12px] leading-relaxed text-slate-200 outline-none"
                />
            ) : (
                <div
                    className={cn('px-2', editable && 'cursor-pointer')}
                    onDoubleClick={() => editable && setEditing(true)}
                    title={editable ? 'Double-click to edit' : undefined}
                >
                    {content.trim() ? (
                        <MermaidDiagram chart={content} />
                    ) : (
                        <div className="py-6 text-center text-xs text-slate-500">Empty diagram</div>
                    )}
                </div>
            )}
        </NodeViewWrapper>
    );
}

export const Mermaid = Node.create({
    name: 'mermaid',
    group: 'block',
    atom: true,
    draggable: true,

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
        // The text child is what markdown-it-derived HTML carries; data-content
        // is the canonical source read back by parseHTML.
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

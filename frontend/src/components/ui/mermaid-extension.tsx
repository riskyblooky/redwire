'use client';

import { Node, mergeAttributes } from '@tiptap/core';
import {
    ReactNodeViewRenderer,
    NodeViewWrapper,
    NodeViewProps,
} from '@tiptap/react';
import { useEffect, useRef, useState } from 'react';
import { Pencil, Check } from 'lucide-react';
import { MermaidDiagram } from './mermaid-diagram';
import { Popover, PopoverContent, PopoverTrigger } from './popover';
import { cn } from '@/lib/utils';

/**
 * Live Mermaid block. The diagram renders inline in the editor; the source is
 * edited in a Popover with a live preview, and closing the popover (Done,
 * Escape, or clicking away) commits and re-renders. Source lives in the
 * `content` attribute (atom node).
 *
 * Why the editor is a Popover and not an inline textarea: an editable field
 * placed inside the ProseMirror DOM fights the editor's selection sync — the
 * moment the textarea takes focus, ProseMirror maps the DOM selection onto the
 * atom node (selecting it) and the field loses focus. The Popover content is
 * rendered in a portal at the document root, completely outside the editor's
 * DOM, so focus/caret/selection all behave like a normal form field.
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
    const [open, setOpen] = useState<boolean>(false);
    const [draft, setDraft] = useState<string>(content);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        setDraft(node.attrs.content || '');
    }, [node.attrs.content]);

    const openEditor = () => {
        setDraft(node.attrs.content || '');
        setOpen(true);
    };
    const commitAndClose = () => {
        if (draft !== (node.attrs.content || '')) {
            updateAttributes({ content: draft });
        }
        setOpen(false);
    };
    // Radix drives this on Done, Escape, and click-outside.
    const onOpenChange = (next: boolean) => (next ? openEditor() : commitAndClose());

    // Read-only surfaces (disabled editor) just render the diagram.
    if (!editable) {
        return (
            <NodeViewWrapper className="my-3">
                <MermaidDiagram chart={content} />
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
            {/* modal traps focus in the portal so ProseMirror can't reclaim it
                and snap the popover shut (the open/close flicker). */}
            <Popover open={open} onOpenChange={onOpenChange} modal>
                <PopoverTrigger asChild>
                    <button
                        type="button"
                        title="Edit diagram"
                        className="absolute left-2 top-2 z-10 flex items-center gap-1 rounded bg-slate-800/90 px-1.5 py-0.5 text-[11px] text-slate-300 opacity-0 shadow transition-opacity hover:bg-slate-700 hover:text-slate-100 group-hover:opacity-100"
                    >
                        <Pencil className="h-3 w-3" /> Edit
                    </button>
                </PopoverTrigger>
                <PopoverContent
                    align="start"
                    side="bottom"
                    className="w-[min(90vw,560px)] p-0 bg-slate-900 border-slate-700"
                    onOpenAutoFocus={(e) => {
                        // Focus the source field, not the Done button (first focusable).
                        e.preventDefault();
                        requestAnimationFrame(() => {
                            const el = textareaRef.current;
                            if (el) {
                                el.focus();
                                const len = el.value.length;
                                el.setSelectionRange(len, len);
                            }
                        });
                    }}
                >
                    <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5">
                        <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
                            Edit Mermaid diagram
                        </span>
                        <button
                            type="button"
                            onClick={commitAndClose}
                            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-slate-800 hover:text-slate-100"
                        >
                            <Check className="h-3 w-3" /> Done
                        </button>
                    </div>
                    <textarea
                        ref={textareaRef}
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        spellCheck={false}
                        rows={Math.max(5, draft.split('\n').length + 1)}
                        placeholder="graph TD; A --> B"
                        className="w-full resize-y bg-transparent px-3 py-2 font-mono text-[12px] leading-relaxed text-slate-200 outline-none"
                    />
                    <div className="max-h-[320px] overflow-auto border-t border-slate-800 p-2">
                        <div className="mb-1 px-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                            Preview
                        </div>
                        {draft.trim() ? (
                            <MermaidDiagram chart={draft} />
                        ) : (
                            <div className="py-4 text-center text-xs text-slate-500">Empty diagram</div>
                        )}
                    </div>
                </PopoverContent>
            </Popover>

            <div className="p-2" onDoubleClick={openEditor} title="Double-click to edit">
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

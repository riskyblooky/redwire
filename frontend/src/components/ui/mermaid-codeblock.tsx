'use client';

import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import {
    ReactNodeViewRenderer,
    NodeViewWrapper,
    NodeViewContent,
    NodeViewProps,
} from '@tiptap/react';
import { useEffect, useState } from 'react';
import { MermaidDiagram } from './mermaid-diagram';

/**
 * CodeBlockLowlight with a node view that renders a live diagram preview under
 * any block whose language is `mermaid`.
 *
 * The editable part stays a normal code block — ProseMirror owns the
 * `NodeViewContent` (the <code>), so typing / selection / lowlight highlighting
 * all behave exactly as the stock extension. The mermaid preview is an inert,
 * contentEditable=false sibling: pure display, no inputs or buttons, so it
 * introduces none of the event-capture problems an interactive node widget
 * would. Non-mermaid code blocks render identically to before.
 *
 * This is what makes mermaid usable in notes, which are edit-only (the
 * collaborative editor with no separate rendered view) — the diagram shows
 * right under its source as you type.
 */

function CodeBlockView({ node }: NodeViewProps) {
    const language: string = node.attrs.language || '';
    const isMermaid = language.toLowerCase() === 'mermaid';
    const code = node.textContent;

    // Debounce the source fed to the renderer so a mermaid re-layout doesn't
    // run on every keystroke.
    const [debounced, setDebounced] = useState(code);
    useEffect(() => {
        if (!isMermaid) return;
        const t = setTimeout(() => setDebounced(code), 400);
        return () => clearTimeout(t);
    }, [code, isMermaid]);

    return (
        <NodeViewWrapper className="code-block-nv">
            <pre className="hljs">
                <NodeViewContent as={'code' as any} className={language ? `language-${language}` : undefined} />
            </pre>
            {isMermaid && (
                <div
                    contentEditable={false}
                    className="mt-1 mb-2 rounded-lg border border-slate-700/60 bg-slate-900/40 p-2"
                >
                    <div className="mb-1 px-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                        Mermaid preview
                    </div>
                    {debounced.trim() ? (
                        <MermaidDiagram chart={debounced} />
                    ) : (
                        <div className="py-4 text-center text-xs text-slate-500">Empty diagram</div>
                    )}
                </div>
            )}
        </NodeViewWrapper>
    );
}

export const CodeBlockWithMermaid = CodeBlockLowlight.extend({
    addNodeView() {
        return ReactNodeViewRenderer(CodeBlockView);
    },
});

export default CodeBlockWithMermaid;

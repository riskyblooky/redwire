'use client';

/**
 * Shared global styling for the TipTap editors (`.tiptap` content) — headings,
 * task-list checkboxes, lists, blockquotes, inline code, Atom One Dark code
 * blocks + lowlight (highlight.js) syntax tokens, and mention chips.
 *
 * Rendered by BOTH the standard editor (`tiptap-editor.tsx`) and the
 * collaborative notes editor (`collaborative-editor.tsx`) so their Markdown
 * rendering can never drift apart again. styled-jsx `global` injects these
 * whenever either editor is mounted.
 */
export function EditorStyles({ currentUsername }: { currentUsername?: string | null }) {
    return (
        <style jsx global>{`
            .tiptap p.is-editor-empty:first-child::before {
                color: #64748b;
                content: attr(data-placeholder);
                float: left;
                height: 0;
                pointer-events: none;
            }
            /* Headings */
            .tiptap h1 {
                font-size: 1.75rem;
                font-weight: 700;
                color: #f1f5f9;
                margin: 1rem 0 0.5rem;
                line-height: 1.3;
                border-bottom: 1px solid #1e293b;
                padding-bottom: 0.375rem;
            }
            .tiptap h2 {
                font-size: 1.375rem;
                font-weight: 600;
                color: #e2e8f0;
                margin: 0.875rem 0 0.375rem;
                line-height: 1.35;
            }
            .tiptap h3 {
                font-size: 1.125rem;
                font-weight: 600;
                color: #cbd5e1;
                margin: 0.75rem 0 0.25rem;
                line-height: 1.4;
            }
            /* Task list / Checkboxes */
            .tiptap ul[data-type="taskList"] {
                list-style: none;
                padding: 0;
            }
            .tiptap ul[data-type="taskList"] li {
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }
            .tiptap ul[data-type="taskList"] li > label {
                flex: 0 0 auto;
                user-select: none;
                display: flex;
                align-items: center;
            }
            .tiptap ul[data-type="taskList"] li > label input[type="checkbox"] {
                appearance: none;
                -webkit-appearance: none;
                width: 1rem;
                height: 1rem;
                border: 2px solid #6366f1;
                border-radius: 0.25rem;
                background: transparent;
                cursor: pointer;
                position: relative;
                vertical-align: middle;
            }
            .tiptap ul[data-type="taskList"] li > label input[type="checkbox"]:checked {
                background: #6366f1;
                border-color: #6366f1;
            }
            .tiptap ul[data-type="taskList"] li > label input[type="checkbox"]:checked::after {
                content: '✓';
                position: absolute;
                top: -2px;
                left: 1px;
                color: white;
                font-size: 0.75rem;
                font-weight: bold;
            }
            .tiptap ul[data-type="taskList"] li > div {
                flex: 1 1 auto;
            }
            /* Zero the paragraph margins inside a task item so the text lines up
               with the checkbox instead of being pushed down by default p margins. */
            .tiptap ul[data-type="taskList"] li > div > p {
                margin: 0;
                line-height: 1.4;
            }
            .tiptap img {
                max-width: 100%;
                height: auto;
                border-radius: 0.5rem;
            }
            .tiptap ul {
                list-style-type: disc;
                padding-left: 1.5rem;
                margin: 0.5rem 0;
            }
            .tiptap ol {
                list-style-type: decimal;
                padding-left: 1.5rem;
                margin: 0.5rem 0;
            }
            .tiptap ul li, .tiptap ol li {
                margin: 0.25rem 0;
            }
            .tiptap ul li::marker {
                color: #94a3b8;
            }
            .tiptap ol li::marker {
                color: #94a3b8;
            }
            .tiptap blockquote {
                border-left: 3px solid #6366f1;
                padding-left: 1rem;
                margin: 0.75rem 0;
                color: #94a3b8;
                background: rgba(99, 102, 241, 0.05);
                border-radius: 0 0.375rem 0.375rem 0;
                padding: 0.5rem 1rem;
            }
            .tiptap code:not(pre code) {
                background: rgba(99, 102, 241, 0.15);
                border: 1px solid rgba(99, 102, 241, 0.25);
                border-radius: 0.25rem;
                padding: 0.125rem 0.375rem;
                font-size: 0.85em;
                font-family: 'JetBrains Mono', monospace;
                color: #c4b5fd;
            }

            /* Atom One Dark — code blocks */
            .tiptap pre {
                background: #282c34;
                border: 1px solid #3e4451;
                border-radius: 0.5rem;
                color: #abb2bf;
                font-family: 'JetBrains Mono', monospace;
                padding: 0.75rem 1rem;
                overflow-x: auto;
            }
            .tiptap pre code {
                background: none;
                color: inherit;
                font-size: 0.875rem;
                padding: 0;
            }

            /* Atom One Dark — lowlight (highlight.js) syntax tokens */
            .tiptap .hljs-comment,
            .tiptap .hljs-quote {
                color: #5c6370;
                font-style: italic;
            }
            .tiptap .hljs-doctag,
            .tiptap .hljs-keyword,
            .tiptap .hljs-formula {
                color: #c678dd;
            }
            .tiptap .hljs-section,
            .tiptap .hljs-name,
            .tiptap .hljs-selector-tag,
            .tiptap .hljs-deletion,
            .tiptap .hljs-subst {
                color: #e06c75;
            }
            .tiptap .hljs-literal {
                color: #56b6c2;
            }
            .tiptap .hljs-string,
            .tiptap .hljs-regexp,
            .tiptap .hljs-addition,
            .tiptap .hljs-attribute,
            .tiptap .hljs-meta .hljs-string {
                color: #98c379;
            }
            .tiptap .hljs-attr,
            .tiptap .hljs-variable,
            .tiptap .hljs-template-variable,
            .tiptap .hljs-type,
            .tiptap .hljs-selector-class,
            .tiptap .hljs-selector-attr,
            .tiptap .hljs-selector-pseudo,
            .tiptap .hljs-number {
                color: #d19a66;
            }
            .tiptap .hljs-symbol,
            .tiptap .hljs-bullet,
            .tiptap .hljs-link,
            .tiptap .hljs-meta,
            .tiptap .hljs-selector-id,
            .tiptap .hljs-title {
                color: #61afef;
            }
            .tiptap .hljs-built_in,
            .tiptap .hljs-title.class_,
            .tiptap .hljs-class .hljs-title {
                color: #e5c07b;
            }
            .tiptap .hljs-emphasis {
                font-style: italic;
            }
            .tiptap .hljs-strong {
                font-weight: 700;
            }
            .tiptap .hljs-link {
                text-decoration: underline;
            }
            /* Mention chips */
            .tiptap .mention {
                background: rgba(20, 184, 166, 0.15);
                border: 1px solid rgba(20, 184, 166, 0.3);
                border-radius: 0.375rem;
                padding: 0.125rem 0.375rem;
                color: #2dd4bf;
                font-weight: 500;
                font-size: 0.9em;
                white-space: nowrap;
                cursor: default;
            }
            ${currentUsername ? `
            .tiptap .mention[data-label="${currentUsername}"] {
                background: rgba(245, 158, 11, 0.15);
                border-color: rgba(245, 158, 11, 0.3);
                color: #fbbf24;
            }
            ` : ''}
        `}</style>
    );
}

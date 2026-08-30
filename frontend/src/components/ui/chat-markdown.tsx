'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import { cn } from '@/lib/utils';

/**
 * Compact markdown renderer for the in-editor AI chat bubbles. GFM enabled
 * (tables, task lists, strikethrough) and sanitized. Styling is intentionally
 * tight to fit the small panel — see ChatMarkdownStyles, rendered once by the
 * panel so the global CSS isn't duplicated per message.
 */
export function ChatMarkdown({ content, className }: { content: string; className?: string }) {
    return (
        <div className={cn('chat-md break-words', className)}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
                {content}
            </ReactMarkdown>
        </div>
    );
}

/** Global CSS for `.chat-md`, prefixed so it only touches chat bubbles.
 *  Render this ONCE (not per message). */
export function ChatMarkdownStyles() {
    return (
        <style jsx global>{`
            .chat-md { font-size: 12px; line-height: 1.55; }
            .chat-md > :first-child { margin-top: 0; }
            .chat-md > :last-child { margin-bottom: 0; }
            .chat-md p { margin: 0.35rem 0; }
            .chat-md h1, .chat-md h2, .chat-md h3, .chat-md h4 {
                font-weight: 600; color: #f1f5f9; margin: 0.55rem 0 0.25rem; line-height: 1.3;
            }
            .chat-md h1 { font-size: 0.92rem; }
            .chat-md h2 { font-size: 0.86rem; }
            .chat-md h3, .chat-md h4 { font-size: 0.8rem; }
            .chat-md ul { list-style: disc; padding-left: 1.1rem; margin: 0.35rem 0; }
            .chat-md ol { list-style: decimal; padding-left: 1.2rem; margin: 0.35rem 0; }
            .chat-md li { margin: 0.15rem 0; }
            .chat-md li::marker { color: #64748b; }
            .chat-md a { color: #60a5fa; text-decoration: underline; }
            .chat-md a:hover { color: #93bbfc; }
            .chat-md strong { color: #f1f5f9; font-weight: 600; }
            .chat-md em { font-style: italic; }
            .chat-md code { font-family: ui-monospace, 'JetBrains Mono', monospace; font-size: 0.85em; }
            .chat-md :not(pre) > code {
                background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.25);
                border-radius: 0.25rem; padding: 0.05rem 0.3rem; color: #c4b5fd;
            }
            .chat-md pre {
                background: rgba(2,6,23,0.7); border: 1px solid rgba(51,65,85,0.6);
                border-radius: 0.375rem; padding: 0.5rem 0.6rem; overflow-x: auto; margin: 0.4rem 0;
            }
            .chat-md pre code { background: none; border: none; padding: 0; color: #cbd5e1; }
            .chat-md blockquote {
                border-left: 2px solid rgba(139,92,246,0.5); padding-left: 0.5rem;
                margin: 0.35rem 0; color: #94a3b8;
            }
            .chat-md hr { border: none; border-top: 1px solid rgba(51,65,85,0.6); margin: 0.5rem 0; }
            .chat-md table { border-collapse: collapse; margin: 0.4rem 0; font-size: 0.9em; display: block; overflow-x: auto; }
            .chat-md th, .chat-md td { border: 1px solid #334155; padding: 0.2rem 0.45rem; text-align: left; }
            .chat-md th { background: #1e293b; color: #f1f5f9; font-weight: 600; }
        `}</style>
    );
}

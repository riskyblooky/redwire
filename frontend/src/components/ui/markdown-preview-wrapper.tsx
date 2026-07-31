'use client';

import React from 'react';
import ReactMarkdownPreview from '@uiw/react-markdown-preview';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { AuthImage } from './auth-image';
import { MermaidDiagram } from './mermaid-diagram';
import { useUsers } from '@/lib/hooks/use-users';
import { UserAvatar } from './user-avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './tooltip';

// Reconstruct the raw text of a fenced code block from react-markdown's
// (possibly syntax-highlighted) children. Highlighters wrap each source line
// in a `.code-line` element and split tokens into spans; walking the tree and
// re-inserting a newline at each line boundary gives back the original source.
function extractCodeText(children: any): string {
    if (children == null) return '';
    if (typeof children === 'string') return children;
    if (typeof children === 'number') return String(children);
    if (Array.isArray(children)) return children.map(extractCodeText).join('');
    if (React.isValidElement(children)) {
        const props: any = (children as any).props || {};
        const cls: string = typeof props.className === 'string' ? props.className : '';
        const inner = extractCodeText(props.children);
        if (cls.split(' ').includes('code-line') && !inner.endsWith('\n')) {
            return inner + '\n';
        }
        return inner;
    }
    return '';
}

/** A @mention chip that reveals the mentioned user's avatar + display name on
 *  hover. Falls back to the plain styled chip when the user can't be resolved
 *  (e.g. the viewer can't list users, or the username no longer exists). */
function MentionChip({ className, children }: { className?: string; children: React.ReactNode }) {
    const { data: users = [] } = useUsers();
    const text = React.Children.toArray(children)
        .map((c) => (typeof c === 'string' ? c : ''))
        .join('');
    const username = text.replace(/^@/, '').trim();
    const u = users.find((x) => x.username.toLowerCase() === username.toLowerCase());

    const chip = <span className={className}>{children}</span>;
    if (!u) return chip;

    return (
        <TooltipProvider delayDuration={150}>
            <Tooltip>
                <TooltipTrigger asChild>{chip}</TooltipTrigger>
                <TooltipContent side="top" className="bg-slate-800 border-slate-700">
                    <div className="flex items-center gap-2">
                        <UserAvatar
                            user={{ id: u.id, username: u.username, profile_photo: u.profile_photo }}
                            className="h-6 w-6 text-[8px]"
                        />
                        <div className="leading-tight">
                            <div className="text-xs font-semibold text-white">{u.full_name || u.username}</div>
                            <div className="text-[10px] text-slate-400">@{u.username}</div>
                        </div>
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

const COMPONENTS = {
    // Route img tags through AuthImage so /api/markdown-images/* fetches
    // with the user's JWT. External / data: URLs fall through to <img>.
    img: ({ node, ...rest }: any) => <AuthImage {...rest} />,
    // ```mermaid fenced blocks render as live diagrams. We intercept at the
    // <pre> level (not <code>) so the whole code-block wrapper is replaced by
    // the diagram — a <div> inside <pre> would be invalid and inherit the
    // monospace code styling. Non-mermaid fences pass straight through with
    // their highlighted children intact.
    pre: ({ node, children, ...rest }: any) => {
        const kids = React.Children.toArray(children);
        const codeEl = kids.find((c) => React.isValidElement(c)) as React.ReactElement | undefined;
        const cls: string =
            codeEl && typeof (codeEl.props as any)?.className === 'string'
                ? (codeEl.props as any).className
                : '';
        if (cls.split(' ').includes('language-mermaid')) {
            const chart = extractCodeText((codeEl!.props as any).children).replace(/\n+$/, '');
            return <MermaidDiagram chart={chart} />;
        }
        return <pre {...rest}>{children}</pre>;
    },
    // @mention chips (class "mention-tag", emitted by processMentionsInMarkdown)
    // become hover targets that reveal the user's avatar + display name. Every
    // other span passes through unchanged.
    span: ({ node, className, children, ...rest }: any) => {
        if (typeof className === 'string' && className.split(' ').includes('mention-tag')) {
            return <MentionChip className={className}>{children}</MentionChip>;
        }
        return <span className={className} {...rest}>{children}</span>;
    },
};

// skipHtml=false is required so TipTap-emitted formatting renders
// (<u>, <mark>, <sub>/<sup>, <span style="color:…">, alignment, etc.).
// To keep that behavior without leaving the raw-HTML XSS escape hatch
// open, we layer rehype-sanitize after rehype-raw with a schema
// extended to allow the safe subset of inline formatting tags and
// attributes that TipTap actually emits. <script>, <iframe>, <object>,
// <embed>, <form>, on*= handlers, and javascript: URLs all stay
// blocked by the underlying defaultSchema.
const SANITIZE_SCHEMA = {
    ...defaultSchema,
    tagNames: [
        ...(defaultSchema.tagNames || []),
        'u', 'mark', 'sub', 'sup', 'span', 'font',
    ],
    attributes: {
        ...(defaultSchema.attributes || {}),
        // Allow inline `style` (color + text-align only — the two
        // attributes TipTap's text-style and text-align extensions use)
        // plus class on span / p / div / td / th / li / etc.
        span: [
            ...((defaultSchema.attributes && defaultSchema.attributes.span) || []),
            ['style', /^color:\s*[#\w(),.\s%-]+;?$/i],
            'className',
            'class',
        ],
        p: [
            ...((defaultSchema.attributes && defaultSchema.attributes.p) || []),
            ['style', /^text-align:\s*(left|right|center|justify);?$/i],
        ],
        // Tables can carry alignment; the underlying TipTap table extension
        // emits text-align on td/th.
        td: [
            ...((defaultSchema.attributes && defaultSchema.attributes.td) || []),
            ['style', /^text-align:\s*(left|right|center|justify);?$/i],
        ],
        th: [
            ...((defaultSchema.attributes && defaultSchema.attributes.th) || []),
            ['style', /^text-align:\s*(left|right|center|justify);?$/i],
        ],
        font: ['color'],
    },
};

export default function MarkdownPreviewWrapper(props: any) {
    const [mounted, setMounted] = React.useState(false);

    React.useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) {
        return <div className="h-full w-full min-h-[20px]" />;
    }

    // Pull the caller's rehypePlugins (if any) and append the sanitizer
    // so it runs LAST — the underlying @uiw/react-markdown-preview
    // pipeline already inserts rehype-raw to honor skipHtml=false, and
    // sanitize must come after raw to actually see the inlined HTML.
    const callerRehype = props.rehypePlugins || [];
    const rehypePlugins = [...callerRehype, [rehypeSanitize, SANITIZE_SCHEMA]];

    return (
        <ReactMarkdownPreview
            skipHtml={false}
            components={{ ...COMPONENTS, ...(props.components || {}) }}
            {...props}
            rehypePlugins={rehypePlugins}
        />
    );
}

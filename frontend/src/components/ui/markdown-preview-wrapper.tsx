'use client';

import React from 'react';
import ReactMarkdownPreview from '@uiw/react-markdown-preview';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { AuthImage } from './auth-image';
import { useUsers } from '@/lib/hooks/use-users';
import { UserAvatar } from './user-avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './tooltip';

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

'use client';

import React from 'react';
import ReactMarkdownPreview from '@uiw/react-markdown-preview';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { AuthImage } from './auth-image';

const COMPONENTS = {
    // Route img tags through AuthImage so /api/markdown-images/* fetches
    // with the user's JWT. External / data: URLs fall through to <img>.
    img: ({ node, ...rest }: any) => <AuthImage {...rest} />,
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

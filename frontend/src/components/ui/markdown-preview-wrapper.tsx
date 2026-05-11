'use client';

import React from 'react';
import ReactMarkdownPreview from '@uiw/react-markdown-preview';
import { AuthImage } from './auth-image';

const COMPONENTS = {
    // Route img tags through AuthImage so /api/markdown-images/* fetches
    // with the user's JWT. External / data: URLs fall through to <img>.
    img: ({ node, ...rest }: any) => <AuthImage {...rest} />,
};

export default function MarkdownPreviewWrapper(props: any) {
    const [mounted, setMounted] = React.useState(false);

    React.useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) {
        return <div className="h-full w-full min-h-[20px]" />;
    }

    // skipHtml=false so TipTap-emitted HTML (underline, mark, sub/sup,
    // colour spans, inline alignment, etc.) renders. Markdown content
    // is authored by trusted engagement users, so the HTML escape hatch
    // is acceptable here.
    return (
        <ReactMarkdownPreview
            skipHtml={false}
            components={{ ...COMPONENTS, ...(props.components || {}) }}
            {...props}
        />
    );
}

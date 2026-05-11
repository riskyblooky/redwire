'use client';

import Image from '@tiptap/extension-image';
import { ReactNodeViewRenderer, NodeViewWrapper, NodeViewProps } from '@tiptap/react';
import { AuthImage } from './auth-image';

/**
 * Custom NodeView for the TipTap Image extension. For markdown-images
 * URLs it goes through AuthImage (axios + blob URL). Everything else
 * falls back to a regular <img>.
 *
 * We keep the underlying schema as the stock Image node so markdown
 * round-trips as `![alt](src)` exactly as before.
 */

function AuthImageNodeView({ node }: NodeViewProps) {
    const src = (node.attrs.src ?? '') as string;
    const alt = (node.attrs.alt ?? '') as string;
    const title = (node.attrs.title ?? undefined) as string | undefined;

    return (
        <NodeViewWrapper
            as="span"
            className="inline-block align-middle"
            data-drag-handle
        >
            <AuthImage
                src={src}
                alt={alt}
                title={title}
                className="max-w-full rounded border border-slate-800/60"
            />
        </NodeViewWrapper>
    );
}

export const AuthAwareImage = Image.extend({
    addNodeView() {
        return ReactNodeViewRenderer(AuthImageNodeView);
    },
});

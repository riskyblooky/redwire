'use client';

import React from 'react';

/**
 * Renders text with @mentions styled as colored chips.
 * Self-mentions (matching currentUsername) use a gold/amber style.
 * Other mentions use teal.
 */
export function renderMentions(
    text: string,
    currentUsername?: string | null
): React.ReactNode[] {
    if (!text) return [text];

    const parts: React.ReactNode[] = [];
    const regex = /@(\w+)/g;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(text)) !== null) {
        // Add text before the match
        if (match.index > lastIndex) {
            parts.push(text.slice(lastIndex, match.index));
        }

        const username = match[1];
        const isSelf = currentUsername && username.toLowerCase() === currentUsername.toLowerCase();

        parts.push(
            <span
                key={`mention-${match.index}`}
                className={
                    isSelf
                        ? 'mention-tag mention-self'
                        : 'mention-tag'
                }
            >
                @{username}
            </span>
        );

        lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < text.length) {
        parts.push(text.slice(lastIndex));
    }

    return parts.length > 0 ? parts : [text];
}

/**
 * Pre-processes markdown source to wrap @mentions in styled HTML spans
 * for use in markdown preview renderers that support inline HTML.
 */
export function processMentionsInMarkdown(
    source: string,
    currentUsername?: string | null
): string {
    if (!source) return source;
    return source.replace(/@(\w+)/g, (full, username) => {
        const isSelf = currentUsername && username.toLowerCase() === currentUsername.toLowerCase();
        const cls = isSelf ? 'mention-tag mention-self' : 'mention-tag';
        return `<span class="${cls}">@${username}</span>`;
    });
}

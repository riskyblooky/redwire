'use client';

import React, { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useAuthStore } from '@/stores/auth-store';
import { processMentionsInMarkdown } from '@/lib/mention-utils';

import "@uiw/react-markdown-preview/markdown.css";

// Dynamic import for Tiptap editor to prevent SSR issues
const TiptapEditor = dynamic(() => import("./tiptap-editor"), {
    ssr: false,
    loading: () => <div className="h-[300px] w-full bg-slate-900/50 animate-pulse rounded-lg border border-slate-800" />
});

import MDPreview from "./markdown-preview-wrapper";

interface MarkdownEditorProps {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    disabled?: boolean;
    minHeight?: string;
    id?: string;
    className?: string;
    fieldContext?: { resourceType: string; fieldName: string };
    /** Required for paste/drop image upload. */
    engagementId?: string;
}

export function MarkdownEditor({ value, onChange, placeholder, disabled, minHeight = '300px', id, className, fieldContext, engagementId }: MarkdownEditorProps) {
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) {
        return <div className="h-[300px] w-full bg-slate-900/50 animate-pulse rounded-lg border border-slate-800" />;
    }

    return (
        <TiptapEditor
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            disabled={disabled}
            minHeight={minHeight}
            id={id}
            className={className}
            fieldContext={fieldContext}
            engagementId={engagementId}
        />
    );
}

export function MarkdownPreview({ value }: { value: string; theme?: string }) {
    const user = useAuthStore((s) => s.user);
    const processedValue = processMentionsInMarkdown(value, user?.username);

    return (
        <div className="markdown-preview-wrapper" data-color-mode="dark">
            <MDPreview source={processedValue} />
            <style jsx global>{`
                .wmde-markdown {
                    background-color: transparent !important;
                    color: #f8fafc !important;
                    font-size: 0.875rem !important;
                    line-height: 1.6 !important;
                }
                /* Headings */
                .wmde-markdown h1 {
                    font-size: 1.75rem !important;
                    font-weight: 700 !important;
                    color: #f1f5f9 !important;
                    margin: 1rem 0 0.5rem !important;
                    line-height: 1.3 !important;
                    border-bottom: 1px solid #1e293b !important;
                    padding-bottom: 0.375rem !important;
                }
                .wmde-markdown h2 {
                    font-size: 1.375rem !important;
                    font-weight: 600 !important;
                    color: #e2e8f0 !important;
                    margin: 0.875rem 0 0.375rem !important;
                    line-height: 1.35 !important;
                }
                .wmde-markdown h3 {
                    font-size: 1.125rem !important;
                    font-weight: 600 !important;
                    color: #cbd5e1 !important;
                    margin: 0.75rem 0 0.25rem !important;
                    line-height: 1.4 !important;
                }
                /* Task list checkboxes */
                .wmde-markdown input[type="checkbox"] {
                    appearance: none !important;
                    -webkit-appearance: none !important;
                    width: 1rem !important;
                    height: 1rem !important;
                    border: 2px solid #6366f1 !important;
                    border-radius: 0.25rem !important;
                    background: transparent !important;
                    cursor: pointer !important;
                    position: relative !important;
                    vertical-align: middle !important;
                    margin-right: 0.375rem !important;
                }
                .wmde-markdown input[type="checkbox"]:checked {
                    background: #6366f1 !important;
                    border-color: #6366f1 !important;
                }
                .wmde-markdown input[type="checkbox"]:checked::after {
                    content: '✓' !important;
                    position: absolute !important;
                    top: -2px !important;
                    left: 1px !important;
                    color: white !important;
                    font-size: 0.75rem !important;
                    font-weight: bold !important;
                }
                .wmde-markdown .task-list-item {
                    list-style: none !important;
                    display: flex !important;
                    align-items: flex-start !important;
                    gap: 0.25rem !important;
                }
                .wmde-markdown ul {
                    list-style-type: disc !important;
                    padding-left: 1.5rem !important;
                    margin: 0.5rem 0 !important;
                }
                .wmde-markdown ol {
                    list-style-type: decimal !important;
                    padding-left: 1.5rem !important;
                    margin: 0.5rem 0 !important;
                }
                .wmde-markdown ul li,
                .wmde-markdown ol li {
                    margin: 0.25rem 0 !important;
                    list-style: inherit !important;
                }
                .wmde-markdown ul li::marker {
                    color: #94a3b8;
                }
                .wmde-markdown ol li::marker {
                    color: #94a3b8;
                }
                .wmde-markdown blockquote {
                    border-left: 3px solid #6366f1 !important;
                    padding: 0.5rem 1rem !important;
                    margin: 0.75rem 0 !important;
                    color: #94a3b8 !important;
                    background: rgba(99, 102, 241, 0.05) !important;
                    border-radius: 0 0.375rem 0.375rem 0 !important;
                }
                .wmde-markdown code:not(pre code) {
                    background: rgba(99, 102, 241, 0.15) !important;
                    border: 1px solid rgba(99, 102, 241, 0.25) !important;
                    border-radius: 0.25rem !important;
                    padding: 0.125rem 0.375rem !important;
                    font-size: 0.85em !important;
                    color: #c4b5fd !important;
                }
                /* Atom One Dark — code blocks */
                .wmde-markdown pre {
                    background: #282c34 !important;
                    border: 1px solid #3e4451 !important;
                    border-radius: 0.5rem !important;
                    padding: 0.75rem 1rem !important;
                    overflow-x: auto !important;
                }
                .wmde-markdown pre code {
                    background: none !important;
                    border: none !important;
                    padding: 0 !important;
                    font-size: 0.875rem !important;
                    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
                    color: #abb2bf !important;
                }
                /* Atom One Dark — Prism syntax tokens */
                .wmde-markdown .token.comment,
                .wmde-markdown .token.prolog,
                .wmde-markdown .token.doctype,
                .wmde-markdown .token.cdata {
                    color: #5c6370 !important;
                    font-style: italic !important;
                }
                .wmde-markdown .token.punctuation {
                    color: #abb2bf !important;
                }
                .wmde-markdown .token.property,
                .wmde-markdown .token.tag,
                .wmde-markdown .token.boolean,
                .wmde-markdown .token.number,
                .wmde-markdown .token.constant,
                .wmde-markdown .token.symbol {
                    color: #d19a66 !important;
                }
                .wmde-markdown .token.selector,
                .wmde-markdown .token.attr-name,
                .wmde-markdown .token.string,
                .wmde-markdown .token.char,
                .wmde-markdown .token.builtin {
                    color: #98c379 !important;
                }
                .wmde-markdown .token.operator,
                .wmde-markdown .token.entity,
                .wmde-markdown .token.url,
                .wmde-markdown .token.variable {
                    color: #56b6c2 !important;
                }
                .wmde-markdown .token.atrule,
                .wmde-markdown .token.attr-value,
                .wmde-markdown .token.keyword {
                    color: #c678dd !important;
                }
                .wmde-markdown .token.function,
                .wmde-markdown .token.class-name {
                    color: #61afef !important;
                }
                .wmde-markdown .token.regex,
                .wmde-markdown .token.important {
                    color: #e5c07b !important;
                }
                .wmde-markdown .token.italic {
                    font-style: italic !important;
                }
                .wmde-markdown .token.bold {
                    font-weight: bold !important;
                }
                /* Code title / language label */
                .wmde-markdown .code-highlight {
                    background: transparent !important;
                }
                .wmde-markdown .code-line {
                    display: block;
                }
                .wmde-markdown a {
                    color: #60a5fa !important;
                    text-decoration: underline !important;
                }
                .wmde-markdown a:hover {
                    color: #93bbfc !important;
                }
                /* Mention styling */
                .mention-tag {
                    background: rgba(20, 184, 166, 0.15);
                    border: 1px solid rgba(20, 184, 166, 0.3);
                    border-radius: 0.375rem;
                    padding: 0.125rem 0.375rem;
                    color: #2dd4bf;
                    font-weight: 500;
                    font-size: 0.9em;
                    white-space: nowrap;
                }
                .mention-tag.mention-self {
                    background: rgba(245, 158, 11, 0.15);
                    border-color: rgba(245, 158, 11, 0.3);
                    color: #fbbf24;
                }
                /* Tables */
                .wmde-markdown table {
                    border-collapse: collapse !important;
                    margin: 0.75rem 0 !important;
                    width: auto !important;
                    background: rgba(15, 23, 42, 0.4) !important;
                    border-radius: 0.375rem !important;
                    overflow: hidden !important;
                }
                .wmde-markdown th,
                .wmde-markdown td {
                    border: 1px solid #1e293b !important;
                    padding: 0.4rem 0.7rem !important;
                    vertical-align: top !important;
                    color: #e2e8f0 !important;
                }
                .wmde-markdown th {
                    background: #1e293b !important;
                    color: #f8fafc !important;
                    font-weight: 600 !important;
                    text-align: left !important;
                }
                .wmde-markdown tr:nth-child(even) td {
                    background: rgba(30, 41, 59, 0.25) !important;
                }
                /* Underline / mark / sub / sup */
                .wmde-markdown u {
                    text-decoration: underline !important;
                }
                .wmde-markdown mark {
                    background: rgba(253, 230, 138, 0.35) !important;
                    color: inherit !important;
                    padding: 0 0.15em !important;
                    border-radius: 0.125rem !important;
                }
                .wmde-markdown sub { vertical-align: sub; font-size: 0.75em; }
                .wmde-markdown sup { vertical-align: super; font-size: 0.75em; }
            `}</style>
        </div>
    );
}

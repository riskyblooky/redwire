'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Sparkles, Send, X, ClipboardPaste, Loader2, Database, TextSelect, ListChecks } from 'lucide-react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { EditorFieldContext } from '@/lib/types';
import { ChatMarkdown, ChatMarkdownStyles } from './chat-markdown';

// Sentinel markers the backend wraps around untrusted tool output. They must
// never reach the field, but a weaker model can echo them into its answer.
const TOOL_DATA_BEGIN = '<<<REDWIRE_UNTRUSTED_TOOL_DATA_BEGIN>>>';
const TOOL_DATA_END = '<<<REDWIRE_UNTRUSTED_TOOL_DATA_END>>>';

/** Strip any tool-data block the model echoed back so raw tool JSON never lands
 *  in the editor: complete BEGIN…END spans, an unclosed BEGIN still streaming,
 *  and stray markers. */
function sanitizeAiOutput(s: string): string {
    if (!s) return s;
    let out = s.replace(new RegExp(`${TOOL_DATA_BEGIN}[\\s\\S]*?${TOOL_DATA_END}`, 'g'), '');
    const begin = out.indexOf(TOOL_DATA_BEGIN);
    if (begin !== -1) out = out.slice(0, begin);
    return out.split(TOOL_DATA_END).join('');
}

/** Three bouncing dots — a live "thinking / working" indicator. */
const AiThinkingDots = () => (
    <span className="inline-flex items-end gap-[3px] ml-1 align-middle">
        {[0, 1, 2].map(i => (
            <span
                key={i}
                className="w-1 h-1 rounded-full bg-current animate-bounce"
                style={{ animationDelay: `${i * 160}ms`, animationDuration: '1s' }}
            />
        ))}
    </span>
);

type AiMessage = { role: string; content: string; replaceRange?: { from: number; to: number }; review?: boolean };

interface AiAssistantPanelProps {
    /** The TipTap editor instance this assistant reads/writes. */
    editor: any;
    /** What is being edited — gates the panel (no fieldContext → hidden) and
     *  grounds the prompt. */
    fieldContext?: EditorFieldContext;
    /** Upper bound (px) for the split-drag handle, so growing the assistant
     *  never crushes the editor above it. */
    maxHeight?: number;
}

/**
 * The in-editor AI assistant: an "Ask AI" chat + a readability "Review" pass,
 * docked below any TipTap editor. Self-contained — it manages its own state,
 * streams from /ai/chat, tracks the editor selection to scope edits, and can
 * insert/replace its output. A split handle at its top resizes the assistant
 * vs the editor above (the editor content should be flex-1 so the total is
 * fixed). Renders nothing unless AI is enabled and a fieldContext is given.
 */
export function AiAssistantPanel({ editor, fieldContext, maxHeight }: AiAssistantPanelProps) {
    const { data: aiStatus } = useQuery<{ enabled: boolean; model: string; mcp_enabled: boolean; mcp_url: string }>({
        queryKey: ['ai', 'status'],
        queryFn: async () => {
            const resp = await api.get('/ai/settings/status');
            return resp.data;
        },
        staleTime: 60_000,
        retry: false,
    });
    const aiEnabled = aiStatus?.enabled && !!fieldContext;

    const [aiOpen, setAiOpen] = useState(false);
    const [aiMessages, setAiMessages] = useState<AiMessage[]>([]);
    const [aiInput, setAiInput] = useState('');
    const [aiSelection, setAiSelection] = useState<{ text: string; from: number; to: number } | null>(null);
    const [aiToolActivity, setAiToolActivity] = useState<string | null>(null);
    const [aiStreaming, setAiStreaming] = useState(false);
    // Height (px) the panel takes; the editor above flexes to fill the rest.
    const [panelHeight, setPanelHeight] = useState(210);
    const aiScrollRef = useRef<HTMLDivElement>(null);
    const aiInputRef = useRef<HTMLInputElement>(null);
    const splitRef = useRef<{ startY: number; startH: number } | null>(null);
    const maxRef = useRef(maxHeight ?? 640);
    useEffect(() => { maxRef.current = maxHeight ?? 640; }, [maxHeight]);
    const clampedPanel = Math.max(110, Math.min(panelHeight, maxHeight ?? 640));

    // Track the current non-empty selection so the assistant can scope edits to
    // it and its reply can replace that exact range.
    useEffect(() => {
        if (!editor) return;
        const handler = () => {
            const { from, to } = editor.state.selection;
            const selText = to > from ? editor.state.doc.textBetween(from, to, '\n\n', '\n') : '';
            if (selText.trim()) setAiSelection({ text: selText, from, to });
            else setAiSelection(null);
        };
        editor.on('selectionUpdate', handler);
        return () => { editor.off('selectionUpdate', handler); };
    }, [editor]);

    useEffect(() => {
        if (aiScrollRef.current) aiScrollRef.current.scrollTop = aiScrollRef.current.scrollHeight;
    }, [aiMessages]);

    const currentEditorMarkdown = useCallback((): string => {
        return editor ? ((editor.storage as any).markdown?.getMarkdown?.() || '') : '';
    }, [editor]);

    const handleInsertAiResponse = useCallback((content: string, range?: { from: number; to: number }) => {
        if (!editor) return;
        if (range) {
            const size = editor.state.doc.content.size;
            const from = Math.max(0, Math.min(range.from, size));
            const to = Math.max(from, Math.min(range.to, size));
            editor.chain().focus().insertContentAt({ from, to }, content).run();
        } else {
            editor.chain().focus().insertContent(content).run();
        }
    }, [editor]);

    // Shared fetch + SSE stream loop. The caller appends the assistant
    // placeholder as the last message (with any UI flags); this fills its
    // content and preserves those flags.
    const streamChat = useCallback(async (body: Record<string, any>) => {
        setAiStreaming(true);
        setAiToolActivity(null);
        try {
            const token = localStorage.getItem('access_token');
            const resp = await fetch(`${api.defaults.baseURL}/ai/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify(body),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                setAiMessages(prev => {
                    const updated = [...prev];
                    updated[updated.length - 1] = { ...updated[updated.length - 1], role: 'assistant', content: `Error: ${err.detail || resp.statusText}` };
                    return updated;
                });
                setAiStreaming(false);
                return;
            }
            const reader = resp.body?.getReader();
            const decoder = new TextDecoder();
            let assistantContent = '';
            let currentEvent = 'chunk';
            if (reader) {
                while (true) {
                    const { done, value: chunk } = await reader.read();
                    if (done) break;
                    const text = decoder.decode(chunk);
                    const lines = text.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim(); continue; }
                        if (line.startsWith('data: ')) {
                            const data = line.slice(6).trim();
                            if (data === '[DONE]') continue;
                            let parsed: any;
                            try { parsed = JSON.parse(data); } catch { continue; }
                            if (currentEvent === 'tool_call_pending') { setAiToolActivity(`Calling ${parsed.name || 'tool'}`); continue; }
                            if (currentEvent === 'tool_call_result') { setAiToolActivity(`Reading ${parsed.name || 'tool'}`); continue; }
                            if (currentEvent === 'tool_call_denied' || currentEvent === 'context_compacted' || currentEvent === 'done') continue;
                            if (parsed.error) {
                                assistantContent += `\nError: ${parsed.error}`;
                            } else {
                                const delta = parsed.choices?.[0]?.delta?.content || '';
                                if (delta) setAiToolActivity(null);
                                assistantContent += delta;
                            }
                            const cleaned = sanitizeAiOutput(assistantContent);
                            setAiMessages(prev => {
                                const updated = [...prev];
                                updated[updated.length - 1] = { ...updated[updated.length - 1], role: 'assistant', content: cleaned };
                                return updated;
                            });
                        }
                    }
                }
            }
        } catch (err: any) {
            setAiMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { ...updated[updated.length - 1], role: 'assistant', content: `Error: ${err.message}` };
                return updated;
            });
        }
        setAiToolActivity(null);
        setAiStreaming(false);
    }, []);

    const handleAiSend = useCallback(async () => {
        if (!aiInput.trim() || aiStreaming) return;
        const userMsg = { role: 'user', content: aiInput.trim() };
        const newMessages = [...aiMessages, userMsg];
        setAiInput('');
        const editorContent = currentEditorMarkdown();
        const sel = aiSelection;
        const selRange = sel ? { from: sel.from, to: sel.to } : undefined;
        setAiMessages([...newMessages, { role: 'assistant', content: '', replaceRange: selRange }]);
        await streamChat({
            mode: 'generate',
            messages: newMessages.map(m => ({ role: m.role, content: m.content })),
            editor_content: editorContent,
            editor_selection: sel?.text || '',
            field_context: fieldContext ? { resourceType: fieldContext.resourceType, fieldName: fieldContext.fieldName } : undefined,
            entity_context: fieldContext?.entityContext,
        });
    }, [aiInput, aiMessages, aiStreaming, fieldContext, aiSelection, streamChat, currentEditorMarkdown]);

    const handleAiReview = useCallback(async () => {
        if (aiStreaming) return;
        const editorContent = currentEditorMarkdown();
        if (!editorContent.trim()) {
            import('sonner').then(({ toast }) => toast.info('Nothing to review yet — write something first.'));
            return;
        }
        const label = fieldContext?.fieldName?.toLowerCase() || 'field';
        const userMsg = { role: 'user', content: `Review this ${label} for readability and AI-slop.` };
        setAiMessages(prev => [...prev, userMsg, { role: 'assistant', content: '', review: true }]);
        await streamChat({
            mode: 'review',
            messages: [{ role: 'user', content: userMsg.content }],
            editor_content: editorContent,
            field_context: fieldContext ? { resourceType: fieldContext.resourceType, fieldName: fieldContext.fieldName } : undefined,
        });
    }, [aiStreaming, fieldContext, streamChat, currentEditorMarkdown]);

    // Split-resize: drag up grows the assistant (editor above shrinks); down
    // shrinks it. Total stays fixed because the editor content is flex-1.
    const onSplitMove = useCallback((e: MouseEvent) => {
        const d = splitRef.current;
        if (!d) return;
        const dy = d.startY - e.clientY;
        setPanelHeight(Math.max(110, Math.min(maxRef.current, d.startH + dy)));
    }, []);
    const onSplitEnd = useCallback(() => {
        splitRef.current = null;
        window.removeEventListener('mousemove', onSplitMove);
        window.removeEventListener('mouseup', onSplitEnd);
        document.body.style.userSelect = '';
    }, [onSplitMove]);
    const onSplitStart = useCallback((e: React.MouseEvent) => {
        splitRef.current = { startY: e.clientY, startH: clampedPanel };
        window.addEventListener('mousemove', onSplitMove);
        window.addEventListener('mouseup', onSplitEnd);
        document.body.style.userSelect = 'none';
        e.preventDefault();
        e.stopPropagation();
    }, [clampedPanel, onSplitMove, onSplitEnd]);

    if (!aiEnabled) return null;

    return (
        <div
            className="border-t border-slate-800 flex flex-col shrink-0"
            style={aiOpen ? { height: clampedPanel } : undefined}
        >
            {aiOpen && (
                <div
                    onMouseDown={onSplitStart}
                    title="Drag to rebalance the editor and the assistant"
                    className="group/aisplit h-2.5 flex items-center justify-center cursor-ns-resize hover:bg-slate-800/40 transition-colors"
                >
                    <div className="w-8 h-0.5 rounded-full bg-slate-600 group-hover/aisplit:bg-slate-400" />
                </div>
            )}
            {!aiOpen ? (
                <button
                    type="button"
                    onClick={() => { setAiOpen(true); setTimeout(() => aiInputRef.current?.focus(), 100); }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-500 hover:text-violet-400 hover:bg-slate-900/50 transition-colors"
                >
                    <Sparkles className="h-3.5 w-3.5" />
                    <span>Ask AI for help with this {fieldContext?.fieldName?.toLowerCase() || 'field'}...</span>
                </button>
            ) : (
                <div className="bg-slate-950/60 backdrop-blur-sm flex flex-col flex-1 min-h-0">
                    <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-800/60">
                        <span className="text-[11px] font-semibold text-violet-400 flex items-center gap-1.5">
                            <Sparkles className="h-3 w-3" /> AI Assistant
                            {aiStatus?.model && <span className="text-slate-600 font-normal">· {aiStatus.model}</span>}
                        </span>
                        <div className="flex items-center gap-1">
                            <button
                                type="button"
                                onClick={handleAiReview}
                                disabled={aiStreaming}
                                title="Review this field for readability & AI-slop"
                                className="flex items-center gap-1 text-[10px] text-emerald-400 hover:text-emerald-300 px-1.5 py-0.5 rounded hover:bg-emerald-500/10 transition-colors disabled:opacity-40"
                            >
                                <ListChecks className="h-3 w-3" /> Review
                            </button>
                            {aiMessages.length > 0 && (
                                <button
                                    type="button"
                                    onClick={() => setAiMessages([])}
                                    className="text-[10px] text-slate-500 hover:text-slate-300 px-1.5 py-0.5 rounded hover:bg-slate-800 transition-colors"
                                >
                                    Clear
                                </button>
                            )}
                            <button
                                type="button"
                                onClick={() => setAiOpen(false)}
                                className="text-slate-500 hover:text-slate-300 p-0.5 rounded hover:bg-slate-800 transition-colors"
                            >
                                <X className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    </div>

                    <div ref={aiScrollRef} className="overflow-y-auto px-3 pb-2 pt-1 space-y-2 flex-1 min-h-0">
                        {aiMessages.length === 0 && (
                            <div className="h-full flex items-center justify-center text-center text-[11px] text-slate-600 px-4">
                                Ask a question about this {fieldContext?.fieldName?.toLowerCase() || 'field'}, or hit <span className="text-emerald-500/80 mx-1">Review</span> to check it for readability.
                            </div>
                        )}
                        {aiMessages.map((msg, i) => (
                            <div key={i} className={cn(
                                "text-xs rounded-lg px-3 py-2 max-w-[90%]",
                                msg.role === 'user'
                                    ? 'bg-violet-500/10 text-violet-200 border border-violet-500/20 ml-auto'
                                    : 'bg-slate-800/60 text-slate-300 border border-slate-700/40'
                            )}>
                                {msg.content ? (
                                    msg.role === 'assistant'
                                        ? <ChatMarkdown content={msg.content} />
                                        : <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                                ) : (aiStreaming && i === aiMessages.length - 1 && msg.role === 'assistant') ? (
                                    <div className="flex items-center gap-1.5 text-slate-400">
                                        {aiToolActivity ? (
                                            <><Database className="h-3 w-3 text-cyan-400" /><span className="text-cyan-300">{aiToolActivity}</span></>
                                        ) : (
                                            <><Sparkles className="h-3 w-3 text-violet-400" /><span>Thinking</span></>
                                        )}
                                        <AiThinkingDots />
                                    </div>
                                ) : msg.role === 'assistant' ? (
                                    <span className="italic text-slate-500">No content returned — try rephrasing your request.</span>
                                ) : null}
                                {msg.role === 'assistant' && msg.content && !aiStreaming && !msg.review && (
                                    <button
                                        type="button"
                                        onClick={() => handleInsertAiResponse(msg.content, msg.replaceRange)}
                                        className="flex items-center gap-1 mt-1.5 text-[10px] text-violet-400 hover:text-violet-300 transition-colors"
                                    >
                                        <ClipboardPaste className="h-3 w-3" /> {msg.replaceRange ? 'Replace selection' : 'Insert into editor'}
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>

                    {aiSelection && (
                        <div className="flex items-center gap-1.5 px-3 pt-2 pb-0.5">
                            <span className="inline-flex items-center gap-1.5 rounded-md border border-violet-500/30 bg-violet-500/10 px-2 py-1 text-[10px] text-violet-300">
                                <TextSelect className="h-3 w-3" />
                                Working on selection ({aiSelection.text.length} chars)
                                <button
                                    type="button"
                                    onClick={() => setAiSelection(null)}
                                    className="ml-0.5 text-violet-400/70 hover:text-violet-200"
                                    title="Use the whole field instead"
                                >
                                    <X className="h-3 w-3" />
                                </button>
                            </span>
                        </div>
                    )}

                    <div className="flex items-center gap-2 px-3 py-2">
                        <input
                            ref={aiInputRef}
                            type="text"
                            value={aiInput}
                            onChange={(e) => setAiInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAiSend(); } }}
                            placeholder={`Ask about ${fieldContext?.fieldName?.toLowerCase() || 'this field'}...`}
                            disabled={aiStreaming}
                            className="flex-1 bg-slate-900/60 border border-slate-700/50 rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-violet-500/50 transition-colors disabled:opacity-50"
                        />
                        <button
                            type="button"
                            onClick={handleAiSend}
                            disabled={aiStreaming || !aiInput.trim()}
                            className="p-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-30 disabled:hover:bg-violet-600 transition-colors"
                        >
                            {aiStreaming ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                        </button>
                    </div>
                </div>
            )}
            <ChatMarkdownStyles />
        </div>
    );
}

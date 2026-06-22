'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/auth-store';
import { usePathname } from 'next/navigation';
import api from '@/lib/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
    MessageCircle, Send, Loader2,
    Sparkles, Trash2, Minus, Square, ChevronDown, ChevronRight, Brain, Plug,
    Check, X, Wrench, Clock, ShieldCheck,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// Per-call tool execution state rendered inline with the chat
// transcript. ``status`` drives the card UI:
//   - "pending"  : tool_call_pending arrived; for write tools the
//                  card shows Approve/Deny + Always-allow checkbox
//                  and blocks the next message until the user clicks.
//   - "executed" : tool_call_result arrived; collapses to a one-line
//                  "ran X" summary with an expand-for-args toggle.
//   - "denied"   : tool_call_denied arrived; renders a muted line
//                  with the reason (user denied / timed out).
// GHSA-q4x9-5gmc-fxh5 follow-up: see /ai/chat tool-use loop.
interface ToolCall {
    callId: string;
    name: string;
    arguments: Record<string, unknown>;
    requiresApproval: boolean;
    status: 'pending' | 'executed' | 'denied';
    resultPreview?: string;
    deniedReason?: string;
}

interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    thinking?: string;
    isMcp?: boolean;
    toolCalls?: ToolCall[];
}

// ── Parse <think>...</think> from raw streamed text ─────────────────────
function parseThinking(raw: string): { thinking: string; content: string; stillThinking: boolean } {
    const thinkOpen = '<' + 'think>';
    const thinkClose = '</' + 'think>';

    const openIdx = raw.indexOf(thinkOpen);
    const closeIdx = raw.indexOf(thinkClose);

    // No think tags at all
    if (openIdx === -1) {
        return { thinking: '', content: raw, stillThinking: false };
    }

    // Has open tag but no close yet → still thinking
    if (closeIdx === -1) {
        const thinkContent = raw.slice(openIdx + thinkOpen.length);
        const before = raw.slice(0, openIdx).trim();
        return { thinking: thinkContent.trim(), content: before, stillThinking: true };
    }

    // Has both open and close → thinking complete
    const thinkContent = raw.slice(openIdx + thinkOpen.length, closeIdx);
    const after = raw.slice(closeIdx + thinkClose.length).trim();
    const before = raw.slice(0, openIdx).trim();
    const content = [before, after].filter(Boolean).join('\n');
    return { thinking: thinkContent.trim(), content, stillThinking: false };
}

// ── Collapsible Thinking Block ──────────────────────────────────────────
function ThinkingBlock({ content, isLive }: { content: string; isLive?: boolean }) {
    const [expanded, setExpanded] = useState(isLive ?? false);

    if (!content && !isLive) return null;

    return (
        <div className="mb-2">
            <button
                onClick={() => setExpanded(!expanded)}
                className={cn(
                    "flex items-center gap-1.5 text-[11px] font-medium rounded-lg px-2 py-1 transition-colors w-full",
                    isLive
                        ? "text-primary bg-primary/10 border border-primary/20"
                        : "text-slate-500 hover:text-slate-400 hover:bg-slate-800/50"
                )}
            >
                {isLive ? (
                    <>
                        <Brain className="h-3 w-3 animate-pulse" />
                        <span className="animate-pulse">Thinking</span>
                        <span className="inline-flex gap-0.5 ml-0.5">
                            <span className="w-1 h-1 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
                            <span className="w-1 h-1 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
                            <span className="w-1 h-1 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
                        </span>
                    </>
                ) : (
                    <>
                        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                        <Brain className="h-3 w-3 opacity-50" />
                        <span>Show thinking</span>
                    </>
                )}
            </button>
            {(expanded || isLive) && content && (
                <div className={cn(
                    "mt-1.5 px-2.5 py-2 rounded-lg text-[11px] leading-relaxed whitespace-pre-wrap break-words border-l-2 max-h-[200px] overflow-y-auto",
                    isLive
                        ? "bg-primary/5 border-primary/30 text-primary/70"
                        : "bg-slate-800/30 border-slate-700/50 text-slate-400"
                )}>
                    {content}
                </div>
            )}
        </div>
    );
}

// ── Markdown message renderer ───────────────────────────────────────────
function MessageContent({ text }: { text: string }) {
    if (!text) return null;
    return (
        <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
                h1: ({ children }) => <h1 className="text-base font-bold text-white mt-2 mb-1">{children}</h1>,
                h2: ({ children }) => <h2 className="text-sm font-bold text-white mt-2 mb-1">{children}</h2>,
                h3: ({ children }) => <h3 className="text-[13px] font-semibold text-white mt-1.5 mb-0.5">{children}</h3>,
                p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="list-disc pl-4 mb-1.5 space-y-0.5">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-4 mb-1.5 space-y-0.5">{children}</ol>,
                li: ({ children }) => <li className="text-[13px]">{children}</li>,
                strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
                em: ({ children }) => <em className="italic text-slate-300">{children}</em>,
                code: ({ className, children, ...props }) => {
                    const isInline = !className;
                    if (isInline) {
                        return <code className="bg-slate-800 text-primary px-1 py-0.5 rounded text-[12px] font-mono">{children}</code>;
                    }
                    return (
                        <pre className="bg-slate-900 border border-slate-700/50 rounded-lg p-2.5 my-1.5 overflow-x-auto">
                            <code className="text-[11px] font-mono text-slate-300 leading-relaxed">{children}</code>
                        </pre>
                    );
                },
                pre: ({ children }) => <>{children}</>,
                table: ({ children }) => (
                    <div className="overflow-x-auto my-2 rounded-lg border border-slate-700/50">
                        <table className="w-full text-[12px] border-collapse">{children}</table>
                    </div>
                ),
                thead: ({ children }) => <thead className="bg-slate-800/80">{children}</thead>,
                tbody: ({ children }) => <tbody className="divide-y divide-slate-700/40">{children}</tbody>,
                tr: ({ children }) => <tr className="hover:bg-slate-800/40 transition-colors">{children}</tr>,
                th: ({ children }) => <th className="px-2.5 py-1.5 text-left text-[11px] font-semibold text-primary uppercase tracking-wider">{children}</th>,
                td: ({ children }) => <td className="px-2.5 py-1.5 text-slate-300">{children}</td>,
                blockquote: ({ children }) => (
                    <blockquote className="border-l-2 border-primary/40 pl-2.5 my-1.5 text-slate-400 italic">{children}</blockquote>
                ),
                a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:text-primary underline">{children}</a>
                ),
                hr: () => <hr className="border-slate-700/50 my-2" />,
            }}
        >
            {text}
        </ReactMarkdown>
    );
}

// ── Tool Call Card ─────────────────────────────────────────────────────
// Claude-Code-style inline card. Read tools render in the executed
// state immediately (collapsed one-liner). Write tools render in the
// pending state with Approve / Deny buttons + the per-session
// "Always allow this tool" checkbox, and block the chat input until
// the user clicks. Auto-approve from the parent's allow-list happens
// before render; by the time the card mounts in approved mode the
// approval POST has already been fired.
function ToolCallCard({
    call,
    onDecision,
    alwaysAllow,
    setAlwaysAllow,
}: {
    call: ToolCall;
    onDecision: (decision: 'approve' | 'deny') => void;
    alwaysAllow: boolean;
    setAlwaysAllow: (v: boolean) => void;
}) {
    const [expanded, setExpanded] = useState(call.status === 'pending');
    const argJson = useMemo(() => {
        try { return JSON.stringify(call.arguments, null, 2); } catch { return '{}'; }
    }, [call.arguments]);

    const isPending = call.status === 'pending';
    const isExecuted = call.status === 'executed';
    const isDenied = call.status === 'denied';

    return (
        <div
            className={cn(
                "my-2 rounded-lg border text-[12px] transition-colors",
                isPending && call.requiresApproval && "border-amber-500/40 bg-amber-500/5",
                isPending && !call.requiresApproval && "border-slate-700/50 bg-slate-900/40",
                isExecuted && "border-slate-700/40 bg-slate-900/30",
                isDenied && "border-red-500/30 bg-red-500/5",
            )}
        >
            {/* Header — always visible */}
            <button
                type="button"
                onClick={() => setExpanded(e => !e)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left"
            >
                {isPending && call.requiresApproval ? (
                    <ShieldCheck className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                ) : isExecuted ? (
                    <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                ) : isDenied ? (
                    <X className="h-3.5 w-3.5 text-red-400 shrink-0" />
                ) : (
                    <Wrench className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                )}
                <span className="font-mono text-slate-200">{call.name}</span>
                {isPending && call.requiresApproval && (
                    <span className="ml-1 text-[10px] text-amber-400 uppercase tracking-wider font-semibold">
                        Awaiting approval
                    </span>
                )}
                {isExecuted && (
                    <span className="ml-1 text-[10px] text-emerald-400/70 uppercase tracking-wider">Done</span>
                )}
                {isDenied && (
                    <span className="ml-1 text-[10px] text-red-400/80 uppercase tracking-wider">
                        {call.deniedReason?.includes('timed out') ? 'Timed out' : 'Denied'}
                    </span>
                )}
                {expanded ? (
                    <ChevronDown className="h-3 w-3 text-slate-500 ml-auto" />
                ) : (
                    <ChevronRight className="h-3 w-3 text-slate-500 ml-auto" />
                )}
            </button>

            {expanded && (
                <div className="px-3 pb-3 space-y-2 border-t border-slate-700/40">
                    {/* Arguments — raw JSON, monospace, as Claude Code does */}
                    <div className="pt-2">
                        <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
                            Arguments
                        </p>
                        <pre className="bg-slate-950/60 border border-slate-800/60 rounded p-2 text-[11px] font-mono text-slate-300 leading-relaxed overflow-x-auto whitespace-pre-wrap">
                            {argJson}
                        </pre>
                    </div>

                    {/* Result preview (executed) */}
                    {isExecuted && call.resultPreview && (
                        <div>
                            <p className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
                                Result preview
                            </p>
                            <pre className="bg-slate-950/60 border border-slate-800/60 rounded p-2 text-[11px] font-mono text-slate-400 leading-relaxed overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto">
                                {call.resultPreview}
                            </pre>
                        </div>
                    )}

                    {/* Denial reason */}
                    {isDenied && call.deniedReason && (
                        <p className="text-[11px] text-red-400/80 italic">{call.deniedReason}</p>
                    )}

                    {/* Approval controls (pending write tools only) */}
                    {isPending && call.requiresApproval && (
                        <div className="space-y-2 pt-1">
                            <label className="flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={alwaysAllow}
                                    onChange={(e) => setAlwaysAllow(e.target.checked)}
                                    className="accent-amber-500"
                                />
                                <span>Always allow <code className="bg-slate-800 px-1 rounded">{call.name}</code> this session</span>
                            </label>
                            <div className="flex gap-2">
                                <button
                                    type="button"
                                    onClick={() => onDecision('approve')}
                                    className="flex-1 px-3 py-1.5 rounded-md bg-amber-500 hover:bg-amber-400 text-white text-[12px] font-semibold flex items-center justify-center gap-1.5"
                                >
                                    <Check className="h-3.5 w-3.5" /> Approve
                                </button>
                                <button
                                    type="button"
                                    onClick={() => onDecision('deny')}
                                    className="flex-1 px-3 py-1.5 rounded-md bg-slate-700 hover:bg-slate-600 text-slate-200 text-[12px] font-semibold flex items-center justify-center gap-1.5"
                                >
                                    <X className="h-3.5 w-3.5" /> Deny
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export function AiChatbot() {
    const pathname = usePathname();
    const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
    const isPublicRoute = pathname === '/login' || pathname === '/register';

    const { data: aiStatus } = useQuery<{
        enabled: boolean;
        model: string;
        chatbot_enabled: boolean;
        mcp_enabled: boolean;
        mcp_url: string;
    }>({
        queryKey: ['ai', 'status'],
        queryFn: async () => {
            const resp = await api.get('/ai/settings/status');
            return resp.data;
        },
        staleTime: 60_000,
        retry: false,
        enabled: isAuthenticated && !isPublicRoute,
    });

    // MCP health check — proxied through backend to avoid CORS/network issues
    const { data: mcpHealth } = useQuery<{ status: string }>({
        queryKey: ['mcp', 'health'],
        queryFn: async () => {
            const resp = await api.get('/ai/mcp/health');
            return resp.data;
        },
        staleTime: 30_000,
        refetchInterval: 30_000,
        retry: false,
        enabled: isAuthenticated && !isPublicRoute && !!aiStatus?.mcp_enabled,
    });

    const mcpConnected = mcpHealth?.status === 'healthy';

    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [streaming, setStreaming] = useState(false);
    const [isThinking, setIsThinking] = useState(false);
    const [expanded, setExpanded] = useState(false);
    // Per-session "always allow" allow-list for write tools. Scoped
    // to the component instance — lost on page reload (deliberate;
    // safer default than localStorage persistence). Keyed by tool
    // name so a user who's approved `update_finding` once doesn't
    // get re-prompted for every subsequent update in the same turn.
    const [toolAllowlist, setToolAllowlist] = useState<Set<string>>(new Set());
    const scrollRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isThinking]);

    useEffect(() => {
        if (open) setTimeout(() => inputRef.current?.focus(), 150);
    }, [open]);

    const shouldShow = isAuthenticated && !isPublicRoute && aiStatus?.chatbot_enabled;

    // ── Send message (streaming) ────────────────────────────────────────
    const handleSend = async () => {
        if (!input.trim() || streaming) return;
        const userMsg: ChatMessage = { role: 'user', content: input.trim() };
        const newMessages = [...messages, userMsg];
        setMessages(newMessages);
        setInput('');
        setStreaming(true);
        setIsThinking(false);

        try {
            const token = localStorage.getItem('access_token');
            const resp = await fetch(`${api.defaults.baseURL}/ai/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    messages: newMessages.filter(m => !m.isMcp).map(m => ({
                        role: m.role,
                        content: m.content,
                    })),
                    editor_content: '',
                    field_context: { resourceType: 'chatbot', fieldName: 'general' },
                }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: `Error: ${err.detail || resp.statusText}`,
                }]);
                setStreaming(false);
                return;
            }

            const reader = resp.body?.getReader();
            const decoder = new TextDecoder();
            let rawContent = '';
            let toolCalls: ToolCall[] = [];
            setMessages(prev => [...prev, { role: 'assistant', content: '', thinking: '', toolCalls: [] }]);

            // Helper: push the updated tool-call list into the last
            // assistant message in-place. Used by every tool_call_*
            // event handler below.
            const syncToolCalls = () => {
                setMessages(prev => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === 'assistant') {
                        updated[updated.length - 1] = { ...last, toolCalls: [...toolCalls] };
                    }
                    return updated;
                });
            };

            if (reader) {
                // SSE format from the backend: ``event: <name>\ndata: <json>\n\n``.
                // The previous parser only handled bare data: lines (no event:
                // discriminator). New shape pairs an event line with a data
                // line; we buffer the most recent event name and apply it
                // when the matching data line arrives.
                let buffer = '';
                let currentEvent = 'chunk'; // default if backend omits event:
                while (true) {
                    const { done, value: chunk } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(chunk, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            currentEvent = line.slice(7).trim();
                            continue;
                        }
                        if (!line.startsWith('data: ')) continue;
                        const data = line.slice(6).trim();
                        if (!data || data === '[DONE]') continue;
                        let parsed: any;
                        try { parsed = JSON.parse(data); } catch { continue; }

                        if (currentEvent === 'chunk') {
                            // OpenAI-compat streaming delta (or our own
                            // {"error":...} envelope on upstream failure).
                            if (parsed.error) {
                                rawContent += `\nError: ${parsed.error}`;
                            } else {
                                const delta = parsed.choices?.[0]?.delta?.content || '';
                                rawContent += delta;
                            }
                            const { thinking, content, stillThinking } = parseThinking(rawContent);
                            setIsThinking(stillThinking);
                            setMessages(prev => {
                                const updated = [...prev];
                                const last = updated[updated.length - 1];
                                if (last && last.role === 'assistant') {
                                    updated[updated.length - 1] = {
                                        ...last,
                                        content,
                                        thinking: thinking || undefined,
                                    };
                                }
                                return updated;
                            });
                        } else if (currentEvent === 'tool_call_pending') {
                            const newCall: ToolCall = {
                                callId: parsed.call_id,
                                name: parsed.name,
                                arguments: parsed.arguments || {},
                                requiresApproval: !!parsed.requires_approval,
                                status: 'pending',
                            };
                            toolCalls = [...toolCalls, newCall];
                            syncToolCalls();
                            // Auto-approve if the user has previously
                            // ticked "always allow" for this tool name
                            // this session. Fire-and-forget POST; the
                            // backend's BLPOP wakes up immediately.
                            if (newCall.requiresApproval && toolAllowlist.has(newCall.name)) {
                                api.post(`/ai/chat/tool-approval/${newCall.callId}`, { decision: 'approve' })
                                    .catch(() => { /* will surface as denied via timeout */ });
                            }
                        } else if (currentEvent === 'tool_call_result') {
                            toolCalls = toolCalls.map(c =>
                                c.callId === parsed.call_id
                                    ? { ...c, status: 'executed', resultPreview: parsed.result_preview }
                                    : c
                            );
                            syncToolCalls();
                        } else if (currentEvent === 'tool_call_denied') {
                            toolCalls = toolCalls.map(c =>
                                c.callId === parsed.call_id
                                    ? { ...c, status: 'denied', deniedReason: parsed.reason }
                                    : c
                            );
                            syncToolCalls();
                        }
                        // event === 'done' is a no-op; the while loop exits
                        // on reader done anyway.
                    }
                }
            }
        } catch (err: any) {
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: `Error: ${err.message}`,
            }]);
        }
        setStreaming(false);
        setIsThinking(false);
    };



    if (!shouldShow) return null;

    return (
        <>
            {/* Floating chat button */}
            {!open && (
                <button
                    onClick={() => setOpen(true)}
                    className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-primary to-primary/70 text-white shadow-lg shadow-primary/40 hover:shadow-primary/60 hover:scale-105 transition-all duration-200 flex items-center justify-center group"
                >
                    <MessageCircle className="h-6 w-6 group-hover:scale-110 transition-transform" />
                    <span className="absolute -top-1 -right-1 w-3 h-3 bg-emerald-400 rounded-full border-2 border-slate-950 animate-pulse" />
                </button>
            )}

            {/* Chat panel */}
            {open && (
                <div className={cn(
                    "fixed bottom-6 right-6 z-50 bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl shadow-black/50 flex flex-col overflow-hidden transition-all duration-300 ease-in-out animate-in slide-in-from-bottom-4 fade-in",
                    expanded ? "w-[700px] h-[800px]" : "w-[420px] h-[580px]"
                )}>
                    {/* Header */}
                    <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-900/80">
                        <div className="flex items-center gap-2">
                            <div className="p-1.5 rounded-lg bg-primary/15">
                                <Sparkles className="h-4 w-4 text-primary" />
                            </div>
                            <div>
                                <h3 className="text-sm font-semibold text-white">RedWire AI</h3>
                                <div className="flex items-center gap-1.5">
                                    <p className="text-[10px] text-slate-500">
                                        {aiStatus?.model || 'AI Assistant'}
                                    </p>
                                    {aiStatus?.mcp_enabled && (
                                        <span className={cn(
                                            "inline-flex items-center gap-1 text-[9px] font-medium px-1.5 py-0.5 rounded-full",
                                            mcpConnected
                                                ? "text-emerald-400 bg-emerald-500/10 border border-emerald-500/20"
                                                : "text-red-400 bg-red-500/10 border border-red-500/20"
                                        )}>
                                            <Plug className="h-2.5 w-2.5" />
                                            {mcpConnected ? 'MCP' : 'MCP Offline'}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-1">
                            {messages.length > 0 && (
                                <button
                                    onClick={() => setMessages([])}
                                    className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
                                    title="Clear chat"
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                </button>
                            )}
                            <button
                                onClick={() => setOpen(false)}
                                className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
                                title="Minimize"
                            >
                                <Minus className="h-3.5 w-3.5" />
                            </button>
                            <button
                                onClick={() => setExpanded(!expanded)}
                                className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
                                title={expanded ? 'Compact' : 'Expand'}
                            >
                                <Square className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    </div>

                    {/* Messages */}
                    <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
                        {messages.length === 0 && (
                            <div className="flex flex-col items-center justify-center h-full text-center gap-3">
                                <div className="p-3 rounded-2xl bg-primary/10 border border-primary/15">
                                    <Sparkles className="h-8 w-8 text-primary" />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-slate-300">How can I help?</p>
                                    <p className="text-xs text-slate-500 mt-1 max-w-[250px]">
                                        Ask about cybersecurity, get help with findings, or query engagement data.
                                    </p>
                                </div>
                            </div>
                        )}
                        {messages.map((msg, i) => {
                            const isLastMsg = i === messages.length - 1;
                            const isStreamingThis = streaming && isLastMsg && msg.role === 'assistant';
                            const isThinkingThis = isStreamingThis && isThinking;

                            return (
                                <div
                                    key={i}
                                    className={cn(
                                        'text-sm rounded-xl px-3.5 py-2.5 max-w-[90%]',
                                        msg.role === 'user'
                                            ? 'bg-primary/20 text-primary-foreground border border-primary/20 ml-auto'
                                            : 'bg-slate-800/60 text-slate-200 border border-slate-700/40',
                                        msg.isMcp && msg.role === 'user' && 'bg-cyan-500/10 text-cyan-200 border-cyan-500/20',
                                        msg.isMcp && msg.role === 'assistant' && 'bg-cyan-900/20 border-cyan-700/30',
                                    )}
                                >
                                    {/* Thinking section */}
                                    {msg.role === 'assistant' && (msg.thinking || isThinkingThis) && (
                                        <ThinkingBlock
                                            content={msg.thinking || ''}
                                            isLive={isThinkingThis}
                                        />
                                    )}

                                    {/* Inline tool call cards (Claude-Code-style) — rendered
                                        above the message content so the user sees what the
                                        assistant did before reading its summary. */}
                                    {msg.role === 'assistant' && msg.toolCalls && msg.toolCalls.length > 0 && (
                                        <div className="mb-1">
                                            {msg.toolCalls.map((tc) => (
                                                <ToolCallCard
                                                    key={tc.callId}
                                                    call={tc}
                                                    alwaysAllow={toolAllowlist.has(tc.name)}
                                                    setAlwaysAllow={(v) => {
                                                        setToolAllowlist(prev => {
                                                            const next = new Set(prev);
                                                            if (v) next.add(tc.name); else next.delete(tc.name);
                                                            return next;
                                                        });
                                                    }}
                                                    onDecision={async (decision) => {
                                                        try {
                                                            await api.post(`/ai/chat/tool-approval/${tc.callId}`, { decision });
                                                        } catch (e) {
                                                            // Surface via toast-style inline message
                                                            console.error('Failed to record tool approval', e);
                                                        }
                                                    }}
                                                />
                                            ))}
                                        </div>
                                    )}

                                    {/* Message content */}
                                    <div className="text-[13px] leading-relaxed chatbot-prose">
                                        {msg.content ? (
                                            <MessageContent text={msg.content} />
                                        ) : (
                                            isStreamingThis && !isThinkingThis && !msg.content ? (
                                                /* Still waiting for first content token after thinking */
                                                <span className="inline-flex gap-1 py-1">
                                                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
                                                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '200ms' }} />
                                                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '400ms' }} />
                                                </span>
                                            ) : null
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* Input area */}
                    <div className="border-t border-slate-800 bg-slate-900/50">
                        <div className="flex items-center gap-2 px-3 py-3">
                            <input
                                ref={inputRef}
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                                placeholder="Ask anything..."
                                disabled={streaming}
                                className="flex-1 bg-slate-800/60 border border-slate-700/50 rounded-xl px-3.5 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-primary/50 transition-colors disabled:opacity-50"
                            />
                            <button
                                onClick={handleSend}
                                disabled={streaming || !input.trim()}
                                className="p-2 rounded-xl bg-primary hover:bg-primary/90 text-white disabled:opacity-30 disabled:hover:bg-primary transition-colors shrink-0"
                            >
                                {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}

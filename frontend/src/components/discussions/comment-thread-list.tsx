'use client';

import { useEffect, useState } from 'react';
import { cn, parseUTCDate } from '@/lib/utils';
import {
    useComments,
    useCreateComment,
    useResolveThread,
    type Thread,
} from '@/lib/hooks/use-discussions';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { UserAvatar } from '@/components/ui/user-avatar';
import {
    MessageSquare, Check, CheckCircle2, CornerDownRight, Loader2, ChevronRight, Quote as QuoteIcon,
} from 'lucide-react';

function ago(iso: string): string {
    const then = parseUTCDate(iso).getTime();
    const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (s < 60) return 'just now';
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h`;
    return `${Math.floor(h / 24)}d`;
}

interface CommentThreadProps {
    thread: Thread;
    active?: boolean;
    orphaned?: boolean;
    /** Show the quoted text the thread is anchored to. */
    showQuote?: boolean;
    onActivate?: (threadId: string) => void;
}

/** One anchored thread: quote snippet, its comments, a reply box, and resolve. */
export function CommentThread({ thread, active, orphaned, showQuote = true, onActivate }: CommentThreadProps) {
    const { data: comments = [] } = useComments(thread.id);
    const createComment = useCreateComment();
    const resolveThread = useResolveThread();
    const [reply, setReply] = useState('');
    const [open, setOpen] = useState(false);

    // Clicking the highlight (or a rail item) activates this thread — expand it
    // so the comment is immediately readable.
    useEffect(() => { if (active) setOpen(true); }, [active]);

    const submit = async () => {
        const body = reply.trim();
        if (!body || createComment.isPending) return;
        await createComment.mutateAsync({ thread_id: thread.id, content: body });
        setReply('');
    };

    return (
        <div
            data-thread-item={thread.id}
            className={cn(
                'rounded-lg border bg-slate-950/40 transition-colors',
                active ? 'border-amber-500/60 ring-1 ring-amber-500/30' : 'border-slate-800/60 hover:border-slate-700',
                thread.is_resolved && 'opacity-70',
            )}
        >
            <button
                type="button"
                onClick={() => { setOpen((o) => !o); onActivate?.(thread.id); }}
                className="w-full text-left p-2.5 flex items-center gap-2"
            >
                <ChevronRight className={cn('h-3.5 w-3.5 text-slate-500 shrink-0 transition-transform', open && 'rotate-90')} />
                <span className="min-w-0 flex-1 flex items-center gap-1 text-[11px]">
                    {showQuote && thread.anchor?.quote ? (
                        <>
                            <QuoteIcon className="h-3 w-3 shrink-0 text-amber-500/70" />
                            <span className="truncate italic text-amber-300/90">{thread.anchor.quote}</span>
                        </>
                    ) : (
                        <span className="truncate font-medium text-slate-300">{thread.title}</span>
                    )}
                </span>
                <span className="flex items-center gap-1.5 shrink-0 text-[11px] text-slate-400">
                    <MessageSquare className="h-3 w-3 text-slate-500" />
                    <span className="tabular-nums">{thread.comment_count}</span>
                    {orphaned && <span className="text-[10px] font-semibold text-orange-400/90 uppercase tracking-wide">Outdated</span>}
                    {thread.is_resolved && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" aria-label="Resolved" />}
                </span>
            </button>

            {open && (
                <div className="px-2.5 pb-2.5 space-y-2">
                    <div className="space-y-1.5">
                        {comments.map((c) => (
                            <div key={c.id} className="rounded-md bg-slate-900/50 border border-slate-800/50 p-2">
                                <div className="flex items-center justify-between gap-2 mb-0.5">
                                    <span className="flex items-center gap-1.5 min-w-0">
                                        <UserAvatar
                                            userId={c.created_by}
                                            username={c.author_name}
                                            user={c.author_profile_photo ? { id: c.created_by, full_name: c.author_name, profile_photo: c.author_profile_photo } as any : undefined}
                                            className="h-4 w-4 text-[8px]"
                                        />
                                        <span className="text-[11px] font-semibold text-slate-300 truncate">{c.author_name || 'Unknown'}</span>
                                    </span>
                                    <span className="text-[10px] text-slate-500 tabular-nums shrink-0">{ago(c.created_at)}</span>
                                </div>
                                <p className="text-[11px] text-slate-400 whitespace-pre-wrap break-words leading-snug">{c.content}</p>
                            </div>
                        ))}
                    </div>
                    <div className="flex items-start gap-1.5">
                        <Textarea
                            value={reply}
                            onChange={(e) => setReply(e.target.value)}
                            placeholder="Reply…"
                            rows={1}
                            className="text-xs bg-slate-950/60 border-slate-800 resize-none min-h-0 py-1.5"
                            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submit(); } }}
                        />
                        <Button size="icon" className="h-7 w-7 shrink-0 bg-primary hover:bg-primary/90" onClick={submit} disabled={createComment.isPending || !reply.trim()}>
                            {createComment.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CornerDownRight className="h-3.5 w-3.5" />}
                        </Button>
                    </div>
                    <div className="flex justify-end">
                        <Button
                            size="sm"
                            variant="ghost"
                            className={cn('h-6 gap-1 text-[10px]', thread.is_resolved ? 'text-slate-400 hover:text-white' : 'text-emerald-400 hover:text-emerald-300')}
                            onClick={() => resolveThread.mutate(thread.id)}
                            disabled={resolveThread.isPending}
                        >
                            <Check className="h-3 w-3" /> {thread.is_resolved ? 'Reopen' : 'Resolve'}
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}

interface CommentThreadListProps {
    threads: Thread[];
    activeId?: string | null;
    orphanedIds?: Set<string>;
    showQuote?: boolean;
    onActivate?: (threadId: string) => void;
    emptyText?: string;
}

/** A list of anchored threads with an "Outdated" group for orphaned ones. */
export function CommentThreadList({ threads, activeId, orphanedIds, showQuote = true, onActivate, emptyText = 'No comments yet.' }: CommentThreadListProps) {
    if (threads.length === 0) {
        return <p className="text-[11px] text-slate-600 italic px-1 py-2">{emptyText}</p>;
    }
    const live = threads.filter((t) => !orphanedIds?.has(t.id));
    const orphaned = threads.filter((t) => orphanedIds?.has(t.id));
    return (
        <div className="space-y-1.5">
            {live.map((t) => (
                <CommentThread key={t.id} thread={t} active={t.id === activeId} showQuote={showQuote} onActivate={onActivate} />
            ))}
            {orphaned.length > 0 && (
                <div className="pt-1.5 space-y-1.5">
                    <p className="text-[10px] font-bold text-orange-400/80 uppercase tracking-widest px-1">Outdated — anchored text changed</p>
                    {orphaned.map((t) => (
                        <CommentThread key={t.id} thread={t} active={t.id === activeId} orphaned showQuote={showQuote} onActivate={onActivate} />
                    ))}
                </div>
            )}
        </div>
    );
}

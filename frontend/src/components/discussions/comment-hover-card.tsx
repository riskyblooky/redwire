'use client';

import { useComments, type Thread } from '@/lib/hooks/use-discussions';
import { MessageSquare } from 'lucide-react';

/**
 * Small popover shown when hovering a comment highlight in the editor: the first
 * comment plus a count. Positioned at the highlight's bounding rect (viewport
 * coords). Clicking opens the thread in the rail via `onOpen`.
 */
export function CommentHoverCard({ thread, rect, onOpen }: { thread: Thread; rect: DOMRect; onOpen: () => void }) {
    const { data: comments = [] } = useComments(thread.id);
    const first = comments[0];
    return (
        <div
            className="fixed z-50 w-64 rounded-lg border border-slate-700 bg-slate-900 shadow-xl p-2.5 text-left cursor-pointer"
            style={{ left: Math.min(rect.left, window.innerWidth - 268), top: rect.bottom + 6 }}
            onClick={onOpen}
        >
            {thread.anchor?.quote && (
                <p className="text-[10px] italic text-amber-300/80 line-clamp-1 mb-1">“{thread.anchor.quote}”</p>
            )}
            {first ? (
                <>
                    <div className="flex items-center justify-between gap-2 mb-0.5">
                        <span className="text-[11px] font-semibold text-slate-300 truncate">{first.author_name || 'Unknown'}</span>
                    </div>
                    <p className="text-[11px] text-slate-400 line-clamp-3 leading-snug">{first.content}</p>
                </>
            ) : (
                <p className="text-[11px] text-slate-500 italic">No comments</p>
            )}
            <div className="flex items-center gap-1 mt-1.5 text-[10px] text-slate-500">
                <MessageSquare className="h-3 w-3" />
                <span className="tabular-nums">{thread.comment_count}</span>
                <span className="ml-auto text-primary">Open →</span>
            </div>
        </div>
    );
}

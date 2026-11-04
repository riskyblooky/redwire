'use client';

import { useEffect, useRef, useState } from 'react';
import { ChevronRight, MessageSquare } from 'lucide-react';
import type { Thread } from '@/lib/hooks/use-discussions';
import { cn } from '@/lib/utils';
import ThreadCard from '@/components/discussions/thread-card';
import NewThreadDialog from '@/components/discussions/new-thread-dialog';

interface ReportSectionThreadsProps {
    engagementId: string;
    sectionId: string;
    /** This section's threads (the tab fetches all report-section threads once). */
    threads: Thread[];
    currentUserId?: string;
    isAdmin?: boolean;
    users?: any[];
    /** Open on mount and scroll into view (deep link to this section). */
    focus?: boolean;
    targetCommentId?: string | null;
    targetThreadId?: string | null;
}

/**
 * Collapsible review-thread list under a report builder section. Collapsed by
 * default; highlight (anchored) comments also show in the editor's rail.
 */
export function ReportSectionThreads({
    engagementId, sectionId, threads, currentUserId, isAdmin, users, focus, targetCommentId, targetThreadId,
}: ReportSectionThreadsProps) {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!focus) return;
        setOpen(true);
        const t = setTimeout(() => rootRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 300);
        return () => clearTimeout(t);
    }, [focus]);

    const openCount = threads.filter((t) => !t.is_resolved).length;

    return (
        <div ref={rootRef} className="rounded-lg border border-slate-800 bg-slate-900/40">
            <div className="flex items-center gap-2 px-3 py-2">
                <button
                    type="button"
                    onClick={() => setOpen((v) => !v)}
                    className="flex flex-1 items-center gap-2 text-left"
                    aria-expanded={open}
                >
                    <ChevronRight className={cn('h-4 w-4 shrink-0 text-slate-400 transition-transform', open && 'rotate-90')} />
                    <MessageSquare className="h-4 w-4 shrink-0 text-primary" />
                    <span className="text-sm font-medium text-slate-200">Review threads</span>
                    <span className="text-xs text-slate-500">
                        {threads.length === 0 ? 'none yet' : `${threads.length} · ${openCount} open`}
                    </span>
                </button>
                <NewThreadDialog engagementId={engagementId} resourceType="report_section" resourceId={sectionId} />
            </div>
            {open && (
                <div className="space-y-3 border-t border-slate-800/60 p-3">
                    {threads.length === 0 ? (
                        <p className="py-4 text-center text-xs text-slate-500">
                            No threads yet. Start one, or select text in the editor to comment on it.
                        </p>
                    ) : (
                        threads.map((thread) => (
                            <ThreadCard
                                key={thread.id}
                                thread={thread}
                                currentUserId={currentUserId}
                                isAdmin={isAdmin}
                                users={users}
                                targetCommentId={targetCommentId}
                                targetThreadId={targetThreadId}
                            />
                        ))
                    )}
                </div>
            )}
        </div>
    );
}

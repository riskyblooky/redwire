'use client';

import { useState, useMemo, useEffect, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useThreads, ResourceType } from '@/lib/hooks/use-discussions';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, MessageSquare, ChevronRight, Eye, EyeOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import ThreadCard from './thread-card';
import NewThreadDialog from './new-thread-dialog';

interface DiscussionSectionProps {
    engagementId: string;
    resourceType: ResourceType;
    resourceId: string;
    currentUserId?: string;
    isAdmin?: boolean;
    users?: any[];
    title?: string;
    description?: string;
}

export default function DiscussionSection({
    engagementId,
    resourceType,
    resourceId,
    currentUserId,
    isAdmin,
    users = [],
    title = 'Discussions',
    description,
}: DiscussionSectionProps) {
    const queryClient = useQueryClient();
    const [isCollapsed, setIsCollapsed] = useState(false);
    // Anchored (peer-review highlight) threads are hidden by default to keep this
    // section focused on general discussion; a toggle reveals them.
    const [showAnchored, setShowAnchored] = useState(false);
    const hasInitialized = useRef(false);
    const threadsParams = useMemo(() => ({
        engagement_id: engagementId,
        resource_type: resourceType,
        resource_id: resourceId,
    }), [engagementId, resourceType, resourceId]);

    const { data: threads = [], isLoading } = useThreads(threadsParams);

    // Listen for real-time discussion updates via WS
    useCollaboration({
        resourceType: 'engagement',
        resourceId: engagementId,
        enabled: !!engagementId,
        onMessage: (data) => {
            if (data.type === 'discussion_update') {
                queryClient.invalidateQueries({ queryKey: ['threads'] });
                queryClient.invalidateQueries({ queryKey: ['comments'] });
            }
        },
    });

    // Deep-link target comment (?commentId=) — from a mention notification or
    // a comment link. Keep the section open so the thread can auto-expand.
    const searchParams = useSearchParams();
    const targetCommentId = searchParams?.get('commentId') || null;
    const targetThreadId = searchParams?.get('threadId') || null;
    const hasDeepLink = !!(targetCommentId || targetThreadId);

    // Auto-collapse if there are no threads after initial load (unless we're
    // deep-linking to a specific comment/thread, in which case stay open).
    useEffect(() => {
        if (!isLoading && !hasInitialized.current) {
            hasInitialized.current = true;
            if (threads.length === 0 && !hasDeepLink) {
                setIsCollapsed(true);
            }
        }
    }, [isLoading, threads.length, hasDeepLink]);

    // If a deep-link arrives after mount, make sure the section is expanded and
    // anchored threads are revealed (the target may be one of them).
    useEffect(() => {
        if (hasDeepLink) { setIsCollapsed(false); setShowAnchored(true); }
    }, [hasDeepLink]);

    const anchoredCount = useMemo(() => threads.filter((t) => t.anchor).length, [threads]);
    const visibleThreads = useMemo(
        () => (showAnchored ? threads : threads.filter((t) => !t.anchor)),
        [threads, showAnchored],
    );
    const totalComments = threads.reduce((sum, thread) => sum + (thread.comment_count || 0), 0);

    const friendlyName: Record<string, string> = {
        finding_remediation: 'finding remediation',
        cleanup_artifact: 'cleanup',
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
            <CardHeader>
                <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                        <button
                            type="button"
                            onClick={() => setIsCollapsed(!isCollapsed)}
                            className="flex items-center gap-2 mb-2 text-left w-full"
                            aria-expanded={!isCollapsed}
                        >
                            <ChevronRight className={cn('h-4 w-4 text-slate-400 shrink-0 transition-transform', !isCollapsed && 'rotate-90')} />
                            <MessageSquare className="h-5 w-5 text-primary shrink-0" />
                            <CardTitle className="text-white">{title}</CardTitle>
                        </button>
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                            <Badge variant="outline" className="bg-purple-500/10 text-purple-400 border-purple-500/20 text-xs">
                                {threads.length} {threads.length === 1 ? 'thread' : 'threads'}
                            </Badge>
                            {totalComments > 0 && (
                                <span className="text-xs text-slate-500">
                                    {totalComments} {totalComments === 1 ? 'comment' : 'comments'}
                                </span>
                            )}
                            {anchoredCount > 0 && (
                                <button
                                    type="button"
                                    onClick={() => setShowAnchored((v) => !v)}
                                    className={cn(
                                        'flex items-center gap-1 text-xs font-medium transition-colors',
                                        showAnchored ? 'text-amber-400 hover:text-amber-300' : 'text-slate-500 hover:text-slate-300',
                                    )}
                                    title={showAnchored ? 'Hide highlighted-text comments' : 'Show highlighted-text comments'}
                                >
                                    {showAnchored ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                                    {showAnchored ? 'Hide' : 'Show'} {anchoredCount} highlight{anchoredCount === 1 ? '' : 's'}
                                </button>
                            )}
                        </div>
                        <CardDescription>
                            {description ?? `Collaborate with your team on this ${friendlyName[resourceType] || resourceType}`}
                        </CardDescription>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                        <NewThreadDialog
                            engagementId={engagementId}
                            resourceType={resourceType}
                            resourceId={resourceId}
                        />
                    </div>
                </div>
            </CardHeader>

            {!isCollapsed && (
                <CardContent>
                    {isLoading ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="h-6 w-6 animate-spin text-primary" />
                        </div>
                    ) : visibleThreads.length > 0 ? (
                        <div className="space-y-3">
                            {visibleThreads.map((thread) => (
                                <ThreadCard
                                    key={thread.id}
                                    thread={thread}
                                    currentUserId={currentUserId}
                                    isAdmin={isAdmin}
                                    users={users}
                                    targetCommentId={targetCommentId}
                                    targetThreadId={targetThreadId}
                                />
                            ))}
                        </div>
                    ) : anchoredCount > 0 ? (
                        <button
                            type="button"
                            onClick={() => setShowAnchored(true)}
                            className="w-full text-center py-8 text-sm text-slate-500 bg-slate-800/20 rounded-lg border border-dashed border-slate-700 hover:text-amber-300 hover:border-amber-500/30 transition-colors"
                        >
                            {anchoredCount} highlighted-text {anchoredCount === 1 ? 'comment' : 'comments'} hidden — show
                        </button>
                    ) : (
                        <div className="text-center py-12 text-slate-500 bg-slate-800/20 rounded-lg border border-dashed border-slate-700">
                            <div className="flex flex-col items-center gap-3">
                                <MessageSquare className="h-12 w-12 opacity-20" />
                                <div>
                                    <p className="text-sm font-medium mb-1">No discussions yet</p>
                                    <p className="text-xs text-slate-600">
                                        Start a thread to collaborate with your team
                                    </p>
                                </div>
                                <NewThreadDialog
                                    engagementId={engagementId}
                                    resourceType={resourceType}
                                    resourceId={resourceId}
                                />
                            </div>
                        </div>
                    )}
                </CardContent>
            )}
        </Card>
    );
}

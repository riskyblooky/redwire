'use client';

import { useState, useEffect } from 'react';
import { Thread } from '@/lib/hooks/use-discussions';
import { useComments, useUpdateThread, useDeleteThread } from '@/lib/hooks/use-discussions';
import { useCanDelete } from '@/lib/hooks/use-permissions';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ChevronDown, ChevronUp, CheckCircle2, MessageSquare, Loader2, Trash2 } from 'lucide-react';
import CommentItem from './comment-item';
import NewCommentForm from './new-comment-form';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';

interface ThreadCardProps {
    thread: Thread;
    currentUserId?: string;
    isAdmin?: boolean;
    users?: any[];
    /** Deep-link target comment id (?commentId=). If it lives in this thread,
     *  auto-expand and let CommentItem scroll/flash it. */
    targetCommentId?: string | null;
}

export default function ThreadCard({ thread, currentUserId, isAdmin, users, targetCommentId }: ThreadCardProps) {
    const [isExpanded, setIsExpanded] = useState(false);
    const { data: comments = [], isLoading } = useComments(thread.id);

    // Auto-expand once when the deep-linked comment is in this thread.
    const containsTarget = !!targetCommentId && comments.some((c: any) => c.id === targetCommentId);
    useEffect(() => {
        if (containsTarget) setIsExpanded(true);
    }, [containsTarget]);
    const updateThread = useUpdateThread();
    const deleteThread = useDeleteThread();
    const canDelete = useCanDelete(thread.engagement_id, 'discussion', thread.created_by);
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const handleToggleResolved = async () => {
        await updateThread.mutateAsync({
            id: thread.id,
            is_resolved: !thread.is_resolved,
        });
    };

    const handleDelete = async () => {
        const confirmed = await confirm({
            title: 'Delete Thread',
            description: `Delete thread "${thread.title}" and all its comments?`,
        });
        if (!confirmed) return;
        await deleteThread.mutateAsync(thread.id);
    };


    return (
        <>
            <div className="border border-slate-800 rounded-lg bg-slate-900/30 overflow-hidden">
                {/* Thread Header */}
                <div
                    className="p-4 cursor-pointer hover:bg-slate-800/30 transition-colors"
                    onClick={() => setIsExpanded(!isExpanded)}
                >
                    <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                                <h4 className="text-base font-medium text-white truncate">
                                    {thread.title}
                                </h4>
                                {thread.is_resolved ? (
                                    <Badge className="bg-green-500/10 text-green-400 border-green-500/20 text-xs">
                                        <CheckCircle2 className="h-3 w-3 mr-1" />
                                        Resolved
                                    </Badge>
                                ) : (
                                    <Badge variant="outline" className="text-slate-400 border-slate-700 text-xs">
                                        Open
                                    </Badge>
                                )}
                            </div>
                            <div className="flex items-center gap-3 text-xs text-slate-500">
                                <span className="flex items-center gap-1">
                                    <MessageSquare className="h-3 w-3" />
                                    {thread.comment_count || 0} {thread.comment_count === 1 ? 'comment' : 'comments'}
                                </span>
                            </div>
                        </div>

                        <div className="flex items-center gap-2">
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleToggleResolved();
                                }}
                                disabled={updateThread.isPending}
                                className={`text-xs h-7 ${thread.is_resolved
                                    ? 'text-slate-400 hover:text-white'
                                    : 'text-green-400 hover:text-green-300'
                                    }`}
                            >
                                {thread.is_resolved ? 'Reopen' : 'Resolve'}
                            </Button>
                            {canDelete && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        handleDelete();
                                    }}
                                    disabled={deleteThread.isPending}
                                    className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            )}
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-slate-400"
                            >
                                {isExpanded ? (
                                    <ChevronUp className="h-4 w-4" />
                                ) : (
                                    <ChevronDown className="h-4 w-4" />
                                )}
                            </Button>
                        </div>
                    </div>
                </div>

                {/* Thread Content (Comments) */}
                {isExpanded && (
                    <div className="border-t border-slate-800">
                        <div className="p-4 space-y-3 bg-slate-950/30">
                            {isLoading ? (
                                <div className="flex items-center justify-center py-8">
                                    <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
                                </div>
                            ) : comments.length > 0 ? (
                                <div className="space-y-2">
                                    {comments.map((comment) => (
                                        <CommentItem
                                            key={comment.id}
                                            comment={comment}
                                            engagementId={thread.engagement_id}
                                            currentUserId={currentUserId}
                                            isAdmin={isAdmin}
                                            users={users}
                                            highlight={comment.id === targetCommentId}
                                        />
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-6 text-sm text-slate-500">
                                    No comments yet. Be the first to comment!
                                </div>
                            )}

                            {/* New Comment Form */}
                            <div className="pt-3 border-t border-slate-800/50">
                                <NewCommentForm threadId={thread.id} />
                            </div>
                        </div>
                    </div>
                )}
            </div>
            <ConfirmDialog />
        </>
    );
}

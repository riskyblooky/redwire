'use client';

import { useEffect, useRef, useState } from 'react';
import { Comment } from '@/lib/hooks/use-discussions';
import { Button } from '@/components/ui/button';
import { CheckCircle, Trash2 } from 'lucide-react';
import { useResolveComment, useDeleteComment } from '@/lib/hooks/use-discussions';
import { useCanDelete } from '@/lib/hooks/use-permissions';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { UserAvatar } from '@/components/ui/user-avatar';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { toast } from 'sonner';

interface CommentItemProps {
    comment: Comment;
    engagementId: string;
    currentUserId?: string;
    isAdmin?: boolean;
    users?: any[];
    /** When true (deep-linked via ?commentId=), scroll to and flash this comment. */
    highlight?: boolean;
}

export default function CommentItem({ comment, engagementId, currentUserId, isAdmin, users, highlight }: CommentItemProps) {
    const resolveComment = useResolveComment();
    const deleteComment = useDeleteComment();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const rootRef = useRef<HTMLDivElement>(null);
    const [flash, setFlash] = useState(false);
    useEffect(() => {
        if (!highlight) return;
        // Let the thread finish expanding, then scroll into view and flash.
        const t = setTimeout(() => {
            rootRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setFlash(true);
        }, 150);
        const off = setTimeout(() => setFlash(false), 3200);
        return () => { clearTimeout(t); clearTimeout(off); };
    }, [highlight]);

    const handleResolve = async () => {
        if (comment.is_resolvable && !comment.is_resolved) {
            await resolveComment.mutateAsync(comment.id);
        }
    };

    const handleDelete = async () => {
        const confirmed = await confirm({
            title: 'Delete Comment',
            description: 'Are you sure you want to delete this comment?',
        });
        if (!confirmed) return;

        try {
            await deleteComment.mutateAsync({ id: comment.id, thread_id: comment.thread_id });
        } catch (error: any) {
            console.error('Failed to delete comment:', error);
            toast.error(getErrorMessage(error, 'Failed to delete comment'));
        }
    };

    const canDelete = useCanDelete(engagementId, 'discussion', comment.created_by);
    const canResolve = comment.is_resolvable && !comment.is_resolved;

    const user = users?.find((u: any) => u.id === comment.created_by) || {
        id: comment.created_by,
        username: comment.author_name || 'Unknown',
        profile_photo: (comment as any).author_profile_photo || null,
    };

    return (
        <>
            <div ref={rootRef} id={`comment-${comment.id}`} className="group relative scroll-mt-24">
                <div className={`flex gap-3 p-3 rounded-lg transition-colors ${flash ? 'bg-indigo-500/15 ring-2 ring-indigo-500/60' : 'bg-slate-800/30 hover:bg-slate-800/50'}`}>
                    {/* Avatar */}
                    <UserAvatar
                        user={user}
                        className="shrink-0"
                    />

                    <div className="flex-1 min-w-0">
                        {/* Header */}
                        <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-medium text-white">
                                {comment.author_name || 'Unknown User'}
                            </span>
                            <span className="text-xs text-slate-500">
                                {formatDistanceToNow(parseUTCDate(comment.created_at), { addSuffix: true })}
                            </span>
                            {comment.is_resolvable && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                    Review
                                </span>
                            )}
                            {comment.is_resolved && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 border border-green-500/20 flex items-center gap-1">
                                    <CheckCircle className="h-3 w-3" />
                                    Resolved by {comment.resolver_name}
                                </span>
                            )}
                        </div>

                        {/* Content — render as Markdown */}
                        <div className="text-sm text-slate-300 [&_.wmde-markdown]:!text-[0.8125rem] [&_.wmde-markdown]:!leading-relaxed">
                            <MarkdownPreview value={comment.content || ''} />
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="shrink-0 flex items-start gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        {canResolve && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={handleResolve}
                                disabled={resolveComment.isPending}
                                className="h-7 w-7 p-0 text-green-400 hover:text-green-300 hover:bg-green-500/10"
                            >
                                <CheckCircle className="h-4 w-4" />
                            </Button>
                        )}
                        {canDelete && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={handleDelete}
                                disabled={deleteComment.isPending}
                                className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                            >
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        )}
                    </div>
                </div>
            </div>
            <ConfirmDialog />
        </>
    );
}

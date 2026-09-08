'use client';

import { useState } from 'react';
import {
    useFindingReviews,
    useSubmitFindingReview,
    useDeleteMyFindingReview,
    type ReviewStatus,
} from '@/lib/hooks/use-finding-reviews';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { getErrorMessage } from '@/components/ui/confirm-dialog';
import {
    CheckCircle2,
    MessageSquareWarning,
    ShieldCheck,
    Loader2,
    Trash2,
    UserRound,
} from 'lucide-react';

function timeAgo(iso: string): string {
    const then = new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime();
    const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (s < 60) return 'just now';
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
}

export function FindingPeerReview({ findingId }: { findingId: string }) {
    const { data, isLoading } = useFindingReviews(findingId);
    const submit = useSubmitFindingReview(findingId);
    const remove = useDeleteMyFindingReview(findingId);

    const [pending, setPending] = useState<ReviewStatus | null>(null);

    if (isLoading || !data) {
        return (
            <div className="space-y-3">
                <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Peer Review</h4>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…
                </div>
            </div>
        );
    }

    const { reviews, my_review, approvals, changes_requested, required, min_approvals, satisfied, is_author } = data;

    const doSubmit = async (status: ReviewStatus) => {
        setPending(status);
        try {
            await submit.mutateAsync({ status });
            toast.success(status === 'APPROVED' ? 'Finding approved' : 'Changes requested');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to submit review'));
        } finally {
            setPending(null);
        }
    };

    const withdraw = async () => {
        try {
            await remove.mutateAsync();
            toast.success('Review withdrawn');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to withdraw review'));
        }
    };

    const pct = required && min_approvals > 0 ? Math.min(100, Math.round((approvals / min_approvals) * 100)) : 0;

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Peer Review</h4>
                {required ? (
                    <span
                        className={cn(
                            'text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded border',
                            satisfied
                                ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
                                : 'text-amber-400 border-amber-500/30 bg-amber-500/10'
                        )}
                    >
                        {approvals}/{min_approvals} approvals
                    </span>
                ) : (
                    <span className="text-[10px] font-semibold text-slate-500">optional</span>
                )}
            </div>

            {required && (
                <Progress
                    value={pct}
                    className={cn('h-1.5 bg-slate-800', satisfied && '[&>div]:bg-emerald-500')}
                />
            )}

            {required && !satisfied && (
                <p className="text-[11px] text-amber-400/80 leading-snug">
                    Needs {min_approvals - approvals} more approval{min_approvals - approvals === 1 ? '' : 's'} before it can be marked Verified.
                </p>
            )}
            {required && satisfied && (
                <p className="text-[11px] text-emerald-400/80 leading-snug flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 shrink-0" /> Approval threshold met.
                </p>
            )}
            {changes_requested > 0 && (
                <p className="text-[11px] text-orange-400/80 leading-snug">
                    {changes_requested} reviewer{changes_requested === 1 ? '' : 's'} requested changes.
                </p>
            )}

            {/* Reviewer controls */}
            {is_author ? (
                <p className="text-[11px] text-slate-500 italic leading-snug">
                    You authored this finding, so you can&apos;t review it. Another operator must approve it.
                </p>
            ) : (
                <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/50 p-2.5">
                    {my_review && (
                        <div className="flex items-center justify-between">
                            <span className="text-[11px] text-slate-400 flex items-center gap-1.5">
                                Your verdict:
                                {my_review.status === 'APPROVED' ? (
                                    <span className="text-emerald-400 font-semibold flex items-center gap-1">
                                        <CheckCircle2 className="h-3 w-3" /> Approved
                                    </span>
                                ) : (
                                    <span className="text-orange-400 font-semibold flex items-center gap-1">
                                        <MessageSquareWarning className="h-3 w-3" /> Changes requested
                                    </span>
                                )}
                            </span>
                            <button
                                onClick={withdraw}
                                disabled={remove.isPending}
                                className="text-[10px] text-slate-500 hover:text-red-400 flex items-center gap-1"
                            >
                                <Trash2 className="h-3 w-3" /> Withdraw
                            </button>
                        </div>
                    )}
                    <div className="flex gap-2">
                        <Button
                            size="sm"
                            onClick={() => doSubmit('APPROVED')}
                            disabled={submit.isPending}
                            className="flex-1 h-8 gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs"
                        >
                            {pending === 'APPROVED' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                            Approve
                        </Button>
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() => doSubmit('CHANGES_REQUESTED')}
                            disabled={submit.isPending}
                            className="flex-1 h-8 gap-1.5 border-orange-500/30 text-orange-400 hover:bg-orange-500/10 text-xs"
                        >
                            {pending === 'CHANGES_REQUESTED' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MessageSquareWarning className="h-3.5 w-3.5" />}
                            Changes
                        </Button>
                    </div>
                </div>
            )}

            {/* Review list */}
            {reviews.length > 0 && (
                <div className="space-y-1.5 pt-1">
                    {reviews.map((r) => (
                        <div key={r.id} className="rounded-md border border-slate-800/70 bg-slate-950/30 p-2">
                            <div className="flex items-center justify-between gap-2">
                                <span className="text-[11px] font-medium text-slate-300 truncate flex items-center gap-1.5">
                                    <UserRound className="h-3 w-3 text-slate-500 shrink-0" />
                                    {r.reviewer_full_name || r.reviewer_username || 'Unknown'}
                                </span>
                                <span className="flex items-center gap-1.5 shrink-0">
                                    {r.status === 'APPROVED' ? (
                                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                                    ) : (
                                        <MessageSquareWarning className="h-3.5 w-3.5 text-orange-400" />
                                    )}
                                    <span className="text-[10px] text-slate-500 tabular-nums">{timeAgo(r.updated_at)}</span>
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
            {reviews.length === 0 && !is_author && (
                <p className="text-[11px] text-slate-600">No reviews yet.</p>
            )}
        </div>
    );
}

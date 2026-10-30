'use client';

import { AlertTriangle } from 'lucide-react';
import { useScoreModelPolicyIssue } from '@/lib/hooks/use-scoring';
import { cn } from '@/lib/utils';

type Finding = Parameters<typeof useScoreModelPolicyIssue>[0];

/** Text explaining a finding scored under a model its engagement no longer allows. */
export function scoreModelPolicyMessage(issue: { model: string; allowed: string[] }): string {
    return `Scored with ${issue.model}, which this engagement doesn't allow `
        + `(allowed: ${issue.allowed.join(', ') || 'none'}). Rescore to switch models.`;
}

/** Amber "model not allowed" pill; renders nothing when the finding's model is allowed. */
export function ScoreModelPolicyBadge({ finding, className }: { finding: Finding; className?: string }) {
    const issue = useScoreModelPolicyIssue(finding);
    if (!issue) return null;
    return (
        <span
            title={scoreModelPolicyMessage(issue)}
            className={cn(
                'inline-flex items-center gap-1 rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-400',
                className,
            )}
        >
            <AlertTriangle className="h-3 w-3" />
            Model not allowed
        </span>
    );
}

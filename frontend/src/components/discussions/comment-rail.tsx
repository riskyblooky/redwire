'use client';

import { useMemo } from 'react';
import { useThreads, type ResourceType } from '@/lib/hooks/use-discussions';
import { CommentThread } from './comment-thread-list';
import { useAnchoredComments } from './anchored-comments-context';
import { MessagesSquare } from 'lucide-react';

const FINDING_FIELD_LABELS: Record<string, string> = {
    description: 'Executive Summary',
    impact: 'Potential Impact',
    steps_to_reproduce: 'Steps to Reproduce',
    technical_details: 'Technical Details',
    mitigations: 'Mitigation & Remediation',
    references: 'External References',
};

const TESTCASE_FIELD_LABELS: Record<string, string> = {
    description: 'Description',
    steps: 'Execution Steps',
    expected_result: 'Expected Result',
    notes: 'Notes',
};

/**
 * Page-level list of all anchored peer-review comments on a resource, grouped by
 * field. Clicking a thread opens its field into annotation mode (via the
 * AnchoredComments context) and focuses that thread's highlight.
 */
export function CommentRail({ engagementId, resourceType, resourceId }: { engagementId: string; resourceType: ResourceType; resourceId: string }) {
    const { data: allThreads = [] } = useThreads({ engagement_id: engagementId, resource_type: resourceType, resource_id: resourceId });
    const anchored = useAnchoredComments();
    const labels = resourceType === 'testcase' ? TESTCASE_FIELD_LABELS : FINDING_FIELD_LABELS;

    const groups = useMemo(() => {
        const byField = new Map<string, typeof allThreads>();
        for (const t of allThreads) {
            if (!t.anchor?.field) continue;
            const arr = byField.get(t.anchor.field) || [];
            arr.push(t);
            byField.set(t.anchor.field, arr);
        }
        return Array.from(byField.entries());
    }, [allThreads]);

    const total = groups.reduce((n, [, arr]) => n + arr.length, 0);
    const openCount = groups.reduce((n, [, arr]) => n + arr.filter((t) => !t.is_resolved).length, 0);

    if (total === 0) return null;

    return (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div className="flex items-center gap-2 mb-3">
                <MessagesSquare className="h-4 w-4 text-amber-400" />
                <h3 className="text-sm font-bold text-white">Peer-review comments</h3>
                <span className="text-[11px] text-slate-500">{openCount} open · {total} total</span>
            </div>
            <div className="space-y-4">
                {groups.map(([fieldName, threads]) => (
                    <div key={fieldName}>
                        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5">
                            {labels[fieldName] || fieldName}
                        </div>
                        <div className="space-y-1.5">
                            {threads.map((t) => (
                                <CommentThread
                                    key={t.id}
                                    thread={t}
                                    active={anchored.focusedThreadId === t.id}
                                    showQuote
                                    onActivate={(id) => anchored.openField(fieldName, id)}
                                />
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

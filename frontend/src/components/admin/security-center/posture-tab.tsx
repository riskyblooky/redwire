'use client';

import { Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CheckStatus, useRefreshPosture, useSecurityPosture } from '@/lib/hooks/use-security-center';
import { CheckBadge, Panel, ago } from './shared';

const ORDER: Record<CheckStatus, number> = { fail: 0, warn: 1, info: 2, pass: 3 };
const CATEGORIES = ['Secrets', 'Accounts', 'Identity', 'Platform', 'Configuration'];

export function PostureTab() {
    const { data, isLoading } = useSecurityPosture();
    const refresh = useRefreshPosture();
    if (isLoading || !data) return <div className="flex justify-center p-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;

    const groups = CATEGORIES
        .map((c) => ({ name: c, checks: data.checks.filter((k) => k.category === c).sort((a, b) => ORDER[a.status] - ORDER[b.status]) }))
        .filter((g) => g.checks.length > 0);

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex gap-4 text-sm tabular-nums">
                    <span className="text-red-400">{data.tally.fail} failing</span>
                    <span className="text-amber-400">{data.tally.warn} warnings</span>
                    <span className="text-green-400">{data.tally.pass} passing</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    Checked {ago(data.generated_at)}
                    <Button size="sm" variant="outline" className="h-7" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
                        <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${refresh.isPending ? 'animate-spin' : ''}`} /> Re-check
                    </Button>
                </div>
            </div>
            {groups.map((g) => (
                <Panel key={g.name} title={g.name}>
                    <ul className="divide-y divide-border/50">
                        {g.checks.map((c) => (
                            <li key={c.id} className="flex gap-3 py-2.5 first:pt-0 last:pb-0">
                                <div className="pt-0.5"><CheckBadge status={c.status} /></div>
                                <div className="min-w-0">
                                    <div className="text-sm font-medium text-foreground">{c.title}</div>
                                    <div className="text-sm text-muted-foreground">{c.detail}</div>
                                    {c.fix && <div className="mt-0.5 text-xs text-primary/90">{c.fix}</div>}
                                </div>
                            </li>
                        ))}
                    </ul>
                </Panel>
            ))}
        </div>
    );
}

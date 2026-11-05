'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, History, Loader2 } from 'lucide-react';
import api from '@/lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface LogGroup {
    engagement_id: string;
    engagement_name?: string | null;
    deleted_at?: string | null;
    deleted_by?: string | null;
    log_count: number;
    first_at?: string | null;
    last_at?: string | null;
}

interface LogEntry {
    id: string;
    created_at: string;
    username?: string | null;
    action: string;
    resource_type: string;
    resource_id: string;
    resource_name?: string | null;
    details?: string | null;
}

const fmt = (d?: string | null) => (d ? new Date(d + (d.endsWith('Z') ? '' : 'Z')).toLocaleString() : '—');

function GroupRows({ engagementId }: { engagementId: string }) {
    const { data = [], isLoading } = useQuery<LogEntry[]>({
        queryKey: ['admin', 'deleted-engagement-logs', engagementId],
        queryFn: async () => (await api.get(`/admin/deleted-engagement-logs/${engagementId}`, { params: { limit: 1000 } })).data,
        staleTime: 30_000,
    });
    if (isLoading) return <div className="py-4 text-center"><Loader2 className="mx-auto h-4 w-4 animate-spin text-slate-500" /></div>;
    return (
        <div className="max-h-[420px] overflow-auto">
            <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900 text-left text-slate-500">
                    <tr>
                        <th className="px-3 py-2 font-medium">Time</th>
                        <th className="px-3 py-2 font-medium">User</th>
                        <th className="px-3 py-2 font-medium">Action</th>
                        <th className="px-3 py-2 font-medium">Resource</th>
                        <th className="px-3 py-2 font-medium">Details</th>
                    </tr>
                </thead>
                <tbody>
                    {data.map((e) => (
                        <tr key={e.id} className="border-t border-slate-800/60 align-top text-slate-300">
                            <td className="whitespace-nowrap px-3 py-1.5 text-slate-400">{fmt(e.created_at)}</td>
                            <td className="px-3 py-1.5">{e.username || '—'}</td>
                            <td className="px-3 py-1.5 font-mono">{e.action}</td>
                            <td className="px-3 py-1.5">
                                <span className="text-slate-500">{e.resource_type}</span>{' '}
                                {e.resource_name || <span className="font-mono text-slate-500">{e.resource_id.slice(0, 8)}</span>}
                            </td>
                            <td className="max-w-md break-words px-3 py-1.5 text-slate-400">{e.details || ''}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

/** Audit trail of deleted engagements — activity rows kept after deletion. */
export function DeletedEngagementLogs() {
    const [open, setOpen] = useState<string | null>(null);
    const { data: groups = [], isLoading } = useQuery<LogGroup[]>({
        queryKey: ['admin', 'deleted-engagement-logs'],
        queryFn: async () => (await api.get('/admin/deleted-engagement-logs')).data,
        staleTime: 30_000,
    });

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                    <History className="h-5 w-5 text-slate-300" /> Deleted engagement logs
                </CardTitle>
                <CardDescription>
                    Activity history kept after an engagement is deleted. Engagements deleted before
                    1.6.2 show only their deletion record.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
                {isLoading ? (
                    <div className="py-8 text-center"><Loader2 className="mx-auto h-5 w-5 animate-spin text-slate-500" /></div>
                ) : groups.length === 0 ? (
                    <p className="py-8 text-center text-sm text-slate-500">No deleted engagements.</p>
                ) : groups.map((g) => (
                    <div key={g.engagement_id} className="rounded-lg border border-slate-800">
                        <button
                            type="button"
                            onClick={() => setOpen(open === g.engagement_id ? null : g.engagement_id)}
                            className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-slate-800/40"
                            aria-expanded={open === g.engagement_id}
                        >
                            <ChevronRight className={cn('h-4 w-4 shrink-0 text-slate-500 transition-transform', open === g.engagement_id && 'rotate-90')} />
                            <span className="min-w-0 flex-1 truncate text-sm font-medium text-white">
                                {g.engagement_name || <span className="font-mono text-slate-400">{g.engagement_id}</span>}
                            </span>
                            <span className="hidden text-xs text-slate-500 md:inline">
                                {g.deleted_at ? `Deleted ${fmt(g.deleted_at)}${g.deleted_by ? ` by ${g.deleted_by}` : ''}` : 'Deletion record missing'}
                            </span>
                            <Badge variant="outline" className="shrink-0 border-slate-700 text-[10px] text-slate-400">
                                {g.log_count} {g.log_count === 1 ? 'entry' : 'entries'}
                            </Badge>
                        </button>
                        {open === g.engagement_id && (
                            <div className="border-t border-slate-800"><GroupRows engagementId={g.engagement_id} /></div>
                        )}
                    </div>
                ))}
            </CardContent>
        </Card>
    );
}

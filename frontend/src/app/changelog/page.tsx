'use client';

import { ScrollText, Loader2 } from 'lucide-react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { useChangelog } from '@/lib/hooks/use-changelog';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MarkdownPreview } from '@/components/ui/markdown-editor';

export default function ChangelogPage() {
    const { data, isLoading } = useChangelog();

    return (
        <DashboardLayout>
            <div className="mx-auto max-w-3xl space-y-4 p-6">
                <div>
                    <h1 className="flex items-center gap-3 text-3xl font-bold text-white">
                        <ScrollText className="h-8 w-8 text-primary" /> Changelog
                    </h1>
                    {data?.current_version && (
                        <p className="text-sm text-slate-500">Currently running v{data.current_version}</p>
                    )}
                </div>

                {isLoading ? (
                    <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
                ) : !data || data.entries.length === 0 ? (
                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="py-16 text-center text-slate-500">No release notes yet.</CardContent>
                    </Card>
                ) : (
                    <div className="space-y-3">
                        {data.entries.map((e) => (
                            <Card key={e.version} className="border-slate-800 bg-slate-900/50">
                                <CardContent className="p-4">
                                    <div className="mb-2 flex items-baseline gap-2">
                                        <h2 className="text-lg font-semibold text-white">v{e.version}</h2>
                                        <span className="text-xs text-slate-500">{e.date}</span>
                                        {e.version === data.current_version && (
                                            <Badge className="border-emerald-500/30 bg-emerald-500/15 text-[10px] text-emerald-400">current</Badge>
                                        )}
                                    </div>
                                    <MarkdownPreview value={e.body} />
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}
            </div>
        </DashboardLayout>
    );
}

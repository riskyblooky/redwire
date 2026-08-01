'use client';

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Rss, Table as TableIcon } from 'lucide-react';
import { LogsTab } from './logs-tab';
import { ActivityFeedTab } from './activity-feed-tab';

/**
 * The engagement "Activity" area. Two views over the same activity stream:
 *  - Feed: content-rich, chronological single-pane-of-glass (diffs + posts).
 *  - Log:  the compact audit table (the original Logs view).
 */
export function ActivityTab({ engagementId }: { engagementId: string }) {
    const [sub, setSub] = useState<'feed' | 'log'>('feed');

    return (
        <Tabs value={sub} onValueChange={(v) => setSub(v as 'feed' | 'log')} className="space-y-4">
            <TabsList className="bg-slate-950/40 border border-slate-800/60 p-1 h-auto rounded-lg gap-0.5">
                <TabsTrigger
                    value="feed"
                    className="px-3 h-8 rounded-md text-xs font-semibold border border-transparent data-[state=active]:bg-orange-500/10 data-[state=active]:text-orange-400 data-[state=active]:border-orange-500/30 hover:text-orange-400/80 transition-colors"
                >
                    <Rss className="h-3.5 w-3.5 mr-1.5" />
                    Feed
                </TabsTrigger>
                <TabsTrigger
                    value="log"
                    className="px-3 h-8 rounded-md text-xs font-semibold border border-transparent data-[state=active]:bg-orange-500/10 data-[state=active]:text-orange-400 data-[state=active]:border-orange-500/30 hover:text-orange-400/80 transition-colors"
                >
                    <TableIcon className="h-3.5 w-3.5 mr-1.5" />
                    Log
                </TabsTrigger>
            </TabsList>

            <TabsContent value="feed" className="mt-0 focus-visible:outline-hidden focus-visible:ring-0">
                <ActivityFeedTab engagementId={engagementId} />
            </TabsContent>
            <TabsContent value="log" className="mt-0 focus-visible:outline-hidden focus-visible:ring-0">
                <LogsTab engagementId={engagementId} />
            </TabsContent>
        </Tabs>
    );
}

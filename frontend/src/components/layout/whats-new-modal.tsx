'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles } from 'lucide-react';
import { useUnseenChangelog, useMarkChangelogSeen } from '@/lib/hooks/use-changelog';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { MarkdownPreview } from '@/components/ui/markdown-editor';

/**
 * One-time "What's New" popup. Opens when the user has unseen releases (their
 * last_seen_version is behind the running version), showing every release since
 * — accumulative. Dismissing marks the current version seen, so it won't show
 * again until the next release. Mounted once in DashboardLayout.
 */
export function WhatsNewModal() {
    const { data } = useUnseenChangelog();
    const markSeen = useMarkChangelogSeen();
    const router = useRouter();
    const [open, setOpen] = useState(false);
    const [handled, setHandled] = useState(false);

    useEffect(() => {
        if (data?.has_unseen && !handled) setOpen(true);
    }, [data?.has_unseen, handled]);

    if (!data?.has_unseen) return null;

    const dismiss = () => {
        setOpen(false);
        setHandled(true);
        markSeen.mutate();
    };

    return (
        <Dialog open={open} onOpenChange={(o) => { if (!o) dismiss(); }}>
            <DialogContent className="flex max-h-[80vh] max-w-2xl flex-col overflow-hidden border-slate-700 bg-slate-900">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-white">
                        <Sparkles className="h-5 w-5 text-amber-400" /> What's New
                        <Badge variant="outline" className="ml-1 border-slate-700 bg-slate-800 text-[10px] text-slate-400">
                            v{data.current_version}
                        </Badge>
                    </DialogTitle>
                </DialogHeader>

                <div className="-mr-1 space-y-6 overflow-y-auto pr-1">
                    {data.entries.map((e) => (
                        <div key={e.version}>
                            <div className="mb-1 flex items-baseline gap-2">
                                <h3 className="text-base font-semibold text-white">v{e.version}</h3>
                                <span className="text-xs text-slate-500">{e.date}</span>
                            </div>
                            <MarkdownPreview value={e.body} />
                        </div>
                    ))}
                </div>

                <div className="flex shrink-0 items-center justify-between border-t border-slate-800 pt-3">
                    <Button
                        variant="ghost"
                        className="text-slate-400 hover:text-white"
                        onClick={() => { dismiss(); router.push('/changelog'); }}
                    >
                        View full changelog
                    </Button>
                    <Button className="bg-primary text-white hover:bg-primary/90" onClick={dismiss}>
                        Got it
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

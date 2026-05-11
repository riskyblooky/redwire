'use client';

import { useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Radar, Search, Loader2 } from 'lucide-react';
import { useIntelItems, useLinkIntel, useUnlinkIntel } from '@/lib/hooks/use-intel';
import { useIntelByEntity } from '@/lib/hooks/use-intel';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const typeColors: Record<string, string> = {
    CVE: 'bg-red-500/10 text-red-400 border-red-500/30',
    ADVISORY: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    ARTICLE: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    EXPLOIT: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
    ZINE: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
    OTHER: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
};

interface IntelLinkDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    entityType: 'finding' | 'testcase' | 'note';
    entityId: string;
}

/**
 * Standalone dialog to search and link intel items to a finding, testcase, or note.
 * Used from the engagement detail page action menus and notes tab.
 */
export function IntelLinkDialog({ open, onOpenChange, entityType, entityId }: IntelLinkDialogProps) {
    const [search, setSearch] = useState('');
    const linkIntel = useLinkIntel();
    const { data: linkedItems = [] } = useIntelByEntity(entityType, entityId);
    const linkedIds = new Set(linkedItems.map(i => i.id));

    const { data: itemsData, isLoading } = useIntelItems({
        search: search || undefined,
        limit: 20,
    });
    const items = itemsData?.items ?? [];

    const handleLink = async (itemId: string) => {
        try {
            await linkIntel.mutateAsync({ itemId, entityType, entityId });
            toast.success('Intel linked');
        } catch {
            toast.error('Failed to link intel — may already be linked');
        }
    };

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!v) setSearch(''); onOpenChange(v); }}>
            <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-lg max-h-[80vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Radar className="h-5 w-5 text-cyan-400" />
                        Link Intel Item
                    </DialogTitle>
                    <DialogDescription className="text-slate-400">
                        Search and select an intel item to link.
                    </DialogDescription>
                </DialogHeader>

                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                    <Input
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="Search intel items, CVEs..."
                        className="pl-9 bg-slate-950 border-slate-800 text-white"
                        autoFocus
                    />
                </div>

                <div className="flex-1 overflow-y-auto space-y-1 min-h-0 max-h-[400px]">
                    {isLoading ? (
                        <div className="flex justify-center py-8">
                            <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
                        </div>
                    ) : items.length === 0 ? (
                        <div className="text-center py-8 text-slate-500 text-sm">
                            No intel items found
                        </div>
                    ) : (
                        items.map(item => {
                            const alreadyLinked = linkedIds.has(item.id);
                            return (
                                <button
                                    key={item.id}
                                    disabled={alreadyLinked}
                                    onClick={() => handleLink(item.id)}
                                    className={cn(
                                        'w-full text-left p-3 rounded-lg border transition-colors flex items-center gap-3',
                                        alreadyLinked
                                            ? 'border-cyan-500/30 bg-cyan-500/5 opacity-60 cursor-not-allowed'
                                            : 'border-slate-800 hover:border-cyan-500/30 hover:bg-slate-800/50 cursor-pointer'
                                    )}
                                >
                                    <Radar className="h-4 w-4 text-cyan-400 shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <span className="text-xs font-bold text-white block truncate">{item.title}</span>
                                        <div className="flex items-center gap-2 mt-0.5">
                                            <Badge className={cn('text-[8px] px-1 py-0 h-4 border-none', typeColors[item.item_type] || typeColors.OTHER)}>
                                                {item.item_type}
                                            </Badge>
                                            {item.cve_id && <span className="text-[9px] font-mono text-red-400">{item.cve_id}</span>}
                                            {item.source && <span className="text-[9px] text-slate-500">via {item.source}</span>}
                                        </div>
                                    </div>
                                    {alreadyLinked && (
                                        <Badge className="text-[8px] bg-cyan-500/10 text-cyan-400 border-none">Linked</Badge>
                                    )}
                                </button>
                            );
                        })
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}

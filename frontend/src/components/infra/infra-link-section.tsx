'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Server, Plus, Search, Loader2, Unlink, MapPin, Wifi } from 'lucide-react';
import { useInfraByEntity, useInfraItems, useLinkInfra, useUnlinkInfra, InfraItem } from '@/lib/hooks/use-infra';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const typeColors: Record<string, string> = {
    VPS: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    C2: 'bg-red-500/10 text-red-400 border-red-500/30',
    REDIRECTOR: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    PROXY: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
    PHISHING: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
    JUMPBOX: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    OTHER: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
};

const statusColors: Record<string, string> = {
    ACTIVE: 'bg-emerald-500/10 text-emerald-400',
    DECOMMISSIONED: 'bg-slate-500/10 text-slate-500',
    STANDBY: 'bg-amber-500/10 text-amber-400',
};

interface InfraLinkSectionProps {
    entityType: 'finding' | 'testcase' | 'note';
    entityId: string;
}

export function InfraLinkSection({ entityType, entityId }: InfraLinkSectionProps) {
    const { data: linkedItems = [], isLoading } = useInfraByEntity(entityType, entityId);
    const [pickerOpen, setPickerOpen] = useState(false);
    const [search, setSearch] = useState('');
    const linkInfra = useLinkInfra();
    const unlinkInfra = useUnlinkInfra();

    const handleUnlink = async (itemId: string) => {
        try {
            await unlinkInfra.mutateAsync({ itemId, entityType, entityId });
            toast.success('Infrastructure unlinked');
        } catch {
            toast.error('Failed to unlink infrastructure');
        }
    };

    const handleLink = async (itemId: string) => {
        try {
            await linkInfra.mutateAsync({ itemId, entityType, entityId });
            toast.success('Infrastructure linked');
        } catch {
            toast.error('Failed to link infrastructure — may already be linked');
        }
    };

    return (
        <div>
            <div className="flex items-center justify-between mb-3">
                <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Linked Infrastructure</h4>
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-teal-400 hover:text-teal-300 hover:bg-teal-500/10"
                    onClick={() => { setPickerOpen(true); setSearch(''); }}
                    title="Link Infrastructure"
                >
                    <Plus className="h-3.5 w-3.5" />
                </Button>
            </div>

            {isLoading ? (
                <div className="flex justify-center py-4">
                    <Loader2 className="h-4 w-4 animate-spin text-teal-400" />
                </div>
            ) : linkedItems.length > 0 ? (
                <div className="space-y-2">
                    {linkedItems.map(item => (
                        <div
                            key={item.id}
                            className="group flex items-center gap-2 p-2 bg-slate-950/40 rounded-lg border border-slate-800/60 hover:border-teal-500/30 transition-colors"
                        >
                            <Server className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                            <div className="flex-1 min-w-0">
                                <span className="text-xs font-bold text-white truncate block" title={item.name}>
                                    {item.name}
                                </span>
                                <div className="flex items-center gap-1.5 mt-0.5">
                                    <Badge className={cn('text-[8px] px-1 py-0 h-4 border-none', typeColors[item.infra_type] || typeColors.OTHER)}>
                                        {item.infra_type}
                                    </Badge>
                                    {item.ip_address && (
                                        <span className="text-[9px] font-mono text-slate-500">{item.ip_address}</span>
                                    )}
                                </div>
                            </div>
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                    className="p-1 rounded hover:bg-red-500/10 text-slate-500 hover:text-red-400 transition-colors"
                                    onClick={() => handleUnlink(item.id)}
                                    title="Unlink"
                                >
                                    <Unlink className="h-3 w-3" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="text-[10px] text-slate-500 italic p-3 text-center border border-dashed border-slate-800 rounded-lg">
                    No infrastructure linked
                </div>
            )}

            {/* Picker Dialog */}
            <InfraPickerDialog
                open={pickerOpen}
                onOpenChange={setPickerOpen}
                search={search}
                onSearchChange={setSearch}
                linkedIds={new Set(linkedItems.map(i => i.id))}
                onLink={handleLink}
            />
        </div>
    );
}

function InfraPickerDialog({
    open,
    onOpenChange,
    search,
    onSearchChange,
    linkedIds,
    onLink,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    search: string;
    onSearchChange: (s: string) => void;
    linkedIds: Set<string>;
    onLink: (id: string) => Promise<void>;
}) {
    const { data: itemsData, isLoading } = useInfraItems({
        search: search || undefined,
        limit: 20,
    });
    const items = itemsData?.items ?? [];

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-lg max-h-[80vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Server className="h-5 w-5 text-teal-400" />
                        Link Infrastructure
                    </DialogTitle>
                    <DialogDescription className="text-slate-400">
                        Search and select an infrastructure item to link.
                    </DialogDescription>
                </DialogHeader>

                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                    <Input
                        value={search}
                        onChange={e => onSearchChange(e.target.value)}
                        placeholder="Search by name, IP, hostname..."
                        className="pl-9 bg-slate-950 border-slate-800 text-white"
                        autoFocus
                    />
                </div>

                <div className="flex-1 overflow-y-auto space-y-1 min-h-0 max-h-[400px]">
                    {isLoading ? (
                        <div className="flex justify-center py-8">
                            <Loader2 className="h-6 w-6 animate-spin text-teal-400" />
                        </div>
                    ) : items.length === 0 ? (
                        <div className="text-center py-8 text-slate-500 text-sm">
                            No infrastructure items found
                        </div>
                    ) : (
                        items.map(item => {
                            const alreadyLinked = linkedIds.has(item.id);
                            return (
                                <button
                                    key={item.id}
                                    disabled={alreadyLinked}
                                    onClick={async () => {
                                        await onLink(item.id);
                                    }}
                                    className={cn(
                                        'w-full text-left p-3 rounded-lg border transition-colors flex items-center gap-3',
                                        alreadyLinked
                                            ? 'border-teal-500/30 bg-teal-500/5 opacity-60 cursor-not-allowed'
                                            : 'border-slate-800 hover:border-teal-500/30 hover:bg-slate-800/50 cursor-pointer'
                                    )}
                                >
                                    <Server className="h-4 w-4 text-teal-400 shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <span className="text-xs font-bold text-white block truncate">{item.name}</span>
                                        <div className="flex items-center gap-2 mt-0.5">
                                            <Badge className={cn('text-[8px] px-1 py-0 h-4 border-none', typeColors[item.infra_type] || typeColors.OTHER)}>
                                                {item.infra_type}
                                            </Badge>
                                            {item.ip_address && <span className="text-[9px] font-mono text-slate-500">{item.ip_address}</span>}
                                            {item.point_of_presence && (
                                                <span className="text-[9px] text-slate-500 flex items-center gap-0.5">
                                                    <MapPin className="h-2.5 w-2.5" />
                                                    {item.point_of_presence}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    {alreadyLinked && (
                                        <Badge className="text-[8px] bg-teal-500/10 text-teal-400 border-none">Linked</Badge>
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

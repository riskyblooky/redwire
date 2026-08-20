'use client';

import { useEffect, useMemo, useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
    Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Building2, Check, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { apiErrorMessage } from '@/lib/api';
import { useClients } from '@/lib/hooks/use-clients';
import { useUpdateEngagement } from '@/lib/hooks/use-engagements';

/**
 * Set / change the client an engagement is linked to. The primary control is a
 * searchable list of existing clients — picking one sends its `client_id` and
 * the backend fills `client_name` from that row. A free-text field remains for
 * a client that isn't a record yet (client_id cleared, client_name kept).
 */
export function EngagementClientDialog({
    open, onOpenChange, engagementId, currentClientId, currentClientName,
}: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    engagementId: string;
    currentClientId?: string | null;
    currentClientName?: string | null;
}) {
    const { data: clients = [], isLoading } = useClients(open);
    const updateEngagement = useUpdateEngagement();
    const [selectedId, setSelectedId] = useState('');
    const [newName, setNewName] = useState('');
    const [saving, setSaving] = useState(false);

    // Seed from the engagement's current link each time the dialog opens.
    useEffect(() => {
        if (open) {
            setSelectedId(currentClientId || '');
            setNewName(currentClientId ? '' : (currentClientName || ''));
        }
    }, [open, currentClientId, currentClientName]);

    const canSave = !!selectedId || !!newName.trim();

    const handleSave = async () => {
        if (!canSave) {
            toast.error('Pick a client or enter a client name');
            return;
        }
        setSaving(true);
        try {
            if (selectedId) {
                // Backend populates client_name from the linked client row.
                await updateEngagement.mutateAsync({ id: engagementId, client_id: selectedId } as any);
            } else {
                // Free-text client name, not linked to a client record.
                await updateEngagement.mutateAsync({
                    id: engagementId, client_id: '', client_name: newName.trim(),
                } as any);
            }
            toast.success('Client updated');
            onOpenChange(false);
        } catch (e) {
            toast.error(apiErrorMessage(e, 'Failed to update client'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[480px]">
                <DialogHeader>
                    <DialogTitle className="text-sm font-semibold flex items-center gap-2">
                        <Building2 className="h-4 w-4 text-indigo-400" /> Set Client
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-3">
                    <div>
                        <Label className="text-xs text-slate-400">Choose an existing client</Label>
                        <Command className="mt-1 rounded-md border border-slate-700 bg-slate-800">
                            <CommandInput placeholder="Search clients…" className="text-white" />
                            <CommandList className="max-h-56">
                                {isLoading ? (
                                    <div className="flex justify-center py-4">
                                        <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
                                    </div>
                                ) : (
                                    <>
                                        <CommandEmpty>No clients found.</CommandEmpty>
                                        <CommandGroup>
                                            {clients.map((c: any) => (
                                                <CommandItem
                                                    key={c.id}
                                                    value={c.name}
                                                    onSelect={() => { setSelectedId(c.id); setNewName(''); }}
                                                    className="text-slate-200"
                                                >
                                                    <Check className={cn('mr-2 h-3.5 w-3.5', selectedId === c.id ? 'opacity-100' : 'opacity-0')} />
                                                    <Building2 className="h-3.5 w-3.5 text-indigo-400 mr-1.5 shrink-0" />
                                                    <span className="truncate flex-1">{c.name}</span>
                                                    {c.client_type?.name && (
                                                        <span className="text-[10px] text-slate-500 ml-2 truncate">{c.client_type.name}</span>
                                                    )}
                                                </CommandItem>
                                            ))}
                                        </CommandGroup>
                                    </>
                                )}
                            </CommandList>
                        </Command>
                    </div>

                    <div className="flex items-center gap-2 text-[11px] text-slate-500">
                        <div className="h-px flex-1 bg-slate-800" /> or <div className="h-px flex-1 bg-slate-800" />
                    </div>

                    <div>
                        <Label className="text-xs text-slate-400">Enter a new client name</Label>
                        <Input
                            value={newName}
                            onChange={e => { setNewName(e.target.value); if (e.target.value) setSelectedId(''); }}
                            placeholder="e.g. Acme Corporation"
                            className="bg-slate-800 border-slate-700 mt-1"
                        />
                        <p className="text-[10px] text-slate-600 mt-1">Free-text name, not linked to a client record.</p>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" className="border-slate-700 text-slate-400 hover:text-white" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button className="bg-primary hover:bg-primary/90 text-white" onClick={handleSave} disabled={saving || !canSave}>
                        {saving ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Saving…</> : 'Save'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

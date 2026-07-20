'use client';

import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Building2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import { useUpdateClient, useClientTypes, useClient } from '@/lib/hooks/use-clients';

/** Edit a client's core info from anywhere (e.g. the engagement overview).
 *  Fetches the full client record so a save can't blank out fields the
 *  caller's partial client object didn't carry. */
export function ClientEditDialog({ open, onOpenChange, clientId }: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    clientId: string | null;
}) {
    const updateClient = useUpdateClient();
    const { data: clientTypes = [] } = useClientTypes();
    const { data: client } = useClient(open && clientId ? clientId : '');
    const qc = useQueryClient();

    const [form, setForm] = useState({
        name: '', client_type_id: '', contact_name: '', contact_email: '', description: '', notes: '',
    });
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (open && client) {
            setForm({
                name: client.name || '',
                client_type_id: client.client_type_id || (client as any).client_type?.id || '',
                contact_name: client.contact_name || '',
                contact_email: client.contact_email || '',
                description: client.description || '',
                notes: client.notes || '',
            });
        }
    }, [open, client]);

    const handleSave = async () => {
        if (!clientId) return;
        if (!form.name.trim()) { toast.error('Client name is required'); return; }
        setSaving(true);
        try {
            await updateClient.mutateAsync({
                id: clientId,
                name: form.name.trim(),
                client_type_id: form.client_type_id || undefined,
                contact_name: form.contact_name,
                contact_email: form.contact_email,
                description: form.description,
                notes: form.notes,
            });
            // The engagement overview reads engagement.client, so refresh it too.
            qc.invalidateQueries({ queryKey: ['engagements'] });
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
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[520px]">
                <DialogHeader>
                    <DialogTitle className="text-sm font-semibold flex items-center gap-2">
                        <Building2 className="h-4 w-4 text-indigo-400" /> Edit Client
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    <div>
                        <Label className="text-xs text-slate-400">Name</Label>
                        <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                            className="bg-slate-800 border-slate-700 mt-1" />
                    </div>
                    <div>
                        <Label className="text-xs text-slate-400">Type</Label>
                        <Select value={form.client_type_id} onValueChange={v => setForm(f => ({ ...f, client_type_id: v }))}>
                            <SelectTrigger className="bg-slate-800 border-slate-700 mt-1"><SelectValue placeholder="Select type" /></SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-700">
                                {clientTypes.map((t: any) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label className="text-xs text-slate-400">Contact Name</Label>
                            <Input value={form.contact_name} onChange={e => setForm(f => ({ ...f, contact_name: e.target.value }))}
                                className="bg-slate-800 border-slate-700 mt-1" />
                        </div>
                        <div>
                            <Label className="text-xs text-slate-400">Contact Email</Label>
                            <Input type="email" value={form.contact_email} onChange={e => setForm(f => ({ ...f, contact_email: e.target.value }))}
                                className="bg-slate-800 border-slate-700 mt-1" />
                        </div>
                    </div>
                    <div>
                        <Label className="text-xs text-slate-400">Description</Label>
                        <Textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                            rows={2} className="bg-slate-800 border-slate-700 mt-1 resize-none" />
                    </div>
                    <div>
                        <Label className="text-xs text-slate-400">Notes</Label>
                        <Textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                            rows={2} className="bg-slate-800 border-slate-700 mt-1 resize-none" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" className="border-slate-700 text-slate-400 hover:text-white" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button className="bg-primary hover:bg-primary/90 text-white" onClick={handleSave} disabled={saving}>
                        {saving ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Saving…</> : 'Save'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

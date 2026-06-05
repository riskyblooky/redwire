/**
 * Marking Profiles — classification / portion-marking policy management.
 *
 * Lists all profiles (built-in TLP 2.0 + IC/DoD, plus custom), and lets
 * Admin/Team-Lead create, duplicate, edit, and delete custom profiles.
 * Built-ins are read-only (Duplicate to customize).
 */
'use client';

import { useState } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { toast } from 'sonner';
import { Plus, Copy, Trash2, Pencil, ShieldAlert, Lock } from 'lucide-react';
import {
    useMarkingProfiles, useCreateMarkingProfile, useUpdateMarkingProfile, useDeleteMarkingProfile,
    MarkingProfile, MarkingProfileCreate, MarkingLevel, MarkAnchor, MARK_ANCHORS,
} from '@/lib/hooks/use-marking-profiles';

const SCHEMES = [
    { value: 'TLP_2_0', label: 'TLP 2.0 (header banner, TLP: tokens)' },
    { value: 'IC_DOD', label: 'IC / DoD (top+bottom banner, (S) tokens)' },
    { value: 'CUSTOM', label: 'Custom (rendered IC-style)' },
] as const;

const ENFORCEMENTS = [
    { value: 'OFF', label: 'Off — no checks' },
    { value: 'WARN', label: 'Warn — flag inherited-default portions' },
    { value: 'BLOCK', label: 'Block — refuse if any portion unmarked' },
] as const;

const GRID: MarkAnchor[][] = [
    ['TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT'],
    ['BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'],
];

function AnchorGrid({ label, value, onChange }: { label: string; value: MarkAnchor[]; onChange: (v: MarkAnchor[]) => void }) {
    const toggle = (a: MarkAnchor) => onChange(value.includes(a) ? value.filter(x => x !== a) : [...value, a]);
    const cell = (a: MarkAnchor) => (
        <button
            key={a}
            type="button"
            onClick={() => toggle(a)}
            className={`text-[10px] py-2 rounded border transition-colors ${value.includes(a)
                ? 'bg-red-500/20 border-red-500/50 text-red-300'
                : 'bg-slate-950/50 border-slate-800 text-slate-500 hover:border-slate-600'}`}
        >
            {a.replace('_', ' ')}
        </button>
    );
    return (
        <div className="space-y-2">
            <Label className="text-slate-300 text-sm">{label}</Label>
            <div className="grid grid-cols-3 gap-1">
                {GRID.flat().map(cell)}
            </div>
            <button
                type="button"
                onClick={() => toggle('CAPTION')}
                className={`w-full text-[10px] py-2 rounded border transition-colors ${value.includes('CAPTION')
                    ? 'bg-red-500/20 border-red-500/50 text-red-300'
                    : 'bg-slate-950/50 border-slate-800 text-slate-500 hover:border-slate-600'}`}
            >
                CAPTION
            </button>
        </div>
    );
}

const EMPTY: MarkingProfileCreate = {
    name: '', description: '', scheme: 'IC_DOD', levels: [],
    enforcement: 'WARN', image_mark_anchors: ['CAPTION'], table_mark_anchors: ['CAPTION'],
    inline_portion_marks: false,
    table_per_row_marks: false, stamp_images: false, show_legend: true,
    distribution_statement: '', static_heading_marks: 'LOWEST', is_default: false,
};

export function MarkingProfilesManager() {
    const { user } = useAuthStore();
    const canManage = user?.role === UserRole.ADMIN || user?.role === UserRole.TEAM_LEAD;
    const { data: profiles = [] } = useMarkingProfiles();
    const createMut = useCreateMarkingProfile();
    const updateMut = useUpdateMarkingProfile();
    const deleteMut = useDeleteMarkingProfile();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [editing, setEditing] = useState<MarkingProfile | null>(null);
    const [form, setForm] = useState<MarkingProfileCreate>(EMPTY);
    const [open, setOpen] = useState(false);

    const openNew = (base?: MarkingProfile) => {
        setEditing(base && !base.is_builtin ? base : null);
        setForm(base
            ? { ...base, name: base.is_builtin ? `${base.name} (copy)` : base.name, is_default: false }
            : EMPTY);
        setOpen(true);
    };

    const set = (patch: Partial<MarkingProfileCreate>) => setForm(f => ({ ...f, ...patch }));

    const setLevel = (i: number, patch: Partial<MarkingLevel>) =>
        set({ levels: (form.levels || []).map((l, idx) => idx === i ? { ...l, ...patch } : l) });
    const addLevel = () =>
        set({ levels: [...(form.levels || []), { abbreviation: '', full_name: '', rank: (form.levels?.length || 0) + 1, banner_color: '#1E293B', text_color: '#FFFFFF' }] });
    const removeLevel = (i: number) =>
        set({ levels: (form.levels || []).filter((_, idx) => idx !== i) });

    const save = async () => {
        if (!form.name.trim()) { toast.error('Name is required'); return; }
        try {
            if (editing) {
                await updateMut.mutateAsync({ id: editing.id, ...form });
                toast.success('Marking profile updated');
            } else {
                await createMut.mutateAsync(form);
                toast.success('Marking profile created');
            }
            setOpen(false);
        } catch (e) {
            toast.error(getErrorMessage(e, 'Something went wrong'));
        }
    };

    const onDelete = async (p: MarkingProfile) => {
        const ok = await confirm({
            title: 'Delete marking profile',
            description: `Delete "${p.name}"? Engagements using it will fall back to no marking.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        });
        if (!ok) return;
        try { await deleteMut.mutateAsync(p.id); toast.success('Deleted'); }
        catch (e) { toast.error(getErrorMessage(e, 'Failed to delete')); }
    };

    return (
        <>
            <div className="space-y-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                            <ShieldAlert className="h-6 w-6 text-red-400" /> Marking Profiles
                        </h1>
                        <p className="text-sm text-slate-400 mt-1">Classification ladders, banner idiom, and mark placement for reports.</p>
                    </div>
                    {canManage && (
                        <Button onClick={() => openNew()} className="bg-primary hover:bg-primary/90 text-white">
                            <Plus className="h-4 w-4 mr-1.5" /> New Profile
                        </Button>
                    )}
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                    {profiles.map(p => (
                        <Card key={p.id} className="bg-slate-900/50 border-slate-800">
                            <CardHeader className="pb-3">
                                <CardTitle className="text-white text-base flex items-center gap-2">
                                    {p.name}
                                    {p.is_default && <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">Default</Badge>}
                                    {p.is_builtin && <Badge className="bg-slate-700/50 text-slate-300 border-slate-600"><Lock className="h-3 w-3 mr-1" />Built-in</Badge>}
                                </CardTitle>
                                <p className="text-xs text-slate-500">{p.scheme} · {p.levels.length} levels · {p.enforcement}</p>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="flex flex-wrap gap-1">
                                    {p.levels.map(l => (
                                        <span key={l.abbreviation} className="text-[10px] px-1.5 py-0.5 rounded font-bold"
                                            style={{ backgroundColor: l.banner_color, color: l.text_color }}>
                                            {l.abbreviation}
                                        </span>
                                    ))}
                                </div>
                                <p className="text-xs text-slate-500">
                                    Images: {p.image_mark_anchors.join(', ') || '—'}<br />
                                    Tables: {p.table_mark_anchors.join(', ') || '—'}{p.table_per_row_marks ? ' · per-row' : ''}
                                </p>
                                {canManage && (
                                    <div className="flex gap-2 pt-1">
                                        <Button size="sm" variant="outline" onClick={() => openNew(p)} className="border-slate-700 text-slate-300 h-8">
                                            <Copy className="h-3.5 w-3.5 mr-1" /> Duplicate
                                        </Button>
                                        {!p.is_builtin && (
                                            <>
                                                <Button size="sm" variant="outline" onClick={() => openNew(p)} className="border-slate-700 text-slate-300 h-8">
                                                    <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                                                </Button>
                                                <Button size="sm" variant="outline" onClick={() => onDelete(p)} className="border-red-900/50 text-red-400 h-8">
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </Button>
                                            </>
                                        )}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white max-w-2xl max-h-[88vh] overflow-y-auto">
                    <DialogHeader><DialogTitle>{editing ? 'Edit' : 'New'} Marking Profile</DialogTitle></DialogHeader>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                                <Label className="text-slate-300">Name</Label>
                                <Input value={form.name} onChange={e => set({ name: e.target.value })} className="bg-slate-950/50 border-slate-800" />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-slate-300">Scheme</Label>
                                <Select value={form.scheme} onValueChange={v => set({ scheme: v as any })}>
                                    <SelectTrigger className="bg-slate-950/50 border-slate-800"><SelectValue /></SelectTrigger>
                                    <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                        {SCHEMES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="text-slate-300">Description</Label>
                            <Input value={form.description || ''} onChange={e => set({ description: e.target.value })} className="bg-slate-950/50 border-slate-800" />
                        </div>

                        {/* Levels */}
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <Label className="text-slate-300">Levels (rank low → high sensitivity)</Label>
                                <Button size="sm" variant="outline" onClick={addLevel} className="border-slate-700 text-slate-300 h-7"><Plus className="h-3 w-3 mr-1" />Add</Button>
                            </div>
                            <div className="space-y-2">
                                {(form.levels || []).map((l, i) => (
                                    <div key={i} className="flex items-center gap-2">
                                        <Input value={l.abbreviation} onChange={e => setLevel(i, { abbreviation: e.target.value })} placeholder="abbr" className="bg-slate-950/50 border-slate-800 h-8 w-20" />
                                        <Input value={l.full_name} onChange={e => setLevel(i, { full_name: e.target.value })} placeholder="full name" className="bg-slate-950/50 border-slate-800 h-8 flex-1" />
                                        <Input type="number" value={l.rank} onChange={e => setLevel(i, { rank: parseInt(e.target.value) || 0 })} className="bg-slate-950/50 border-slate-800 h-8 w-16" />
                                        <input type="color" value={l.banner_color} onChange={e => setLevel(i, { banner_color: e.target.value })} className="h-8 w-8 rounded bg-transparent border border-slate-800" title="banner" />
                                        <input type="color" value={l.text_color} onChange={e => setLevel(i, { text_color: e.target.value })} className="h-8 w-8 rounded bg-transparent border border-slate-800" title="text" />
                                        <Button size="sm" variant="ghost" onClick={() => removeLevel(i)} className="h-8 w-8 p-0 text-red-400"><Trash2 className="h-3.5 w-3.5" /></Button>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <AnchorGrid label="Image mark placement" value={form.image_mark_anchors || []} onChange={v => set({ image_mark_anchors: v })} />
                            <AnchorGrid label="Table mark placement" value={form.table_mark_anchors || []} onChange={v => set({ table_mark_anchors: v })} />
                        </div>

                        <div className="space-y-2.5">
                            <div className="flex items-center justify-between">
                                <div>
                                    <Label className="text-slate-300">Inline portion marks</Label>
                                    <p className="text-xs text-slate-500">Off → page banner only (typical for TLP). On → also mark titles, findings, tables, images.</p>
                                </div>
                                <Switch checked={!!form.inline_portion_marks} onCheckedChange={v => set({ inline_portion_marks: v })} />
                            </div>
                            <div className="flex items-center justify-between"><Label className="text-slate-300">Per-row table marks</Label><Switch checked={!!form.table_per_row_marks} onCheckedChange={v => set({ table_per_row_marks: v })} /></div>
                            <div className="flex items-center justify-between"><Label className="text-slate-300">Stamp mark onto image bitmap</Label><Switch checked={!!form.stamp_images} onCheckedChange={v => set({ stamp_images: v })} /></div>
                            <div className="flex items-center justify-between"><Label className="text-slate-300">Show legend on cover</Label><Switch checked={!!form.show_legend} onCheckedChange={v => set({ show_legend: v })} /></div>
                            <div className="flex items-center justify-between"><Label className="text-slate-300">Default profile</Label><Switch checked={!!form.is_default} onCheckedChange={v => set({ is_default: v })} /></div>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="text-slate-300">Static heading marks</Label>
                            <Select value={form.static_heading_marks || 'LOWEST'} onValueChange={v => set({ static_heading_marks: v })}>
                                <SelectTrigger className="bg-slate-950/50 border-slate-800"><SelectValue /></SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                    <SelectItem value="LOWEST">Lowest level (e.g. (U) / TLP:CLEAR)</SelectItem>
                                    <SelectItem value="INHERIT">Engagement default</SelectItem>
                                </SelectContent>
                            </Select>
                            <p className="text-xs text-slate-500">How the TOC, section titles, and other structural headings are marked (unless a section sets its own).</p>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="text-slate-300">Enforcement</Label>
                            <Select value={form.enforcement} onValueChange={v => set({ enforcement: v as any })}>
                                <SelectTrigger className="bg-slate-950/50 border-slate-800"><SelectValue /></SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                    {ENFORCEMENTS.map(e => <SelectItem key={e.value} value={e.value}>{e.label}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-1.5">
                            <Label className="text-slate-300">Distribution statement (IC)</Label>
                            <Textarea value={form.distribution_statement || ''} onChange={e => set({ distribution_statement: e.target.value })} className="bg-slate-950/50 border-slate-800" rows={2} />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setOpen(false)} className="border-slate-700 text-slate-300">Cancel</Button>
                        <Button onClick={save} disabled={createMut.isPending || updateMut.isPending} className="bg-primary hover:bg-primary/90 text-white">Save</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            <ConfirmDialog />
        </>
    );
}

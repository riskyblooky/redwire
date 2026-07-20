'use client';

/**
 * ChainLinksSection — the "attack chain" editor shown on a finding / testcase
 * / vault-item detail sheet.
 *
 * Renders two directed lists: **Caused by** (upstream — things that led to
 * this entity) and **Led to** (downstream — things this entity enabled).
 * Findings and vault items (credentials) are the connective tissue between
 * testcase "buckets"; a testcase→testcase link is intentionally unavailable
 * (that's the testcase parent tree), so the picker hides testcases when the
 * focused entity is itself a testcase.
 */

import { useMemo, useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import type { ChainNodeRef } from '@/lib/hooks/use-chain-links';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
    ArrowDownRight, ArrowUpRight, Bug, Target, Key, Plus, X, Pencil,
    Search, Loader2, Link2, CornerDownRight,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import { useFindings } from '@/lib/hooks/use-findings';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { useVaultItems } from '@/lib/hooks/use-vault';
import {
    useChainLinksFor, useCreateChainLink, useUpdateChainLinkNote, useDeleteChainLink,
    type ChainNodeType, type ChainNeighbor,
} from '@/lib/hooks/use-chain-links';

const NODE_META: Record<ChainNodeType, { icon: React.ElementType; color: string; label: string }> = {
    testcase:   { icon: Target, color: 'text-primary',     label: 'Test Case' },
    finding:    { icon: Bug,    color: 'text-red-400',     label: 'Finding' },
    vault_item: { icon: Key,    color: 'text-yellow-400',  label: 'Vault' },
};

interface ChainLinksSectionProps {
    engagementId: string;
    entityType: ChainNodeType;
    entityId: string;
    entityName: string;
    canEdit?: boolean;
}

export function ChainLinksSection({
    engagementId, entityType, entityId, entityName, canEdit = true,
}: ChainLinksSectionProps) {
    const { data, isLoading } = useChainLinksFor(engagementId, entityType, entityId);
    const deleteLink = useDeleteChainLink(engagementId);
    const createLink = useCreateChainLink(engagementId);

    const [pickerDir, setPickerDir] = useState<'cause' | 'effect' | null>(null);
    const [noteEdit, setNoteEdit] = useState<ChainNeighbor | null>(null);
    const [promoting, setPromoting] = useState<string | null>(null); // `${type}:${id}` in flight

    const upstream = data?.upstream ?? [];
    const downstream = data?.downstream ?? [];
    const candidates = data?.candidates ?? [];

    const handlePromote = async (node: ChainNodeRef, direction: 'cause' | 'effect') => {
        const payload = direction === 'effect'
            ? { source_type: entityType, source_id: entityId, target_type: node.type, target_id: node.id }
            : { source_type: node.type, source_id: node.id, target_type: entityType, target_id: entityId };
        setPromoting(`${node.type}:${node.id}`);
        try {
            await createLink.mutateAsync({ ...payload, note: null });
            toast.success('Added to chain');
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to add to chain'));
        } finally {
            setPromoting(null);
        }
    };

    // Keys already linked in either direction — the picker disables them.
    const existingKeys = useMemo(() => {
        const s = new Set<string>();
        [...upstream, ...downstream].forEach(n => s.add(`${n.node.type}:${n.node.id}`));
        return s;
    }, [upstream, downstream]);

    const handleRemove = async (neighbor: ChainNeighbor) => {
        try {
            await deleteLink.mutateAsync(neighbor.link_id);
            toast.success('Chain link removed');
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to remove link'));
        }
    };

    const renderList = (neighbors: ChainNeighbor[], emptyText: string) => {
        if (neighbors.length === 0) {
            return <p className="text-xs text-slate-600 italic px-1 py-1">{emptyText}</p>;
        }
        return (
            <div className="space-y-1">
                {neighbors.map(n => {
                    const meta = NODE_META[n.node.type] ?? NODE_META.finding;
                    const Icon = meta.icon;
                    const dangling = !n.node.label;
                    return (
                        <div key={n.link_id}
                            className="group flex items-start gap-2 rounded-md border border-slate-800 bg-slate-900/40 px-2.5 py-1.5">
                            <Icon className={cn('h-3.5 w-3.5 mt-0.5 shrink-0', dangling ? 'text-slate-600' : meta.color)} />
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-1.5">
                                    <span className={cn('text-xs font-medium truncate', dangling ? 'text-slate-600 italic' : 'text-slate-200')}>
                                        {dangling ? '(deleted item)' : n.node.label}
                                    </span>
                                    {n.node.sub && !dangling && (
                                        <Badge variant="secondary" className="h-4 px-1 text-[9px] bg-slate-800 text-slate-400 border-slate-700 shrink-0">
                                            {n.node.sub}
                                        </Badge>
                                    )}
                                </div>
                                {n.note && (
                                    <p className="text-[11px] text-slate-500 mt-0.5 flex items-start gap-1">
                                        <CornerDownRight className="h-3 w-3 mt-0.5 shrink-0 text-slate-600" />
                                        <span className="italic">{n.note}</span>
                                    </p>
                                )}
                            </div>
                            {canEdit && (
                                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                                    <button onClick={() => setNoteEdit(n)}
                                        className="text-slate-500 hover:text-slate-300 p-0.5" title="Edit note">
                                        <Pencil className="h-3 w-3" />
                                    </button>
                                    <button onClick={() => handleRemove(n)}
                                        className="text-slate-500 hover:text-red-400 p-0.5" title="Remove link">
                                        <X className="h-3 w-3" />
                                    </button>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        );
    };

    return (
        <div className="space-y-3">
            <div className="flex items-center gap-2">
                <Link2 className="h-4 w-4 text-indigo-400" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Attack Chain</h3>
            </div>

            {isLoading ? (
                <div className="flex items-center gap-2 text-xs text-slate-500 px-1">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading chain…
                </div>
            ) : (
                <div className="space-y-3">
                    {/* Caused by (upstream) */}
                    <div>
                        <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[11px] font-semibold text-slate-500 flex items-center gap-1.5">
                                <ArrowUpRight className="h-3.5 w-3.5 text-amber-400" /> Caused by
                            </span>
                            {canEdit && (
                                <Button size="sm" variant="ghost"
                                    className="h-6 px-1.5 text-[11px] text-slate-400 hover:text-white"
                                    onClick={() => setPickerDir('cause')}>
                                    <Plus className="h-3 w-3 mr-0.5" /> Add cause
                                </Button>
                            )}
                        </div>
                        {renderList(upstream, 'Nothing recorded as leading here yet.')}
                    </div>

                    {/* Led to (downstream) */}
                    <div>
                        <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[11px] font-semibold text-slate-500 flex items-center gap-1.5">
                                <ArrowDownRight className="h-3.5 w-3.5 text-emerald-400" /> Led to
                            </span>
                            {canEdit && (
                                <Button size="sm" variant="ghost"
                                    className="h-6 px-1.5 text-[11px] text-slate-400 hover:text-white"
                                    onClick={() => setPickerDir('effect')}>
                                    <Plus className="h-3 w-3 mr-0.5" /> Add effect
                                </Button>
                            )}
                        </div>
                        {renderList(downstream, 'Nothing recorded as following from this yet.')}
                    </div>

                    {/* Promote-from-links: flat-linked items not yet chained */}
                    {canEdit && candidates.length > 0 && (
                        <div className="pt-1">
                            <p className="text-[11px] font-semibold text-slate-500 mb-1.5 flex items-center gap-1.5">
                                <Link2 className="h-3.5 w-3.5 text-slate-500" /> Linked — not yet chained
                            </p>
                            <div className="space-y-1">
                                {candidates.map(c => {
                                    const meta = NODE_META[c.type] ?? NODE_META.finding;
                                    const Icon = meta.icon;
                                    const busy = promoting === `${c.type}:${c.id}`;
                                    return (
                                        <div key={`${c.type}:${c.id}`}
                                            className="flex items-center gap-2 rounded-md border border-dashed border-slate-800 bg-slate-900/20 px-2.5 py-1.5">
                                            <Icon className={cn('h-3.5 w-3.5 shrink-0', meta.color)} />
                                            <span className="text-xs text-slate-300 truncate flex-1">{c.label}</span>
                                            {c.sub && (
                                                <Badge variant="secondary" className="h-4 px-1 text-[9px] bg-slate-800 text-slate-400 border-slate-700 shrink-0">
                                                    {c.sub}
                                                </Badge>
                                            )}
                                            {busy ? (
                                                <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-500 shrink-0" />
                                            ) : (
                                                <div className="flex items-center gap-1 shrink-0">
                                                    <button onClick={() => handlePromote(c, 'cause')}
                                                        className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-400 hover:bg-amber-500/10 flex items-center gap-0.5"
                                                        title="This item caused the current one">
                                                        <ArrowUpRight className="h-3 w-3" /> cause
                                                    </button>
                                                    <button onClick={() => handlePromote(c, 'effect')}
                                                        className="text-[10px] px-1.5 py-0.5 rounded border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 flex items-center gap-0.5"
                                                        title="The current item led to this one">
                                                        <ArrowDownRight className="h-3 w-3" /> effect
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {pickerDir && (
                <ChainPickerDialog
                    open={!!pickerDir}
                    onOpenChange={(v) => { if (!v) setPickerDir(null); }}
                    engagementId={engagementId}
                    direction={pickerDir}
                    selfType={entityType}
                    selfId={entityId}
                    selfName={entityName}
                    existingKeys={existingKeys}
                />
            )}

            {noteEdit && (
                <ChainNoteDialog
                    open={!!noteEdit}
                    onOpenChange={(v) => { if (!v) setNoteEdit(null); }}
                    engagementId={engagementId}
                    neighbor={noteEdit}
                />
            )}
        </div>
    );
}

// ── Picker: choose an entity to chain in a fixed direction ──
interface ChainPickerDialogProps {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    engagementId: string;
    direction: 'cause' | 'effect';
    selfType: ChainNodeType;
    selfId: string;
    selfName: string;
    existingKeys: Set<string>;
}

function ChainPickerDialog({
    open, onOpenChange, engagementId, direction, selfType, selfId, selfName, existingKeys,
}: ChainPickerDialogProps) {
    const createLink = useCreateChainLink(engagementId);
    const { data: findings = [] } = useFindings({ engagement_id: engagementId });
    const { data: testcases = [] } = useTestCases(engagementId);
    const { data: vaultItems = [] } = useVaultItems(engagementId);

    const [search, setSearch] = useState('');
    const [typeFilter, setTypeFilter] = useState<ChainNodeType | 'all'>('all');
    const [selected, setSelected] = useState<{ type: ChainNodeType; id: string; label: string } | null>(null);
    const [note, setNote] = useState('');
    const [saving, setSaving] = useState(false);

    // Testcase↔testcase is the tree, not a chain — hide testcases when the
    // focused entity is a testcase.
    const excludeTestcases = selfType === 'testcase';

    const options = useMemo(() => {
        const rows: { type: ChainNodeType; id: string; label: string; sub?: string }[] = [];
        findings.forEach(f => rows.push({ type: 'finding', id: f.id, label: f.title, sub: f.severity }));
        if (!excludeTestcases) {
            testcases.forEach(t => rows.push({ type: 'testcase', id: t.id, label: t.title, sub: t.category || undefined }));
        }
        vaultItems.forEach(v => rows.push({ type: 'vault_item', id: v.id, label: v.name, sub: v.item_type }));

        const term = search.toLowerCase();
        return rows.filter(r => {
            if (r.type === selfType && r.id === selfId) return false;        // no self-link
            if (existingKeys.has(`${r.type}:${r.id}`)) return false;         // already linked
            if (typeFilter !== 'all' && r.type !== typeFilter) return false;
            if (term && !r.label.toLowerCase().includes(term)) return false;
            return true;
        });
    }, [findings, testcases, vaultItems, excludeTestcases, search, typeFilter, selfType, selfId, existingKeys]);

    const typeChips: { key: ChainNodeType | 'all'; label: string }[] = [
        { key: 'all', label: 'All' },
        { key: 'finding', label: 'Findings' },
        ...(excludeTestcases ? [] : [{ key: 'testcase' as const, label: 'Test Cases' }]),
        { key: 'vault_item', label: 'Vault' },
    ];

    const handleSubmit = async () => {
        if (!selected) { toast.warning('Pick an item to link'); return; }
        // direction 'effect': this → selected. direction 'cause': selected → this.
        const payload = direction === 'effect'
            ? { source_type: selfType, source_id: selfId, target_type: selected.type, target_id: selected.id }
            : { source_type: selected.type, source_id: selected.id, target_type: selfType, target_id: selfId };
        setSaving(true);
        try {
            await createLink.mutateAsync({ ...payload, note: note.trim() || null });
            toast.success('Chain link added');
            onOpenChange(false);
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to add link'));
        } finally {
            setSaving(false);
        }
    };

    const verb = direction === 'effect' ? 'led to' : 'was caused by';

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[560px] p-0 gap-0 overflow-hidden max-h-[80vh] flex flex-col">
                <DialogHeader className="px-4 pt-4 pb-3 border-b border-slate-800/60">
                    <DialogTitle className="text-sm font-semibold flex items-center gap-2">
                        <Link2 className="h-4 w-4 text-indigo-400" />
                        {direction === 'effect' ? 'Add effect' : 'Add cause'}
                    </DialogTitle>
                    <p className="text-xs text-slate-500 mt-0.5">
                        &ldquo;{selfName}&rdquo; {verb} the selected item.
                    </p>
                </DialogHeader>

                {/* Type chips */}
                <div className="flex gap-1 px-4 pt-3 pb-1 flex-wrap">
                    {typeChips.map(chip => (
                        <button key={chip.key}
                            onClick={() => setTypeFilter(chip.key)}
                            className={cn('px-2 py-0.5 rounded text-[11px] border transition-colors',
                                typeFilter === chip.key
                                    ? 'border-indigo-500/50 bg-indigo-500/10 text-indigo-300'
                                    : 'border-slate-700 text-slate-400 hover:text-slate-200')}>
                            {chip.label}
                        </button>
                    ))}
                </div>

                {/* Search */}
                <div className="px-4 py-2">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                        <Input value={search} onChange={e => setSearch(e.target.value)}
                            placeholder="Search items…"
                            className="h-8 text-xs pl-8 bg-slate-800/50 border-slate-700 focus:border-primary" />
                    </div>
                </div>

                {/* List */}
                <div className="flex-1 overflow-y-auto min-h-0 px-3 space-y-0.5" style={{ maxHeight: '300px' }}>
                    {options.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-10 text-slate-500">
                            <Link2 className="h-7 w-7 mb-2 opacity-30" />
                            <p className="text-xs">{search ? 'No matching items' : 'No linkable items'}</p>
                        </div>
                    ) : options.map(opt => {
                        const meta = NODE_META[opt.type];
                        const Icon = meta.icon;
                        const isSel = selected?.type === opt.type && selected?.id === opt.id;
                        return (
                            <button key={`${opt.type}:${opt.id}`}
                                onClick={() => setSelected({ type: opt.type, id: opt.id, label: opt.label })}
                                className={cn('w-full text-left px-3 py-2 rounded-md flex items-center gap-2.5 transition-colors border',
                                    isSel ? 'border-indigo-500/50 bg-indigo-500/10' : 'border-transparent hover:bg-slate-800/70')}>
                                <Icon className={cn('h-3.5 w-3.5 shrink-0', meta.color)} />
                                <span className={cn('text-sm truncate flex-1', isSel ? 'text-white' : 'text-slate-300')}>{opt.label}</span>
                                {opt.sub && (
                                    <Badge variant="secondary" className="text-[10px] h-4 px-1.5 shrink-0 bg-slate-800 text-slate-400 border-slate-700">
                                        {opt.sub}
                                    </Badge>
                                )}
                            </button>
                        );
                    })}
                </div>

                {/* Note */}
                <div className="px-4 py-2 border-t border-slate-800/60">
                    <label className="text-[11px] text-slate-500 mb-1 block">Note (optional)</label>
                    <textarea value={note} onChange={e => setNote(e.target.value)}
                        placeholder="e.g. used dumped NTLM hash to pass-the-hash into DC01"
                        rows={2}
                        className="w-full bg-slate-800/50 border border-slate-700 rounded-md px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-primary resize-none" />
                </div>

                <DialogFooter className="px-4 py-2 border-t border-slate-800/60">
                    <Button variant="outline" className="border-slate-700 text-slate-400 hover:text-white" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button className="bg-primary hover:bg-primary/90 text-white" onClick={handleSubmit} disabled={saving || !selected}>
                        {saving ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Adding…</> : 'Add to chain'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ── Note editor for an existing chain edge ──
function ChainNoteDialog({ open, onOpenChange, engagementId, neighbor }: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    engagementId: string;
    neighbor: ChainNeighbor;
}) {
    const updateNote = useUpdateChainLinkNote(engagementId);
    const [note, setNote] = useState(neighbor.note ?? '');
    const [saving, setSaving] = useState(false);

    const handleSave = async () => {
        setSaving(true);
        try {
            await updateNote.mutateAsync({ linkId: neighbor.link_id, note: note.trim() || null });
            toast.success('Note updated');
            onOpenChange(false);
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to update note'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[440px]">
                <DialogHeader>
                    <DialogTitle className="text-sm font-semibold flex items-center gap-2">
                        <Pencil className="h-4 w-4 text-indigo-400" /> Chain note
                    </DialogTitle>
                </DialogHeader>
                <textarea autoFocus value={note} onChange={e => setNote(e.target.value)}
                    placeholder="Describe how one led to the other…" rows={4}
                    className="w-full bg-slate-800/50 border border-slate-700 rounded-md px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-primary resize-none" />
                <DialogFooter>
                    <Button variant="outline" className="border-slate-700 text-slate-400 hover:text-white" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button className="bg-primary hover:bg-primary/90 text-white" onClick={handleSave} disabled={saving}>
                        {saving ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Saving…</> : 'Save note'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ── Dialog wrapper: the chain editor for compact surfaces (table rows,
// vault cards) that can't host it inline. ──
export function ChainLinksDialog({
    open, onOpenChange, engagementId, entityType, entityId, entityName, canEdit = true,
}: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    engagementId: string;
    entityType: ChainNodeType;
    entityId: string;
    entityName: string;
    canEdit?: boolean;
}) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[520px] max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="text-sm font-semibold flex items-center gap-2">
                        <Link2 className="h-4 w-4 text-indigo-400" /> Attack Chain — {entityName}
                    </DialogTitle>
                </DialogHeader>
                <ChainLinksSection
                    engagementId={engagementId}
                    entityType={entityType}
                    entityId={entityId}
                    entityName={entityName}
                    canEdit={canEdit}
                />
            </DialogContent>
        </Dialog>
    );
}

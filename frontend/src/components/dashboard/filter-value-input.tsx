'use client';

import { useState, useMemo } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
    Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Check, ChevronsUpDown, Briefcase, User as UserIcon, Building2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { useUsers } from '@/lib/hooks/use-users';
import { useClients } from '@/lib/hooks/use-clients';

// Columns that hold a user id — a query-builder filter on any of these should
// let the author pick a person rather than paste a UUID.
const USER_COLS = new Set([
    'created_by', 'updated_by', 'user_id', 'actor_id', 'owner_user_id',
    'pinned_by', 'changed_by', 'resolved_by', 'cleaned_by', 'granted_by', 'assigned_by',
]);

export type RefKind = 'engagement' | 'user' | 'client' | null;

export function referenceKind(column: string): RefKind {
    if (column === 'engagement_id') return 'engagement';
    if (column === 'client_id') return 'client';
    if (USER_COLS.has(column)) return 'user';
    return null;
}

interface RefItem { id: string; label: string; sub?: string }

function RefCombo({ items, value, onChange, icon: Icon }: {
    items: RefItem[]; value: string; onChange: (v: string) => void; icon: React.ElementType;
}) {
    const [open, setOpen] = useState(false);
    const selected = items.find(i => i.id === value);
    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button variant="outline" role="combobox"
                    className="bg-slate-900 border-slate-700 text-white h-7 text-[11px] flex-1 justify-between font-normal hover:bg-slate-800 hover:text-white min-w-0">
                    <span className="flex items-center gap-1.5 min-w-0">
                        <Icon className="h-3 w-3 shrink-0 text-slate-400" />
                        <span className="truncate">{selected ? selected.label : (value || 'Select…')}</span>
                    </span>
                    <ChevronsUpDown className="h-3 w-3 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[280px] p-0 bg-slate-900 border-slate-700" align="start">
                <Command className="bg-slate-900">
                    <CommandInput placeholder="Search…" className="text-white text-xs" />
                    <CommandList className="max-h-60">
                        <CommandEmpty>No match.</CommandEmpty>
                        <CommandGroup>
                            {items.map(it => (
                                <CommandItem key={it.id} value={`${it.label} ${it.sub ?? ''} ${it.id}`}
                                    onSelect={() => { onChange(it.id); setOpen(false); }}
                                    className="text-slate-200 text-xs">
                                    <Check className={cn('mr-2 h-3.5 w-3.5', value === it.id ? 'opacity-100' : 'opacity-0')} />
                                    <span className="truncate flex-1">{it.label}</span>
                                    {it.sub && <span className="text-[10px] text-slate-500 ml-2 truncate">{it.sub}</span>}
                                </CommandItem>
                            ))}
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
}

function EngagementRef({ value, onChange }: { value: string; onChange: (v: string) => void }) {
    const { data: engagements = [] } = useEngagements();
    const items = useMemo(() => engagements.map(e => ({ id: e.id, label: e.name, sub: e.client_name })), [engagements]);
    return <RefCombo items={items} value={value} onChange={onChange} icon={Briefcase} />;
}
function UserRef({ value, onChange }: { value: string; onChange: (v: string) => void }) {
    const { data: users = [] } = useUsers();
    const items = useMemo(() => users.map((u: any) => ({ id: u.id, label: u.full_name || u.username, sub: `@${u.username}` })), [users]);
    return <RefCombo items={items} value={value} onChange={onChange} icon={UserIcon} />;
}
function ClientRef({ value, onChange }: { value: string; onChange: (v: string) => void }) {
    const { data: clients = [] } = useClients();
    const items = useMemo(() => clients.map((c: any) => ({ id: c.id, label: c.name })), [clients]);
    return <RefCombo items={items} value={value} onChange={onChange} icon={Building2} />;
}

/** Filter value input for the query builder: a searchable entity picker for
 *  reference columns (engagement/user/client id), a plain text field otherwise. */
export function FilterValueInput({ column, value, onChange }: {
    column: string; value: string; onChange: (v: string) => void;
}) {
    const kind = referenceKind(column);
    if (kind === 'engagement') return <EngagementRef value={value} onChange={onChange} />;
    if (kind === 'user') return <UserRef value={value} onChange={onChange} />;
    if (kind === 'client') return <ClientRef value={value} onChange={onChange} />;
    return (
        <Input value={value} placeholder="value"
            onChange={e => onChange(e.target.value)}
            className="bg-slate-900 border-slate-700 text-white h-7 text-[11px] flex-1" />
    );
}

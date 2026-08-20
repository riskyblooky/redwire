'use client';

import { useState } from 'react';
import {
    Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import {
    Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import { Button } from '@/components/ui/button';
import { Building2, Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ClientOption {
    id: string;
    name: string;
    client_type?: { name?: string } | null;
}

/**
 * Inline searchable client picker for engagement forms. Sets the form's
 * client_id + client_name via onSelect; the caller owns persistence. Same
 * cmdk-based search pattern as the engagement switcher and the overview
 * "Set Client" dialog.
 */
export function ClientCombobox({
    clients, value, onSelect, placeholder = 'Select a client', className, id,
}: {
    clients: ClientOption[];
    value: string; // selected client_id
    onSelect: (client: { id: string; name: string }) => void;
    placeholder?: string;
    className?: string;
    id?: string;
}) {
    const [open, setOpen] = useState(false);
    const selected = clients.find(c => c.id === value);

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    id={id}
                    type="button"
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    className={cn(
                        'w-full justify-between bg-slate-800/50 border-slate-700 text-white font-normal hover:bg-slate-800 hover:text-white',
                        className,
                    )}
                >
                    <span className={cn('flex items-center gap-2 min-w-0', !selected && 'text-slate-500')}>
                        <Building2 className="h-4 w-4 shrink-0" />
                        <span className="truncate">{selected?.name ?? placeholder}</span>
                    </span>
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent
                className="w-[--radix-popover-trigger-width] p-0 bg-slate-900 border-slate-700"
                align="start"
            >
                <Command className="bg-slate-900">
                    <CommandInput placeholder="Search clients…" className="text-white" />
                    <CommandList className="max-h-64">
                        <CommandEmpty>No clients found.</CommandEmpty>
                        <CommandGroup>
                            {clients.map(c => (
                                <CommandItem
                                    key={c.id}
                                    value={c.name}
                                    onSelect={() => { onSelect({ id: c.id, name: c.name }); setOpen(false); }}
                                    className="text-slate-200"
                                >
                                    <Check className={cn('mr-2 h-3.5 w-3.5', value === c.id ? 'opacity-100' : 'opacity-0')} />
                                    <Building2 className="h-3.5 w-3.5 text-indigo-400 mr-1.5 shrink-0" />
                                    <span className="truncate flex-1">{c.name}</span>
                                    {c.client_type?.name && (
                                        <span className="text-[10px] text-slate-500 ml-2 truncate">{c.client_type.name}</span>
                                    )}
                                </CommandItem>
                            ))}
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
}

/**
 * technique-picker.tsx — Searchable MITRE ATT&CK technique selector.
 *
 * Used on finding create/edit forms to map findings to techniques.
 * Features:
 *  - Search by technique ID (T1059) or name ("PowerShell")
 *  - Grouped by tactic with collapsible sections
 *  - Multi-select with checkboxes
 *  - Selected techniques shown as removable badges
 *  - Debounced search for performance with 600+ entries
 */

'use client';

import { useState, useMemo, useCallback } from 'react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import { useDebounce } from '@/lib/hooks/use-debounce';
import {
    TACTICS,
    TECHNIQUES,
    TECHNIQUE_MAP,
    TACTIC_MAP,
    type AttackTechnique,
} from '@/lib/attack-data';
import {
    Search,
    X,
    ChevronDown,
    ChevronRight,
    Shield,
    ExternalLink,
} from 'lucide-react';
import { cn } from '@/lib/utils';


interface TechniquePickerProps {
    value: string[];
    onChange: (ids: string[]) => void;
    placeholder?: string;
    disabled?: boolean;
    className?: string;
}

export function TechniquePicker({
    value,
    onChange,
    placeholder = 'Map ATT&CK techniques…',
    disabled = false,
    className,
}: TechniquePickerProps) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const debouncedSearch = useDebounce(search, 200);
    const [expandedTactics, setExpandedTactics] = useState<Set<string>>(new Set());

    // Selected technique IDs as a set for O(1) lookup
    const selectedSet = useMemo(() => new Set(value), [value]);

    // Build the filtered, grouped dataset
    const groupedTechniques = useMemo(() => {
        const q = debouncedSearch.toLowerCase().trim();

        // Filter techniques by query
        const filtered = q
            ? TECHNIQUES.filter(
                t => t.id.toLowerCase().includes(q) || t.name.toLowerCase().includes(q)
            )
            : TECHNIQUES;

        // Group by tactic
        const groups: { tactic: typeof TACTICS[0]; techniques: AttackTechnique[] }[] = [];
        for (const tactic of TACTICS) {
            const techs = filtered.filter(t => t.tacticIds.includes(tactic.id));
            if (techs.length > 0) {
                // Sort: base techniques first (alphabetically), then sub-techniques under parents
                const sorted = techs.sort((a, b) => {
                    // Base techniques before sub-techniques
                    if (!a.isSubtechnique && b.isSubtechnique) return -1;
                    if (a.isSubtechnique && !b.isSubtechnique) return 1;
                    // Within same level, sort by ID
                    return a.id.localeCompare(b.id);
                });
                groups.push({ tactic, techniques: sorted });
            }
        }
        return groups;
    }, [debouncedSearch]);

    const toggleTechnique = useCallback((id: string) => {
        if (selectedSet.has(id)) {
            onChange(value.filter(v => v !== id));
        } else {
            onChange([...value, id]);
        }
    }, [value, selectedSet, onChange]);

    const removeTechnique = useCallback((id: string) => {
        onChange(value.filter(v => v !== id));
    }, [value, onChange]);

    const toggleTactic = useCallback((tacticId: string) => {
        setExpandedTactics(prev => {
            const next = new Set(prev);
            if (next.has(tacticId)) {
                next.delete(tacticId);
            } else {
                next.add(tacticId);
            }
            return next;
        });
    }, []);

    // Auto-expand tactics when searching
    const effectiveExpanded = useMemo(() => {
        if (debouncedSearch.trim()) {
            return new Set(TACTICS.map(t => t.id));
        }
        return expandedTactics;
    }, [debouncedSearch, expandedTactics]);

    return (
        <div className={cn('space-y-2', className)}>
            {/* Picker trigger */}
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild disabled={disabled}>
                    <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={open}
                        className={cn(
                            'w-full justify-between bg-slate-950/50 border-slate-800 text-slate-400 hover:text-white hover:bg-slate-900/70',
                            value.length > 0 && 'text-primary'
                        )}
                    >
                        <span className="flex items-center gap-2">
                            <Shield className="h-4 w-4 shrink-0 text-primary" />
                            {value.length > 0
                                ? `${value.length} technique${value.length !== 1 ? 's' : ''} mapped`
                                : placeholder
                            }
                        </span>
                        <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                </PopoverTrigger>

                <PopoverContent
                    className="w-[520px] p-0 bg-slate-900 border-slate-800"
                    align="start"
                    sideOffset={4}
                >
                    {/* Search */}
                    <div className="flex items-center gap-2 p-3 border-b border-slate-800/60">
                        <Search className="h-4 w-4 text-slate-500 shrink-0" />
                        <Input
                            placeholder="Search by ID or name (e.g. T1059 or PowerShell)…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="h-8 bg-transparent border-none shadow-none focus-visible:ring-0 text-sm placeholder:text-slate-600"
                            autoFocus
                        />
                        {search && (
                            <button onClick={() => setSearch('')} className="text-slate-500 hover:text-slate-300">
                                <X className="h-4 w-4" />
                            </button>
                        )}
                    </div>

                    {/* Technique list */}
                    <ScrollArea className="h-[400px]">
                        <div className="p-2">
                            {groupedTechniques.length === 0 && (
                                <p className="text-sm text-slate-500 text-center py-8">
                                    No techniques match "{search}"
                                </p>
                            )}

                            {groupedTechniques.map(({ tactic, techniques }) => {
                                const isExpanded = effectiveExpanded.has(tactic.id);
                                const selectedInTactic = techniques.filter(t => selectedSet.has(t.id)).length;

                                return (
                                    <div key={tactic.id} className="mb-1">
                                        {/* Tactic header */}
                                        <button
                                            onClick={() => toggleTactic(tactic.id)}
                                            className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-slate-800/60 text-left group"
                                        >
                                            {isExpanded
                                                ? <ChevronDown className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                                                : <ChevronRight className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                                            }
                                            <span className="text-xs font-bold uppercase tracking-wider text-slate-400 group-hover:text-slate-300">
                                                {tactic.name}
                                            </span>
                                            <span className="text-[10px] text-slate-600 ml-auto">
                                                {selectedInTactic > 0 && (
                                                    <Badge variant="secondary" className="bg-primary/20 text-primary border-none px-1 h-4 text-[9px] mr-1">
                                                        {selectedInTactic}
                                                    </Badge>
                                                )}
                                                {techniques.length}
                                            </span>
                                        </button>

                                        {/* Techniques */}
                                        {isExpanded && (
                                            <div className="ml-2 border-l border-slate-800/40 pl-2 space-y-0.5">
                                                {techniques.map(tech => (
                                                    <label
                                                        key={`${tactic.id}-${tech.id}`}
                                                        className={cn(
                                                            'flex items-center gap-2 px-2 py-1 rounded-md cursor-pointer transition-colors text-sm',
                                                            selectedSet.has(tech.id)
                                                                ? 'bg-primary/10 text-primary'
                                                                : 'hover:bg-slate-800/40 text-slate-400 hover:text-slate-300',
                                                            tech.isSubtechnique && 'ml-4 text-xs'
                                                        )}
                                                    >
                                                        <Checkbox
                                                            checked={selectedSet.has(tech.id)}
                                                            onCheckedChange={() => toggleTechnique(tech.id)}
                                                            className="border-slate-700 data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                                                        />
                                                        <span className="font-mono text-[11px] text-slate-500 w-[75px] shrink-0">
                                                            {tech.id}
                                                        </span>
                                                        <span className="truncate flex-1">{tech.name}</span>
                                                        <a
                                                            href={tech.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            onClick={(e) => e.stopPropagation()}
                                                            className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-primary transition-opacity"
                                                        >
                                                            <ExternalLink className="h-3 w-3" />
                                                        </a>
                                                    </label>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </ScrollArea>

                    {/* Footer */}
                    <div className="flex items-center justify-between p-2 border-t border-slate-800/60 text-xs text-slate-500">
                        <span>{value.length} selected</span>
                        {value.length > 0 && (
                            <button
                                onClick={() => onChange([])}
                                className="text-red-400/70 hover:text-red-400 transition-colors"
                            >
                                Clear all
                            </button>
                        )}
                    </div>
                </PopoverContent>
            </Popover>

            {/* Selected badges — rendered below the trigger so selections don't shift the button */}
            {value.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                    {value.map(id => {
                        const tech = TECHNIQUE_MAP.get(id);
                        return (
                            <Badge
                                key={id}
                                variant="secondary"
                                className="bg-purple-500/15 text-purple-400 border-purple-500/30 hover:bg-primary/25 pr-1 gap-1 text-xs"
                            >
                                <Shield className="h-3 w-3 shrink-0" />
                                {tech ? `${tech.id} ${tech.name}` : id}
                                {!disabled && (
                                    <button
                                        onClick={(e) => { e.stopPropagation(); removeTechnique(id); }}
                                        className="ml-0.5 rounded-full p-0.5 hover:bg-primary/30 transition-colors"
                                    >
                                        <X className="h-3 w-3" />
                                    </button>
                                )}
                            </Badge>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

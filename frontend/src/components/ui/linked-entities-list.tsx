'use client';

import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Bug, CheckSquare, StickyNote, Trash2, Search } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface LinkedEntity {
    type: 'finding' | 'testcase' | 'note';
    id: string;
    title: string;
}

const TYPE_ICON: Record<LinkedEntity['type'], React.ElementType> = {
    finding: Bug,
    testcase: CheckSquare,
    note: StickyNote,
};

const TYPE_COLOR: Record<LinkedEntity['type'], string> = {
    finding: 'text-red-400',
    testcase: 'text-emerald-400',
    note: 'text-teal-400',
};

interface LinkedEntitiesListProps {
    entities: LinkedEntity[];
    onUnlink?: (entity: LinkedEntity) => void | Promise<void>;
    emptyText?: string;
    /** Show a filter box once the list grows past this many rows. */
    searchThreshold?: number;
    /** Rows shown before a "Show all" expander appears. */
    collapsedCount?: number;
}

/**
 * Scale-friendly list of entities linked to a global item (intel / infra).
 * Because those items can accumulate a large number of links, the list caps
 * its height and offers a filter + collapse so it never dominates the panel.
 */
export function LinkedEntitiesList({
    entities,
    onUnlink,
    emptyText = 'No linked entities yet.',
    searchThreshold = 8,
    collapsedCount = 6,
}: LinkedEntitiesListProps) {
    const [query, setQuery] = useState('');
    const [expanded, setExpanded] = useState(false);

    const showSearch = entities.length > searchThreshold;

    const filtered = useMemo(() => {
        const term = query.trim().toLowerCase();
        if (!term) return entities;
        return entities.filter(
            e => e.title.toLowerCase().includes(term) || e.type.includes(term)
        );
    }, [entities, query]);

    if (entities.length === 0) {
        return <p className="text-xs text-slate-500 italic py-2">{emptyText}</p>;
    }

    const isFiltering = query.trim().length > 0;
    const canCollapse = !isFiltering && filtered.length > collapsedCount;
    const visible = canCollapse && !expanded ? filtered.slice(0, collapsedCount) : filtered;
    // Scroll once we're showing a long list (expanded or actively filtering).
    const scroll = visible.length > collapsedCount;

    return (
        <div className="space-y-2">
            {showSearch && (
                <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                    <Input
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        placeholder="Filter linked items..."
                        className="h-8 text-xs pl-8 bg-slate-950 border-slate-800"
                    />
                </div>
            )}

            <div className={cn('space-y-1', scroll && 'max-h-72 overflow-y-auto pr-1')}>
                {visible.length === 0 ? (
                    <p className="text-xs text-slate-500 italic py-2">No matches.</p>
                ) : (
                    visible.map(entity => {
                        const Icon = TYPE_ICON[entity.type];
                        return (
                            <div
                                key={`${entity.type}-${entity.id}`}
                                className="flex items-center justify-between rounded-lg bg-slate-950/50 border border-slate-800 px-3 py-2 min-w-0"
                            >
                                <div className="flex items-center gap-2 min-w-0 flex-1">
                                    {Icon && <Icon className={cn('h-3.5 w-3.5 shrink-0', TYPE_COLOR[entity.type])} />}
                                    <Badge className="text-[10px] py-0 bg-slate-800 text-slate-400 border-slate-700 capitalize shrink-0">
                                        {entity.type}
                                    </Badge>
                                    <span className="text-sm text-slate-300 truncate" title={entity.title}>
                                        {entity.title}
                                    </span>
                                </div>
                                {onUnlink && (
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-6 w-6 text-slate-600 hover:text-red-400 shrink-0"
                                        onClick={() => onUnlink(entity)}
                                        title="Unlink"
                                    >
                                        <Trash2 className="h-3 w-3" />
                                    </Button>
                                )}
                            </div>
                        );
                    })
                )}
            </div>

            {canCollapse && (
                <button
                    onClick={() => setExpanded(v => !v)}
                    className="text-[11px] text-slate-400 hover:text-white transition-colors"
                >
                    {expanded ? 'Show less' : `Show all ${filtered.length}`}
                </button>
            )}
            {isFiltering && (
                <p className="text-[11px] text-slate-500">{filtered.length} of {entities.length} match</p>
            )}
        </div>
    );
}

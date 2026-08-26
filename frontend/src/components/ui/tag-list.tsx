'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export interface TagListTag {
    id: string;
    name: string;
    color?: string | null;
}

/**
 * Renders a list of colored tag badges that scales: it shows at most `max`
 * tags, collapses the rest behind a clickable "+N" pill (hover shows their
 * names), and each long tag name truncates with a hover tooltip. Used on the
 * finding/test-case detail sheets and full view pages so 10+ tags don't blow
 * out the layout.
 */
export function TagList({
    tags,
    max = 6,
    className,
}: {
    tags?: TagListTag[] | null;
    max?: number;
    className?: string;
}) {
    const [expanded, setExpanded] = useState(false);
    const list = tags ?? [];
    if (list.length === 0) return null;

    const shown = expanded ? list : list.slice(0, max);
    const hidden = list.length - shown.length;

    return (
        <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
            {shown.map(tag => (
                <Badge
                    key={tag.id}
                    variant="outline"
                    title={tag.name}
                    className="px-2 py-0.5 border-none font-bold text-[10px] uppercase tracking-wider max-w-[160px] truncate"
                    style={{ backgroundColor: `${tag.color || '#64748b'}20`, color: tag.color || '#94a3b8' }}
                >
                    {tag.name}
                </Badge>
            ))}
            {hidden > 0 && (
                <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setExpanded(true); }}
                    title={list.slice(max).map(t => t.name).join(', ')}
                    className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
                >
                    +{hidden}
                </button>
            )}
            {expanded && list.length > max && (
                <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setExpanded(false); }}
                    className="text-[10px] font-medium px-2 py-0.5 rounded-full text-slate-500 hover:text-white transition-colors"
                >
                    show less
                </button>
            )}
        </div>
    );
}

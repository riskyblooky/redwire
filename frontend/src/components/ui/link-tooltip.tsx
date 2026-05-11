'use client';

import * as React from 'react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import Link from 'next/link';

interface LinkTooltipItem {
    name: string;
    /** Optional URL to navigate to when the item is clicked */
    href?: string;
    /** Optional click handler (used when href is not applicable, e.g. opening a dialog) */
    onClick?: () => void;
}

interface LinkTooltipProps {
    icon: React.ReactNode;
    count: number;
    items: LinkTooltipItem[];
    label: string;
    colorClass: string;
    /** Optional className for the outer wrapper */
    className?: string;
    /** Icon size class for the count text, defaults to text-sm */
    countClass?: string;
}

/**
 * Wraps a link icon + count with a hover tooltip that lists linked item names.
 * Falls back to a simple count label if no item names are available.
 * Items with an `href` are rendered as clickable links.
 * Items with an `onClick` are rendered as clickable buttons.
 */
export function LinkTooltip({
    icon,
    count,
    items,
    label,
    colorClass,
    className,
    countClass = 'text-sm font-medium',
}: LinkTooltipProps) {
    if (count <= 0) return null;

    const hasNames = items.length > 0 && items.some(i => i.name);

    return (
        <TooltipProvider delayDuration={200}>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className={cn('flex items-center gap-1 cursor-default', colorClass, className)}>
                        {icon}
                        <span className={countClass}>{count}</span>
                    </div>
                </TooltipTrigger>
                <TooltipContent
                    side="top"
                    className="bg-slate-900 border-slate-700 text-white px-3 py-2.5 rounded-xl shadow-xl shadow-black/40 max-w-[280px]"
                >
                    <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold mb-1.5">
                        {label} ({count})
                    </p>
                    {hasNames ? (
                        <ul className="space-y-1">
                            {items.map((item, idx) => (
                                <li
                                    key={idx}
                                    className="text-xs truncate max-w-[250px] flex items-center gap-1.5"
                                >
                                    <span className="w-1 h-1 rounded-full bg-current shrink-0 opacity-50" />
                                    {item.href ? (
                                        <Link
                                            href={item.href}
                                            className="text-slate-200 hover:text-white hover:underline underline-offset-2 transition-colors truncate"
                                            onClick={(e) => e.stopPropagation()}
                                        >
                                            {item.name}
                                        </Link>
                                    ) : item.onClick ? (
                                        <button
                                            className="text-slate-200 hover:text-white hover:underline underline-offset-2 transition-colors truncate text-left"
                                            onClick={(e) => { e.stopPropagation(); item.onClick!(); }}
                                        >
                                            {item.name}
                                        </button>
                                    ) : (
                                        <span className="text-slate-200 truncate">{item.name}</span>
                                    )}
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="text-xs text-slate-300">
                            {count} {label.toLowerCase()} linked
                        </p>
                    )}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

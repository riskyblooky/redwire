'use client';

import { useState, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CollapsibleSectionProps {
    /** Section heading text. */
    title: string;
    /** Optional leading icon (a lucide icon component). */
    icon?: React.ComponentType<{ className?: string }>;
    /** Tailwind text-color class for the icon, e.g. "text-red-400". */
    iconColor?: string;
    /** Whether the section starts expanded. Defaults to true. */
    defaultOpen?: boolean;
    /** Optional node rendered on the right of the header (e.g. a + Link button
     *  or an approval-count badge). Clicks here do NOT toggle the section. */
    right?: ReactNode;
    children: ReactNode;
    className?: string;
    contentClassName?: string;
}

/**
 * A lightweight collapsible section used by the detail side-sheets so a narrow
 * half-view can hide sections the reader isn't interested in. Default open/closed
 * state is set per section to match the full detail page.
 */
export function CollapsibleSection({
    title,
    icon: Icon,
    iconColor,
    defaultOpen = true,
    right,
    children,
    className,
    contentClassName,
}: CollapsibleSectionProps) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className={className}>
            <div className="flex items-center justify-between gap-2">
                <button
                    type="button"
                    onClick={() => setOpen((o) => !o)}
                    className="flex items-center gap-2 flex-1 min-w-0 text-left py-1 text-white"
                >
                    <ChevronRight className={cn('h-3.5 w-3.5 text-slate-400 shrink-0 transition-transform', open && 'rotate-90')} />
                    {Icon && <Icon className={cn('h-4 w-4 shrink-0', iconColor)} />}
                    <h4 className="text-sm font-bold text-white truncate">{title}</h4>
                </button>
                {right}
            </div>
            {open && <div className={cn('mt-2', contentClassName)}>{children}</div>}
        </div>
    );
}

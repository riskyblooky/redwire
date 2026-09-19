'use client';

import { useEffect, useState } from 'react';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Per-view persisted collapse state for a detail page's right pane. Remembers the
 * choice in localStorage (keyed per view) so it survives navigation/reload; falls
 * back gracefully if storage is unavailable.
 */
export function useRightPaneCollapsed(storageKey: string): [boolean, (v: boolean) => void] {
    const [collapsed, setCollapsed] = useState(false);

    useEffect(() => {
        try {
            const v = localStorage.getItem(storageKey);
            if (v === '1') setCollapsed(true);
        } catch { /* storage unavailable */ }
    }, [storageKey]);

    const set = (v: boolean) => {
        setCollapsed(v);
        try { localStorage.setItem(storageKey, v ? '1' : '0'); } catch { /* ignore */ }
    };

    return [collapsed, set];
}

/** Header button that collapses the right pane (chevron/panel pointing right). */
export function RightPaneCollapseButton({ onClick, className }: { onClick: () => void; className?: string }) {
    return (
        <button
            type="button"
            onClick={onClick}
            title="Collapse panel"
            aria-label="Collapse panel"
            className={cn('p-1 rounded text-slate-500 hover:text-white hover:bg-slate-800/60 transition-colors', className)}
        >
            <PanelRightClose className="h-4 w-4" />
        </button>
    );
}

/**
 * Slim vertical tab shown in place of the collapsed pane, on the right edge, to
 * bring it back. Rendered as its own grid column so the main content still fills
 * the rest of the row.
 */
export function RightPaneExpandTab({ onClick, label = 'Details' }: { onClick: () => void; label?: string }) {
    return (
        <button
            type="button"
            onClick={onClick}
            title="Expand panel"
            aria-label="Expand panel"
            className="group flex flex-col items-center gap-2 py-3 px-1.5 rounded-lg border border-slate-800 bg-slate-900/50 hover:bg-slate-800/60 hover:border-slate-700 text-slate-500 hover:text-white transition-colors self-start"
        >
            <PanelRightOpen className="h-4 w-4" />
            <span className="text-[10px] font-black uppercase tracking-widest [writing-mode:vertical-rl] rotate-180">{label}</span>
        </button>
    );
}

/**
 * useColumnVisibility — Persisted column visibility for engagement tab tables.
 *
 * Stores visible column state in localStorage so preferences survive reloads.
 * Returns [visibleCols, toggleCol] where visibleCols is a Set<string>.
 */
import { useState, useCallback, useEffect } from 'react';

export interface ColumnDef {
    key: string;
    label: string;
    /** If true the column cannot be hidden (e.g. "Name", "Actions") */
    required?: boolean;
}

/** Returns a Set of currently-visible column keys and a toggle function. */
export function useColumnVisibility(
    storageKey: string,
    columns: ColumnDef[],
): [Set<string>, (key: string) => void] {
    const [visible, setVisible] = useState<Set<string>>(() => {
        if (typeof window === 'undefined') return new Set(columns.map(c => c.key));
        const saved = localStorage.getItem(storageKey);
        if (saved) {
            try {
                const parsed: string[] = JSON.parse(saved);
                // Only include keys that still exist in the current column def
                const valid = parsed.filter(k => columns.some(c => c.key === k));
                if (valid.length > 0) return new Set(valid);
            } catch { /* ignore */ }
        }
        return new Set(columns.map(c => c.key));
    });

    useEffect(() => {
        localStorage.setItem(storageKey, JSON.stringify([...visible]));
    }, [visible, storageKey]);

    const toggle = useCallback((key: string) => {
        const col = columns.find(c => c.key === key);
        if (col?.required) return;
        setVisible(prev => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key); else next.add(key);
            return next;
        });
    }, [columns]);

    return [visible, toggle];
}

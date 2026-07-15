/**
 * useColumnVisibility — Persisted column visibility for engagement tab tables.
 *
 * Stores visible column state in localStorage so preferences survive reloads.
 * Returns [visibleCols, toggleCol] where visibleCols is a Set<string>.
 */
import { useState, useCallback, useEffect, useRef } from 'react';

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

    // Default brand-new columns (e.g. a just-added custom field, which loads
    // async after mount) to VISIBLE instead of hidden. A separate ":known"
    // list distinguishes "column never seen" (default on) from "user hid it"
    // (stay off). On first migration we seed known with the current columns so
    // existing hide choices are preserved.
    const knownRef = useRef<Set<string> | null>(null);
    const columnsKey = columns.map(c => c.key).join(',');
    useEffect(() => {
        if (typeof window === 'undefined') return;
        if (knownRef.current === null) {
            const raw = localStorage.getItem(storageKey + ':known');
            if (raw) {
                try { knownRef.current = new Set(JSON.parse(raw)); }
                catch { knownRef.current = new Set(); }
            } else {
                knownRef.current = new Set(columns.map(c => c.key));
                localStorage.setItem(storageKey + ':known', JSON.stringify([...knownRef.current]));
                return;
            }
        }
        const fresh = columns.filter(c => !knownRef.current!.has(c.key));
        if (fresh.length > 0) {
            fresh.forEach(c => knownRef.current!.add(c.key));
            localStorage.setItem(storageKey + ':known', JSON.stringify([...knownRef.current!]));
            setVisible(prev => new Set([...prev, ...fresh.map(c => c.key)]));
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [columnsKey, storageKey]);

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

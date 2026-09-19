import { cn } from '@/lib/utils';

interface ResultCountProps {
    /** Number of rows currently shown (after search + filters). */
    count: number;
    /** Optional pre-filter total. When given and different from `count`, the
     *  label reads "N of M" so it's clear a search/filter is narrowing things. */
    total?: number;
    /** Singular noun for the row type, e.g. "finding". Pluralized with +s. */
    noun?: string;
    className?: string;
}

/**
 * Compact, muted "N results" label shown next to a search/filter bar. Kept as a
 * shared component so every list page reads the same. Uses tabular-nums so the
 * number doesn't jitter as results change.
 */
export function ResultCount({ count, total, noun = 'result', className }: ResultCountProps) {
    const plural = count === 1 ? noun : `${noun}s`;
    const narrowed = total != null && total !== count;
    return (
        <span
            className={cn('text-xs text-slate-500 whitespace-nowrap tabular-nums shrink-0', className)}
            aria-live="polite"
        >
            {narrowed ? `${count} of ${total} ${noun}${total === 1 ? '' : 's'}` : `${count} ${plural}`}
        </span>
    );
}

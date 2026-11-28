'use client';

import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export const PAGE_SIZES = [25, 50, 100] as const;

interface ListPaginationProps {
    /** 1-based. */
    page: number;
    pageSize: number;
    /** Rows matching the filters (X-Total-Count). */
    total: number;
    onPageChange: (page: number) => void;
    onPageSizeChange?: (size: number) => void;
    isFetching?: boolean;
    className?: string;
}

/**
 * The paging bar under a server-paged list: "26–50 of 132", page size, and
 * previous / next. Hidden when everything fits on one page at the smallest
 * size, so short lists look as they did.
 */
export function ListPagination({
    page, pageSize, total, onPageChange, onPageSizeChange, isFetching, className,
}: ListPaginationProps) {
    const pages = Math.max(1, Math.ceil(total / pageSize));
    if (total <= PAGE_SIZES[0] && page === 1) return null;
    const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
    const last = Math.min(total, page * pageSize);

    return (
        <div className={cn('flex flex-wrap items-center justify-between gap-3 pt-4 text-xs text-muted-foreground', className)}>
            <span className="tabular-nums" aria-live="polite">
                {first}–{last} of {total}
                {isFetching && <Loader2 className="ml-2 inline h-3 w-3 animate-spin" />}
            </span>
            <div className="flex items-center gap-3">
                {onPageSizeChange && (
                    <label className="flex items-center gap-1.5">
                        <span>Per page</span>
                        <select
                            value={pageSize}
                            onChange={(e) => onPageSizeChange(Number(e.target.value))}
                            className="h-7 rounded border border-slate-700 bg-slate-900 px-1.5 text-xs text-slate-200 focus:border-primary focus:outline-none"
                        >
                            {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
                        </select>
                    </label>
                )}
                <span className="tabular-nums">Page {Math.min(page, pages)} of {pages}</span>
                <div className="flex items-center gap-1">
                    <Button
                        size="icon" variant="ghost" className="h-7 w-7"
                        disabled={page <= 1} onClick={() => onPageChange(page - 1)} aria-label="Previous page"
                    >
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button
                        size="icon" variant="ghost" className="h-7 w-7"
                        disabled={page >= pages} onClick={() => onPageChange(page + 1)} aria-label="Next page"
                    >
                        <ChevronRight className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        </div>
    );
}

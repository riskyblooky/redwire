'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import {
    Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import {
    Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
    Search, BookOpen, Loader2, FileText, ChevronLeft, ChevronRight,
    Filter, Check, ChevronsUpDown, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { useDebounce } from '@/lib/hooks/use-debounce';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';

const PAGE_SIZE = 25;

export type PickerTemplateStatus = 'DRAFT' | 'SUBMITTED' | 'PUBLISHED';

/** The picker fetches full template rows; onSelect hands the caller the whole object. */
export interface PickerTemplate {
    id: string;
    title: string;
    category?: string | null;
    description?: string | null;
    status?: PickerTemplateStatus;
    [key: string]: any;
}
// Back-compat alias for existing imports.
export type TemplateItem = PickerTemplate;

const STATUS_PILL: Record<PickerTemplateStatus, { label: string; cls: string }> = {
    DRAFT:     { label: 'Draft',     cls: 'bg-slate-500/15 text-slate-300 border-slate-500/30' },
    SUBMITTED: { label: 'Submitted', cls: 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30' },
    PUBLISHED: { label: 'Published', cls: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' },
};

interface TemplatePickerDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    /** Which template library to browse. Drives the endpoint + category types. */
    resource: 'finding' | 'testcase';
    onSelect: (template: PickerTemplate) => void;
    title?: string;
    description?: string;
}

export function TemplatePickerDialog({
    open,
    onOpenChange,
    resource,
    onSelect,
    title = 'Select Template',
    description = 'Search and select a template to apply.',
}: TemplatePickerDialogProps) {
    const [search, setSearch] = useState('');
    const debouncedSearch = useDebounce(search, 300);
    const [categories, setCategories] = useState<string[]>([]);   // [] = all
    const [includeNonPublished, setIncludeNonPublished] = useState(false);
    const [showFilters, setShowFilters] = useState(false);
    const [catOpen, setCatOpen] = useState(false);

    const endpoint = resource === 'finding' ? '/templates' : '/testcase-templates';

    // Category options + colors from the configurable types (full set).
    const { data: categoryTypes = [] } = useConfigurableTypes(resource);
    const categoryColors = useMemo(() => {
        const m: Record<string, string> = {};
        categoryTypes.forEach((t: any) => { m[t.name] = t.color; });
        return m;
    }, [categoryTypes]);

    const activeFilterCount = categories.length + (includeNonPublished ? 1 : 0);

    const scrollRef = useRef<HTMLDivElement>(null);
    const sentinelRef = useRef<HTMLDivElement>(null);

    // Server-side search + infinite scroll (live). Only runs while the dialog is open.
    const query = useInfiniteQuery({
        queryKey: ['template-picker', resource, { q: debouncedSearch, categories, includeNonPublished }],
        queryFn: async ({ pageParam }) => {
            // URLSearchParams so multi-category serializes as repeated ?category=A&category=B
            const params = new URLSearchParams();
            if (debouncedSearch.trim()) params.set('q', debouncedSearch.trim());
            categories.forEach(c => params.append('category', c));
            if (!includeNonPublished) params.set('status', 'PUBLISHED');
            params.set('sort_by', 'title');
            params.set('sort_dir', 'asc');
            params.set('skip', String(pageParam * PAGE_SIZE));
            params.set('limit', String(PAGE_SIZE));
            const res = await api.get(`${endpoint}?${params.toString()}`);
            const total = Number(res.headers['x-total-count'] ?? res.data.length);
            return { items: res.data as PickerTemplate[], total, page: pageParam };
        },
        initialPageParam: 0,
        getNextPageParam: (lastPage, allPages) => {
            const loaded = allPages.reduce((n, p) => n + p.items.length, 0);
            return loaded < lastPage.total ? allPages.length : undefined;
        },
        enabled: open,
        staleTime: 30_000,
    });

    const items = query.data?.pages.flatMap(p => p.items) ?? [];
    const total = query.data?.pages[0]?.total ?? 0;
    const isLoading = query.isLoading;

    // Fetch the next page as the sentinel scrolls near the bottom of the list.
    useEffect(() => {
        const el = sentinelRef.current;
        if (!el || !query.hasNextPage) return;
        const obs = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting && query.hasNextPage && !query.isFetchingNextPage) {
                    query.fetchNextPage();
                }
            },
            { root: scrollRef.current, rootMargin: '200px' },
        );
        obs.observe(el);
        return () => obs.disconnect();
    }, [query.hasNextPage, query.isFetchingNextPage, query.fetchNextPage, items.length]);

    // Jump back to the top when the result set changes.
    useEffect(() => {
        scrollRef.current?.scrollTo({ top: 0 });
    }, [debouncedSearch, categories, includeNonPublished]);

    const handleOpenChange = (isOpen: boolean) => {
        if (!isOpen) {
            setSearch(''); setCategories([]); setIncludeNonPublished(false); setShowFilters(false);
        }
        onOpenChange(isOpen);
    };

    const handleSelect = (t: PickerTemplate) => {
        onSelect(t);
        handleOpenChange(false);
    };

    const stripHtml = (html: string) => html.replace(/<[^>]*>/g, '').trim();
    const categoryLabel = categories.length === 0
        ? 'All categories'
        : categories.length === 1
            ? categories[0].replace(/_/g, ' ')
            : `${categories.length} categories`;

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[820px] p-0 gap-0 overflow-hidden max-h-[85vh] flex flex-col top-[7vh] translate-y-0 data-[state=open]:slide-in-from-top-[7%] data-[state=closed]:slide-out-to-top-[7%]">
                <div className="p-6 pb-4 space-y-3 shrink-0">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-lg">
                            <BookOpen className="h-5 w-5 text-indigo-400" />
                            {title}
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">{description}</DialogDescription>
                    </DialogHeader>

                    {/* Search + inline filter toggle */}
                    <div className="flex items-center gap-2">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                            <Input
                                placeholder="Search by title, category, or description..."
                                className="pl-11 h-12 text-base bg-slate-950/50 border-slate-800 text-white rounded-lg focus:ring-primary/30 placeholder:text-slate-600"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                autoFocus
                            />
                        </div>
                        <Button
                            size="icon"
                            variant="ghost"
                            onClick={() => setShowFilters(o => !o)}
                            title={activeFilterCount > 0 ? `Filters — ${activeFilterCount} applied` : 'Filters'}
                            className={cn(
                                'h-12 w-12 shrink-0',
                                activeFilterCount > 0
                                    ? 'text-primary bg-primary/10 hover:bg-primary/15'
                                    : 'text-slate-400 hover:text-white',
                            )}
                        >
                            <Filter className="h-4 w-4" />
                        </Button>
                    </div>

                    {/* Filter controls — revealed by the filter button */}
                    {showFilters && (
                        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 pt-1">
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Category</span>
                                <Popover open={catOpen} onOpenChange={setCatOpen}>
                                    <PopoverTrigger asChild>
                                        <Button variant="outline" role="combobox" className="h-10 w-72 justify-between bg-slate-800/50 border-slate-700 text-white font-normal hover:bg-slate-800 hover:text-white">
                                            <span className="flex items-center gap-2 min-w-0">
                                                {categories.length === 1 && (
                                                    <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: categoryColors[categories[0]] || '#6366f1' }} />
                                                )}
                                                <span className={cn('truncate', categories.length === 0 && 'text-slate-500')}>{categoryLabel}</span>
                                            </span>
                                            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="p-0 bg-slate-900 border-slate-700" style={{ width: 'var(--radix-popover-trigger-width)' }} align="start">
                                        <Command className="bg-slate-900">
                                            <CommandInput placeholder="Search categories…" className="text-white" />
                                            <CommandList className="max-h-80">
                                                <CommandEmpty>No categories.</CommandEmpty>
                                                <CommandGroup>
                                                    {categoryTypes.map((t: any) => {
                                                        const selected = categories.includes(t.name);
                                                        return (
                                                            <CommandItem
                                                                key={t.id ?? t.name}
                                                                value={t.name}
                                                                onSelect={() => setCategories(prev => prev.includes(t.name) ? prev.filter(c => c !== t.name) : [...prev, t.name])}
                                                                className="text-slate-200"
                                                            >
                                                                <Check className={cn('mr-2 h-3.5 w-3.5', selected ? 'opacity-100' : 'opacity-0')} />
                                                                <span className="h-2 w-2 rounded-full mr-2 shrink-0" style={{ backgroundColor: t.color || '#6366f1' }} />
                                                                <span className="truncate">{t.name.replace(/_/g, ' ')}</span>
                                                            </CommandItem>
                                                        );
                                                    })}
                                                </CommandGroup>
                                            </CommandList>
                                        </Command>
                                    </PopoverContent>
                                </Popover>
                                {categories.length > 0 && (
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-white" onClick={() => setCategories([])} title="Clear categories">
                                        <X className="h-3.5 w-3.5" />
                                    </Button>
                                )}
                            </div>
                            <label className="flex items-center gap-2 text-xs text-slate-400 select-none cursor-pointer">
                                <Switch checked={includeNonPublished} onCheckedChange={setIncludeNonPublished} />
                                Include drafts &amp; submitted
                            </label>
                        </div>
                    )}
                </div>

                {/* Results — server-side infinite scroll */}
                <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0 px-6">
                    {isLoading ? (
                        <div className="flex flex-col items-center justify-center py-16">
                            <Loader2 className="h-6 w-6 animate-spin text-indigo-400 mb-2" />
                            <p className="text-slate-500 text-sm">Loading templates...</p>
                        </div>
                    ) : items.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16">
                            <FileText className="h-10 w-10 text-slate-700 mb-3" />
                            <p className="text-slate-400 font-medium">No templates match your filters</p>
                            {(search || categories.length > 0) && <p className="text-slate-600 text-xs mt-1">Try a different search or category</p>}
                        </div>
                    ) : (
                        <div className="space-y-1.5 pb-2">
                            {items.map((t) => {
                                const catColor = categoryColors[t.category || ''] || '#64748b';
                                return (
                                    <button
                                        key={t.id}
                                        onClick={() => handleSelect(t)}
                                        className={cn(
                                            'w-full text-left p-3 rounded-lg border transition-all duration-150',
                                            'bg-slate-950/30 border-slate-800/60',
                                            'hover:border-indigo-500/30 hover:bg-slate-900',
                                            'focus:outline-hidden focus:ring-1 focus:ring-primary/40 group cursor-pointer',
                                        )}
                                    >
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="min-w-0 flex-1">
                                                <div className="flex items-center gap-1.5 flex-wrap">
                                                    <h4 className="text-sm font-semibold text-slate-200 group-hover:text-white truncate">{t.title}</h4>
                                                    {t.status && t.status !== 'PUBLISHED' && (
                                                        <Badge variant="outline" className={cn('text-[9px] h-4 px-1.5 uppercase tracking-wider shrink-0', STATUS_PILL[t.status].cls)}>
                                                            {STATUS_PILL[t.status].label}
                                                        </Badge>
                                                    )}
                                                </div>
                                                {t.description && (
                                                    <p className="text-xs text-slate-500 mt-1 line-clamp-2 leading-relaxed group-hover:text-slate-400">{stripHtml(t.description)}</p>
                                                )}
                                            </div>
                                            {t.category && (
                                                <span
                                                    role="button"
                                                    tabIndex={0}
                                                    onClick={(e) => { e.stopPropagation(); const c = t.category!; setCategories(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]); setShowFilters(true); }}
                                                    title={`Filter by ${t.category.replace(/_/g, ' ')}`}
                                                    className="shrink-0 mt-0.5 cursor-pointer"
                                                >
                                                    <Badge
                                                        variant="outline"
                                                        className={cn(
                                                            'text-[9px] px-1.5 py-0 h-5 transition-opacity hover:opacity-80',
                                                            categories.includes(t.category) && 'ring-1 ring-inset ring-current',
                                                        )}
                                                        style={{ backgroundColor: `${catColor}15`, color: catColor, borderColor: `${catColor}40` }}
                                                    >
                                                        {t.category.replace(/_/g, ' ')}
                                                    </Badge>
                                                </span>
                                            )}
                                        </div>
                                    </button>
                                );
                            })}
                            {/* Infinite-scroll sentinel + "loading more" indicator */}
                            <div ref={sentinelRef} />
                            {query.isFetchingNextPage && (
                                <div className="flex items-center justify-center gap-2 py-3 text-xs text-slate-500">
                                    <Loader2 className="h-4 w-4 animate-spin" /> Loading more…
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer — count */}
                {!isLoading && total > 0 && (
                    <div className="px-6 py-3 border-t border-slate-800/60 shrink-0 flex items-center justify-between">
                        <p className="text-[11px] text-slate-500 flex items-center gap-2">
                            {items.length} of {total} shown{(search || categories.length > 0) ? ' · filtered' : ''}
                            {query.isFetching && !query.isFetchingNextPage && <Loader2 className="h-3 w-3 animate-spin" />}
                        </p>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

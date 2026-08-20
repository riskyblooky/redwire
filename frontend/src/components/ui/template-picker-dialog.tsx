'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
    const [page, setPage] = useState(0);
    const [category, setCategory] = useState('');            // '' = all
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

    const activeFilterCount = (category ? 1 : 0) + (includeNonPublished ? 1 : 0);

    // Server-side search + paging (live). Only runs while the dialog is open.
    const query = useQuery({
        queryKey: ['template-picker', resource, { q: debouncedSearch, category, includeNonPublished, page }],
        queryFn: async () => {
            const res = await api.get(endpoint, {
                params: {
                    q: debouncedSearch.trim() || undefined,
                    category: category || undefined,
                    status: includeNonPublished ? undefined : 'PUBLISHED',
                    sort_by: 'title', sort_dir: 'asc',
                    skip: page * PAGE_SIZE, limit: PAGE_SIZE,
                },
            });
            const total = Number(res.headers['x-total-count'] ?? res.data.length);
            return { items: res.data as PickerTemplate[], total };
        },
        enabled: open,
        placeholderData: (prev) => prev,
        staleTime: 30_000,
    });

    const items = query.data?.items ?? [];
    const total = query.data?.total ?? 0;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const isLoading = query.isLoading;

    // Reset to page 0 when the query narrows/widens.
    useEffect(() => { setPage(0); }, [debouncedSearch, category, includeNonPublished]);

    const handleOpenChange = (isOpen: boolean) => {
        if (!isOpen) {
            setSearch(''); setPage(0); setCategory(''); setIncludeNonPublished(false); setShowFilters(false);
        }
        onOpenChange(isOpen);
    };

    const handleSelect = (t: PickerTemplate) => {
        onSelect(t);
        handleOpenChange(false);
    };

    const stripHtml = (html: string) => html.replace(/<[^>]*>/g, '').trim();
    const categoryLabel = category ? category.replace(/_/g, ' ') : 'All categories';

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[820px] p-0 gap-0 overflow-hidden max-h-[85vh] flex flex-col">
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
                                className="pl-10 h-10 bg-slate-950/50 border-slate-800 text-white rounded-lg focus:ring-primary/30 placeholder:text-slate-600"
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
                                'h-10 w-10 shrink-0',
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
                                        <Button variant="outline" role="combobox" className="h-8 w-56 justify-between bg-slate-800/50 border-slate-700 text-white font-normal hover:bg-slate-800 hover:text-white">
                                            <span className="flex items-center gap-2 min-w-0">
                                                {category && (
                                                    <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: categoryColors[category] || '#6366f1' }} />
                                                )}
                                                <span className={cn('truncate', !category && 'text-slate-500')}>{categoryLabel}</span>
                                            </span>
                                            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="p-0 bg-slate-900 border-slate-700" style={{ width: 'var(--radix-popover-trigger-width)' }} align="start">
                                        <Command className="bg-slate-900">
                                            <CommandInput placeholder="Search categories…" className="text-white" />
                                            <CommandList className="max-h-64">
                                                <CommandEmpty>No categories.</CommandEmpty>
                                                <CommandGroup>
                                                    <CommandItem value="__all__ All categories" onSelect={() => { setCategory(''); setCatOpen(false); }} className="text-slate-200">
                                                        <Check className={cn('mr-2 h-3.5 w-3.5', !category ? 'opacity-100' : 'opacity-0')} />
                                                        All categories
                                                    </CommandItem>
                                                    {categoryTypes.map((t: any) => (
                                                        <CommandItem key={t.id ?? t.name} value={t.name} onSelect={() => { setCategory(t.name); setCatOpen(false); }} className="text-slate-200">
                                                            <Check className={cn('mr-2 h-3.5 w-3.5', category === t.name ? 'opacity-100' : 'opacity-0')} />
                                                            <span className="h-2 w-2 rounded-full mr-2 shrink-0" style={{ backgroundColor: t.color || '#6366f1' }} />
                                                            <span className="truncate">{t.name.replace(/_/g, ' ')}</span>
                                                        </CommandItem>
                                                    ))}
                                                </CommandGroup>
                                            </CommandList>
                                        </Command>
                                    </PopoverContent>
                                </Popover>
                                {category && (
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-white" onClick={() => setCategory('')} title="Clear category">
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

                {/* Results — server page */}
                <div className="flex-1 overflow-y-auto min-h-0 px-6">
                    {isLoading ? (
                        <div className="flex flex-col items-center justify-center py-16">
                            <Loader2 className="h-6 w-6 animate-spin text-indigo-400 mb-2" />
                            <p className="text-slate-500 text-sm">Loading templates...</p>
                        </div>
                    ) : items.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16">
                            <FileText className="h-10 w-10 text-slate-700 mb-3" />
                            <p className="text-slate-400 font-medium">No templates match your filters</p>
                            {(search || category) && <p className="text-slate-600 text-xs mt-1">Try a different search or category</p>}
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
                                                    onClick={(e) => { e.stopPropagation(); setCategory(t.category!); setShowFilters(true); }}
                                                    title={`Filter by ${t.category.replace(/_/g, ' ')}`}
                                                    className="shrink-0 mt-0.5 cursor-pointer"
                                                >
                                                    <Badge
                                                        variant="outline"
                                                        className={cn(
                                                            'text-[9px] px-1.5 py-0 h-5 transition-opacity hover:opacity-80',
                                                            category === t.category && 'ring-1 ring-inset ring-current',
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
                        </div>
                    )}
                </div>

                {/* Footer — server paging + count */}
                {!isLoading && total > 0 && (
                    <div className="px-6 py-3 border-t border-slate-800/60 shrink-0 flex items-center justify-between">
                        <p className="text-[11px] text-slate-500 flex items-center gap-2">
                            {total} template{total !== 1 ? 's' : ''}{(search || category) ? ' matching' : ' total'}
                            {query.isFetching && <Loader2 className="h-3 w-3 animate-spin" />}
                        </p>
                        {totalPages > 1 && (
                            <div className="flex items-center gap-2">
                                <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                                    className="h-7 px-2 bg-slate-800/50 border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white disabled:opacity-30">
                                    <ChevronLeft className="h-3.5 w-3.5" />
                                </Button>
                                <span className="text-[11px] text-slate-400 tabular-nums min-w-[60px] text-center">{page + 1} of {totalPages}</span>
                                <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                                    className="h-7 px-2 bg-slate-800/50 border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white disabled:opacity-30">
                                    <ChevronRight className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                        )}
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

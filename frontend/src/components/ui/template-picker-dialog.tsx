'use client';

import { useState, useMemo } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Search, BookOpen, Loader2, FileText, ChevronLeft, ChevronRight, Tag } from 'lucide-react';
import { cn } from '@/lib/utils';

const PAGE_SIZE = 25;

export type PickerTemplateStatus = 'DRAFT' | 'SUBMITTED' | 'PUBLISHED';

export interface TemplateItem {
    id: string;
    title: string;
    category?: string | null;
    description?: string | null;
    status?: PickerTemplateStatus;
}

const STATUS_PILL: Record<PickerTemplateStatus, { label: string; cls: string }> = {
    DRAFT:     { label: 'Draft',     cls: 'bg-slate-500/15 text-slate-300 border-slate-500/30' },
    SUBMITTED: { label: 'Submitted', cls: 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30' },
    PUBLISHED: { label: 'Published', cls: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' },
};

interface TemplatePickerDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    templates: TemplateItem[];
    isLoading?: boolean;
    onSelect: (templateId: string) => void;
    title?: string;
    description?: string;
}

export function TemplatePickerDialog({
    open,
    onOpenChange,
    templates,
    isLoading = false,
    onSelect,
    title = 'Select Template',
    description = 'Search and select a template to apply.',
}: TemplatePickerDialogProps) {
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(0);
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [includeNonPublished, setIncludeNonPublished] = useState(false);

    // Status data is only meaningful if at least one item has a status field set —
    // otherwise we're being given items from a resource that doesn't track workflow yet.
    const hasStatusData = useMemo(() => templates.some(t => !!t.status), [templates]);
    const nonPublishedCount = useMemo(
        () => templates.filter(t => t.status && t.status !== 'PUBLISHED').length,
        [templates],
    );

    // Apply the status gate first so all derived data (categories, counts) reflects
    // what the user actually sees.
    const statusGated = useMemo(() => {
        if (!hasStatusData) return templates;
        if (includeNonPublished) return templates;
        return templates.filter(t => !t.status || t.status === 'PUBLISHED');
    }, [templates, hasStatusData, includeNonPublished]);

    // Derive unique categories from the status-gated set
    const categories = useMemo(() => {
        const cats = new Set<string>();
        for (const t of statusGated) {
            if (t.category) cats.add(t.category);
        }
        return Array.from(cats).sort();
    }, [statusGated]);

    // Filter templates by category and search query
    const filtered = useMemo(() => {
        let result = statusGated;
        if (selectedCategory) {
            result = result.filter(t => t.category === selectedCategory);
        }
        if (search.trim()) {
            const q = search.toLowerCase();
            result = result.filter(
                (t) =>
                    t.title.toLowerCase().includes(q) ||
                    t.category?.toLowerCase().includes(q) ||
                    t.description?.toLowerCase().includes(q)
            );
        }
        return result;
    }, [statusGated, search, selectedCategory]);

    // Pagination
    const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
    const needsPaging = filtered.length > PAGE_SIZE;
    const paged = needsPaging ? filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE) : filtered;

    // Group the current page by category
    const grouped = useMemo(() => {
        const groups: Record<string, TemplateItem[]> = {};
        for (const t of paged) {
            const cat = t.category || 'Uncategorized';
            if (!groups[cat]) groups[cat] = [];
            groups[cat].push(t);
        }
        return groups;
    }, [paged]);

    const handleSelect = (templateId: string) => {
        onSelect(templateId);
        onOpenChange(false);
        setSearch('');
        setPage(0);
    };

    // Reset search, page, and category when dialog closes
    const handleOpenChange = (isOpen: boolean) => {
        if (!isOpen) {
            setSearch('');
            setPage(0);
            setSelectedCategory(null);
            setIncludeNonPublished(false);
        }
        onOpenChange(isOpen);
    };

    // Reset page when search changes
    const handleSearchChange = (value: string) => {
        setSearch(value);
        setPage(0);
    };

    const handleCategoryChange = (cat: string | null) => {
        setSelectedCategory(cat);
        setPage(0);
    };

    // Strip HTML tags for plain-text preview
    const stripHtml = (html: string) => {
        return html.replace(/<[^>]*>/g, '').trim();
    };

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[600px] p-0 gap-0 overflow-hidden max-h-[85vh] flex flex-col">
                <div className="p-6 pb-4 space-y-4 shrink-0">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-lg">
                            <BookOpen className="h-5 w-5 text-indigo-400" />
                            {title}
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">
                            {description}
                        </DialogDescription>
                    </DialogHeader>

                    {/* Search input */}
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                        <Input
                            placeholder="Search by title, category, or description..."
                            className="pl-10 h-10 bg-slate-950/50 border-slate-800 text-white rounded-lg focus:ring-primary/30 placeholder:text-slate-600"
                            value={search}
                            onChange={(e) => handleSearchChange(e.target.value)}
                            autoFocus
                        />
                    </div>

                    {/* Status visibility toggle — only shown when there are non-published items to reveal */}
                    {hasStatusData && nonPublishedCount > 0 && (
                        <label className="flex items-center justify-between gap-2 text-xs text-slate-400 select-none cursor-pointer">
                            <span className="flex items-center gap-2">
                                Include drafts &amp; submitted
                                <span className="text-[10px] text-slate-600">({nonPublishedCount})</span>
                            </span>
                            <Switch
                                checked={includeNonPublished}
                                onCheckedChange={(v) => { setIncludeNonPublished(v); setPage(0); }}
                            />
                        </label>
                    )}

                    {/* Category filter chips */}
                    {categories.length > 1 && (
                        <div className="flex flex-wrap gap-1.5">
                            <button
                                onClick={() => handleCategoryChange(null)}
                                className={cn(
                                    "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all duration-150",
                                    selectedCategory === null
                                        ? "bg-indigo-500/15 border-indigo-500/40 text-indigo-300"
                                        : "bg-slate-800/40 border-slate-700/50 text-slate-400 hover:bg-slate-800 hover:text-slate-300"
                                )}
                            >
                                All
                                <Badge variant="outline" className="text-[9px] h-3.5 px-1 ml-0.5 border-current/30">
                                    {templates.length}
                                </Badge>
                            </button>
                            {categories.map(cat => {
                                const count = templates.filter(t => t.category === cat).length;
                                return (
                                    <button
                                        key={cat}
                                        onClick={() => handleCategoryChange(selectedCategory === cat ? null : cat)}
                                        className={cn(
                                            "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all duration-150",
                                            selectedCategory === cat
                                                ? "bg-indigo-500/15 border-indigo-500/40 text-indigo-300"
                                                : "bg-slate-800/40 border-slate-700/50 text-slate-400 hover:bg-slate-800 hover:text-slate-300"
                                        )}
                                    >
                                        {cat.replace(/_/g, ' ')}
                                        <Badge variant="outline" className="text-[9px] h-3.5 px-1 ml-0.5 border-current/30">
                                            {count}
                                        </Badge>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Template list — scrollable area */}
                <div className="flex-1 overflow-y-auto min-h-0 px-6">
                    {isLoading ? (
                        <div className="flex flex-col items-center justify-center py-16">
                            <Loader2 className="h-6 w-6 animate-spin text-indigo-400 mb-2" />
                            <p className="text-slate-500 text-sm">Loading templates...</p>
                        </div>
                    ) : filtered.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16">
                            <FileText className="h-10 w-10 text-slate-700 mb-3" />
                            <p className="text-slate-400 font-medium">
                                {templates.length === 0 ? 'No templates available' : 'No templates match your filters'}
                            </p>
                            {search && (
                                <p className="text-slate-600 text-xs mt-1">
                                    Try a different search term
                                </p>
                            )}
                        </div>
                    ) : (
                        <div className="space-y-4 pb-2">
                            {Object.entries(grouped).map(([category, items]) => (
                                <div key={category}>
                                    {/* Category header */}
                                    <div className="flex items-center gap-2 mb-2 px-1">
                                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                                            {category.replace(/_/g, ' ')}
                                        </span>
                                        <div className="flex-1 h-px bg-slate-800/60" />
                                        <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-slate-800 text-slate-600">
                                            {items.length}
                                        </Badge>
                                    </div>

                                    {/* Template cards */}
                                    <div className="space-y-1.5">
                                        {items.map((t) => (
                                            <button
                                                key={t.id}
                                                onClick={() => handleSelect(t.id)}
                                                className={cn(
                                                    "w-full text-left p-3 rounded-lg border transition-all duration-150",
                                                    "bg-slate-950/30 border-slate-800/60",
                                                    "hover:bg-primary/90/5 hover:border-indigo-500/30 hover:shadow-[0_0_20px_rgba(99,102,241,0.05)]",
                                                    "focus:outline-hidden focus:ring-1 focus:ring-primary/40",
                                                    "group cursor-pointer"
                                                )}
                                            >
                                                <div className="flex items-start justify-between gap-3">
                                                    <div className="min-w-0 flex-1">
                                                        <div className="flex items-center gap-1.5 flex-wrap">
                                                            <h4 className="text-sm font-semibold text-slate-200 group-hover:text-white truncate">
                                                                {t.title}
                                                            </h4>
                                                            {t.status && t.status !== 'PUBLISHED' && (
                                                                <Badge
                                                                    variant="outline"
                                                                    className={cn('text-[9px] h-4 px-1.5 uppercase tracking-wider shrink-0', STATUS_PILL[t.status].cls)}
                                                                >
                                                                    {STATUS_PILL[t.status].label}
                                                                </Badge>
                                                            )}
                                                        </div>
                                                        {t.description && (
                                                            <p className="text-xs text-slate-500 mt-1 line-clamp-2 leading-relaxed group-hover:text-slate-400">
                                                                {stripHtml(t.description)}
                                                            </p>
                                                        )}
                                                    </div>
                                                    <Badge
                                                        variant="outline"
                                                        className="text-[9px] px-1.5 py-0 h-5 border-slate-700/60 text-slate-500 shrink-0 mt-0.5"
                                                    >
                                                        {(t.category || 'Other').replace(/_/g, ' ')}
                                                    </Badge>
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Footer with pagination and count */}
                {!isLoading && templates.length > 0 && (
                    <div className="px-6 py-3 border-t border-slate-800/60 shrink-0">
                        {needsPaging ? (
                            <div className="flex items-center justify-between">
                                <p className="text-[11px] text-slate-500">
                                    {filtered.length} template{filtered.length !== 1 ? 's' : ''}
                                    {search ? ' matching' : ' total'}
                                </p>
                                <div className="flex items-center gap-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => setPage(p => Math.max(0, p - 1))}
                                        disabled={page === 0}
                                        className="h-7 px-2 bg-slate-800/50 border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white disabled:opacity-30"
                                    >
                                        <ChevronLeft className="h-3.5 w-3.5" />
                                    </Button>
                                    <span className="text-[11px] text-slate-400 tabular-nums min-w-[60px] text-center">
                                        {page + 1} of {totalPages}
                                    </span>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                                        disabled={page >= totalPages - 1}
                                        className="h-7 px-2 bg-slate-800/50 border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white disabled:opacity-30"
                                    >
                                        <ChevronRight className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            </div>
                        ) : (
                            <p className="text-[10px] text-slate-600 text-center">
                                {filtered.length} of {templates.length} template{templates.length !== 1 ? 's' : ''}
                                {search ? ' matching' : ' available'}
                            </p>
                        )}
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

'use client';

import { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEngagementContext } from '@/stores/engagement-store';
import { useEngagements } from '@/lib/hooks/use-engagements';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
    CommandSeparator,
} from '@/components/ui/command';
import { Button } from '@/components/ui/button';
import { Briefcase, Check, ChevronsUpDown, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function EngagementSelector() {
    const pathname = usePathname();
    const router = useRouter();
    const searchParams = useSearchParams();
    const { selectedEngagementId, setSelectedEngagement } = useEngagementContext();
    const { data: engagements, isLoading } = useEngagements();
    const [open, setOpen] = useState(false);

    // Only show on dashboard, engagements, findings, assets, testcases and stats pages
    const isDashboard = pathname === '/dashboard';
    const isEngagements = pathname?.startsWith('/engagements');
    const isFindings = pathname?.startsWith('/findings');
    const isAssets = pathname?.startsWith('/assets');
    const isTestcases = pathname?.startsWith('/testcases');
    const isStats = pathname?.startsWith('/stats');
    const shouldShow = isDashboard || isEngagements || isFindings || isAssets || isTestcases || isStats;

    // Sync store with URL on mount or path change
    useEffect(() => {
        if (pathname?.startsWith('/engagements/')) {
            const id = pathname?.split('/')[2];
            if (id && id !== selectedEngagementId) {
                setSelectedEngagement(id);
            }
        } else if (pathname === '/engagements') {
            // When on the list page, the context should be 'global'
            if (selectedEngagementId !== 'global') {
                setSelectedEngagement('global');
            }
        }
    }, [pathname, selectedEngagementId, setSelectedEngagement]);

    // PLANNING, IN_PROGRESS, REPORTING — the three "still in flight" states
    // where the operator might want quick context-switching. COMPLETED /
    // ON_HOLD / PROPOSED are deliberately excluded so the list stays short;
    // those live on the full engagements list page.
    const activeEngagements = useMemo(
        () => engagements?.filter(
            (eng) => eng.status === 'IN_PROGRESS' || eng.status === 'PLANNING' || eng.status === 'REPORTING',
        ) ?? [],
        [engagements],
    );

    const selectedName = useMemo(() => {
        if (!selectedEngagementId || selectedEngagementId === 'global') return null;
        return engagements?.find(e => e.id === selectedEngagementId)?.name ?? null;
    }, [engagements, selectedEngagementId]);

    const handleValueChange = (value: string) => {
        const currentTab = searchParams?.get('tab');

        if (value === 'global') {
            setSelectedEngagement('global');
            if (isDashboard || isStats) {
                return;
            }
            if (pathname?.startsWith('/engagements/')) {
                router.push('/engagements');
            }
        } else {
            setSelectedEngagement(value);
            if (isDashboard || isStats) {
                return;
            }
            if (pathname?.startsWith('/engagements/')) {
                const tabQuery = currentTab ? `?tab=${currentTab}` : '';
                router.push(`/engagements/${value}${tabQuery}`);
            } else {
                router.push(`/engagements/${value}`);
            }
        }
    };

    if (!shouldShow || isLoading) {
        return null;
    }

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    className="w-[280px] justify-between bg-slate-900 border-slate-700 text-white font-normal hover:bg-slate-800 hover:text-white"
                >
                    <div className="flex items-center gap-2 min-w-0">
                        <Briefcase className="h-4 w-4 shrink-0" />
                        <span className="truncate">
                            {selectedName ?? 'Global (All Engagements)'}
                        </span>
                    </div>
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent
                className="w-[320px] p-0 bg-slate-900 border-slate-700"
                align="start"
            >
                <Command className="bg-slate-900">
                    <CommandInput placeholder="Search engagements…" className="text-white" />
                    <CommandList className="max-h-80">
                        <CommandEmpty>No engagement found.</CommandEmpty>
                        <CommandGroup>
                            <CommandItem
                                value="__global__ Global All Engagements"
                                onSelect={() => {
                                    handleValueChange('global');
                                    setOpen(false);
                                }}
                                className="text-slate-200"
                            >
                                <Check
                                    className={cn(
                                        'mr-2 h-3.5 w-3.5',
                                        (!selectedEngagementId || selectedEngagementId === 'global')
                                            ? 'opacity-100' : 'opacity-0',
                                    )}
                                />
                                <Globe className="h-3.5 w-3.5 text-slate-400 mr-1.5" />
                                <span>Global (All Engagements)</span>
                            </CommandItem>
                        </CommandGroup>
                        {activeEngagements.length > 0 && (
                            <>
                                <CommandSeparator />
                                <CommandGroup heading="Active Engagements">
                                    {activeEngagements.map(eng => (
                                        <CommandItem
                                            key={eng.id}
                                            value={`${eng.name} ${eng.client_name ?? ''}`}
                                            onSelect={() => {
                                                handleValueChange(eng.id);
                                                setOpen(false);
                                            }}
                                            className="text-slate-200"
                                        >
                                            <Check
                                                className={cn(
                                                    'mr-2 h-3.5 w-3.5',
                                                    selectedEngagementId === eng.id ? 'opacity-100' : 'opacity-0',
                                                )}
                                            />
                                            <Briefcase className="h-3 w-3 text-primary mr-1.5" />
                                            <span className="truncate flex-1">{eng.name}</span>
                                            {eng.client_name && (
                                                <span className="text-[10px] text-slate-500 ml-2 truncate">
                                                    {eng.client_name}
                                                </span>
                                            )}
                                        </CommandItem>
                                    ))}
                                </CommandGroup>
                            </>
                        )}
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
}

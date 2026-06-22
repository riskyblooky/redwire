'use client';

import { useEffect } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEngagementContext } from '@/stores/engagement-store';
import { useEngagements } from '@/lib/hooks/use-engagements';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Briefcase } from 'lucide-react';

export default function EngagementSelector() {
    const pathname = usePathname();
    const router = useRouter();
    const searchParams = useSearchParams();
    const { selectedEngagementId, setSelectedEngagement } = useEngagementContext();
    const { data: engagements, isLoading } = useEngagements();

    // Only show on dashboard, engagements, findings, assets, testcases and stats pages
    const isDashboard = pathname === '/dashboard';
    const isEngagements = pathname.startsWith('/engagements');
    const isFindings = pathname.startsWith('/findings');
    const isAssets = pathname.startsWith('/assets');
    const isTestcases = pathname.startsWith('/testcases');
    const isStats = pathname.startsWith('/stats');
    const shouldShow = isDashboard || isEngagements || isFindings || isAssets || isTestcases || isStats;

    // Sync store with URL on mount or path change
    useEffect(() => {
        if (pathname.startsWith('/engagements/')) {
            const id = pathname.split('/')[2];
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
    // ON_HOLD / PROPOSED are deliberately excluded so the dropdown stays
    // short; those live on the full engagements list page.
    const activeEngagements = engagements?.filter(
        (eng) => eng.status === 'IN_PROGRESS' || eng.status === 'PLANNING' || eng.status === 'REPORTING'
    ) || [];

    const handleValueChange = (value: string) => {
        const currentTab = searchParams.get('tab');

        if (value === 'global') {
            setSelectedEngagement('global');
            if (isDashboard || isStats) {
                // On dashboard/stats, just update store — no navigation
                return;
            }
            if (pathname.startsWith('/engagements/')) {
                router.push('/engagements');
            }
        } else {
            setSelectedEngagement(value);
            if (isDashboard || isStats) {
                // On dashboard/stats, just update store — no navigation
                return;
            }
            // If we're on an engagement detail page, navigate to the new one while preserving the tab
            if (pathname.startsWith('/engagements/')) {
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
        <Select
            value={selectedEngagementId || 'global'}
            onValueChange={handleValueChange}
        >
            <SelectTrigger className="w-[280px] bg-slate-900 border-slate-700 text-white">
                <div className="flex items-center gap-2">
                    <Briefcase className="h-4 w-4" />
                    <SelectValue placeholder="Select engagement" />
                </div>
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700">
                <SelectItem value="global" className="text-slate-300 hover:bg-slate-800 hover:text-white">
                    Global (All Engagements)
                </SelectItem>
                {activeEngagements.length > 0 && (
                    <>
                        <div className="px-2 py-1.5 text-xs font-semibold text-slate-500">Active Engagements</div>
                        {activeEngagements.map((engagement) => (
                            <SelectItem
                                key={engagement.id}
                                value={engagement.id}
                                className="text-slate-300 hover:bg-slate-800 hover:text-white"
                            >
                                {engagement.name}
                            </SelectItem>
                        ))}
                    </>
                )}
            </SelectContent>
        </Select>
    );
}

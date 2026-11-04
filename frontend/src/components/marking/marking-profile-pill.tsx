'use client';

import { Shield } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { MarkingProfile } from '@/lib/hooks/use-marking-profiles';
import { cn } from '@/lib/utils';

interface MarkingProfilePillProps {
    profile?: MarkingProfile;
    /** The engagement's default level abbreviation, highlighted in the hover list. */
    defaultLevel?: string | null;
    className?: string;
}

/** Compact marking-profile badge; hovering lists the profile's levels in their banner colors. */
export function MarkingProfilePill({ profile, defaultLevel, className }: MarkingProfilePillProps) {
    if (!profile) return <span className="text-slate-500">—</span>;
    const levels = [...profile.levels].sort((a, b) => a.rank - b.rank);
    return (
        <TooltipProvider delayDuration={150}>
            <Tooltip>
                <TooltipTrigger asChild>
                    <span
                        onClick={(e) => e.stopPropagation()}
                        className={cn(
                            'inline-flex max-w-[11rem] items-center gap-1 rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[11px] font-medium text-violet-300',
                            className,
                        )}
                    >
                        <Shield className="h-3 w-3 shrink-0" />
                        <span className="truncate">{profile.name}</span>
                    </span>
                </TooltipTrigger>
                <TooltipContent side="bottom" align="start" className="max-w-xs border border-slate-700 bg-slate-900 p-3 text-slate-200">
                    <div className="mb-2 text-xs font-semibold">{profile.name}</div>
                    {levels.length === 0 ? (
                        <div className="text-xs text-slate-500">No levels defined</div>
                    ) : (
                        <div className="flex flex-col gap-1">
                            {levels.map((l) => (
                                <div key={l.abbreviation} className="flex items-center gap-2 text-xs">
                                    <span
                                        className="min-w-[3.5rem] rounded px-1.5 py-0.5 text-center text-[10px] font-bold"
                                        style={{ backgroundColor: l.banner_color, color: l.text_color }}
                                    >
                                        {l.abbreviation}
                                    </span>
                                    <span className="text-slate-300">{l.full_name}</span>
                                    {defaultLevel === l.abbreviation && (
                                        <span className="ml-auto text-[10px] uppercase tracking-wide text-slate-500">default</span>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

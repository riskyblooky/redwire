'use client';

import { Shield } from 'lucide-react';
import { useEngagementMarkingProfile } from '@/lib/hooks/use-marking-profiles';

/**
 * Classification banner for an engagement page: the engagement's default
 * marking level in the level's banner colors, with the profile and ceiling.
 * Renders nothing when the engagement has no marking profile.
 */
interface MarkedEngagement {
    id: string;
    default_classification_level?: string | null;
    default_classification_suffix?: string | null;
    ceiling_classification_level?: string | null;
}

export function EngagementMarkingBanner({ engagement }: { engagement: MarkedEngagement }) {
    const profile = useEngagementMarkingProfile(engagement.id);
    if (!profile) return null;

    const level = profile.levels.find((l) => l.abbreviation === engagement.default_classification_level);
    const ceiling = profile.levels.find((l) => l.abbreviation === engagement.ceiling_classification_level);
    const suffix = engagement.default_classification_suffix?.trim();

    const details = [profile.name, ceiling && `Ceiling: ${ceiling.full_name}`].filter(Boolean).join(' · ');

    if (!level) {
        return (
            <div className="flex items-center justify-center gap-2 rounded-md border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs text-slate-300">
                <Shield className="h-3.5 w-3.5" />
                <span className="font-semibold">Marking: {profile.name}</span>
                <span className="text-slate-500">— no default level set{ceiling ? ` · Ceiling: ${ceiling.full_name}` : ''}</span>
            </div>
        );
    }

    return (
        <div
            className="relative flex items-center justify-center rounded-md px-3 py-1.5 text-center"
            style={{ backgroundColor: level.banner_color, color: level.text_color }}
            title={`Default marking for this engagement · ${details}`}
        >
            <span className="text-sm font-bold uppercase tracking-[0.2em]">
                {level.full_name}{suffix ? `//${suffix.replace(/^\/+/, '')}` : ''}
            </span>
            <span className="absolute right-3 hidden text-[11px] font-medium opacity-80 xl:inline">{details}</span>
        </div>
    );
}

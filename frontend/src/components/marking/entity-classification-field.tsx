'use client';

import { Label } from '@/components/ui/label';
import { ShieldAlert } from 'lucide-react';
import { useEngagement } from '@/lib/hooks/use-engagements';
import { useMarkingProfiles } from '@/lib/hooks/use-marking-profiles';
import { ClassificationPicker } from './classification-picker';

interface Props {
    engagementId?: string | null;
    level?: string | null;
    suffix?: string | null;
    onChange: (level: string | null, suffix: string | null) => void;
    /** What an unset level means for this entity. */
    inheritLabel?: string;
    label?: string;
}

/**
 * Self-contained per-entity classification control: resolves the engagement's
 * active marking profile (its profile → the default profile) and renders the
 * ladder picker. Renders nothing when no marking profile applies, so it's safe
 * to drop into any entity editor unconditionally.
 */
export function EntityClassificationField({
    engagementId,
    level,
    suffix,
    onChange,
    inheritLabel = 'Inherit',
    label = 'Classification',
}: Props) {
    const { data: engagement } = useEngagement(engagementId || '');
    const { data: profiles = [] } = useMarkingProfiles();

    // Only show when the engagement has its OWN marking profile selected —
    // no fallback to the default profile. No profile = no marking controls.
    const profile = engagement?.marking_profile_id
        ? profiles.find((p) => p.id === engagement.marking_profile_id)
        : undefined;

    if (!profile || profile.levels.length === 0) return null;

    return (
        <div className="space-y-1.5">
            {label ? (
                <Label className="text-slate-300 flex items-center gap-1.5">
                    <ShieldAlert className="h-3.5 w-3.5 text-red-400" /> {label}
                </Label>
            ) : null}
            <ClassificationPicker
                levels={profile.levels}
                level={level}
                suffix={suffix}
                onChange={onChange}
                inheritLabel={inheritLabel}
            />
            <p className="text-xs text-slate-500">
                Unset = inherit the report/engagement default. Profile: {profile.name}.
            </p>
        </div>
    );
}

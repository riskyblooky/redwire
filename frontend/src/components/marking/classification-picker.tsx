'use client';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { MarkingLevel } from '@/lib/hooks/use-marking-profiles';

const INHERIT = '_inherit';

interface Props {
    levels: MarkingLevel[];
    level?: string | null;
    suffix?: string | null;
    onChange: (level: string | null, suffix: string | null) => void;
    /** Label for the "no explicit level" option. */
    inheritLabel?: string;
    /** Show the free-text caveat suffix input (e.g. //SAR/123). */
    showSuffix?: boolean;
    disabled?: boolean;
    compact?: boolean;
}

/**
 * Picks a classification {level, suffix} against the active marking profile's
 * ladder. An unset level means "inherit" (report/engagement default).
 */
export function ClassificationPicker({
    levels,
    level,
    suffix,
    onChange,
    inheritLabel = 'Inherit (default)',
    showSuffix = true,
    disabled,
    compact,
}: Props) {
    const current = levels.find((l) => l.abbreviation === level);

    return (
        <div className={compact ? 'flex items-center gap-2' : 'flex flex-col gap-2 sm:flex-row sm:items-center'}>
            <Select
                value={level || INHERIT}
                onValueChange={(v) => onChange(v === INHERIT ? null : v, v === INHERIT ? null : (suffix || null))}
                disabled={disabled}
            >
                <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white h-9 min-w-[12rem]">
                    <SelectValue>
                        {current ? (
                            <span className="flex items-center gap-2">
                                <span
                                    className="inline-block w-3 h-3 rounded-sm border border-slate-700"
                                    style={{ backgroundColor: current.banner_color }}
                                />
                                {current.abbreviation} — {current.full_name}
                            </span>
                        ) : (
                            inheritLabel
                        )}
                    </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                    <SelectItem value={INHERIT} className="focus:bg-red-500/20 focus:text-red-400">
                        {inheritLabel}
                    </SelectItem>
                    {levels.map((l) => (
                        <SelectItem key={l.abbreviation} value={l.abbreviation} className="focus:bg-red-500/20 focus:text-red-400">
                            <span className="flex items-center gap-2">
                                <span
                                    className="inline-block w-3 h-3 rounded-sm border border-slate-700"
                                    style={{ backgroundColor: l.banner_color }}
                                />
                                {l.abbreviation} — {l.full_name}
                            </span>
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>

            {showSuffix && level && (
                <Input
                    value={suffix || ''}
                    onChange={(e) => onChange(level, e.target.value || null)}
                    placeholder="caveat e.g. //SAR/123"
                    disabled={disabled}
                    className="bg-slate-950/50 border-slate-800 text-white h-9 max-w-[14rem]"
                />
            )}
        </div>
    );
}

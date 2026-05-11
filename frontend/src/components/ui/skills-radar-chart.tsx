'use client';

import { useMemo } from 'react';
import {
    RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
    Radar, ResponsiveContainer, Legend, Tooltip,
} from 'recharts';

export interface SkillDataPoint {
    skill: string;
    color?: string;
    fullMark: number;
    /** Tooltip details for drill-down */
    details?: { name: string; value: number }[];
    [seriesKey: string]: any;
}

interface SeriesConfig {
    key: string;
    label: string;
    color: string;
    fillOpacity?: number;
    strokeDasharray?: string;
}

interface SkillsRadarChartProps {
    data: SkillDataPoint[];
    series: SeriesConfig[];
    height?: number;
    hideLegend?: boolean;
    /** Map from skill label → category color, used to tint axis labels */
    labelColors?: Record<string, string>;
}

const LEVEL_LABELS: Record<number, string> = {
    0: 'None',
    1: 'Beginner',
    2: 'Intermediate',
    3: 'Advanced',
};

const LEVEL_COLORS: Record<number, string> = {
    0: '#64748b',  // slate
    1: '#60a5fa',  // blue
    2: '#fbbf24',  // amber
    3: '#34d399',  // emerald
};

function getLevelInfo(val: number): { label: string; color: string } {
    const rounded = Math.round(val);
    const clamped = Math.max(0, Math.min(3, rounded));
    return {
        label: LEVEL_LABELS[clamped] || 'None',
        color: LEVEL_COLORS[clamped] || LEVEL_COLORS[0],
    };
}

function CustomTooltip({ active, payload, label }: any) {
    if (!active || !payload?.length) return null;

    const point = payload[0]?.payload;

    return (
        <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-xl p-3 min-w-[200px]">
            <p className="text-sm font-semibold text-white mb-2" style={{ color: point?.color }}>
                {label}
            </p>
            {payload.map((entry: any) => {
                const val = typeof entry.value === 'number' ? entry.value : 0;
                const info = getLevelInfo(val);
                const isFloat = val !== Math.round(val);
                return (
                    <div key={entry.dataKey} className="flex items-center justify-between gap-4 py-0.5">
                        <div className="flex items-center gap-1.5">
                            <div
                                className="w-2 h-2 rounded-full"
                                style={{ backgroundColor: entry.color }}
                            />
                            <span className="text-xs text-slate-400">{entry.name}</span>
                        </div>
                        <span
                            className="text-xs font-medium px-1.5 py-0.5 rounded"
                            style={{
                                color: info.color,
                                backgroundColor: `${info.color}15`,
                            }}
                        >
                            {info.label}{isFloat ? ` (${val.toFixed(1)})` : ''}
                        </span>
                    </div>
                );
            })}
            {point?.details && point.details.length > 0 && (
                <>
                    <div className="border-t border-slate-700/50 my-1.5" />
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-1">Skills</p>
                    {point.details.map((d: any) => {
                        const info = getLevelInfo(d.value);
                        return (
                            <div key={d.name} className="flex items-center justify-between gap-4 py-0.5">
                                <span className="text-[11px] text-slate-400 truncate">{d.name}</span>
                                <span
                                    className="text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0"
                                    style={{
                                        color: info.color,
                                        backgroundColor: `${info.color}15`,
                                    }}
                                >
                                    {info.label}
                                </span>
                            </div>
                        );
                    })}
                </>
            )}
        </div>
    );
}


function CustomAxisTick({ x, y, payload, labelColors }: any) {
    const color = labelColors?.[payload?.value] || '#94a3b8';
    return (
        <text
            x={x}
            y={y}
            fill={color}
            fontSize={11}
            fontWeight={500}
            textAnchor="middle"
            dominantBaseline="central"
        >
            {payload?.value}
        </text>
    );
}


export function SkillsRadarChart({ data, series, height = 300, hideLegend = false, labelColors }: SkillsRadarChartProps) {
    if (!data.length) return null;

    return (
        <ResponsiveContainer width="100%" height={height}>
            <RadarChart cx="50%" cy="50%" outerRadius="65%" data={data}>
                <PolarGrid stroke="#334155" strokeOpacity={0.5} />
                <PolarAngleAxis
                    dataKey="skill"
                    tick={<CustomAxisTick labelColors={labelColors} />}
                    tickLine={false}
                />
                <PolarRadiusAxis
                    angle={90}
                    domain={[0, 3]}
                    tickCount={4}
                    tick={{ fill: '#475569', fontSize: 9 }}
                    axisLine={false}
                />
                {series.map((s) => (
                    <Radar
                        key={s.key}
                        name={s.label}
                        dataKey={s.key}
                        stroke={s.color}
                        fill={s.color}
                        fillOpacity={s.fillOpacity ?? 0.15}
                        strokeWidth={2}
                        strokeDasharray={s.strokeDasharray}
                        dot={{ r: 3, fill: s.color, strokeWidth: 0 }}
                        activeDot={{ r: 5, fill: s.color, stroke: '#fff', strokeWidth: 1 }}
                    />
                ))}
                <Tooltip content={<CustomTooltip />} />
                {series.length > 1 && !hideLegend && (
                    <Legend
                        wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
                    />
                )}
            </RadarChart>
        </ResponsiveContainer>
    );
}


/**
 * Build radar data from user skills or engagement skills.
 * Groups by category and produces one data point per skill.
 */
export function buildRadarData(
    skills: { skill_id: string; skill_name: string; category_name: string; level?: number; min_level?: number }[],
    seriesKey: string = 'level',
): SkillDataPoint[] {
    return skills.map((s) => ({
        skill: s.skill_name,
        fullMark: 3,
        [seriesKey]: (s as any)[seriesKey] ?? (s as any).level ?? (s as any).min_level ?? 0,
    }));
}


/**
 * Build category-grouped radar data.
 * Returns one point per category with avgLevel computed.
 */
export function buildCategoryRadarData(
    categories: { name: string; color: string | null; skills: { id: string; name: string }[] }[],
    userLevels: Record<string, number>,
    averageLevels?: Record<string, number>,
    targetLevels?: Record<string, number | null | undefined>,
): { data: SkillDataPoint[]; labelColors: Record<string, string> } {
    const labelColors: Record<string, string> = {};

    const data = categories.map((cat) => {
        const color = cat.color || '#6366f1';
        labelColors[cat.name] = color;

        // Compute average level in this category (only count non-zero)
        const skillLevels = cat.skills.map((s) => userLevels[s.id] ?? 0);
        const nonZero = skillLevels.filter(l => l > 0);
        const avgLevel = nonZero.length > 0 ? nonZero.reduce((a, b) => a + b, 0) / nonZero.length : 0;

        // Compute team average for this category
        let teamAvg = 0;
        if (averageLevels) {
            const teamLevels = cat.skills.map((s) => averageLevels[s.id] ?? 0).filter(l => l > 0);
            teamAvg = teamLevels.length > 0 ? teamLevels.reduce((a, b) => a + b, 0) / teamLevels.length : 0;
        }

        // Compute growth-goal average. For each skill, use the target level
        // if set, otherwise the current level — so the target line shows the
        // projected category level if all growth goals are achieved.
        let targetAvg = avgLevel;
        let hasAnyTarget = false;
        if (targetLevels) {
            const projected = cat.skills.map((s) => {
                const t = targetLevels[s.id];
                if (t != null) hasAnyTarget = true;
                return t != null ? t : (userLevels[s.id] ?? 0);
            });
            const projectedNonZero = projected.filter(l => l > 0);
            targetAvg = projectedNonZero.length > 0
                ? projectedNonZero.reduce((a, b) => a + b, 0) / projectedNonZero.length
                : 0;
        }

        // Build details for tooltip
        const details = cat.skills
            .map((s) => ({ name: s.name, value: userLevels[s.id] ?? 0 }))
            .sort((a, b) => b.value - a.value);

        return {
            skill: cat.name,
            color,
            level: Math.round(avgLevel * 100) / 100,
            average: Math.round(teamAvg * 100) / 100,
            target: Math.round(targetAvg * 100) / 100,
            hasAnyTarget,
            fullMark: 3,
            details,
        };
    });

    return { data, labelColors };
}


/**
 * Merge two datasets for overlaid radar (e.g., required vs actual).
 * Both arrays must have the same skill ordering.
 */
export function mergeRadarData(
    base: SkillDataPoint[],
    overlay: SkillDataPoint[],
    overlayKey: string,
): SkillDataPoint[] {
    return base.map((point, idx) => ({
        ...point,
        [overlayKey]: overlay[idx]?.[overlayKey] ?? 0,
    }));
}

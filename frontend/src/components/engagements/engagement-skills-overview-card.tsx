/**
 * engagement-skills-overview-card.tsx — Required Skills Radar Card
 *
 * Renders a radar chart showing the minimum skill levels required for
 * the engagement, alongside a legend listing each skill with its
 * required proficiency badge. Uses the shared SkillsRadarChart component.
 * Returns null if no skills are configured for the engagement.
 */
'use client';

import { useEngagementSkills, SKILL_LEVELS } from '@/lib/hooks/use-skills';
import { SkillsRadarChart, buildRadarData } from '@/components/ui/skills-radar-chart';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Radar } from 'lucide-react';
import { cn } from '@/lib/utils';

export function EngagementSkillsOverviewCard({ engagementId }: { engagementId: string }) {
    const { data: engagementSkills = [] } = useEngagementSkills(engagementId);

    if (engagementSkills.length === 0) return null;

    const radarData = buildRadarData(engagementSkills, 'min_level');

    return (
        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
            <CardHeader className="pb-3 border-b border-slate-800/50">
                <CardTitle className="text-sm font-medium text-slate-400 flex items-center gap-2">
                    <Radar className="h-4 w-4" />
                    Required Skills
                </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
                <SkillsRadarChart
                    data={radarData}
                    series={[{ key: 'min_level', label: 'Required', color: '#ec4899' }]}
                    height={240}
                />
                <div className="space-y-1.5 mt-3">
                    {engagementSkills.map((es: any) => (
                        <div key={es.skill_id} className="flex items-center justify-between text-xs px-2">
                            <span className="text-slate-400">{es.skill_name}</span>
                            <Badge
                                variant="outline"
                                className={cn(
                                    'text-[10px] py-0',
                                    es.min_level === 1 ? 'border-blue-500/30 text-blue-400 bg-blue-500/10' :
                                    es.min_level === 2 ? 'border-amber-500/30 text-amber-400 bg-amber-500/10' :
                                    'border-emerald-500/30 text-emerald-400 bg-emerald-500/10'
                                )}
                            >
                                {SKILL_LEVELS.find(l => l.value === es.min_level)?.label}+
                            </Badge>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}

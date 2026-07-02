/**
 * attack-tab.tsx — MITRE ATT&CK heatmap + gap analysis tab.
 *
 * Rendered inside the engagement detail page. Shows:
 *  1. Interactive heatmap matrix (14 tactic columns)
 *  2. Gap analysis panel (untested techniques)
 *  3. Toolbar: Navigator export, AI auto-suggest, search, sub-technique toggle
 */

'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    Shield,
    Download,
    Sparkles,
    Search,
    Loader2,
    ExternalLink,
    BarChart3,
    Grid3X3,
    Bug,
    ChevronDown,
    ChevronRight,
    AlertTriangle,
    CheckCircle2,
    XCircle,
    TrendingUp,
    Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
    TACTICS,
    TECHNIQUES,
    TECHNIQUE_MAP,
    TACTIC_MAP,
    getBaseTechniquesByTactic,
    getSubTechniques,
    getTechniqueLabel,
    type AttackTechnique,
} from '@/lib/attack-data';
import {
    useAttackCoverage,
    useAiSuggestTechniques,
    useAttackNavigatorExport,
    type CoverageFinding,
    type CoverageTestCase,
} from '@/lib/hooks/use-attack';
import { useUpdateFinding } from '@/lib/hooks/use-findings';
import { CheckSquare } from 'lucide-react';
import { apiErrorMessage } from '@/lib/api';

export type AttackTabSource = 'finding' | 'testcase';

interface AttackTabProps {
    engagementId: string;
    /** Which resource type drives the heatmap. Defaults to 'finding'. */
    source?: AttackTabSource;
}

// Severity is only meaningful for findings — testcases get a flat tone.
type CoverageItem = CoverageFinding | CoverageTestCase;

// ── Severity colors for finding badges ────────────────────────────────
const severityColors: Record<string, string> = {
    CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/30',
    HIGH: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    MEDIUM: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    LOW: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    INFO: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

// ── Intensity colors for heatmap cells ────────────────────────────────
function getCellColor(count: number, maxSeverity?: string): string {
    if (count === 0) return 'bg-slate-900/30 border-slate-800/40';
    if (maxSeverity === 'CRITICAL') return 'bg-red-500/25 border-red-500/40 hover:bg-red-500/35';
    if (maxSeverity === 'HIGH') return 'bg-orange-500/20 border-orange-500/35 hover:bg-orange-500/30';
    if (maxSeverity === 'MEDIUM') return 'bg-amber-500/15 border-amber-500/30 hover:bg-amber-500/25';
    if (maxSeverity === 'LOW') return 'bg-blue-500/15 border-blue-500/30 hover:bg-blue-500/25';
    return 'bg-emerald-500/15 border-emerald-500/30 hover:bg-emerald-500/25';
}

function getMaxSeverity(findings: CoverageFinding[]): string | undefined {
    const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
    for (const s of order) {
        if (findings.some(f => f.severity === s)) return s;
    }
    return undefined;
}

// Testcase-flavoured cell tone — green if any pass, red if any fail, amber if untested.
function getTestcaseCellTone(items: CoverageTestCase[]): string | undefined {
    if (items.length === 0) return undefined;
    if (items.some(tc => tc.is_executed && tc.is_successful)) return 'LOW'; // blue-ish
    if (items.some(tc => tc.is_executed && tc.is_successful === false)) return 'HIGH'; // orange-ish
    return 'MEDIUM'; // pending
}

// ── Component ─────────────────────────────────────────────────────────

export function AttackTab({ engagementId, source = 'finding' }: AttackTabProps) {
    const { data: coverage, isLoading } = useAttackCoverage(engagementId);
    const navigatorExport = useAttackNavigatorExport(engagementId);
    const aiSuggest = useAiSuggestTechniques(engagementId);
    const updateFinding = useUpdateFinding();

    const isTestcaseSource = source === 'testcase';
    const itemNoun = isTestcaseSource ? 'test case' : 'finding';
    const itemNounPlural = isTestcaseSource ? 'test cases' : 'findings';

    const [search, setSearch] = useState('');
    const [showSubTechniques, setShowSubTechniques] = useState(false);
    const [view, setView] = useState<'matrix' | 'gaps'>('matrix');
    const [selectedTechId, setSelectedTechId] = useState<string | null>(null);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [aiElapsed, setAiElapsed] = useState(0);
    const [appliedFindingIds, setAppliedFindingIds] = useState<Set<string>>(new Set());
    const [mappedOnly, setMappedOnly] = useState(true);

    // Elapsed timer for AI suggest
    useEffect(() => {
        if (!aiSuggest.isPending) {
            setAiElapsed(0);
            return;
        }
        const interval = setInterval(() => setAiElapsed(s => s + 1), 1000);
        return () => clearInterval(interval);
    }, [aiSuggest.isPending]);

    // Coverage map for quick lookup — switches between findings/testcases
    // depending on the active sub-tab source.
    const coverageMap = useMemo(() => {
        if (!coverage) return new Map<string, CoverageItem[]>();
        const raw = isTestcaseSource ? coverage.testcases_by_technique : coverage.findings_by_technique;
        return new Map<string, CoverageItem[]>(Object.entries(raw || {}));
    }, [coverage, isTestcaseSource]);

    // Search filter
    const searchLower = search.toLowerCase().trim();

    // Stats
    const stats = useMemo(() => {
        if (!coverage) return { mapped: 0, total: 0, pct: 0, unmapped: 0, totalItems: 0, mappedItems: 0, unmappedItems: 0 };
        const baseTechs = TECHNIQUES.filter(t => !t.isSubtechnique);
        const mapped = baseTechs.filter(t => coverageMap.has(t.id) || getSubTechniques(t.id).some(st => coverageMap.has(st.id))).length;
        return {
            mapped,
            total: baseTechs.length,
            pct: Math.round((mapped / baseTechs.length) * 100),
            unmapped: baseTechs.length - mapped,
            totalItems: isTestcaseSource ? coverage.total_testcases : coverage.total_findings,
            mappedItems: isTestcaseSource ? coverage.mapped_testcases : coverage.mapped_findings,
            unmappedItems: isTestcaseSource ? coverage.unmapped_testcases : coverage.unmapped_findings,
        };
    }, [coverage, coverageMap, isTestcaseSource]);

    // Handle Navigator export
    const handleExport = useCallback(async () => {
        try {
            await navigatorExport.mutateAsync();
            toast.success('ATT&CK Navigator layer downloaded');
        } catch (err) {
            toast.error('Failed to export Navigator layer');
        }
    }, [navigatorExport]);

    // Handle AI suggestions
    const handleAiSuggest = useCallback(async () => {
        // Fresh run — clear any "Applied" markers from a previous batch
        setAppliedFindingIds(new Set());
        try {
            const result = await aiSuggest.mutateAsync(undefined);
            if (result.message) {
                toast.info(result.message);
                return;
            }
            // Prefer the backend-supplied counts; fall back to deriving from suggestions
            const total = result.suggestions.length;
            const succeeded = result.succeeded ?? result.suggestions.filter(s => s.techniques.length > 0).length;
            const failed = result.failed ?? result.suggestions.filter(s => !!s.error).length;
            const firstError = result.first_error ?? result.suggestions.find(s => s.error)?.error ?? null;

            // Show panel whenever we have at least one usable suggestion
            if (succeeded > 0) setShowSuggestions(true);

            if (succeeded === total) {
                toast.success(`Generated suggestions for ${total} findings`);
            } else if (succeeded > 0) {
                toast.warning(
                    `${succeeded} of ${total} succeeded`,
                    { description: firstError ? `Failures: ${firstError}` : undefined },
                );
            } else if (failed > 0) {
                toast.error(
                    `All ${total} suggestions failed`,
                    { description: firstError || 'See backend logs for details' },
                );
            } else {
                // total === 0 (no findings) — already covered by result.message above, but fallback:
                toast.info('No findings to process');
            }
        } catch (err: any) {
            const msg = apiErrorMessage(err, 'Failed to get AI suggestions');
            toast.error(msg);
        }
    }, [aiSuggest]);

    // Apply a single AI suggestion
    const handleApplySuggestion = useCallback(async (findingId: string, techniqueIds: string[]) => {
        try {
            await updateFinding.mutateAsync({
                id: findingId,
                attack_technique_ids: techniqueIds,
            });
            setAppliedFindingIds(prev => {
                const next = new Set(prev);
                next.add(findingId);
                return next;
            });
            toast.success('Techniques applied to finding');
        } catch {
            toast.error('Failed to apply techniques');
        }
    }, [updateFinding]);

    if (isLoading) {
        return (
            <div className="flex h-64 items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* ── Stats Bar ────────────────────────────────────── */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Card className="border-slate-800 bg-slate-900/40">
                    <CardContent className="p-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
                                <Shield className="h-5 w-5 text-primary" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-white">{stats.pct}%</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Coverage</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-800 bg-slate-900/40">
                    <CardContent className="p-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                                <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-white">{stats.mapped}</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Techniques Tested</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-800 bg-slate-900/40">
                    <CardContent className="p-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                                <XCircle className="h-5 w-5 text-red-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-white">{stats.unmapped}</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Gaps</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-800 bg-slate-900/40">
                    <CardContent className="p-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
                                {isTestcaseSource
                                    ? <CheckSquare className="h-5 w-5 text-blue-400" />
                                    : <Bug className="h-5 w-5 text-blue-400" />}
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-white">{stats.mappedItems}</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">
                                    Mapped {itemNounPlural}
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-800 bg-slate-900/40">
                    <CardContent className="p-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
                                <AlertTriangle className="h-5 w-5 text-amber-400" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-white">{stats.unmappedItems}</p>
                                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">
                                    Unmapped {itemNounPlural}
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* ── Toolbar ──────────────────────────────────────── */}
            <div className="flex items-center gap-3 flex-wrap">
                {/* View toggle */}
                <div className="flex items-center bg-slate-900/60 border border-slate-800 rounded-lg p-0.5">
                    <Button
                        variant="ghost"
                        size="sm"
                        className={cn(
                            'h-8 px-3 rounded-md text-xs',
                            view === 'matrix' ? 'bg-primary/15 text-primary' : 'text-slate-500'
                        )}
                        onClick={() => setView('matrix')}
                    >
                        <Grid3X3 className="h-3.5 w-3.5 mr-1.5" />
                        Matrix
                    </Button>
                    <Button
                        variant="ghost"
                        size="sm"
                        className={cn(
                            'h-8 px-3 rounded-md text-xs',
                            view === 'gaps' ? 'bg-primary/15 text-primary' : 'text-slate-500'
                        )}
                        onClick={() => setView('gaps')}
                    >
                        <BarChart3 className="h-3.5 w-3.5 mr-1.5" />
                        Gap Analysis
                    </Button>
                </div>

                {/* Search */}
                <div className="relative flex-1 min-w-[200px] max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                    <Input
                        placeholder="Filter techniques…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="pl-9 h-8 bg-slate-950/50 border-slate-800 text-sm"
                    />
                </div>

                {/* Mapped-only toggle */}
                <div className="flex items-center gap-2">
                    <Switch
                        id="mapped-only"
                        checked={mappedOnly}
                        onCheckedChange={setMappedOnly}
                        className="data-[state=checked]:bg-primary"
                    />
                    <Label htmlFor="mapped-only" className="text-xs text-slate-400 cursor-pointer">
                        Mapped only
                    </Label>
                </div>

                {/* Sub-techniques toggle */}
                <div className="flex items-center gap-2">
                    <Switch
                        id="sub-techniques"
                        checked={showSubTechniques}
                        onCheckedChange={setShowSubTechniques}
                        className="data-[state=checked]:bg-primary"
                    />
                    <Label htmlFor="sub-techniques" className="text-xs text-slate-400 cursor-pointer">
                        Sub-techniques
                    </Label>
                </div>

                <Separator orientation="vertical" className="h-6 bg-slate-800" />

                {/* Actions */}
                <Button
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs border-slate-700 bg-slate-900/50 hover:bg-slate-800 text-slate-300"
                    onClick={handleExport}
                    disabled={navigatorExport.isPending}
                >
                    {navigatorExport.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Download className="h-3.5 w-3.5 mr-1.5" />}
                    Navigator Export
                </Button>
                {!isTestcaseSource && (
                    <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs border-primary/40 bg-primary/10 hover:bg-primary/20 text-primary"
                        onClick={handleAiSuggest}
                        disabled={aiSuggest.isPending}
                    >
                        {aiSuggest.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 mr-1.5" />}
                        {aiSuggest.isPending
                            ? `AI Analyzing… ${Math.floor(aiElapsed / 60)}:${String(aiElapsed % 60).padStart(2, '0')}`
                            : 'AI Auto-Suggest'}
                    </Button>
                )}
            </div>

            {/* ── AI Suggestions Panel (findings only) ─────────── */}
            {!isTestcaseSource && showSuggestions && aiSuggest.data && aiSuggest.data.suggestions.length > 0 && (
                <Card className="border-primary/30 bg-primary/5">
                    <CardHeader className="p-4 pb-2">
                        <div className="flex items-center justify-between">
                            <CardTitle className="text-sm font-bold text-primary flex items-center gap-2">
                                <Sparkles className="h-4 w-4" />
                                AI Technique Suggestions
                            </CardTitle>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 text-xs text-slate-500"
                                onClick={() => setShowSuggestions(false)}
                            >
                                Dismiss
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent className="p-4 pt-2 space-y-3">
                        {aiSuggest.data.suggestions.map(suggestion => {
                            const isApplied = appliedFindingIds.has(suggestion.finding_id);
                            return (
                            <div
                                key={suggestion.finding_id}
                                className={cn(
                                    "rounded-lg p-3 border transition-colors",
                                    isApplied
                                        ? "bg-emerald-950/20 border-emerald-500/30"
                                        : "bg-slate-900/50 border-slate-800/50",
                                )}
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-semibold text-white">{suggestion.finding_title}</span>
                                    {suggestion.techniques.length > 0 && (
                                        isApplied ? (
                                            <Badge className="h-6 text-[10px] bg-emerald-500/15 text-emerald-300 border-emerald-500/30 gap-1">
                                                <CheckCircle2 className="h-3 w-3" />
                                                Applied
                                            </Badge>
                                        ) : (
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-6 text-[10px] border-primary/30 text-primary hover:bg-primary/10"
                                                onClick={() => handleApplySuggestion(
                                                    suggestion.finding_id,
                                                    suggestion.techniques.map(t => t.technique_id)
                                                )}
                                            >
                                                Apply All
                                            </Button>
                                        )
                                    )}
                                </div>
                                {suggestion.error ? (
                                    <span className="text-xs text-red-400">{suggestion.error}</span>
                                ) : (
                                    <div className="flex flex-wrap gap-1.5">
                                        {suggestion.techniques.map(tech => (
                                            <TooltipProvider key={tech.technique_id} delayDuration={200}>
                                                <Tooltip>
                                                    <TooltipTrigger asChild>
                                                        <Badge className="bg-purple-500/10 text-purple-400 border-purple-500/20 text-[10px] cursor-help">
                                                            {getTechniqueLabel(tech.technique_id)}
                                                        </Badge>
                                                    </TooltipTrigger>
                                                    <TooltipContent side="top" className="max-w-xs bg-slate-900 border-slate-700 text-xs">
                                                        {tech.reasoning}
                                                    </TooltipContent>
                                                </Tooltip>
                                            </TooltipProvider>
                                        ))}
                                    </div>
                                )}
                            </div>
                            );
                        })}
                    </CardContent>
                </Card>
            )}

            {/* ── Matrix View ──────────────────────────────────── */}
            {view === 'matrix' && mappedOnly && coverageMap.size === 0 && (
                <div className="rounded-lg border border-slate-800/60 bg-slate-950/30 p-12 text-center">
                    <p className="text-sm text-slate-400">
                        No {itemNounPlural} have been mapped to ATT&amp;CK techniques yet.
                    </p>
                    <Button
                        variant="outline"
                        size="sm"
                        className="mt-4 border-slate-700 text-slate-300 hover:bg-slate-800"
                        onClick={() => setMappedOnly(false)}
                    >
                        Show all tactics
                    </Button>
                </div>
            )}
            {view === 'matrix' && !(mappedOnly && coverageMap.size === 0) && (
                <div className="rounded-lg border border-slate-800/60 bg-slate-950/30 max-h-[calc(100vh-280px)] overflow-auto">
                    <div className="flex gap-1.5 min-w-[1200px] p-2">
                        {TACTICS.map(tactic => {
                            const baseTechs = getBaseTechniquesByTactic(tactic.id);
                            // Filter by search
                            let filteredTechs = searchLower
                                ? baseTechs.filter(t =>
                                    t.id.toLowerCase().includes(searchLower) ||
                                    t.name.toLowerCase().includes(searchLower) ||
                                    getSubTechniques(t.id).some(st =>
                                        st.id.toLowerCase().includes(searchLower) ||
                                        st.name.toLowerCase().includes(searchLower)
                                    )
                                )
                                : baseTechs;

                            // Filter by coverage when "Mapped only" is on
                            if (mappedOnly) {
                                filteredTechs = filteredTechs.filter(t =>
                                    coverageMap.has(t.id) ||
                                    getSubTechniques(t.id).some(st => coverageMap.has(st.id))
                                );
                            }

                            // Hide the entire tactic column when filters leave it empty
                            if (filteredTechs.length === 0 && (searchLower || mappedOnly)) return null;

                            return (
                                <div key={tactic.id} className="flex-1 min-w-[140px]">
                                    {/* Tactic header — sticks to the top of the scroll viewport */}
                                    <div className="sticky top-0 z-10 bg-primary/20 backdrop-blur-sm border border-primary/30 rounded-t-lg p-2 mb-1">
                                        <h3 className="text-[10px] font-bold uppercase tracking-wider text-primary text-center leading-tight">
                                            {tactic.name}
                                        </h3>
                                        <p className="text-[9px] text-primary/70 text-center mt-0.5">
                                            {filteredTechs.filter(t => coverageMap.has(t.id) || getSubTechniques(t.id).some(st => coverageMap.has(st.id))).length}/{filteredTechs.length}
                                        </p>
                                    </div>

                                    {/* Technique cells */}
                                    <div className="space-y-0.5">
                                        {filteredTechs.map(tech => {
                                            const items = coverageMap.get(tech.id) || [];
                                            const subTechs = getSubTechniques(tech.id);
                                            const subItems = subTechs.flatMap(st => coverageMap.get(st.id) || []);
                                            const allItems = [...items, ...subItems];
                                            const cellTone = isTestcaseSource
                                                ? getTestcaseCellTone(allItems as CoverageTestCase[])
                                                : getMaxSeverity(allItems as CoverageFinding[]);
                                            const hasSubCoverage = subTechs.some(st => coverageMap.has(st.id));

                                            return (
                                                <div key={tech.id}>
                                                    <TechniqueCell
                                                        technique={tech}
                                                        items={allItems}
                                                        toneSeverity={cellTone}
                                                        itemNoun={itemNoun}
                                                        isSelected={selectedTechId === tech.id}
                                                        onClick={() => setSelectedTechId(selectedTechId === tech.id ? null : tech.id)}
                                                        hasSubCoverage={hasSubCoverage}
                                                    />

                                                    {/* Sub-techniques */}
                                                    {showSubTechniques && subTechs.map(sub => {
                                                        if (searchLower && !sub.id.toLowerCase().includes(searchLower) && !sub.name.toLowerCase().includes(searchLower)) return null;
                                                        const subF = coverageMap.get(sub.id) || [];
                                                        const subTone = isTestcaseSource
                                                            ? getTestcaseCellTone(subF as CoverageTestCase[])
                                                            : getMaxSeverity(subF as CoverageFinding[]);
                                                        return (
                                                            <TechniqueCell
                                                                key={sub.id}
                                                                technique={sub}
                                                                items={subF}
                                                                toneSeverity={subTone}
                                                                itemNoun={itemNoun}
                                                                isSelected={selectedTechId === sub.id}
                                                                onClick={() => setSelectedTechId(selectedTechId === sub.id ? null : sub.id)}
                                                                isSub
                                                            />
                                                        );
                                                    })}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ── Technique detail popover ─────────────────────── */}
            {selectedTechId && (
                <TechniqueDetail
                    techniqueId={selectedTechId}
                    items={coverageMap.get(selectedTechId) || []}
                    source={source}
                    engagementId={engagementId}
                    onClose={() => setSelectedTechId(null)}
                />
            )}

            {/* ── Gap Analysis View ────────────────────────────── */}
            {view === 'gaps' && (
                <GapAnalysis
                    coverageMap={coverageMap}
                    search={searchLower}
                    showSubTechniques={showSubTechniques}
                />
            )}

            {/* ── Legend ────────────────────────────────────────── */}
            <div className="flex items-center gap-4 px-2">
                <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Legend:</span>
                <div className="flex items-center gap-1.5">
                    <div className="w-4 h-4 rounded bg-slate-900/30 border border-slate-800/40" />
                    <span className="text-[10px] text-slate-500">Untested</span>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-4 h-4 rounded bg-emerald-500/15 border border-emerald-500/30" />
                    <span className="text-[10px] text-slate-500">Info</span>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-4 h-4 rounded bg-blue-500/15 border border-blue-500/30" />
                    <span className="text-[10px] text-slate-500">Low</span>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-4 h-4 rounded bg-amber-500/15 border border-amber-500/30" />
                    <span className="text-[10px] text-slate-500">Medium</span>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-4 h-4 rounded bg-orange-500/20 border border-orange-500/35" />
                    <span className="text-[10px] text-slate-500">High</span>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-4 h-4 rounded bg-red-500/25 border border-red-500/40" />
                    <span className="text-[10px] text-slate-500">Critical</span>
                </div>
            </div>
        </div>
    );
}


// ── Technique Cell ────────────────────────────────────────────────────

function TechniqueCell({
    technique,
    items,
    toneSeverity,
    itemNoun,
    isSelected,
    onClick,
    isSub = false,
    hasSubCoverage = false,
}: {
    technique: AttackTechnique;
    items: CoverageItem[];
    toneSeverity?: string;
    itemNoun: string;
    isSelected: boolean;
    onClick: () => void;
    isSub?: boolean;
    hasSubCoverage?: boolean;
}) {
    const count = items.length;
    const maxSeverity = toneSeverity;

    return (
        <TooltipProvider delayDuration={300}>
            <Tooltip>
                <TooltipTrigger asChild>
                    <button
                        onClick={onClick}
                        className={cn(
                            'w-full text-left rounded border transition-all duration-200',
                            isSub ? 'ml-2 px-1.5 py-0.5' : 'px-2 py-1',
                            getCellColor(count, maxSeverity),
                            isSelected && 'ring-1 ring-primary/50',
                            count === 0 && 'opacity-60 hover:opacity-80',
                        )}
                    >
                        <div className="flex items-center gap-1">
                            <span className={cn(
                                'font-mono shrink-0',
                                isSub ? 'text-[8px]' : 'text-[9px]',
                                count > 0 ? 'text-white/70' : 'text-slate-600'
                            )}>
                                {technique.id}
                            </span>
                            {count > 0 && (
                                <span className={cn(
                                    'ml-auto font-bold flex items-center gap-0.5',
                                    isSub ? 'text-[8px]' : 'text-[9px]',
                                    maxSeverity === 'CRITICAL' ? 'text-red-400' :
                                    maxSeverity === 'HIGH' ? 'text-orange-400' :
                                    maxSeverity === 'MEDIUM' ? 'text-amber-400' :
                                    maxSeverity === 'LOW' ? 'text-blue-400' :
                                    'text-emerald-400'
                                )}>
                                    {count}
                                </span>
                            )}
                            {!isSub && hasSubCoverage && count === 0 && (
                                <span className="ml-auto text-[8px] text-emerald-500">●</span>
                            )}
                        </div>
                        <p className={cn(
                            'truncate',
                            isSub ? 'text-[8px]' : 'text-[9px]',
                            count > 0 ? 'text-white/80' : 'text-slate-500'
                        )}>
                            {technique.name}
                        </p>
                    </button>
                </TooltipTrigger>
                <TooltipContent
                    side="right"
                    className="bg-slate-900 border-slate-700 max-w-xs"
                >
                    <p className="text-xs font-bold text-white">{technique.id} — {technique.name}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                        Tactics: {technique.tacticIds.map(id => TACTIC_MAP.get(id)?.name).filter(Boolean).join(', ')}
                    </p>
                    {count > 0 && (
                        <p className="text-[10px] text-emerald-400 mt-1">
                            {count} {itemNoun}{count !== 1 ? 's' : ''} mapped
                        </p>
                    )}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}


// ── Technique Detail Panel ────────────────────────────────────────────

function TechniqueDetail({
    techniqueId,
    items,
    source,
    engagementId,
    onClose,
}: {
    techniqueId: string;
    items: CoverageItem[];
    source: AttackTabSource;
    engagementId: string;
    onClose: () => void;
}) {
    const tech = TECHNIQUE_MAP.get(techniqueId);
    if (!tech) return null;

    const isTestcase = source === 'testcase';
    const linkBase = isTestcase ? '/testcases' : '/findings';
    const itemNoun = isTestcase ? 'Test Case' : 'Finding';

    return (
        <Card className="border-primary/30 bg-slate-900/60">
            <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                        <Shield className="h-4 w-4 text-primary" />
                        {tech.id} — {tech.name}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                        <a
                            href={tech.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:text-primary/80 transition-colors"
                        >
                            <ExternalLink className="h-4 w-4" />
                        </a>
                        <Button variant="ghost" size="sm" className="h-6 text-xs text-slate-500" onClick={onClose}>
                            Close
                        </Button>
                    </div>
                </div>
                <p className="text-[10px] text-slate-500 mt-1">
                    Tactics: {tech.tacticIds.map(id => TACTIC_MAP.get(id)?.name).filter(Boolean).join(', ')}
                </p>
            </CardHeader>
            <CardContent className="p-4 pt-2">
                {items.length === 0 ? (
                    <p className="text-sm text-slate-500">No {itemNoun.toLowerCase()}s mapped to this technique.</p>
                ) : (
                    <div className="space-y-1.5">
                        <p className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-2">
                            {items.length} Linked {itemNoun}{items.length !== 1 ? 's' : ''}
                        </p>
                        {items.map(it => {
                            if (isTestcase) {
                                const tc = it as CoverageTestCase;
                                const passLabel = tc.is_executed
                                    ? (tc.is_successful ? 'Pass' : 'Fail')
                                    : 'Pending';
                                const passClass = tc.is_executed
                                    ? (tc.is_successful
                                        ? 'bg-green-500/10 text-green-400 border-green-500/30'
                                        : 'bg-red-500/10 text-red-400 border-red-500/30')
                                    : 'bg-slate-500/10 text-slate-400 border-slate-500/30';
                                return (
                                    <a
                                        key={tc.id}
                                        href={`${linkBase}/${tc.id}?engagementId=${engagementId}`}
                                        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-950/50 border border-slate-800/50 hover:border-primary/30 transition-colors group"
                                    >
                                        <CheckSquare className="h-3.5 w-3.5 text-slate-500 group-hover:text-primary shrink-0" />
                                        <span className="text-xs text-white truncate flex-1">{tc.title}</span>
                                        <Badge variant="outline" className={cn('text-[9px] px-1.5 h-4', passClass)}>
                                            {passLabel}
                                        </Badge>
                                    </a>
                                );
                            }
                            const f = it as CoverageFinding;
                            return (
                                <a
                                    key={f.id}
                                    href={`${linkBase}/${f.id}?engagementId=${engagementId}`}
                                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-950/50 border border-slate-800/50 hover:border-primary/30 transition-colors group"
                                >
                                    <Bug className="h-3.5 w-3.5 text-slate-500 group-hover:text-primary shrink-0" />
                                    <span className="text-xs text-white truncate flex-1">{f.title}</span>
                                    {f.severity && (
                                        <Badge className={cn('text-[9px] px-1.5 h-4', severityColors[f.severity] || '')}>
                                            {f.severity}
                                        </Badge>
                                    )}
                                </a>
                            );
                        })}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}


// ── Gap Analysis ──────────────────────────────────────────────────────

function GapAnalysis({
    coverageMap,
    search,
    showSubTechniques,
}: {
    coverageMap: Map<string, CoverageItem[]>;
    search: string;
    showSubTechniques: boolean;
}) {
    const [expandedTactics, setExpandedTactics] = useState<Set<string>>(new Set(TACTICS.map(t => t.id)));

    const toggleTactic = (id: string) => {
        setExpandedTactics(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    return (
        <div className="space-y-2">
            {TACTICS.map(tactic => {
                const techs = showSubTechniques
                    ? TECHNIQUES.filter(t => t.tacticIds.includes(tactic.id))
                    : getBaseTechniquesByTactic(tactic.id);

                // Only untested techniques
                const gaps = techs.filter(t => {
                    const hasCoverage = coverageMap.has(t.id);
                    if (hasCoverage) return false;
                    // For base techniques, also check if any sub-technique has coverage
                    if (!t.isSubtechnique && !showSubTechniques) {
                        const subs = getSubTechniques(t.id);
                        if (subs.some(s => coverageMap.has(s.id))) return false;
                    }
                    return true;
                });

                // Apply search filter
                const filtered = search
                    ? gaps.filter(t => t.id.toLowerCase().includes(search) || t.name.toLowerCase().includes(search))
                    : gaps;

                if (filtered.length === 0) return null;

                const isExpanded = expandedTactics.has(tactic.id);
                const totalInTactic = techs.length;
                const gapPct = Math.round((gaps.length / totalInTactic) * 100);

                return (
                    <Card key={tactic.id} className="border-slate-800 bg-slate-900/40">
                        <button
                            className="w-full flex items-center gap-3 p-3 hover:bg-slate-800/40 transition-colors rounded-t-xl"
                            onClick={() => toggleTactic(tactic.id)}
                        >
                            {isExpanded
                                ? <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />
                                : <ChevronRight className="h-4 w-4 text-slate-500 shrink-0" />
                            }
                            <span className="text-xs font-bold text-white">{tactic.name}</span>
                            <div className="flex items-center gap-2 ml-auto">
                                <Badge variant="secondary" className="bg-red-500/10 text-red-400 border-red-500/20 text-[10px]">
                                    {gaps.length} gaps
                                </Badge>
                                <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-emerald-500/60 rounded-full transition-all"
                                        style={{ width: `${100 - gapPct}%` }}
                                    />
                                </div>
                                <span className="text-[10px] text-slate-500 w-8 text-right">{100 - gapPct}%</span>
                            </div>
                        </button>

                        {isExpanded && (
                            <CardContent className="p-3 pt-0">
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-1.5">
                                    {filtered.map(tech => (
                                        <a
                                            key={tech.id}
                                            href={tech.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className={cn(
                                                'flex items-center gap-2 px-2.5 py-1.5 rounded-md border border-slate-800/40 bg-slate-950/30 hover:border-red-500/20 hover:bg-red-500/5 transition-colors group',
                                                tech.isSubtechnique && 'ml-4'
                                            )}
                                        >
                                            <XCircle className="h-3 w-3 text-red-500/50 group-hover:text-red-400 shrink-0" />
                                            <span className="font-mono text-[10px] text-slate-500 w-[70px] shrink-0">{tech.id}</span>
                                            <span className="text-[11px] text-slate-400 group-hover:text-slate-300 truncate">{tech.name}</span>
                                            <ExternalLink className="h-3 w-3 text-slate-700 group-hover:text-slate-500 ml-auto shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                                        </a>
                                    ))}
                                </div>
                            </CardContent>
                        )}
                    </Card>
                );
            })}
        </div>
    );
}

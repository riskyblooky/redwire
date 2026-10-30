'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Calculator, Check, Copy, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
    ScoreResult, ScoringMetric, useEvaluateScoring, useScoringModel,
} from '@/lib/hooks/use-scoring';

// Canonical severity palette (mirrors backend scoring/severity.py SEVERITY_COLORS).
const SEVERITY_HEX: Record<string, string> = {
    CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#eab308', LOW: '#60a5fa', INFO: '#94a3b8',
};
const severityHex = (sev?: string | null) => (sev && SEVERITY_HEX[sev]) || '#64748b';

export interface ScoringApplyResult {
    model_id: string;
    score: number | null;
    vector: string | null;
    severity: string;
    outcome: string | null;
    inputs: Record<string, unknown>;
}

interface ScoringCalculatorModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    modelId: string;
    initialInputs?: Record<string, unknown> | null;
    onApply: (result: ScoringApplyResult) => void;
    /** When provided, an in-modal model picker is shown (used by inline editing;
     *  the form pages supply their own external picker instead). */
    models?: { id: string; label: string }[];
    onModelChange?: (id: string) => void;
}

export function ScoringCalculatorModal({
    open, onOpenChange, modelId, initialInputs, onApply, models, onModelChange,
}: ScoringCalculatorModalProps) {
    const { data: model, isLoading } = useScoringModel(open ? modelId : null);
    const evaluate = useEvaluateScoring();
    const [inputs, setInputs] = useState<Record<string, unknown>>({});
    const [result, setResult] = useState<ScoreResult | null>(null);
    const [copied, setCopied] = useState(false);
    const seq = useRef(0);

    // Seed inputs when the modal opens (or the model changes).
    useEffect(() => {
        if (open) {
            setInputs(initialInputs && Object.keys(initialInputs).length ? { ...initialInputs } : {});
            setResult(null);
        }
    }, [open, modelId]); // eslint-disable-line react-hooks/exhaustive-deps

    const metrics = model?.metrics ?? [];
    const isComplete = useMemo(
        () => metrics.length > 0 && metrics.every((m) => inputs[m.id] !== undefined && inputs[m.id] !== ''),
        [metrics, inputs],
    );

    // Debounced live preview — one engine, server-side, so it matches the save.
    useEffect(() => {
        if (!open || !model || !isComplete) {
            setResult(null);
            return;
        }
        const mine = ++seq.current;
        const t = setTimeout(async () => {
            try {
                const r = await evaluate.mutateAsync({ modelId: model.id, inputs });
                if (mine === seq.current) setResult(r);
            } catch {
                if (mine === seq.current) setResult(null);
            }
        }, 200);
        return () => clearTimeout(t);
    }, [open, model, inputs, isComplete]); // eslint-disable-line react-hooks/exhaustive-deps

    const setValue = useCallback((metric: ScoringMetric, value: string) => {
        setInputs((prev) => ({
            ...prev,
            [metric.id]: metric.type === 'number' && value !== '' ? Number(value) : value,
        }));
    }, []);

    const color = severityHex(result?.severity);
    const scoreLabel = result
        // Categorical models' score is only a nominal sort key — show the outcome.
        ? (model?.score_kind !== 'categorical' && result.score !== null
            ? result.score.toFixed(1)
            : (result.outcome ? (model?.outcome_labels?.[result.outcome] ?? result.outcome) : '—'))
        : '—';

    const handleApply = () => {
        if (!result || !model) return;
        onApply({
            model_id: model.id, score: result.score, vector: result.vector,
            severity: result.severity, outcome: result.outcome, inputs,
        });
        onOpenChange(false);
    };

    const handleCopy = () => {
        if (result?.vector) {
            navigator.clipboard.writeText(result.vector);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        }
    };

    // Preserve metric order, grouped by `group`.
    const groups = useMemo(() => {
        const order: string[] = [];
        const byGroup: Record<string, ScoringMetric[]> = {};
        for (const m of metrics) {
            const g = m.group || '';
            if (!(g in byGroup)) { byGroup[g] = []; order.push(g); }
            byGroup[g].push(m);
        }
        return order.map((g) => ({ group: g, metrics: byGroup[g] }));
    }, [metrics]);

    const filled = metrics.filter((m) => inputs[m.id] !== undefined && inputs[m.id] !== '').length;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl max-h-[90vh] bg-slate-950 border-slate-800 text-white p-0 gap-0 overflow-hidden">
                <DialogHeader className="px-6 pt-5 pb-4 border-b border-slate-800/60">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-amber-500/10 rounded-lg">
                                <Calculator className="h-4 w-4 text-amber-500" />
                            </div>
                            <div>
                                <DialogTitle className="text-base font-semibold">
                                    {model?.label ?? 'Scoring Calculator'}
                                </DialogTitle>
                                {models && onModelChange ? (
                                    <Select value={modelId} onValueChange={onModelChange}>
                                        <SelectTrigger className="h-6 mt-1 bg-slate-900/60 border-slate-800 text-xs text-slate-300 w-[200px]">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {models.map((m) => (
                                                <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                ) : (
                                    <DialogDescription className="text-xs text-slate-500 mt-0.5">
                                        {model?.description ?? 'Select metrics to compute the rating'}
                                    </DialogDescription>
                                )}
                            </div>
                        </div>
                        <div className="text-right">
                            <div className="text-3xl font-black font-mono leading-none transition-all duration-300" style={{ color }}>
                                {scoreLabel}
                            </div>
                            <div className="text-[10px] font-bold uppercase tracking-widest mt-0.5 transition-all duration-300" style={{ color }}>
                                {result?.severity ?? 'Incomplete'}
                            </div>
                        </div>
                    </div>
                </DialogHeader>

                <ScrollArea className="flex-1 overflow-y-auto" style={{ maxHeight: 'calc(90vh - 180px)' }}>
                    <div className="px-6 py-4 space-y-4">
                        <div className="flex items-center gap-2">
                            <div className="h-1 flex-1 bg-slate-800 rounded-full overflow-hidden">
                                <div className="h-full rounded-full transition-all duration-300"
                                    style={{ width: `${metrics.length ? (filled / metrics.length) * 100 : 0}%`, backgroundColor: isComplete ? color : '#64748b' }} />
                            </div>
                            <span className="text-[10px] text-slate-500 font-mono">{filled}/{metrics.length || '—'}</span>
                        </div>

                        {isLoading && <div className="text-xs text-slate-500 py-8 text-center">Loading model…</div>}

                        <TooltipProvider delayDuration={200}>
                            <div className="space-y-4">
                                {groups.map(({ group, metrics: gm }, gi) => (
                                    <div key={group || gi} className="space-y-3">
                                        {group && (
                                            <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 px-1">{group}</div>
                                        )}
                                        {gm.map((m) => (
                                            <MetricRow key={m.id} metric={m} value={inputs[m.id]} onChange={setValue} />
                                        ))}
                                        {gi < groups.length - 1 && <Separator className="bg-slate-800/50" />}
                                    </div>
                                ))}
                            </div>
                        </TooltipProvider>

                        {result?.vector && (
                            <div className="bg-slate-900/50 border border-slate-800/60 rounded-lg px-3 py-2.5 flex items-center justify-between gap-2">
                                <code className="text-[10px] font-mono text-slate-400 break-all select-all">{result.vector}</code>
                                <Button variant="ghost" size="sm" className="h-6 w-6 p-0 shrink-0 text-slate-500 hover:text-white" onClick={handleCopy}>
                                    {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
                                </Button>
                            </div>
                        )}
                    </div>
                </ScrollArea>

                <div className="px-6 py-3 border-t border-slate-800/60 flex items-center justify-between bg-slate-950">
                    <Button variant="ghost" size="sm" onClick={() => { setInputs({}); setResult(null); }}
                        className="text-slate-500 hover:text-white h-8 text-xs">
                        <RotateCcw className="h-3 w-3 mr-1.5" /> Reset
                    </Button>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}
                            className="border-slate-800 text-slate-400 hover:text-white h-8 text-xs">Cancel</Button>
                        <Button size="sm" disabled={!result} onClick={handleApply} className="h-8 text-xs font-semibold"
                            style={{ backgroundColor: result ? color : undefined, borderColor: result ? color : undefined }}>
                            Apply Score
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}

// ─── Metric Row ──────────────────────────────────────────────────────────────

const segButton = (selected: boolean) =>
    cn(
        'flex-1 h-8 px-2 rounded-md text-[11px] font-bold transition-all duration-150 border',
        'focus:outline-hidden focus:ring-2 focus:ring-offset-1 focus:ring-offset-slate-950',
        selected
            ? 'bg-amber-500 border-amber-400 text-slate-950 shadow-[0_0_16px_rgba(245,158,11,0.35)]'
            : 'bg-slate-900/60 border-slate-800/60 text-slate-500 hover:text-slate-200 hover:bg-slate-800/80 hover:border-slate-600',
    );

function MetricRow({ metric, value, onChange }: {
    metric: ScoringMetric;
    value: unknown;
    onChange: (metric: ScoringMetric, value: string) => void;
}) {
    // Integer scales (DREAD 0-10, OWASP 0-9) render as a segmented button row.
    // Only fall back to a plain input for an unusually wide/open range.
    const min = metric.min ?? 0;
    const max = metric.max ?? 10;
    const span = max - min;
    const useSegments = metric.type === 'number' && Number.isFinite(span) && span >= 0 && span <= 20;
    const steps = useSegments ? Array.from({ length: Math.round(span) + 1 }, (_, i) => min + i) : [];
    const hasValue = value !== undefined && value !== null && value !== '';

    return (
        <div className="flex items-center gap-3 group">
            <div className="w-[150px] shrink-0">
                <div className="text-xs font-semibold text-slate-300 leading-tight">{metric.label}</div>
                {metric.description && (
                    <div className="text-[10px] text-slate-600 leading-tight mt-0.5 hidden sm:block">{metric.description}</div>
                )}
            </div>
            <div className="flex gap-1 flex-1 flex-wrap">
                {metric.type === 'number' ? (
                    useSegments ? (
                        steps.map((n) => (
                            <button
                                key={n}
                                type="button"
                                onClick={() => onChange(metric, String(n))}
                                className={cn(segButton(hasValue && Number(value) === n), 'min-w-[30px] px-1')}
                            >
                                {n}
                            </button>
                        ))
                    ) : (
                        <Input
                            type="number"
                            value={hasValue ? String(value) : ''}
                            min={metric.min ?? undefined}
                            max={metric.max ?? undefined}
                            step="1"
                            onChange={(e) => onChange(metric, e.target.value)}
                            className="bg-slate-900/60 border-slate-800/60 text-white h-8 text-xs font-mono"
                        />
                    )
                ) : (
                    (metric.options ?? []).map((opt) => {
                        const selected = value === opt.value;
                        return (
                            <Tooltip key={opt.value}>
                                <TooltipTrigger asChild>
                                    <button
                                        type="button"
                                        onClick={() => onChange(metric, opt.value)}
                                        className={cn(segButton(selected), 'min-w-[48px]')}
                                    >
                                        {opt.label}
                                    </button>
                                </TooltipTrigger>
                                {opt.description && (
                                    <TooltipContent side="top" className="bg-slate-900 border-slate-700 text-white text-xs max-w-[250px]">
                                        <p className="font-semibold">{opt.label}</p>
                                        <p className="text-slate-400 mt-1">{opt.description}</p>
                                    </TooltipContent>
                                )}
                            </Tooltip>
                        );
                    })
                )}
            </div>
        </div>
    );
}

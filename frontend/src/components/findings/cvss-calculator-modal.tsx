'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    CvssMetrics,
    MetricKey,
    METRIC_DEFINITIONS,
    calculateCVSSFromMetrics,
    parseVectorString,
    severityRating,
    severityColor,
    emptyMetrics,
    isComplete,
} from '@/lib/cvss31';
import { Calculator, Check, RotateCcw, Copy, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CvssCalculatorModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onApply: (score: number, vector: string) => void;
    initialVector?: string;
}

export function CvssCalculatorModal({
    open,
    onOpenChange,
    onApply,
    initialVector,
}: CvssCalculatorModalProps) {
    const [metrics, setMetrics] = useState<CvssMetrics>(emptyMetrics());
    const [copied, setCopied] = useState(false);

    // Parse initial vector when modal opens
    useEffect(() => {
        if (open) {
            if (initialVector) {
                const parsed = parseVectorString(initialVector);
                if (parsed) {
                    setMetrics(parsed);
                    return;
                }
            }
            setMetrics(emptyMetrics());
        }
    }, [open, initialVector]);

    const handleMetricChange = useCallback((key: MetricKey, value: string) => {
        setMetrics(prev => ({ ...prev, [key]: value }));
    }, []);

    const result = useMemo(() => {
        if (!isComplete(metrics)) return null;
        const r = calculateCVSSFromMetrics(metrics);
        return r.success ? r : null;
    }, [metrics]);

    const score = result ? parseFloat(result.baseMetricScore) : null;
    const severity = score !== null ? severityRating(score) : null;
    const color = severity ? severityColor(severity) : '#64748b';

    const handleApply = () => {
        if (result && score !== null) {
            onApply(score, result.vectorString);
            onOpenChange(false);
        }
    };

    const handleReset = () => {
        setMetrics(emptyMetrics());
    };

    const handleCopy = () => {
        if (result?.vectorString) {
            navigator.clipboard.writeText(result.vectorString);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        }
    };

    const filledCount = Object.values(metrics).filter(v => v !== '').length;

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
                                <DialogTitle className="text-base font-semibold">CVSS v3.1 Calculator</DialogTitle>
                                <DialogDescription className="text-xs text-slate-500 mt-0.5">
                                    Select metrics to compute the base score
                                </DialogDescription>
                            </div>
                        </div>

                        {/* Score display */}
                        <div className="flex items-center gap-3">
                            <div className="text-right">
                                <div
                                    className="text-3xl font-black font-mono leading-none transition-all duration-300"
                                    style={{ color }}
                                >
                                    {score !== null ? score.toFixed(1) : '—'}
                                </div>
                                <div
                                    className="text-[10px] font-bold uppercase tracking-widest mt-0.5 transition-all duration-300"
                                    style={{ color }}
                                >
                                    {severity || 'Incomplete'}
                                </div>
                            </div>
                        </div>
                    </div>
                </DialogHeader>

                <ScrollArea className="flex-1 overflow-y-auto" style={{ maxHeight: 'calc(90vh - 180px)' }}>
                    <div className="px-6 py-4 space-y-4">
                        {/* Progress bar */}
                        <div className="flex items-center gap-2">
                            <div className="h-1 flex-1 bg-slate-800 rounded-full overflow-hidden">
                                <div
                                    className="h-full rounded-full transition-all duration-300"
                                    style={{
                                        width: `${(filledCount / 8) * 100}%`,
                                        backgroundColor: filledCount === 8 ? color : '#64748b',
                                    }}
                                />
                            </div>
                            <span className="text-[10px] text-slate-500 font-mono">{filledCount}/8</span>
                        </div>

                        {/* Metric groups */}
                        <TooltipProvider delayDuration={200}>
                            <div className="space-y-3">
                                {/* Exploitability Section */}
                                <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 px-1">
                                    Exploitability Metrics
                                </div>
                                {METRIC_DEFINITIONS.slice(0, 4).map(metric => (
                                    <MetricRow
                                        key={metric.key}
                                        metric={metric}
                                        value={metrics[metric.key]}
                                        onChange={handleMetricChange}
                                        scoreColor={color}
                                    />
                                ))}

                                <Separator className="bg-slate-800/50" />

                                {/* Scope */}
                                <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 px-1">
                                    Scope
                                </div>
                                <MetricRow
                                    metric={METRIC_DEFINITIONS[4]}
                                    value={metrics.S}
                                    onChange={handleMetricChange}
                                    scoreColor={color}
                                />

                                <Separator className="bg-slate-800/50" />

                                {/* Impact Section */}
                                <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 px-1">
                                    Impact Metrics
                                </div>
                                {METRIC_DEFINITIONS.slice(5, 8).map(metric => (
                                    <MetricRow
                                        key={metric.key}
                                        metric={metric}
                                        value={metrics[metric.key]}
                                        onChange={handleMetricChange}
                                        scoreColor={color}
                                    />
                                ))}
                            </div>
                        </TooltipProvider>

                        {/* Vector string display */}
                        {result && (
                            <div className="bg-slate-900/50 border border-slate-800/60 rounded-lg px-3 py-2.5 flex items-center justify-between gap-2">
                                <code className="text-[10px] font-mono text-slate-400 break-all select-all">
                                    {result.vectorString}
                                </code>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-6 w-6 p-0 shrink-0 text-slate-500 hover:text-white"
                                    onClick={handleCopy}
                                >
                                    {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
                                </Button>
                            </div>
                        )}
                    </div>
                </ScrollArea>

                {/* Footer */}
                <div className="px-6 py-3 border-t border-slate-800/60 flex items-center justify-between bg-slate-950">
                    <div className="flex items-center gap-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleReset}
                            className="text-slate-500 hover:text-white h-8 text-xs"
                        >
                            <RotateCcw className="h-3 w-3 mr-1.5" />
                            Reset
                        </Button>
                        <a
                            href="https://www.first.org/cvss/calculator/3.1"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-slate-600 hover:text-slate-400 flex items-center gap-1 transition-colors"
                        >
                            <ExternalLink className="h-3 w-3" />
                            FIRST.org
                        </a>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onOpenChange(false)}
                            className="border-slate-800 text-slate-400 hover:text-white h-8 text-xs"
                        >
                            Cancel
                        </Button>
                        <Button
                            size="sm"
                            disabled={!result}
                            onClick={handleApply}
                            className="h-8 text-xs font-semibold"
                            style={{
                                backgroundColor: result ? color : undefined,
                                borderColor: result ? color : undefined,
                            }}
                        >
                            Apply Score
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}


// ─── Metric Row ─────────────────────────────────────────────────────────────

interface MetricRowProps {
    metric: (typeof METRIC_DEFINITIONS)[number];
    value: string;
    onChange: (key: MetricKey, value: string) => void;
    scoreColor: string;
}

function MetricRow({ metric, value, onChange, scoreColor }: MetricRowProps) {
    return (
        <div className="flex items-center gap-3 group">
            {/* Label */}
            <div className="w-[130px] shrink-0">
                <div className="text-xs font-semibold text-slate-300 leading-tight">{metric.name}</div>
                <div className="text-[10px] text-slate-600 leading-tight mt-0.5 hidden sm:block">{metric.key}</div>
            </div>

            {/* Options */}
            <div className="flex gap-1 flex-1">
                {metric.options.map(option => {
                    const isSelected = value === option.value;
                    return (
                        <Tooltip key={option.value}>
                            <TooltipTrigger asChild>
                                <button
                                    type="button"
                                    onClick={() => onChange(metric.key, option.value)}
                                    className={cn(
                                        'flex-1 h-8 rounded-md text-[11px] font-bold transition-all duration-150 border',
                                        'focus:outline-hidden focus:ring-2 focus:ring-offset-1 focus:ring-offset-slate-950',
                                        isSelected
                                            ? 'bg-amber-500 border-amber-400 text-slate-950 shadow-[0_0_16px_rgba(245,158,11,0.35)]'
                                            : 'bg-slate-900/60 border-slate-800/60 text-slate-500 hover:text-slate-200 hover:bg-slate-800/80 hover:border-slate-600'
                                    )}
                                >
                                    {option.label}
                                </button>
                            </TooltipTrigger>
                            <TooltipContent
                                side="top"
                                className="bg-slate-900 border-slate-700 text-white text-xs max-w-[250px]"
                            >
                                <p className="font-semibold">{option.label} ({metric.key}:{option.value})</p>
                                <p className="text-slate-400 mt-1">{option.description}</p>
                            </TooltipContent>
                        </Tooltip>
                    );
                })}
            </div>
        </div>
    );
}

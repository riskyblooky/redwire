'use client';

import { useEffect, useState, ReactNode } from 'react';
import { ScoringApplyResult, ScoringCalculatorModal } from '@/components/findings/scoring-calculator-modal';
import { useScoringModels } from '@/lib/hooks/use-scoring';
import { Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface InlineCvssFieldProps {
    vector?: string | null;
    /** The finding's current scoring model + raw inputs (so the calculator opens
     *  on the right model and round-trips the metric selections). */
    scoreModel?: string | null;
    scoreInputs?: Record<string, unknown> | null;
    onSave: (result: ScoringApplyResult) => Promise<void>;
    canEdit?: boolean;
    /** The read-view display (e.g. the existing score widget). */
    children: ReactNode;
}

/**
 * Wraps the score read-view display. Double-click (for editors) opens the shared
 * model-driven scoring calculator seeded with the finding's current model +
 * inputs; the model can be switched in the modal. Apply saves via onSave.
 */
export function InlineCvssField({ vector, scoreModel, scoreInputs, onSave, canEdit = false, children }: InlineCvssFieldProps) {
    const [open, setOpen] = useState(false);
    const { data: scoringModels = [] } = useScoringModels();
    const [modelId, setModelId] = useState(scoreModel || 'cvss31');

    // Re-seed the picker to the finding's model each time the editor opens.
    useEffect(() => {
        if (open) setModelId(scoreModel || 'cvss31');
    }, [open, scoreModel]);

    return (
        <div
            className={cn('group/inline relative', canEdit && 'cursor-pointer')}
            onDoubleClick={() => canEdit && setOpen(true)}
            title={canEdit ? 'Double-click to score' : undefined}
        >
            {canEdit && (
                <button
                    type="button"
                    onClick={() => setOpen(true)}
                    className="absolute top-1 right-1 z-10 p-1 rounded opacity-0 group-hover/inline:opacity-100 bg-slate-800/80 text-slate-400 hover:text-white transition-opacity"
                    title="Score"
                    aria-label="Score"
                >
                    <Pencil className="h-3 w-3" />
                </button>
            )}
            {children}
            {canEdit && (
                <ScoringCalculatorModal
                    open={open}
                    onOpenChange={setOpen}
                    modelId={modelId}
                    initialInputs={modelId === (scoreModel || 'cvss31') ? scoreInputs : null}
                    models={scoringModels}
                    onModelChange={setModelId}
                    onApply={async (result) => {
                        try {
                            await onSave(result);
                            toast.success('Score updated');
                        } catch (e: any) {
                            toast.error(e?.response?.data?.detail || e?.message || 'Failed to update score');
                        }
                    }}
                />
            )}
        </div>
    );
}

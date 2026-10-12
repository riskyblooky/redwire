'use client';

import { useEffect, useState, ReactNode } from 'react';
import { ScoringApplyResult, ScoringCalculatorModal } from '@/components/findings/scoring-calculator-modal';
import { useEffectiveScoringPolicy } from '@/lib/hooks/use-scoring';
import { Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface InlineCvssFieldProps {
    vector?: string | null;
    /** The finding's current scoring model + raw inputs (so the calculator opens
     *  on the right model and round-trips the metric selections). */
    scoreModel?: string | null;
    scoreInputs?: Record<string, unknown> | null;
    /** Engagement the finding belongs to — drives the scoring-model policy. */
    engagementId?: string | null;
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
export function InlineCvssField({ vector, scoreModel, scoreInputs, engagementId, onSave, canEdit = false, children }: InlineCvssFieldProps) {
    const [open, setOpen] = useState(false);
    const { data: policy } = useEffectiveScoringPolicy(engagementId);
    const allowed = policy?.allowed ?? [];
    const locked = !!policy?.locked;
    const [modelId, setModelId] = useState(scoreModel || 'cvss31');

    // On open, seed to the finding's model, clamped to the engagement's allowed
    // set (fall back to the policy default when the current model isn't allowed).
    useEffect(() => {
        if (!open) return;
        const want = scoreModel || policy?.default || 'cvss31';
        const ok = allowed.length === 0 || allowed.some((m) => m.id === want);
        setModelId(ok ? want : (policy?.default || want));
    }, [open, scoreModel, policy]); // eslint-disable-line react-hooks/exhaustive-deps

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
                    initialInputs={modelId === scoreModel ? scoreInputs : null}
                    models={locked ? undefined : allowed}
                    onModelChange={locked ? undefined : setModelId}
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

'use client';

import { useState, ReactNode } from 'react';
import { CvssCalculatorModal } from '@/components/findings/cvss-calculator-modal';
import { Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface InlineCvssFieldProps {
    vector?: string | null;
    onSave: (score: number, vector: string) => Promise<void>;
    canEdit?: boolean;
    /** The read-view display (e.g. the existing CVSS score widget). */
    children: ReactNode;
}

/**
 * Wraps the CVSS read-view display. Double-click (for editors) opens the shared
 * CVSS calculator seeded with the current vector; Apply saves score + vector via
 * the caller's onSave.
 */
export function InlineCvssField({ vector, onSave, canEdit = false, children }: InlineCvssFieldProps) {
    const [open, setOpen] = useState(false);

    return (
        <div
            className={cn('group/inline relative', canEdit && 'cursor-pointer')}
            onDoubleClick={() => canEdit && setOpen(true)}
            title={canEdit ? 'Double-click to score CVSS' : undefined}
        >
            {canEdit && (
                <button
                    type="button"
                    onClick={() => setOpen(true)}
                    className="absolute top-1 right-1 z-10 p-1 rounded opacity-0 group-hover/inline:opacity-100 bg-slate-800/80 text-slate-400 hover:text-white transition-opacity"
                    title="Score CVSS"
                    aria-label="Score CVSS"
                >
                    <Pencil className="h-3 w-3" />
                </button>
            )}
            {children}
            {canEdit && (
                <CvssCalculatorModal
                    open={open}
                    onOpenChange={setOpen}
                    initialVector={vector || undefined}
                    onApply={async (score, v) => {
                        try {
                            await onSave(score, v);
                            toast.success('CVSS updated');
                        } catch (e: any) {
                            toast.error(e?.response?.data?.detail || e?.message || 'Failed to update CVSS');
                        }
                    }}
                />
            )}
        </div>
    );
}

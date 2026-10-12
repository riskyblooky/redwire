'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import api from '../api';

// ─── Types (mirror backend/scoring/types.py) ─────────────────────────────────

export interface ScoringMetricOption {
    value: string;
    label: string;
    weight?: number | null;
    description?: string | null;
}

export interface ScoringMetric {
    id: string;
    label: string;
    group?: string | null;
    type: 'select' | 'number';
    options?: ScoringMetricOption[] | null;
    min?: number | null;
    max?: number | null;
    description?: string | null;
}

export interface ScoringModelSummary {
    id: string;
    label: string;
    version: string;
    source: string;
    score_kind: 'numeric' | 'categorical';
    description?: string | null;
}

export interface ScoringModel extends ScoringModelSummary {
    metrics: ScoringMetric[];
    formula: Record<string, unknown>;
    severity: { from: 'bands' | 'map'; bands?: unknown[]; map?: Record<string, string> };
    vector_template?: string | null;
    nominal_score?: Record<string, number> | null;
}

export interface ScoreResult {
    model_id: string;
    score: number | null;
    outcome: string | null;
    severity: string;              // CRITICAL | HIGH | MEDIUM | LOW | INFO
    vector: string | null;
    inputs: Record<string, unknown>;
}

// ─── Hooks ───────────────────────────────────────────────────────────────────

/** All available scoring models (summary form, for the picker). Models change
 *  rarely, so cache them for a while. */
export function useScoringModels() {
    return useQuery<ScoringModelSummary[]>({
        queryKey: ['scoring', 'models'],
        queryFn: async () => (await api.get('/scoring/models')).data,
        staleTime: 5 * 60_000,
    });
}

/** Full definition of one model (metrics + formula + severity mapping). */
export function useScoringModel(modelId?: string | null) {
    return useQuery<ScoringModel>({
        queryKey: ['scoring', 'models', modelId],
        queryFn: async () => (await api.get(`/scoring/models/${modelId}`)).data,
        enabled: !!modelId,
        staleTime: 5 * 60_000,
    });
}

/** The default scoring model id for new findings. */
export function useDefaultScoringModel() {
    return useQuery<ScoringModelSummary>({
        queryKey: ['scoring', 'default'],
        queryFn: async () => (await api.get('/scoring/default')).data,
        staleTime: 5 * 60_000,
    });
}

/** Evaluate a model over inputs server-side (used for the calculator's live
 *  preview — the same engine runs authoritatively on save, so no drift). */
export function useEvaluateScoring() {
    return useMutation<ScoreResult, unknown, { modelId: string; inputs: Record<string, unknown> }>({
        mutationFn: async ({ modelId, inputs }) =>
            (await api.post('/scoring/evaluate', { model_id: modelId, inputs })).data,
    });
}

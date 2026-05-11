/**
 * use-attack.ts — React Query hooks for ATT&CK API endpoints.
 *
 * Provides data fetching for engagement-level coverage, AI technique
 * suggestion, and Navigator JSON export.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

// ── Types ───────────────────────────────────────────────────────────

export interface CoverageFinding {
    id: string;
    title: string;
    severity: string | null;
    status: string | null;
}

export interface CoverageTestCase {
    id: string;
    title: string;
    category: string | null;
    is_executed: boolean;
    is_successful: boolean | null;
}

export interface AttackCoverage {
    mapped_techniques: string[];
    findings_by_technique: Record<string, CoverageFinding[]>;
    testcases_by_technique: Record<string, CoverageTestCase[]>;
    total_findings: number;
    mapped_findings: number;
    unmapped_findings: number;
    total_testcases: number;
    mapped_testcases: number;
    unmapped_testcases: number;
}

export interface SuggestionResult {
    technique_id: string;
    reasoning: string;
}

export interface FindingSuggestion {
    finding_id: string;
    finding_title: string;
    techniques: SuggestionResult[];
    error?: string;
}

export interface SuggestResponse {
    suggestions: FindingSuggestion[];
    message?: string;
    succeeded?: number;
    failed?: number;
    first_error?: string | null;
}


// ── Hooks ───────────────────────────────────────────────────────────

/**
 * Fetch ATT&CK technique coverage for an engagement.
 */
export function useAttackCoverage(engagementId: string) {
    return useQuery({
        queryKey: ['attack', 'coverage', engagementId],
        queryFn: async () => {
            const { data } = await api.get<AttackCoverage>(
                `/attack/engagement/${engagementId}/coverage`
            );
            return data;
        },
        enabled: !!engagementId,
        staleTime: 30_000,
    });
}

/**
 * AI-suggest ATT&CK techniques for unmapped findings.
 */
export function useAiSuggestTechniques(engagementId: string) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (findingIds?: string[]) => {
            const { data } = await api.post<SuggestResponse>(
                `/attack/engagement/${engagementId}/suggest`,
                { finding_ids: findingIds || [] },
                { timeout: 600_000 } // 10 minutes — local LLM inference can be slow
            );
            return data;
        },
        onSuccess: () => {
            // Invalidate coverage so the heatmap refreshes after applying suggestions
            queryClient.invalidateQueries({ queryKey: ['attack', 'coverage', engagementId] });
        },
    });
}

/**
 * Download ATT&CK Navigator JSON layer for an engagement.
 */
export function useAttackNavigatorExport(engagementId: string) {
    return useMutation({
        mutationFn: async () => {
            const { data } = await api.get(
                `/attack/engagement/${engagementId}/navigator`,
                { responseType: 'json' }
            );
            // Trigger download
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `redwire_attack_navigator.json`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            return data;
        },
    });
}

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
    entity_type: 'finding' | 'testcase';
    entity_id: string;
    entity_title: string;
    techniques: SuggestionResult[];
    error?: string;
}

export interface SuggestResponse {
    suggestions: FindingSuggestion[];
    message?: string;
    succeeded?: number;
    failed?: number;
    first_error?: string | null;
    total?: number;
    next_offset?: number | null;
}


// ── Hooks ───────────────────────────────────────────────────────────

/**
 * Fetch ATT&CK technique coverage for an engagement.
 */
export function useAttackCoverage(engagementId: string, enabled: boolean = true) {
    return useQuery({
        queryKey: ['attack', 'coverage', engagementId],
        queryFn: async () => {
            const { data } = await api.get<AttackCoverage>(
                `/attack/engagement/${engagementId}/coverage`
            );
            return data;
        },
        enabled: enabled && !!engagementId,
        staleTime: 30_000,
    });
}

/**
 * AI-suggest ATT&CK techniques for unmapped findings.
 */
export function useAiSuggestTechniques(engagementId: string) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (opts?: {
            source?: 'finding' | 'testcase'; findingIds?: string[]; testcaseIds?: string[]; includeMapped?: boolean;
            onProgress?: (done: number, total: number) => void;
        }) => {
            // One item per request: each stays within a single LLM call's
            // timeout, where a whole engagement in one request could outlive
            // the proxy's read timeout and lose every result.
            const merged: SuggestResponse = { suggestions: [], succeeded: 0, failed: 0, first_error: null };
            let offset: number | null = 0;
            while (offset !== null) {
                const { data }: { data: SuggestResponse } = await api.post<SuggestResponse>(
                    `/attack/engagement/${engagementId}/suggest`,
                    {
                        source: opts?.source ?? 'finding',
                        finding_ids: opts?.findingIds || [],
                        testcase_ids: opts?.testcaseIds || [],
                        include_mapped: opts?.includeMapped ?? false,
                        offset,
                        limit: 1,
                    },
                    { timeout: 600_000 } // 10 minutes — local LLM inference can be slow
                );
                if (data.message && !data.suggestions.length) return data;
                merged.suggestions.push(...data.suggestions);
                merged.succeeded! += data.succeeded ?? 0;
                merged.failed! += data.failed ?? 0;
                merged.first_error = merged.first_error ?? data.first_error ?? null;
                merged.total = data.total;
                opts?.onProgress?.(merged.suggestions.length, data.total ?? merged.suggestions.length);
                offset = data.next_offset ?? null;
            }
            return merged;
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

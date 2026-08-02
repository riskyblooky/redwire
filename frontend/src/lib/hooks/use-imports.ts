/**
 * use-imports.ts — Scanner Import Hooks
 *
 * Two mutation hooks for the two-step import flow:
 *  - `usePreviewImport` — dry-run parse, returns preview data
 *  - `useCommitImport`  — creates assets + findings in DB
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../api';

// ── Preview Types ───────────────────────────────────────────────

export interface PreviewPort {
    port_number: number;
    protocol: string;
    service_name?: string;
    state: string;
    version?: string;
}

export interface PreviewAsset {
    index: number;
    name: string;
    asset_type: string;
    identifier: string;
    description: string;
    ports: PreviewPort[];
    is_duplicate: boolean;
}

export interface PreviewFinding {
    index: number;
    title: string;
    severity: string;
    description: string;
    impact?: string;
    mitigations?: string;
    references?: string;
    cvss_score?: number;
    cvss_vector?: string;
    category?: string;
    affected_asset_count: number;
    is_duplicate: boolean;
}

export interface PreviewResponse {
    source_tool: string;
    assets: PreviewAsset[];
    findings: PreviewFinding[];
    warnings: string[];
    metadata: Record<string, unknown>;
}

// ── Commit Types ────────────────────────────────────────────────

export interface CommitResponse {
    assets_created: number;
    assets_skipped: number;
    findings_created: number;
    findings_skipped: number;
    ports_added: number;
    finding_asset_links: number;
    errors: string[];
    scan_import_id?: string | null;
}

// ── Scan history ────────────────────────────────────────────────

export interface ScanImport {
    id: string;
    engagement_id: string;
    source_tool: string;
    source_format?: string | null;
    filename?: string | null;
    command?: string | null;
    scanner?: string | null;
    scanner_version?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    elapsed_seconds?: number | null;
    summary?: string | null;
    hosts_total?: number | null;
    hosts_up?: number | null;
    hosts_down?: number | null;
    assets_created: number;
    assets_merged: number;
    findings_created: number;
    ports_added: number;
    created_by?: string | null;
    created_by_username?: string | null;
    created_at?: string | null;
}

// ── Hooks ───────────────────────────────────────────────────────

export function usePreviewImport() {
    return useMutation({
        mutationFn: async ({ file, engagementId }: { file: File; engagementId?: string }) => {
            const formData = new FormData();
            formData.append('file', file);
            if (engagementId) {
                formData.append('engagement_id', engagementId);
            }
            const { data } = await api.post<PreviewResponse>('/imports/preview', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data;
        },
    });
}

export function useCommitImport() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            file,
            engagementId,
            importAssets = true,
            importFindings = true,
            assetIndices,
            findingIndices,
        }: {
            file: File;
            engagementId: string;
            importAssets?: boolean;
            importFindings?: boolean;
            assetIndices?: number[];
            findingIndices?: number[];
        }) => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('engagement_id', engagementId);
            formData.append('import_assets', String(importAssets));
            formData.append('import_findings', String(importFindings));
            if (assetIndices) {
                formData.append('asset_indices', JSON.stringify(assetIndices));
            }
            if (findingIndices) {
                formData.append('finding_indices', JSON.stringify(findingIndices));
            }
            const { data } = await api.post<CommitResponse>('/imports/commit', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data;
        },
        onSuccess: (_data, vars) => {
            queryClient.invalidateQueries({ queryKey: ['assets'] });
            queryClient.invalidateQueries({ queryKey: ['findings'] });
            queryClient.invalidateQueries({ queryKey: ['analytics'] });
            queryClient.invalidateQueries({ queryKey: ['scan-imports', vars.engagementId] });
        },
    });
}

/** Past scanner imports for an engagement (most recent first), each carrying the
 *  command line + scan metadata captured at import time. */
export function useScanImports(engagementId?: string) {
    return useQuery({
        queryKey: ['scan-imports', engagementId],
        enabled: !!engagementId,
        staleTime: 30_000,
        queryFn: async () => {
            const { data } = await api.get<ScanImport[]>('/imports/scans', {
                params: { engagement_id: engagementId },
            });
            return data;
        },
    });
}

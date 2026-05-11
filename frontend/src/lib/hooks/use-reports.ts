import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface ReportConfiguration {
    engagement_id: string;
    layout_id: string;
    report_format: 'pdf' | 'markdown' | 'json_zip';
    exclude_severities: string[];
    theme_id?: string;
    include_evidence?: boolean;
    finding_ids?: string[];
    testcase_ids?: string[];
    cleanup_ids?: string[];
}

export interface GenerateReportResult {
    blob: Blob;
    filename: string;
    mimeType: string;
}

/**
 * Generate a report and return the blob + filename for preview.
 * Does NOT auto-download — the caller decides what to do with the result.
 */
export function useGenerateReport() {
    return useMutation({
        mutationFn: async (config: ReportConfiguration): Promise<GenerateReportResult> => {
            const response = await api.post('/reports/generate', config, {
                responseType: 'blob',
            });

            // Extract filename from Content-Disposition header
            const contentDisposition = String(response.headers['content-disposition'] ?? '');
            let filename = 'report.pdf';
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
                if (filenameMatch && filenameMatch.length === 2) filename = filenameMatch[1];
            }

            // Determine mime type
            const mimeType = String(response.headers['content-type'] ?? 'application/octet-stream');

            return {
                blob: new Blob([response.data]),
                filename,
                mimeType,
            };
        },
    });
}

/**
 * Trigger a browser download from a blob + filename.
 */
export function downloadBlob(blob: Blob, filename: string) {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
}

/**
 * Save a generated report as an engagement attachment.
 */
export function useSaveReportToEngagement() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            blob,
            filename,
            engagementId,
        }: {
            blob: Blob;
            filename: string;
            engagementId: string;
        }) => {
            const formData = new FormData();
            formData.append('file', blob, filename);
            formData.append('engagement_id', engagementId);
            formData.append('filename', filename);

            const { data } = await api.post<{
                id: string;
                filename: string;
                file_size: number;
                message: string;
            }>('/reports/save-to-engagement', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data;
        },
        onSuccess: (_data, variables) => {
            // Invalidate attachments / evidence queries so the saved report shows up
            queryClient.invalidateQueries({ queryKey: ['engagements', variables.engagementId, 'evidence'] });
        },
    });
}

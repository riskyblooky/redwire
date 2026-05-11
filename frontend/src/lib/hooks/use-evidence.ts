import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { Evidence } from '../types';

// Get all evidence for an engagement
export function useEngagementEvidence(engagementId: string) {
    return useQuery({
        queryKey: ['engagements', engagementId, 'evidence'],
        queryFn: async () => {
            const { data } = await api.get<Evidence[]>(`/engagements/${engagementId}/evidence`);
            return data;
        },
        enabled: !!engagementId,
    });
}

// Get single evidence metadata
export function useEvidence(evidenceId: string) {
    return useQuery({
        queryKey: ['evidence', evidenceId],
        queryFn: async () => {
            const { data } = await api.get<Evidence>(`/evidence/${evidenceId}`);
            return data;
        },
        enabled: !!evidenceId,
    });
}

// Upload evidence (can be linked to finding, testcase, or just engagement)
export function useUploadEvidence(ids: { findingId?: string; testcaseId?: string; engagementId?: string }) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ file, description, includeInReport = true }: { file: File; description?: string; includeInReport?: boolean }) => {
            const formData = new FormData();
            formData.append('file', file);
            if (description) formData.append('description', description);
            formData.append('include_in_report', String(includeInReport));

            let endpoint = '';
            if (ids.findingId) {
                endpoint = `/findings/${ids.findingId}/evidence`;
            } else if (ids.testcaseId) {
                endpoint = `/testcases/${ids.testcaseId}/evidence`;
            } else if (ids.engagementId) {
                endpoint = `/engagements/${ids.engagementId}/evidence`;
            } else {
                throw new Error("Either findingId, testcaseId, or engagementId must be provided");
            }

            const { data } = await api.post<Evidence>(endpoint, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });
            return data;
        },
        onSuccess: (data) => {
            // Invalidate relevant queries
            if (data.finding_id) {
                queryClient.invalidateQueries({ queryKey: ['findings', data.finding_id] });
                queryClient.invalidateQueries({ queryKey: ['findings'] });
            }
            if ((data as any).testcase_id) {
                queryClient.invalidateQueries({ queryKey: ['testcases', (data as any).testcase_id] });
                queryClient.invalidateQueries({ queryKey: ['testcases'] });
            }
            if (data.engagement_id) {
                queryClient.invalidateQueries({ queryKey: ['engagements', data.engagement_id, 'evidence'] });
            }
        },
    });
}

// Update evidence metadata
export function useUpdateEvidence() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, description, includeInReport }: { id: string; description?: string; includeInReport?: boolean }) => {
            const updateData: any = {};
            if (description !== undefined) updateData.description = description;
            if (includeInReport !== undefined) updateData.include_in_report = includeInReport;

            const { data } = await api.patch<Evidence>(`/evidence/${id}`, updateData);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['evidence', data.id] });
            if (data.finding_id) {
                queryClient.invalidateQueries({ queryKey: ['findings', data.finding_id] });
            }
            if ((data as any).testcase_id) {
                queryClient.invalidateQueries({ queryKey: ['testcases', (data as any).testcase_id] });
            }
            if (data.engagement_id) {
                queryClient.invalidateQueries({ queryKey: ['engagements', data.engagement_id, 'evidence'] });
            }
        },
    });
}

// Delete evidence
export function useDeleteEvidence() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (evidence: Evidence) => {
            await api.delete(`/evidence/${evidence.id}`);
            return evidence;
        },
        onSuccess: (evidence) => {
            queryClient.invalidateQueries({ queryKey: ['evidence', evidence.id] });
            if (evidence.finding_id) {
                queryClient.invalidateQueries({ queryKey: ['findings', evidence.finding_id] });
            }
            if ((evidence as any).testcase_id) {
                queryClient.invalidateQueries({ queryKey: ['testcases', (evidence as any).testcase_id] });
            }
            if (evidence.engagement_id) {
                queryClient.invalidateQueries({ queryKey: ['engagements', evidence.engagement_id, 'evidence'] });
            }
        },
    });
}

// Replace evidence file (for image editor)
export function useReplaceEvidenceFile() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, file }: { id: string; file: Blob }) => {
            const formData = new FormData();
            formData.append('file', file, 'edited-image.png');

            const { data } = await api.put<Evidence>(`/evidence/${id}/replace-file`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['evidence', data.id] });
            if (data.finding_id) {
                queryClient.invalidateQueries({ queryKey: ['findings', data.finding_id] });
            }
            if ((data as any).testcase_id) {
                queryClient.invalidateQueries({ queryKey: ['testcases', (data as any).testcase_id] });
            }
            if (data.engagement_id) {
                queryClient.invalidateQueries({ queryKey: ['engagements', data.engagement_id, 'evidence'] });
            }
        },
    });
}

// Get presigned URL for evidence
export async function getEvidenceUrl(evidenceId: string) {
    // Note: We use the generic /evidence/{id}/url endpoint now
    const { data } = await api.get<{ url: string }>(`/evidence/${evidenceId}/url`);
    return data.url;
}

// Get EXIF data for an image evidence
export function useEvidenceExif(evidenceId: string, mimeType?: string | null) {
    return useQuery({
        queryKey: ['evidence', evidenceId, 'exif'],
        queryFn: async () => {
            const { data } = await api.get<{ exif: Record<string, any>; has_exif: boolean }>(`/evidence/${evidenceId}/exif`);
            return data;
        },
        enabled: !!evidenceId && !!mimeType?.startsWith('image/'),
    });
}

// Strip EXIF from image evidence
export function useStripExif() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (evidenceId: string) => {
            const { data } = await api.post<{ message: string; date_taken: string | null; new_file_size: number }>(`/evidence/${evidenceId}/strip-exif`);
            return data;
        },
        onSuccess: (_, evidenceId) => {
            queryClient.invalidateQueries({ queryKey: ['evidence', evidenceId] });
            queryClient.invalidateQueries({ queryKey: ['evidence', evidenceId, 'exif'] });
        },
    });
}

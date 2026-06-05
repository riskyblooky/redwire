import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface CleanupArtifact {
    id: string;
    engagement_id: string;
    title: string;
    artifact_type: 'SSH_KEY' | 'FILE' | 'ACCOUNT' | 'PERMISSION' | 'BACKDOOR' | 'IMPLANT' | 'OTHER';
    status: 'PENDING' | 'CLEANED' | 'PARTIALLY_CLEANED' | 'NOT_APPLICABLE';
    location?: string;
    description?: string;
    cleanup_notes?: string;
    classification_level?: string | null;
    classification_suffix?: string | null;
    cleaned_at?: string;
    cleaned_by?: string;
    cleaned_by_username?: string;
    created_at: string;
    updated_at: string;
    created_by: string;
    created_by_username?: string;
    created_by_profile_photo?: string;
    updated_by?: string;
    findings?: { id: string; title: string; severity: string }[];
    testcases?: { id: string; title: string }[];
    assets?: { id: string; name: string; identifier: string }[];
}

export function useCleanupArtifacts(engagementId: string) {
    return useQuery({
        queryKey: ['engagements', engagementId, 'cleanup-artifacts'],
        queryFn: async () => {
            const { data } = await api.get<CleanupArtifact[]>(`/cleanup-artifacts?engagement_id=${engagementId}`);
            return data;
        },
        enabled: !!engagementId,
    });
}

export function useCleanupArtifact(id: string | undefined) {
    return useQuery({
        queryKey: ['cleanup-artifacts', id],
        queryFn: async () => {
            const { data } = await api.get<CleanupArtifact>(`/cleanup-artifacts/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useCreateCleanupArtifact() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: Omit<CleanupArtifact, 'id' | 'created_at' | 'updated_at' | 'created_by' | 'findings' | 'testcases'>) => {
            const { data: result } = await api.post<CleanupArtifact>('/cleanup-artifacts', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
        },
    });
}

export function useUpdateCleanupArtifact() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...data }: { id: string } & Partial<CleanupArtifact>) => {
            const { data: result } = await api.patch<CleanupArtifact>(`/cleanup-artifacts/${id}`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
        },
    });
}

export function useDeleteCleanupArtifact() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/cleanup-artifacts/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
        },
    });
}

export function useLinkCleanupToFinding() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ artifactId, findingId }: { artifactId: string; findingId: string }) => {
            await api.post(`/cleanup-artifacts/${artifactId}/findings/${findingId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['findings'] });
        },
    });
}

export function useUnlinkCleanupFromFinding() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ artifactId, findingId }: { artifactId: string; findingId: string }) => {
            await api.delete(`/cleanup-artifacts/${artifactId}/findings/${findingId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['findings'] });
        },
    });
}

export function useLinkCleanupToTestCase() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ artifactId, testcaseId }: { artifactId: string; testcaseId: string }) => {
            await api.post(`/cleanup-artifacts/${artifactId}/testcases/${testcaseId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

export function useUnlinkCleanupFromTestCase() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ artifactId, testcaseId }: { artifactId: string; testcaseId: string }) => {
            await api.delete(`/cleanup-artifacts/${artifactId}/testcases/${testcaseId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

export function useLinkCleanupToAsset() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ artifactId, assetId }: { artifactId: string; assetId: string }) => {
            await api.post(`/cleanup-artifacts/${artifactId}/assets/${assetId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

export function useUnlinkCleanupFromAsset() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ artifactId, assetId }: { artifactId: string; assetId: string }) => {
            await api.delete(`/cleanup-artifacts/${artifactId}/assets/${assetId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}


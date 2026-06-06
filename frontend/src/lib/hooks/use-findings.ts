import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { Asset, Tag, Evidence } from '../types';

export interface Finding {
    id: string;
    engagement_id: string;
    title: string;
    category: string | null;
    description: string;
    severity: string;
    status: string;
    impact: string | null;
    technical_details: string | null;
    steps_to_reproduce: string | null;
    mitigations: string | null;
    references: string | null;
    cvss_score: number | null;
    cvss_vector: string | null;
    classification_level?: string | null;
    classification_suffix?: string | null;
    created_by: string;
    created_at: string;
    updated_at: string;
    evidence?: Evidence[];
    asset_ids: string[];
    assets?: Asset[];
    unresolved_thread_count?: number;
    created_by_username?: string;
    created_by_profile_photo?: string;
    tags?: Tag[];
    testcases?: { id: string; title: string }[];
    vault_items?: { id: string; name: string; item_type: string }[];
    cleanup_artifacts?: { id: string; title: string; artifact_type: string; status: string }[];
    attack_technique_ids?: string[];
}



export interface FindingCreate {
    engagement_id: string;
    title: string;
    category?: string;
    description: string;
    severity: string;
    impact?: string;
    technical_details?: string;
    steps_to_reproduce?: string;
    mitigations?: string;
    references?: string;
    cvss_score?: number;
    cvss_vector?: string;
    classification_level?: string | null;
    classification_suffix?: string | null;
    asset_ids?: string[];
    tag_ids?: string[];
    testcase_id?: string;
    attack_technique_ids?: string[];
}

export interface FindingUpdate extends Partial<FindingCreate> {
    id: string;
    status?: string;
}

export type TemplateStatus = 'DRAFT' | 'SUBMITTED' | 'PUBLISHED';

export interface FindingTemplate {
    id: string;
    title: string;
    category: string | null;
    description: string;
    impact: string | null;
    mitigations: string | null;
    references: string | null;
    attack_technique_ids: string[];
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by: string | null;
    status: TemplateStatus;
    submitted_at: string | null;
    published_at: string | null;
    published_by: string | null;
    review_note: string | null;
}


export function useFindings(params?: { engagement_id?: string; severity?: string; status?: string }) {
    return useQuery({
        queryKey: ['findings', params],
        queryFn: async () => {
            const { data } = await api.get<Finding[]>('/findings', { params });
            return data;
        },
        staleTime: 30_000,
    });
}

export function useFinding(id: string) {
    return useQuery({
        queryKey: ['findings', id],
        queryFn: async () => {
            const { data } = await api.get<Finding>(`/findings/${id}`);
            return data;
        },
        enabled: !!id,
        staleTime: 30_000,
    });
}

export function useCreateFinding() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (finding: FindingCreate) => {
            const { data } = await api.post<Finding>('/findings', finding);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['findings'] });
            queryClient.invalidateQueries({ queryKey: ['engagements', data.engagement_id] });
        },
    });
}

export function useUpdateFinding() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, ...finding }: FindingUpdate) => {
            const { data } = await api.put<Finding>(`/findings/${id}`, finding);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['findings'] });
            queryClient.invalidateQueries({ queryKey: ['findings', data.id] });
            queryClient.invalidateQueries({ queryKey: ['engagements', data.engagement_id] });
            queryClient.invalidateQueries({ queryKey: ['versions', 'finding', data.id] });
        },
    });
}

export function useDeleteFinding() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/findings/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['findings'] });
        },
    });
}

// Finding Templates Hooks
export function useFindingTemplate(id?: string) {
    return useQuery({
        queryKey: ['finding-template', id],
        queryFn: async () => {
            const { data } = await api.get<FindingTemplate>(`/templates/${id}`);
            return data;
        },
        enabled: !!id,
        staleTime: 60_000,
    });
}

export function useFindingTemplates(category?: string) {
    return useQuery({
        queryKey: ['finding-templates', category],
        queryFn: async () => {
            const params = category ? { category } : {};
            const { data } = await api.get<FindingTemplate[]>('/templates', { params });
            return data;
        },
        staleTime: 60_000,
    });
}

export function useCreateFindingTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (template: { title: string; category?: string; description: string; impact?: string; mitigations?: string }) => {
            const { data } = await api.post<FindingTemplate>('/templates', template);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['finding-templates'] });
        },
    });
}

export function useUpdateFindingTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...template }: { id: string; title?: string; category?: string; description?: string; impact?: string; mitigations?: string }) => {
            const { data } = await api.put<FindingTemplate>(`/templates/${id}`, template);
            return data;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['finding-templates'] });
            queryClient.invalidateQueries({ queryKey: ['finding-template', variables.id] });
        },
    });
}

export function useDeleteFindingTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/templates/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['finding-templates'] });
        },
    });
}

function templateAction(action: 'submit' | 'withdraw' | 'approve' | 'reject' | 'unpublish') {
    return function useTemplateAction() {
        const queryClient = useQueryClient();
        return useMutation({
            mutationFn: async (args: { id: string; review_note?: string; expected_updated_at?: string }) => {
                let body: Record<string, string> | undefined;
                if (action === 'reject') {
                    body = { review_note: args.review_note ?? '' };
                } else if (action === 'approve' && args.expected_updated_at) {
                    // GHSA-9cvp-w26m-49j9: pin the approval to the exact row revision the reviewer read.
                    body = { expected_updated_at: args.expected_updated_at };
                }
                const { data } = await api.post<FindingTemplate>(`/templates/${args.id}/${action}`, body);
                return data;
            },
            onSuccess: (_data, variables) => {
                queryClient.invalidateQueries({ queryKey: ['finding-templates'] });
                queryClient.invalidateQueries({ queryKey: ['finding-template', variables.id] });
            },
        });
    };
}

export const useSubmitFindingTemplate = templateAction('submit');
export const useWithdrawFindingTemplate = templateAction('withdraw');
export const useApproveFindingTemplate = templateAction('approve');
export const useRejectFindingTemplate = templateAction('reject');
export const useUnpublishFindingTemplate = templateAction('unpublish');

export function useTags() {
    return useQuery({
        queryKey: ['tags'],
        queryFn: async () => {
            const { data } = await api.get<Tag[]>('/findings/tags/list');
            return data;
        },
        staleTime: 60_000,
    });
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface RunbookItemTemplate {
    id: string;
    title: string;
    category: string;
    description: string;
    steps: string | null;
    expected_result: string | null;
}

export interface RunbookItem {
    id: string;
    runbook_id: string;
    template_id: string;
    parent_id: string | null;
    sort_order: number;
    template: RunbookItemTemplate | null;
}

export type TemplateStatus = 'DRAFT' | 'SUBMITTED' | 'PUBLISHED';

export interface Runbook {
    id: string;
    name: string;
    description: string | null;
    runbook_type: string | null;
    items: RunbookItem[];
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

export interface RunbookItemCreate {
    template_id: string;
    temp_key: string;
    parent_temp_key: string | null;
    sort_order: number;
}

export interface RunbookCreate {
    name: string;
    description?: string;
    runbook_type?: string;
    items: RunbookItemCreate[];
}

export interface RunbookUpdate {
    name?: string;
    description?: string;
    runbook_type?: string;
    items?: RunbookItemCreate[];
}

export function useRunbooks() {
    return useQuery({
        queryKey: ['runbooks'],
        queryFn: async () => {
            try {
                const { data } = await api.get<Runbook[]>('/runbooks');
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useRunbook(id?: string) {
    return useQuery({
        queryKey: ['runbook', id],
        queryFn: async () => {
            const { data } = await api.get<Runbook>(`/runbooks/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useCreateRunbook() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (runbook: RunbookCreate) => {
            const { data } = await api.post<Runbook>('/runbooks', runbook);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['runbooks'] });
        },
    });
}

export function useUpdateRunbook() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...runbook }: { id: string } & RunbookUpdate) => {
            const { data } = await api.put<Runbook>(`/runbooks/${id}`, runbook);
            return data;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['runbooks'] });
            queryClient.invalidateQueries({ queryKey: ['runbook', variables.id] });
        },
    });
}

export function useDeleteRunbook() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/runbooks/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['runbooks'] });
        },
    });
}

function rbAction(action: 'submit' | 'withdraw' | 'approve' | 'reject' | 'unpublish') {
    return function useRunbookAction() {
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
                const { data } = await api.post<Runbook>(`/runbooks/${args.id}/${action}`, body);
                return data;
            },
            onSuccess: (_data, variables) => {
                queryClient.invalidateQueries({ queryKey: ['runbooks'] });
                queryClient.invalidateQueries({ queryKey: ['runbook', variables.id] });
            },
        });
    };
}

export const useSubmitRunbook = rbAction('submit');
export const useWithdrawRunbook = rbAction('withdraw');
export const useApproveRunbook = rbAction('approve');
export const useRejectRunbook = rbAction('reject');
export const useUnpublishRunbook = rbAction('unpublish');

export function useApplyRunbook() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ runbookId, engagementId, parentTestcaseId }: {
            runbookId: string;
            engagementId: string;
            parentTestcaseId?: string;
        }) => {
            const params = parentTestcaseId ? { parent_testcase_id: parentTestcaseId } : {};
            const { data } = await api.post(`/runbooks/${runbookId}/apply/${engagementId}`, null, { params });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

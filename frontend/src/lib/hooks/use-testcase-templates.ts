import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export type TestCaseCategory = string;
export type TemplateStatus = 'DRAFT' | 'SUBMITTED' | 'PUBLISHED';

export interface TestCaseTemplate {
    id: string;
    title: string;
    category: TestCaseCategory;
    description: string;
    steps: string | null;
    expected_result: string | null;
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

export interface TestCaseTemplateCreate {
    title: string;
    category: TestCaseCategory;
    description: string;
    steps?: string;
    expected_result?: string;
    attack_technique_ids?: string[];
}

export function useTestCaseTemplate(id?: string) {
    return useQuery({
        queryKey: ['testcase-template', id],
        queryFn: async () => {
            const { data } = await api.get<TestCaseTemplate>(`/testcase-templates/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useTestCaseTemplates(category?: string) {
    return useQuery({
        queryKey: ['testcase-templates', category],
        queryFn: async () => {
            const { data } = await api.get<TestCaseTemplate[]>('/testcase-templates', {
                params: { category }
            });
            return data;
        },
    });
}

export function useCreateTestCaseTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (template: TestCaseTemplateCreate) => {
            const { data } = await api.post<TestCaseTemplate>('/testcase-templates', template);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['testcase-templates'] });
        },
    });
}

export function useUpdateTestCaseTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...template }: { id: string } & Partial<TestCaseTemplateCreate>) => {
            const { data } = await api.put<TestCaseTemplate>(`/testcase-templates/${id}`, template);
            return data;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['testcase-templates'] });
            queryClient.invalidateQueries({ queryKey: ['testcase-template', variables.id] });
        },
    });
}

export function useDeleteTestCaseTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/testcase-templates/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['testcase-templates'] });
        },
    });
}

function tcAction(action: 'submit' | 'withdraw' | 'approve' | 'reject' | 'unpublish') {
    return function useTestCaseTemplateAction() {
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
                const { data } = await api.post<TestCaseTemplate>(`/testcase-templates/${args.id}/${action}`, body);
                return data;
            },
            onSuccess: (_data, variables) => {
                queryClient.invalidateQueries({ queryKey: ['testcase-templates'] });
                queryClient.invalidateQueries({ queryKey: ['testcase-template', variables.id] });
            },
        });
    };
}

export const useSubmitTestCaseTemplate = tcAction('submit');
export const useWithdrawTestCaseTemplate = tcAction('withdraw');
export const useApproveTestCaseTemplate = tcAction('approve');
export const useRejectTestCaseTemplate = tcAction('reject');
export const useUnpublishTestCaseTemplate = tcAction('unpublish');

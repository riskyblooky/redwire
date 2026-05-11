import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { ReportLayoutTemplate } from '../types';

export interface ReportLayoutTemplateSectionCreate {
    section_type: 'text' | 'findings' | 'testcases' | 'cleanup_artifacts';
    title: string;
    content?: string;
    sort_order: number;
}

export interface ReportLayoutTemplateCreate {
    name: string;
    description?: string;
    sections: ReportLayoutTemplateSectionCreate[];
}

export interface ReportLayoutTemplateUpdate {
    name?: string;
    description?: string;
    sections?: ReportLayoutTemplateSectionCreate[];
}

export function useReportLayoutTemplates() {
    return useQuery({
        queryKey: ['report-layout-templates'],
        queryFn: async () => {
            const { data } = await api.get<ReportLayoutTemplate[]>('/report-layout-templates');
            return data;
        },
    });
}

export function useReportLayoutTemplate(id?: string) {
    return useQuery({
        queryKey: ['report-layout-template', id],
        queryFn: async () => {
            const { data } = await api.get<ReportLayoutTemplate>(`/report-layout-templates/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useCreateReportLayoutTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (template: ReportLayoutTemplateCreate) => {
            const { data } = await api.post<ReportLayoutTemplate>('/report-layout-templates', template);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['report-layout-templates'] });
        },
    });
}

export function useUpdateReportLayoutTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...template }: { id: string } & ReportLayoutTemplateUpdate) => {
            const { data } = await api.put<ReportLayoutTemplate>(`/report-layout-templates/${id}`, template);
            return data;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['report-layout-templates'] });
            queryClient.invalidateQueries({ queryKey: ['report-layout-template', variables.id] });
        },
    });
}

export function useDeleteReportLayoutTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/report-layout-templates/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['report-layout-templates'] });
        },
    });
}

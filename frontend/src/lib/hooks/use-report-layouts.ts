import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { ReportLayout } from '../types';

export interface ReportSectionCreate {
    section_type: 'text' | 'findings' | 'testcases' | 'cleanup_artifacts';
    title: string;
    content?: string;
    sort_order: number;
}

export interface ReportLayoutCreate {
    name: string;
    is_default?: boolean;
    sections: ReportSectionCreate[];
}

export interface ReportLayoutUpdate {
    name?: string;
    is_default?: boolean;
    sections?: ReportSectionCreate[];
}

export function useReportLayouts(engagementId?: string) {
    return useQuery({
        queryKey: ['report-layouts', engagementId],
        queryFn: async () => {
            const { data } = await api.get<ReportLayout[]>(`/engagements/${engagementId}/report-layouts`);
            return data;
        },
        enabled: !!engagementId,
    });
}

export function useReportLayout(engagementId?: string, layoutId?: string) {
    return useQuery({
        queryKey: ['report-layout', engagementId, layoutId],
        queryFn: async () => {
            const { data } = await api.get<ReportLayout>(`/engagements/${engagementId}/report-layouts/${layoutId}`);
            return data;
        },
        enabled: !!engagementId && !!layoutId,
    });
}

export function useCreateReportLayout() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ engagementId, ...layout }: { engagementId: string } & ReportLayoutCreate) => {
            const { data } = await api.post<ReportLayout>(`/engagements/${engagementId}/report-layouts`, layout);
            return data;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['report-layouts', variables.engagementId] });
        },
    });
}

export function useUpdateReportLayout() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ engagementId, layoutId, ...layout }: { engagementId: string; layoutId: string } & ReportLayoutUpdate) => {
            const { data } = await api.put<ReportLayout>(`/engagements/${engagementId}/report-layouts/${layoutId}`, layout);
            return data;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['report-layouts', variables.engagementId] });
            queryClient.invalidateQueries({ queryKey: ['report-layout', variables.engagementId, variables.layoutId] });
        },
    });
}

export function useDeleteReportLayout() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ engagementId, layoutId }: { engagementId: string; layoutId: string }) => {
            await api.delete(`/engagements/${engagementId}/report-layouts/${layoutId}`);
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['report-layouts', variables.engagementId] });
        },
    });
}

export function useImportLayoutFromTemplate() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ engagementId, templateId }: { engagementId: string; templateId: string }) => {
            const { data } = await api.post<ReportLayout>(`/engagements/${engagementId}/report-layouts/from-template/${templateId}`);
            return data;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['report-layouts', variables.engagementId] });
        },
    });
}

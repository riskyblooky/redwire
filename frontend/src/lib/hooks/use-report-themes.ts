import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface ReportTheme {
    id: string;
    name: string;
    description?: string;
    primary_color: string;
    secondary_color: string;
    header_text_color: string;
    body_text_color: string;
    table_header_bg: string;
    table_header_text: string;
    font_family: string;
    font_size_body: number;
    font_size_heading: number;
    logo_base64?: string;
    show_page_numbers: boolean;
    show_cover_page: boolean;
    cover_title: string;
    header_text?: string;
    footer_text?: string;
    page_size: string;
    is_default: boolean;
    created_at: string;
    updated_at: string;
}

export interface ReportThemeCreate {
    name: string;
    description?: string;
    primary_color?: string;
    secondary_color?: string;
    header_text_color?: string;
    body_text_color?: string;
    table_header_bg?: string;
    table_header_text?: string;
    font_family?: string;
    font_size_body?: number;
    font_size_heading?: number;
    logo_base64?: string;
    show_page_numbers?: boolean;
    show_cover_page?: boolean;
    cover_title?: string;
    header_text?: string;
    footer_text?: string;
    page_size?: string;
    is_default?: boolean;
}

export interface ReportThemeUpdate extends Partial<ReportThemeCreate> { }

export function useReportThemes() {
    return useQuery<ReportTheme[]>({
        queryKey: ['report-themes'],
        queryFn: async () => {
            const { data } = await api.get('/report-themes');
            return data;
        },
    });
}

export function useReportTheme(id: string | null) {
    return useQuery<ReportTheme>({
        queryKey: ['report-themes', id],
        queryFn: async () => {
            const { data } = await api.get(`/report-themes/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useCreateReportTheme() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: ReportThemeCreate) => {
            const { data: res } = await api.post('/report-themes', data);
            return res as ReportTheme;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-themes'] }),
    });
}

export function useUpdateReportTheme() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...data }: ReportThemeUpdate & { id: string }) => {
            const { data: res } = await api.put(`/report-themes/${id}`, data);
            return res as ReportTheme;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-themes'] }),
    });
}

export function useDeleteReportTheme() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/report-themes/${id}`);
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-themes'] }),
    });
}

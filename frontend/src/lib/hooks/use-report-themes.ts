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
    logo_base64?: string | null;
    logo_scale?: number | null;
    show_page_numbers: boolean;
    show_cover_page: boolean;
    cover_title: string;
    header_text?: string;
    footer_text?: string;
    page_size: string;
    is_default: boolean;
    // Deepened appearance controls (nullable; generator falls back to defaults)
    severity_critical_color?: string | null;
    severity_high_color?: string | null;
    severity_medium_color?: string | null;
    severity_low_color?: string | null;
    severity_info_color?: string | null;
    table_zebra_enabled?: boolean | null;
    table_alt_row_bg?: string | null;
    table_grid_color?: string | null;
    header_left?: string | null;
    header_center?: string | null;
    header_right?: string | null;
    footer_left?: string | null;
    footer_center?: string | null;
    footer_right?: string | null;
    show_page_x_of_y?: boolean | null;
    cover_template?: string | null;
    cover_background_base64?: string | null;
    cover_subtitle?: string | null;
    report_reference?: string | null;
    report_version?: string | null;
    show_evidence_filenames?: boolean | null;
    show_finding_severity_bar?: boolean | null;
    show_section_title_background?: boolean | null;
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
    logo_base64?: string | null;
    logo_scale?: number | null;
    show_page_numbers?: boolean;
    show_cover_page?: boolean;
    cover_title?: string;
    header_text?: string;
    footer_text?: string;
    page_size?: string;
    is_default?: boolean;
    severity_critical_color?: string | null;
    severity_high_color?: string | null;
    severity_medium_color?: string | null;
    severity_low_color?: string | null;
    severity_info_color?: string | null;
    table_zebra_enabled?: boolean | null;
    table_alt_row_bg?: string | null;
    table_grid_color?: string | null;
    header_left?: string | null;
    header_center?: string | null;
    header_right?: string | null;
    footer_left?: string | null;
    footer_center?: string | null;
    footer_right?: string | null;
    show_page_x_of_y?: boolean | null;
    cover_template?: string | null;
    cover_background_base64?: string | null;
    cover_subtitle?: string | null;
    report_reference?: string | null;
    report_version?: string | null;
    show_evidence_filenames?: boolean | null;
    show_finding_severity_bar?: boolean | null;
    show_section_title_background?: boolean | null;
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

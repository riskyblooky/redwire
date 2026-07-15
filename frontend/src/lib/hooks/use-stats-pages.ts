import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import type { LayoutItem } from '@/lib/hooks/use-dashboard-widgets';

// A stats page is a globally-shared tab on /stats. Its `layout` is
// page-owned (every viewer sees the same arrangement) and references the
// same global DashboardWidget definitions the dashboard uses.
export interface StatsPage {
    id: string;
    name: string;
    icon?: string | null;
    position: number;
    layout: LayoutItem[];
    is_system: boolean;
    is_active: boolean;
}

const KEY = ['stats-pages'];

export function useStatsPages() {
    return useQuery<StatsPage[]>({
        queryKey: KEY,
        queryFn: async () => (await api.get('/stats-pages')).data,
        staleTime: 30_000,
    });
}

export function useCreateStatsPage() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (data: { name: string; icon?: string; position?: number }) =>
            (await api.post('/stats-pages', data)).data as StatsPage,
        onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
    });
}

export function useUpdateStatsPage() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...updates }: { id: string } & Partial<Pick<StatsPage, 'name' | 'icon' | 'position' | 'is_active'>>) =>
            (await api.put(`/stats-pages/${id}`, updates)).data as StatsPage,
        onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
    });
}

export function useSaveStatsPageLayout() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, layout }: { id: string; layout: LayoutItem[] }) =>
            (await api.put(`/stats-pages/${id}/layout`, { layout })).data as StatsPage,
        onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
    });
}

export function useDeleteStatsPage() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => (await api.delete(`/stats-pages/${id}`)).data,
        onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
    });
}

export function useReorderStatsPages() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (pages: Array<{ id: string; position: number }>) =>
            (await api.post('/stats-pages/reorder', { pages })).data as StatsPage[],
        onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
    });
}

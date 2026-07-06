import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

export interface AutomationCondition {
    field: string;
    operator: string;
    value: string;
}

export interface AutomationAction {
    type: string;
    // notify_users
    user_ids?: string[];
    message?: string;
    // notify_role
    role?: string;
    // webhook
    url?: string;
    method?: string;
    headers?: Record<string, string>;
    body_template?: string;
    // email
    recipients?: string[];
    subject?: string;
    body?: string;
    // add_tags
    tag_ids?: string[];
}

export interface AutomationRule {
    id: string;
    name: string;
    description?: string;
    trigger_type: string;
    conditions: AutomationCondition[];
    actions: AutomationAction[];
    is_enabled: boolean;
    created_by: string;
    engagement_id?: string | null;
    owner_user_id?: string | null;
    is_personal?: boolean;
    created_at: string;
    updated_at: string;
    last_triggered_at?: string;
    trigger_count: number;
}

export interface TriggerType {
    value: string;
    label: string;
    icon: string;
    fields: string[];
}

export function useAutomations() {
    return useQuery<AutomationRule[]>({
        queryKey: ['automations'],
        queryFn: async () => {
            const { data } = await api.get('/automations');
            return data.rules;
        },
    });
}

export function useMyPersonalAutomations() {
    return useQuery<AutomationRule[]>({
        queryKey: ['automations', 'personal'],
        queryFn: async () => {
            const { data } = await api.get('/automations', { params: { scope: 'personal' } });
            return data.rules;
        },
    });
}

export function useTriggerTypes() {
    return useQuery<TriggerType[]>({
        queryKey: ['trigger-types'],
        queryFn: async () => {
            const { data } = await api.get('/automations/trigger-types');
            return data.trigger_types;
        },
    });
}

export function useCreateAutomation() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload: Partial<AutomationRule>) => {
            const { data } = await api.post('/automations', payload);
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    });
}

export function useUpdateAutomation() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: Partial<AutomationRule> & { id: string }) => {
            const { data } = await api.put(`/automations/${id}`, payload);
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    });
}

export function useDeleteAutomation() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/automations/${id}`);
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    });
}

export function useToggleAutomation() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            const { data } = await api.post(`/automations/${id}/toggle`);
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    });
}

export function useTriggerAutomation() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            const { data } = await api.post(`/automations/${id}/run`);
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
    });
}

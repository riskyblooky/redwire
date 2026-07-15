import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

export type CustomFieldEntity = 'asset' | 'testcase' | 'finding' | 'client' | 'engagement';

export type CustomFieldType =
    | 'text' | 'textarea' | 'number' | 'date' | 'boolean'
    | 'select' | 'multiselect' | 'url';

export interface CustomFieldDef {
    id: string;
    entity_type: CustomFieldEntity;
    field_key: string;
    label: string;
    field_type: CustomFieldType;
    options?: string[] | null;
    required: boolean;
    help_text?: string | null;
    placeholder?: string | null;
    position: number;
    show_in_list: boolean;
    show_in_report: boolean;
    is_active: boolean;
}

export type CustomFieldValues = Record<string, unknown>;

const key = (entity: CustomFieldEntity, includeInactive = false) =>
    ['custom-field-definitions', entity, includeInactive] as const;

/** Active definitions for an entity — what the forms/detail views render. */
export function useCustomFieldDefs(entity: CustomFieldEntity, includeInactive = false) {
    return useQuery<CustomFieldDef[]>({
        queryKey: key(entity, includeInactive),
        queryFn: async () => {
            const { data } = await api.get(`/custom-field-definitions/${entity}`, {
                params: includeInactive ? { include_inactive: true } : undefined,
            });
            return data;
        },
        staleTime: 60_000,
    });
}

function invalidateEntity(qc: ReturnType<typeof useQueryClient>, entity: CustomFieldEntity) {
    qc.invalidateQueries({ queryKey: ['custom-field-definitions', entity] });
}

export function useCreateCustomFieldDef(entity: CustomFieldEntity) {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (data: Partial<CustomFieldDef>) =>
            (await api.post(`/custom-field-definitions/${entity}`, data)).data as CustomFieldDef,
        onSuccess: () => invalidateEntity(qc, entity),
    });
}

export function useUpdateCustomFieldDef(entity: CustomFieldEntity) {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...updates }: { id: string } & Partial<CustomFieldDef>) =>
            (await api.put(`/custom-field-definitions/${entity}/${id}`, updates)).data as CustomFieldDef,
        onSuccess: () => invalidateEntity(qc, entity),
    });
}

export function useDeleteCustomFieldDef(entity: CustomFieldEntity) {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) =>
            (await api.delete(`/custom-field-definitions/${entity}/${id}`)).data,
        onSuccess: () => invalidateEntity(qc, entity),
    });
}

export function useReorderCustomFieldDefs(entity: CustomFieldEntity) {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (fields: Array<{ id: string; position: number }>) =>
            (await api.post(`/custom-field-definitions/${entity}/reorder`, { fields })).data as CustomFieldDef[],
        onSuccess: () => invalidateEntity(qc, entity),
    });
}

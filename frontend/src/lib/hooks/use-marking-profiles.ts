import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { useEngagement } from './use-engagements';

export type MarkingScheme = 'TLP_2_0' | 'IC_DOD' | 'CUSTOM';
export type MarkingEnforcement = 'OFF' | 'WARN' | 'BLOCK';

export const MARK_ANCHORS = [
    'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
    'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT',
    'CAPTION',
] as const;
export type MarkAnchor = typeof MARK_ANCHORS[number];

export interface MarkingLevel {
    abbreviation: string;
    full_name: string;
    rank: number;
    banner_color: string;
    text_color: string;
}

export interface MarkingProfile {
    id: string;
    name: string;
    description?: string;
    scheme: MarkingScheme;
    levels: MarkingLevel[];
    enforcement: MarkingEnforcement;
    image_mark_anchors: MarkAnchor[];
    table_mark_anchors: MarkAnchor[];
    inline_portion_marks?: boolean | null;
    table_per_row_marks: boolean;
    stamp_images: boolean;
    show_legend: boolean;
    distribution_statement?: string;
    static_heading_marks?: string | null;
    is_default: boolean;
    is_builtin: boolean;
    created_at: string;
    updated_at: string;
}

export interface MarkingProfileCreate {
    name: string;
    description?: string;
    scheme?: MarkingScheme;
    levels?: MarkingLevel[];
    enforcement?: MarkingEnforcement;
    image_mark_anchors?: MarkAnchor[];
    table_mark_anchors?: MarkAnchor[];
    inline_portion_marks?: boolean | null;
    table_per_row_marks?: boolean;
    stamp_images?: boolean;
    show_legend?: boolean;
    distribution_statement?: string;
    static_heading_marks?: string | null;
    is_default?: boolean;
}

export interface MarkingProfileUpdate extends Partial<MarkingProfileCreate> { }

export function useMarkingProfiles() {
    return useQuery<MarkingProfile[]>({
        queryKey: ['marking-profiles'],
        queryFn: async () => {
            const { data } = await api.get('/marking-profiles');
            return data;
        },
        staleTime: 30_000,
    });
}

/**
 * The marking profile that actually applies to an engagement — its OWN selected
 * profile, and only when that profile has real levels. Returns undefined when no
 * marking applies (no profile selected, or an empty one), so callers can hide
 * the whole classification-marking UI (card included), not just the picker.
 */
export function useEngagementMarkingProfile(engagementId: string | null | undefined) {
    const { data: engagement } = useEngagement(engagementId || '');
    const { data: profiles = [] } = useMarkingProfiles();
    if (!engagement?.marking_profile_id) return undefined;
    const profile = profiles.find((p) => p.id === engagement.marking_profile_id);
    return profile && profile.levels.length > 0 ? profile : undefined;
}

export function useMarkingProfile(id: string | null) {
    return useQuery<MarkingProfile>({
        queryKey: ['marking-profiles', id],
        queryFn: async () => {
            const { data } = await api.get(`/marking-profiles/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useCreateMarkingProfile() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: MarkingProfileCreate) => {
            const { data: res } = await api.post('/marking-profiles', data);
            return res as MarkingProfile;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['marking-profiles'] }),
    });
}

export function useUpdateMarkingProfile() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...data }: MarkingProfileUpdate & { id: string }) => {
            const { data: res } = await api.put(`/marking-profiles/${id}`, data);
            return res as MarkingProfile;
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['marking-profiles'] }),
    });
}

export function useDeleteMarkingProfile() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/marking-profiles/${id}`);
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['marking-profiles'] }),
    });
}

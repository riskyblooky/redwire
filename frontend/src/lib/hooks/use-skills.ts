import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

// ── Types ───────────────────────────────────────────────────────

export interface SkillCategory {
    id: string;
    name: string;
    color: string | null;
    sort_order: number;
    skills: Skill[];
}

export interface Skill {
    id: string;
    category_id: string;
    name: string;
    description: string | null;
    sort_order: number;
}

export interface UserSkill {
    skill_id: string;
    skill_name: string;
    category_id: string;
    category_name: string;
    level: number; // 0-3
    target_level: number | null; // when set, must equal level + 1
}

export interface FocusFitSkill {
    id: string;
    name: string;
}

export interface FocusFitMatch {
    user_id: string;
    full_name: string | null;
    username: string;
    profile_photo: string | null;
    matching_skills: FocusFitSkill[];
}

export interface EngagementFocusFit {
    engagement_id: string;
    matches: FocusFitMatch[];
}

export const MAX_GROWTH_FOCUSES = 3;

export interface EngagementSkill {
    skill_id: string;
    skill_name: string;
    category_id: string;
    category_name: string;
    min_level: number;
}

export const SKILL_LEVELS = [
    { value: 0, label: 'None', color: 'text-slate-500' },
    { value: 1, label: 'Beginner', color: 'text-blue-400' },
    { value: 2, label: 'Intermediate', color: 'text-amber-400' },
    { value: 3, label: 'Advanced', color: 'text-emerald-400' },
] as const;


// ── Categories ──────────────────────────────────────────────────

export function useSkillCategories() {
    return useQuery<SkillCategory[]>({
        queryKey: ['skill-categories'],
        queryFn: async () => {
            try {
                return (await api.get('/skills/categories')).data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useCreateSkillCategory() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (data: { name: string; color?: string; sort_order?: number }) =>
            (await api.post('/skills/categories', data)).data,
        onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-categories'] }),
    });
}

export function useUpdateSkillCategory() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...data }: { id: string; name?: string; color?: string; sort_order?: number }) =>
            (await api.put(`/skills/categories/${id}`, data)).data,
        onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-categories'] }),
    });
}

export function useDeleteSkillCategory() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => (await api.delete(`/skills/categories/${id}`)).data,
        onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-categories'] }),
    });
}


// ── Skills ──────────────────────────────────────────────────────

export function useCreateSkill() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (data: { category_id: string; name: string; description?: string; sort_order?: number }) =>
            (await api.post('/skills/skills', data)).data,
        onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-categories'] }),
    });
}

export function useUpdateSkill() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...data }: { id: string; name?: string; description?: string; category_id?: string; sort_order?: number }) =>
            (await api.put(`/skills/skills/${id}`, data)).data,
        onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-categories'] }),
    });
}

export function useDeleteSkill() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => (await api.delete(`/skills/skills/${id}`)).data,
        onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-categories'] }),
    });
}


// ── User Skills ─────────────────────────────────────────────────

export function useUserSkills(userId: string | undefined) {
    return useQuery<UserSkill[]>({
        queryKey: ['user-skills', userId],
        queryFn: async () => (await api.get(`/skills/users/${userId}`)).data,
        enabled: !!userId,
    });
}

export function useSetMySkills() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (skills: { skill_id: string; level: number; target_level?: number | null }[]) =>
            (await api.put('/skills/users/me', skills)).data,
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['user-skills'] });
            qc.invalidateQueries({ queryKey: ['focus-fit'] });
        },
    });
}

export function useFocusFit(enabled: boolean = true) {
    return useQuery<EngagementFocusFit[]>({
        queryKey: ['focus-fit'],
        queryFn: async () => {
            try {
                return (await api.get('/skills/focus-fit')).data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        enabled,
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useAverageSkills() {
    return useQuery<UserSkill[]>({
        queryKey: ['average-skills'],
        queryFn: async () => (await api.get('/skills/users/average')).data,
    });
}


// ── Engagement Skills ───────────────────────────────────────────

export function useEngagementSkills(engagementId: string | undefined) {
    return useQuery<EngagementSkill[]>({
        queryKey: ['engagement-skills', engagementId],
        queryFn: async () => {
            try {
                return (await api.get(`/skills/engagements/${engagementId}`)).data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        enabled: !!engagementId,
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useSetEngagementSkills() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ engagementId, skills }: { engagementId: string; skills: { skill_id: string; min_level: number }[] }) =>
            (await api.put(`/skills/engagements/${engagementId}`, skills)).data,
        onSuccess: (_data, vars) => {
            qc.invalidateQueries({ queryKey: ['engagement-skills', vars.engagementId] });
        },
    });
}


// ── Seed ────────────────────────────────────────────────────────

export function useSeedSkills() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async () => (await api.post('/skills/seed')).data,
        onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-categories'] }),
    });
}

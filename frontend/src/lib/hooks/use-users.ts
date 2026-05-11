import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { Group } from './use-rbac';

export interface User {
    id: string;
    username: string;
    email: string;
    full_name: string | null;
    profile_photo: string | null;
    role: string;
    is_active: boolean;
    created_at: string;
    last_login: string | null;
    last_active: string | null;
    groups: Group[];
}

export interface UserCreate {
    username: string;
    email: string;
    password: string;
    full_name?: string;
    role: string;
}

export interface UserUpdate {

    full_name?: string;
    role?: string;
    is_active?: boolean;
    group_ids?: string[];
}

export function useUsers() {
    return useQuery({
        queryKey: ['users'],
        queryFn: async () => {
            const { data } = await api.get<User[]>('/users');
            return data;
        },
    });
}

export function useUpdateUser() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, ...update }: UserUpdate & { id: string }) => {
            const { data } = await api.put<User>(`/users/${id}`, update);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
        },
    });
}

export function useCreateUser() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (user: UserCreate) => {
            const { data } = await api.post<User>('/users', user);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
        },
    });
}


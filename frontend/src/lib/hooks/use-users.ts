import { useQuery } from '@tanstack/react-query';
import { fetchAllPages } from '../fetch-all';
import type { Group } from './use-admin-permissions';

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

export function useUsers(enabled: boolean = true) {
    return useQuery({
        queryKey: ['users'],
        queryFn: async () => {
            // Every active user: a bare request returned the first 100.
            return fetchAllPages<User>('/users');
        },
        enabled,
    });
}

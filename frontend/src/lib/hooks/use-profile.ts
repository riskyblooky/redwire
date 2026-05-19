import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { useAuthStore } from '@/stores/auth-store';

import type { ThemePreference, ThemePalette } from '@/lib/types';

export interface ProfileUpdate {
    full_name?: string;
    email?: string;
    theme_preference?: ThemePreference;
    theme_palette?: ThemePalette;
    theme_accent_custom?: string | null;
    // Step-up auth — only required when changing `email`
    // (GHSA-hc9w-hggj-r52w).
    current_password?: string;
    totp_code?: string;
}

export interface PasswordUpdate {
    old_password: string;
    new_password: string;
    totp_code?: string;
}

export function useUpdateProfile() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: ProfileUpdate) => {
            const { data: response } = await api.put('/users/me', data);
            return response;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
            useAuthStore.getState().setUser(data);
        }
    });
}

export function useUpdatePassword() {
    return useMutation({
        mutationFn: async (data: PasswordUpdate) => {
            const { data: response } = await api.put('/users/me/password', data);
            return response;
        }
    });
}

export function useUploadProfilePhoto() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (file: File) => {
            const formData = new FormData();
            formData.append('file', file);
            const { data: response } = await api.post('/users/me/photo', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });
            return response;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
            useAuthStore.getState().setUser(data);
        }
    });
}

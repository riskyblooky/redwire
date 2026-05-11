import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface WordlistMeta {
    id: string;
    filename: string;
    entry_count: number;
    status: 'PROCESSING' | 'READY' | 'FAILED';
    error_message?: string;
    uploaded_by?: string;
    created_at: string;
}

export interface WordlistStatusResponse {
    bloom_loaded: boolean;
    bloom_loading: boolean;
    bloom_count: number;
    wordlists: WordlistMeta[];
}

export interface CheckPasswordResponse {
    found: boolean;
}

export interface LookupHashResponse {
    found: boolean;
    password?: string;
    hash_type?: string;
    note?: string;
}

export function useWordlistStatus() {
    return useQuery({
        queryKey: ['wordlist', 'status'],
        queryFn: async () => {
            const { data } = await api.get<WordlistStatusResponse>('/wordlist/status');
            return data;
        },
        refetchInterval: (query) => {
            const data = query.state.data;
            // Poll while any wordlist is PROCESSING or bloom filter is loading
            if (data?.wordlists?.some(w => w.status === 'PROCESSING') || data?.bloom_loading) {
                return 3000;
            }
            return false;
        },
    });
}

export function useCheckPassword() {
    return useMutation({
        mutationFn: async (password: string) => {
            const { data } = await api.post<CheckPasswordResponse>('/wordlist/check-password', { password });
            return data;
        },
    });
}

export function useLookupHash() {
    return useMutation({
        mutationFn: async (hash: string) => {
            const { data } = await api.post<LookupHashResponse>('/wordlist/lookup-hash', { hash });
            return data;
        },
    });
}

export function useUploadWordlist() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (file: File) => {
            const formData = new FormData();
            formData.append('file', file);
            const { data } = await api.post('/wordlist/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['wordlist', 'status'] });
        },
    });
}

export function useDeleteWordlist() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (wordlistId: string) => {
            await api.delete(`/wordlist/${wordlistId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['wordlist', 'status'] });
        },
    });
}

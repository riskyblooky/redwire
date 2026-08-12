import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

export interface ChangelogEntry {
    version: string;
    date: string;
    body: string;
}

export interface ChangelogResult {
    current_version: string;
    entries: ChangelogEntry[];
}

export interface UnseenChangelogResult {
    has_unseen: boolean;
    current_version: string;
    entries: ChangelogEntry[];
}

/** Full release history (for the /changelog page). */
export function useChangelog() {
    return useQuery<ChangelogResult>({
        queryKey: ['changelog'],
        queryFn: async () => (await api.get('/changelog')).data,
        staleTime: 5 * 60_000,
    });
}

/** Releases this user hasn't seen yet (drives the What's New modal). Fetches
 *  once per session; a null-last-seen user is silently marked seen server-side. */
export function useUnseenChangelog() {
    return useQuery<UnseenChangelogResult>({
        queryKey: ['changelog', 'unseen'],
        queryFn: async () => (await api.get('/changelog/unseen')).data,
        staleTime: Infinity,
        refetchOnWindowFocus: false,
    });
}

export function useMarkChangelogSeen() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            await api.post('/changelog/seen');
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['changelog', 'unseen'] });
        },
    });
}

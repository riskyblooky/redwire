'use client';

import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

export interface HelpDocMeta {
    slug: string;
    title: string;
    description: string;
    admin_only: boolean;
}

export interface HelpDoc {
    slug: string;
    title: string;
    content: string;
}

/** Guides the current user may read (admin guides are hidden server-side). */
export function useHelpDocs() {
    return useQuery<HelpDocMeta[]>({
        queryKey: ['help', 'docs'],
        queryFn: async () => (await api.get<HelpDocMeta[]>('/help/docs')).data,
        staleTime: 5 * 60_000,
    });
}

/** One guide's rendered Markdown content. */
export function useHelpDoc(slug: string | null | undefined) {
    return useQuery<HelpDoc>({
        queryKey: ['help', 'doc', slug],
        queryFn: async () => (await api.get<HelpDoc>(`/help/docs/${slug}`)).data,
        enabled: !!slug,
        staleTime: 5 * 60_000,
    });
}

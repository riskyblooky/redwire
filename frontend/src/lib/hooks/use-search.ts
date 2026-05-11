import { useQuery } from '@tanstack/react-query';
import api from '../api';

export interface SearchResultItem {
    id: string;
    title: string;
    subtitle: string;
    status?: string;
    description?: string;
    extra?: Record<string, string>;
    fields?: Record<string, string>;
    engagement_name?: string;
    url: string;
    match_count?: number;
}

export interface SearchResultCategory {
    category: string;
    items: SearchResultItem[];
}

export interface SearchResponse {
    query: string;
    parsed_terms: string[];
    results: SearchResultCategory[];
    total: number;
}

export function useGlobalSearch(query: string, sort: string = 'relevance') {
    return useQuery({
        queryKey: ['global-search', query, sort],
        queryFn: async () => {
            const { data } = await api.get<SearchResponse>('/search', {
                params: { q: query, limit: 10, sort },
            });
            return data;
        },
        enabled: query.trim().length > 0,
        staleTime: 30_000,
    });
}

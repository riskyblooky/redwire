import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export type ReviewStatus = 'APPROVED' | 'CHANGES_REQUESTED';

export interface FindingReview {
    id: string;
    finding_id: string;
    reviewer_id: string;
    reviewer_username?: string | null;
    reviewer_full_name?: string | null;
    status: ReviewStatus;
    created_at: string;
    updated_at: string;
}

export interface FindingReviewSummary {
    reviews: FindingReview[];
    my_review: FindingReview | null;
    approvals: number;
    changes_requested: number;
    required: boolean;
    min_approvals: number;
    satisfied: boolean;
    author_id: string;
    is_author: boolean;
}

export function useFindingReviews(findingId: string | undefined) {
    return useQuery<FindingReviewSummary>({
        queryKey: ['findings', findingId, 'reviews'],
        queryFn: async () => (await api.get(`/findings/${findingId}/reviews`)).data,
        enabled: !!findingId,
        staleTime: 30_000,
    });
}

export function useSubmitFindingReview(findingId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (body: { status: ReviewStatus }) =>
            (await api.post(`/findings/${findingId}/reviews`, body)).data,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['findings', findingId, 'reviews'] });
        },
    });
}

export function useDeleteMyFindingReview(findingId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async () => (await api.delete(`/findings/${findingId}/reviews/mine`)).data,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['findings', findingId, 'reviews'] });
        },
    });
}

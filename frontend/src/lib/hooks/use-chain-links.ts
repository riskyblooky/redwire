import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export type ChainNodeType = 'testcase' | 'finding' | 'vault_item';

export interface ChainNodeRef {
    type: ChainNodeType;
    id: string;
    label: string | null;      // null when the entity no longer resolves (dangling)
    sub?: string | null;
    severity?: string | null;
    status?: string | null;
}

export interface ChainNeighbor {
    link_id: string;
    relation: string;
    note: string | null;
    node: ChainNodeRef;
}

export interface ChainLinksForEntity {
    upstream: ChainNeighbor[];    // things that led to this entity (its causes)
    downstream: ChainNeighbor[];  // things this entity led to (its effects)
    candidates: ChainNodeRef[];   // flat-linked items not yet chained — promotable
}

export interface CreateChainLinkInput {
    source_type: ChainNodeType;
    source_id: string;
    target_type: ChainNodeType;
    target_id: string;
    note?: string | null;
}

const forKey = (engagementId: string, entityType: string, entityId: string) =>
    ['chain-links', engagementId, entityType, entityId] as const;

/** Upstream (causes) + downstream (effects) chain edges for one entity. */
export function useChainLinksFor(engagementId: string, entityType: ChainNodeType, entityId: string) {
    return useQuery<ChainLinksForEntity>({
        queryKey: forKey(engagementId, entityType, entityId),
        queryFn: async () => {
            const res = await api.get(
                `/engagements/${engagementId}/chain-links/for/${entityType}/${entityId}`,
            );
            return res.data;
        },
        enabled: !!engagementId && !!entityType && !!entityId,
        staleTime: 30_000,
    });
}

function useInvalidateChain(engagementId: string) {
    const qc = useQueryClient();
    return () => {
        // Broad partial-match invalidation covers every per-entity key.
        qc.invalidateQueries({ queryKey: ['chain-links', engagementId] });
        qc.invalidateQueries({ queryKey: ['attack-graph', engagementId] });
    };
}

export function useCreateChainLink(engagementId: string) {
    const invalidate = useInvalidateChain(engagementId);
    return useMutation({
        mutationFn: async (input: CreateChainLinkInput) => {
            const res = await api.post(`/engagements/${engagementId}/chain-links`, input);
            return res.data;
        },
        onSuccess: invalidate,
    });
}

export function useUpdateChainLinkNote(engagementId: string) {
    const invalidate = useInvalidateChain(engagementId);
    return useMutation({
        mutationFn: async ({ linkId, note }: { linkId: string; note: string | null }) => {
            const res = await api.patch(
                `/engagements/${engagementId}/chain-links/${linkId}`,
                { note },
            );
            return res.data;
        },
        onSuccess: invalidate,
    });
}

export function useDeleteChainLink(engagementId: string) {
    const invalidate = useInvalidateChain(engagementId);
    return useMutation({
        mutationFn: async (linkId: string) => {
            await api.delete(`/engagements/${engagementId}/chain-links/${linkId}`);
        },
        onSuccess: invalidate,
    });
}

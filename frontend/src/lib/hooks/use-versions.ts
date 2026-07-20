import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

export interface VersionSummary {
    id: string;
    version: number;
    changed_fields: string[];
    changed_by: string;
    changed_by_username: string | null;
    created_at: string;
}

export interface VersionSnapshot extends VersionSummary {
    snapshot: Record<string, any>;
}

/**
 * Fetch list of all versions for an entity.
 */
export function useVersionHistory(entityType: 'finding' | 'testcase', entityId: string) {
    const basePath = entityType === 'finding' ? 'findings' : 'testcases';
    return useQuery<VersionSummary[]>({
        queryKey: ['versions', entityType, entityId],
        queryFn: async () => {
            const { data } = await api.get(`/${basePath}/${entityId}/versions`);
            return data;
        },
        enabled: !!entityId,
    });
}

/**
 * Fetch the full snapshot of a specific version.
 */
export function useVersionSnapshot(
    entityType: 'finding' | 'testcase',
    entityId: string,
    versionId: string | null,
) {
    const basePath = entityType === 'finding' ? 'findings' : 'testcases';
    return useQuery<VersionSnapshot>({
        queryKey: ['version-snapshot', entityType, entityId, versionId],
        queryFn: async () => {
            const { data } = await api.get(`/${basePath}/${entityId}/versions/${versionId}`);
            return data;
        },
        enabled: !!entityId && !!versionId,
    });
}

/** Restore an entity to a prior version. The backend snapshots the current
 *  state first, so this is reversible. */
export function useRestoreVersion(entityType: 'finding' | 'testcase', entityId: string) {
    const qc = useQueryClient();
    const basePath = entityType === 'finding' ? 'findings' : 'testcases';
    return useMutation({
        mutationFn: async (versionId: string) => {
            const { data } = await api.post(`/${basePath}/${entityId}/versions/${versionId}/restore`);
            return data;
        },
        onSuccess: () => {
            // Refresh the entity (list + detail via partial match) and its history.
            qc.invalidateQueries({ queryKey: [basePath] });
            qc.invalidateQueries({ queryKey: [entityType, entityId] });
            qc.invalidateQueries({ queryKey: ['versions', entityType, entityId] });
        },
    });
}

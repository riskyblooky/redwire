'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

// ─── Generic factory ────────────────────────────────────────────────────────

function createLinkHook(entityPath: string, resourcePath: string) {
    return function useLinkEntityToResource() {
        const queryClient = useQueryClient();
        return useMutation({
            mutationFn: async ({ entityId, resourceId }: { entityId: string; resourceId: string }) => {
                await api.post(`${entityPath}/${entityId}/${resourcePath}/${resourceId}`);
            },
            onSuccess: () => {
                queryClient.invalidateQueries({ queryKey: [entityPath.replace('/', '')] });
                queryClient.invalidateQueries({ queryKey: ['findings'] });
                queryClient.invalidateQueries({ queryKey: ['testcases'] });
                queryClient.invalidateQueries({ queryKey: ['assets'] });
            },
        });
    };
}

function createUnlinkHook(entityPath: string, resourcePath: string) {
    return function useUnlinkEntityFromResource() {
        const queryClient = useQueryClient();
        return useMutation({
            mutationFn: async ({ entityId, resourceId }: { entityId: string; resourceId: string }) => {
                await api.delete(`${entityPath}/${entityId}/${resourcePath}/${resourceId}`);
            },
            onSuccess: () => {
                queryClient.invalidateQueries({ queryKey: [entityPath.replace('/', '')] });
                queryClient.invalidateQueries({ queryKey: ['findings'] });
                queryClient.invalidateQueries({ queryKey: ['testcases'] });
                queryClient.invalidateQueries({ queryKey: ['assets'] });
            },
        });
    };
}

// ─── Finding links ───────────────────────────────────────────────────────────

export const useLinkFindingToTestCase   = createLinkHook('/findings', 'testcases');
export const useUnlinkFindingFromTestCase = createUnlinkHook('/findings', 'testcases');

export const useLinkFindingToVaultItem   = createLinkHook('/findings', 'vault-items');
export const useUnlinkFindingFromVaultItem = createUnlinkHook('/findings', 'vault-items');

export const useLinkFindingToCleanup   = createLinkHook('/findings', 'cleanup-artifacts');
export const useUnlinkFindingFromCleanup = createUnlinkHook('/findings', 'cleanup-artifacts');

// ─── TestCase links ──────────────────────────────────────────────────────────

export const useLinkTestCaseToFinding   = createLinkHook('/testcases', 'findings');
export const useUnlinkTestCaseFromFinding = createUnlinkHook('/testcases', 'findings');

export const useLinkTestCaseToAsset   = createLinkHook('/testcases', 'assets');
export const useUnlinkTestCaseFromAsset = createUnlinkHook('/testcases', 'assets');

export const useLinkTestCaseToVaultItem   = createLinkHook('/testcases', 'vault-items');
export const useUnlinkTestCaseFromVaultItem = createUnlinkHook('/testcases', 'vault-items');

export const useLinkTestCaseToCleanup   = createLinkHook('/testcases', 'cleanup-artifacts');
export const useUnlinkTestCaseFromCleanup = createUnlinkHook('/testcases', 'cleanup-artifacts');

// ─── Asset links ─────────────────────────────────────────────────────────────

export const useLinkAssetToFinding   = createLinkHook('/assets', 'findings');
export const useUnlinkAssetFromFinding = createUnlinkHook('/assets', 'findings');

export const useLinkAssetToTestCase   = createLinkHook('/assets', 'testcases');
export const useUnlinkAssetFromTestCase = createUnlinkHook('/assets', 'testcases');

export const useLinkAssetToVaultItem   = createLinkHook('/assets', 'vault-items');
export const useUnlinkAssetFromVaultItem = createUnlinkHook('/assets', 'vault-items');

export const useLinkAssetToCleanup   = createLinkHook('/assets', 'cleanup-artifacts');
export const useUnlinkAssetFromCleanup = createUnlinkHook('/assets', 'cleanup-artifacts');

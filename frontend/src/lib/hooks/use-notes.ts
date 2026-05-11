'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

export interface LinkedResourceRef {
    id: string;
    title: string;
}

export interface LinkedVaultRef {
    id: string;
    name: string;
    item_type: string;
}

export interface LinkedCleanupRef {
    id: string;
    title: string;
    artifact_type: string;
}

export interface Note {
    id: string;
    engagement_id: string;
    parent_id?: string | null;
    title: string;
    content: string;
    created_by: string;
    created_by_username?: string;
    created_by_profile_photo?: string;
    updated_by?: string;
    updated_by_username?: string;
    created_at: string;
    updated_at: string;
    linked_findings: LinkedResourceRef[];
    linked_testcases: LinkedResourceRef[];
    linked_assets: LinkedResourceRef[];
    linked_vault_items: LinkedVaultRef[];
    linked_cleanup_artifacts: LinkedCleanupRef[];
}

export function useNotes(engagementId: string) {
    return useQuery({
        queryKey: ['notes', engagementId],
        queryFn: async () => {
            const { data } = await api.get<Note[]>(`/engagements/${engagementId}/notes`);
            return data;
        },
        enabled: !!engagementId,
    });
}

export function useNote(noteId: string) {
    return useQuery({
        queryKey: ['note', noteId],
        queryFn: async () => {
            const { data } = await api.get<Note>(`/notes/${noteId}`);
            return data;
        },
        enabled: !!noteId,
    });
}

export function useCreateNote() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ engagementId, title, content, parentId }: { engagementId: string; title: string; content?: string; parentId?: string | null }) => {
            const { data } = await api.post<Note>(`/engagements/${engagementId}/notes`, { title, content, parent_id: parentId || null });
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['notes', data.engagement_id] });
        },
    });
}

export function useUpdateNote() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...updates }: { id: string; title?: string; content?: string }) => {
            const { data } = await api.patch<Note>(`/notes/${id}`, updates);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['notes', data.engagement_id] });
            queryClient.invalidateQueries({ queryKey: ['note', data.id] });
        },
    });
}

export function useDeleteNote() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, engagementId }: { id: string; engagementId: string }) => {
            await api.delete(`/notes/${id}`);
            return { id, engagementId };
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['notes', data.engagementId] });
        },
    });
}

// ─── Link / Unlink hooks ──────────────────────────────────────────────

function createNoteLinkHook(resourcePath: string) {
    return function useLinkNoteToResource() {
        const queryClient = useQueryClient();
        return useMutation({
            mutationFn: async ({ noteId, resourceId }: { noteId: string; resourceId: string }) => {
                await api.post(`/notes/${noteId}/${resourcePath}/${resourceId}`);
            },
            onSuccess: () => {
                queryClient.invalidateQueries({ queryKey: ['notes'] });
            },
        });
    };
}

function createNoteUnlinkHook(resourcePath: string) {
    return function useUnlinkNoteFromResource() {
        const queryClient = useQueryClient();
        return useMutation({
            mutationFn: async ({ noteId, resourceId }: { noteId: string; resourceId: string }) => {
                await api.delete(`/notes/${noteId}/${resourcePath}/${resourceId}`);
            },
            onSuccess: () => {
                queryClient.invalidateQueries({ queryKey: ['notes'] });
            },
        });
    };
}

export const useLinkNoteToFinding = createNoteLinkHook('findings');
export const useUnlinkNoteFromFinding = createNoteUnlinkHook('findings');

export const useLinkNoteToTestCase = createNoteLinkHook('testcases');
export const useUnlinkNoteFromTestCase = createNoteUnlinkHook('testcases');

export const useLinkNoteToAsset = createNoteLinkHook('assets');
export const useUnlinkNoteFromAsset = createNoteUnlinkHook('assets');

export const useLinkNoteToVaultItem = createNoteLinkHook('vault-items');
export const useUnlinkNoteFromVaultItem = createNoteUnlinkHook('vault-items');

export const useLinkNoteToCleanupArtifact = createNoteLinkHook('cleanup-artifacts');
export const useUnlinkNoteFromCleanupArtifact = createNoteUnlinkHook('cleanup-artifacts');

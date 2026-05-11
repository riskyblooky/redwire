'use client';

import { useAuthStore } from '@/stores/auth-store';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

/**
 * Hook to fetch user's global (site-wide) permissions from the backend.
 */
function useGlobalPermissionsQuery() {
    const { user } = useAuthStore();

    return useQuery<string[]>({
        queryKey: ['global-permissions', user?.id],
        queryFn: async () => {
            const response = await api.get('/users/me/permissions');
            return response.data;
        },
        enabled: !!user,
        staleTime: 1000 * 60 * 5, // Cache for 5 minutes
    });
}

/**
 * Hook to check if the current user has a specific global permission.
 * 
 * @param permission - The permission string to check (e.g., 'intel_create', 'intel_manage_feeds')
 * @returns boolean indicating if the user has the permission
 */
export function useGlobalPermission(permission: string): boolean {
    const { user } = useAuthStore();
    const { data: permissions = [], isLoading } = useGlobalPermissionsQuery();

    // Admins and Team Leads have all permissions
    if (user?.role === 'admin' || user?.role === 'read_only_admin' || user?.role === 'team_lead') {
        return true;
    }

    if (isLoading) return false;

    return permissions.includes(permission);
}

/**
 * Hook to fetch user's permissions for a specific engagement from the backend.
 */
function useEngagementPermissions(engagementId: string | undefined) {
    const { user } = useAuthStore();

    return useQuery<string[]>({
        queryKey: ['engagement-permissions', engagementId, user?.id],
        queryFn: async () => {
            if (!engagementId) return [];
            const response = await api.get(`/engagements/${engagementId}/my-permissions`);
            return response.data;
        },
        enabled: !!engagementId && !!user,
        staleTime: 1000 * 60 * 5, // Cache for 5 minutes
    });
}

/**
 * Hook to check if the current user has a specific permission for an engagement.
 * 
 * @param engagementId - The engagement ID to check permissions for
 * @param permission - The permission string to check (e.g., 'finding_edit', 'asset_delete_any')
 * @returns boolean indicating if the user has the permission
 */
export function usePermission(engagementId: string | undefined, permission: string): boolean {
    const { user } = useAuthStore();
    const { data: permissions = [], isLoading } = useEngagementPermissions(engagementId);

    // Admins and Team Leads have all permissions
    if (user?.role === 'admin' || user?.role === 'read_only_admin' || user?.role === 'team_lead') {
        return true;
    }

    // If still loading or no engagement ID, deny permission
    if (isLoading || !engagementId) {
        return false;
    }

    // Check if user has the specific permission
    return permissions.includes(permission);
}

/**
 * Hook to check multiple permissions at once.
 * 
 * @param engagementId - The engagement ID to check permissions for
 * @param permissionList - Array of permission strings to check
 * @returns Object with permission strings as keys and boolean values
 */
export function usePermissions(
    engagementId: string | undefined,
    permissionList: string[]
): Record<string, boolean> {
    const { user } = useAuthStore();
    const { data: userPermissions = [], isLoading } = useEngagementPermissions(engagementId);

    // Handle undefined permissions
    if (!permissionList || permissionList.length === 0) {
        return {};
    }

    // Admins and Team Leads have all permissions
    if (user?.role === 'admin' || user?.role === 'read_only_admin' || user?.role === 'team_lead') {
        return permissionList.reduce((acc, perm) => ({ ...acc, [perm]: true }), {});
    }

    // If still loading or no engagement ID, deny all permissions
    if (isLoading || !engagementId) {
        return permissionList.reduce((acc, perm) => ({ ...acc, [perm]: false }), {});
    }

    // Check each permission
    return permissionList.reduce((acc, perm) => ({
        ...acc,
        [perm]: userPermissions.includes(perm)
    }), {});
}

/**
 * Hook to check if user can edit a specific resource.
 * Handles the ANY permission model where owners need base permission
 * and non-owners need ANY permission.
 * 
 * @param engagementId - The engagement ID
 * @param resourceType - Type of resource ('finding', 'asset', 'testcase', 'evidence', 'vault')
 * @param createdBy - User ID of the resource creator
 * @returns boolean indicating if the user can edit the resource
 */
export function useCanEdit(
    engagementId: string | undefined,
    resourceType: 'finding' | 'asset' | 'testcase' | 'evidence' | 'vault' | 'engagement' | 'discussion' | 'note' | 'cleanup',
    createdBy: string | undefined
): boolean {
    const { user } = useAuthStore();
    const { data: permissions = [], isLoading } = useEngagementPermissions(engagementId);

    // Admins and Team Leads can edit anything (read-only admins cannot)
    if (user?.role === 'admin' || user?.role === 'team_lead') {
        return true;
    }

    // If still loading or no engagement ID, deny permission
    if (isLoading || !engagementId) {
        return false;
    }

    const isOwner = user?.id === createdBy;
    const basePermission = `${resourceType}_edit`;

    // Special case for engagement: it doesn't use owner/any distinction in the same way
    // Anyone with engagement_edit can edit it
    if (resourceType === 'engagement') {
        return permissions.includes(basePermission);
    }

    const anyPermission = `${resourceType}_edit_any`;

    // Owner needs base permission, non-owner needs ANY permission
    if (isOwner) {
        return permissions.includes(basePermission);
    } else {
        return permissions.includes(anyPermission);
    }
}

/**
 * Hook to check if user can delete a specific resource.
 * Handles the ANY permission model where owners need base permission
 * and non-owners need ANY permission.
 * 
 * @param engagementId - The engagement ID
 * @param resourceType - Type of resource ('finding', 'asset', 'testcase', 'evidence', 'vault', 'engagement')
 * @param createdBy - User ID of the resource creator
 * @returns boolean indicating if the user can delete the resource
 */
export function useCanDelete(
    engagementId: string | undefined,
    resourceType: 'finding' | 'asset' | 'testcase' | 'evidence' | 'vault' | 'engagement' | 'discussion' | 'note' | 'cleanup',
    createdBy: string | undefined
): boolean {
    const { user } = useAuthStore();
    const { data: permissions = [], isLoading } = useEngagementPermissions(engagementId);

    // Admins and Team Leads can delete anything (read-only admins cannot)
    if (user?.role === 'admin' || user?.role === 'team_lead') {
        return true;
    }

    // If still loading or no engagement ID, deny permission
    if (isLoading || !engagementId) {
        return false;
    }

    const isOwner = user?.id === createdBy;
    const basePermission = `${resourceType}_delete`;

    // Special case for engagement: it doesn't use owner/any distinction in the same way
    if (resourceType === 'engagement') {
        return permissions.includes(basePermission);
    }

    const anyPermission = `${resourceType}_delete_any`;

    // Owner needs base permission, non-owner needs ANY permission
    if (isOwner) {
        return permissions.includes(basePermission);
    } else {
        return permissions.includes(anyPermission);
    }
}

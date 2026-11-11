'use client';

import React, { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { AccessDenied } from '@/components/ui/access-denied';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { useGlobalPermissions } from '@/lib/hooks/use-permissions';

interface RequirePermissionProps {
    /** Global permission the page needs (e.g. 'remediation_view'). */
    permission: string;
    /** Page name for the refusal message. */
    page: string;
    children: ReactNode;
}

/**
 * Gate a main-nav page on its view permission. The sidebar already hides the
 * tab without it; this covers a direct link or a bookmarked URL. The list
 * from /users/me/permissions is effective (admin bypasses included), so no
 * role check is needed here.
 */
export function RequirePermission({ permission, page, children }: RequirePermissionProps) {
    // isPending, not isLoading: the query is disabled until the user has
    // loaded, and a disabled v5 query reports isLoading=false.
    const { data, isPending } = useGlobalPermissions();

    if (isPending) {
        return (
            <DashboardLayout>
                <div className="flex h-[60vh] items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    // A failed fetch counts as no permissions (refuse rather than spin).
    if (!(data ?? []).includes(permission)) {
        return (
            <DashboardLayout>
                <div className="flex h-[calc(100vh-200px)] items-center justify-center">
                    <AccessDenied
                        title={`No access to ${page}`}
                        message={`You need the '${permission}' permission to open ${page}. Ask an administrator to grant it to one of your groups.`}
                        backPath="/dashboard"
                    />
                </div>
            </DashboardLayout>
        );
    }

    return <>{children}</>;
}

'use client';

import React, { ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/types';
import { Loader2 } from 'lucide-react';
import { AccessDenied } from '@/components/ui/access-denied';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { useGlobalPermissions } from '@/lib/hooks/use-permissions';
import { ADMIN_SURFACE_PERMISSIONS } from '@/lib/admin-tabs';

interface AdminGuardProps {
    children: ReactNode;
}

export function AdminGuard({ children }: AdminGuardProps) {
    const { user, isLoading } = useAuthStore();
    // Admin roles bypass; other users may enter if they hold a delegatable
    // admin-surface permission (the page then shows only their tabs).
    const isAdminView = user?.role === UserRole.ADMIN || user?.role === UserRole.READ_ONLY_ADMIN;
    const { data: myPerms = [], isLoading: permsLoading } = useGlobalPermissions();

    if (isLoading || (!isAdminView && permsLoading)) {
        return (
            <DashboardLayout>
                <div className="flex h-[60vh] items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    const hasAdminSurface = isAdminView || ADMIN_SURFACE_PERMISSIONS.some((p) => myPerms.includes(p));
    if (!hasAdminSurface) {
        return (
            <DashboardLayout>
                <div className="flex h-[calc(100vh-200px)] items-center justify-center">
                    <AccessDenied
                        title="Administrative Access Required"
                        message="This area contains administrative controls. You need an admin role or a delegated management permission to access it."
                        backPath="/dashboard"
                    />
                </div>
            </DashboardLayout>
        );
    }

    return <>{children}</>;
}

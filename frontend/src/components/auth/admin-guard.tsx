'use client';

import React, { ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/types';
import { Loader2 } from 'lucide-react';
import { AccessDenied } from '@/components/ui/access-denied';
import DashboardLayout from '@/components/layout/dashboard-layout';

interface AdminGuardProps {
    children: ReactNode;
}

export function AdminGuard({ children }: AdminGuardProps) {
    const { user, isLoading } = useAuthStore();

    if (isLoading) {
        return (
            <DashboardLayout>
                <div className="flex h-[60vh] items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    // Read-only admins can VIEW admin pages but write actions are gated
    // separately by the backend (and individual UI controls).
    if (user?.role !== UserRole.ADMIN && user?.role !== UserRole.READ_ONLY_ADMIN) {
        return (
            <DashboardLayout>
                <div className="flex h-[calc(100vh-200px)] items-center justify-center">
                    <AccessDenied
                        title="Administrative Access Required"
                        message="The requested page contains sensitive administrative controls. Only users with the Admin role can access this area."
                        backPath="/dashboard"
                    />
                </div>
            </DashboardLayout>
        );
    }

    return <>{children}</>;
}

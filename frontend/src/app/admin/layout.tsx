'use client';

import { AdminGuard } from '@/components/auth/admin-guard';
import { ReactNode } from 'react';

export default function AdminLayout({ children }: { children: ReactNode }) {
    return (
        <AdminGuard>
            {children}
        </AdminGuard>
    );
}

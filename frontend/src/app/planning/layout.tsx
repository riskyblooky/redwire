'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Planning tab shows only with planning_view; this refuses direct links too
// (every page under /planning).
export default function PlanningLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="planning_view" page="Planning">
            {children}
        </RequirePermission>
    );
}

'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Stats tab shows only with stats_view; this refuses direct links too
// (every page under /stats).
export default function StatsLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="stats_view" page="Stats">
            {children}
        </RequirePermission>
    );
}

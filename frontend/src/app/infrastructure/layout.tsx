'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Infrastructure tab shows only with infra_view; this refuses direct links too
// (every page under /infrastructure).
export default function InfrastructureLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="infra_view" page="Infrastructure">
            {children}
        </RequirePermission>
    );
}

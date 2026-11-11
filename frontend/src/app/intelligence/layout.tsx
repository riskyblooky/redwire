'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Intelligence tab shows only with intel_view; this refuses direct links too
// (every page under /intelligence).
export default function IntelligenceLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="intel_view" page="Intelligence">
            {children}
        </RequirePermission>
    );
}

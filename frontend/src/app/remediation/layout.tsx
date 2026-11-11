'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Remediation tab shows only with remediation_view; this refuses direct links too
// (every page under /remediation).
export default function RemediationLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="remediation_view" page="Remediation">
            {children}
        </RequirePermission>
    );
}

'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Clients tab shows only with client_view; this refuses direct links too
// (every page under /clients).
export default function ClientsLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="client_view" page="Clients">
            {children}
        </RequirePermission>
    );
}

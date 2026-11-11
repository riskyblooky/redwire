'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Templates tab shows only with template_view; this refuses direct links too
// (every page under /templates).
export default function TemplatesLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="template_view" page="Templates">
            {children}
        </RequirePermission>
    );
}

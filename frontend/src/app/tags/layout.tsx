'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Tags tab shows only with tag_view; this refuses direct links too
// (every page under /tags).
export default function TagsLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="tag_view" page="Tags">
            {children}
        </RequirePermission>
    );
}

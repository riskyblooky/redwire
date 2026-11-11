'use client';

import { ReactNode } from 'react';
import { RequirePermission } from '@/components/auth/require-permission';

// The Calendar tab shows only with calendar_view; this refuses direct links too
// (every page under /calendar).
export default function CalendarLayout({ children }: { children: ReactNode }) {
    return (
        <RequirePermission permission="calendar_view" page="Calendar">
            {children}
        </RequirePermission>
    );
}

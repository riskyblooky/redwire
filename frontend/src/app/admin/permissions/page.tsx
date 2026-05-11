/**
 * admin/permissions/page.tsx — Permissions Redirect
 *
 * Stub route that immediately redirects to /admin?tab=permissions.
 * Exists so that direct links to /admin/permissions resolve correctly.
 */
'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function PermissionsPage() {
    const router = useRouter();

    useEffect(() => {
        // Redirect to admin page with permissions tab
        router.replace('/admin?tab=permissions');
    }, [router]);

    return (
        <div className="flex h-full items-center justify-center p-8">
            <p className="text-slate-400">Redirecting to admin console...</p>
        </div>
    );
}

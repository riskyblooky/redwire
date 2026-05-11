/**
 * page.tsx — Root Landing Page
 *
 * Entry point for the application. Redirects authenticated users to
 * /dashboard and unauthenticated users to /login. Renders a loading
 * splash screen while the auth state is being resolved.
 */
'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/auth-store';
import { RedWireSpinner } from '@/components/ui/redwire-spinner';

export default function HomePage() {
    const router = useRouter();
    const { isAuthenticated, isLoading } = useAuthStore();

    useEffect(() => {
        if (!isLoading) {
            if (isAuthenticated) {
                router.push('/dashboard');
            } else {
                router.push('/login');
            }
        }
    }, [isAuthenticated, isLoading, router]);

    return <RedWireSpinner />;
}

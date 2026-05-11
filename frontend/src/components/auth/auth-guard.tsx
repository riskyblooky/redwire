'use client';

import { useEffect, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/stores/auth-store';
import { RedWireSpinner } from '@/components/ui/redwire-spinner';

const PUBLIC_ROUTES = ['/login', '/register'];

export function AuthGuard({ children }: { children: ReactNode }) {
    const { user, isAuthenticated, isLoading, checkAuth, needsRedirect } = useAuthStore();
    const router = useRouter();
    const pathname = usePathname();

    useEffect(() => {
        // Initial check if not already done by Providers or previous mount
        if (isLoading && !isAuthenticated) {
            checkAuth();
        }
    }, [checkAuth, isLoading, isAuthenticated]);

    useEffect(() => {
        const isPublicRoute = PUBLIC_ROUTES.includes(pathname);

        if (!isLoading) {
            if (needsRedirect && !isPublicRoute) {
                router.push('/login');
                return;
            }

            if (!isAuthenticated && !isPublicRoute) {
                router.push('/login');
            } else if (isAuthenticated && isPublicRoute) {
                router.push('/dashboard');
            }
        }
    }, [isAuthenticated, isLoading, pathname, router, needsRedirect]);

    if (isLoading) {
        return <RedWireSpinner />;
    }

    return <>{children}</>;
}

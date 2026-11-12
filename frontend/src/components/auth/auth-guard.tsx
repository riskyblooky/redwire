'use client';

import { useEffect, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/stores/auth-store';
import { RedWireSpinner } from '@/components/ui/redwire-spinner';
import { loginUrlForCurrentPage, afterLoginPath, PUBLIC_ROUTES, SIGNED_IN_REDIRECT_ROUTES } from '@/lib/login-redirect';


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
        const isPublicRoute = PUBLIC_ROUTES.includes(pathname || '');

        if (!isLoading) {
            if (needsRedirect && !isPublicRoute) {
                router.push(loginUrlForCurrentPage());
                return;
            }

            if (!isAuthenticated && !isPublicRoute) {
                router.push(loginUrlForCurrentPage());
            } else if (isAuthenticated && SIGNED_IN_REDIRECT_ROUTES.includes(pathname || '')) {
                router.push(afterLoginPath());
            }
        }
    }, [isAuthenticated, isLoading, pathname, router, needsRedirect]);

    if (isLoading) {
        return <RedWireSpinner />;
    }

    return <>{children}</>;
}

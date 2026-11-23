'use client';

import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

/**
 * Branding line under the sign-in / registration window, with the live
 * version from GET /health (unauthenticated; same query the admin About
 * panel uses). It used to hard-code "v2.0".
 */
export function AuthFooter() {
    const { data } = useQuery<{ version?: string }>({
        queryKey: ['about', 'health'],
        queryFn: async () => (await api.get('/health')).data,
        staleTime: 60_000,
        retry: false,
    });
    return (
        <p className="text-center text-[9px] font-mono text-white/10 mt-4 tracking-widest uppercase">
            RedWire Security Platform{data?.version ? ` — v${data.version}` : ''}
        </p>
    );
}

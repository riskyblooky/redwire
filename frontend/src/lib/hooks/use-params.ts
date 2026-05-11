import { use } from 'react';

/**
 * Unwrap Next.js 15+ async params in client components.
 * 
 * In Next.js 15, page params are wrapped in a Proxy that is typed
 * as Promise<T>. We always use React.use() to properly unwrap it,
 * which eliminates the console warning about direct property access.
 * 
 * Usage:
 *   function MyPage({ params }: { params: Promise<{ id: string }> }) {
 *     const { id } = useParams(params);
 *   }
 */
export function useParams<T extends Record<string, string>>(
    params: Promise<T> | T
): T {
    // Always use React.use() — Next.js 15 params are a thenable Proxy,
    // not a true Promise, so instanceof checks don't work reliably.
    // React.use() handles both real Promises and thenables correctly.
    return use(params as Promise<T>);
}

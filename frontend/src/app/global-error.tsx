'use client';

import { useEffect } from 'react';

/**
 * Last-resort boundary for errors in the root layout itself (providers,
 * auth bootstrap...), which app/error.tsx can't catch because it renders
 * inside that layout. It replaces the whole document, so it brings its own
 * <html>/<body> and inline styles rather than relying on the app's CSS.
 */
export default function GlobalError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        console.error(error);
    }, [error]);

    return (
        <html lang="en" className="dark">
            <body
                style={{
                    margin: 0, minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: '#020617', color: '#f1f5f9', fontFamily: 'system-ui, sans-serif', padding: '0 16px',
                }}
            >
                <div style={{ maxWidth: 420, textAlign: 'center' }}>
                    <div style={{ fontSize: 56, fontWeight: 700, color: 'rgba(239,68,68,0.7)', fontFamily: 'monospace' }}>!</div>
                    <h1 style={{ fontSize: 20, fontWeight: 600, margin: '16px 0 8px' }}>RedWire couldn&apos;t load</h1>
                    <p style={{ color: '#94a3b8', fontSize: 14, margin: '0 0 16px' }}>
                        An unexpected error stopped the app from starting. Try again, or reload the page.
                    </p>
                    {error?.digest && (
                        <p style={{ color: '#64748b', fontSize: 12, fontFamily: 'monospace' }}>Digest: {error.digest}</p>
                    )}
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                        <button
                            onClick={() => reset()}
                            style={{ background: '#2563eb', color: '#fff', border: 0, borderRadius: 6, padding: '8px 16px', fontSize: 14, cursor: 'pointer' }}
                        >
                            Try again
                        </button>
                        <button
                            onClick={() => window.location.reload()}
                            style={{ background: 'transparent', color: '#cbd5e1', border: '1px solid #334155', borderRadius: 6, padding: '8px 16px', fontSize: 14, cursor: 'pointer' }}
                        >
                            Reload
                        </button>
                    </div>
                </div>
            </body>
        </html>
    );
}

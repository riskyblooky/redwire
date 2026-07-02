'use client';

import { useEffect } from 'react';

export default function ErrorBoundary({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        // Log to browser console so operators can grab the message from
        // DevTools if reporting a bug. Server logs already capture the
        // upstream cause.
        // eslint-disable-next-line no-console
        console.error(error);
    }, [error]);

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-100 px-4">
            <div className="max-w-md text-center space-y-4">
                <div className="text-6xl font-mono font-bold text-red-500/70">!</div>
                <h1 className="text-xl font-semibold">Something went wrong</h1>
                <p className="text-slate-400 text-sm">
                    An unexpected error interrupted rendering. Try again, or navigate away and back.
                </p>
                {error?.digest && (
                    <p className="text-slate-500 text-xs font-mono">Digest: {error.digest}</p>
                )}
                <div>
                    <button
                        onClick={() => reset()}
                        className="inline-block rounded-md bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 text-sm font-medium transition-colors"
                    >
                        Try again
                    </button>
                </div>
            </div>
        </div>
    );
}

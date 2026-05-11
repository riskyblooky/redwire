'use client';

/**
 * RedWireSpinner — full-screen themed loading splash.
 *
 * Used by AuthGuard during the initial auth check, by the root /
 * redirect transit, and by data-heavy pages (dashboard, etc.) while
 * their first fetch resolves. Pass `message` to label the operation;
 * defaults to "redwire" so the same component covers a plain splash.
 *
 * Uses bg-background and the themed --primary so palette / accent
 * changes carry through.
 */
export function RedWireSpinner({ message }: { message?: string } = {}) {
    return (
        <div className="flex h-screen w-full items-center justify-center bg-background">
            <div className="relative flex flex-col items-center gap-6">
                {/* Animated concentric rings */}
                <div className="relative w-20 h-20">
                    {/* Outer ring — slow pulse */}
                    <div
                        className="absolute inset-0 rounded-full border-2 border-primary/20 animate-ping"
                        style={{ animationDuration: '2s' }}
                    />
                    {/* Middle ring — medium spin */}
                    <div
                        className="absolute inset-2 rounded-full border-2 border-transparent border-t-primary border-r-primary/60 animate-spin"
                        style={{ animationDuration: '1.5s' }}
                    />
                    {/* Inner ring — fast spin, opposite direction */}
                    <div
                        className="absolute inset-4 rounded-full border-2 border-transparent border-b-primary/80 border-l-primary/40 animate-spin"
                        style={{ animationDuration: '0.8s', animationDirection: 'reverse' }}
                    />
                    {/* Center dot — always RedWire red, regardless of theme accent */}
                    <div
                        className="absolute inset-[34px] rounded-full bg-red-500 animate-pulse"
                        style={{ boxShadow: '0 0 12px rgba(239, 68, 68, 0.6)' }}
                    />
                </div>

                {/* Caption */}
                <div className="relative">
                    <span className="text-sm font-mono tracking-[0.3em] text-slate-600 uppercase animate-pulse">
                        {message ?? 'redwire'}
                    </span>
                </div>
            </div>
        </div>
    );
}

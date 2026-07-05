'use client';

/**
 * Admin About panel — shows exactly what's running so an operator can
 * confirm "yes, my deploy landed."
 *
 * Reads GET /health. The endpoint returns
 * ``{status, service, version, commit, build_time}`` — see
 * backend/main.py::_resolve_build_info. `commit` and `build_time` come
 * from Docker build args set by scripts/deploy_server.sh. When those
 * args weren't passed (raw ``docker compose build``, dev-only images),
 * the backend falls back to a ``git rev-parse`` probe against the
 * mounted source; if THAT fails too the field is ``"unknown"``.
 */
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Info, GitCommit, Clock, Package, Copy, Check, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

interface HealthPayload {
    status: string;
    service: string;
    version: string;
    commit: string;
    build_time: string;
}

export function AboutPanel() {
    const { data, isLoading, error } = useQuery<HealthPayload>({
        queryKey: ['about', 'health'],
        queryFn: async () => {
            const { data } = await api.get<HealthPayload>('/health');
            return data;
        },
        staleTime: 60_000,
    });

    const [copiedKey, setCopiedKey] = useState<string | null>(null);
    const copy = async (key: string, value: string) => {
        try {
            await navigator.clipboard.writeText(value);
            setCopiedKey(key);
            setTimeout(() => setCopiedKey(null), 1500);
        } catch {
            toast.error('Copy failed');
        }
    };

    if (isLoading) {
        return (
            <Card className="border-slate-800 bg-slate-900/50 max-w-2xl">
                <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
                </CardContent>
            </Card>
        );
    }

    if (error || !data) {
        return (
            <Card className="border-slate-800 bg-slate-900/50 max-w-2xl">
                <CardContent className="py-8 text-center text-red-400">
                    Failed to load version info.
                </CardContent>
            </Card>
        );
    }

    const rows: Array<{ key: keyof HealthPayload; label: string; icon: React.ReactNode }> = [
        { key: 'version',    label: 'Version',    icon: <Package className="h-4 w-4 text-slate-500" /> },
        { key: 'commit',     label: 'Commit',     icon: <GitCommit className="h-4 w-4 text-slate-500" /> },
        { key: 'build_time', label: 'Build time', icon: <Clock className="h-4 w-4 text-slate-500" /> },
    ];

    return (
        <Card className="border-slate-800 bg-slate-900/50 max-w-2xl">
            <CardHeader>
                <CardTitle className="text-white flex items-center gap-2 text-lg">
                    <Info className="h-5 w-5 text-slate-400" />
                    About This Deployment
                </CardTitle>
                <CardDescription>
                    What&apos;s actually running right now. Useful for confirming a deploy landed.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
                {rows.map((row) => {
                    const value = data[row.key] || 'unknown';
                    return (
                        <div
                            key={row.key}
                            className="flex items-center justify-between py-2.5 px-3 rounded-lg bg-slate-950/40 border border-slate-800/50"
                        >
                            <div className="flex items-center gap-2.5">
                                {row.icon}
                                <span className="text-sm text-slate-400 font-medium min-w-[100px]">
                                    {row.label}
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <code className="text-sm text-slate-200 font-mono">{value}</code>
                                {value !== 'unknown' && (
                                    <button
                                        onClick={() => copy(row.key, value)}
                                        className="p-1 text-slate-600 hover:text-slate-300 transition-colors"
                                        title="Copy"
                                    >
                                        {copiedKey === row.key ? (
                                            <Check className="h-3.5 w-3.5 text-emerald-400" />
                                        ) : (
                                            <Copy className="h-3.5 w-3.5" />
                                        )}
                                    </button>
                                )}
                            </div>
                        </div>
                    );
                })}

                <div className="mt-4 pt-4 border-t border-slate-800 text-xs text-slate-500 space-y-1">
                    <p>
                        Version comes from <code className="text-slate-400">backend/version.py</code>.
                        Commit and build time are baked at image build time by{' '}
                        <code className="text-slate-400">scripts/deploy_server.sh</code>{' '}
                        via Docker build args.
                    </p>
                    <p>
                        Values of <code className="text-slate-400">&quot;unknown&quot;</code> mean the image was
                        built without those args (raw <code className="text-slate-400">docker compose build</code>).
                    </p>
                </div>
            </CardContent>
        </Card>
    );
}

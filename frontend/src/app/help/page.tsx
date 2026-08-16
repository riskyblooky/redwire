'use client';

import { Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { useHelpDocs, useHelpDoc } from '@/lib/hooks/use-help';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { Card, CardContent } from '@/components/ui/card';
import { BookOpen, Loader2, Shield } from 'lucide-react';
import { cn } from '@/lib/utils';

function HelpInner() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const { data: docs = [], isLoading: loadingDocs } = useHelpDocs();
    const requested = searchParams?.get('doc');
    const slug = requested || docs[0]?.slug || null;
    const { data: doc, isLoading: loadingDoc } = useHelpDoc(slug);

    const select = (s: string) => router.push(`/help?doc=${s}`, { scroll: false });

    return (
        <DashboardLayout>
            <div className="mx-auto max-w-6xl p-6">
                <div className="mb-5">
                    <h1 className="flex items-center gap-2 text-xl font-bold text-white">
                        <BookOpen className="h-5 w-5 text-blue-400" /> Help &amp; Guides
                    </h1>
                    <p className="text-sm text-slate-500">Documentation for using and administering RedWire.</p>
                </div>

                <div className="grid gap-6 lg:grid-cols-4">
                    {/* Nav */}
                    <div className="space-y-1.5 lg:col-span-1">
                        {loadingDocs ? (
                            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-slate-500" /></div>
                        ) : (
                            docs.map(d => (
                                <button
                                    key={d.slug}
                                    onClick={() => select(d.slug)}
                                    className={cn(
                                        'w-full rounded-lg border p-3 text-left transition-colors',
                                        d.slug === slug
                                            ? 'border-blue-500/40 bg-blue-500/5'
                                            : 'border-slate-800 bg-slate-900/50 hover:border-slate-700',
                                    )}
                                >
                                    <div className="flex items-center gap-1.5">
                                        <span className="text-sm font-semibold text-white">{d.title}</span>
                                        {d.admin_only && <Shield className="h-3 w-3 text-amber-400" />}
                                    </div>
                                    <p className="mt-0.5 text-[11px] leading-snug text-slate-500">{d.description}</p>
                                </button>
                            ))
                        )}
                    </div>

                    {/* Content */}
                    <div className="lg:col-span-3">
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardContent className="p-6">
                                {loadingDoc || !doc ? (
                                    <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
                                ) : (
                                    <MarkdownPreview value={doc.content} />
                                )}
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
}

export default function HelpPage() {
    return (
        <Suspense fallback={null}>
            <HelpInner />
        </Suspense>
    );
}

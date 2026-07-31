'use client';

import React, { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * Client-side Mermaid renderer. `mermaid` is a heavy dependency (SVG layout
 * engines, dagre, etc.), so it's loaded via a dynamic import and shared across
 * every diagram on the page through a single module-level promise — the code
 * lands in its own chunk and never bloats the main bundle (matters for the
 * 2GB-capped prod build).
 *
 * securityLevel:'strict' makes mermaid sanitize labels/HTML in the diagram
 * source, so rendering user-authored charts via dangerouslySetInnerHTML is
 * safe here — the same trust model TipTap-emitted markdown already relies on.
 */

let _mermaidPromise: Promise<any> | null = null;

function loadMermaid(): Promise<any> {
    if (!_mermaidPromise) {
        _mermaidPromise = import('mermaid').then((mod) => {
            const mermaid = mod.default;
            mermaid.initialize({
                startOnLoad: false,
                securityLevel: 'strict',
                theme: 'dark',
                fontFamily: 'inherit',
                themeVariables: {
                    // Blend with the dark-only RedWire palette (slate + indigo).
                    darkMode: true,
                    background: 'transparent',
                    primaryColor: '#1e293b',
                    primaryTextColor: '#e2e8f0',
                    primaryBorderColor: '#6366f1',
                    lineColor: '#64748b',
                    secondaryColor: '#312e81',
                    tertiaryColor: '#0f172a',
                    fontSize: '14px',
                },
            });
            return mermaid;
        });
    }
    return _mermaidPromise;
}

// Monotonic id so each render target is unique (mermaid keys internal state by id).
let _idCounter = 0;

interface MermaidDiagramProps {
    chart: string;
    className?: string;
}

export function MermaidDiagram({ chart, className }: MermaidDiagramProps) {
    const [svg, setSvg] = useState<string>('');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        let cancelled = false;
        const src = (chart || '').trim();

        if (!src) {
            setSvg('');
            setError(null);
            setLoading(false);
            return;
        }

        setLoading(true);
        loadMermaid()
            .then(async (mermaid) => {
                const id = `redwire-mermaid-${++_idCounter}`;
                try {
                    // parse() surfaces a clean syntax error before we attempt a render
                    await mermaid.parse(src);
                    const { svg: rendered } = await mermaid.render(id, src);
                    if (!cancelled) {
                        setSvg(rendered);
                        setError(null);
                    }
                } catch (e: any) {
                    if (!cancelled) {
                        setSvg('');
                        setError(e?.str || e?.message || 'Invalid diagram syntax');
                    }
                } finally {
                    if (!cancelled) setLoading(false);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setError('Failed to load the diagram renderer');
                    setLoading(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, [chart]);

    if (error) {
        return (
            <div className={cn('my-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3', className)}>
                <div className="mb-1.5 text-xs font-medium text-red-400">Diagram error: {error}</div>
                <pre className="overflow-x-auto whitespace-pre-wrap text-[11px] leading-relaxed text-slate-400">
                    {chart}
                </pre>
            </div>
        );
    }

    if (loading) {
        return (
            <div className={cn('my-2 h-16 w-full animate-pulse rounded-lg border border-slate-800 bg-slate-900/40', className)} />
        );
    }

    return (
        <div
            ref={containerRef}
            className={cn('mermaid-diagram my-2 flex justify-center overflow-x-auto', className)}
            // eslint-disable-next-line react/no-danger -- mermaid strict-mode output, see file header
            dangerouslySetInnerHTML={{ __html: svg }}
        />
    );
}

export default MermaidDiagram;

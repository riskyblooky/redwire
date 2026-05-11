'use client';

import { useEffect, useRef, useState } from 'react';
import api from '@/lib/api';

/**
 * <img>-style component that fetches its src via the authenticated axios
 * client when src points at /api/markdown-images/* (or its bare form).
 * Falls back to a plain <img> for any other URL so external images and
 * data: URLs still work.
 *
 * The fetched bytes are kept as an object URL while the component is
 * mounted; the URL is revoked on unmount.
 */

const AUTH_PREFIXES = ['/api/markdown-images/', '/markdown-images/'];

function shouldAuthFetch(src?: string | null): boolean {
    if (!src) return false;
    return AUTH_PREFIXES.some(p => src.startsWith(p));
}

interface AuthImageProps extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> {
    src?: string | null;
}

export function AuthImage({ src, alt, className, style, ...rest }: AuthImageProps) {
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [error, setError] = useState(false);
    const objectUrlRef = useRef<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        setError(false);

        if (objectUrlRef.current) {
            URL.revokeObjectURL(objectUrlRef.current);
            objectUrlRef.current = null;
            setBlobUrl(null);
        }

        if (!src || !shouldAuthFetch(src)) return;

        // Strip the /api prefix because our axios baseURL already includes it.
        const path = src.replace(/^\/api/, '');

        api.get(path, { responseType: 'blob' })
            .then(res => {
                if (cancelled) return;
                const url = URL.createObjectURL(res.data);
                objectUrlRef.current = url;
                setBlobUrl(url);
            })
            .catch(() => {
                if (!cancelled) setError(true);
            });

        return () => {
            cancelled = true;
            if (objectUrlRef.current) {
                URL.revokeObjectURL(objectUrlRef.current);
                objectUrlRef.current = null;
            }
        };
    }, [src]);

    if (!src) return null;

    // Plain <img> for non-auth URLs (data:, https://, /uploads, etc.)
    if (!shouldAuthFetch(src)) {
        // eslint-disable-next-line @next/next/no-img-element
        return <img src={src} alt={alt} className={className} style={style} {...rest} />;
    }

    if (error) {
        return (
            <span
                className="inline-block px-2 py-1 rounded border border-red-500/30 bg-red-500/10 text-red-400 text-xs"
                title={typeof src === 'string' ? src : undefined}
            >
                Image unavailable
            </span>
        );
    }

    if (!blobUrl) {
        // While loading: render a grey placeholder of indeterminate size
        return (
            <span
                className="inline-block w-32 h-20 rounded bg-slate-800/40 border border-slate-700/40 animate-pulse"
                aria-label="Loading image"
            />
        );
    }

    // eslint-disable-next-line @next/next/no-img-element
    return <img src={blobUrl} alt={alt} className={className} style={style} {...rest} />;
}

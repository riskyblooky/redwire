'use client';

/**
 * useAuthedImageUrl — fetch an image behind an authenticated URL and hand
 * back a blob: URL suitable for <img src>.
 *
 * Needed because <img> and <AvatarImage> render as raw HTML img tags, which
 * browsers don't send the Authorization header with. GHSA-h77m-pjqc-5cm3
 * moved /uploads/* behind get_current_user, so plain <img src="/uploads/…">
 * requests 401 for signed-in users. This hook fetches the bytes via the
 * shared axios client (which attaches the JWT), wraps them in a blob URL,
 * and revokes the URL when the caller unmounts or the source path changes.
 *
 * Non-authed paths (data:, https://, http://) are returned as-is with no
 * fetch, so this is safe to sprinkle over every img-style consumer without
 * doubling up requests on external images.
 */

import { ImgHTMLAttributes, useEffect, useState } from 'react';
import api from '@/lib/api';

// Any src that lives on the RedWire origin under one of these prefixes
// needs auth. External URLs, data: URIs, and blob: URIs are passed through
// untouched.
const AUTH_PREFIXES = ['/uploads/', 'uploads/', '/api/markdown-images/', '/markdown-images/'];

function needsAuthFetch(src?: string | null): boolean {
    if (!src) return false;
    if (src.startsWith('data:') || src.startsWith('blob:')) return false;
    // External absolute URL — leave to the browser.
    if (/^https?:\/\//.test(src)) return false;
    return AUTH_PREFIXES.some(p => src.startsWith(p));
}

/**
 * Given a profile-photo path from the backend (e.g. "uploads/profile_photos/<uuid>.png"),
 * returns a blob: URL that renders in <img src>, or null while loading /
 * on error. Non-authed paths return the original src unchanged.
 */
export function useAuthedImageUrl(src?: string | null): string | null {
    const [url, setUrl] = useState<string | null>(() =>
        src && !needsAuthFetch(src) ? src : null,
    );

    useEffect(() => {
        if (!src) { setUrl(null); return; }
        if (!needsAuthFetch(src)) { setUrl(src); return; }

        let cancelled = false;
        let currentBlobUrl: string | null = null;
        // Normalize leading slash so axios's baseURL joins cleanly.
        const cleanPath = src.startsWith('/') ? src.slice(1) : src;

        api.get(`/${cleanPath}`, { responseType: 'blob' })
            .then(res => {
                if (cancelled) return;
                currentBlobUrl = URL.createObjectURL(res.data);
                setUrl(currentBlobUrl);
            })
            .catch(() => {
                if (!cancelled) setUrl(null);
            });

        return () => {
            cancelled = true;
            if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
        };
    }, [src]);

    return url;
}


/**
 * Drop-in replacement for <img> whose src resolves through
 * useAuthedImageUrl. Use where a raw <img> renders an /uploads/* path
 * and you don't need Radix Avatar composition (for that, use UserAvatar).
 *
 * Renders nothing while loading / on 404 so callers can layer a fallback
 * (initials block, placeholder icon) sibling-wise. See profile page,
 * stats page, presence indicator, scheduling assistant for examples.
 */
interface AuthedImgProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> {
    src?: string | null;
}

export function AuthedImg({ src, alt = '', ...rest }: AuthedImgProps) {
    const resolved = useAuthedImageUrl(src);
    if (!resolved) return null;
    return <img src={resolved} alt={alt} {...rest} />;
}


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

// ── Session-wide blob cache ──────────────────────────────────────────────
// The same profile photo is rendered once per table row / mention / presence
// dot — often dozens of times for the same user. Without sharing, every
// UserAvatar instance fired its own authed fetch and minted its own blob URL.
// These module-level maps dedupe by image path so each distinct photo is
// fetched exactly once per session and all consumers reuse one blob URL.
//
// Blob URLs here are intentionally never revoked: they're shared across an
// unknown number of live consumers, and the set of distinct photos is bounded
// by the user count (small, a few KB each). Revoking on any one unmount would
// break every other avatar still pointing at the same URL.
const blobCache = new Map<string, string>();          // cleanPath -> blob: URL
const inflight = new Map<string, Promise<string>>();  // cleanPath -> pending fetch
const failed = new Set<string>();                     // cleanPath -> 404/err (don't retry)

function fetchAuthedBlob(cleanPath: string): Promise<string> {
    const cached = blobCache.get(cleanPath);
    if (cached) return Promise.resolve(cached);
    const pending = inflight.get(cleanPath);
    if (pending) return pending;

    const p = api.get(`/${cleanPath}`, { responseType: 'blob' })
        .then(res => {
            const url = URL.createObjectURL(res.data);
            blobCache.set(cleanPath, url);
            inflight.delete(cleanPath);
            return url;
        })
        .catch(err => {
            inflight.delete(cleanPath);
            failed.add(cleanPath);
            throw err;
        });
    inflight.set(cleanPath, p);
    return p;
}

/**
 * Given a profile-photo path from the backend (e.g. "uploads/profile_photos/<uuid>.png"),
 * returns a blob: URL that renders in <img src>, or null while loading /
 * on error. Non-authed paths return the original src unchanged.
 *
 * De-duplicated across all consumers via a session-wide cache: the first
 * avatar for a given photo fetches it, every subsequent one reuses the same
 * blob URL synchronously — no per-row requests.
 */
export function useAuthedImageUrl(src?: string | null): string | null {
    // Normalize leading slash so axios's baseURL joins cleanly.
    const cleanPath = src && needsAuthFetch(src) ? (src.startsWith('/') ? src.slice(1) : src) : null;

    const [url, setUrl] = useState<string | null>(() => {
        if (!src) return null;
        if (!needsAuthFetch(src)) return src;                    // data:/http(s):/blob: pass-through
        return (cleanPath && blobCache.get(cleanPath)) || null;  // synchronous cache hit
    });

    useEffect(() => {
        if (!src) { setUrl(null); return; }
        if (!needsAuthFetch(src) || !cleanPath) { setUrl(src); return; }

        const cached = blobCache.get(cleanPath);
        if (cached) { setUrl(cached); return; }
        if (failed.has(cleanPath)) { setUrl(null); return; }

        let cancelled = false;
        fetchAuthedBlob(cleanPath)
            .then(u => { if (!cancelled) setUrl(u); })
            .catch(() => { if (!cancelled) setUrl(null); });

        // No blob revocation here — the URL is shared and cached session-wide.
        return () => { cancelled = true; };
    }, [src, cleanPath]);

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


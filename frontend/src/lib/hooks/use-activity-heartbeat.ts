'use client';

import { useEffect, useRef } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import api from '@/lib/api';

// URL → tracked resource. Detail/edit routes like /findings/{id} (and
// /findings/{id}/edit) map to the record the user is working on, so the
// heartbeat can attribute effort to it. `new` is not a real resource.
const RESOURCE_ROUTES: Record<string, string> = {
    findings: 'finding',
    testcases: 'testcase',
    assets: 'asset',
};
function resourceFromUrl(
    pathname: string | null,
    search: URLSearchParams | null,
): { resource_type: string; resource_id: string } | null {
    const m = /^\/(findings|testcases|assets)\/([^/?#]+)/.exec(pathname || '');
    if (m) {
        const id = m[2];
        if (!id || id === 'new') return null;
        return { resource_type: RESOURCE_ROUTES[m[1]], resource_id: id };
    }
    // Notes live under the engagement page as ?tab=notes&noteId=… (synced to the
    // URL by the notes tab), so they need the query string, not just the path.
    if (search && search.get('tab') === 'notes') {
        const noteId = search.get('noteId');
        if (noteId) return { resource_type: 'note', resource_id: noteId };
    }
    return null;
}

/**
 * Reports the user as genuinely active by POSTing /users/me/heartbeat — but only
 * while the tab is VISIBLE and the user has actually interacted (mouse/keyboard/
 * scroll/touch) recently. Drives `last_active` (the admin online indicator), and
 * when a tracked resource is open (finding/test-case/asset detail/edit) includes
 * it so the backend records a resource-scoped effort ping (time-on-task).
 *
 * It deliberately does NOT fire from background polling, so an idle tab left open
 * ages out of "online" and stops accruing effort time.
 */
export function useActivityHeartbeat(enabled: boolean = true) {
    const pathname = usePathname();
    const searchParams = useSearchParams();
    // Recompute the open resource each render and stash it, so the interval's
    // send() closure always reads the current page (path + query).
    const resourceRef = useRef<{ resource_type: string; resource_id: string } | null>(null);
    resourceRef.current = resourceFromUrl(pathname, searchParams);
    const lastInteraction = useRef<number>(Date.now());
    const lastSent = useRef<number>(0);

    useEffect(() => {
        if (!enabled) return;
        const IDLE_MS = 2 * 60 * 1000;   // "active" only if interacted within 2 min
        const MIN_GAP = 45 * 1000;       // send at most once / 45s
        const CHECK_MS = 30 * 1000;      // evaluate every 30s

        const bump = () => { lastInteraction.current = Date.now(); };
        const events: (keyof WindowEventMap)[] = ['pointerdown', 'keydown', 'mousemove', 'scroll', 'touchstart'];
        events.forEach((e) => window.addEventListener(e, bump, { passive: true }));

        const send = () => {
            const now = Date.now();
            if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
            if (now - lastInteraction.current > IDLE_MS) return;   // idle → skip
            if (now - lastSent.current < MIN_GAP) return;          // throttle
            lastSent.current = now;
            api.post('/users/me/heartbeat', resourceRef.current || {}).catch(() => {});
        };

        send(); // fresh page load / mount counts as active
        const interval = setInterval(send, CHECK_MS);
        const onVisibility = () => {
            if (document.visibilityState === 'visible') {
                lastInteraction.current = Date.now();
                send();
            }
        };
        document.addEventListener('visibilitychange', onVisibility);

        return () => {
            events.forEach((e) => window.removeEventListener(e, bump));
            clearInterval(interval);
            document.removeEventListener('visibilitychange', onVisibility);
        };
    }, [enabled]);
}

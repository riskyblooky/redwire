'use client';

import { useEffect, useRef } from 'react';
import api from '@/lib/api';

/**
 * Reports the user as genuinely active by POSTing /users/me/heartbeat — but only
 * while the tab is VISIBLE and the user has actually interacted (mouse/keyboard/
 * scroll/touch) recently. This is what drives `last_active` (the admin online
 * indicator); it deliberately does NOT fire from background polling, so an idle
 * tab left open ages out of "online" instead of looking active forever.
 *
 * - Active user → a heartbeat roughly every MIN_GAP.
 * - No interaction for IDLE_MS, or tab hidden → heartbeats stop → user ages out.
 */
export function useActivityHeartbeat(enabled: boolean = true) {
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
            api.post('/users/me/heartbeat').catch(() => {});
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

/**
 * Reconnect policy shared by the WebSocket clients (use-collaboration,
 * yjs-room).
 *
 * - Backoff 2s → 30s, retried indefinitely: an outage longer than a few
 *   minutes (server restart, laptop asleep) must not leave the page
 *   permanently offline.
 * - The backoff resets on the first *message*, not on open: the server
 *   accepts the socket before it checks the auth frame, so "opened" says
 *   nothing about whether it will stay.
 * - 1008 (policy violation) is how the server refuses auth or access. One
 *   retry is allowed, since each connect fetches a fresh token first
 *   (getFreshAccessToken), so an expired token is covered. A second 1008 in
 *   a row is a real refusal and stops the loop instead of hammering it.
 * - Coming back online or to a visible tab reconnects straight away
 *   rather than waiting out the backoff.
 */
const MIN_DELAY_MS = 2_000;
const MAX_DELAY_MS = 30_000;
const POLICY_VIOLATION = 1008;

export interface ReconnectPolicy {
    /** Call from onmessage: the server accepted us. */
    onMessage(): void;
    /** Call from onclose (unless the component is cleaning up). */
    onClose(code: number): void;
    /** Stop timers and listeners (component cleanup). */
    dispose(): void;
}

export function createReconnectPolicy(connect: () => void): ReconnectPolicy {
    let attempt = 0;
    let policyCloses = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const reconnectNow = () => {
        if (stopped || timer === undefined) return; // connected, or gave up
        clearTimeout(timer);
        timer = undefined;
        connect();
    };
    const onVisible = () => {
        if (document.visibilityState === 'visible') reconnectNow();
    };
    window.addEventListener('online', reconnectNow);
    document.addEventListener('visibilitychange', onVisible);

    return {
        onMessage() {
            attempt = 0;
            policyCloses = 0;
        },
        onClose(code: number) {
            if (stopped) return;
            if (code === POLICY_VIOLATION && ++policyCloses >= 2) {
                stopped = true;
                return;
            }
            const delay = Math.max(MIN_DELAY_MS, Math.min(1000 * 2 ** attempt, MAX_DELAY_MS));
            attempt++;
            clearTimeout(timer);
            timer = setTimeout(() => {
                timer = undefined;
                connect();
            }, delay);
        },
        dispose() {
            stopped = true;
            clearTimeout(timer);
            timer = undefined;
            window.removeEventListener('online', reconnectNow);
            document.removeEventListener('visibilitychange', onVisible);
        },
    };
}

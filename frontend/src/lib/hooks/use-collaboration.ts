import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '@/stores/auth-store';

export interface PresenceUser {
    id: string;
    username?: string;
    full_name?: string;
    profile_photo?: string;
    role?: string;
    color?: string; // assigned color for cursor/avatar
    /** 'edit' = user is on the edit page; 'view' or absent = read-only.
     *  Used by edit pages to soft-lock when another user is editing. */
    mode?: 'edit' | 'view';
}

export interface CursorPosition {
    x: number;
    y: number;
}

interface UseCollaborationOptions {
    resourceType: 'finding' | 'engagement' | 'report' | 'testcase' | 'asset' | 'evidence' | 'dashboard' | 'user' | 'note';
    resourceId: string;
    enabled?: boolean;
    onMessage?: (data: any) => void;
    /** Tag this connection's intent. Defaults to 'view'. Edit pages
     *  pass 'edit' so others can detect concurrent edits. */
    mode?: 'edit' | 'view';
}

export function useCollaboration({ resourceType, resourceId, enabled = true, onMessage, mode = 'view' }: UseCollaborationOptions) {
    const { isAuthenticated, user: currentUser } = useAuthStore();
    const wsRef = useRef<any>(null);
    const [activeUsers, setActiveUsers] = useState<PresenceUser[]>([]);
    const [cursors, setCursors] = useState<Record<string, CursorPosition>>({});
    const [isConnected, setIsConnected] = useState(false);

    // Store callback in ref to avoid reconnecting when callback changes
    const onMessageRef = useRef(onMessage);
    useEffect(() => {
        onMessageRef.current = onMessage;
    }, [onMessage]);

    useEffect(() => {
        // Only run in browser environment
        if (typeof window === 'undefined') return;
        if (!enabled || !isAuthenticated || !resourceId) return;

        const token = localStorage.getItem('access_token');
        if (!token) return;

        let reconnectTimeout: NodeJS.Timeout;
        let userClearTimeout: NodeJS.Timeout;
        let retryCount = 0;
        const maxRetries = 10;
        let isCleaningUp = false;

        const connect = () => {
            if (isCleaningUp) return;

            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;

            const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
            let url = '';

            // Token is intentionally NOT in the URL — the backend reads
            // it from the first message after accept() (see
            // routers/websocket.py::_auth_via_first_frame). Putting the
            // bearer JWT in a query string leaks it to every URL sink:
            // browser history, nginx access logs, Referer headers,
            // process listings on CLI clients. CWE-598.
            if (apiUrl && !apiUrl.includes(host)) {
                const wsBaseUrl = apiUrl.replace(/^http/, 'ws');
                url = `${wsBaseUrl}/ws/${resourceType}/${resourceId}`;
            } else {
                url = `${protocol}//${host}/api/ws/${resourceType}/${resourceId}`;
            }

            // GHSA-7x2f-ff7r-h388 #3 (CWE-532): don't log the WS URL to
            // the browser console. The token is intentionally NOT in the
            // URL (see comment above and _auth_via_first_frame on the
            // backend), but keeping this debug print out of production
            // browser DevTools reduces the noise surface an attacker
            // shoulder-surfing (or logging with a compromised extension)
            // could use to fingerprint session state. If we need this
            // back for local debugging, guard it on
            // `process.env.NODE_ENV === 'development'`.

            // Create WebSocket only in browser environment
            // Using globalThis to avoid referencing WebSocket class during SSR
            const WebSocketConstructor = typeof window !== 'undefined' ? window.WebSocket : null;
            if (!WebSocketConstructor) {
                console.error('WebSocket not available');
                return;
            }

            const ws = new WebSocketConstructor(url);
            wsRef.current = ws;

            ws.onopen = () => {
                if (isCleaningUp) {
                    ws.close();
                    return;
                }
                // First frame MUST be the auth bearer. Backend has 5s to
                // receive it before closing with 1008 (see
                // _AUTH_FRAME_TIMEOUT_S in routers/websocket.py).
                ws.send(JSON.stringify({ type: 'auth', token }));

                // WS connected — reconnection logic handles retries
                setIsConnected(true);
                clearTimeout(userClearTimeout); // Cancel any pending user clear
                retryCount = 0;

                if (currentUser) {
                    ws.send(JSON.stringify({
                        type: 'identify',
                        user: {
                            id: currentUser.id,
                            username: currentUser.username,
                            full_name: currentUser.full_name,
                            profile_photo: currentUser.profile_photo,
                            role: currentUser.role,
                            mode,
                        }
                    }));
                }
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (onMessageRef.current) {
                        onMessageRef.current(data);
                    }

                    if (data.type === 'presence_update') {
                        if (data.active_users) {
                            setActiveUsers(data.active_users);
                        } else {
                            if (data.action === 'joined' || data.action === 'identified') {
                                setActiveUsers(prev => {
                                    const existingIndex = prev.findIndex(u => u.id === data.user.id);
                                    if (existingIndex > -1) {
                                        const newUsers = [...prev];
                                        newUsers[existingIndex] = { ...newUsers[existingIndex], ...data.user };
                                        return newUsers;
                                    }
                                    return [...prev, data.user];
                                });
                            } else if (data.action === 'left') {
                                setActiveUsers(prev => prev.filter(u => u.id !== data.user_id));
                                setCursors(prev => {
                                    const newCursors = { ...prev };
                                    delete newCursors[data.user_id];
                                    return newCursors;
                                });
                            }
                        }
                    } else if (data.type === 'cursor_update') {
                        setCursors(prev => ({
                            ...prev,
                            [data.user_id]: data.position
                        }));
                    }
                } catch (e) {
                    console.error('WS parse error', e);
                }
            };

            ws.onclose = () => {
                if (isCleaningUp) return;

                // WS disconnected — reconnect timer handles retry
                setIsConnected(false);
                wsRef.current = null;

                // Don't clear users immediately — debounce so brief reconnects
                // don't cause the "who's watching" indicator to flicker
                clearTimeout(userClearTimeout);
                userClearTimeout = setTimeout(() => {
                    setActiveUsers([]);
                }, 5000);

                if (retryCount < maxRetries) {
                    const delay = Math.max(2000, Math.min(1000 * Math.pow(2, retryCount), 30000));
                    reconnectTimeout = setTimeout(() => {
                        retryCount++;
                        connect();
                    }, delay);
                }
            };

            ws.onerror = (err) => {
                // Don't hard-close on error — let onclose handle reconnection
                // WS error — onclose handler will reconnect
            };
        };

        connect();

        return () => {
            isCleaningUp = true;
            if (wsRef.current) {
                wsRef.current.close();
            }
            clearTimeout(reconnectTimeout);
            clearTimeout(userClearTimeout);
            wsRef.current = null;
        };
    }, [isAuthenticated, resourceType, resourceId, enabled, currentUser?.id, mode]); // eslint-disable-line react-hooks/exhaustive-deps

    const lastCursorSentRef = useRef<number>(0);
    const sendCursorMove = (x: number, y: number) => {
        // Only run in browser environment
        if (typeof window === 'undefined') return;

        const now = Date.now();
        if (now - lastCursorSentRef.current < 100) return;

        // WebSocket.OPEN = 1, using numeric value to avoid SSR issues
        if (wsRef.current?.readyState === 1) {
            wsRef.current.send(JSON.stringify({
                type: 'cursor_move',
                position: { x, y }
            }));
            lastCursorSentRef.current = now;
        }
    };

    return {
        activeUsers,
        cursors,
        isConnected,
        sendCursorMove
    };
}

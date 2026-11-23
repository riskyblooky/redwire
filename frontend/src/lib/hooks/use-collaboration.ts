import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/auth-store';
import { getFreshAccessToken } from '@/lib/api';
import { createReconnectPolicy } from '@/lib/ws-reconnect';

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

// ── One socket per channel ───────────────────────────────────────────
//
// Every useCollaboration call on the same (user, resourceType, resourceId)
// shares one presence socket. A page often subscribes to its channel from
// more than one component (a sheet's header and body, the notes tab's list
// and editor, the layout and a page on 'user'); separate sockets cost a
// server connection each, and closing either sent a "left" for the user
// while the other was still open. The channel's mode is 'edit' if any
// subscriber is an editor, re-sent when that changes. The socket closes a
// moment after its last subscriber leaves, so a remount reuses it.

interface ChannelState {
    activeUsers: PresenceUser[];
    cursors: Record<string, CursorPosition>;
    isConnected: boolean;
}

const EMPTY_STATE: ChannelState = { activeUsers: [], cursors: {}, isConnected: false };

interface Subscriber {
    mode: 'edit' | 'view';
    onMessage: (data: any) => void;
    onState: (state: ChannelState) => void;
}

interface Channel {
    key: string;
    resourceType: string;
    resourceId: string;
    subs: Set<Subscriber>;
    ws: WebSocket | null;
    state: ChannelState;
    sentMode: 'edit' | 'view' | null;
    closed: boolean;
    closeTimer: ReturnType<typeof setTimeout> | null;
    userClearTimer: ReturnType<typeof setTimeout> | null;
    reconnect: ReturnType<typeof createReconnectPolicy> | null;
}

const CLOSE_GRACE_MS = 1000;
const channels = new Map<string, Channel>();

function channelMode(ch: Channel): 'edit' | 'view' {
    for (const s of ch.subs) if (s.mode === 'edit') return 'edit';
    return 'view';
}

function setChannelState(ch: Channel, patch: Partial<ChannelState>) {
    ch.state = { ...ch.state, ...patch };
    for (const s of ch.subs) s.onState(ch.state);
}

function identify(ch: Channel) {
    const user = useAuthStore.getState().user;
    // WebSocket.OPEN = 1 (numeric to stay SSR-safe)
    if (!ch.ws || ch.ws.readyState !== 1 || !user) return;
    const mode = channelMode(ch);
    if (ch.sentMode === mode) return;
    ch.sentMode = mode;
    ch.ws.send(JSON.stringify({
        type: 'identify',
        user: {
            id: user.id,
            username: user.username,
            full_name: user.full_name,
            profile_photo: user.profile_photo,
            role: user.role,
            mode,
        },
    }));
}

function channelUrl(resourceType: string, resourceId: string): string {
    // Token is intentionally NOT in the URL — the backend reads it from the
    // first message after accept() (routers/websocket.py::_auth_via_first_frame).
    // A bearer JWT in a query string leaks to every URL sink: browser
    // history, nginx access logs, Referer headers (CWE-598). And the URL is
    // not logged to the console (GHSA-7x2f-ff7r-h388 #3, CWE-532).
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
    if (apiUrl && !apiUrl.includes(host)) {
        return `${apiUrl.replace(/^http/, 'ws')}/ws/${resourceType}/${resourceId}`;
    }
    return `${protocol}//${host}/api/ws/${resourceType}/${resourceId}`;
}

function handleMessage(ch: Channel, data: any) {
    for (const s of ch.subs) s.onMessage(data);
    if (data.type === 'presence_update') {
        if (data.active_users) {
            setChannelState(ch, { activeUsers: data.active_users });
        } else if (data.action === 'joined' || data.action === 'identified') {
            const prev = ch.state.activeUsers;
            const i = prev.findIndex(u => u.id === data.user.id);
            const next = i > -1
                ? prev.map((u, j) => (j === i ? { ...u, ...data.user } : u))
                : [...prev, data.user];
            setChannelState(ch, { activeUsers: next });
        } else if (data.action === 'left') {
            const cursors = { ...ch.state.cursors };
            delete cursors[data.user_id];
            setChannelState(ch, {
                activeUsers: ch.state.activeUsers.filter(u => u.id !== data.user_id),
                cursors,
            });
        }
    } else if (data.type === 'cursor_update') {
        setChannelState(ch, { cursors: { ...ch.state.cursors, [data.user_id]: data.position } });
    }
}

async function connect(ch: Channel) {
    if (ch.closed) return;
    // Fresh per connect (see getFreshAccessToken), not the mount-time one.
    const token = await getFreshAccessToken();
    if (ch.closed || !token) return;

    const ws = new window.WebSocket(channelUrl(ch.resourceType, ch.resourceId));
    ch.ws = ws;
    ch.sentMode = null;

    ws.onopen = () => {
        if (ch.closed) { ws.close(); return; }
        // First frame MUST be the auth bearer: the backend closes with 1008
        // if it doesn't arrive within _AUTH_FRAME_TIMEOUT_S.
        ws.send(JSON.stringify({ type: 'auth', token }));
        if (ch.userClearTimer) clearTimeout(ch.userClearTimer);
        setChannelState(ch, { isConnected: true });
        identify(ch);
    };

    ws.onmessage = (event) => {
        ch.reconnect?.onMessage();
        let data: any;
        try { data = JSON.parse(event.data); } catch (e) { console.error('WS parse error', e); return; }
        handleMessage(ch, data);
    };

    ws.onclose = (event) => {
        if (ch.closed) return;
        ch.ws = null;
        setChannelState(ch, { isConnected: false });
        // Debounce the presence clear so a brief reconnect doesn't make
        // the "who's watching" indicator flicker.
        if (ch.userClearTimer) clearTimeout(ch.userClearTimer);
        ch.userClearTimer = setTimeout(() => setChannelState(ch, { activeUsers: [] }), 5000);
        ch.reconnect?.onClose(event.code);
    };

    // Errors are followed by close, which handles reconnection.
    ws.onerror = () => {};
}

function shutdown(ch: Channel) {
    ch.closed = true;
    channels.delete(ch.key);
    ch.reconnect?.dispose();
    if (ch.userClearTimer) clearTimeout(ch.userClearTimer);
    ch.ws?.close();
    ch.ws = null;
}

function subscribe(key: string, resourceType: string, resourceId: string, sub: Subscriber): Channel {
    let ch = channels.get(key);
    if (!ch) {
        const created: Channel = {
            key, resourceType, resourceId, subs: new Set(), ws: null, state: EMPTY_STATE,
            sentMode: null, closed: false, closeTimer: null, userClearTimer: null, reconnect: null,
        };
        created.reconnect = createReconnectPolicy(() => { connect(created); });
        channels.set(key, created);
        connect(created);
        ch = created;
    }
    if (ch.closeTimer) { clearTimeout(ch.closeTimer); ch.closeTimer = null; }
    ch.subs.add(sub);
    sub.onState(ch.state);
    identify(ch);
    return ch;
}

function unsubscribe(ch: Channel, sub: Subscriber) {
    ch.subs.delete(sub);
    if (ch.subs.size > 0) { identify(ch); return; }
    const target = ch;
    ch.closeTimer = setTimeout(() => { if (target.subs.size === 0) shutdown(target); }, CLOSE_GRACE_MS);
}

export function useCollaboration({ resourceType, resourceId, enabled = true, onMessage, mode = 'view' }: UseCollaborationOptions) {
    const { isAuthenticated, user: currentUser } = useAuthStore();
    const [state, setState] = useState<ChannelState>(EMPTY_STATE);
    const channelRef = useRef<Channel | null>(null);

    // Store callback in ref to avoid resubscribing when callback changes
    const onMessageRef = useRef(onMessage);
    useEffect(() => {
        onMessageRef.current = onMessage;
    }, [onMessage]);

    useEffect(() => {
        if (typeof window === 'undefined' || !window.WebSocket) return;
        if (!enabled || !isAuthenticated || !resourceId) return;
        if (!localStorage.getItem('access_token')) return;

        const sub: Subscriber = {
            mode,
            onMessage: (data) => onMessageRef.current?.(data),
            onState: setState,
        };
        const ch = subscribe(`${currentUser?.id ?? ''}|${resourceType}|${resourceId}`, resourceType, resourceId, sub);
        channelRef.current = ch;
        return () => {
            unsubscribe(ch, sub);
            channelRef.current = null;
            setState(EMPTY_STATE);
        };
    }, [isAuthenticated, resourceType, resourceId, enabled, currentUser?.id, mode]);

    const lastCursorSentRef = useRef<number>(0);
    const sendCursorMove = (x: number, y: number) => {
        const now = Date.now();
        if (now - lastCursorSentRef.current < 100) return;
        const ws = channelRef.current?.ws;
        if (ws?.readyState === 1) {
            ws.send(JSON.stringify({ type: 'cursor_move', position: { x, y } }));
            lastCursorSentRef.current = now;
        }
    };

    return {
        activeUsers: state.activeUsers,
        cursors: state.cursors,
        isConnected: state.isConnected,
        sendCursorMove,
    };
}


/**
 * onMessage handler for a record's presence channel (useCollaboration on
 * finding / testcase / asset): refetch the record when one of its fields is
 * saved live (`record_updated`, sent on every live save by the server), so
 * a page showing the field — but not editing it — keeps up with someone
 * typing on the edit page or in another inline editor. Debounced: a typist
 * saves about once a second.
 */
export function useRecordUpdatedRefresh(queryKey: readonly unknown[]) {
    const queryClient = useQueryClient();
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const keyRef = useRef(queryKey);
    keyRef.current = queryKey;
    useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
    return useCallback((data: any) => {
        if (data?.type !== 'record_updated') return;
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => queryClient.invalidateQueries({ queryKey: keyRef.current }), 600);
    }, [queryClient]);
}

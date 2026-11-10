'use client';

/**
 * Y.js room client shared by the Notes editor and the collaborative fields on
 * the edit pages / report builder. Speaks the Yjs sync + awareness wire
 * protocol over a raw WebSocket to the backend's binary relay
 * (/ws/yjs/note/{id}, /ws/yjs/field/{type}/{id}/{field}); CRDT merging happens
 * entirely in the clients.
 *
 * Seeding: the server sends the DB copy as `initial_content`. Alone in the
 * room → seed from it at once; peers present → give them a moment to sync
 * their (authoritative) state first, then fall back to the DB copy only if the
 * doc is still empty.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react';
import type { Editor } from '@tiptap/react';
import { Extension } from '@tiptap/core';
import { yCursorPluginKey } from '@tiptap/y-tiptap';
import * as Y from 'yjs';
import * as syncProtocol from 'y-protocols/sync';
import * as awarenessProtocol from 'y-protocols/awareness';
import * as encoding from 'lib0/encoding';
import * as decoding from 'lib0/decoding';
import { fixedCursorPlugin } from '@/lib/fixed-cursor-plugin';
import { useAuthStore } from '@/stores/auth-store';
import { getFreshAccessToken } from '@/lib/api';

const MSG_SYNC = 0;
const MSG_AWARENESS = 1;
const SYNC_STEP1 = 0;

// Cursor colors — consistent per user via hash.
const CURSOR_COLORS = [
    '#14b8a6', '#f97316', '#a855f7', '#ef4444',
    '#3b82f6', '#22c55e', '#eab308', '#ec4899',
];

export function getCursorColor(userId: string): string {
    let hash = 0;
    for (let i = 0; i < userId.length; i++) {
        hash = ((hash << 5) - hash + userId.charCodeAt(i)) | 0;
    }
    return CURSOR_COLORS[Math.abs(hash) % CURSOR_COLORS.length];
}

/** wss URL for a relay path such as `note/<id>` or `field/finding/<id>/impact`. */
export function yjsSocketUrl(path: string): string {
    if (typeof window === 'undefined') return '';
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const base = apiUrl && !apiUrl.includes(host)
        ? apiUrl.replace(/^http/, 'ws')
        : `${protocol}//${host}/api`;
    // Token is intentionally NOT in the URL — it's sent as the first frame
    // after open. CWE-598 (bearer-in-URL).
    return `${base}/ws/yjs/${path}`;
}

/** TipTap extension drawing peers' carets from awareness. */
export function createCollabCursorExtension(awareness: awarenessProtocol.Awareness) {
    return Extension.create({
        name: 'collaborationCursor',
        addProseMirrorPlugins() {
            return [
                // fixedCursorPlugin corrects the off-by-one caret position (assoc -1 → 0).
                fixedCursorPlugin(awareness, {
                    cursorBuilder: (user: any) => {
                        const cursor = document.createElement('span');
                        cursor.classList.add('collaboration-cursor__caret');
                        // GHSA-82vg-f3qp-gv8v: `user.color` is peer-supplied via
                        // Y.js awareness and the backend relay forwards it byte-for-byte.
                        // Assigning to the typed CSSOM property makes the browser parse
                        // the value as a single CSS token — a multi-declaration payload
                        // like `red;position:fixed;…` is rejected and the property is
                        // left unset. Do NOT go back to setAttribute('style', …).
                        cursor.style.borderColor = user.color;
                        const wj1 = document.createTextNode('⁠');
                        const wj2 = document.createTextNode('⁠');
                        const label = document.createElement('div');
                        label.classList.add('collaboration-cursor__label');
                        label.style.backgroundColor = user.color;
                        label.textContent = user.name;
                        cursor.appendChild(wj1);
                        cursor.appendChild(label);
                        cursor.appendChild(wj2);
                        return cursor;
                    },
                }),
            ];
        },
    });
}

export type YjsConnectionStatus = 'connecting' | 'connected' | 'disconnected';

interface UseYjsRoomOptions {
    /** Relay path (see yjsSocketUrl); null disables the room. */
    path: string | null;
    editorRef: MutableRefObject<Editor | null>;
    /** Apply the DB copy to an empty doc. */
    seed: (editor: Editor, content: string) => void;
    /** Server asked for the doc's content (notes' debounced persistence). */
    onRequestSave?: (data: any) => void;
    /** Record-field auto-save: returns the doc's Markdown. When set,
     *  `scheduleSave()` sends it (`save_content`) after a pause in typing,
     *  again after a reconnect, and on close / page hide. */
    autosave?: () => string;
}

/** Auto-save progress of a record field (see `autosave`). */
export type FieldSaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

// Quiet time after the author's last keystroke before the field is sent.
const AUTOSAVE_DEBOUNCE_MS = 1_200;
// After a reconnect, let the peer sync land before sending our copy, so a
// stale offline doc doesn't overwrite text others saved meanwhile.
const AUTOSAVE_RECONNECT_MS = 1_500;

/**
 * Creates the Y.Doc + awareness (stable for the component's lifetime; remount
 * with a new key to switch rooms) and keeps them synced with the room.
 */
export function useYjsRoom({ path, editorRef, seed, onRequestSave, autosave }: UseYjsRoomOptions) {
    const currentUser = useAuthStore((s) => s.user);
    const [status, setStatus] = useState<YjsConnectionStatus>('connecting');
    // True once the server's document state has been applied — used to keep the
    // loading overlay up until the content is actually present, not just the
    // WebSocket open.
    const [hasSynced, setHasSynced] = useState(false);
    // Where the doc's real content came from, once it has some: seeded from
    // the server's DB copy ('db') or synced from a peer ('peer'). Unlike
    // hasSynced there's no timeout fallback — until this is set the doc may
    // be a placeholder, and anything read from it must not be persisted.
    const [contentSource, setContentSource] = useState<'db' | 'peer' | null>(null);
    const [peerCount, setPeerCount] = useState(0);
    const [socket, setSocket] = useState<WebSocket | null>(null);

    const ydoc = useMemo(() => new Y.Doc(), []);
    const awareness = useMemo(() => new awarenessProtocol.Awareness(ydoc), [ydoc]);
    const userColor = useMemo(() => getCursorColor(currentUser?.id || 'anon'), [currentUser?.id]);
    const wsUrl = useMemo(() => (path ? yjsSocketUrl(path) : ''), [path]);

    // Latest callbacks without re-running the connection effect.
    const seedRef = useLatest(seed);
    const onRequestSaveRef = useLatest(onRequestSave);

    // ── Record-field auto-save ──
    const autosaveRef = useLatest(autosave);
    const [saveState, setSaveState] = useState<FieldSaveState>('idle');
    // The server's verdict on this user's rights in the room, which can change
    // mid-session (it re-checks access; see routers/websocket.py
    // _serve_yjs_room): null until known, false once edit is taken away.
    // `revoked` = view access was removed and the server closed the room.
    const [serverCanEdit, setServerCanEdit] = useState<boolean | null>(null);
    const [revoked, setRevoked] = useState(false);
    const socketRef = useRef<WebSocket | null>(null);
    const savePending = useRef(false);
    const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    // The doc's Markdown as last loaded or sent. Only a difference is sent:
    // editor housekeeping on load can fire "local" updates that change
    // nothing, and those mustn't count as edits (or show "Saved").
    const lastSent = useRef<string | null>(null);
    const hasSaved = useRef(false);
    const flushSave = useCallback(() => {
        clearTimeout(saveTimer.current);
        const get = autosaveRef.current;
        const ws = socketRef.current;
        // Not open → stays pending; onopen retries.
        if (!savePending.current || !get || !ws || ws.readyState !== WebSocket.OPEN) return;
        savePending.current = false;
        const content = get();
        if (content === lastSent.current) {
            setSaveState(hasSaved.current ? 'saved' : 'idle');
            return;
        }
        try {
            ws.send(JSON.stringify({ type: 'save_content', content }));
            lastSent.current = content;
            hasSaved.current = true;
            setSaveState('saving');
        } catch {
            savePending.current = true;
        }
    }, [autosaveRef]);
    const scheduleSave = useCallback((delay = AUTOSAVE_DEBOUNCE_MS) => {
        const get = autosaveRef.current;
        if (!get) return;
        if (!savePending.current && lastSent.current !== null && get() === lastSent.current) return;
        savePending.current = true;
        setSaveState('pending');
        clearTimeout(saveTimer.current);
        saveTimer.current = setTimeout(flushSave, delay);
    }, [autosaveRef, flushSave]);
    const flushSaveRef = useLatest(flushSave);
    // Baseline once the doc holds real content (DB seed or peer sync).
    useEffect(() => {
        if (contentSource && lastSent.current === null) lastSent.current = autosaveRef.current?.() ?? null;
    }, [contentSource, autosaveRef]);

    useEffect(() => {
        if (typeof window === 'undefined' || !wsUrl || !currentUser) return;
        const token = localStorage.getItem('access_token');
        if (!token) return;

        let ws: WebSocket;
        let reconnectTimeout: ReturnType<typeof setTimeout> | undefined;
        let retryCount = 0;
        let isCleaningUp = false;
        let initialContentPending: string | null = null;
        let initialContentTimer: ReturnType<typeof setTimeout> | undefined;
        // Belt-and-suspenders: guarantees the loading overlay is dismissed even
        // if neither a peer sync nor an initial_content frame ever arrives.
        let readyFallbackTimer: ReturnType<typeof setTimeout> | undefined;
        let current: WebSocket | null = null;
        // A read-only client's own writes never reach peers (the server drops
        // them), so its DB seed is local-only. Once an editor's content
        // arrives it's dropped first, or the viewer would show both copies.
        let viewerSeeded = false;

        const rebuildCursors = () => {
            const ed = editorRef.current;
            if (ed?.view) {
                try {
                    ed.view.dispatch(ed.view.state.tr.setMeta(yCursorPluginKey, { awarenessUpdated: true }));
                } catch { /* editor might be destroyed */ }
            }
        };

        const awarenessChangeHandler = () => {
            let others = 0;
            awareness.getStates().forEach((_state, clientID) => {
                if (clientID !== ydoc.clientID) others++;
            });
            setPeerCount(others);
        };
        awareness.on('change', awarenessChangeHandler);

        // setLocalState (not setLocalStateField): after cleanup calls
        // removeAwarenessStates() the local state is null, and
        // setLocalStateField silently does nothing when state is null.
        awareness.setLocalState({
            user: {
                name: currentUser.full_name || currentUser.username || 'Anonymous',
                color: userColor,
            },
        });

        const sendBinary = (msg: Uint8Array) => {
            if (current?.readyState === WebSocket.OPEN) current.send(msg);
        };

        const docUpdateHandler = (update: Uint8Array, origin: any) => {
            if (origin === 'remote') return; // Don't echo remote updates
            const encoder = encoding.createEncoder();
            encoding.writeVarUint(encoder, MSG_SYNC);
            syncProtocol.writeUpdate(encoder, update);
            sendBinary(encoding.toUint8Array(encoder));
        };
        ydoc.on('update', docUpdateHandler);

        const awarenessUpdateHandler = ({ added, updated, removed }: any) => {
            const changed = [...added, ...updated, ...removed];
            const encoder = encoding.createEncoder();
            encoding.writeVarUint(encoder, MSG_AWARENESS);
            encoding.writeVarUint8Array(encoder, awarenessProtocol.encodeAwarenessUpdate(awareness, changed));
            sendBinary(encoding.toUint8Array(encoder));
        };
        awareness.on('update', awarenessUpdateHandler);

        const connect = async () => {
            if (isCleaningUp) return;
            // Fresh per connect: a reconnect after the token lapsed must not
            // replay the one captured at mount.
            const token = await getFreshAccessToken();
            if (isCleaningUp || !token) return;
            setStatus('connecting');
            ws = new WebSocket(wsUrl);
            ws.binaryType = 'arraybuffer';
            current = ws;
            socketRef.current = ws;
            setSocket(ws);

            ws.onopen = () => {
                if (isCleaningUp) { ws.close(); return; }
                setStatus('connected');
                retryCount = 0;
                clearTimeout(readyFallbackTimer);
                readyFallbackTimer = setTimeout(() => setHasSynced(true), 2_000);

                // FIRST frame MUST be the auth bearer (backend closes 1008 after
                // 5s without it — _AUTH_FRAME_TIMEOUT_S in routers/websocket.py).
                ws.send(JSON.stringify({ type: 'auth', token }));
                // Our Y.js clientID, so the server can tell peers to drop our
                // cursor when we disconnect.
                ws.send(JSON.stringify({ type: 'register_client_id', client_id: ydoc.clientID }));

                // Sync step 1: our state vector → peers reply with what we're missing.
                const encoder = encoding.createEncoder();
                encoding.writeVarUint(encoder, MSG_SYNC);
                syncProtocol.writeSyncStep1(encoder, ydoc);
                sendBinary(encoding.toUint8Array(encoder));

                const aw = encoding.createEncoder();
                encoding.writeVarUint(aw, MSG_AWARENESS);
                encoding.writeVarUint8Array(aw, awarenessProtocol.encodeAwarenessUpdate(awareness, [ydoc.clientID]));
                sendBinary(encoding.toUint8Array(aw));

                if (savePending.current) {
                    clearTimeout(saveTimer.current);
                    saveTimer.current = setTimeout(() => flushSaveRef.current(), AUTOSAVE_RECONNECT_MS);
                }
            };

            ws.onmessage = (event) => {
                if (typeof event.data === 'string') {
                    let data: any;
                    try { data = JSON.parse(event.data); } catch { return; }

                    if (data.type === 'initial_content') {
                        // Store it; only apply if no peer sync fills the doc.
                        initialContentPending = data.content || '';
                        const canEdit = data.can_edit !== false;
                        setServerCanEdit(canEdit);
                        const seedFromDb = () => {
                            const ed = editorRef.current;
                            if (!ed) {
                                // Editor not mounted yet — retry shortly rather
                                // than dropping the pending DB content.
                                clearTimeout(initialContentTimer);
                                initialContentTimer = setTimeout(seedFromDb, 50);
                                return;
                            }
                            if (ydoc.getXmlFragment('default').length === 0) {
                                if (initialContentPending) {
                                    seedRef.current(ed, initialContentPending);
                                    viewerSeeded = !canEdit;
                                }
                                setContentSource((s) => s ?? 'db');
                            } else {
                                setContentSource((s) => s ?? 'peer');
                            }
                            initialContentPending = null;
                            setHasSynced(true);   // DB baseline settled — reveal the editor
                        };
                        clearTimeout(initialContentTimer);
                        if ((data.peers ?? 0) <= 0) {
                            // Alone — nobody holds a newer Y.js doc, seed at once.
                            seedFromDb();
                        } else {
                            // A peer is here — let them sync first so we don't double-seed.
                            initialContentTimer = setTimeout(seedFromDb, 300);
                        }
                    } else if (data.type === 'access_changed') {
                        setServerCanEdit(data.can_edit !== false);
                        if (data.can_edit === false) {
                            clearTimeout(saveTimer.current);
                            savePending.current = false;
                        }
                    } else if (data.type === 'access_revoked') {
                        // Don't reconnect: the next connect would be refused too.
                        isCleaningUp = true;
                        clearTimeout(saveTimer.current);
                        savePending.current = false;
                        setRevoked(true);
                        setServerCanEdit(false);
                        setStatus('disconnected');
                    } else if (data.type === 'request_save') {
                        onRequestSaveRef.current?.(data);
                    } else if (data.type === 'content_saved') {
                        setSaveState(savePending.current ? 'pending' : data.ok ? 'saved' : 'error');
                    } else if (data.type === 'peer_disconnected') {
                        const clientId = data.client_id;
                        if (clientId != null && clientId !== ydoc.clientID) {
                            awarenessProtocol.removeAwarenessStates(awareness, [clientId], 'peer_disconnect');
                            awareness.getStates().delete(clientId);
                            rebuildCursors();
                        }
                    }
                    return;
                }

                const bytes = new Uint8Array(event.data as ArrayBuffer);
                if (bytes.length < 1) return;
                const decoder = decoding.createDecoder(bytes);
                switch (decoding.readVarUint(decoder)) {
                    case MSG_SYNC: {
                        if (viewerSeeded && bytes.length > 1 && bytes[1] !== SYNC_STEP1) {
                            viewerSeeded = false;
                            const fragment = ydoc.getXmlFragment('default');
                            // 'remote' origin: not echoed (the server would drop it anyway).
                            ydoc.transact(() => fragment.delete(0, fragment.length), 'remote');
                        }
                        const reply = encoding.createEncoder();
                        encoding.writeVarUint(reply, MSG_SYNC);
                        syncProtocol.readSyncMessage(decoder, reply, ydoc, 'remote');
                        setHasSynced(true);
                        if (encoding.length(reply) > 1) sendBinary(encoding.toUint8Array(reply));
                        // Peer state arrived — cancel the DB-seed fallback.
                        if (ydoc.getXmlFragment('default').length > 0 && initialContentPending !== null) {
                            clearTimeout(initialContentTimer);
                            initialContentPending = null;
                            setContentSource((s) => s ?? 'peer');
                        }
                        break;
                    }
                    case MSG_AWARENESS:
                        awarenessProtocol.applyAwarenessUpdate(awareness, decoding.readVarUint8Array(decoder), 'remote');
                        break;
                }
            };

            ws.onclose = () => {
                if (isCleaningUp) return;
                setStatus('disconnected');
                current = null;
                setSocket(null);
                if (retryCount < 10) {
                    const delay = Math.max(2000, Math.min(1000 * Math.pow(2, retryCount), 30000));
                    reconnectTimeout = setTimeout(() => { retryCount++; connect(); }, delay);
                }
            };
            ws.onerror = () => { ws.close(); };
        };

        connect();

        // Aggressive stale-awareness cleanup: y-protocols' default timeout is
        // 30s, too slow for cursor removal. Evict peers silent for 10s.
        const STALE_THRESHOLD = 10_000;
        const peerLastSeen = new Map<number, number>();
        const trackPeerActivity = ({ added, updated, removed }: any) => {
            const now = Date.now();
            for (const id of [...(added || []), ...(updated || [])]) {
                if (id !== ydoc.clientID) peerLastSeen.set(id, now);
            }
            for (const id of (removed || [])) peerLastSeen.delete(id);
        };
        awareness.on('change', trackPeerActivity);
        const staleCleanupInterval = setInterval(() => {
            const now = Date.now();
            const states = awareness.getStates();
            const stale: number[] = [];
            states.forEach((_s, clientID) => {
                if (clientID === ydoc.clientID) return;
                const lastSeen = peerLastSeen.get(clientID);
                if ((lastSeen ? now - lastSeen : Infinity) > STALE_THRESHOLD) stale.push(clientID);
            });
            if (stale.length > 0) {
                awarenessProtocol.removeAwarenessStates(awareness, stale, 'timeout');
                for (const id of stale) {
                    peerLastSeen.delete(id);
                    states.delete(id);
                }
                // Dispatch directly — awareness.emit doesn't reliably trigger
                // ProseMirror's plugin apply.
                rebuildCursors();
            }
        }, 5_000);

        // Closing the tab skips React cleanup — send what's pending now.
        const onPageHide = () => flushSaveRef.current();
        window.addEventListener('pagehide', onPageHide);

        return () => {
            // 0. Send any unsaved field text while the socket is still open
            //    (close() delivers queued frames before the close handshake).
            flushSaveRef.current();
            window.removeEventListener('pagehide', onPageHide);
            isCleaningUp = true;
            clearTimeout(initialContentTimer);
            clearTimeout(readyFallbackTimer);
            clearTimeout(reconnectTimeout);
            clearInterval(staleCleanupInterval);
            awareness.off('change', trackPeerActivity);
            // 1. Remove our awareness state FIRST — while the update handler
            //    is still attached so it can broadcast the removal to peers.
            awarenessProtocol.removeAwarenessStates(awareness, [ydoc.clientID], 'local');
            // 2. Now remove handlers (no more updates to send).
            ydoc.off('update', docUpdateHandler);
            awareness.off('update', awarenessUpdateHandler);
            awareness.off('change', awarenessChangeHandler);
            // 3. Close the WebSocket last.
            current?.close();
            current = null;
            setSocket(null);
        };
    }, [wsUrl, currentUser, ydoc, awareness, userColor, editorRef, seedRef, onRequestSaveRef, flushSaveRef]);

    // Y.Doc + awareness live as long as the component.
    useEffect(() => () => {
        awareness.destroy();
        ydoc.destroy();
    }, [ydoc, awareness]);

    return { ydoc, awareness, status, hasSynced, contentSource, peerCount, socket, saveState, scheduleSave, serverCanEdit, revoked };
}

function useLatest<T>(value: T): MutableRefObject<T> {
    const [ref] = useState(() => ({ current: value }));
    ref.current = value;
    return ref;
}

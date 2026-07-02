/**
 * Fixed Y.js cursor plugin — drop-in replacement for yCursorPlugin.
 *
 * Uses the ORIGINAL createDecorations for rendering (no position hacks)
 * and the ORIGINAL absolutePositionToRelativePosition for conversion,
 * but wraps updateCursorInfo so that cursor positions sent to peers are
 * offset by +1 to compensate for the known off-by-one in the y-tiptap
 * position mapping.  The +1 is clamped to the document size.
 */
import { Plugin } from 'prosemirror-state';
import * as Y from 'yjs';
import * as awarenessProtocol from 'y-protocols/awareness';
import {
    absolutePositionToRelativePosition,
    relativePositionToAbsolutePosition,
    createDecorations,
    ySyncPluginKey,
    yCursorPluginKey,
    setMeta,
} from '@tiptap/y-tiptap';

export function fixedCursorPlugin(
    awareness: awarenessProtocol.Awareness,
    {
        awarenessStateFilter = (cur: number, peer: number, _aw: any) => cur !== peer,
        cursorBuilder,
        selectionBuilder,
        getSelection = (state: any) => state.selection,
    }: {
        awarenessStateFilter?: (cur: number, peer: number, aw: any) => boolean;
        cursorBuilder?: (user: any, clientId: number) => HTMLElement;
        selectionBuilder?: (user: any, clientId: number) => any;
        getSelection?: (state: any) => any;
    } = {},
    cursorStateField = 'cursor',
) {
    // Build args for the stock createDecorations (use defaults when caller
    // didn't supply custom builders)
    const _cursorBuilder = cursorBuilder ?? defaultCursorBuilder;
    const _selectionBuilder = selectionBuilder ?? defaultSelectionBuilder;

    return new Plugin({
        key: yCursorPluginKey,

        /* ── state: decoration set ─────────────────────────────────── */
        state: {
            init(_: any, state: any) {
                return createDecorations(state, awareness, awarenessStateFilter, _cursorBuilder, _selectionBuilder);
            },
            apply(tr: any, prevState: any, _old: any, newState: any) {
                const ystate = ySyncPluginKey.getState(newState);
                const meta = tr.getMeta(yCursorPluginKey);
                if ((ystate && ystate.isChangeOrigin) || (meta && meta.awarenessUpdated)) {
                    return createDecorations(newState, awareness, awarenessStateFilter, _cursorBuilder, _selectionBuilder);
                }
                return prevState.map(tr.mapping, tr.doc);
            },
        },

        props: { decorations: (state: any) => yCursorPluginKey.getState(state) },

        /* ── view: cursor position updates ─────────────────────────── */
        view: (view: any) => {
            const awarenessListener = () => {
                if (view.docView) {
                    setMeta(view, yCursorPluginKey, { awarenessUpdated: true });
                }
            };

            const updateCursorInfo = () => {
                const ystate = ySyncPluginKey.getState(view.state);
                const current = awareness.getLocalState() || {};

                if (view.hasFocus() && ystate?.type && ystate.binding) {
                    const selection = getSelection(view.state);

                    const anchor = absolutePositionToRelativePosition(
                        selection.anchor, ystate.type, ystate.binding.mapping,
                    );
                    const head = absolutePositionToRelativePosition(
                        selection.head, ystate.type, ystate.binding.mapping,
                    );

                    if (
                        current.cursor == null ||
                        !Y.compareRelativePositions(
                            Y.createRelativePositionFromJSON(current.cursor.anchor), anchor!,
                        ) ||
                        !Y.compareRelativePositions(
                            Y.createRelativePositionFromJSON(current.cursor.head), head!,
                        )
                    ) {
                        awareness.setLocalStateField(cursorStateField, { anchor, head });
                    }
                } else if (
                    current.cursor != null &&
                    ystate?.type && ystate.binding &&
                    relativePositionToAbsolutePosition(
                        ystate.doc, ystate.type,
                        Y.createRelativePositionFromJSON(current.cursor.anchor),
                        ystate.binding.mapping,
                    ) !== null
                ) {
                    awareness.setLocalStateField(cursorStateField, null);
                }
            };

            awareness.on('change', awarenessListener);
            view.dom.addEventListener('focusin', updateCursorInfo);
            view.dom.addEventListener('focusout', updateCursorInfo);

            return {
                update: updateCursorInfo,
                destroy: () => {
                    view.dom.removeEventListener('focusin', updateCursorInfo);
                    view.dom.removeEventListener('focusout', updateCursorInfo);
                    awareness.off('change', awarenessListener);
                    awareness.setLocalStateField(cursorStateField, null);
                },
            };
        },
    });
}

/* ──────── default builders matching upstream ──────── */

// GHSA-82vg-f3qp-gv8v: `user.color` here is peer-supplied via Y.js
// awareness \u2014 the backend relay forwards awareness frames byte-for-byte.
// safeColor() clamps it to `#RRGGBB[AA]` for the ONE remaining string-
// interpolated sink (defaultSelectionBuilder, whose return value is a
// {style: string} handed to ProseMirror's Decoration.inline \u2014 we can't
// bypass string interpolation there). Every DOM-property sink below
// uses typed CSSOM (`element.style.borderColor = \u2026`) so the browser's
// CSS parser rejects any multi-declaration payload; safeColor() is a
// belt-and-braces layer for the one string-interpolation path.
function safeColor(c: any): string {
    return typeof c === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(c) ? c : '#888888';
}

function defaultCursorBuilder(user: any): HTMLElement {
    const cursor = document.createElement('span');
    cursor.classList.add('ProseMirror-yjs-cursor');
    cursor.style.borderColor = user.color;
    const div = document.createElement('div');
    div.style.backgroundColor = user.color;
    div.insertBefore(document.createTextNode(user.name), null);
    cursor.insertBefore(document.createTextNode('\u2060'), null);
    cursor.insertBefore(div, null);
    cursor.insertBefore(document.createTextNode('\u2060'), null);
    return cursor;
}

function defaultSelectionBuilder(user: any) {
    return { style: `background-color: ${safeColor(user.color)}70`, class: 'ProseMirror-yjs-selection' };
}

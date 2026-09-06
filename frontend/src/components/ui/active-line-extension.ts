/**
 * Active-line highlight for the TipTap editors, shared by the standard editor
 * (tiptap-editor.tsx) and the collaborative notes editor (collaborative-editor.tsx).
 *
 * Implemented as a ProseMirror decoration rather than imperative classList
 * changes — ProseMirror re-applies decorations on every render, so the
 * highlight survives keystrokes instead of flickering. `enabledRef` lets the
 * React "line numbers" toggle turn it on/off; toggling should dispatch a
 * transaction with `activeLineKey` meta so the decoration recomputes.
 */
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

export const activeLineKey = new PluginKey('rwActiveLine');

export const createActiveLineExtension = (enabledRef: { current: boolean }) =>
    Extension.create({
        name: 'rwActiveLine',
        addProseMirrorPlugins() {
            return [
                new Plugin({
                    key: activeLineKey,
                    props: {
                        decorations(state) {
                            if (!enabledRef.current) return null;
                            const { selection, doc } = state;
                            const $from = selection.$from;
                            if ($from.depth < 1) return null;
                            const start = $from.before(1);
                            const node = $from.node(1);
                            return DecorationSet.create(doc, [
                                Decoration.node(start, start + node.nodeSize, { class: 'rw-active-line' }),
                            ]);
                        },
                    },
                }),
            ];
        },
    });

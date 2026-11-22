import { Mapping } from '@tiptap/pm/transform';

interface TransactionSource {
    on(event: 'transaction', cb: (props: { transaction: { mapping: Mapping } }) => void): unknown;
    off(event: 'transaction', cb: (props: { transaction: { mapping: Mapping } }) => void): unknown;
}

/**
 * Follow a document position through the edits made while something async
 * (an image upload) is in flight: typing, other uploads landing, a
 * collaborator's changes. A position captured before the await pointed at
 * the wrong place afterwards, or past the end of the document.
 */
export function trackPosition(editor: TransactionSource | null | undefined, pos: number) {
    const mapping = new Mapping();
    const onTransaction = ({ transaction }: { transaction: { mapping: Mapping } }) => {
        mapping.appendMapping(transaction.mapping);
    };
    editor?.on('transaction', onTransaction);
    return {
        /** The position now, and stop following. */
        current(): number {
            editor?.off('transaction', onTransaction);
            return mapping.map(pos);
        },
    };
}

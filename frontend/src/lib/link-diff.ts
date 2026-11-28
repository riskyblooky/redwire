/**
 * Which links a link dialog must create and which it must remove to turn the
 * currently linked set into the selected set. Order follows each input's
 * iteration order.
 */
export function diffLinkSelection(
    currentlyLinked: ReadonlySet<string>,
    selected: ReadonlySet<string>,
): { toLink: string[]; toUnlink: string[] } {
    return {
        toLink: [...selected].filter(id => !currentlyLinked.has(id)),
        toUnlink: [...currentlyLinked].filter(id => !selected.has(id)),
    };
}

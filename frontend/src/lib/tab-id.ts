/** A random id for this browser tab (page load). Sent with live-editor
 *  sockets and with version restores, so the server can tell "an editor in
 *  the tab doing the restore" (which reloads after it) from "the same user's
 *  editor in another tab" (which would save the old text back). Not a
 *  secret and not an identity — the user id still comes from the token. */
export const TAB_ID: string =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2) + Date.now().toString(36);

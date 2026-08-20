/**
 * Friendly-name resolution for users, in one place.
 *
 * Everywhere we show a person, prefer their full ("friendly") name and fall
 * back to the username when they haven't set one. The username is still the
 * stable identifier, so UI should surface it on hover (see <UserName>).
 */

export interface NamedUser {
    full_name?: string | null;
    username?: string | null;
}

/** The name to show for a user: full_name if set, else username, else fallback. */
export function displayName(
    user?: NamedUser | null,
    fallback = 'Unknown user',
): string {
    const full = user?.full_name?.trim();
    if (full) return full;
    const uname = user?.username?.trim();
    if (uname) return uname;
    return fallback;
}

/** Resolve from separate flattened fields (e.g. created_by_full_name / _username). */
export function displayNameFrom(
    fullName?: string | null,
    username?: string | null,
    fallback = 'Unknown user',
): string {
    return displayName({ full_name: fullName, username }, fallback);
}

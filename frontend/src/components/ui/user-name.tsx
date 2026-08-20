'use client';

import { cn } from '@/lib/utils';
import { displayName, type NamedUser } from '@/lib/display-name';

/**
 * Renders a user's friendly name (full_name, falling back to username) with the
 * `@username` shown on hover via the native title tooltip. Accepts either a
 * user object or separate name/username strings (for flattened API fields like
 * created_by_full_name / created_by_username).
 */
export function UserName({
    user,
    name,
    username,
    fallback = 'Unknown user',
    className,
}: {
    user?: NamedUser | null;
    name?: string | null;
    username?: string | null;
    fallback?: string;
    className?: string;
}) {
    const resolvedUser: NamedUser = user ?? { full_name: name, username };
    const label = displayName(resolvedUser, fallback);
    const uname = resolvedUser.username?.trim();
    // Only add the hover tooltip when the username differs from what's shown.
    const title = uname && uname !== label ? `@${uname}` : undefined;
    return (
        <span className={cn(className)} title={title}>
            {label}
        </span>
    );
}

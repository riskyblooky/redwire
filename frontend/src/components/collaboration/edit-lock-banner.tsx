'use client';

import { Lock } from 'lucide-react';
import { UserAvatar } from '@/components/ui/user-avatar';
import type { PresenceUser } from '@/lib/hooks/use-collaboration';

/**
 * Soft-lock banner shown on an edit page when another user is also
 * editing the same resource. Doesn't block — just warns. The Save
 * button on the host page should colour itself differently when
 * `otherEditors.length > 0` to reinforce the "this may overwrite"
 * implication.
 */
export function EditLockBanner({ otherEditors }: { otherEditors: PresenceUser[] }) {
    if (otherEditors.length === 0) return null;

    const names = otherEditors
        .map(u => u.full_name || u.username || 'Someone')
        .join(', ');

    return (
        <div className="mx-6 mt-3 mb-1 flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-200">
            <Lock className="h-4 w-4 text-amber-400 shrink-0" />
            <div className="flex items-center gap-2 flex-wrap">
                <span className="flex -space-x-2">
                    {otherEditors.slice(0, 4).map(u => (
                        <UserAvatar
                            key={u.id}
                            user={{ id: u.id, username: u.username || '', profile_photo: u.profile_photo || null }}
                            userId={u.id}
                            username={u.username || ''}
                            className="h-6 w-6 ring-2 ring-amber-500/40"
                        />
                    ))}
                </span>
                <span>
                    <strong className="font-semibold text-amber-100">{names}</strong>{' '}
                    {otherEditors.length === 1 ? 'is' : 'are'} also editing — saving will overwrite their unsaved work.
                </span>
            </div>
        </div>
    );
}

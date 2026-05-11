'use client';

import React, { useMemo } from 'react';
import { PresenceUser } from '@/lib/hooks/use-collaboration';
import { useAuthStore } from '@/stores/auth-store';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { getAvatarUrl } from '@/lib/utils';

interface PresenceIndicatorProps {
    users: PresenceUser[];
    maxDisplay?: number;
}

export function PresenceIndicator({ users, maxDisplay = 5 }: PresenceIndicatorProps) {
    const { user: currentUser } = useAuthStore();

    // Filter and sanitize users
    const displayList = useMemo(() => {
        if (!users) return [];

        // Use a Map to ensure uniqueness by ID and prefer users with more metadata
        const userMap = new Map<string, PresenceUser>();

        users.forEach(u => {
            if (!u.id) return;
            const existing = userMap.get(u.id);
            // Prefer the entry with a username/fullname, as some connections might be in "identifying" state
            if (!existing || (!existing.username && u.username) || (!existing.full_name && u.full_name)) {
                userMap.set(u.id, u);
            }
        });

        return Array.from(userMap.values());
    }, [users]);

    if (displayList.length === 0) return null;

    const displayUsers = displayList.slice(0, maxDisplay);
    const remainingCount = displayList.length - maxDisplay;

    const getInitials = (user: PresenceUser) => {
        if (user.full_name) {
            return user.full_name
                .split(' ')
                .map((n) => n[0])
                .join('')
                .toUpperCase()
                .slice(0, 2);
        }
        if (user.username && user.username !== 'operator') {
            return user.username.substring(0, 2).toUpperCase();
        }
        return '??';
    };

    // Use HEX colors to avoid tailwind dynamic class purging issues
    const hexColors = [
        '#ef4444', '#f97316', '#f59e0b',
        '#22c55e', '#10b981', '#14b8a6',
        '#06b6d4', '#0ea5e9', '#3b82f6',
        '#6366f1', '#8b5cf6', '#a855f7',
        '#d946ef', '#ec4899', '#f43f5e'
    ];

    const getHexColor = (id: string) => {
        let hash = 0;
        for (let i = 0; i < id.length; i++) {
            hash = id.charCodeAt(i) + ((hash << 5) - hash);
        }
        const index = Math.abs(hash) % hexColors.length;
        return hexColors[index];
    };


    return (
        <div className="flex items-center px-1.5 py-1 bg-slate-900/60 rounded-full border border-slate-800/80 shadow-inner backdrop-blur-md h-9">
            <TooltipProvider delayDuration={0}>
                <div className="flex items-center -space-x-2 mr-1">
                    {displayUsers.map((user) => (
                        <Tooltip key={user.id}>
                            <TooltipTrigger asChild>
                                <div className="relative group cursor-default">
                                    <Avatar className="h-7 w-7 ring-2 ring-slate-950 transition-all group-hover:z-30 group-hover:scale-110 shadow-lg">
                                        {user.profile_photo ? (
                                            <AvatarImage
                                                src={getAvatarUrl(user.profile_photo)}
                                                alt={user.full_name || user.username || 'User'}
                                            />
                                        ) : null}
                                        <AvatarFallback
                                            className="text-white text-[10px] font-bold border border-white/10"
                                            style={{ backgroundColor: getHexColor(user.id) }}
                                        >
                                            {getInitials(user)}
                                        </AvatarFallback>
                                    </Avatar>
                                    <span className="absolute bottom-0 right-0 block h-2 w-2 rounded-full ring-1 ring-slate-950 bg-green-500 shadow-xs" />
                                </div>
                            </TooltipTrigger>
                            <TooltipContent
                                side="bottom"
                                avoidCollisions={false}
                                className="bg-slate-900 border-slate-800 text-white p-2 shadow-2xl z-1000 min-w-[140px] animate-in fade-in zoom-in-95 duration-100"
                                sideOffset={10}
                            >
                                <div className="flex flex-col gap-0.5">
                                    <p className="text-xs font-semibold flex items-center justify-between gap-2">
                                        <span className="truncate max-w-[100px]">{user.full_name || user.username || 'Identifying...'}</span>
                                        {user.id === currentUser?.id && <span className="text-[9px] bg-indigo-500/20 text-indigo-400 px-1 rounded font-bold uppercase tracking-tighter">You</span>}
                                    </p>
                                    <p className="text-[10px] text-slate-500 capitalize">{user.role || 'connecting...'}</p>
                                </div>
                            </TooltipContent>
                        </Tooltip>
                    ))}

                    {remainingCount > 0 && (
                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-800 border border-slate-700 ring-2 ring-slate-950 z-10 shadow-lg">
                            <span className="text-[10px] font-bold text-slate-300">+{remainingCount}</span>
                        </div>
                    )}
                </div>
                {displayList.length === 1 && displayList[0].id === currentUser?.id ? (
                    <span className="text-[10px] text-slate-500 font-medium px-2 italic whitespace-nowrap">Watching solo</span>
                ) : (
                    <div className="w-1" />
                )}
            </TooltipProvider>
        </div>
    );
}

'use client';

import React from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { getAvatarUrl } from '@/lib/utils';
import { User } from '@/lib/types';
import { cn } from '@/lib/utils';

export interface UserAvatarProps {
    user?: Partial<User> | null;
    userId?: string;
    username?: string | null;
    className?: string;
}

export function UserAvatar({ user, userId, username, className }: UserAvatarProps) {
    // If we have a full user object, prefer that
    const id = user?.id || userId || 'unknown';
    const name = user?.username || user?.full_name || username || '??';
    const profilePhoto = user?.profile_photo;

    const getInitials = (name: string) => {
        if (!name) return '??';
        if (name === '??') return '??';

        // precise initials for full names
        if (name.includes(' ')) {
            return name
                .split(' ')
                .map((n) => n[0])
                .join('')
                .toUpperCase()
                .slice(0, 2);
        }

        return name.substring(0, 2).toUpperCase();
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
        <Avatar className={cn("h-8 w-8 ring-2 ring-slate-950 shadow-lg", className)}>
            {profilePhoto ? (
                <AvatarImage
                    src={getAvatarUrl(profilePhoto)}
                    alt={name}
                />
            ) : null}
            <AvatarFallback
                className="text-white text-[10px] font-bold border border-white/10"
                style={{ backgroundColor: getHexColor(id) }}
            >
                {getInitials(name)}
            </AvatarFallback>
        </Avatar>
    );
}

'use client';

/**
 * The shared frame of the finding / asset / test-case detail sheets: the
 * non-modal scroll fix, the Sheet with its loading state and accent bar,
 * the linked-note rows, and the Metadata rows. The three sheets were near
 * copies of each other; their bodies (fields, sections) stay their own.
 */

import { useEffect, type ComponentType, type ReactNode } from 'react';
import Link from 'next/link';
import { Loader2, StickyNote } from 'lucide-react';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet';
import { UserAvatar } from '@/components/ui/user-avatar';
import { UserName } from '@/components/ui/user-name';
import { cn, parseUTCDate } from '@/lib/utils';

/**
 * Radix Dialog locks body scroll even with modal={false}. While a non-modal
 * sheet is open, keep clearing the lock on a 50 ms interval to beat Radix's
 * scheduler, so the page behind stays scrollable.
 */
export function useNonModalScrollUnlock(nonModal: boolean | undefined, open: boolean) {
    useEffect(() => {
        if (!nonModal || !open) return;
        const unlock = () => {
            if (document.body.style.overflow) document.body.style.removeProperty('overflow');
            if (document.body.style.paddingRight) document.body.style.removeProperty('padding-right');
        };
        unlock();
        const id = setInterval(unlock, 50);
        return () => clearInterval(id);
    }, [nonModal, open]);
}

interface DetailSheetShellProps<T> {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    /** When true, background stays interactive (no overlay, no scroll lock). */
    nonModal?: boolean;
    /** The sheet's record; the spinner shows while loading or while it's missing. */
    record: T | null | undefined;
    isLoading?: boolean;
    /** Screen-reader title while loading, e.g. "Loading asset details". */
    loadingTitle: string;
    spinnerClassName?: string;
    /** Background class of the bar across the top (severity, type, category). */
    accent?: (record: T) => string | undefined;
    /** Renders the loaded record (name the parameter after the record so the
     *  body reads the narrowed, non-null value). */
    children: (record: T) => ReactNode;
}

export function DetailSheetShell<T>({
    open, onOpenChange, nonModal, record, isLoading, loadingTitle, spinnerClassName, accent, children,
}: DetailSheetShellProps<T>) {
    useNonModalScrollUnlock(nonModal, open);
    return (
        <Sheet open={open} onOpenChange={onOpenChange} modal={!nonModal}>
            <SheetContent
                side="right"
                nonModal={nonModal}
                className="w-full sm:max-w-[40vw] bg-slate-950 border-slate-800 p-0 overflow-y-auto"
            >
                {isLoading || record == null ? (
                    <div className="flex items-center justify-center h-full">
                        <VisuallyHidden><SheetTitle>{loadingTitle}</SheetTitle></VisuallyHidden>
                        <Loader2 className={cn('h-8 w-8 animate-spin', spinnerClassName || 'text-primary')} />
                    </div>
                ) : (
                    <div className="flex flex-col h-full">
                        <div className={cn('h-1.5 w-full shrink-0', accent?.(record) || 'bg-slate-500')} />
                        {children(record)}
                    </div>
                )}
            </SheetContent>
        </Sheet>
    );
}

/** One row per linked note, linking to it on the engagement's Notes tab. */
export function LinkedNoteRows({ notes, engagementId, onNavigate }: {
    notes: { id: string; title: string }[];
    engagementId: string;
    onNavigate: () => void;
}) {
    return (
        <div className="space-y-1.5">
            {notes.map((note) => (
                <Link
                    key={note.id}
                    href={`/engagements/${engagementId}?tab=notes&noteId=${note.id}`}
                    className="flex items-center gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/60 hover:border-teal-500/30 transition-colors group"
                    onClick={onNavigate}
                >
                    <StickyNote className="h-3.5 w-3.5 text-teal-400 shrink-0" />
                    <span className="text-xs font-medium text-slate-300 group-hover:text-teal-300 truncate">{note.title}</span>
                </Link>
            ))}
        </div>
    );
}

/** A label / value row of a sheet's Metadata section. */
export function MetaRow({ icon: Icon, label, children }: {
    icon: ComponentType<{ className?: string }>;
    label: string;
    children: ReactNode;
}) {
    return (
        <div className="flex items-center justify-between text-[10px]">
            <span className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-tighter">
                <Icon className="h-3 w-3" /> {label}
            </span>
            {children}
        </div>
    );
}

export function MetaDate({ value }: { value: string }) {
    return <span className="text-slate-300">{parseUTCDate(value).toLocaleString()}</span>;
}

/** Avatar + name of a record's creator. ``avatarUser`` overrides the
 *  engagement-roster lookup for the avatar (the finding sheet passes the
 *  creator's own photo, which works when they're no longer assigned). */
export function MetaCreator({ users, id, username, fullName, avatarUser }: {
    users?: any[];
    id?: string | null;
    username?: string | null;
    fullName?: string | null;
    avatarUser?: any;
}) {
    const rosterUser = users?.find((u: any) => u.id === id);
    return (
        <div className="flex items-center gap-2">
            <UserAvatar
                user={avatarUser ?? rosterUser}
                userId={id ?? undefined}
                username={username || id || undefined}
                className="h-5 w-5"
            />
            <UserName
                className="text-slate-300"
                user={rosterUser}
                name={fullName ?? undefined}
                username={username ?? undefined}
                fallback={id?.slice(0, 8)}
            />
        </div>
    );
}

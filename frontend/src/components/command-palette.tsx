'use client';

/**
 * Global command palette — Cmd/Ctrl+K opens a fuzzy-searchable action
 * list, Linear/Slack-style. Actions cover:
 *
 *  - **Create**: new finding, test case, asset, note. When the current
 *    route is /engagements/<id>/*, the create actions target THAT
 *    engagement (pre-selecting it on the new-<resource> page).
 *    Otherwise they open the "new" page cold, letting the user pick.
 *  - **Jump to engagement**: dynamic list from useEngagements(). Fuzzy
 *    filter across name + client name.
 *  - **Navigate**: top-level nav destinations (dashboard, engagements,
 *    calendar, planning, admin, profile, imports, help).
 *
 * Vim-style two-key sequences work when the palette is CLOSED:
 *   N F  — new finding
 *   N T  — new test case
 *   N A  — new asset
 *   N N  — new note (in current engagement, else opens palette)
 *   G E  — go to engagements
 *   G H  — go to dashboard (home)
 *   G I  — go to imports
 *   G A  — go to admin
 *   G P  — go to profile
 *   G C  — go to calendar
 *   G L  — go to planning
 *
 * The sequence times out after 1200 ms of inactivity — a stray N or G
 * on its own does nothing.
 *
 * Mounted once at the DashboardLayout root so every authenticated page
 * gets it for free.
 */
import { useEffect, useMemo, useState, useRef, useCallback } from 'react';
import { useRouter, usePathname, useParams } from 'next/navigation';
import {
    CommandDialog,
    CommandInput,
    CommandList,
    CommandEmpty,
    CommandGroup,
    CommandItem,
    CommandSeparator,
    CommandShortcut,
} from '@/components/ui/command';
import { useEngagements } from '@/lib/hooks/use-engagements';
import {
    LayoutDashboard,
    Briefcase,
    Calendar,
    GanttChart,
    Settings,
    User,
    Upload,
    HelpCircle,
    Bug,
    CheckSquare,
    Server,
    StickyNote,
    ArrowRight,
} from 'lucide-react';

/** Sniff the current engagement id from /engagements/[id]/* URLs. */
function useCurrentEngagementId(): string | null {
    const pathname = usePathname() || '';
    const params = useParams() as Record<string, string | string[]> | null;
    // useParams handles the [id] segment when we're on an engagement route.
    if (pathname.startsWith('/engagements/') && params?.id) {
        const raw = Array.isArray(params.id) ? params.id[0] : params.id;
        // Guard against the "new" and list routes which don't have a real id.
        if (raw && raw !== 'new') return raw;
    }
    return null;
}

/**
 * Two-key sequence tracker. Listens on document keydown; when a
 * "leader" key (n or g) is pressed while nothing typable is focused,
 * we start a short timer and watch for the second key.
 *
 * ``onSequence`` gets called with the joined pair (e.g. "nf", "ge").
 * Return true to indicate a match was consumed; on match we swallow
 * the follow-up so it doesn't leak into any focused input.
 */
function useKeySequences(onSequence: (combo: string) => boolean) {
    const bufferRef = useRef<string | null>(null);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const clear = useCallback(() => {
        bufferRef.current = null;
        if (timerRef.current) {
            clearTimeout(timerRef.current);
            timerRef.current = null;
        }
    }, []);

    useEffect(() => {
        const isTypableTarget = (t: EventTarget | null): boolean => {
            if (!(t instanceof HTMLElement)) return false;
            const tag = t.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
            if (t.isContentEditable) return true;
            return false;
        };
        const onKey = (e: KeyboardEvent) => {
            // Ignore modifier chords — those are for the palette open + real hotkeys.
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            // Ignore when the user is typing into an input.
            if (isTypableTarget(e.target)) return;
            const k = e.key.toLowerCase();
            if (!bufferRef.current) {
                if (k === 'n' || k === 'g') {
                    bufferRef.current = k;
                    timerRef.current = setTimeout(clear, 1200);
                }
                return;
            }
            // Second key
            const combo = bufferRef.current + k;
            const consumed = onSequence(combo);
            if (consumed) {
                e.preventDefault();
            }
            clear();
        };
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('keydown', onKey);
            clear();
        };
    }, [onSequence, clear]);
}

export function CommandPalette() {
    const [open, setOpen] = useState(false);
    const router = useRouter();
    const engagementId = useCurrentEngagementId();
    const { data: engagements = [] } = useEngagements();

    // Cmd/Ctrl+K toggle.
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                setOpen((v) => !v);
            }
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, []);

    // Navigation helpers. When engagementId is set (current route is inside
    // an engagement), create-shortcuts pre-scope to it.
    const go = useCallback(
        (href: string) => {
            router.push(href);
            setOpen(false);
        },
        [router],
    );

    const newFinding = useCallback(() => {
        go(engagementId ? `/findings/new?engagementId=${engagementId}` : '/findings/new');
    }, [go, engagementId]);
    const newTestCase = useCallback(() => {
        go(engagementId ? `/testcases/new?engagementId=${engagementId}` : '/testcases/new');
    }, [go, engagementId]);
    const newAsset = useCallback(() => {
        go(engagementId ? `/assets/new?engagementId=${engagementId}` : '/assets/new');
    }, [go, engagementId]);
    const newNote = useCallback(() => {
        // Notes only make sense scoped to an engagement — open the palette
        // when no engagement context so the user can pick one.
        if (engagementId) {
            go(`/engagements/${engagementId}?tab=notes`);
        } else {
            setOpen(true);
        }
    }, [go, engagementId]);

    // Two-letter sequences. Only fire when palette is closed — otherwise
    // typing "n" while searching in the palette would be captured.
    useKeySequences((combo) => {
        if (open) return false;
        switch (combo) {
            case 'nf': newFinding(); return true;
            case 'nt': newTestCase(); return true;
            case 'na': newAsset(); return true;
            case 'nn': newNote(); return true;
            case 'ge': go('/engagements'); return true;
            case 'gh': go('/dashboard'); return true;
            case 'gi': go('/imports'); return true;
            case 'ga': go('/admin'); return true;
            case 'gp': go('/profile'); return true;
            case 'gc': go('/calendar'); return true;
            case 'gl': go('/planning'); return true;
        }
        return false;
    });

    // Cache-friendly derivations
    const engagementItems = useMemo(
        () => engagements.slice(0, 30).map((e) => ({
            id: e.id,
            name: e.name,
            client: e.client_name || '',
        })),
        [engagements],
    );

    return (
        <CommandDialog open={open} onOpenChange={setOpen}>
            <CommandInput placeholder="Type a command or search…" />
            <CommandList>
                <CommandEmpty>No results.</CommandEmpty>

                <CommandGroup heading="Create">
                    <CommandItem onSelect={newFinding}>
                        <Bug />
                        <span>New Finding{engagementId && <span className="text-slate-500"> in current engagement</span>}</span>
                        <CommandShortcut>N F</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={newTestCase}>
                        <CheckSquare />
                        <span>New Test Case{engagementId && <span className="text-slate-500"> in current engagement</span>}</span>
                        <CommandShortcut>N T</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={newAsset}>
                        <Server />
                        <span>New Asset{engagementId && <span className="text-slate-500"> in current engagement</span>}</span>
                        <CommandShortcut>N A</CommandShortcut>
                    </CommandItem>
                    {engagementId && (
                        <CommandItem onSelect={newNote}>
                            <StickyNote />
                            <span>Open Notes on current engagement</span>
                            <CommandShortcut>N N</CommandShortcut>
                        </CommandItem>
                    )}
                </CommandGroup>

                <CommandSeparator />

                {engagementItems.length > 0 && (
                    <>
                        <CommandGroup heading="Jump to engagement">
                            {engagementItems.map((eng) => (
                                <CommandItem
                                    key={eng.id}
                                    // Include the client name in the value so cmdk's built-in
                                    // fuzzy matcher can filter on "novatech" or "acme" too.
                                    value={`${eng.name} ${eng.client}`}
                                    onSelect={() => go(`/engagements/${eng.id}`)}
                                >
                                    <Briefcase />
                                    <span className="flex-1">{eng.name}</span>
                                    {eng.client && (
                                        <span className="text-xs text-slate-500 ml-2">{eng.client}</span>
                                    )}
                                    <ArrowRight className="text-slate-600" />
                                </CommandItem>
                            ))}
                        </CommandGroup>
                        <CommandSeparator />
                    </>
                )}

                <CommandGroup heading="Navigate">
                    <CommandItem onSelect={() => go('/dashboard')}>
                        <LayoutDashboard />
                        <span>Dashboard</span>
                        <CommandShortcut>G H</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => go('/engagements')}>
                        <Briefcase />
                        <span>Engagements</span>
                        <CommandShortcut>G E</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => go('/calendar')}>
                        <Calendar />
                        <span>Calendar</span>
                        <CommandShortcut>G C</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => go('/planning')}>
                        <GanttChart />
                        <span>Planning</span>
                        <CommandShortcut>G L</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => go('/imports')}>
                        <Upload />
                        <span>Import Scanner Output</span>
                        <CommandShortcut>G I</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => go('/admin')}>
                        <Settings />
                        <span>Admin Settings</span>
                        <CommandShortcut>G A</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => go('/profile')}>
                        <User />
                        <span>Profile</span>
                        <CommandShortcut>G P</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => window.open('/', '_blank')}>
                        <HelpCircle />
                        <span>Help / Docs</span>
                    </CommandItem>
                </CommandGroup>
            </CommandList>
        </CommandDialog>
    );
}

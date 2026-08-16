'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { HelpCircle, BookOpen } from 'lucide-react';
import { getPageHelp } from '@/lib/page-help';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { MarkdownPreview } from '@/components/ui/markdown-editor';
import { Button } from '@/components/ui/button';

/**
 * Header "?" button. Reads the current pathname, looks up its page help, and
 * opens a modal explaining what the page is for with an optional deep-link into
 * the full /help guide. Renders nothing on pages with no registered help.
 */
export function PageHelpButton() {
    const pathname = usePathname();
    const router = useRouter();
    const [open, setOpen] = useState(false);
    const help = getPageHelp(pathname || '');
    if (!help) return null;

    return (
        <>
            <button
                onClick={() => setOpen(true)}
                title="What is this page?"
                aria-label="Page help"
                className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-800/60 hover:text-white"
            >
                <HelpCircle className="h-5 w-5" />
            </button>

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <HelpCircle className="h-5 w-5 text-blue-400" />
                            {help.title}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="text-sm text-slate-300">
                        <MarkdownPreview value={help.body} />
                    </div>
                    {help.doc && (
                        <Button
                            variant="outline"
                            className="mt-2 gap-2 border-slate-700"
                            onClick={() => {
                                setOpen(false);
                                router.push(`/help?doc=${help.doc}`);
                            }}
                        >
                            <BookOpen className="h-4 w-4" />
                            Open the full guide
                        </Button>
                    )}
                </DialogContent>
            </Dialog>
        </>
    );
}

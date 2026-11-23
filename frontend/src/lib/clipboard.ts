import { toast } from 'sonner';

/**
 * Copy text and report whether it worked. navigator.clipboard.writeText is
 * async and rejects when the page lacks focus, isn't a secure context or
 * the browser denies permission — call sites that didn't await it showed
 * "copied" either way. On failure this shows one error toast and returns
 * false, so callers only confirm success:
 *
 *     if (await copyText(token)) setCopied(true);
 */
export async function copyText(text: string): Promise<boolean> {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        toast.error("Couldn't copy to the clipboard", { description: 'Your browser blocked clipboard access.' });
        return false;
    }
}

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { UploadCloud, ClipboardPaste, FileIcon, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

/**
 * Shared upload affordance for every engagement-scoped attachment surface
 * (finding evidence, testcase evidence, engagement attachments, intel
 * attachments, engagement + infra vault files).
 *
 * Deliberately presentational: it produces a validated `File[]` and hands
 * it to `onFiles`. It never POSTs. The upload endpoints it feeds do NOT
 * share a wire contract — intel wants a `files` (plural) field, vault
 * requires a `name`, markdown-images requires an `engagement_id` — so
 * ownership of the request stays with each surface's existing mutation
 * hook and this component stays free of endpoint plumbing.
 */

// Only one dropzone may consume a given paste. Without this, a quick-add
// dialog rendered over a page that already has an inline dropzone would
// see both handlers fire and upload the clipboard image twice. Mount order
// is the tiebreak: the most recently mounted dropzone (i.e. the dialog)
// wins, which matches what the user is looking at.
type PasteSubscriber = { accept: (files: File[]) => void };
const pasteStack: PasteSubscriber[] = [];
let documentPasteBound = false;

function isTypingTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false;
    const tag = target.tagName.toLowerCase();
    return tag === 'input' || tag === 'textarea' || target.isContentEditable;
}

function filesFromClipboard(data: DataTransfer | null): File[] {
    if (!data) return [];
    const out: File[] = [];
    // `items` carries screenshots (kind === 'file'); `files` carries an
    // OS file-manager copy. A given paste populates one or the other.
    for (const item of Array.from(data.items ?? [])) {
        if (item.kind !== 'file') continue;
        const f = item.getAsFile();
        if (f) out.push(f);
    }
    if (out.length === 0) out.push(...Array.from(data.files ?? []));
    return out;
}

/**
 * Screenshot pastes arrive named `image.png` regardless of source, so a
 * finding with three pasted screenshots would show three identical rows.
 * Stamp them instead.
 */
function nameAnonymousPaste(file: File): File {
    if (file.name && file.name !== 'image.png' && file.name !== 'blob') return file;
    const ext = file.type.split('/')[1]?.replace('+xml', '') || 'png';
    const ts = new Date()
        .toISOString()
        .replace(/[-:T]/g, '')
        .slice(0, 15); // YYYYMMDDhhmmss
    return new File([file], `pasted-${ts}.${ext}`, {
        type: file.type,
        lastModified: file.lastModified,
    });
}

function onDocumentPaste(e: ClipboardEvent) {
    // Let the caret win — pasting text into a description field must not
    // be hijacked by a dropzone listening at the document level.
    if (isTypingTarget(e.target)) return;
    const top = pasteStack[pasteStack.length - 1];
    if (!top) return;
    const files = filesFromClipboard(e.clipboardData);
    if (files.length === 0) return;
    e.preventDefault();
    top.accept(files.map(nameAnonymousPaste));
}

/** Does `file` satisfy an `accept`-style filter (".csv,.xlsx" / "image/*")? */
function matchesAccept(file: File, accept?: string): boolean {
    if (!accept) return true;
    const rules = accept.split(',').map((r) => r.trim().toLowerCase()).filter(Boolean);
    if (rules.length === 0) return true;
    const name = file.name.toLowerCase();
    const type = file.type.toLowerCase();
    return rules.some((rule) => {
        if (rule.startsWith('.')) return name.endsWith(rule);
        if (rule.endsWith('/*')) return type.startsWith(rule.slice(0, -1));
        return type === rule;
    });
}

export interface FileDropzoneProps {
    /** Receives files that passed the `accept` and `maxSizeBytes` gates. */
    onFiles: (files: File[]) => void;
    multiple?: boolean;
    /** Standard `accept` string. Gates drop and paste too, not just browse. */
    accept?: string;
    /** Client-side size gate. Surfaces a toast rather than a server 413. */
    maxSizeBytes?: number;
    disabled?: boolean;
    /** Set false for surfaces where a clipboard image is meaningless. */
    pasteEnabled?: boolean;
    /** Tighter padding — for dialogs. */
    compact?: boolean;
    title?: string;
    hint?: string;
    className?: string;
}

export function FileDropzone({
    onFiles,
    multiple = false,
    accept,
    maxSizeBytes,
    disabled = false,
    pasteEnabled = true,
    compact = false,
    title,
    hint,
    className,
}: FileDropzoneProps) {
    const [dragActive, setDragActive] = useState(false);
    const [pasteFlash, setPasteFlash] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    // `onFiles` is typically an inline arrow, so a new identity every
    // render. Route the paste subscription through a ref so the effect
    // below doesn't tear down and re-register the listener each render
    // (which would also reshuffle the stack and break dialog precedence).
    const onFilesRef = useRef(onFiles);
    onFilesRef.current = onFiles;

    const acceptFiles = useCallback(
        (incoming: File[]) => {
            if (disabled || incoming.length === 0) return;

            const batch = multiple ? incoming : incoming.slice(0, 1);
            const passed: File[] = [];

            for (const file of batch) {
                if (!matchesAccept(file, accept)) {
                    toast.error(`${file.name} isn't an accepted file type`);
                    continue;
                }
                if (maxSizeBytes && file.size > maxSizeBytes) {
                    const mb = (maxSizeBytes / (1024 * 1024)).toFixed(0);
                    toast.error(`${file.name} is larger than the ${mb} MB limit`);
                    continue;
                }
                passed.push(file);
            }

            if (passed.length > 0) onFilesRef.current(passed);
        },
        [accept, disabled, maxSizeBytes, multiple],
    );

    const acceptFilesRef = useRef(acceptFiles);
    acceptFilesRef.current = acceptFiles;

    useEffect(() => {
        if (!pasteEnabled || disabled) return;

        const subscriber: PasteSubscriber = {
            accept: (files) => {
                acceptFilesRef.current(files);
                // Confirm the paste landed — without this the only signal
                // is a new row appearing, which is easy to miss on a long page.
                setPasteFlash(true);
                window.setTimeout(() => setPasteFlash(false), 600);
            },
        };
        pasteStack.push(subscriber);

        if (!documentPasteBound) {
            document.addEventListener('paste', onDocumentPaste);
            documentPasteBound = true;
        }

        return () => {
            const i = pasteStack.indexOf(subscriber);
            if (i !== -1) pasteStack.splice(i, 1);
            if (pasteStack.length === 0 && documentPasteBound) {
                document.removeEventListener('paste', onDocumentPaste);
                documentPasteBound = false;
            }
        };
    }, [pasteEnabled, disabled]);

    const handleDrag = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            e.stopPropagation();
            if (disabled) return;
            if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
            else if (e.type === 'dragleave') setDragActive(false);
        },
        [disabled],
    );

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            e.stopPropagation();
            setDragActive(false);
            acceptFiles(Array.from(e.dataTransfer.files ?? []));
        },
        [acceptFiles],
    );

    const defaultTitle = pasteEnabled
        ? 'Click to upload, drag and drop, or paste'
        : 'Click to upload or drag and drop';

    return (
        <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => !disabled && inputRef.current?.click()}
            className={cn(
                'relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed text-center transition-all',
                compact ? 'p-6' : 'p-8',
                disabled
                    ? 'cursor-not-allowed border-border bg-muted/20 opacity-60'
                    : 'cursor-pointer border-border bg-muted/20 hover:border-muted-foreground/40 hover:bg-muted/30',
                dragActive && !disabled && 'border-primary bg-primary/10',
                pasteFlash && 'border-primary bg-primary/10',
                className,
            )}
        >
            <input
                ref={inputRef}
                type="file"
                className="hidden"
                multiple={multiple}
                accept={accept}
                disabled={disabled}
                onChange={(e) => {
                    acceptFiles(Array.from(e.target.files ?? []));
                    // Reset so re-picking the same file fires onChange again.
                    e.target.value = '';
                }}
            />

            <div
                className={cn(
                    'rounded-full p-3 transition-colors',
                    dragActive || pasteFlash
                        ? 'bg-primary/20 text-primary'
                        : 'bg-muted text-muted-foreground',
                )}
            >
                {pasteFlash ? (
                    <ClipboardPaste className="h-6 w-6" />
                ) : (
                    <UploadCloud className="h-6 w-6" />
                )}
            </div>

            <div>
                <p className="text-sm font-medium text-foreground">
                    {pasteFlash ? 'Pasted from clipboard' : title || defaultTitle}
                </p>
                {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
            </div>

            {pasteEnabled && !disabled && (
                <p className="text-[11px] text-muted-foreground/70">
                    Screenshot in your clipboard? Press{' '}
                    <kbd className="rounded border border-border bg-muted px-1 py-0.5 font-mono text-[10px]">
                        Ctrl+V
                    </kbd>{' '}
                    anywhere on this page
                </p>
            )}
        </div>
    );
}

export function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Thumbnail for a not-yet-uploaded image. Object URLs are revoked on
 * unmount — a paste-heavy session would otherwise leak a blob per
 * screenshot for the lifetime of the document.
 */
function FileThumb({ file }: { file: File }) {
    const [url, setUrl] = useState<string | null>(null);

    useEffect(() => {
        if (!file.type.startsWith('image/')) return;
        const objectUrl = URL.createObjectURL(file);
        setUrl(objectUrl);
        return () => URL.revokeObjectURL(objectUrl);
    }, [file]);

    if (!url) {
        return (
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
                <FileIcon className="h-5 w-5 text-muted-foreground" />
            </div>
        );
    }

    return (
        // eslint-disable-next-line @next/next/no-img-element
        <img
            src={url}
            alt={file.name}
            className="h-11 w-11 shrink-0 rounded-md border border-border object-cover"
        />
    );
}

export interface SelectedFileCardProps {
    file: File;
    onRemove: () => void;
    disabled?: boolean;
    /** Optional per-file description input. Omit to render name + size only. */
    description?: string;
    onDescriptionChange?: (value: string) => void;
    descriptionPlaceholder?: string;
}

/** Uniform "file staged for upload" row. */
export function SelectedFileCard({
    file,
    onRemove,
    disabled = false,
    description,
    onDescriptionChange,
    descriptionPlaceholder = 'Add a description…',
}: SelectedFileCardProps) {
    return (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-3">
            <div className="flex items-center gap-3">
                <FileThumb file={file} />
                <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{file.name}</p>
                    <p className="text-[11px] text-muted-foreground">{formatFileSize(file.size)}</p>
                </div>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={onRemove}
                    disabled={disabled}
                    className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                >
                    <X className="h-4 w-4" />
                </Button>
            </div>

            {onDescriptionChange && (
                <Input
                    value={description ?? ''}
                    onChange={(e) => onDescriptionChange(e.target.value)}
                    placeholder={descriptionPlaceholder}
                    disabled={disabled}
                    className="h-8 text-xs"
                />
            )}
        </div>
    );
}

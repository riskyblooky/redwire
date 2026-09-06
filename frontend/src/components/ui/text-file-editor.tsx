'use client';

/**
 * TextFileEditor — in-app editing for text attachments, mirroring the
 * ImageEditor pattern (crop/annotate → replace-file). Loads the current file
 * text, edits it in the shared TipTap editor (markdown-aware), and saves the
 * result back over the same evidence object via `onSave(blob)`.
 *
 * Only offered for prose/markdown-friendly text files (see isTextEditable);
 * structured formats (json/csv/xml/code) would be mangled by the markdown
 * round-trip, so they keep the download-only path.
 */
import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Loader2, Save, X, FileText } from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import TiptapEditor from '@/components/ui/tiptap-editor';

/** Text files we hand to the markdown editor. Deliberately narrow: prose/notes,
 *  not structured formats a markdown round-trip would corrupt. */
export function isTextEditable(mimeType?: string | null, filename?: string | null): boolean {
    const editableExts = ['txt', 'text', 'md', 'markdown', 'log', 'rst'];
    const ext = (filename?.split('.').pop() || '').toLowerCase();
    if (editableExts.includes(ext)) return true;
    // text/plain and text/markdown are safe; other text/* (csv, xml, html, ...)
    // fall through to download-only unless the extension opted in above.
    const mt = (mimeType || '').toLowerCase();
    return mt === 'text/plain' || mt === 'text/markdown' || mt === 'text/x-markdown';
}

interface TextFileEditorProps {
    open: boolean;
    onClose: () => void;
    fileUrl: string;
    filename: string;
    mimeType?: string | null;
    engagementId?: string;
    onSave: (blob: Blob) => Promise<void>;
}

export default function TextFileEditor({ open, onClose, fileUrl, filename, mimeType, engagementId, onSave }: TextFileEditorProps) {
    const [content, setContent] = useState('');
    const [baseline, setBaseline] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Load the current file text whenever the dialog opens.
    useEffect(() => {
        if (!open || !fileUrl) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        fetch(fileUrl)
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.text();
            })
            .then((text) => {
                if (cancelled) return;
                setContent(text);
                setBaseline(text);
                setLoading(false);
            })
            .catch(() => {
                if (cancelled) return;
                setError('Failed to load the file for editing.');
                setLoading(false);
            });
        return () => { cancelled = true; };
    }, [open, fileUrl]);

    const isDirty = !loading && content !== baseline;

    const handleSave = async () => {
        setSaving(true);
        try {
            const blob = new Blob([content], { type: mimeType || 'text/plain' });
            await onSave(blob);
            setBaseline(content); // saved — reset the dirty baseline
        } catch (e) {
            toast.error(apiErrorMessage(e, 'Failed to save the file'));
        } finally {
            setSaving(false);
        }
    };

    const handleOpenChange = (next: boolean) => {
        if (!next && !saving) onClose();
    };

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-w-4xl w-[92vw] bg-slate-900 border-slate-800 text-white p-0 overflow-hidden gap-0">
                <DialogHeader className="px-5 py-4 border-b border-slate-800">
                    <DialogTitle className="flex items-center gap-2 text-base">
                        <FileText className="h-4 w-4 text-blue-400" />
                        <span className="truncate">Edit {filename}</span>
                    </DialogTitle>
                    <DialogDescription className="text-slate-400 text-xs">
                        Edits are saved back over this attachment. Content is treated as
                        markdown, so markdown syntax renders as formatting.
                    </DialogDescription>
                </DialogHeader>

                <div className="p-5">
                    {loading ? (
                        <div className="flex items-center justify-center h-[50vh] text-slate-500">
                            <Loader2 className="h-6 w-6 animate-spin" />
                        </div>
                    ) : error ? (
                        <div className="flex items-center justify-center h-[50vh] text-slate-400 text-sm">
                            {error}
                        </div>
                    ) : (
                        <TiptapEditor
                            value={content}
                            onChange={setContent}
                            engagementId={engagementId}
                            resizable={false}
                            minHeight="52vh"
                            lineNumbers
                            placeholder="Empty file…"
                        />
                    )}
                </div>

                <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-slate-800 bg-slate-950/40">
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={onClose}
                        disabled={saving}
                        className="text-slate-400 hover:text-white"
                    >
                        <X className="h-4 w-4 mr-2" />
                        Cancel
                    </Button>
                    <Button
                        type="button"
                        onClick={handleSave}
                        disabled={saving || loading || !!error || !isDirty}
                        className="bg-primary/90 hover:bg-primary text-white"
                    >
                        {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                        Save Changes
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

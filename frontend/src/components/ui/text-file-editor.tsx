'use client';

/**
 * TextFileEditor — inline editing for text attachments. Renders in place of the
 * file preview (no modal): the shared TipTap editor (markdown-aware) loaded with
 * the file text, plus Save/Cancel controls. Saves back over the same evidence
 * via `onSave(blob)`.
 *
 * Only offered for prose/markdown-friendly text files (see isTextEditable);
 * structured formats (json/csv/xml/code) would be mangled by the markdown
 * round-trip, so they keep the download-only path.
 */
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Loader2, Save, X } from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import TiptapEditor from '@/components/ui/tiptap-editor';

/** Text files we hand to the markdown editor. Deliberately narrow: prose/notes,
 *  not structured formats a markdown round-trip would corrupt. */
export function isTextEditable(mimeType?: string | null, filename?: string | null): boolean {
    const editableExts = ['txt', 'text', 'md', 'markdown', 'log', 'rst'];
    const ext = (filename?.split('.').pop() || '').toLowerCase();
    if (editableExts.includes(ext)) return true;
    const mt = (mimeType || '').toLowerCase();
    return mt === 'text/plain' || mt === 'text/markdown' || mt === 'text/x-markdown';
}

interface TextFileEditorProps {
    fileUrl: string;
    mimeType?: string | null;
    engagementId?: string;
    onSave: (blob: Blob) => Promise<void>;
    onCancel: () => void;
}

export default function TextFileEditor({ fileUrl, mimeType, engagementId, onSave, onCancel }: TextFileEditorProps) {
    const [content, setContent] = useState('');
    const [baseline, setBaseline] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!fileUrl) return;
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
    }, [fileUrl]);

    const isDirty = !loading && content !== baseline;

    const handleSave = async () => {
        setSaving(true);
        try {
            const blob = new Blob([content], { type: mimeType || 'text/plain' });
            await onSave(blob);
            setBaseline(content);
        } catch (e) {
            toast.error(apiErrorMessage(e, 'Failed to save the file'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="flex h-full w-full flex-col self-stretch">
            {loading ? (
                <div className="flex flex-1 items-center justify-center text-slate-500"><Loader2 className="h-6 w-6 animate-spin" /></div>
            ) : error ? (
                <div className="flex flex-1 items-center justify-center text-slate-400 text-sm">{error}</div>
            ) : (
                <div className="flex-1 overflow-auto p-3">
                    <TiptapEditor
                        value={content}
                        onChange={setContent}
                        engagementId={engagementId}
                        resizable={false}
                        minHeight="48vh"
                        lineNumbers
                        placeholder="Empty file…"
                    />
                </div>
            )}

            <div className="flex items-center justify-between gap-2 border-t border-slate-800 bg-slate-950/40 px-3 py-2">
                <span className="text-[11px] text-slate-500">Content is treated as markdown.</span>
                <div className="flex items-center gap-2">
                    <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={saving} className="text-slate-400 hover:text-white">
                        <X className="h-4 w-4 mr-2" /> Cancel
                    </Button>
                    <Button type="button" size="sm" onClick={handleSave} disabled={saving || loading || !!error || !isDirty} className="bg-primary/90 hover:bg-primary text-white">
                        {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                        Save Changes
                    </Button>
                </div>
            </div>
        </div>
    );
}

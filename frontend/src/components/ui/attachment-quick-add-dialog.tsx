'use client';

import { useState, useEffect, useCallback } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, Paperclip, UploadCloud, X, FileIcon } from 'lucide-react';
import { useUploadEvidence } from '@/lib/hooks/use-evidence';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';

interface AttachmentQuickAddDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    /** One of these must be set — determines which entity the upload links to. */
    findingId?: string;
    testcaseId?: string;
    /** Display label for the parent entity (e.g. finding title) */
    entityName?: string;
}

/**
 * Compact upload-and-link modal — used by Quick Add submenus on the
 * findings and testcases tabs to attach a file to the row's entity
 * without leaving the table.
 */
export function AttachmentQuickAddDialog({
    open,
    onOpenChange,
    findingId,
    testcaseId,
    entityName,
}: AttachmentQuickAddDialogProps) {
    const [file, setFile] = useState<File | null>(null);
    const [description, setDescription] = useState('');
    const [includeInReport, setIncludeInReport] = useState(true);
    const [dragActive, setDragActive] = useState(false);
    const upload = useUploadEvidence({ findingId, testcaseId });

    // Reset on open/close
    useEffect(() => {
        if (!open) {
            setFile(null);
            setDescription('');
            setIncludeInReport(true);
            setDragActive(false);
        }
    }, [open]);

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
        else if (e.type === 'dragleave') setDragActive(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        const f = e.dataTransfer.files?.[0];
        if (f) setFile(f);
    }, []);

    const handleSubmit = async () => {
        if (!file) return;
        try {
            await upload.mutateAsync({ file, description: description || undefined, includeInReport });
            toast.success('Attachment uploaded');
            onOpenChange(false);
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Failed to upload attachment'));
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[480px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Paperclip className="h-5 w-5 text-primary" />
                        Quick Add Attachment
                    </DialogTitle>
                    {entityName && (
                        <DialogDescription className="text-slate-400">
                            Attaching to <span className="text-white font-semibold">{entityName}</span>
                        </DialogDescription>
                    )}
                </DialogHeader>

                <div className="space-y-4 py-2">
                    {/* Drop zone */}
                    {!file ? (
                        <label
                            onDragEnter={handleDrag}
                            onDragLeave={handleDrag}
                            onDragOver={handleDrag}
                            onDrop={handleDrop}
                            className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-lg p-8 cursor-pointer transition-all ${
                                dragActive
                                    ? 'border-primary bg-primary/5'
                                    : 'border-slate-700 hover:border-slate-600 bg-slate-950/50'
                            }`}
                        >
                            <UploadCloud className={`h-8 w-8 ${dragActive ? 'text-primary' : 'text-slate-500'}`} />
                            <p className="text-sm text-slate-300">Drop a file here, or click to browse</p>
                            <p className="text-[11px] text-slate-600">Images, documents, or any artifact</p>
                            <input
                                type="file"
                                className="hidden"
                                onChange={(e) => {
                                    const f = e.target.files?.[0];
                                    if (f) setFile(f);
                                }}
                            />
                        </label>
                    ) : (
                        <div className="flex items-center gap-3 p-3 rounded-lg border border-slate-700 bg-slate-950/50">
                            <FileIcon className="h-5 w-5 text-primary shrink-0" />
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-white truncate">{file.name}</p>
                                <p className="text-[11px] text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
                            </div>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 shrink-0 text-slate-500 hover:text-red-400"
                                onClick={() => setFile(null)}
                                disabled={upload.isPending}
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        </div>
                    )}

                    {/* Description */}
                    <div className="space-y-1.5">
                        <Label className="text-xs text-slate-400">Description <span className="text-slate-600">(optional)</span></Label>
                        <Input
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="What is this artifact?"
                            className="bg-slate-950 border-slate-700 text-white"
                            disabled={upload.isPending}
                        />
                    </div>

                    {/* Include in report */}
                    <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                        <Checkbox
                            checked={includeInReport}
                            onCheckedChange={(v) => setIncludeInReport(!!v)}
                            disabled={upload.isPending}
                        />
                        Include in report
                    </label>
                </div>

                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={upload.isPending}>
                        Cancel
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        disabled={!file || upload.isPending}
                        className="bg-primary hover:bg-primary/90 text-primary-foreground"
                    >
                        {upload.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <UploadCloud className="h-4 w-4 mr-2" />}
                        Upload
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

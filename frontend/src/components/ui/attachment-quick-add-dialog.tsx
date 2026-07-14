'use client';

import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, Paperclip, UploadCloud } from 'lucide-react';
import { useUploadEvidence } from '@/lib/hooks/use-evidence';
import { FileDropzone, SelectedFileCard } from '@/components/ui/file-dropzone';
import { MAX_EVIDENCE_BYTES } from '@/lib/upload-limits';
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
    const upload = useUploadEvidence({ findingId, testcaseId });

    // Reset on open/close
    useEffect(() => {
        if (!open) {
            setFile(null);
            setDescription('');
            setIncludeInReport(true);
        }
    }, [open]);

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
                    {!file ? (
                        <FileDropzone
                            onFiles={(files) => setFile(files[0])}
                            maxSizeBytes={MAX_EVIDENCE_BYTES}
                            disabled={upload.isPending}
                            compact
                            hint="Images, documents, or any artifact"
                        />
                    ) : (
                        <SelectedFileCard
                            file={file}
                            onRemove={() => setFile(null)}
                            disabled={upload.isPending}
                        />
                    )}

                    {/* Description */}
                    <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">
                            Description <span className="text-muted-foreground/60">(optional)</span>
                        </Label>
                        <Input
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="What is this artifact?"
                            disabled={upload.isPending}
                        />
                    </div>

                    {/* Include in report */}
                    <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
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

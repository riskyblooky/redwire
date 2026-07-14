'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, UploadCloud } from 'lucide-react';
import { useUploadEvidence } from '@/lib/hooks/use-evidence';
import { FileDropzone, SelectedFileCard } from '@/components/ui/file-dropzone';
import { MAX_EVIDENCE_BYTES } from '@/lib/upload-limits';
import { toast } from 'sonner';

interface EvidenceUploadProps {
    findingId?: string;
    testcaseId?: string;
}

interface StagedFile {
    file: File;
    description: string;
}

export function EvidenceUpload({ findingId, testcaseId }: EvidenceUploadProps) {
    const [staged, setStaged] = useState<StagedFile[]>([]);
    const [includeInReport, setIncludeInReport] = useState(true);
    const uploadMutation = useUploadEvidence({ findingId, testcaseId });

    const addFiles = (files: File[]) => {
        setStaged((prev) => [...prev, ...files.map((file) => ({ file, description: '' }))]);
    };

    const removeFile = (index: number) => {
        setStaged((prev) => prev.filter((_, i) => i !== index));
    };

    const updateDescription = (index: number, description: string) => {
        setStaged((prev) => prev.map((item, i) => (i === index ? { ...item, description } : item)));
    };

    const handleUpload = async () => {
        const failed: string[] = [];
        let successCount = 0;

        for (const item of staged) {
            try {
                await uploadMutation.mutateAsync({
                    file: item.file,
                    description: item.description || undefined,
                    includeInReport,
                });
                successCount++;
            } catch {
                failed.push(item.file.name);
            }
        }

        if (successCount > 0) {
            toast.success(`Uploaded ${successCount} file${successCount > 1 ? 's' : ''}`);
        }
        if (failed.length > 0) {
            toast.error(`Failed to upload ${failed.join(', ')}`);
        }

        // Keep whatever failed staged so the user can retry without re-picking.
        setStaged((prev) => prev.filter((item) => failed.includes(item.file.name)));
    };

    return (
        <div className="space-y-4">
            <FileDropzone
                onFiles={addFiles}
                multiple
                maxSizeBytes={MAX_EVIDENCE_BYTES}
                disabled={uploadMutation.isPending}
                hint="Screenshots, PDFs, logs, or payload files"
            />

            {staged.length > 0 && (
                <div className="space-y-3">
                    {staged.map((item, index) => (
                        <SelectedFileCard
                            key={`${item.file.name}-${index}`}
                            file={item.file}
                            onRemove={() => removeFile(index)}
                            disabled={uploadMutation.isPending}
                            description={item.description}
                            onDescriptionChange={(value) => updateDescription(index, value)}
                            descriptionPlaceholder="What does this evidence show?"
                        />
                    ))}

                    <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
                        <Checkbox
                            checked={includeInReport}
                            onCheckedChange={(v) => setIncludeInReport(!!v)}
                            disabled={uploadMutation.isPending}
                        />
                        Include in report
                    </label>

                    <Button
                        onClick={handleUpload}
                        disabled={uploadMutation.isPending}
                        className="w-full"
                    >
                        {uploadMutation.isPending ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Uploading…
                            </>
                        ) : (
                            <>
                                <UploadCloud className="mr-2 h-4 w-4" />
                                Upload {staged.length} file{staged.length > 1 ? 's' : ''}
                            </>
                        )}
                    </Button>
                </div>
            )}
        </div>
    );
}

'use client';

import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { UploadCloud, X, FileIcon, Loader2 } from 'lucide-react';
import { useUploadEvidence } from '@/lib/hooks/use-evidence';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';

interface EvidenceUploadProps {
    findingId?: string;
    testcaseId?: string;
}

interface SelectedFile {
    file: File;
    description: string;
}

export function EvidenceUpload({ findingId, testcaseId }: EvidenceUploadProps) {
    const [dragActive, setDragActive] = useState(false);
    const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([]);
    const uploadMutation = useUploadEvidence({ findingId, testcaseId });

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            const files = Array.from(e.dataTransfer.files).map(f => ({ file: f, description: '' }));
            setSelectedFiles(prev => [...prev, ...files]);
        }
    }, []);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        e.preventDefault();
        if (e.target.files && e.target.files[0]) {
            const files = Array.from(e.target.files).map(f => ({ file: f, description: '' }));
            setSelectedFiles(prev => [...prev, ...files]);
        }
    };

    const removeFile = (index: number) => {
        setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    };

    const updateDescription = (index: number, description: string) => {
        setSelectedFiles(prev => {
            const next = [...prev];
            next[index].description = description;
            return next;
        });
    };

    const handleUpload = async () => {
        let successCount = 0;
        for (const item of selectedFiles) {
            try {
                await uploadMutation.mutateAsync({
                    file: item.file,
                    description: item.description
                });
                successCount++;
            } catch (error) {
                toast.error(`Failed to upload ${item.file.name}`);
            }
        }

        if (successCount > 0) {
            toast.success(`Successfully uploaded ${successCount} file${successCount > 1 ? 's' : ''}`);
        }
        setSelectedFiles([]);
    };

    return (
        <div className="space-y-4">
            <div
                className={`relative border-2 border-dashed rounded-xl p-6 transition-all text-center ${dragActive ? 'border-primary bg-primary/10' : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
                    }`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
            >
                <input
                    type="file"
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    multiple
                    onChange={handleChange}
                />

                <div className="flex flex-col items-center gap-2">
                    <div className="p-3 rounded-full bg-slate-800 text-slate-400">
                        <UploadCloud className="h-6 w-6" />
                    </div>
                    <div>
                        <p className="text-sm font-medium text-white">
                            Click to upload or drag and drop
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                            Images, PDFs, logs, or payload files
                        </p>
                    </div>
                </div>
            </div>

            {selectedFiles.length > 0 && (
                <div className="space-y-3">
                    {selectedFiles.map((item, index) => (
                        <Card key={index} className="p-4 border-slate-800 bg-slate-900/60 flex flex-col gap-3">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <FileIcon className="h-4 w-4 text-primary" />
                                    <div className="text-sm min-w-0">
                                        <p className="text-white font-medium truncate max-w-[200px]">{item.file.name}</p>
                                        <p className="text-slate-500 text-[10px]">{(item.file.size / 1024).toFixed(1)} KB</p>
                                    </div>
                                </div>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => removeFile(index)}
                                    className="h-8 w-8 text-slate-500 hover:text-white"
                                >
                                    <X className="h-4 w-4" />
                                </Button>
                            </div>
                            <Input
                                placeholder="Add description..."
                                value={item.description}
                                onChange={(e) => updateDescription(index, e.target.value)}
                                className="h-8 text-xs bg-slate-950 border-slate-800 text-slate-300 placeholder:text-slate-600"
                            />
                        </Card>
                    ))}

                    <Button
                        onClick={handleUpload}
                        disabled={uploadMutation.isPending}
                        className="w-full bg-primary hover:bg-primary/90 text-white font-medium shadow-lg shadow-primary/20"
                    >
                        {uploadMutation.isPending ? (
                            <>
                                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                Uploading...
                            </>
                        ) : (
                            `Upload ${selectedFiles.length} File${selectedFiles.length > 1 ? 's' : ''}`
                        )}
                    </Button>
                </div>
            )}
        </div>
    );
}

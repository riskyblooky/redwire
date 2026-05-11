'use client';

import React, { useState, useCallback, useRef } from 'react';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Upload,
    FileSpreadsheet,
    FileText,
    Code2,
    Download,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Loader2,
    X,
    Network,
} from 'lucide-react';
import { useImportAssets, ImportResult } from '@/lib/hooks/use-assets';
import { toast } from 'sonner';

interface AssetImportDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    engagementId: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type DetectedFormat = 'csv' | 'xlsx' | 'nmap' | null;

function detectFormat(filename: string): DetectedFormat {
    const lower = filename.toLowerCase();
    if (lower.endsWith('.csv')) return 'csv';
    if (lower.endsWith('.xlsx') || lower.endsWith('.xls')) return 'xlsx';
    if (lower.endsWith('.xml')) return 'nmap';
    return null;
}

const formatInfo: Record<string, { label: string; icon: React.ReactNode; color: string; desc: string }> = {
    csv: {
        label: 'CSV',
        icon: <FileText className="h-5 w-5" />,
        color: 'bg-green-500/10 text-green-400 border-green-500/20',
        desc: 'Comma-separated values with asset data columns',
    },
    xlsx: {
        label: 'Excel',
        icon: <FileSpreadsheet className="h-5 w-5" />,
        color: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
        desc: 'Excel spreadsheet with asset data columns',
    },
    nmap: {
        label: 'NMAP XML',
        icon: <Network className="h-5 w-5" />,
        color: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
        desc: 'NMAP scan output with hosts and ports',
    },
};

export function AssetImportDialog({ open, onOpenChange, engagementId }: AssetImportDialogProps) {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [format, setFormat] = useState<DetectedFormat>(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const [result, setResult] = useState<ImportResult | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const importAssets = useImportAssets();

    const handleReset = useCallback(() => {
        setSelectedFile(null);
        setFormat(null);
        setResult(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
    }, []);

    const handleClose = useCallback(() => {
        handleReset();
        onOpenChange(false);
    }, [handleReset, onOpenChange]);

    const handleFileSelect = useCallback((file: File) => {
        const detected = detectFormat(file.name);
        if (!detected) {
            toast.error('Unsupported file format. Use .csv, .xlsx, or .xml (NMAP).');
            return;
        }
        setSelectedFile(file);
        setFormat(detected);
        setResult(null);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFileSelect(file);
    }, [handleFileSelect]);

    const handleImport = async () => {
        if (!selectedFile) return;
        try {
            const importResult = await importAssets.mutateAsync({
                file: selectedFile,
                engagementId,
            });
            setResult(importResult);
            if (importResult.created > 0) {
                toast.success(`Imported ${importResult.created} asset${importResult.created !== 1 ? 's' : ''}`);
            }
        } catch (error: any) {
            toast.error(error?.response?.data?.detail || 'Failed to import assets');
        }
    };

    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-lg bg-slate-900 border-slate-800 text-white">
                <DialogHeader>
                    <DialogTitle className="text-white flex items-center gap-2">
                        <Upload className="h-5 w-5 text-primary" />
                        Import Assets
                    </DialogTitle>
                    <DialogDescription className="text-slate-400">
                        Upload a CSV, Excel, or NMAP XML file to bulk import assets.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-5 pt-2">
                    {/* Template Downloads */}
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500 uppercase tracking-wider">Download Template:</span>
                        <a
                            href={`${API_URL}/assets/templates/csv`}
                            className="inline-flex items-center gap-1.5 text-xs text-green-400 hover:text-green-300 transition-colors"
                        >
                            <Download className="h-3 w-3" />
                            CSV
                        </a>
                        <span className="text-slate-700">·</span>
                        <a
                            href={`${API_URL}/assets/templates/xlsx`}
                            className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                        >
                            <Download className="h-3 w-3" />
                            Excel
                        </a>
                    </div>

                    {/* Drop Zone */}
                    {!result && (
                        <div
                            className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer
                                ${isDragOver ? 'border-primary bg-primary/10' : 'border-slate-700 hover:border-slate-600 bg-slate-950/50'}
                            `}
                            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                            onDragLeave={() => setIsDragOver(false)}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".csv,.xlsx,.xls,.xml"
                                className="hidden"
                                onChange={(e) => {
                                    const file = e.target.files?.[0];
                                    if (file) handleFileSelect(file);
                                }}
                            />
                            {selectedFile ? (
                                <div className="space-y-3">
                                    <div className="flex items-center justify-center gap-3">
                                        {format && formatInfo[format] && (
                                            <Badge variant="outline" className={`${formatInfo[format].color} text-xs px-2 py-0.5`}>
                                                {formatInfo[format].icon}
                                                <span className="ml-1.5">{formatInfo[format].label}</span>
                                            </Badge>
                                        )}
                                    </div>
                                    <p className="text-sm text-white font-medium truncate max-w-[300px] mx-auto">
                                        {selectedFile.name}
                                    </p>
                                    <p className="text-xs text-slate-500">
                                        {(selectedFile.size / 1024).toFixed(1)} KB
                                    </p>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-slate-400 hover:text-white"
                                        onClick={(e) => { e.stopPropagation(); handleReset(); }}
                                    >
                                        <X className="h-3 w-3 mr-1" /> Change file
                                    </Button>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    <Upload className="h-10 w-10 mx-auto text-slate-600" />
                                    <div>
                                        <p className="text-sm text-slate-300">
                                            Drop a file here or <span className="text-primary">browse</span>
                                        </p>
                                        <p className="text-xs text-slate-500 mt-1">
                                            Supports CSV, XLSX, and NMAP XML
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Format Info */}
                    {format && !result && formatInfo[format] && (
                        <div className={`flex items-start gap-3 p-3 rounded-lg border ${formatInfo[format].color}`}>
                            {formatInfo[format].icon}
                            <div>
                                <p className="text-sm font-medium">{formatInfo[format].label} Format Detected</p>
                                <p className="text-xs opacity-70 mt-0.5">{formatInfo[format].desc}</p>
                            </div>
                        </div>
                    )}

                    {/* Import Results */}
                    {result && (
                        <div className="space-y-3 p-4 rounded-xl bg-slate-950/60 border border-slate-800">
                            <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                                <CheckCircle2 className="h-4 w-4 text-green-400" />
                                Import Complete
                            </h4>
                            <div className="grid grid-cols-3 gap-3">
                                <div className="text-center p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                                    <p className="text-2xl font-bold text-green-400">{result.created}</p>
                                    <p className="text-[10px] uppercase tracking-wider text-green-400/70">Created</p>
                                </div>
                                <div className="text-center p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                                    <p className="text-2xl font-bold text-yellow-400">{result.skipped}</p>
                                    <p className="text-[10px] uppercase tracking-wider text-yellow-400/70">Skipped</p>
                                </div>
                                <div className="text-center p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                                    <p className="text-2xl font-bold text-blue-400">{result.ports_added}</p>
                                    <p className="text-[10px] uppercase tracking-wider text-blue-400/70">Ports</p>
                                </div>
                            </div>
                            {result.errors.length > 0 && (
                                <div className="mt-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                                    <p className="text-xs font-semibold text-red-400 flex items-center gap-1 mb-1">
                                        <AlertTriangle className="h-3 w-3" />
                                        {result.errors.length} error{result.errors.length !== 1 ? 's' : ''}
                                    </p>
                                    <ul className="text-xs text-red-400/80 space-y-0.5 max-h-24 overflow-y-auto">
                                        {result.errors.map((err, i) => (
                                            <li key={i}>• {err}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Actions */}
                    <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                        {result ? (
                            <Button onClick={handleClose} className="bg-primary hover:bg-primary/90">
                                Done
                            </Button>
                        ) : (
                            <>
                                <Button variant="ghost" onClick={handleClose} className="text-slate-400 hover:text-white">
                                    Cancel
                                </Button>
                                <Button
                                    onClick={handleImport}
                                    disabled={!selectedFile || importAssets.isPending}
                                    className="bg-primary hover:bg-primary/90 disabled:opacity-50"
                                >
                                    {importAssets.isPending ? (
                                        <>
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            Importing...
                                        </>
                                    ) : (
                                        <>
                                            <Upload className="h-4 w-4 mr-2" />
                                            Import
                                        </>
                                    )}
                                </Button>
                            </>
                        )}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}

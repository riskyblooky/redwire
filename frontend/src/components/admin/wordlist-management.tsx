'use client';

import { useState, useRef } from 'react';
import {
    useWordlistStatus,
    useUploadWordlist,
    useDeleteWordlist,
} from '@/lib/hooks/use-wordlist';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Upload,
    Trash2,
    Database,
    Loader2,
    CheckCircle2,
    XCircle,
    Clock,
    FileText,
    Zap,
    Shield,
    Info,
} from 'lucide-react';
import { toast } from 'sonner';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';

export function WordlistManagement() {
    const { data: status, isLoading } = useWordlistStatus();
    const uploadWordlist = useUploadWordlist();
    const deleteWordlist = useDeleteWordlist();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const handleUpload = async (file: File) => {
        try {
            await uploadWordlist.mutateAsync(file);
            toast.success(`Uploading "${file.name}" — processing in background`);
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to upload wordlist'));
        }
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            handleUpload(file);
            e.target.value = '';
        }
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) handleUpload(file);
    };

    const handleDelete = async (id: string, filename: string) => {
        const confirmed = await confirm({
            title: 'Delete Wordlist',
            description: `Are you sure you want to delete "${filename}" and all its entries? The Bloom filter will be rebuilt.`,
            variant: 'destructive',
            confirmLabel: 'Delete',
        });
        if (!confirmed) return;

        try {
            await deleteWordlist.mutateAsync(id);
            toast.success('Wordlist deleted');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to delete wordlist'));
        }
    };

    const statusBadge = (s: string) => {
        switch (s) {
            case 'READY':
                return (
                    <Badge className="bg-green-500/10 text-green-400 border-green-500/20 gap-1 text-[10px]">
                        <CheckCircle2 className="h-3 w-3" />
                        READY
                    </Badge>
                );
            case 'PROCESSING':
                return (
                    <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20 gap-1 text-[10px]">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        PROCESSING
                    </Badge>
                );
            case 'FAILED':
                return (
                    <Badge className="bg-red-500/10 text-red-400 border-red-500/20 gap-1 text-[10px]">
                        <XCircle className="h-3 w-3" />
                        FAILED
                    </Badge>
                );
            default:
                return <Badge variant="outline" className="text-[10px]">{s}</Badge>;
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center p-12">
                <Loader2 className="h-6 w-6 text-indigo-400 animate-spin" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Info Banner */}
            <div className="rounded-xl border border-indigo-500/20 bg-gradient-to-r from-indigo-500/5 via-purple-500/5 to-indigo-500/5 p-4">
                <div className="flex gap-3">
                    <Shield className="h-5 w-5 text-indigo-400 shrink-0 mt-0.5" />
                    <div className="space-y-2">
                        <h3 className="text-sm font-semibold text-white">Password Strength &amp; Hash Cracking</h3>
                        <p className="text-xs text-slate-400 leading-relaxed">
                            Upload plaintext wordlists to build a rainbow table for identifying weak passwords.
                            Each password is hashed into <span className="text-indigo-400 font-medium">NTLM</span>,{' '}
                            <span className="text-indigo-400 font-medium">MD5</span>, and{' '}
                            <span className="text-indigo-400 font-medium">SHA-1</span> formats and indexed with a
                            Bloom filter for instant lookups. Vault credentials can then be checked against the
                            wordlist, and unsalted hashes can be reverse-cracked to reveal the plaintext.
                        </p>
                        <div className="flex items-center gap-1.5 pt-1">
                            <Info className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
                            <p className="text-xs text-amber-400/80">
                                Recommended: start with{' '}
                                <span className="font-semibold text-amber-400">rockyou.txt</span>{' '}
                                (~14M passwords, ~133MB file). Expect ~30 min processing time and ~5.4 GB database storage
                                (2.2 GB data + 3.2 GB indexes for NTLM, MD5, SHA-1 columns).
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Bloom Filter Status */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium text-slate-300">Bloom Filter</CardTitle>
                        <Zap className="h-4 w-4 text-amber-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-2">
                            {status?.bloom_loaded ? (
                                <Badge className="bg-green-500/10 text-green-400 border-green-500/20 text-[10px]">ACTIVE</Badge>
                            ) : status?.bloom_loading ? (
                                <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20 gap-1 text-[10px]">
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                    LOADING
                                </Badge>
                            ) : (
                                <Badge className="bg-slate-500/10 text-slate-400 border-slate-500/20 text-[10px]">NOT LOADED</Badge>
                            )}
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium text-slate-300">Passwords Indexed</CardTitle>
                        <Database className="h-4 w-4 text-indigo-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-white">
                            {(status?.bloom_count || 0).toLocaleString()}
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium text-slate-300">Wordlists</CardTitle>
                        <FileText className="h-4 w-4 text-cyan-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-white">
                            {status?.wordlists?.length || 0}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Upload Area */}
            <Card className="border-slate-800 bg-slate-900/50">
                <CardHeader>
                    <CardTitle className="text-white flex items-center gap-2">
                        <Upload className="h-5 w-5 text-indigo-400" />
                        Upload Wordlist
                    </CardTitle>
                    <CardDescription>
                        Upload a plaintext wordlist file (e.g. rockyou.txt). One password per line. Hashes (NTLM, MD5, SHA-1) will be computed automatically.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div
                        className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${isDragOver
                            ? 'border-indigo-500 bg-indigo-500/5'
                            : 'border-slate-700 hover:border-slate-600'
                            }`}
                        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                        onDragLeave={() => setIsDragOver(false)}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <Upload className="h-8 w-8 text-slate-500 mx-auto mb-3" />
                        <p className="text-sm text-slate-400 mb-1">
                            Drag & drop a wordlist file here, or click to browse
                        </p>
                        <p className="text-xs text-slate-600">
                            Supports .txt files • Processing happens in the background
                        </p>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".txt,.lst,.dict"
                            className="hidden"
                            onChange={handleFileSelect}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Wordlist Table */}
            {status?.wordlists && status.wordlists.length > 0 && (
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardHeader>
                        <CardTitle className="text-white">Uploaded Wordlists</CardTitle>
                        <CardDescription>
                            Manage your imported wordlists and their processing status.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow className="border-slate-800 hover:bg-slate-900/50">
                                    <TableHead className="text-slate-400">Filename</TableHead>
                                    <TableHead className="text-slate-400">Entries</TableHead>
                                    <TableHead className="text-slate-400">Status</TableHead>
                                    <TableHead className="text-slate-400">Uploaded</TableHead>
                                    <TableHead className="text-slate-400 text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {status.wordlists.map((wl) => (
                                    <TableRow key={wl.id} className="border-slate-800 hover:bg-slate-800/50">
                                        <TableCell>
                                            <div className="flex items-center gap-2">
                                                <FileText className="h-4 w-4 text-slate-500" />
                                                <span className="text-white font-medium text-sm">{wl.filename}</span>
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-white font-mono text-sm">
                                                {wl.entry_count.toLocaleString()}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            {statusBadge(wl.status)}
                                            {wl.error_message && (
                                                <p className="text-xs text-red-400 mt-1 max-w-[200px] truncate" title={wl.error_message}>
                                                    {wl.error_message}
                                                </p>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-slate-400 text-sm">
                                                {new Date(wl.created_at).toLocaleDateString()}
                                            </span>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8 hover:bg-slate-800 text-red-400 hover:text-red-300"
                                                onClick={() => handleDelete(wl.id, wl.filename)}
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            )}

            <ConfirmDialog />
        </div>
    );
}

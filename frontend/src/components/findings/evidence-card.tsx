'use client';

import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogTitle,
} from '@/components/ui/dialog';
import { FileIcon, ExternalLink, Download, ImageIcon, FileText, FileCode, CheckCircle2, XCircle, Eye, X, ZoomIn, ZoomOut, RotateCw } from 'lucide-react';
import { getEvidenceUrl } from '@/lib/hooks/use-evidence';
import { Evidence } from '@/lib/types';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { cn } from '@/lib/utils';
import { useRouter, useSearchParams } from 'next/navigation';

interface EvidenceCardProps {
    evidence: Evidence;
    findingId: string;
}

export function EvidenceCard({ evidence, findingId }: EvidenceCardProps) {
    const router = useRouter();
    const isImage = evidence.mime_type?.startsWith('image/');
    const [showPreview, setShowPreview] = useState(false);
    const [zoom, setZoom] = useState(1);
    const [rotation, setRotation] = useState(0);

    const getImageUrl = () => {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
        return `${apiUrl}/evidence/${evidence.id}/download?token=${localStorage.getItem('access_token')}`;
    };

    const handleDownload = (e: React.MouseEvent) => {
        e.stopPropagation();
        window.open(getImageUrl(), '_blank');
    };

    const searchParams = useSearchParams();

    const navigateToDetail = (e?: React.MouseEvent) => {
        e?.stopPropagation();
        const params = new URLSearchParams();
        params.set('source', 'finding');
        const returnEngagementId = searchParams.get('engagementId');
        const returnTab = searchParams.get('tab');
        if (returnEngagementId) params.set('returnEngagementId', returnEngagementId);
        if (returnTab) params.set('returnTab', returnTab);
        router.push(`/engagements/${evidence.engagement_id || 'global'}/evidence/${evidence.id}?${params.toString()}`);
    };

    const handleCardClick = () => {
        if (isImage) {
            setZoom(1);
            setRotation(0);
            setShowPreview(true);
        } else {
            navigateToDetail();
        }
    };

    const getIcon = () => {
        if (isImage) return <ImageIcon className="h-4 w-4 text-pink-400" />;
        if (evidence.mime_type?.includes('text') || evidence.mime_type?.includes('json')) return <FileText className="h-4 w-4 text-blue-400" />;
        if (evidence.mime_type?.includes('zip') || evidence.mime_type?.includes('tar')) return <FileCode className="h-4 w-4 text-amber-400" />;
        return <FileIcon className="h-4 w-4 text-slate-400" />;
    };

    return (
        <>
            <Card
                className="flex items-center justify-between p-3 border-slate-800 bg-slate-900/40 hover:bg-slate-800/60 transition-all group cursor-pointer"
                onClick={handleCardClick}
            >
                <div className="flex items-center gap-3 overflow-hidden">
                    <div className="p-2 rounded-lg bg-slate-800/50 group-hover:bg-slate-700/50 transition-colors">
                        {getIcon()}
                    </div>
                    <div className="text-sm min-w-0">
                        <p className="text-white font-medium truncate">{evidence.original_filename}</p>
                        <div className="flex items-center gap-2 text-[10px] text-slate-500">
                            <span>{(evidence.file_size / 1024).toFixed(1)} KB</span>
                            <span>•</span>
                            <span>{formatDistanceToNow(parseUTCDate(evidence.created_at), { addSuffix: true })}</span>
                            {evidence.include_in_report && (
                                <Badge variant="outline" className="text-[8px] h-4 leading-none inline-flex items-center bg-green-500/10 text-green-500 border-none px-1">
                                    REPORT
                                </Badge>
                            )}
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {isImage && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-slate-400 hover:text-pink-400"
                            title="Preview Image"
                            onClick={(e) => {
                                e.stopPropagation();
                                setZoom(1);
                                setRotation(0);
                                setShowPreview(true);
                            }}
                        >
                            <ZoomIn className="h-4 w-4" />
                        </Button>
                    )}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-slate-400 hover:text-white"
                        title="View Details"
                        onClick={(e) => {
                            e.stopPropagation();
                            navigateToDetail();
                        }}
                    >
                        <Eye className="h-4 w-4" />
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleDownload}
                        title="Download Original"
                        className="h-8 w-8 text-slate-400 hover:text-white"
                    >
                        <Download className="h-4 w-4" />
                    </Button>
                </div>
            </Card>

            {/* Image Preview Modal */}
            {isImage && (
                <Dialog open={showPreview} onOpenChange={setShowPreview}>
                    <DialogContent className="max-w-[90vw] max-h-[90vh] p-0 bg-slate-950/95 border-slate-800 overflow-hidden flex flex-col [&>button:last-child]:hidden">
                        <DialogTitle className="sr-only">{evidence.original_filename}</DialogTitle>
                        {/* Header */}
                        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/60 shrink-0 gap-4">
                            <div className="flex items-center gap-3 min-w-0 flex-1">
                                <ImageIcon className="h-4 w-4 text-pink-400 shrink-0" />
                                <div className="min-w-0">
                                    <p className="text-sm font-medium text-white truncate">{evidence.original_filename}</p>
                                    <p className="text-[10px] text-slate-500">{(evidence.file_size / 1024).toFixed(1)} KB • {evidence.mime_type}</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-0.5 shrink-0">
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-slate-400 hover:text-white"
                                    title="Zoom Out"
                                    onClick={() => setZoom(z => Math.max(0.25, z - 0.25))}
                                >
                                    <ZoomOut className="h-3.5 w-3.5" />
                                </Button>
                                <span className="text-[10px] text-slate-500 w-9 text-center font-mono tabular-nums">{Math.round(zoom * 100)}%</span>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-slate-400 hover:text-white"
                                    title="Zoom In"
                                    onClick={() => setZoom(z => Math.min(5, z + 0.25))}
                                >
                                    <ZoomIn className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-slate-400 hover:text-white"
                                    title="Rotate"
                                    onClick={() => setRotation(r => (r + 90) % 360)}
                                >
                                    <RotateCw className="h-3.5 w-3.5" />
                                </Button>
                                <div className="w-px h-5 bg-slate-800 mx-1" />
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-slate-400 hover:text-white"
                                    title="Download"
                                    onClick={handleDownload}
                                >
                                    <Download className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-slate-400 hover:text-white"
                                    title="View Full Details"
                                    onClick={(e) => { setShowPreview(false); navigateToDetail(e); }}
                                >
                                    <ExternalLink className="h-3.5 w-3.5" />
                                </Button>
                                <div className="w-px h-5 bg-slate-800 mx-1" />
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-slate-400 hover:text-white"
                                    title="Close"
                                    onClick={() => setShowPreview(false)}
                                >
                                    <X className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                        {/* Image */}
                        <div className="flex-1 overflow-auto flex items-center justify-center p-4 min-h-0">
                            <img
                                src={getImageUrl()}
                                alt={evidence.original_filename}
                                className="max-w-full max-h-full object-contain transition-transform duration-200"
                                style={{
                                    transform: `scale(${zoom}) rotate(${rotation}deg)`,
                                    transformOrigin: 'center center',
                                }}
                                draggable={false}
                            />
                        </div>
                    </DialogContent>
                </Dialog>
            )}
        </>
    );
}

// Add Badge import if not available, or use the class names manually
function Badge({ children, variant, className }: { children: React.ReactNode, variant?: string, className?: string }) {
    return <span className={cn("px-1.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider", className)}>{children}</span>;
}

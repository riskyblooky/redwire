'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import {
    Dialog,
    DialogContent,
} from '@/components/ui/dialog';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    Square,
    RectangleHorizontal,
    Pencil,
    Undo2,
    Redo2,
    Save,
    X,
    Loader2,
    Type,
    Eraser,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ─── Types ───────────────────────────────────────────────────────
type Tool = 'rect' | 'filled-rect' | 'pen' | 'text' | 'eraser';

interface Point {
    x: number;
    y: number;
}

interface Annotation {
    type: Tool;
    color: string;
    strokeWidth: number;
    // Rect annotations
    startX?: number;
    startY?: number;
    width?: number;
    height?: number;
    // Pen annotations
    points?: Point[];
    // Text annotations
    text?: string;
    x?: number;
    y?: number;
    fontSize?: number;
}

interface ImageEditorProps {
    open: boolean;
    onClose: () => void;
    imageUrl: string;
    onSave: (blob: Blob) => Promise<void>;
    filename?: string;
}

// ─── Constants ───────────────────────────────────────────────────
const COLORS = [
    { value: '#ef4444', label: 'Red' },
    { value: '#000000', label: 'Black' },
    { value: '#eab308', label: 'Yellow' },
    { value: '#ffffff', label: 'White' },
    { value: '#22c55e', label: 'Green' },
    { value: '#3b82f6', label: 'Blue' },
];

const TOOLS: { id: Tool; icon: typeof Square; label: string }[] = [
    { id: 'rect', icon: Square, label: 'Rectangle (outline)' },
    { id: 'filled-rect', icon: RectangleHorizontal, label: 'Redact (filled)' },
    { id: 'pen', icon: Pencil, label: 'Freehand Pen' },
    { id: 'text', icon: Type, label: 'Text' },
    { id: 'eraser', icon: Eraser, label: 'Eraser (undo last)' },
];

// ═════════════════════════════════════════════════════════════════
// ImageEditor Component
// ═════════════════════════════════════════════════════════════════
export default function ImageEditor({ open, onClose, imageUrl, onSave, filename }: ImageEditorProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const baseImageRef = useRef<HTMLImageElement | null>(null);

    const [tool, setTool] = useState<Tool>('rect');
    const [color, setColor] = useState('#ef4444');
    const [strokeWidth, setStrokeWidth] = useState(3);
    const [annotations, setAnnotations] = useState<Annotation[]>([]);
    const [redoStack, setRedoStack] = useState<Annotation[]>([]);
    const [isDrawing, setIsDrawing] = useState(false);
    const [currentAnnotation, setCurrentAnnotation] = useState<Annotation | null>(null);
    const [isSaving, setIsSaving] = useState(false);
    const [imageLoaded, setImageLoaded] = useState(false);
    const [scale, setScale] = useState(1);
    const [offset, setOffset] = useState<Point>({ x: 0, y: 0 });
    const [textInput, setTextInput] = useState('');
    const [textPosition, setTextPosition] = useState<Point | null>(null);

    // Load image when URL changes
    useEffect(() => {
        if (!open || !imageUrl) return;
        setImageLoaded(false);
        setAnnotations([]);
        setRedoStack([]);

        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
            baseImageRef.current = img;
            setImageLoaded(true);
        };
        img.onerror = () => {
            console.error('Failed to load image for editor');
        };
        img.src = imageUrl;
    }, [open, imageUrl]);

    // Fit image to container and render when loaded
    useEffect(() => {
        if (!imageLoaded || !baseImageRef.current || !canvasRef.current || !containerRef.current) return;

        const img = baseImageRef.current;
        const container = containerRef.current;
        const canvas = canvasRef.current;

        const containerRect = container.getBoundingClientRect();
        const maxW = containerRect.width;
        const maxH = containerRect.height;

        const scaleX = maxW / img.naturalWidth;
        const scaleY = maxH / img.naturalHeight;
        const fitScale = Math.min(scaleX, scaleY, 1);

        const displayW = img.naturalWidth * fitScale;
        const displayH = img.naturalHeight * fitScale;

        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        canvas.style.width = `${displayW}px`;
        canvas.style.height = `${displayH}px`;

        setScale(fitScale);
        setOffset({
            x: (maxW - displayW) / 2,
            y: (maxH - displayH) / 2,
        });

        renderCanvas();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [imageLoaded]);

    // Re-render on annotation changes
    useEffect(() => {
        if (imageLoaded) renderCanvas();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [annotations, currentAnnotation, imageLoaded]);

    // ─── Canvas rendering ────────────────────────────────────────
    const renderCanvas = useCallback(() => {
        const canvas = canvasRef.current;
        const img = baseImageRef.current;
        if (!canvas || !img) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // Clear and draw base image
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight);

        // Draw all saved annotations
        const allAnnotations = currentAnnotation ? [...annotations, currentAnnotation] : annotations;

        for (const ann of allAnnotations) {
            ctx.strokeStyle = ann.color;
            ctx.fillStyle = ann.color;
            ctx.lineWidth = ann.strokeWidth;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';

            if (ann.type === 'rect' && ann.startX !== undefined && ann.width !== undefined) {
                ctx.strokeRect(ann.startX, ann.startY!, ann.width, ann.height!);
            } else if (ann.type === 'filled-rect' && ann.startX !== undefined && ann.width !== undefined) {
                ctx.fillRect(ann.startX, ann.startY!, ann.width, ann.height!);
            } else if (ann.type === 'pen' && ann.points && ann.points.length > 1) {
                ctx.beginPath();
                ctx.moveTo(ann.points[0].x, ann.points[0].y);
                for (let i = 1; i < ann.points.length; i++) {
                    ctx.lineTo(ann.points[i].x, ann.points[i].y);
                }
                ctx.stroke();
            } else if (ann.type === 'text' && ann.text && ann.x !== undefined) {
                ctx.font = `${ann.fontSize || 24}px Inter, sans-serif`;
                ctx.fillText(ann.text, ann.x, ann.y!);
            }
        }
    }, [annotations, currentAnnotation]);

    // ─── Coordinate mapping ──────────────────────────────────────
    const getCanvasCoords = useCallback((e: React.MouseEvent<HTMLCanvasElement>): Point => {
        const canvas = canvasRef.current!;
        const rect = canvas.getBoundingClientRect();
        return {
            x: (e.clientX - rect.left) * (canvas.width / rect.width),
            y: (e.clientY - rect.top) * (canvas.height / rect.height),
        };
    }, []);

    // ─── Mouse handlers ──────────────────────────────────────────
    const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        if (tool === 'eraser') {
            // Eraser = undo last
            setAnnotations(prev => {
                if (prev.length === 0) return prev;
                const last = prev[prev.length - 1];
                setRedoStack(redo => [...redo, last]);
                return prev.slice(0, -1);
            });
            return;
        }

        if (tool === 'text') {
            const coords = getCanvasCoords(e);
            setTextPosition(coords);
            setTextInput('');
            return;
        }

        const coords = getCanvasCoords(e);
        setIsDrawing(true);
        setRedoStack([]);

        if (tool === 'rect' || tool === 'filled-rect') {
            setCurrentAnnotation({
                type: tool,
                color,
                strokeWidth,
                startX: coords.x,
                startY: coords.y,
                width: 0,
                height: 0,
            });
        } else if (tool === 'pen') {
            setCurrentAnnotation({
                type: 'pen',
                color,
                strokeWidth,
                points: [coords],
            });
        }
    }, [tool, color, strokeWidth, getCanvasCoords]);

    const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        if (!isDrawing || !currentAnnotation) return;

        const coords = getCanvasCoords(e);

        if (currentAnnotation.type === 'rect' || currentAnnotation.type === 'filled-rect') {
            setCurrentAnnotation(prev => prev ? {
                ...prev,
                width: coords.x - prev.startX!,
                height: coords.y - prev.startY!,
            } : null);
        } else if (currentAnnotation.type === 'pen') {
            setCurrentAnnotation(prev => prev ? {
                ...prev,
                points: [...(prev.points || []), coords],
            } : null);
        }
    }, [isDrawing, currentAnnotation, getCanvasCoords]);

    const handleMouseUp = useCallback(() => {
        if (!isDrawing || !currentAnnotation) return;
        setIsDrawing(false);

        // Only add if the annotation has meaningful size
        const isValid =
            (currentAnnotation.type === 'pen' && currentAnnotation.points && currentAnnotation.points.length > 2) ||
            ((currentAnnotation.type === 'rect' || currentAnnotation.type === 'filled-rect') &&
                Math.abs(currentAnnotation.width || 0) > 2 && Math.abs(currentAnnotation.height || 0) > 2);

        if (isValid) {
            setAnnotations(prev => [...prev, currentAnnotation]);
        }
        setCurrentAnnotation(null);
    }, [isDrawing, currentAnnotation]);

    // ─── Text input submit ───────────────────────────────────────
    const handleTextSubmit = useCallback(() => {
        if (textInput.trim() && textPosition) {
            const ann: Annotation = {
                type: 'text',
                color,
                strokeWidth,
                text: textInput.trim(),
                x: textPosition.x,
                y: textPosition.y,
                fontSize: Math.max(16, strokeWidth * 8),
            };
            setAnnotations(prev => [...prev, ann]);
            setRedoStack([]);
        }
        setTextPosition(null);
        setTextInput('');
    }, [textInput, textPosition, color, strokeWidth]);

    // ─── Undo / Redo ─────────────────────────────────────────────
    const handleUndo = useCallback(() => {
        setAnnotations(prev => {
            if (prev.length === 0) return prev;
            const last = prev[prev.length - 1];
            setRedoStack(redo => [...redo, last]);
            return prev.slice(0, -1);
        });
    }, []);

    const handleRedo = useCallback(() => {
        setRedoStack(prev => {
            if (prev.length === 0) return prev;
            const last = prev[prev.length - 1];
            setAnnotations(anns => [...anns, last]);
            return prev.slice(0, -1);
        });
    }, []);

    // ─── Save ────────────────────────────────────────────────────
    const handleSave = useCallback(async () => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        // Ensure final render
        renderCanvas();

        setIsSaving(true);
        try {
            const blob = await new Promise<Blob>((resolve, reject) => {
                canvas.toBlob(b => {
                    if (b) resolve(b);
                    else reject(new Error('Failed to export canvas'));
                }, 'image/png');
            });
            await onSave(blob);
        } finally {
            setIsSaving(false);
        }
    }, [renderCanvas, onSave]);

    // ─── Keyboard shortcuts ──────────────────────────────────────
    useEffect(() => {
        if (!open) return;
        const handler = (e: KeyboardEvent) => {
            if (e.ctrlKey && e.key === 'z') {
                e.preventDefault();
                if (e.shiftKey) handleRedo();
                else handleUndo();
            }
            if (e.key === 'Escape') {
                if (textPosition) {
                    setTextPosition(null);
                    setTextInput('');
                }
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [open, handleUndo, handleRedo, textPosition]);

    if (!open) return null;

    return (
        <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
            <DialogContent className="max-w-[95vw] w-[95vw] max-h-[95vh] h-[95vh] p-0 gap-0 bg-slate-950 border-slate-800 overflow-hidden flex flex-col">
                {/* ─── Toolbar ─── */}
                <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900/80 backdrop-blur-xs px-4 py-2 shrink-0 relative z-50">
                    <div className="flex items-center gap-4">
                        {/* Filename */}
                        <span className="text-sm font-medium text-slate-300 max-w-[200px] truncate">
                            {filename || 'Image Editor'}
                        </span>

                        <div className="h-6 w-px bg-slate-700" />

                        {/* Tools */}
                        <TooltipProvider delayDuration={200}>
                            <div className="flex items-center gap-1 bg-slate-800/50 rounded-lg p-1">
                                {TOOLS.map(t => (
                                    <Tooltip key={t.id}>
                                        <TooltipTrigger asChild>
                                            <button
                                                className={cn(
                                                    'p-2 rounded-md transition-all',
                                                    tool === t.id
                                                        ? 'bg-primary text-white shadow-lg shadow-primary/20'
                                                        : 'text-slate-400 hover:text-white hover:bg-slate-700'
                                                )}
                                                onClick={() => setTool(t.id)}
                                            >
                                                <t.icon className="h-4 w-4" />
                                            </button>
                                        </TooltipTrigger>
                                        <TooltipContent side="bottom">{t.label}</TooltipContent>
                                    </Tooltip>
                                ))}
                            </div>
                        </TooltipProvider>

                        <div className="h-6 w-px bg-slate-700" />

                        {/* Colors */}
                        <div className="flex items-center gap-1.5">
                            {COLORS.map(c => (
                                <button
                                    key={c.value}
                                    className={cn(
                                        'h-6 w-6 rounded-full border-2 transition-all',
                                        color === c.value
                                            ? 'border-primary scale-110 ring-2 ring-primary/30'
                                            : 'border-slate-600 hover:border-slate-400'
                                    )}
                                    style={{ backgroundColor: c.value }}
                                    onClick={() => setColor(c.value)}
                                    title={c.label}
                                />
                            ))}
                        </div>

                        <div className="h-6 w-px bg-slate-700" />

                        {/* Stroke width */}
                        <div className="flex items-center gap-2">
                            <span className="text-xs text-slate-500">Size</span>
                            <Slider
                                value={[strokeWidth]}
                                onValueChange={([v]) => setStrokeWidth(v)}
                                min={1}
                                max={20}
                                step={1}
                                className="w-24"
                            />
                            <span className="text-xs text-slate-400 w-4">{strokeWidth}</span>
                        </div>

                        <div className="h-6 w-px bg-slate-700" />

                        {/* Undo / Redo */}
                        <div className="flex items-center gap-1">
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white" onClick={handleUndo} disabled={annotations.length === 0}>
                                <Undo2 className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white" onClick={handleRedo} disabled={redoStack.length === 0}>
                                <Redo2 className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white" onClick={onClose}>
                            <X className="h-4 w-4 mr-1" /> Cancel
                        </Button>
                        <Button
                            size="sm"
                            className="bg-primary hover:bg-primary/90 text-white"
                            onClick={handleSave}
                            disabled={isSaving || annotations.length === 0}
                        >
                            {isSaving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                            Save Changes
                        </Button>
                    </div>
                </div>

                {/* ─── Canvas area ─── */}
                <div ref={containerRef} className="flex-1 relative overflow-hidden bg-[#0a0a0f] flex items-center justify-center">
                    {!imageLoaded ? (
                        <div className="flex flex-col items-center gap-3">
                            <Loader2 className="h-10 w-10 animate-spin text-primary" />
                            <p className="text-sm text-slate-500">Loading image…</p>
                        </div>
                    ) : (
                        <>
                            {/* Checkerboard pattern behind canvas for transparency */}
                            <div
                                className="absolute"
                                style={{
                                    left: offset.x,
                                    top: offset.y,
                                    width: canvasRef.current ? canvasRef.current.style.width : 0,
                                    height: canvasRef.current ? canvasRef.current.style.height : 0,
                                    backgroundImage: 'linear-gradient(45deg, #1a1a2e 25%, transparent 25%), linear-gradient(-45deg, #1a1a2e 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #1a1a2e 75%), linear-gradient(-45deg, transparent 75%, #1a1a2e 75%)',
                                    backgroundSize: '20px 20px',
                                    backgroundPosition: '0 0, 0 10px, 10px -10px, -10px 0px',
                                }}
                            />
                            <canvas
                                ref={canvasRef}
                                onMouseDown={handleMouseDown}
                                onMouseMove={handleMouseMove}
                                onMouseUp={handleMouseUp}
                                onMouseLeave={handleMouseUp}
                                className={cn(
                                    'relative z-10',
                                    tool === 'text' ? 'cursor-text' :
                                        tool === 'eraser' ? 'cursor-pointer' :
                                            'cursor-crosshair'
                                )}
                                style={{
                                    marginLeft: offset.x > 0 ? undefined : 0,
                                    marginTop: offset.y > 0 ? undefined : 0,
                                }}
                            />

                            {/* Text input overlay */}
                            {textPosition && (
                                <div
                                    className="absolute z-30"
                                    style={{
                                        left: offset.x + textPosition.x * scale,
                                        top: offset.y + textPosition.y * scale,
                                    }}
                                    onMouseDown={(e) => e.stopPropagation()}
                                >
                                    <input
                                        ref={(el) => {
                                            if (el) setTimeout(() => el.focus(), 50);
                                        }}
                                        value={textInput}
                                        onChange={(e) => setTextInput(e.target.value)}
                                        onKeyDown={(e) => {
                                            e.stopPropagation();
                                            if (e.key === 'Enter') handleTextSubmit();
                                            if (e.key === 'Escape') { setTextPosition(null); setTextInput(''); }
                                        }}
                                        onBlur={() => {
                                            // Delay to avoid premature submit from focus trap stealing focus
                                            setTimeout(() => handleTextSubmit(), 150);
                                        }}
                                        className="bg-slate-900/95 border-2 border-primary text-white px-3 py-1.5 text-sm rounded-md outline-hidden min-w-[150px] shadow-lg shadow-primary/20"
                                        placeholder="Type text, press Enter…"
                                        style={{ color }}
                                    />
                                </div>
                            )}
                        </>
                    )}
                </div>

                {/* ─── Status bar ─── */}
                <div className="border-t border-slate-800 bg-slate-900/60 px-4 py-1.5 flex items-center justify-between text-xs text-slate-500 shrink-0">
                    <span>{annotations.length} annotation{annotations.length !== 1 ? 's' : ''}</span>
                    <span>
                        {baseImageRef.current ? `${baseImageRef.current.naturalWidth} × ${baseImageRef.current.naturalHeight}px` : ''}
                        {' · '}Ctrl+Z / Ctrl+Shift+Z to undo/redo
                    </span>
                </div>
            </DialogContent>
        </Dialog>
    );
}

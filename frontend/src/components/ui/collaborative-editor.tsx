'use client';

import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import Placeholder from '@tiptap/extension-placeholder';
import Link from '@tiptap/extension-link';
import { AuthAwareImage as Image } from './auth-image-node-view';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import Underline from '@tiptap/extension-underline';
import Highlight from '@tiptap/extension-highlight';
import TextAlign from '@tiptap/extension-text-align';
import { Color } from '@tiptap/extension-color';
import { TextStyle } from '@tiptap/extension-text-style';
import Subscript from '@tiptap/extension-subscript';
import Superscript from '@tiptap/extension-superscript';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableHeader } from '@tiptap/extension-table-header';
import { TableCell } from '@tiptap/extension-table-cell';
import api, { apiErrorMessage } from '@/lib/api';
import Collaboration from '@tiptap/extension-collaboration';
import { fixedCursorPlugin } from '@/lib/fixed-cursor-plugin';
import { yCursorPluginKey } from '@tiptap/y-tiptap';
import { Extension } from '@tiptap/core';
import { common, createLowlight } from 'lowlight';
import * as Y from 'yjs';
import * as syncProtocol from 'y-protocols/sync';
import * as awarenessProtocol from 'y-protocols/awareness';
import * as encoding from 'lib0/encoding';
import * as decoding from 'lib0/decoding';
import { useState, useEffect, useRef, useMemo } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { cn } from '@/lib/utils';
import { Wifi, WifiOff, Loader2, Users, Eye } from 'lucide-react';
import {
    Bold, Italic, List as ListIcon, ListOrdered, Quote,
    Undo, Redo, Code, Heading as HeadingIcon, Strikethrough,
    Link as LinkIcon, Image as ImageIcon, CheckSquare, CodeXml, ChevronDown,
    Underline as UnderlineIcon, Highlighter, Palette, Subscript as SubIcon,
    Superscript as SupIcon, AlignLeft, AlignCenter, AlignRight, AlignJustify,
    Table as TableIcon, Trash2, Plus, Minus,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const lowlight = createLowlight(common);

// Binary message types (first varuint in the message)
const MSG_SYNC = 0;
const MSG_AWARENESS = 1;

// Cursor colors — consistent per user via hash
const CURSOR_COLORS = [
    '#14b8a6', '#f97316', '#a855f7', '#ef4444',
    '#3b82f6', '#22c55e', '#eab308', '#ec4899',
];

function getCursorColor(userId: string): string {
    let hash = 0;
    for (let i = 0; i < userId.length; i++) {
        hash = ((hash << 5) - hash + userId.charCodeAt(i)) | 0;
    }
    return CURSOR_COLORS[Math.abs(hash) % CURSOR_COLORS.length];
}

interface CollaborativeEditorProps {
    noteId: string;
    disabled?: boolean;
    placeholder?: string;
    minHeight?: string;
    className?: string;
    /** Required for paste/drop image upload. */
    engagementId?: string;
}

/**
 * Upload a pasted/dropped image to /markdown-images and insert an image
 * node at the given position. Mirrors the same helper in tiptap-editor.
 */
async function uploadAndInsertImage(view: any, file: File, pos: number, engagementId: string) {
    const { toast } = await import('sonner');
    try {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('engagement_id', engagementId);
        const { data } = await api.post('/markdown-images', fd, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        const node = view.state.schema.nodes.image.create({
            src: data.url,
            alt: file.name,
        });
        view.dispatch(view.state.tr.insert(pos, node));
    } catch (err: any) {
        toast.error(apiErrorMessage(err, 'Failed to upload image'));
    }
}

// ─── Menu Bar ──────────────────────────────────────────────────────────

const MenuBar = ({ editor }: { editor: any }) => {
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);
    const [imageDialogOpen, setImageDialogOpen] = useState(false);
    const [linkUrl, setLinkUrl] = useState('');
    const [imageUrl, setImageUrl] = useState('');

    if (!editor) return null;

    const openLinkDialog = () => {
        const previousUrl = editor.getAttributes('link').href;
        setLinkUrl(previousUrl || '');
        setLinkDialogOpen(true);
    };

    const handleSetLink = () => {
        if (linkUrl === '') {
            editor.chain().focus().extendMarkRange('link').unsetLink().run();
        } else {
            editor.chain().focus().extendMarkRange('link').setLink({ href: linkUrl }).run();
        }
        setLinkDialogOpen(false);
        setLinkUrl('');
    };

    const openImageDialog = () => {
        setImageUrl('');
        setImageDialogOpen(true);
    };

    const handleSetImage = () => {
        if (imageUrl) {
            editor.chain().focus().setImage({ src: imageUrl }).run();
        }
        setImageDialogOpen(false);
        setImageUrl('');
    };

    return (
        <>
            <div className="flex flex-wrap items-center gap-1 p-2 border-b border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                <Button type="button" variant="ghost" size="icon"
                    onClick={() => editor.chain().focus().undo().run()}
                    disabled={!editor.can().chain().focus().undo().run()}
                    className="h-8 w-8 text-slate-400 hover:text-white hover:bg-slate-800">
                    <Undo className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon"
                    onClick={() => editor.chain().focus().redo().run()}
                    disabled={!editor.can().chain().focus().redo().run()}
                    className="h-8 w-8 text-slate-400 hover:text-white hover:bg-slate-800">
                    <Redo className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button type="button" variant="ghost" size="sm"
                            className="h-8 px-2 gap-1 text-slate-400 hover:text-white hover:bg-slate-800">
                            <HeadingIcon className="h-4 w-4" />
                            <ChevronDown className="h-3 w-3" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="bg-slate-900 border-slate-800 text-slate-300">
                        <DropdownMenuItem onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer">Heading 1</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer">Heading 2</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer">Heading 3</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => editor.chain().focus().setParagraph().run()} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer">Paragraph</DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>

                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleBold().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('bold') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <Bold className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleItalic().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('italic') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <Italic className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleUnderline().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('underline') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <UnderlineIcon className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleStrike().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('strike') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <Strikethrough className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleCode().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('code') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <Code className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                {/* Highlight + colour */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button type="button" variant="ghost" size="icon"
                            className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('highlight') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                            title="Highlight">
                            <Highlighter className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 p-2 min-w-0">
                        <div className="flex flex-wrap gap-1.5 max-w-[160px]">
                            {['#fde68a', '#fca5a5', '#86efac', '#93c5fd', '#c4b5fd', '#fdba74', '#f9a8d4'].map(c => (
                                <button key={c} type="button"
                                    onClick={() => editor.chain().focus().toggleHighlight({ color: c }).run()}
                                    className="h-5 w-5 rounded border border-slate-700 hover:scale-110 transition-transform"
                                    style={{ backgroundColor: c }} />
                            ))}
                            <button type="button"
                                onClick={() => editor.chain().focus().unsetHighlight().run()}
                                className="h-5 w-5 rounded border border-slate-700 bg-slate-800 text-slate-400 flex items-center justify-center text-[10px] hover:bg-slate-700"
                                title="Clear">×</button>
                        </div>
                    </DropdownMenuContent>
                </DropdownMenu>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button type="button" variant="ghost" size="icon"
                            className="h-8 w-8 text-slate-400 hover:bg-slate-800"
                            title="Text colour">
                            <Palette className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 p-2 min-w-0">
                        <div className="flex flex-wrap gap-1.5 max-w-[160px]">
                            {['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6', '#ec4899', '#ffffff', '#94a3b8'].map(c => (
                                <button key={c} type="button"
                                    onClick={() => editor.chain().focus().setColor(c).run()}
                                    className="h-5 w-5 rounded border border-slate-700 hover:scale-110 transition-transform"
                                    style={{ backgroundColor: c }} />
                            ))}
                            <button type="button"
                                onClick={() => editor.chain().focus().unsetColor().run()}
                                className="h-5 w-5 rounded border border-slate-700 bg-slate-800 text-slate-400 flex items-center justify-center text-[10px] hover:bg-slate-700"
                                title="Clear">×</button>
                        </div>
                    </DropdownMenuContent>
                </DropdownMenu>

                {/* Subscript / superscript */}
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleSubscript().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('subscript') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Subscript">
                    <SubIcon className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleSuperscript().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('superscript') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Superscript">
                    <SupIcon className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                {/* Text alignment */}
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().setTextAlign('left').run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive({ textAlign: 'left' }) ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Align left">
                    <AlignLeft className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().setTextAlign('center').run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive({ textAlign: 'center' }) ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Align center">
                    <AlignCenter className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().setTextAlign('right').run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive({ textAlign: 'right' }) ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Align right">
                    <AlignRight className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().setTextAlign('justify').run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive({ textAlign: 'justify' }) ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Justify">
                    <AlignJustify className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                <Button type="button" variant="ghost" size="icon" onClick={openLinkDialog}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('link') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <LinkIcon className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleBulletList().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('bulletList') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <ListIcon className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleOrderedList().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('orderedList') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <ListOrdered className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleTaskList().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('taskList') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <CheckSquare className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleBlockquote().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('blockquote') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <Quote className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" onClick={() => editor.chain().focus().toggleCodeBlock().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('codeBlock') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}>
                    <CodeXml className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                {/* Tables */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button type="button" variant="ghost" size="icon"
                            className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('table') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                            title="Table">
                            <TableIcon className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 text-slate-300">
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white">
                            <Plus className="h-3.5 w-3.5 mr-2" /> Insert table (3×3)
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().addColumnAfter().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white">
                            <Plus className="h-3.5 w-3.5 mr-2" /> Column after
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().deleteColumn().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white">
                            <Minus className="h-3.5 w-3.5 mr-2" /> Delete column
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().addRowAfter().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white">
                            <Plus className="h-3.5 w-3.5 mr-2" /> Row after
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().deleteRow().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white">
                            <Minus className="h-3.5 w-3.5 mr-2" /> Delete row
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().toggleHeaderRow().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white">
                            Toggle header row
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().deleteTable().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white text-red-400">
                            <Trash2 className="h-3.5 w-3.5 mr-2" /> Delete table
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>

                <Button type="button" variant="ghost" size="icon" onClick={openImageDialog}
                    className="h-8 w-8 text-slate-400 hover:text-white hover:bg-slate-800">
                    <ImageIcon className="h-4 w-4" />
                </Button>
            </div>

            {/* Link Dialog */}
            <Dialog open={linkDialogOpen} onOpenChange={setLinkDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white">
                    <DialogHeader>
                        <DialogTitle>Insert Link</DialogTitle>
                        <DialogDescription className="text-slate-400">Enter the URL.</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="collab-link-url" className="text-slate-300">URL</Label>
                            <Input id="collab-link-url" placeholder="https://example.com" value={linkUrl}
                                onChange={(e) => setLinkUrl(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter') handleSetLink(); }}
                                className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-500" autoFocus />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => setLinkDialogOpen(false)} className="border-slate-700 text-slate-300 hover:bg-slate-800">Cancel</Button>
                        <Button type="button" onClick={handleSetLink} className="bg-blue-600 hover:bg-blue-700">{linkUrl ? 'Set Link' : 'Remove Link'}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Image Dialog */}
            <Dialog open={imageDialogOpen} onOpenChange={setImageDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white">
                    <DialogHeader>
                        <DialogTitle>Insert Image</DialogTitle>
                        <DialogDescription className="text-slate-400">Enter the image URL.</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="collab-image-url" className="text-slate-300">Image URL</Label>
                            <Input id="collab-image-url" placeholder="https://example.com/image.png" value={imageUrl}
                                onChange={(e) => setImageUrl(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter') handleSetImage(); }}
                                className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-500" autoFocus />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => setImageDialogOpen(false)} className="border-slate-700 text-slate-300 hover:bg-slate-800">Cancel</Button>
                        <Button type="button" onClick={handleSetImage} disabled={!imageUrl} className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50">Insert Image</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
};

// ─── Collaborative Editor ──────────────────────────────────────────────

export default function CollaborativeEditor({
    noteId,
    disabled = false,
    placeholder = 'Start writing your notes...',
    minHeight = 'calc(100vh - 450px)',
    className,
    engagementId,
}: CollaborativeEditorProps) {
    const { user: currentUser } = useAuthStore();
    const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
    const [peerCount, setPeerCount] = useState(0);
    const [, setForceUpdate] = useState(0);
    const wsRef = useRef<WebSocket | null>(null);
    const editorRef = useRef<any>(null);

    // Stable Y.js doc + awareness — created once per mount.
    // Parent uses key={noteId} to force full remount on note switch.
    const ydoc = useMemo(() => new Y.Doc(), []); // eslint-disable-line react-hooks/exhaustive-deps
    const awareness = useMemo(() => new awarenessProtocol.Awareness(ydoc), [ydoc]);

    const userColor = useMemo(() => getCursorColor(currentUser?.id || 'anon'), [currentUser?.id]);

    // Build WebSocket URL
    const wsUrl = useMemo(() => {
        if (typeof window === 'undefined') return '';
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;

        let base: string;
        if (apiUrl && !apiUrl.includes(host)) {
            base = apiUrl.replace(/^http/, 'ws');
        } else {
            base = `${protocol}//${host}/api`;
        }
        // Token is intentionally NOT in the URL — backend reads it from
        // the first message after accept(). CWE-598 (bearer-in-URL).
        // Auth bearer is sent as the first WS frame in onopen below.
        return `${base}/ws/yjs/note/${noteId}`;
    }, [noteId]);

    // ─── WebSocket + Y.js sync protocol ───────────────────────────────
    useEffect(() => {
        if (typeof window === 'undefined' || !wsUrl || !currentUser) return;

        const token = localStorage.getItem('access_token');
        if (!token) return;

        let ws: WebSocket;
        let reconnectTimeout: NodeJS.Timeout;
        let retryCount = 0;
        let isCleaningUp = false;
        let initialContentPending: string | null = null;
        let initialContentTimer: NodeJS.Timeout | undefined;

        // Track awareness changes → update peer count
        const awarenessChangeHandler = () => {
            const states = awareness.getStates();
            // Count other users (exclude self)
            let others = 0;
            states.forEach((_state, clientID) => {
                if (clientID !== ydoc.clientID) others++;
            });
            setPeerCount(others);
        };
        awareness.on('change', awarenessChangeHandler);

        // Set local awareness user info.
        // IMPORTANT: Use setLocalState (not setLocalStateField) because after
        // cleanup calls removeAwarenessStates(), the local state is null, and
        // setLocalStateField silently does nothing when state is null.
        awareness.setLocalState({
            user: {
                name: currentUser.full_name || currentUser.username || 'Anonymous',
                color: userColor,
            },
        });

        // Send encoded binary message via WebSocket
        const sendBinary = (msg: Uint8Array) => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send(msg);
            }
        };

        // Y.Doc update handler → send sync update to peers
        const docUpdateHandler = (update: Uint8Array, origin: any) => {
            if (origin === 'remote') return; // Don't echo remote updates
            const encoder = encoding.createEncoder();
            encoding.writeVarUint(encoder, MSG_SYNC);
            syncProtocol.writeUpdate(encoder, update);
            sendBinary(encoding.toUint8Array(encoder));
        };
        ydoc.on('update', docUpdateHandler);

        // Awareness update handler → send to peers
        const awarenessUpdateHandler = ({ added, updated, removed }: any) => {
            const changedClients = [...added, ...updated, ...removed];
            const encoder = encoding.createEncoder();
            encoding.writeVarUint(encoder, MSG_AWARENESS);
            encoding.writeVarUint8Array(encoder,
                awarenessProtocol.encodeAwarenessUpdate(awareness, changedClients)
            );
            const msg = encoding.toUint8Array(encoder);
            sendBinary(msg);
        };
        awareness.on('update', awarenessUpdateHandler);

        const connect = () => {
            if (isCleaningUp) return;
            setConnectionStatus('connecting');

            ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.binaryType = 'arraybuffer';

            ws.onopen = () => {
                if (isCleaningUp) { ws.close(); return; }
                setConnectionStatus('connected');
                retryCount = 0;

                // FIRST frame MUST be the auth bearer. Backend has 5s
                // to receive it before closing with 1008 (see
                // _AUTH_FRAME_TIMEOUT_S in routers/websocket.py). The
                // register/sync/awareness messages below all flow
                // *after* auth succeeds.
                ws.send(JSON.stringify({ type: 'auth', token }));

                // 0. Register our Y.js clientID with the server so it can
                //    notify peers when we disconnect (for cursor cleanup)
                ws.send(JSON.stringify({
                    type: 'register_client_id',
                    client_id: ydoc.clientID,
                }));

                // 1. Send Y.js sync step 1 (our state vector → peers respond with what we're missing)
                const encoder = encoding.createEncoder();
                encoding.writeVarUint(encoder, MSG_SYNC);
                syncProtocol.writeSyncStep1(encoder, ydoc);
                sendBinary(encoding.toUint8Array(encoder));

                // 2. Broadcast our awareness state
                const awarenessEncoder = encoding.createEncoder();
                encoding.writeVarUint(awarenessEncoder, MSG_AWARENESS);
                encoding.writeVarUint8Array(awarenessEncoder,
                    awarenessProtocol.encodeAwarenessUpdate(awareness, [ydoc.clientID])
                );
                sendBinary(encoding.toUint8Array(awarenessEncoder));
            };

            ws.onmessage = (event) => {
                if (typeof event.data === 'string') {
                    // JSON control messages from server
                    try {
                        const data = JSON.parse(event.data);

                        if (data.type === 'initial_content') {
                            // Store it; only apply if no peer sync fills the doc
                            initialContentPending = data.content || '';
                            // Give peers 800ms to sync their state before falling back to DB content
                            clearTimeout(initialContentTimer);
                            initialContentTimer = setTimeout(() => {
                                const fragment = ydoc.getXmlFragment('default');
                                if (fragment.length === 0 && initialContentPending && editorRef.current) {
                                    // No peer sync happened — bootstrap from DB
                                    editorRef.current.commands.setContent(initialContentPending);
                                }
                                initialContentPending = null;
                            }, 800);
                        } else if (data.type === 'request_save') {
                            // Server wants us to save current content to DB
                            const ed = editorRef.current;
                            if (ed) {
                                const markdown = (ed.storage as any).markdown?.getMarkdown?.() || '';
                                ws.send(JSON.stringify({
                                    type: 'save_content',
                                    content: markdown,
                                    note_id: data.note_id,
                                }));
                            }
                        } else if (data.type === 'peer_disconnected') {
                            const clientId = data.client_id;
                            if (clientId != null && clientId !== ydoc.clientID) {
                                awarenessProtocol.removeAwarenessStates(awareness, [clientId], 'peer_disconnect');
                                // Also force-delete from map and dispatch decoration rebuild
                                awareness.getStates().delete(clientId);
                                const ed = editorRef.current;
                                if (ed?.view) {
                                    try {
                                        ed.view.dispatch(ed.view.state.tr.setMeta(yCursorPluginKey, { awarenessUpdated: true }));
                                    } catch { /* editor might be destroyed */ }
                                }
                            }
                        }
                    } catch { /* ignore */ }
                } else {
                    // Binary: Y.js sync protocol or awareness
                    const data = new Uint8Array(event.data as ArrayBuffer);
                    if (data.length < 1) return;

                    const decoder = decoding.createDecoder(data);
                    const messageType = decoding.readVarUint(decoder);

                    switch (messageType) {
                        case MSG_SYNC: {
                            // Process sync message and potentially respond (e.g., sync step 2 reply)
                            const responseEncoder = encoding.createEncoder();
                            encoding.writeVarUint(responseEncoder, MSG_SYNC);
                            syncProtocol.readSyncMessage(decoder, responseEncoder, ydoc, 'remote');
                            // If a response was generated (sync step 2), send it back
                            if (encoding.length(responseEncoder) > 1) {
                                sendBinary(encoding.toUint8Array(responseEncoder));
                            }
                            // If we received peer state, cancel the initial_content fallback
                            const fragment = ydoc.getXmlFragment('default');
                            if (fragment.length > 0 && initialContentPending !== null) {
                                clearTimeout(initialContentTimer);
                                initialContentPending = null;
                            }
                            break;
                        }
                        case MSG_AWARENESS: {
                            const update = decoding.readVarUint8Array(decoder);
                            awarenessProtocol.applyAwarenessUpdate(awareness, update, 'remote');
                            break;
                        }
                    }
                }
            };

            ws.onclose = () => {
                if (isCleaningUp) return;
                setConnectionStatus('disconnected');
                wsRef.current = null;

                if (retryCount < 10) {
                    const delay = Math.max(2000, Math.min(1000 * Math.pow(2, retryCount), 30000));
                    reconnectTimeout = setTimeout(() => {
                        retryCount++;
                        connect();
                    }, delay);
                }
            };

            ws.onerror = () => { ws.close(); };
        };

        connect();

        // ─── Aggressive stale awareness cleanup ──────────────────────
        // y-protocols default timeout is 30s — too slow for cursor removal.
        // Track when we last received an awareness update for each peer and
        // evict any that go stale after 10s.
        const STALE_THRESHOLD = 10_000; // 10 seconds
        const peerLastSeen = new Map<number, number>();

        // Update timestamp whenever we hear from a peer
        const trackPeerActivity = ({ added, updated, removed }: any) => {
            const now = Date.now();
            for (const id of [...(added || []), ...(updated || [])]) {
                if (id !== ydoc.clientID) peerLastSeen.set(id, now);
            }
            // Clean removed peers from tracking
            for (const id of (removed || [])) {
                peerLastSeen.delete(id);
            }
        };
        awareness.on('change', trackPeerActivity);

        const staleCleanupInterval = setInterval(() => {
            const now = Date.now();
            const states = awareness.getStates();
            const stale: number[] = [];
            states.forEach((_state, clientID) => {
                if (clientID !== ydoc.clientID) {
                    const lastSeen = peerLastSeen.get(clientID);
                    const age = lastSeen ? now - lastSeen : Infinity;
                    if (age > STALE_THRESHOLD) {
                        stale.push(clientID);
                    }
                }
            });
            if (stale.length > 0) {
                awarenessProtocol.removeAwarenessStates(awareness, stale, 'timeout');
                for (const id of stale) {
                    peerLastSeen.delete(id);
                    if (states.has(id)) {
                        states.delete(id);
                    }
                }
                // Force the editor to rebuild cursor decorations by dispatching
                // directly to the view — the awareness.emit approach doesn't
                // reliably trigger ProseMirror's plugin apply method.
                const ed = editorRef.current;
                if (ed?.view) {
                    try {
                        ed.view.dispatch(ed.view.state.tr.setMeta(yCursorPluginKey, { awarenessUpdated: true }));
                    } catch { /* editor might be destroyed */ }
                }
            }
        }, 5_000);

        return () => {
            isCleaningUp = true;
            clearTimeout(initialContentTimer);
            clearTimeout(reconnectTimeout);
            clearInterval(staleCleanupInterval);
            awareness.off('change', trackPeerActivity);
            // 1. Remove our awareness state FIRST — while the update handler
            //    is still attached so it can broadcast the removal to peers.
            awarenessProtocol.removeAwarenessStates(awareness, [ydoc.clientID], 'local');
            // 2. Now remove handlers (no more updates to send)
            ydoc.off('update', docUpdateHandler);
            awareness.off('update', awarenessUpdateHandler);
            awareness.off('change', awarenessChangeHandler);
            // 3. Close the WebSocket last
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, [wsUrl, currentUser, ydoc, awareness, userColor]);

    // ─── TipTap Editor ────────────────────────────────────────────────
    const editor = useEditor({
        extensions: [
            StarterKit.configure({
                codeBlock: false,
            }),
            CodeBlockLowlight.configure({
                lowlight,
                HTMLAttributes: { class: 'hljs' },
            }),
            Markdown.configure({
                html: false,
                transformPastedText: true,
                transformCopiedText: true,
            }),
            Placeholder.configure({
                placeholder,
            }),
            Link.configure({
                openOnClick: false,
                HTMLAttributes: {
                    class: 'text-blue-400 underline hover:text-blue-300 cursor-pointer',
                },
            }),
            Image,
            TaskList,
            TaskItem.configure({ nested: true }),
            Underline,
            Highlight.configure({ multicolor: true }),
            TextAlign.configure({ types: ['heading', 'paragraph'] }),
            TextStyle,
            Color,
            Subscript,
            Superscript,
            Table.configure({ resizable: true, HTMLAttributes: { class: 'redwire-table' } }),
            TableRow,
            TableHeader,
            TableCell,
            Collaboration.configure({
                document: ydoc,
            }),
            // Custom cursor extension using fixedCursorPlugin that corrects
            // the off-by-one cursor position (assoc -1 → 0)
            Extension.create({
                name: 'collaborationCursor',
                addProseMirrorPlugins() {
                    return [
                        fixedCursorPlugin(
                            awareness,
                            {
                                cursorBuilder: (user: any) => {
                                    const cursor = document.createElement('span');
                                    cursor.classList.add('collaboration-cursor__caret');
                                    // GHSA-82vg-f3qp-gv8v: `user.color` is peer-supplied via
                                    // Y.js awareness and the backend relay forwards it byte-for-byte.
                                    // Assigning to the typed CSSOM property makes the browser parse
                                    // the value as a single CSS token \u2014 a multi-declaration payload
                                    // like `red;position:fixed;\u2026` is rejected and the property is
                                    // left unset. Do NOT go back to setAttribute('style', \u2026).
                                    cursor.style.borderColor = user.color;
                                    const wj1 = document.createTextNode('\u2060');
                                    const wj2 = document.createTextNode('\u2060');
                                    const label = document.createElement('div');
                                    label.classList.add('collaboration-cursor__label');
                                    label.style.backgroundColor = user.color;
                                    label.textContent = user.name;
                                    cursor.appendChild(wj1);
                                    cursor.appendChild(label);
                                    cursor.appendChild(wj2);
                                    return cursor;
                                },
                            }
                        ),
                    ];
                },
            }),
        ],
        editable: !disabled,
        immediatelyRender: false,
        onUpdate: ({ editor: ed }) => {
            // Schedule a server-side DB save via the WS
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                const markdown = (ed.storage as any).markdown?.getMarkdown?.() || '';
                wsRef.current.send(JSON.stringify({
                    type: 'save_content',
                    content: markdown,
                    note_id: noteId,
                }));
            }
        },
        onSelectionUpdate: () => {
            setForceUpdate(prev => prev + 1);
        },
        editorProps: {
            attributes: {
                class: 'prose prose-invert max-w-none focus:outline-hidden p-4 min-h-[inherit]',
            },
            // Drag/drop image upload — same flow as tiptap-editor.
            handleDrop: (view, event, _slice, _moved) => {
                const dt = (event as DragEvent).dataTransfer;
                if (!dt || !dt.files || dt.files.length === 0) return false;
                const images = Array.from(dt.files).filter(f => f.type.startsWith('image/'));
                if (images.length === 0) return false;
                if (!engagementId) {
                    event.preventDefault();
                    import('sonner').then(({ toast }) =>
                        toast.error('Image upload requires an engagement context')
                    );
                    return true;
                }
                event.preventDefault();
                const coords = view.posAtCoords({ left: (event as DragEvent).clientX, top: (event as DragEvent).clientY });
                const insertPos = coords?.pos ?? view.state.selection.from;
                images.forEach(f => uploadAndInsertImage(view, f, insertPos, engagementId));
                return true;
            },
            handlePaste: (view, event, _slice) => {
                const items = (event as ClipboardEvent).clipboardData?.items;
                if (!items) return false;
                const images: File[] = [];
                for (let i = 0; i < items.length; i++) {
                    const it = items[i];
                    if (it.kind === 'file' && it.type.startsWith('image/')) {
                        const f = it.getAsFile();
                        if (f) images.push(f);
                    }
                }
                if (images.length === 0) return false;
                if (!engagementId) {
                    event.preventDefault();
                    import('sonner').then(({ toast }) =>
                        toast.error('Image upload requires an engagement context')
                    );
                    return true;
                }
                event.preventDefault();
                const insertPos = view.state.selection.from;
                images.forEach(f => uploadAndInsertImage(view, f, insertPos, engagementId));
                return true;
            },
        },
    });

    // Keep ref in sync
    editorRef.current = editor;

    // Cleanup Y.Doc + Awareness on unmount
    useEffect(() => {
        return () => {
            awareness.destroy();
            ydoc.destroy();
        };
    }, [ydoc, awareness]);

    return (
        <div className={cn("flex flex-col border border-slate-800 rounded-lg overflow-hidden bg-slate-950/40", className)}>
            {/* Toolbar */}
            <div className="relative">
                <MenuBar editor={editor} />

                {/* Connection status + peer count */}
                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-2">
                    {disabled && (
                        <span
                            className="flex items-center gap-1 text-[10px] font-medium text-slate-300 bg-slate-800/70 border border-slate-700 rounded-full px-2 py-0.5"
                            title="You don't have permission to edit this note. Live edits from others still appear as they happen."
                        >
                            <Eye className="h-3 w-3" />
                            Read only
                        </span>
                    )}
                    {peerCount > 0 && (
                        <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                            <Users className="h-3 w-3" />
                            {peerCount + 1} editing
                        </span>
                    )}
                    {connectionStatus === 'connected' && (
                        <span className="flex items-center gap-1 text-[10px] text-emerald-400" title="Connected — real-time sync active">
                            <Wifi className="h-3 w-3" />
                        </span>
                    )}
                    {connectionStatus === 'connecting' && (
                        <span className="flex items-center gap-1 text-[10px] text-amber-400" title="Connecting...">
                            <Loader2 className="h-3 w-3 animate-spin" />
                        </span>
                    )}
                    {connectionStatus === 'disconnected' && (
                        <span className="flex items-center gap-1 text-[10px] text-red-400" title="Disconnected — changes saved locally">
                            <WifiOff className="h-3 w-3" />
                        </span>
                    )}
                </div>
            </div>

            {/* Editor content */}
            <div
                className="overflow-y-auto"
                style={{ minHeight }}
                onClick={() => editor?.commands.focus()}
            >
                <EditorContent editor={editor} />
            </div>
        </div>
    );
}

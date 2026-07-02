'use client';

import { useEditor, EditorContent, ReactRenderer } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import Placeholder from '@tiptap/extension-placeholder';
import Link from '@tiptap/extension-link';
import { AuthAwareImage as Image } from './auth-image-node-view';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import Mention from '@tiptap/extension-mention';
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
import { SuggestionProps, SuggestionKeyDownProps } from '@tiptap/suggestion';
import tippy, { Instance as TippyInstance } from 'tippy.js';
import { common, createLowlight } from 'lowlight';
import { useState, useEffect, useCallback, useRef } from 'react';
import MentionList, { MentionListRef, MentionSuggestionItem } from './mention-list';
import api, { apiErrorMessage } from '@/lib/api';
import { useAuthStore } from '@/stores/auth-store';
import { useQuery } from '@tanstack/react-query';

import {
    Bold, Italic, List as ListIcon, ListOrdered, Quote,
    Undo, Redo, Code, Heading as HeadingIcon, Strikethrough,
    Link as LinkIcon, Image as ImageIcon, CheckSquare, CodeXml, ChevronDown,
    Sparkles, Send, X, ClipboardPaste, Loader2, Database,
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
import { cn } from '@/lib/utils';

// Create lowlight instance with common languages
const lowlight = createLowlight(common);

// Cache for loaded users to avoid re-fetching
let _cachedUsers: MentionSuggestionItem[] | null = null;
let _fetchPromise: Promise<MentionSuggestionItem[]> | null = null;

async function fetchAllUsers(): Promise<MentionSuggestionItem[]> {
    if (_cachedUsers) return _cachedUsers;
    if (_fetchPromise) return _fetchPromise;
    _fetchPromise = api.get<MentionSuggestionItem[]>('/users').then(res => {
        _cachedUsers = res.data;
        return _cachedUsers!;
    }).catch(() => {
        _fetchPromise = null;
        return [] as MentionSuggestionItem[];
    });
    return _fetchPromise;
}

// Mention suggestion config
const mentionSuggestion = {
    items: async ({ query }: { query: string }) => {
        const users = await fetchAllUsers();
        const q = query.toLowerCase();
        return users
            .filter(
                (u) =>
                    u.username.toLowerCase().includes(q) ||
                    (u.full_name && u.full_name.toLowerCase().includes(q))
            )
            .slice(0, 8);
    },
    render: () => {
        let component: ReactRenderer<MentionListRef> | null = null;
        let popup: TippyInstance[] | null = null;

        return {
            onStart: (props: SuggestionProps) => {
                component = new ReactRenderer(MentionList, {
                    props: { items: props.items, command: props.command },
                    editor: props.editor,
                });

                if (!props.clientRect) return;

                popup = tippy('body', {
                    getReferenceClientRect: props.clientRect as () => DOMRect,
                    appendTo: () => document.body,
                    content: component.element,
                    showOnCreate: true,
                    interactive: true,
                    trigger: 'manual',
                    placement: 'bottom-start',
                });
            },
            onUpdate: (props: SuggestionProps) => {
                component?.updateProps({ items: props.items, command: props.command });
                if (popup && props.clientRect) {
                    popup[0].setProps({ getReferenceClientRect: props.clientRect as () => DOMRect });
                }
            },
            onKeyDown: (props: SuggestionKeyDownProps) => {
                if (props.event.key === 'Escape') {
                    popup?.[0]?.hide();
                    return true;
                }
                return component?.ref?.onKeyDown(props) ?? false;
            },
            onExit: () => {
                popup?.[0]?.destroy();
                component?.destroy();
            },
        };
    },
};

interface TiptapEditorProps {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    disabled?: boolean;
    minHeight?: string;
    id?: string;
    className?: string;
    fieldContext?: { resourceType: string; fieldName: string };
    /** When provided, paste/drop of image files uploads them via
     *  POST /markdown-images and inserts the resulting URL.
     *  Without it the toolbar image-by-URL dialog still works. */
    engagementId?: string;
}

const MenuBar = ({ editor }: { editor: any }) => {
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);
    const [imageDialogOpen, setImageDialogOpen] = useState(false);
    const [linkUrl, setLinkUrl] = useState('');
    const [imageUrl, setImageUrl] = useState('');

    if (!editor) {
        return null;
    }

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
                {/* History */}
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().undo().run()}
                    disabled={!editor.can().chain().focus().undo().run()}
                    className="h-8 w-8 text-slate-400 hover:text-white hover:bg-slate-800"
                >
                    <Undo className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().redo().run()}
                    disabled={!editor.can().chain().focus().redo().run()}
                    className="h-8 w-8 text-slate-400 hover:text-white hover:bg-slate-800"
                >
                    <Redo className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                {/* Headings */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-8 px-2 gap-1 text-slate-400 hover:text-white hover:bg-slate-800"
                        >
                            <HeadingIcon className="h-4 w-4" />
                            <ChevronDown className="h-3 w-3" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="bg-slate-900 border-slate-800 text-slate-300">
                        <DropdownMenuItem onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer">
                            Heading 1
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer">
                            Heading 2
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer">
                            Heading 3
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => editor.chain().focus().setParagraph().run()} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer">
                            Paragraph
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>

                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleBold().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('bold') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Bold className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleItalic().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('italic') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Italic className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleUnderline().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('underline') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <UnderlineIcon className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleStrike().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('strike') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Strikethrough className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleCode().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('code') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Code className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                {/* Highlight + colour */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('highlight') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                            title="Highlight"
                        >
                            <Highlighter className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 p-2 min-w-0">
                        <div className="flex flex-wrap gap-1.5 max-w-[160px]">
                            {['#fde68a', '#fca5a5', '#86efac', '#93c5fd', '#c4b5fd', '#fdba74', '#f9a8d4'].map(c => (
                                <button
                                    key={c}
                                    type="button"
                                    onClick={() => editor.chain().focus().toggleHighlight({ color: c }).run()}
                                    className="h-5 w-5 rounded border border-slate-700 hover:scale-110 transition-transform"
                                    style={{ backgroundColor: c }}
                                />
                            ))}
                            <button
                                type="button"
                                onClick={() => editor.chain().focus().unsetHighlight().run()}
                                className="h-5 w-5 rounded border border-slate-700 bg-slate-800 text-slate-400 flex items-center justify-center text-[10px] hover:bg-slate-700"
                                title="Clear"
                            >
                                ×
                            </button>
                        </div>
                    </DropdownMenuContent>
                </DropdownMenu>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-slate-400 hover:bg-slate-800"
                            title="Text colour"
                        >
                            <Palette className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 p-2 min-w-0">
                        <div className="flex flex-wrap gap-1.5 max-w-[160px]">
                            {['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6', '#ec4899', '#ffffff', '#94a3b8'].map(c => (
                                <button
                                    key={c}
                                    type="button"
                                    onClick={() => editor.chain().focus().setColor(c).run()}
                                    className="h-5 w-5 rounded border border-slate-700 hover:scale-110 transition-transform"
                                    style={{ backgroundColor: c }}
                                />
                            ))}
                            <button
                                type="button"
                                onClick={() => editor.chain().focus().unsetColor().run()}
                                className="h-5 w-5 rounded border border-slate-700 bg-slate-800 text-slate-400 flex items-center justify-center text-[10px] hover:bg-slate-700"
                                title="Clear"
                            >
                                ×
                            </button>
                        </div>
                    </DropdownMenuContent>
                </DropdownMenu>

                {/* Subscript / superscript */}
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleSubscript().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('subscript') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Subscript"
                >
                    <SubIcon className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleSuperscript().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('superscript') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Superscript"
                >
                    <SupIcon className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                {/* Text alignment */}
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().setTextAlign('left').run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive({ textAlign: 'left' }) ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Align left"
                >
                    <AlignLeft className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().setTextAlign('center').run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive({ textAlign: 'center' }) ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Align center"
                >
                    <AlignCenter className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().setTextAlign('right').run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive({ textAlign: 'right' }) ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Align right"
                >
                    <AlignRight className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().setTextAlign('justify').run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive({ textAlign: 'justify' }) ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Justify"
                >
                    <AlignJustify className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={openLinkDialog}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('link') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <LinkIcon className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleBulletList().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('bulletList') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <ListIcon className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleOrderedList().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('orderedList') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <ListOrdered className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleTaskList().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('taskList') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <CheckSquare className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleBlockquote().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('blockquote') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Quote className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().toggleCodeBlock().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('codeBlock') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <CodeXml className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                {/* Tables */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('table') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                            title="Table"
                        >
                            <TableIcon className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 text-slate-300">
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white"
                        >
                            <Plus className="h-3.5 w-3.5 mr-2" /> Insert table (3×3)
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().addColumnAfter().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white"
                        >
                            <Plus className="h-3.5 w-3.5 mr-2" /> Column after
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().deleteColumn().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white"
                        >
                            <Minus className="h-3.5 w-3.5 mr-2" /> Delete column
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().addRowAfter().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white"
                        >
                            <Plus className="h-3.5 w-3.5 mr-2" /> Row after
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().deleteRow().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white"
                        >
                            <Minus className="h-3.5 w-3.5 mr-2" /> Delete row
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().toggleHeaderRow().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white"
                        >
                            Toggle header row
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => editor.chain().focus().deleteTable().run()}
                            disabled={!editor.isActive('table')}
                            className="cursor-pointer focus:bg-slate-800 focus:text-white text-red-400"
                        >
                            <Trash2 className="h-3.5 w-3.5 mr-2" /> Delete table
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>

                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={openImageDialog}
                    className="h-8 w-8 text-slate-400 hover:text-white hover:bg-slate-800"
                >
                    <ImageIcon className="h-4 w-4" />
                </Button>
            </div>

            {/* Link Dialog */}
            <Dialog open={linkDialogOpen} onOpenChange={setLinkDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white">
                    <DialogHeader>
                        <DialogTitle>Insert Link</DialogTitle>
                        <DialogDescription className="text-slate-400">
                            Enter the URL for the link. Leave empty to remove the link.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="link-url" className="text-slate-300">URL</Label>
                            <Input
                                id="link-url"
                                placeholder="https://example.com"
                                value={linkUrl}
                                onChange={(e) => setLinkUrl(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        handleSetLink();
                                    }
                                }}
                                className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-500"
                                autoFocus
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setLinkDialogOpen(false)}
                            className="border-slate-700 text-slate-300 hover:bg-slate-800"
                        >
                            Cancel
                        </Button>
                        <Button
                            type="button"
                            onClick={handleSetLink}
                            className="bg-blue-600 hover:bg-blue-700"
                        >
                            {linkUrl ? 'Set Link' : 'Remove Link'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Image Dialog */}
            <Dialog open={imageDialogOpen} onOpenChange={setImageDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white">
                    <DialogHeader>
                        <DialogTitle>Insert Image</DialogTitle>
                        <DialogDescription className="text-slate-400">
                            Enter the URL of the image you want to insert.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="image-url" className="text-slate-300">Image URL</Label>
                            <Input
                                id="image-url"
                                placeholder="https://example.com/image.png"
                                value={imageUrl}
                                onChange={(e) => setImageUrl(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        handleSetImage();
                                    }
                                }}
                                className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-500"
                                autoFocus
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setImageDialogOpen(false)}
                            className="border-slate-700 text-slate-300 hover:bg-slate-800"
                        >
                            Cancel
                        </Button>
                        <Button
                            type="button"
                            onClick={handleSetImage}
                            disabled={!imageUrl}
                            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
                        >
                            Insert Image
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
};

/**
 * Upload a pasted/dropped image to the markdown-images endpoint and
 * insert an image node at the given position in the editor.
 *
 * The src is the same `/api/markdown-images/{id}` URL we'll persist into
 * the markdown text. The actual rendering goes through AuthImage (in the
 * preview) or the editor's own node-view, both of which fetch the bytes
 * with the user's JWT.
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
        const detail = apiErrorMessage(err, 'Failed to upload image');
        toast.error(detail);
    }
}

export default function TiptapEditor({ value, onChange, placeholder, disabled, minHeight = '300px', id, className, fieldContext, engagementId }: TiptapEditorProps) {
    const [, setForceUpdate] = useState(0);
    const currentUsername = useAuthStore((s) => s.user?.username);

    // Check if AI is enabled
    const { data: aiStatus } = useQuery<{ enabled: boolean; model: string; mcp_enabled: boolean; mcp_url: string }>({
        queryKey: ['ai', 'status'],
        queryFn: async () => {
            const resp = await api.get('/ai/settings/status');
            return resp.data;
        },
        staleTime: 60_000,
        retry: false,
    });
    const aiEnabled = aiStatus?.enabled && !!fieldContext;
    const mcpEnabled = aiStatus?.mcp_enabled;

    // AI chat state
    const [aiOpen, setAiOpen] = useState(false);
    const [aiMessages, setAiMessages] = useState<{ role: string; content: string }[]>([]);
    const [aiInput, setAiInput] = useState('');
    const [aiStreaming, setAiStreaming] = useState(false);
    const [mcpToolsOpen, setMcpToolsOpen] = useState(false);
    const [mcpLoading, setMcpLoading] = useState(false);
    const aiScrollRef = useRef<HTMLDivElement>(null);
    const aiInputRef = useRef<HTMLInputElement>(null);
    const editorRef = useRef<any>(null);

    const editor = useEditor({

        extensions: [
            StarterKit.configure({
                codeBlock: false, // We'll use CodeBlockLowlight instead
            }),
            CodeBlockLowlight.configure({
                lowlight,
                HTMLAttributes: {
                    class: 'hljs',
                },
            }),
            Markdown.configure({
                html: false,
                transformPastedText: true,
                transformCopiedText: true,
            }),
            Placeholder.configure({
                placeholder: placeholder || 'Start typing...',
            }),
            Link.configure({
                openOnClick: false,
                HTMLAttributes: {
                    class: 'text-blue-400 underline hover:text-blue-300 cursor-pointer',
                },
            }),
            Image,
            TaskList,
            TaskItem.configure({
                nested: true,
            }),
            Underline,
            Highlight.configure({ multicolor: true }),
            TextAlign.configure({
                types: ['heading', 'paragraph'],
            }),
            TextStyle,
            Color,
            Subscript,
            Superscript,
            Table.configure({
                resizable: true,
                HTMLAttributes: {
                    class: 'redwire-table',
                },
            }),
            TableRow,
            TableHeader,
            TableCell,
            Mention.configure({
                HTMLAttributes: {
                    class: 'mention',
                },
                suggestion: mentionSuggestion,
                renderText({ node }) {
                    return `@${node.attrs.label ?? node.attrs.id}`;
                },
            }).extend({
                addStorage() {
                    return {
                        markdown: {
                            serialize(state: any, node: any) {
                                state.write(`@${node.attrs.label ?? node.attrs.id}`);
                            },
                            parse: {
                                setup(markdownit: any) {
                                    // Add inline rule: match @username and emit a mention token
                                    markdownit.inline.ruler.push('mention', (state: any, silent: boolean) => {
                                        if (state.src.charAt(state.pos) !== '@') return false;

                                        const tail = state.src.slice(state.pos);
                                        const match = tail.match(/^@(\w+)/);
                                        if (!match) return false;

                                        if (!silent) {
                                            const token = state.push('mention', '', 0);
                                            token.content = match[1];
                                        }
                                        state.pos += match[0].length;
                                        return true;
                                    });

                                    // Render mention tokens as span elements with data attrs
                                    markdownit.renderer.rules.mention = (tokens: any[], idx: number) => {
                                        const username = tokens[idx].content;
                                        return `<span data-type="mention" data-id="${username}" data-label="${username}" class="mention">@${username}</span>`;
                                    };
                                },
                                updateDOM(element: HTMLElement) {
                                    return {
                                        id: element.getAttribute('data-id'),
                                        label: element.getAttribute('data-label'),
                                    };
                                },
                            },
                        },
                    };
                },
            }),
        ],
        content: value,
        editable: !disabled,
        immediatelyRender: false,
        onUpdate: ({ editor }) => {
            const markdown = (editor.storage as any).markdown.getMarkdown();
            onChange(markdown);
        },
        onSelectionUpdate: () => {
            // Force re-render of MenuBar when selection changes
            setForceUpdate(prev => prev + 1);
        },
        editorProps: {
            attributes: {
                class: 'prose prose-invert max-w-none focus:outline-hidden p-4 min-h-[inherit]',
            },
            // Drag-and-drop image upload. We swallow the drop event when files
            // are present, upload via /markdown-images, then insert nodes.
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
            // Paste handler (Cmd/Ctrl+V from screenshot tools, etc.)
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

    // Update editor content when value changes externally
    useEffect(() => {
        if (!editor) return;
        const currentMarkdown = (editor.storage as any).markdown.getMarkdown();
        // Only update if content is actually different (avoids cursor jumping from own edits)
        if (value !== currentMarkdown) {
            editor.commands.setContent(value);
        }
    }, [value, editor]);

    // Keep editorRef in sync
    editorRef.current = editor;

    // AI handlers (placed after editor is declared)
    const handleAiSend = useCallback(async () => {
        if (!aiInput.trim() || aiStreaming) return;
        const userMsg = { role: 'user', content: aiInput.trim() };
        const newMessages = [...aiMessages, userMsg];
        setAiMessages(newMessages);
        setAiInput('');
        setAiStreaming(true);

        // Get current editor content
        let editorContent = '';
        const ed = editorRef.current;
        if (ed) {
            editorContent = (ed.storage as any).markdown?.getMarkdown?.() || '';
        }

        try {
            const token = localStorage.getItem('access_token');
            const resp = await fetch(`${api.defaults.baseURL}/ai/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({
                    messages: newMessages,
                    editor_content: editorContent,
                    field_context: fieldContext,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                setAiMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.detail || resp.statusText}` }]);
                setAiStreaming(false);
                return;
            }

            const reader = resp.body?.getReader();
            const decoder = new TextDecoder();
            let assistantContent = '';
            setAiMessages(prev => [...prev, { role: 'assistant', content: '' }]);

            if (reader) {
                while (true) {
                    const { done, value: chunk } = await reader.read();
                    if (done) break;
                    const text = decoder.decode(chunk);
                    const lines = text.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.slice(6).trim();
                            if (data === '[DONE]') continue;
                            try {
                                const parsed = JSON.parse(data);
                                if (parsed.error) {
                                    assistantContent += `\nError: ${parsed.error}`;
                                } else {
                                    const delta = parsed.choices?.[0]?.delta?.content || '';
                                    assistantContent += delta;
                                }
                                setAiMessages(prev => {
                                    const updated = [...prev];
                                    updated[updated.length - 1] = { role: 'assistant', content: assistantContent };
                                    return updated;
                                });
                            } catch { /* skip unparseable lines */ }
                        }
                    }
                }
            }
        } catch (err: any) {
            setAiMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }]);
        }
        setAiStreaming(false);
    }, [aiInput, aiMessages, aiStreaming, fieldContext]);

    // Auto-scroll AI messages
    useEffect(() => {
        if (aiScrollRef.current) {
            aiScrollRef.current.scrollTop = aiScrollRef.current.scrollHeight;
        }
    }, [aiMessages]);

    const handleInsertAiResponse = useCallback((content: string) => {
        const ed = editorRef.current;
        if (!ed) return;
        ed.chain().focus().insertContent(content).run();
    }, []);

    // MCP tool call handler
    const callMcpTool = useCallback(async (toolName: string, args: Record<string, string> = {}) => {
        setMcpLoading(true);
        setMcpToolsOpen(false);
        setAiMessages(prev => [...prev, { role: 'user', content: `🔌 Querying: ${toolName}${Object.keys(args).length ? ` (${JSON.stringify(args)})` : ''}` }]);
        try {
            const resp = await api.post('/ai/mcp/call-tool', { tool_name: toolName, arguments: args });
            const resultText = JSON.stringify(resp.data.result, null, 2);
            setAiMessages(prev => [...prev, { role: 'assistant', content: `📊 **${toolName}** result:\n\`\`\`json\n${resultText}\n\`\`\`` }]);
        } catch (err: any) {
            const detail = apiErrorMessage(err) || err.message;
            setAiMessages(prev => [...prev, { role: 'assistant', content: `❌ Error: ${detail}` }]);
        }
        setMcpLoading(false);
    }, []);

    return (
        <div id={id} className={cn("flex flex-col border border-slate-800 rounded-lg overflow-hidden bg-slate-950/40", className)}>
            <MenuBar editor={editor} />
            <div
                className="overflow-y-auto"
                style={{ minHeight }}
                onClick={() => editor?.commands.focus()}
            >
                <EditorContent editor={editor} />
            </div>

            {/* AI Assistant overlay */}
            {aiEnabled && (
                <div className="border-t border-slate-800">
                    {!aiOpen ? (
                        /* Collapsed bar */
                        <button
                            type="button"
                            onClick={() => { setAiOpen(true); setTimeout(() => aiInputRef.current?.focus(), 100); }}
                            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-500 hover:text-violet-400 hover:bg-slate-900/50 transition-colors"
                        >
                            <Sparkles className="h-3.5 w-3.5" />
                            <span>Ask AI for help with this {fieldContext?.fieldName?.toLowerCase() || 'field'}...</span>
                        </button>
                    ) : (
                        /* Expanded AI chat */
                        <div className="bg-slate-950/60 backdrop-blur-sm">
                            {/* Header */}
                            <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-800/60">
                                <span className="text-[11px] font-semibold text-violet-400 flex items-center gap-1.5">
                                    <Sparkles className="h-3 w-3" /> AI Assistant
                                    {aiStatus?.model && <span className="text-slate-600 font-normal">· {aiStatus.model}</span>}
                                </span>
                                <div className="flex items-center gap-1">
                                    {aiMessages.length > 0 && (
                                        <button
                                            type="button"
                                            onClick={() => setAiMessages([])}
                                            className="text-[10px] text-slate-500 hover:text-slate-300 px-1.5 py-0.5 rounded hover:bg-slate-800 transition-colors"
                                        >
                                            Clear
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        onClick={() => setAiOpen(false)}
                                        className="text-slate-500 hover:text-slate-300 p-0.5 rounded hover:bg-slate-800 transition-colors"
                                    >
                                        <X className="h-3.5 w-3.5" />
                                    </button>
                                </div>
                            </div>

                            {/* Messages */}
                            {aiMessages.length > 0 && (
                                <div ref={aiScrollRef} className="max-h-[200px] overflow-y-auto px-3 py-2 space-y-2">
                                    {aiMessages.map((msg, i) => (
                                        <div key={i} className={cn(
                                            "text-xs rounded-lg px-3 py-2 max-w-[90%]",
                                            msg.role === 'user'
                                                ? 'bg-violet-500/10 text-violet-200 border border-violet-500/20 ml-auto'
                                                : 'bg-slate-800/60 text-slate-300 border border-slate-700/40'
                                        )}>
                                            <div className="whitespace-pre-wrap break-words">{msg.content || (aiStreaming && i === aiMessages.length - 1 ? '...' : '')}</div>
                                            {msg.role === 'assistant' && msg.content && !aiStreaming && (
                                                <button
                                                    type="button"
                                                    onClick={() => handleInsertAiResponse(msg.content)}
                                                    className="flex items-center gap-1 mt-1.5 text-[10px] text-violet-400 hover:text-violet-300 transition-colors"
                                                >
                                                    <ClipboardPaste className="h-3 w-3" /> Insert into editor
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Input */}
                            <div className="flex items-center gap-2 px-3 py-2">
                                {mcpEnabled && (
                                    <div className="relative">
                                        <button
                                            type="button"
                                            onClick={() => setMcpToolsOpen(!mcpToolsOpen)}
                                            disabled={mcpLoading}
                                            className="p-1.5 rounded-lg border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10 transition-colors disabled:opacity-30"
                                            title="Query data via MCP"
                                        >
                                            {mcpLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
                                        </button>
                                        {mcpToolsOpen && (
                                            <div className="absolute bottom-full left-0 mb-1 w-56 bg-slate-900 border border-slate-700 rounded-lg shadow-xl z-50 overflow-hidden">
                                                <div className="px-3 py-1.5 border-b border-slate-800">
                                                    <span className="text-[10px] font-semibold text-cyan-400">MCP Data Tools</span>
                                                </div>
                                                <div className="max-h-[200px] overflow-y-auto py-1">
                                                    {[
                                                        { name: 'list_engagements', label: 'List Engagements' },
                                                        { name: 'get_global_stats', label: 'Global Stats' },
                                                        { name: 'search', label: 'Search...', needsInput: true },
                                                    ].map(tool => (
                                                        <button
                                                            key={tool.name}
                                                            type="button"
                                                            onClick={() => {
                                                                if (tool.needsInput) {
                                                                    const q = prompt('Search query:');
                                                                    if (q) callMcpTool(tool.name, { query: q });
                                                                    else setMcpToolsOpen(false);
                                                                } else {
                                                                    callMcpTool(tool.name);
                                                                }
                                                            }}
                                                            className="w-full text-left px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition-colors flex items-center gap-2"
                                                        >
                                                            <Database className="h-3 w-3 text-cyan-400/60" />
                                                            {tool.label}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                                <input
                                    ref={aiInputRef}
                                    type="text"
                                    value={aiInput}
                                    onChange={(e) => setAiInput(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAiSend(); } }}
                                    placeholder={`Ask about ${fieldContext?.fieldName?.toLowerCase() || 'this field'}...`}
                                    disabled={aiStreaming}
                                    className="flex-1 bg-slate-900/60 border border-slate-700/50 rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-violet-500/50 transition-colors disabled:opacity-50"
                                />
                                <button
                                    type="button"
                                    onClick={handleAiSend}
                                    disabled={aiStreaming || !aiInput.trim()}
                                    className="p-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-30 disabled:hover:bg-violet-600 transition-colors"
                                >
                                    {aiStreaming ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}
            <style jsx global>{`
                .tiptap p.is-editor-empty:first-child::before {
                    color: #64748b;
                    content: attr(data-placeholder);
                    float: left;
                    height: 0;
                    pointer-events: none;
                }
                /* Headings */
                .tiptap h1 {
                    font-size: 1.75rem;
                    font-weight: 700;
                    color: #f1f5f9;
                    margin: 1rem 0 0.5rem;
                    line-height: 1.3;
                    border-bottom: 1px solid #1e293b;
                    padding-bottom: 0.375rem;
                }
                .tiptap h2 {
                    font-size: 1.375rem;
                    font-weight: 600;
                    color: #e2e8f0;
                    margin: 0.875rem 0 0.375rem;
                    line-height: 1.35;
                }
                .tiptap h3 {
                    font-size: 1.125rem;
                    font-weight: 600;
                    color: #cbd5e1;
                    margin: 0.75rem 0 0.25rem;
                    line-height: 1.4;
                }
                /* Task list / Checkboxes */
                .tiptap ul[data-type="taskList"] {
                    list-style: none;
                    padding: 0;
                }
                .tiptap ul[data-type="taskList"] li {
                    display: flex;
                    align-items: flex-start;
                    gap: 0.5rem;
                }
                .tiptap ul[data-type="taskList"] li > label {
                    flex: 0 0 auto;
                    user-select: none;
                    margin-top: 0.25rem;
                }
                .tiptap ul[data-type="taskList"] li > label input[type="checkbox"] {
                    appearance: none;
                    -webkit-appearance: none;
                    width: 1rem;
                    height: 1rem;
                    border: 2px solid #6366f1;
                    border-radius: 0.25rem;
                    background: transparent;
                    cursor: pointer;
                    position: relative;
                    vertical-align: middle;
                }
                .tiptap ul[data-type="taskList"] li > label input[type="checkbox"]:checked {
                    background: #6366f1;
                    border-color: #6366f1;
                }
                .tiptap ul[data-type="taskList"] li > label input[type="checkbox"]:checked::after {
                    content: '✓';
                    position: absolute;
                    top: -2px;
                    left: 1px;
                    color: white;
                    font-size: 0.75rem;
                    font-weight: bold;
                }
                .tiptap ul[data-type="taskList"] li > div {
                    flex: 1 1 auto;
                }
                .tiptap img {
                    max-width: 100%;
                    height: auto;
                    border-radius: 0.5rem;
                }
                .tiptap ul {
                    list-style-type: disc;
                    padding-left: 1.5rem;
                    margin: 0.5rem 0;
                }
                .tiptap ol {
                    list-style-type: decimal;
                    padding-left: 1.5rem;
                    margin: 0.5rem 0;
                }
                .tiptap ul li, .tiptap ol li {
                    margin: 0.25rem 0;
                }
                .tiptap ul li::marker {
                    color: #94a3b8;
                }
                .tiptap ol li::marker {
                    color: #94a3b8;
                }
                .tiptap blockquote {
                    border-left: 3px solid #6366f1;
                    padding-left: 1rem;
                    margin: 0.75rem 0;
                    color: #94a3b8;
                    background: rgba(99, 102, 241, 0.05);
                    border-radius: 0 0.375rem 0.375rem 0;
                    padding: 0.5rem 1rem;
                }
                .tiptap code:not(pre code) {
                    background: rgba(99, 102, 241, 0.15);
                    border: 1px solid rgba(99, 102, 241, 0.25);
                    border-radius: 0.25rem;
                    padding: 0.125rem 0.375rem;
                    font-size: 0.85em;
                    font-family: 'JetBrains Mono', monospace;
                    color: #c4b5fd;
                }
                
                /* Atom One Dark — code blocks */
                .tiptap pre {
                    background: #282c34;
                    border: 1px solid #3e4451;
                    border-radius: 0.5rem;
                    color: #abb2bf;
                    font-family: 'JetBrains Mono', monospace;
                    padding: 0.75rem 1rem;
                    overflow-x: auto;
                }
                .tiptap pre code {
                    background: none;
                    color: inherit;
                    font-size: 0.875rem;
                    padding: 0;
                }

                /* Atom One Dark — lowlight (highlight.js) syntax tokens */
                .tiptap .hljs-comment,
                .tiptap .hljs-quote {
                    color: #5c6370;
                    font-style: italic;
                }
                .tiptap .hljs-doctag,
                .tiptap .hljs-keyword,
                .tiptap .hljs-formula {
                    color: #c678dd;
                }
                .tiptap .hljs-section,
                .tiptap .hljs-name,
                .tiptap .hljs-selector-tag,
                .tiptap .hljs-deletion,
                .tiptap .hljs-subst {
                    color: #e06c75;
                }
                .tiptap .hljs-literal {
                    color: #56b6c2;
                }
                .tiptap .hljs-string,
                .tiptap .hljs-regexp,
                .tiptap .hljs-addition,
                .tiptap .hljs-attribute,
                .tiptap .hljs-meta .hljs-string {
                    color: #98c379;
                }
                .tiptap .hljs-attr,
                .tiptap .hljs-variable,
                .tiptap .hljs-template-variable,
                .tiptap .hljs-type,
                .tiptap .hljs-selector-class,
                .tiptap .hljs-selector-attr,
                .tiptap .hljs-selector-pseudo,
                .tiptap .hljs-number {
                    color: #d19a66;
                }
                .tiptap .hljs-symbol,
                .tiptap .hljs-bullet,
                .tiptap .hljs-link,
                .tiptap .hljs-meta,
                .tiptap .hljs-selector-id,
                .tiptap .hljs-title {
                    color: #61afef;
                }
                .tiptap .hljs-built_in,
                .tiptap .hljs-title.class_,
                .tiptap .hljs-class .hljs-title {
                    color: #e5c07b;
                }
                .tiptap .hljs-emphasis {
                    font-style: italic;
                }
                .tiptap .hljs-strong {
                    font-weight: 700;
                }
                .tiptap .hljs-link {
                    text-decoration: underline;
                }
                /* Mention chips */
                .tiptap .mention {
                    background: rgba(20, 184, 166, 0.15);
                    border: 1px solid rgba(20, 184, 166, 0.3);
                    border-radius: 0.375rem;
                    padding: 0.125rem 0.375rem;
                    color: #2dd4bf;
                    font-weight: 500;
                    font-size: 0.9em;
                    white-space: nowrap;
                    cursor: default;
                }
                ${currentUsername ? `
                .tiptap .mention[data-label="${currentUsername}"] {
                    background: rgba(245, 158, 11, 0.15);
                    border-color: rgba(245, 158, 11, 0.3);
                    color: #fbbf24;
                }
                ` : ''}
            `}</style>
        </div>
    );
}

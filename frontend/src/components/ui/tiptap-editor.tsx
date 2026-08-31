'use client';

import { useEditor, EditorContent, ReactRenderer } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import Placeholder from '@tiptap/extension-placeholder';
import Link from '@tiptap/extension-link';
import { AuthAwareImage as Image } from './auth-image-node-view';
import { EditorStyles } from './editor-styles';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { Mermaid } from './mermaid-extension';
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
    Table as TableIcon, Trash2, Plus, Minus, Workflow, TextSelect, ListChecks, ChevronsUpDown,
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
import { EditorFieldContext } from '@/lib/types';
import { ChatMarkdownStyles } from './chat-markdown';
import { AiAssistantPanel } from './ai-assistant-panel';

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
    fieldContext?: EditorFieldContext;
    /** When provided, paste/drop of image files uploads them via
     *  POST /markdown-images and inserts the resulting URL.
     *  Without it the toolbar image-by-URL dialog still works. */
    engagementId?: string;
    /** Fixed-height, user-resizable mode: a corner handle drags the whole
     *  editor taller/shorter, and (when the AI panel is open) an inner handle
     *  rebalances the split between the text area and the AI panel without
     *  changing the total height. Used by the inline editor. */
    resizable?: boolean;
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

    // Clicking the link button while a link is active removes it (toggle off).
    const toggleLink = () => {
        if (editor.isActive('link')) {
            editor.chain().focus().extendMarkRange('link').unsetLink().run();
        } else {
            openLinkDialog();
        }
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
                    title="Undo"
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
                    title="Redo"
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
                            title="Heading / paragraph"
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
                    title="Bold (Ctrl+B)"
                    onClick={() => editor.chain().focus().toggleBold().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('bold') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Bold className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Italic (Ctrl+I)"
                    onClick={() => editor.chain().focus().toggleItalic().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('italic') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Italic className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Underline (Ctrl+U)"
                    onClick={() => editor.chain().focus().toggleUnderline().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('underline') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <UnderlineIcon className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Strikethrough"
                    onClick={() => editor.chain().focus().toggleStrike().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('strike') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Strikethrough className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Inline code"
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
                    title="Insert / edit link"
                    onClick={toggleLink}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('link') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <LinkIcon className="h-4 w-4" />
                </Button>

                <Separator orientation="vertical" className="h-6 bg-slate-700 mx-1" />

                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Bullet list"
                    onClick={() => editor.chain().focus().toggleBulletList().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('bulletList') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <ListIcon className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Numbered list"
                    onClick={() => editor.chain().focus().toggleOrderedList().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('orderedList') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <ListOrdered className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Task list"
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
                    title="Blockquote"
                    onClick={() => editor.chain().focus().toggleBlockquote().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('blockquote') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <Quote className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Code block"
                    onClick={() => editor.chain().focus().toggleCodeBlock().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('codeBlock') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                >
                    <CodeXml className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => editor.chain().focus().insertMermaid().run()}
                    className={cn("h-8 w-8 hover:bg-slate-800", editor.isActive('mermaid') ? 'text-blue-400 bg-slate-800' : 'text-slate-400')}
                    title="Insert Mermaid diagram"
                >
                    <Workflow className="h-4 w-4" />
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
                    title="Insert image"
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

/** True when `text` is a single, whitespace-free http/https/mailto URL — the
 *  shape we treat as "paste a link over the selection" rather than plain text. */
function isLikelyUrl(text: string): boolean {
    const t = text.trim();
    if (!t || /\s/.test(t)) return false;
    try {
        const u = new URL(t);
        return u.protocol === 'http:' || u.protocol === 'https:' || u.protocol === 'mailto:';
    } catch {
        return false;
    }
}

/** Seed the resizable editor's starting height from the caller's minHeight
 *  (e.g. "400px" → 400) so each editor opens at its intended size; falls back
 *  to a sensible default for non-px values like "min(75vh, 720px)". */
function parseInitialEditorHeight(minHeight?: string): number {
    const m = minHeight ? /^(\d+)px$/.exec(minHeight.trim()) : null;
    return m ? Math.max(220, parseInt(m[1], 10)) : 360;
}

export default function TiptapEditor({ value, onChange, placeholder, disabled, minHeight = '300px', id, className, fieldContext, engagementId, resizable = true }: TiptapEditorProps) {
    const [, setForceUpdate] = useState(0);
    const currentUsername = useAuthStore((s) => s.user?.username);

    // Whole-editor height (corner resize handle). The AI assistant docked below
    // owns its own split. Seeded from minHeight so each editor opens at its
    // intended size; only applied when `resizable`.
    const [editorHeight, setEditorHeight] = useState(() => parseInitialEditorHeight(minHeight));
    const editorHeightRef = useRef(parseInitialEditorHeight(minHeight));
    useEffect(() => { editorHeightRef.current = editorHeight; }, [editorHeight]);
    const dragRef = useRef<{ startY: number; startH: number } | null>(null);
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
            Mermaid,
            Markdown.configure({
                html: false,
                transformPastedText: true,
                transformCopiedText: true,
            }),
            Placeholder.configure({
                placeholder: placeholder || 'Start typing...',
            }),
            Link.extend({ inclusive: false }).configure({
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
            // Force re-render of MenuBar when selection changes. (The AI panel
            // tracks the selection itself via editor.on('selectionUpdate').)
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
                // Paste a URL over highlighted text → turn the selection into a
                // hyperlink pointing at the pasted URL (instead of replacing it).
                const pastedText = (event as ClipboardEvent).clipboardData?.getData('text/plain') ?? '';
                const { from, to, empty } = view.state.selection;
                const linkMark = view.state.schema.marks.link;
                if (!empty && linkMark && isLikelyUrl(pastedText)) {
                    event.preventDefault();
                    const tr = view.state.tr.addMark(from, to, linkMark.create({ href: pastedText.trim() }));
                    view.dispatch(tr.setMeta('preventAutolink', true));
                    return true;
                }

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

    // Corner resize: drag the whole editor taller/shorter.
    const onResizeMove = useCallback((e: MouseEvent) => {
        const d = dragRef.current;
        if (!d) return;
        const dy = e.clientY - d.startY; // drag down = taller
        setEditorHeight(Math.max(260, Math.min(1100, d.startH + dy)));
    }, []);
    const onResizeEnd = useCallback(() => {
        dragRef.current = null;
        window.removeEventListener('mousemove', onResizeMove);
        window.removeEventListener('mouseup', onResizeEnd);
        document.body.style.userSelect = '';
    }, [onResizeMove]);
    const startResize = useCallback((e: React.MouseEvent) => {
        dragRef.current = { startY: e.clientY, startH: editorHeightRef.current };
        window.addEventListener('mousemove', onResizeMove);
        window.addEventListener('mouseup', onResizeEnd);
        document.body.style.userSelect = 'none';
        e.preventDefault();
        e.stopPropagation();
    }, [onResizeMove, onResizeEnd]);

    return (
        <div
            id={id}
            className={cn("flex flex-col border border-slate-800 rounded-lg overflow-hidden bg-slate-950/40", className)}
            style={resizable ? { height: editorHeight } : undefined}
        >
            <MenuBar editor={editor} />
            <div
                className={cn("overflow-y-auto", resizable && "flex-1 min-h-0")}
                style={resizable ? undefined : { minHeight }}
                onClick={() => editor?.commands.focus()}
            >
                <EditorContent editor={editor} />
            </div>

            {/* AI assistant (shared with the collaborative editor). Docks below
                the content; owns its own split. */}
            <AiAssistantPanel
                editor={editor}
                fieldContext={fieldContext}
                maxHeight={resizable ? editorHeight - 150 : undefined}
            />

            {/* Corner grab handle: drag to resize the whole editor vertically. */}
            {resizable && (
                <div
                    onMouseDown={startResize}
                    title="Drag to resize the editor"
                    className="group/edrag h-3.5 shrink-0 border-t border-slate-800/60 flex items-center justify-end px-1.5 cursor-ns-resize hover:bg-slate-800/40 transition-colors"
                >
                    <ChevronsUpDown className="h-3 w-3 text-slate-600 group-hover/edrag:text-slate-400" />
                </div>
            )}
            <EditorStyles currentUsername={currentUsername} />
            <ChatMarkdownStyles />
        </div>
    );
}

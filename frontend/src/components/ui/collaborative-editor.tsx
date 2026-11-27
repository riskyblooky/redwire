'use client';

import TiptapEditor from './tiptap-editor';
import { cn } from '@/lib/utils';

interface CollaborativeEditorProps {
    noteId: string;
    disabled?: boolean;
    placeholder?: string;
    className?: string;
    /** Required for paste/drop image upload. */
    engagementId?: string;
    /** The note's last-known content (from the list query). Shown read-only
     *  while the live editor connects so the note isn't blank. */
    initialPreview?: string;
}

const ignore = () => {};

/**
 * The Notes editor: the shared TiptapEditor in a live note room. It fills its
 * container, adds the timestamp controls, answers the room's server-side save
 * requests, and hides the AI assistant from read-only viewers (who can't
 * insert its output). The room's doc is the source of truth, so the content
 * is never read back through onChange. Mount with key={noteId}: the room is
 * fixed at mount.
 */
export default function CollaborativeEditor({
    noteId,
    disabled = false,
    placeholder = 'Start writing your notes...',
    className,
    engagementId,
    initialPreview,
}: CollaborativeEditorProps) {
    return (
        <TiptapEditor
            value={initialPreview ?? ''}
            onChange={ignore}
            placeholder={placeholder}
            disabled={disabled}
            className={cn('h-full', className)}
            engagementId={engagementId}
            fieldContext={{ resourceType: 'note', fieldName: 'note' }}
            resizable={false}
            fillHeight
            timestamps
            aiPanel={!disabled}
            collab={{ path: `note/${noteId}`, answerSaveRequests: true }}
        />
    );
}

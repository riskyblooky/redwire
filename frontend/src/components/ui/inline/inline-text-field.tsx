'use client';

import { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface InlineTextFieldProps {
    value: string;
    onSave: (value: string) => Promise<void>;
    canEdit?: boolean;
    /** Applied to both the read text and the input, so the input inherits the
     *  same typography (e.g. the page title's size/weight). */
    className?: string;
    placeholder?: string;
    /** Reject an empty value (keeps editing + toasts). Default true. */
    required?: boolean;
}

/**
 * A single-line text field that reads as plain text and, on double-click (for
 * editors), swaps to an inline input. Enter or blur saves, Esc cancels.
 */
export function InlineTextField({
    value,
    onSave,
    canEdit = false,
    className,
    placeholder = 'Untitled',
    required = true,
}: InlineTextFieldProps) {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState('');
    const [saving, setSaving] = useState(false);
    const committedRef = useRef(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (editing) inputRef.current?.select();
    }, [editing]);

    const start = () => {
        if (!canEdit || saving) return;
        setDraft(value || '');
        committedRef.current = false;
        setEditing(true);
    };

    const cancel = () => { committedRef.current = true; setEditing(false); };

    const save = async () => {
        if (committedRef.current) return;      // guard against Enter + blur double-fire
        const next = draft.trim();
        if (required && !next) { toast.error('This field can’t be empty'); inputRef.current?.focus(); return; }
        committedRef.current = true;
        if (next === (value || '')) { setEditing(false); return; }
        setSaving(true);
        try {
            await onSave(next);
            setEditing(false);
        } catch (e: any) {
            toast.error(e?.response?.data?.detail || e?.message || 'Failed to save');
            committedRef.current = false;      // let them retry
            setEditing(true);
        } finally {
            setSaving(false);
        }
    };

    const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') { e.preventDefault(); save(); }
        else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    };

    if (editing) {
        return (
            <input
                ref={inputRef}
                autoFocus
                value={draft}
                disabled={saving}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={onKeyDown}
                onBlur={save}
                placeholder={placeholder}
                className={cn(
                    'bg-transparent border-b border-slate-600 focus:border-primary outline-none px-0 w-full max-w-full',
                    className,
                )}
            />
        );
    }

    return (
        <span className="group/inline relative inline-flex items-center gap-2 min-w-0">
            <span
                className={cn(className, canEdit && 'cursor-text')}
                onDoubleClick={start}
                title={canEdit ? 'Double-click to edit' : undefined}
            >
                {value || <span className="text-slate-600 italic">{placeholder}</span>}
            </span>
            {canEdit && (
                <button
                    type="button"
                    onClick={start}
                    className="p-0.5 rounded opacity-0 group-hover/inline:opacity-100 text-slate-500 hover:text-white transition-opacity shrink-0"
                    title="Edit"
                    aria-label="Edit"
                >
                    <Pencil className="h-4 w-4" />
                </button>
            )}
        </span>
    );
}

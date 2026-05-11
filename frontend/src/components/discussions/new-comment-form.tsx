'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { MarkdownEditor } from '@/components/ui/markdown-editor';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Send } from 'lucide-react';
import { useCreateComment } from '@/lib/hooks/use-discussions';

interface NewCommentFormProps {
    threadId: string;
    onSuccess?: () => void;
}

export default function NewCommentForm({ threadId, onSuccess }: NewCommentFormProps) {
    const [content, setContent] = useState('');
    const createComment = useCreateComment();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!content.trim()) return;

        try {
            await createComment.mutateAsync({
                thread_id: threadId,
                content: content.trim(),
                is_resolvable: false,
            });

            setContent('');
            onSuccess?.();
        } catch (error) {
            console.error('Failed to create comment:', error);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-2 min-h-[150px]">
                <MarkdownEditor
                    value={content}
                    onChange={(val) => setContent(val)}
                    placeholder="Write a comment..."
                    minHeight="150px"
                />
            </div>

            <div className="flex items-center justify-end">
                <Button
                    type="submit"
                    size="sm"
                    disabled={!content.trim() || createComment.isPending}
                    className="bg-primary hover:bg-primary/90"
                >
                    {createComment.isPending ? (
                        'Posting...'
                    ) : (
                        <>
                            <Send className="h-4 w-4 mr-2" />
                            Comment
                        </>
                    )}
                </Button>
            </div>
        </form>
    );
}

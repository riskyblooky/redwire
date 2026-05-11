'use client';

import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus } from 'lucide-react';
import { useCreateThread, ResourceType } from '@/lib/hooks/use-discussions';

interface NewThreadDialogProps {
    engagementId: string;
    resourceType: ResourceType;
    resourceId?: string;
    onSuccess?: () => void;
}

export default function NewThreadDialog({ engagementId, resourceType, resourceId, onSuccess }: NewThreadDialogProps) {
    const [open, setOpen] = useState(false);
    const [title, setTitle] = useState('');
    const createThread = useCreateThread();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!title.trim()) return;

        try {
            await createThread.mutateAsync({
                engagement_id: engagementId,
                resource_type: resourceType,
                resource_id: resourceId || null,
                title: title.trim(),
            });

            setTitle('');
            setOpen(false);
            onSuccess?.();
        } catch (error) {
            console.error('Failed to create thread:', error);
        }
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button size="sm" className="bg-primary hover:bg-primary/90">
                    <Plus className="h-4 w-4 mr-2" />
                    New Discussion
                </Button>
            </DialogTrigger>
            <DialogContent className="bg-slate-900 border-slate-800">
                <form onSubmit={handleSubmit}>
                    <DialogHeader>
                        <DialogTitle className="text-white">Start a New Discussion</DialogTitle>
                        <DialogDescription className="text-slate-400">
                            Create a thread to discuss this {
                                ({ finding_remediation: 'finding remediation', cleanup_artifact: 'cleanup' } as Record<string, string>)[resourceType] || resourceType
                            } with your team.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="thread-title" className="text-slate-200">
                                Thread Title
                            </Label>
                            <Input
                                id="thread-title"
                                value={title}
                                onChange={(e) => setTitle(e.target.value)}
                                placeholder="e.g., Verify CVSS score"
                                className="bg-slate-800 border-slate-700 text-white"
                                required
                                autoFocus
                            />
                        </div>
                    </div>

                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setOpen(false)}
                            className="border-slate-700 text-slate-300"
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            disabled={!title.trim() || createThread.isPending}
                            className="bg-primary hover:bg-primary/90"
                        >
                            {createThread.isPending ? 'Creating...' : 'Create Thread'}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

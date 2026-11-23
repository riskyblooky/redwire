'use client';

// Quick-create dialogs opened from a finding, test case or asset row on the
// engagement page: create a vault item / cleanup artifact and link it to
// that row in one step.

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Key, Loader2, Lock, Shield, Sparkles } from 'lucide-react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { getErrorMessage } from '@/components/ui/confirm-dialog';
import { useLinkVaultToFinding, useLinkVaultToTestCase, useLinkVaultToAsset } from '@/lib/hooks/use-vault';
import {
    useCreateCleanupArtifact, useLinkCleanupToFinding, useLinkCleanupToTestCase, useLinkCleanupToAsset,
    type CleanupArtifact,
} from '@/lib/hooks/use-cleanup-artifacts';

/** The row the new item is linked to. */
export interface QuickLinkTarget {
    type: 'finding' | 'testcase' | 'asset';
    id: string;
    name: string;
}

interface QuickCreateDialogProps {
    engagementId: string;
    target: QuickLinkTarget | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

const targetLabel = (t: QuickLinkTarget) => (t.type === 'testcase' ? 'test case' : t.type);

const EMPTY_VAULT_ITEM = { name: '', item_type: 'CREDENTIAL' as string, username: '', password: '', note: '', description: '' };

export function QuickCreateVaultDialog({ engagementId, target, open, onOpenChange }: QuickCreateDialogProps) {
    const queryClient = useQueryClient();
    const linkVaultToFinding = useLinkVaultToFinding();
    const linkVaultToTestCase = useLinkVaultToTestCase();
    const linkVaultToAsset = useLinkVaultToAsset();
    const [item, setItem] = useState(EMPTY_VAULT_ITEM);
    const [isCreating, setIsCreating] = useState(false);

    // A fresh form each time the dialog opens.
    useEffect(() => { if (open) setItem(EMPTY_VAULT_ITEM); }, [open]);

    const handleCreate = async () => {
        if (!target || !item.name) return;
        setIsCreating(true);
        try {
            const res = await api.post('/vault', { ...item, engagement_id: engagementId });
            const createdId = res.data.id;
            if (target.type === 'finding') {
                await linkVaultToFinding.mutateAsync({ vaultItemId: createdId, findingId: target.id });
            } else if (target.type === 'testcase') {
                await linkVaultToTestCase.mutateAsync({ vaultItemId: createdId, testcaseId: target.id });
            } else {
                await linkVaultToAsset.mutateAsync({ vaultItemId: createdId, assetId: target.id });
            }
            toast.success(`Vault item created and linked to ${targetLabel(target)}`);
            onOpenChange(false);
            queryClient.invalidateQueries({ queryKey: ['engagements', engagementId, 'vault'] });
            queryClient.invalidateQueries({ queryKey: ['engagements', engagementId, 'counts'] });
        } catch (error: unknown) {
            toast.error(getErrorMessage(error, 'Failed to create vault item'));
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[480px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Lock className="h-5 w-5 text-amber-400" />
                        Create & Link Vault Item
                    </DialogTitle>
                    <DialogDescription className="text-slate-400">
                        Create a new vault item linked to <span className="text-white font-semibold">{target?.name}</span>
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-2">
                    <div className="space-y-2">
                        <Label>Name</Label>
                        <Input
                            value={item.name}
                            onChange={(e) => setItem(p => ({ ...p, name: e.target.value }))}
                            placeholder="e.g. Admin Credentials"
                            className="bg-slate-950 border-slate-700 text-white"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Type</Label>
                        <Select value={item.item_type} onValueChange={(v) => setItem(p => ({ ...p, item_type: v }))}>
                            <SelectTrigger className="bg-slate-950 border-slate-700 text-white">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-700 text-white">
                                <SelectItem value="CREDENTIAL"><div className="flex items-center gap-2"><Lock className="h-3.5 w-3.5 text-amber-400" /> Credential</div></SelectItem>
                                <SelectItem value="KEY"><div className="flex items-center gap-2"><Key className="h-3.5 w-3.5 text-primary" /> API Key / Token</div></SelectItem>
                                <SelectItem value="NOTE"><div className="flex items-center gap-2"><Shield className="h-3.5 w-3.5 text-emerald-400" /> Secure Note</div></SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    {item.item_type === 'CREDENTIAL' && (
                        <>
                            <div className="space-y-2">
                                <Label>Username</Label>
                                <Input
                                    value={item.username}
                                    onChange={(e) => setItem(p => ({ ...p, username: e.target.value }))}
                                    placeholder="admin"
                                    className="bg-slate-950 border-slate-700 text-white"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Password</Label>
                                <Input
                                    type="password"
                                    value={item.password}
                                    onChange={(e) => setItem(p => ({ ...p, password: e.target.value }))}
                                    placeholder="••••••••"
                                    className="bg-slate-950 border-slate-700 text-white"
                                />
                            </div>
                        </>
                    )}
                    {(item.item_type === 'KEY' || item.item_type === 'NOTE') && (
                        <div className="space-y-2">
                            <Label>{item.item_type === 'KEY' ? 'Key / Token' : 'Note Content'}</Label>
                            <Textarea
                                value={item.note}
                                onChange={(e) => setItem(p => ({ ...p, note: e.target.value }))}
                                placeholder={item.item_type === 'KEY' ? 'Paste API key or token...' : 'Enter secure note...'}
                                className="bg-slate-950 border-slate-700 text-white font-mono text-xs"
                                rows={3}
                            />
                        </div>
                    )}
                    <div className="space-y-2">
                        <Label>Description (optional)</Label>
                        <Textarea
                            value={item.description}
                            onChange={(e) => setItem(p => ({ ...p, description: e.target.value }))}
                            placeholder="Brief description..."
                            className="bg-slate-950 border-slate-700 text-white text-xs"
                            rows={2}
                        />
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button
                        onClick={handleCreate}
                        disabled={!item.name || isCreating}
                        className="bg-amber-600 hover:bg-amber-500 text-white"
                    >
                        {isCreating ? (
                            <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Creating...</>
                        ) : (
                            <><Lock className="h-4 w-4 mr-2" /> Create & Link</>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

const EMPTY_CLEANUP_ITEM = { title: '', artifact_type: 'SSH_KEY' as string, location: '', description: '' };

export function QuickCreateCleanupDialog({ engagementId, target, open, onOpenChange }: QuickCreateDialogProps) {
    const createCleanupArtifact = useCreateCleanupArtifact();
    const linkCleanupToFinding = useLinkCleanupToFinding();
    const linkCleanupToTestCase = useLinkCleanupToTestCase();
    const linkCleanupToAsset = useLinkCleanupToAsset();
    const [item, setItem] = useState(EMPTY_CLEANUP_ITEM);
    const [isCreating, setIsCreating] = useState(false);

    useEffect(() => { if (open) setItem(EMPTY_CLEANUP_ITEM); }, [open]);

    const handleCreate = async () => {
        if (!target || !item.title) return;
        setIsCreating(true);
        try {
            const created = await createCleanupArtifact.mutateAsync({
                engagement_id: engagementId,
                title: item.title,
                artifact_type: item.artifact_type as CleanupArtifact['artifact_type'],
                status: 'PENDING',
                location: item.location || undefined,
                description: item.description || undefined,
            } as Parameters<typeof createCleanupArtifact.mutateAsync>[0]);
            if (target.type === 'finding') {
                await linkCleanupToFinding.mutateAsync({ artifactId: created.id, findingId: target.id });
            } else if (target.type === 'testcase') {
                await linkCleanupToTestCase.mutateAsync({ artifactId: created.id, testcaseId: target.id });
            } else {
                await linkCleanupToAsset.mutateAsync({ artifactId: created.id, assetId: target.id });
            }
            toast.success(`Cleanup artifact created and linked to ${targetLabel(target)}`);
            onOpenChange(false);
        } catch (error: unknown) {
            toast.error(getErrorMessage(error, 'Failed to create cleanup artifact'));
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-lime-400" />
                        Quick Add Cleanup Artifact
                    </DialogTitle>
                    <DialogDescription className="text-slate-400">
                        Create a cleanup item and link it to{' '}
                        <span className="text-white font-semibold">{target?.name}</span>
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 pt-2">
                    <div>
                        <label className="text-xs font-medium text-slate-400 block mb-1.5">Title *</label>
                        <Input
                            placeholder="e.g. Remove SSH key from target"
                            value={item.title}
                            onChange={(e) => setItem({ ...item, title: e.target.value })}
                            className="bg-slate-800/50 border-slate-700 text-white"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-400 block mb-1.5">Type</label>
                        <Select
                            value={item.artifact_type}
                            onValueChange={(v) => setItem({ ...item, artifact_type: v })}
                        >
                            <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-800 border-slate-700">
                                <SelectItem value="SSH_KEY">SSH Key</SelectItem>
                                <SelectItem value="FILE">File</SelectItem>
                                <SelectItem value="ACCOUNT">Account</SelectItem>
                                <SelectItem value="PERMISSION">Permission</SelectItem>
                                <SelectItem value="BACKDOOR">Backdoor</SelectItem>
                                <SelectItem value="IMPLANT">Implant</SelectItem>
                                <SelectItem value="OTHER">Other</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-400 block mb-1.5">Location</label>
                        <Input
                            placeholder="e.g. /home/user/.ssh/authorized_keys"
                            value={item.location}
                            onChange={(e) => setItem({ ...item, location: e.target.value })}
                            className="bg-slate-800/50 border-slate-700 text-white"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-400 block mb-1.5">Description</label>
                        <Textarea
                            placeholder="Brief description of the artifact..."
                            value={item.description}
                            onChange={(e) => setItem({ ...item, description: e.target.value })}
                            className="bg-slate-800/50 border-slate-700 text-white h-20 resize-none"
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={isCreating}>Cancel</Button>
                    <Button
                        className="bg-lime-600 hover:bg-lime-500 text-white"
                        onClick={handleCreate}
                        disabled={!item.title || isCreating}
                    >
                        {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create & Link'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { RegistrationCode } from '@/lib/types';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from '@/components/ui/table';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Loader2, Plus, Trash2, Copy, Check, Users } from 'lucide-react';
import { toast } from 'sonner';

interface CodeUser {
    id: string;
    username: string;
    email: string;
    full_name?: string;
    created_at: string;
}

export function RegistrationCodeManagement() {
    const queryClient = useQueryClient();
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    // The code value is now generated server-side with a CSPRNG
    // (GHSA-gc2q-wm5m-59xm). The client only chooses label and max_uses.
    const [newLabel, setNewLabel] = useState('');
    const [maxUses, setMaxUses] = useState(1);
    const [copiedId, setCopiedId] = useState<string | null>(null);
    const [usersDialogCodeId, setUsersDialogCodeId] = useState<string | null>(null);
    const [usersDialogCodeLabel, setUsersDialogCodeLabel] = useState('');

    const { data: codes = [], isLoading } = useQuery({
        queryKey: ['registration-codes'],
        queryFn: async () => {
            const response = await api.get<RegistrationCode[]>('/admin/registration-codes');
            return response.data;
        }
    });

    const { data: codeUsers = [], isLoading: isLoadingUsers } = useQuery({
        queryKey: ['registration-code-users', usersDialogCodeId],
        queryFn: async () => {
            const response = await api.get<CodeUser[]>(`/admin/registration-codes/${usersDialogCodeId}/users`);
            return response.data;
        },
        enabled: !!usersDialogCodeId,
    });

    const createMutation = useMutation({
        mutationFn: async (data: { label?: string; max_uses: number }) => {
            const response = await api.post<RegistrationCode>('/admin/registration-codes', data);
            return response.data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['registration-codes'] });
            setIsCreateOpen(false);
            setNewLabel('');
            setMaxUses(1);
            toast.success(`Registration code created: ${data.code}`);
        },
        onError: () => {
            toast.error('Failed to create code.');
        }
    });

    const toggleMutation = useMutation({
        mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) => {
            const response = await api.patch<RegistrationCode>(`/admin/registration-codes/${id}`, { is_active });
            return response.data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['registration-codes'] });
            toast.success(data.is_active ? 'Code enabled' : 'Code disabled');
        },
        onError: () => {
            toast.error('Failed to update code');
        }
    });

    const deleteMutation = useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/admin/registration-codes/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['registration-codes'] });
            toast.success('Registration code deleted');
        },
        onError: () => {
            toast.error('Failed to delete code');
        }
    });

    const handleCreate = () => {
        createMutation.mutate({ label: newLabel || undefined, max_uses: maxUses });
    };

    const copyToClipboard = (text: string, id: string) => {
        navigator.clipboard.writeText(text);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
        toast.success('Code copied to clipboard');
    };

    const getStatusInfo = (code: RegistrationCode) => {
        if (!code.is_active) return { label: 'Disabled', className: 'bg-red-500/10 text-red-400 border-red-500/20' };
        if (code.used_count >= code.max_uses) return { label: 'Exhausted', className: 'bg-slate-700 text-slate-400' };
        return { label: 'Active', className: 'bg-green-500/10 text-green-400 border-green-500/20' };
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="flex flex-row items-center justify-between">
                <div>
                    <CardTitle>Registration Codes</CardTitle>
                    <CardDescription>Manage invite codes for new user registration</CardDescription>
                </div>
                <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
                    <DialogTrigger asChild>
                        <Button>
                            <Plus className="mr-2 h-4 w-4" />
                            Generate Code
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="bg-slate-900 border-slate-800">
                        <DialogHeader>
                            <DialogTitle>Create Registration Code</DialogTitle>
                            <DialogDescription>
                                A secure code will be generated on save.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="grid gap-4 py-4">
                            <div className="grid grid-cols-4 items-center gap-4">
                                <Label htmlFor="label" className="text-right">Label</Label>
                                <Input
                                    id="label"
                                    value={newLabel}
                                    onChange={(e) => setNewLabel(e.target.value)}
                                    placeholder="e.g. Client onboarding, Beta testers..."
                                    className="col-span-3 bg-slate-800 border-slate-700"
                                />
                            </div>
                            <div className="grid grid-cols-4 items-center gap-4">
                                <Label htmlFor="maxUses" className="text-right">Max Uses</Label>
                                <Input
                                    id="maxUses"
                                    type="number"
                                    min="1"
                                    value={maxUses}
                                    onChange={(e) => setMaxUses(parseInt(e.target.value))}
                                    className="col-span-3 bg-slate-800 border-slate-700"
                                />
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>Cancel</Button>
                            <Button onClick={handleCreate} disabled={createMutation.isPending}>
                                {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Create Code
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </CardHeader>
            <CardContent>
                <div className="rounded-md border border-slate-800">
                    <Table>
                        <TableHeader className="bg-slate-900/50">
                            <TableRow className="border-slate-800 hover:bg-transparent">
                                <TableHead className="text-slate-400">Code</TableHead>
                                <TableHead className="text-slate-400">Label</TableHead>
                                <TableHead className="text-slate-400">Usage</TableHead>
                                <TableHead className="text-slate-400">Status</TableHead>
                                <TableHead className="text-slate-400">Enabled</TableHead>
                                <TableHead className="text-slate-400">Created At</TableHead>
                                <TableHead className="text-right text-slate-400">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {isLoading ? (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-center py-8">
                                        <Loader2 className="h-6 w-6 animate-spin mx-auto text-primary" />
                                    </TableCell>
                                </TableRow>
                            ) : codes.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-center py-8 text-slate-500">
                                        No registration codes.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                codes.map((code) => {
                                    const statusInfo = getStatusInfo(code);
                                    return (
                                        <TableRow key={code.id} className="border-slate-800 hover:bg-slate-800/30">
                                            <TableCell className="font-mono text-sm">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-primary font-bold">{code.code}</span>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-6 w-6 text-slate-500 hover:text-white"
                                                        onClick={() => copyToClipboard(code.code, code.id)}
                                                    >
                                                        {copiedId === code.id ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
                                                    </Button>
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-slate-300 text-sm">
                                                {code.label ? (
                                                    <span className="text-slate-300">{code.label}</span>
                                                ) : (
                                                    <span className="text-slate-600 italic text-xs">No label</span>
                                                )}
                                            </TableCell>
                                            <TableCell className="text-slate-300">
                                                {code.used_count} / {code.max_uses}
                                            </TableCell>
                                            <TableCell>
                                                <Badge variant="secondary" className={statusInfo.className}>
                                                    {statusInfo.label}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>
                                                <Switch
                                                    checked={code.is_active}
                                                    onCheckedChange={(checked) => toggleMutation.mutate({ id: code.id, is_active: checked })}
                                                    disabled={toggleMutation.isPending}
                                                />
                                            </TableCell>
                                            <TableCell className="text-slate-400 text-xs">
                                                {new Date(code.created_at).toLocaleDateString()}
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <div className="flex items-center justify-end gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        onClick={() => {
                                                            setUsersDialogCodeId(code.id);
                                                            setUsersDialogCodeLabel(code.label || code.code);
                                                        }}
                                                        className="h-8 w-8 text-slate-400 hover:text-white hover:bg-slate-800"
                                                        title="View registered users"
                                                    >
                                                        <Users className="h-4 w-4" />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        onClick={() => deleteMutation.mutate(code.id)}
                                                        disabled={deleteMutation.isPending}
                                                        className="h-8 w-8 text-red-400 hover:text-red-300 hover:bg-red-900/20"
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </TableCell>
                                        </TableRow>
                                    );
                                })
                            )}
                        </TableBody>
                    </Table>
                </div>
            </CardContent>

            {/* Users Dialog */}
            <Dialog open={!!usersDialogCodeId} onOpenChange={(open) => { if (!open) setUsersDialogCodeId(null); }}>
                <DialogContent className="bg-slate-900 border-slate-800 max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Users className="h-4 w-4 text-primary" />
                            Users Registered
                        </DialogTitle>
                        <DialogDescription>
                            Users who registered with code: <span className="font-mono text-primary">{usersDialogCodeLabel}</span>
                        </DialogDescription>
                    </DialogHeader>
                    <div className="max-h-[300px] overflow-y-auto">
                        {isLoadingUsers ? (
                            <div className="flex justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                            </div>
                        ) : codeUsers.length === 0 ? (
                            <p className="text-center py-8 text-slate-500 text-sm">No users have registered with this code yet.</p>
                        ) : (
                            <div className="space-y-2">
                                {codeUsers.map((user) => (
                                    <div key={user.id} className="flex items-center justify-between px-3 py-2 rounded-md bg-slate-800/50 border border-slate-700/50">
                                        <div>
                                            <p className="text-sm font-medium text-white">{user.username}</p>
                                            <p className="text-xs text-slate-400">{user.email}</p>
                                        </div>
                                        <span className="text-[10px] text-slate-500 font-mono">
                                            {new Date(user.created_at).toLocaleDateString()}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setUsersDialogCodeId(null)}>Close</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    );
}

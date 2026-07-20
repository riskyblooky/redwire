'use client';

import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { parseUTCDate } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Key, Plus, Trash2, Copy, Check, Eye, EyeOff, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/api';

interface ApiToken {
    id: string;
    name: string;
    token_prefix: string;
    permission: string;
    user_id: string;
    username?: string;
    user_full_name?: string;
    created_at: string;
    last_used_at: string | null;
    expires_at: string | null;
    is_active: boolean;
    created_by: string | null;
}

interface UserOption {
    id: string;
    username: string;
    full_name: string;
}

export function ApiTokenManagement() {
    const [tokens, setTokens] = useState<ApiToken[]>([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [newName, setNewName] = useState('');
    const [newPerm, setNewPerm] = useState<'ro' | 'rw'>('ro');
    const [newExpiry, setNewExpiry] = useState('');
    const [selectedUser, setSelectedUser] = useState('');
    const [users, setUsers] = useState<UserOption[]>([]);
    const [creating, setCreating] = useState(false);
    const [rawToken, setRawToken] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);
    const [showToken, setShowToken] = useState(false);
    const [showRevoked, setShowRevoked] = useState(false);

    const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const getToken = () => localStorage.getItem('access_token') || '';

    const fetchTokens = useCallback(async () => {
        try {
            const res = await fetch(`${API}/admin/api-tokens`, {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (res.ok) setTokens(await res.json());
        } catch { /* ignore */ } finally {
            setLoading(false);
        }
    }, [API]);

    const fetchUsers = useCallback(async () => {
        try {
            const res = await api.get('/users');
            setUsers(res.data.map((u: UserOption) => ({ id: u.id, username: u.username, full_name: u.full_name })));
        } catch { /* ignore */ }
    }, []);

    useEffect(() => { fetchTokens(); fetchUsers(); }, [fetchTokens, fetchUsers]);

    const handleCreate = async () => {
        if (!newName.trim() || !selectedUser) return;
        setCreating(true);
        try {
            const body: Record<string, unknown> = {
                name: newName,
                permission: newPerm,
                user_id: selectedUser,
            };
            if (newExpiry) body.expires_at = new Date(newExpiry).toISOString();
            const res = await fetch(`${API}/admin/api-tokens`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${getToken()}`,
                },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error('Failed to create token');
            const data = await res.json();
            setRawToken(data.raw_token);
            setShowCreate(false);
            setNewName('');
            setNewPerm('ro');
            setNewExpiry('');
            setSelectedUser('');
            fetchTokens();
            toast.success('Service token created');
        } catch {
            toast.error('Failed to create token');
        } finally {
            setCreating(false);
        }
    };

    const handleRevoke = async (id: string) => {
        try {
            await fetch(`${API}/admin/api-tokens/${id}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            fetchTokens();
            toast.success('Token revoked');
        } catch {
            toast.error('Failed to revoke token');
        }
    };

    const copyToken = () => {
        if (rawToken) {
            navigator.clipboard.writeText(rawToken);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    const activeCount = tokens.filter(t => t.is_active).length;
    const revokedCount = tokens.filter(t => !t.is_active).length;
    const visibleTokens = showRevoked ? tokens : tokens.filter(t => t.is_active);

    return (
        <Card className="border-slate-700 bg-slate-800/50">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-white flex items-center gap-2">
                            <Key className="h-5 w-5" />
                            API Tokens
                            <Badge variant="secondary" className="ml-1">{activeCount} active{revokedCount > 0 ? `, ${revokedCount} revoked` : ''}</Badge>
                        </CardTitle>
                        <CardDescription className="text-slate-400 mt-1">
                            Manage all API tokens across users. Generate service tokens for automation.
                        </CardDescription>
                    </div>
                    <Button
                        size="sm"
                        onClick={() => { setShowCreate(true); setRawToken(null); }}
                        className="bg-emerald-600 hover:bg-emerald-700"
                    >
                        <Plus className="h-4 w-4 mr-1" /> Service Token
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Raw token display */}
                {rawToken && (
                    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 space-y-2">
                        <div className="flex items-center gap-2 text-amber-400 text-sm font-medium">
                            <AlertTriangle className="h-4 w-4" />
                            Copy the token now — it won&apos;t be shown again
                        </div>
                        <div className="flex items-center gap-2">
                            <code className="flex-1 bg-slate-900 text-emerald-400 px-3 py-2 rounded font-mono text-sm break-all">
                                {showToken ? rawToken : '•'.repeat(rawToken.length)}
                            </code>
                            <Button size="icon" variant="ghost" onClick={() => setShowToken(!showToken)} className="shrink-0">
                                {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                            </Button>
                            <Button size="icon" variant="ghost" onClick={copyToken} className="shrink-0">
                                {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                            </Button>
                        </div>
                    </div>
                )}

                {/* Create form */}
                {showCreate && (
                    <div className="bg-slate-900/50 border border-slate-700 rounded-lg p-4 space-y-3">
                        <div className="space-y-2">
                            <Label className="text-slate-200">User</Label>
                            <Select value={selectedUser} onValueChange={setSelectedUser}>
                                <SelectTrigger className="bg-slate-800 border-slate-600 text-white">
                                    <SelectValue placeholder="Select a user..." />
                                </SelectTrigger>
                                <SelectContent>
                                    {users.map((u) => (
                                        <SelectItem key={u.id} value={u.id}>
                                            {u.username} {u.full_name ? `(${u.full_name})` : ''}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-200">Token Name</Label>
                            <Input
                                placeholder="e.g. CI Pipeline, Reporting Service"
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                className="bg-slate-800 border-slate-600 text-white"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-200">Permission</Label>
                            <div className="flex gap-2">
                                <Button
                                    size="sm"
                                    variant={newPerm === 'ro' ? 'default' : 'outline'}
                                    onClick={() => setNewPerm('ro')}
                                    className={newPerm === 'ro' ? 'bg-blue-600' : 'border-slate-600 text-slate-300'}
                                >
                                    Read Only
                                </Button>
                                <Button
                                    size="sm"
                                    variant={newPerm === 'rw' ? 'default' : 'outline'}
                                    onClick={() => setNewPerm('rw')}
                                    className={newPerm === 'rw' ? 'bg-orange-600' : 'border-slate-600 text-slate-300'}
                                >
                                    Read &amp; Write
                                </Button>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-200">Expiration (optional)</Label>
                            <Input
                                type="date"
                                value={newExpiry}
                                onChange={(e) => setNewExpiry(e.target.value)}
                                className="bg-slate-800 border-slate-600 text-white"
                            />
                        </div>
                        <div className="flex gap-2 justify-end">
                            <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)} className="text-slate-400">
                                Cancel
                            </Button>
                            <Button size="sm" onClick={handleCreate} disabled={creating || !newName.trim() || !selectedUser} className="bg-emerald-600 hover:bg-emerald-700">
                                {creating ? 'Creating...' : 'Create Service Token'}
                            </Button>
                        </div>
                    </div>
                )}

                {/* Token table */}
                {loading ? (
                    <p className="text-slate-500 text-sm">Loading tokens...</p>
                ) : tokens.length === 0 ? (
                    <p className="text-slate-500 text-sm">No API tokens have been created.</p>
                ) : (
                    <div className="space-y-2">
                        {revokedCount > 0 && (
                            <div className="flex items-center justify-end">
                                <button
                                    onClick={() => setShowRevoked(!showRevoked)}
                                    className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
                                >
                                    {showRevoked ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                    {showRevoked ? 'Hide' : 'Show'} revoked ({revokedCount})
                                </button>
                            </div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-slate-700 text-slate-400">
                                        <th className="text-left py-2 px-3">User</th>
                                        <th className="text-left py-2 px-3">Name</th>
                                        <th className="text-left py-2 px-3">Prefix</th>
                                        <th className="text-left py-2 px-3">Perm</th>
                                        <th className="text-left py-2 px-3">Status</th>
                                        <th className="text-left py-2 px-3">Created</th>
                                        <th className="text-left py-2 px-3">Last Used</th>
                                        <th className="text-right py-2 px-3"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {visibleTokens.map((t) => (
                                        <tr key={t.id} className={`border-b border-slate-800 ${!t.is_active ? 'opacity-40' : ''}`}>
                                            <td className="py-2 px-3 text-white">{t.username || t.user_id.slice(0, 8)}</td>
                                            <td className="py-2 px-3 text-slate-300">{t.name}</td>
                                            <td className="py-2 px-3 font-mono text-slate-500">{t.token_prefix}...</td>
                                            <td className="py-2 px-3">
                                                <Badge variant="outline" className={t.permission === 'rw' ? 'border-orange-500 text-orange-400' : 'border-blue-500 text-blue-400'}>
                                                    {t.permission === 'rw' ? 'RW' : 'RO'}
                                                </Badge>
                                            </td>
                                            <td className="py-2 px-3">
                                                {t.is_active ? (
                                                    <Badge className="bg-emerald-500/20 text-emerald-400 border-none">Active</Badge>
                                                ) : (
                                                    <Badge variant="destructive" className="text-xs">Revoked</Badge>
                                                )}
                                            </td>
                                            <td className="py-2 px-3 text-slate-500">{parseUTCDate(t.created_at).toLocaleDateString()}</td>
                                            <td className="py-2 px-3 text-slate-500">{t.last_used_at ? parseUTCDate(t.last_used_at).toLocaleDateString() : '—'}</td>
                                            <td className="py-2 px-3 text-right">
                                                {t.is_active && (
                                                    <Button size="icon" variant="ghost" onClick={() => handleRevoke(t.id)} className="text-red-400 hover:text-red-300 h-8 w-8">
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

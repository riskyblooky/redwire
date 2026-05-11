'use client';

import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Key, Plus, Trash2, Copy, Check, Eye, EyeOff, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

interface ApiToken {
    id: string;
    name: string;
    token_prefix: string;
    permission: string;
    created_at: string;
    last_used_at: string | null;
    expires_at: string | null;
    is_active: boolean;
}

export function ApiTokensCard() {
    const [tokens, setTokens] = useState<ApiToken[]>([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [newName, setNewName] = useState('');
    const [newPerm, setNewPerm] = useState<'ro' | 'rw'>('ro');
    const [newExpiry, setNewExpiry] = useState('');
    const [creating, setCreating] = useState(false);
    const [rawToken, setRawToken] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);
    const [showToken, setShowToken] = useState(false);
    const [showRevoked, setShowRevoked] = useState(false);

    const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const getToken = () => localStorage.getItem('access_token') || '';

    const fetchTokens = useCallback(async () => {
        try {
            const res = await fetch(`${API}/api-tokens`, {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (res.ok) setTokens(await res.json());
        } catch { /* ignore */ } finally {
            setLoading(false);
        }
    }, [API]);

    useEffect(() => { fetchTokens(); }, [fetchTokens]);

    const handleCreate = async () => {
        if (!newName.trim()) return;
        setCreating(true);
        try {
            const body: Record<string, unknown> = { name: newName, permission: newPerm };
            if (newExpiry) body.expires_at = new Date(newExpiry).toISOString();
            const res = await fetch(`${API}/api-tokens`, {
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
            fetchTokens();
            toast.success('API token created');
        } catch {
            toast.error('Failed to create token');
        } finally {
            setCreating(false);
        }
    };

    const handleRevoke = async (id: string) => {
        try {
            await fetch(`${API}/api-tokens/${id}`, {
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

    return (
        <Card className="border-slate-700 bg-slate-800/50">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-white flex items-center gap-2">
                            <Key className="h-5 w-5" />
                            API Tokens
                        </CardTitle>
                        <CardDescription className="text-slate-400 mt-1">
                            Generate long-lived tokens for scripts and automation.
                        </CardDescription>
                    </div>
                    <Button
                        size="sm"
                        onClick={() => { setShowCreate(true); setRawToken(null); }}
                        className="bg-primary hover:bg-primary/90"
                    >
                        <Plus className="h-4 w-4 mr-1" /> New Token
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Show raw token after creation */}
                {rawToken && (
                    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 space-y-2">
                        <div className="flex items-center gap-2 text-amber-400 text-sm font-medium">
                            <AlertTriangle className="h-4 w-4" />
                            Copy your token now — it won&apos;t be shown again
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
                            <Label className="text-slate-200">Token Name</Label>
                            <Input
                                placeholder="e.g. CI Pipeline, Reporting Script"
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
                            <Button size="sm" onClick={handleCreate} disabled={creating || !newName.trim()} className="bg-primary hover:bg-primary/90">
                                {creating ? 'Creating...' : 'Create Token'}
                            </Button>
                        </div>
                    </div>
                )}

                {/* Token list */}
                {loading ? (
                    <p className="text-slate-500 text-sm">Loading tokens...</p>
                ) : tokens.length === 0 ? (
                    <p className="text-slate-500 text-sm">No API tokens yet.</p>
                ) : (() => {
                    const revokedCount = tokens.filter(t => !t.is_active).length;
                    const visibleTokens = showRevoked ? tokens : tokens.filter(t => t.is_active);
                    return (
                    <div className="space-y-2">
                        {revokedCount > 0 && (
                            <div className="flex items-center justify-between">
                                <span className="text-xs text-slate-500">
                                    {tokens.filter(t => t.is_active).length} active{revokedCount > 0 && `, ${revokedCount} revoked`}
                                </span>
                                <button
                                    onClick={() => setShowRevoked(!showRevoked)}
                                    className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
                                >
                                    {showRevoked ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                    {showRevoked ? 'Hide' : 'Show'} revoked
                                </button>
                            </div>
                        )}
                        {visibleTokens.map((t) => (
                            <div key={t.id} className={`flex items-center justify-between p-3 rounded-lg border ${t.is_active ? 'border-slate-700 bg-slate-900/30' : 'border-slate-800 bg-slate-900/10 opacity-50'}`}>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-white text-sm font-medium truncate">{t.name}</span>
                                        <Badge variant="outline" className={t.permission === 'rw' ? 'border-orange-500 text-orange-400' : 'border-blue-500 text-blue-400'}>
                                            {t.permission === 'rw' ? 'RW' : 'RO'}
                                        </Badge>
                                        {!t.is_active && <Badge variant="destructive" className="text-xs">Revoked</Badge>}
                                    </div>
                                    <div className="text-xs text-slate-500 mt-1 space-x-3">
                                        <span>{t.token_prefix}...</span>
                                        <span>Created {new Date(t.created_at).toLocaleDateString()}</span>
                                        {t.last_used_at && <span>Last used {new Date(t.last_used_at).toLocaleDateString()}</span>}
                                        {t.expires_at && <span>Expires {new Date(t.expires_at).toLocaleDateString()}</span>}
                                    </div>
                                </div>
                                {t.is_active && (
                                    <Button size="icon" variant="ghost" onClick={() => handleRevoke(t.id)} className="text-red-400 hover:text-red-300 shrink-0">
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                )}
                            </div>
                        ))}
                    </div>
                    );
                })()}
            </CardContent>
        </Card>
    );
}

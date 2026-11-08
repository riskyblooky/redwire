'use client';

import { useMemo, useState } from 'react';
import { Ban, Loader2, LogOut, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { apiErrorMessage } from '@/lib/api';
import {
    SecurityAccount, useDisableUser, useRevokeApiToken, useRevokeSessions, useSecurityAccounts,
} from '@/lib/hooks/use-security-center';
import { useAuthStore } from '@/stores/auth-store';
import { cn } from '@/lib/utils';
import { EmptyRow, Panel, StatCard, TD, TH, ago } from './shared';

type UserFilter = 'all' | 'privileged' | 'no_mfa' | 'dormant' | 'failing' | 'disabled';

const ROLE_LABEL: Record<string, string> = {
    admin: 'Admin', read_only_admin: 'RO Admin', team_lead: 'Team Lead', operator: 'Operator', read_only: 'Read-Only',
};

const TOKEN_FLAG: Record<string, { label: string; cls: string }> = {
    no_expiry: { label: 'no expiry', cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
    read_write: { label: 'read-write', cls: 'bg-orange-500/10 text-orange-400 border-orange-500/20' },
    unused: { label: 'unused', cls: 'bg-slate-500/10 text-slate-300 border-slate-500/20' },
    revoked: { label: 'revoked', cls: 'bg-slate-500/10 text-slate-500 border-slate-600/30' },
    expired: { label: 'expired', cls: 'bg-slate-500/10 text-slate-500 border-slate-600/30' },
};

export function AccountsTab({ canManage }: { canManage: boolean }) {
    const { data, isLoading } = useSecurityAccounts();
    const { user: me } = useAuthStore();
    const [filter, setFilter] = useState<UserFilter>('all');
    const [showInactiveTokens, setShowInactiveTokens] = useState(false);
    const revokeSessions = useRevokeSessions();
    const disableUser = useDisableUser();
    const revokeToken = useRevokeApiToken();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const users = data?.users ?? [];
    const counts = useMemo(() => ({
        privileged: users.filter((u) => u.privileged && u.is_active).length,
        no_mfa: users.filter((u) => u.is_active && !u.mfa && u.auth_provider !== 'saml').length,
        dormant: users.filter((u) => u.dormant).length,
        failing: users.filter((u) => u.failed_24h > 0).length,
        disabled: users.filter((u) => !u.is_active).length,
    }), [users]);

    const shown = users.filter((u) => {
        switch (filter) {
            case 'privileged': return u.privileged && u.is_active;
            case 'no_mfa': return u.is_active && !u.mfa && u.auth_provider !== 'saml';
            case 'dormant': return u.dormant;
            case 'failing': return u.failed_24h > 0;
            case 'disabled': return !u.is_active;
            default: return true;
        }
    }).sort((a, b) => Number(b.privileged) - Number(a.privileged) || a.username.localeCompare(b.username));
    const tokens = (data?.tokens ?? []).filter((t) => showInactiveTokens || !t.flags.some((f) => f === 'revoked' || f === 'expired'));

    // A delegated security manager can't act on admin accounts (server enforces it too).
    const canActOn = (u: SecurityAccount) => canManage && u.id !== me?.id && (u.role !== 'admin' || me?.role === 'admin');

    const run = async (fn: () => Promise<unknown>, ok: string) => {
        try {
            await fn();
            toast.success(ok);
        } catch (e) {
            toast.error(apiErrorMessage(e, 'Action failed'));
        }
    };

    const onSignOut = async (u: SecurityAccount) => {
        if (await confirm({
            title: `Sign ${u.username} out everywhere?`,
            description: 'Every browser session and refresh token for this account stops working immediately. API tokens are not affected — revoke those separately.',
            confirmLabel: 'Sign out everywhere', variant: 'warning',
        }) === true) await run(() => revokeSessions.mutateAsync(u.id), `${u.username} signed out everywhere`);
    };
    const onDisable = async (u: SecurityAccount) => {
        if (await confirm({
            title: `Disable ${u.username}?`,
            description: 'The account is deactivated and all of its sessions are revoked. Re-enable it from the Operators tab.',
            confirmLabel: 'Disable account',
        }) === true) await run(() => disableUser.mutateAsync(u.id), `${u.username} disabled`);
    };

    if (isLoading) return <div className="flex justify-center p-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;

    return (
        <div className="space-y-4">
            <ConfirmDialog />
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                <StatCard label="Privileged accounts" value={counts.privileged} onClick={() => setFilter('privileged')} />
                <StatCard label="Without 2FA" value={counts.no_mfa} tone={counts.no_mfa ? 'warn' : 'good'} onClick={() => setFilter('no_mfa')} />
                <StatCard label={`Dormant (${data?.dormant_days}d+)`} value={counts.dormant} tone={counts.dormant ? 'warn' : 'good'} onClick={() => setFilter('dormant')} />
                <StatCard label="Failed sign-ins · 24h" value={counts.failing} tone={counts.failing ? 'warn' : 'default'} onClick={() => setFilter('failing')} />
                <StatCard label="Disabled" value={counts.disabled} onClick={() => setFilter('disabled')} />
            </div>

            <Panel
                title={<span>Accounts <span className="font-normal text-muted-foreground">· {shown.length}</span></span>}
                action={filter !== 'all' && <button className="text-xs text-primary hover:underline" onClick={() => setFilter('all')}>Show all</button>}
            >
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="border-b border-border">
                            <tr>
                                <th className={TH}>User</th><th className={TH}>Role</th><th className={TH}>Auth</th><th className={TH}>2FA</th>
                                <th className={TH}>Last sign-in</th><th className={TH}>Last IP</th><th className={TH}>Fails 24h</th>
                                <th className={TH}>Tokens</th>{canManage && <th className={TH} />}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                            {shown.length === 0 && <EmptyRow cols={canManage ? 9 : 8}>No accounts match.</EmptyRow>}
                            {shown.map((u) => (
                                <tr key={u.id} className={cn('hover:bg-accent/30', !u.is_active && 'opacity-50')}>
                                    <td className={TD}>
                                        <span className="block text-sm">{u.username}</span>
                                        <span className="block text-xs text-muted-foreground">{u.full_name || u.email}</span>
                                    </td>
                                    <td className={`${TD} text-xs`}>
                                        <span className={cn(u.privileged && 'text-purple-300')}>{ROLE_LABEL[u.role ?? ''] ?? u.role}</span>
                                        {!u.is_active && <Badge variant="outline" className="ml-1.5 text-[10px]">disabled</Badge>}
                                        {u.dormant && <Badge variant="outline" className="ml-1.5 border-amber-500/20 text-[10px] text-amber-400">dormant</Badge>}
                                    </td>
                                    <td className={`${TD} text-xs uppercase text-muted-foreground`}>{u.auth_provider}</td>
                                    <td className={TD}>
                                        {u.mfa ? <ShieldCheck className="h-4 w-4 text-green-400" />
                                            : u.auth_provider !== 'saml'
                                                ? <ShieldAlert className={cn('h-4 w-4', u.privileged ? 'text-red-400' : 'text-amber-400')} />
                                                : <span className="text-xs text-muted-foreground">IdP</span>}
                                    </td>
                                    <td className={`${TD} whitespace-nowrap text-xs text-muted-foreground`}>{u.last_login ? ago(u.last_login) : 'never'}</td>
                                    <td className={`${TD} font-mono text-xs`}>{u.last_ip ?? '—'}</td>
                                    <td className={cn(TD, 'tabular-nums', u.failed_24h > 0 && 'text-red-400')}>{u.failed_24h}</td>
                                    <td className={`${TD} tabular-nums`}>{u.active_tokens}</td>
                                    {canManage && (
                                        <td className={`${TD} whitespace-nowrap text-right`}>
                                            {canActOn(u) && u.is_active && (
                                                <>
                                                    <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => onSignOut(u)}>
                                                        <LogOut className="mr-1 h-3.5 w-3.5" /> Sign out
                                                    </Button>
                                                    <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-red-400 hover:text-red-300" onClick={() => onDisable(u)}>
                                                        <Ban className="mr-1 h-3.5 w-3.5" /> Disable
                                                    </Button>
                                                </>
                                            )}
                                        </td>
                                    )}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </Panel>

            <Panel
                title={<span>API tokens <span className="font-normal text-muted-foreground">· {tokens.length}</span></span>}
                action={
                    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <input type="checkbox" checked={showInactiveTokens} onChange={(e) => setShowInactiveTokens(e.target.checked)} />
                        Show revoked / expired
                    </label>
                }
            >
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="border-b border-border">
                            <tr>
                                <th className={TH}>Token</th><th className={TH}>Owner</th><th className={TH}>Access</th>
                                <th className={TH}>Last used</th><th className={TH}>Expires</th><th className={TH}>Flags</th>{canManage && <th className={TH} />}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                            {tokens.length === 0 && <EmptyRow cols={canManage ? 7 : 6}>No API tokens.</EmptyRow>}
                            {tokens.map((t) => {
                                const owner = users.find((u) => u.id === t.user_id);
                                const active = !t.flags.includes('revoked') && !t.flags.includes('expired');
                                return (
                                    <tr key={t.id} className={cn('hover:bg-accent/30', !active && 'opacity-50')}>
                                        <td className={TD}>
                                            <span className="block text-sm">{t.name}</span>
                                            <span className="block font-mono text-xs text-muted-foreground">{t.token_prefix}…</span>
                                        </td>
                                        <td className={`${TD} text-xs`}>{t.username}</td>
                                        <td className={`${TD} text-xs uppercase`}>{t.permission}</td>
                                        <td className={`${TD} text-xs text-muted-foreground`}>{t.last_used_at ? ago(t.last_used_at) : 'never'}</td>
                                        <td className={`${TD} text-xs text-muted-foreground`}>{t.expires_at ? ago(t.expires_at) : 'never'}</td>
                                        <td className={TD}>
                                            <span className="inline-flex flex-wrap gap-1">
                                                {t.flags.map((f) => (
                                                    <Badge key={f} variant="outline" className={cn('text-[10px]', TOKEN_FLAG[f]?.cls)}>{TOKEN_FLAG[f]?.label ?? f}</Badge>
                                                ))}
                                            </span>
                                        </td>
                                        {canManage && (
                                            <td className={`${TD} text-right`}>
                                                {active && (!owner || canActOn(owner) || owner.id === me?.id) && (
                                                    <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-red-400 hover:text-red-300"
                                                        onClick={async () => {
                                                            if (await confirm({
                                                                title: `Revoke token “${t.name}”?`,
                                                                description: `${t.token_prefix}… (owned by ${t.username}) stops working immediately. This can't be undone.`,
                                                                confirmLabel: 'Revoke',
                                                            }) === true) await run(() => revokeToken.mutateAsync(t.id), 'Token revoked');
                                                        }}>
                                                        <XCircle className="mr-1 h-3.5 w-3.5" /> Revoke
                                                    </Button>
                                                )}
                                            </td>
                                        )}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </Panel>
        </div>
    );
}

'use client';

import { useEffect, useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiErrorMessage } from '@/lib/api';
import {
    Retention, useSecurityEvents, useSecuritySettings, useSensitiveActivity, useUpdateSecuritySettings,
} from '@/lib/hooks/use-security-center';
import { EmptyRow, Pager, Panel, TD, TH, WindowPicker, ago, describeEvent, eventLabel, stamp } from './shared';

const PAGE = 50;
const WINDOWS = [
    { hours: 24, label: '24h' },
    { hours: 24 * 7, label: '7d' },
    { hours: 24 * 30, label: '30d' },
    { hours: 24 * 365, label: '1y' },
];

const ACTION_LABEL: Record<string, string> = {
    updated_setting: 'Changed a setting',
    exported_engagement_with_secrets: 'Exported engagement with secrets',
    accessed_vault_secret: 'Revealed a vault secret',
    deleted_engagement: 'Deleted an engagement',
    consumed_recovery_code: 'Used a 2FA recovery code',
    issued_recovery_codes: 'Issued 2FA recovery codes',
    cleared_recovery_codes: 'Cleared 2FA recovery codes',
    regenerated_recovery_codes: 'Regenerated 2FA recovery codes',
};

function RetentionSettings({ canManage }: { canManage: boolean }) {
    const { data } = useSecuritySettings();
    const update = useUpdateSecuritySettings();
    const [form, setForm] = useState<Retention | null>(null);
    useEffect(() => { if (data) setForm(data.retention); }, [data]);
    if (!form) return null;

    const field = (key: keyof Retention, label: string, min: number, max: number) => (
        <label className="block space-y-1">
            <span className="text-xs text-muted-foreground">{label}</span>
            <Input type="number" min={min} max={max} value={form[key]} disabled={!canManage}
                onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })} className="h-9 w-28" />
        </label>
    );
    return (
        <Panel title="Retention" action={<span className="text-xs text-muted-foreground">pruned hourly</span>}>
            <div className="flex flex-wrap items-end gap-4">
                {field('http_days', 'Raw web requests (days, 1–90)', 1, 90)}
                {field('rollup_days', 'Hourly traffic totals (days)', 30, 3650)}
                {field('events_days', 'Security events (days)', 30, 3650)}
                {canManage && (
                    <Button size="sm" className="h-9" disabled={update.isPending}
                        onClick={async () => {
                            try {
                                await update.mutateAsync(form);
                                toast.success('Retention saved');
                            } catch (e) {
                                toast.error(apiErrorMessage(e, 'Save failed'));
                            }
                        }}>
                        {update.isPending ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />} Save
                    </Button>
                )}
            </div>
        </Panel>
    );
}

export function AuditTab({ canManage }: { canManage: boolean }) {
    const [hours, setHours] = useState(24 * 30);
    const [offset, setOffset] = useState(0);
    const [actOffset, setActOffset] = useState(0);
    const { data: admin } = useSecurityEvents({ audit: true, hours, offset, limit: PAGE });
    const { data: activity } = useSensitiveActivity({ hours, offset: actOffset, limit: PAGE });

    return (
        <div className="space-y-4">
            <WindowPicker value={hours} onChange={(h) => { setHours(h); setOffset(0); setActOffset(0); }} options={WINDOWS} />

            <Panel title={<span>Admin actions {admin && <span className="font-normal text-muted-foreground">· {admin.total}</span>}</span>}>
                <p className="mb-3 text-xs text-muted-foreground">
                    Account and API-token changes, and every successful change to admin configuration (groups, roles, registration codes,
                    authentication / SMTP / SAML, plugins, AI, types, custom fields, marking profiles, wordlists).
                </p>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="border-b border-border">
                            <tr><th className={TH}>Time</th><th className={TH}>Who</th><th className={TH}>Action</th><th className={TH}>Subject</th><th className={TH}>Detail</th><th className={TH}>IP</th></tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                            {admin && admin.items.length === 0 && <EmptyRow cols={6}>No admin actions in this window.</EmptyRow>}
                            {admin?.items.map((e) => (
                                <tr key={e.id} className="hover:bg-accent/30">
                                    <td className={`${TD} whitespace-nowrap text-xs text-muted-foreground`} title={stamp(e.created_at)}>{ago(e.created_at)}</td>
                                    <td className={`${TD} text-xs`}>{e.actor_username ?? '—'}</td>
                                    <td className={`${TD} whitespace-nowrap`}>{eventLabel(e.event_type)}</td>
                                    <td className={`${TD} text-xs`}>{e.event_type === 'config_changed' ? '—' : e.username ?? '—'}</td>
                                    <td className={`${TD} font-mono text-xs text-muted-foreground`}>{describeEvent(e)}</td>
                                    <td className={`${TD} font-mono text-xs`}>{e.ip ?? '—'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {admin && <Pager offset={offset} limit={PAGE} total={admin.total} onChange={setOffset} />}
            </Panel>

            <Panel title={<span>Sensitive activity {activity && <span className="font-normal text-muted-foreground">· {activity.total}</span>}</span>}>
                <p className="mb-3 text-xs text-muted-foreground">
                    Vault secret reveals, exports that include secrets, engagement deletions, setting changes and 2FA recovery codes, from the activity log.
                </p>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="border-b border-border">
                            <tr><th className={TH}>Time</th><th className={TH}>User</th><th className={TH}>Action</th><th className={TH}>Resource</th><th className={TH}>Detail</th></tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                            {activity && activity.items.length === 0 && <EmptyRow cols={5}>Nothing in this window.</EmptyRow>}
                            {activity?.items.map((a) => (
                                <tr key={a.id} className="hover:bg-accent/30">
                                    <td className={`${TD} whitespace-nowrap text-xs text-muted-foreground`} title={stamp(a.created_at)}>{ago(a.created_at)}</td>
                                    <td className={`${TD} text-xs`}>{a.username ?? '—'}</td>
                                    <td className={`${TD} whitespace-nowrap`}>{ACTION_LABEL[a.action] ?? a.action}</td>
                                    <td className={`${TD} text-xs`}>{a.resource_name ?? a.resource_type}</td>
                                    <td className={`${TD} max-w-[360px] truncate text-xs text-muted-foreground`} title={a.details ?? ''}>{a.details ?? ''}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {activity && <Pager offset={actOffset} limit={PAGE} total={activity.total} onChange={setActOffset} />}
            </Panel>

            <RetentionSettings canManage={canManage} />
        </div>
    );
}

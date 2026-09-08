'use client';

import { useEffect, useState } from 'react';
import { usePeerReviewConfig, useUpdatePeerReviewConfig } from '@/lib/hooks/use-admin';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { ShieldCheck, Save } from 'lucide-react';
import { toast } from 'sonner';

export function PeerReviewSettings() {
    const { data, isLoading } = usePeerReviewConfig();
    const update = useUpdatePeerReviewConfig();

    const [required, setRequired] = useState(false);
    const [minApprovals, setMinApprovals] = useState(2);

    useEffect(() => {
        if (data) {
            setRequired(data.required);
            setMinApprovals(data.min_approvals);
        }
    }, [data?.required, data?.min_approvals]);

    const clamped = Math.max(1, Math.min(20, minApprovals || 1));
    const hasChanges = !!data && (required !== data.required || clamped !== data.min_approvals);

    const handleSave = async () => {
        try {
            await update.mutateAsync({ required, min_approvals: clamped });
            setMinApprovals(clamped);
            toast.success('Peer review policy saved');
        } catch {
            toast.error('Failed to update peer review policy');
        }
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-emerald-400" />
                    Finding peer review
                </CardTitle>
                <CardDescription>
                    Require a minimum number of independent operator approvals before any
                    finding can be marked <strong>Verified</strong>. The finding&apos;s own
                    author never counts toward its approvals, and the gate applies to
                    everyone — including team leads and admins performing the verify.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                    <div className="space-y-0.5">
                        <Label htmlFor="pr-required" className="text-sm font-medium text-slate-200">
                            Require peer review to verify
                        </Label>
                        <p className="text-xs text-slate-500">
                            When off, findings can be verified without any approvals (reviews
                            are still recorded for audit).
                        </p>
                    </div>
                    <Switch
                        id="pr-required"
                        checked={required}
                        onCheckedChange={setRequired}
                        disabled={isLoading}
                    />
                </div>

                <div className="flex items-end gap-3">
                    <div className="space-y-1.5">
                        <Label htmlFor="pr-min" className="text-xs text-slate-400">
                            Minimum approvals
                        </Label>
                        <Input
                            id="pr-min"
                            type="number"
                            min={1}
                            max={20}
                            value={minApprovals}
                            onChange={(e) => setMinApprovals(parseInt(e.target.value, 10) || 0)}
                            disabled={isLoading || !required}
                            className="w-24 bg-slate-950/50"
                        />
                    </div>
                    <Button
                        onClick={handleSave}
                        disabled={!hasChanges || update.isPending}
                        size="sm"
                        className="gap-1.5"
                    >
                        <Save className="h-3.5 w-3.5" />
                        Save
                    </Button>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400">
                    {required ? (
                        <p>
                            A finding needs <strong className="text-emerald-400">{clamped}</strong>{' '}
                            distinct non-author {clamped === 1 ? 'approval' : 'approvals'} before it
                            can move to Verified. Any operator who can view the finding can review it.
                        </p>
                    ) : (
                        <p>Peer review is <strong>optional</strong>. Anyone with permission to edit
                            a finding&apos;s status can verify it directly.</p>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

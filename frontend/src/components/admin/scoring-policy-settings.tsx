'use client';

import { useEffect, useMemo, useState } from 'react';
import { useScoringPolicy, useUpdateScoringPolicy } from '@/lib/hooks/use-admin';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { SlidersHorizontal, Save, Lock } from 'lucide-react';
import { toast } from 'sonner';

const NO_LOCK = '__none__';

export function ScoringPolicySettings() {
    const { data, isLoading } = useScoringPolicy();
    const update = useUpdateScoringPolicy();

    const allIds = useMemo(() => (data?.available_models ?? []).map((m) => m.id), [data]);
    const [enabled, setEnabled] = useState<string[]>([]);
    const [defaultModel, setDefaultModel] = useState('');
    const [lockedModel, setLockedModel] = useState('');

    useEffect(() => {
        if (!data) return;
        setEnabled(data.enabled_models ?? allIds);
        setDefaultModel(data.default_model ?? '');
        setLockedModel(data.locked_model ?? '');
    }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

    const toggle = (id: string) =>
        setEnabled((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

    // "all enabled" is stored as null.
    const enabledPayload = enabled.length === allIds.length ? null : enabled;
    const enabledModels = data?.available_models.filter((m) => enabled.includes(m.id)) ?? [];

    const sameSet = (a: string[] | null, b: string[] | null) => {
        const A = a ?? allIds, B = b ?? allIds;
        return A.length === B.length && A.every((x) => B.includes(x));
    };
    const hasChanges = !!data && (
        !sameSet(enabledPayload, data.enabled_models) ||
        (defaultModel || null) !== (data.default_model || null) ||
        (lockedModel || null) !== (data.locked_model || null)
    );

    const handleSave = async () => {
        try {
            await update.mutateAsync({
                enabled_models: enabledPayload,
                default_model: defaultModel || null,
                locked_model: lockedModel || null,
            });
            toast.success('Scoring policy saved');
        } catch {
            toast.error('Failed to update scoring policy');
        }
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                    <SlidersHorizontal className="h-4 w-4 text-amber-400" />
                    Finding scoring models
                </CardTitle>
                <CardDescription>
                    Choose which scoring models are available site-wide, the default for new
                    findings, and optionally lock a single model everywhere. Engagements can
                    narrow the available set further (unless a model is locked here).
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
                <div className="space-y-2">
                    <Label className="text-xs text-slate-400">Enabled models</Label>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {(data?.available_models ?? []).map((m) => (
                            <label
                                key={m.id}
                                className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 cursor-pointer hover:bg-slate-800/40"
                            >
                                <Checkbox
                                    checked={enabled.includes(m.id)}
                                    onCheckedChange={() => toggle(m.id)}
                                    disabled={isLoading || !!lockedModel}
                                />
                                <span className="text-sm text-slate-200">{m.label}</span>
                            </label>
                        ))}
                    </div>
                    {enabled.length === 0 && (
                        <p className="text-xs text-red-400">At least one model should be enabled.</p>
                    )}
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                        <Label className="text-xs text-slate-400">Site default model</Label>
                        <Select value={defaultModel || undefined} onValueChange={setDefaultModel} disabled={isLoading}>
                            <SelectTrigger className="bg-slate-950/50 border-slate-800 h-9 text-sm">
                                <SelectValue placeholder="First enabled" />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                {enabledModels.map((m) => (
                                    <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="space-y-1.5">
                        <Label className="text-xs text-slate-400 flex items-center gap-1">
                            <Lock className="h-3 w-3" /> Lock to one model (site-wide)
                        </Label>
                        <Select
                            value={lockedModel || NO_LOCK}
                            onValueChange={(v) => setLockedModel(v === NO_LOCK ? '' : v)}
                            disabled={isLoading}
                        >
                            <SelectTrigger className="bg-slate-950/50 border-slate-800 h-9 text-sm">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                <SelectItem value={NO_LOCK}>No lock</SelectItem>
                                {(data?.available_models ?? []).map((m) => (
                                    <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                </div>

                <div className="flex items-center justify-between">
                    <p className="text-xs text-slate-500">
                        {lockedModel
                            ? 'Locked: every engagement and finding must use this model.'
                            : 'Not locked: engagements may choose from the enabled models.'}
                    </p>
                    <Button onClick={handleSave} disabled={!hasChanges || update.isPending} size="sm" className="gap-1.5">
                        <Save className="h-3.5 w-3.5" /> Save
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}

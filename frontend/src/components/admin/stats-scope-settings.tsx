'use client';

import { useEffect, useState } from 'react';
import { useStatsScopeMode, useUpdateStatsScopeMode, type StatsScopeMode } from '@/lib/hooks/use-admin';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Globe, Save, Eye, EyeOff } from 'lucide-react';
import { toast } from 'sonner';

export function StatsScopeSettings() {
    const { data, isLoading } = useStatsScopeMode();
    const update = useUpdateStatsScopeMode();

    const [mode, setMode] = useState<StatsScopeMode>('global');
    const [hasChanges, setHasChanges] = useState(false);

    useEffect(() => {
        if (data?.mode) {
            setMode(data.mode);
            setHasChanges(false);
        }
    }, [data?.mode]);

    const handleSave = async () => {
        try {
            await update.mutateAsync(mode);
            toast.success(`Stats scope set to ${mode}`);
            setHasChanges(false);
        } catch {
            toast.error('Failed to update stats scope');
        }
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                    <Globe className="h-4 w-4 text-violet-400" />
                    Stats visibility scope
                </CardTitle>
                <CardDescription>
                    Controls what the dashboard and stats pages show non-admin users.
                    Admins always see full platform-wide data with identifiers.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex items-end gap-3">
                    <div className="flex-1 max-w-sm">
                        <Select
                            value={mode}
                            onValueChange={(v: StatsScopeMode) => {
                                setMode(v);
                                setHasChanges(v !== data?.mode);
                            }}
                            disabled={isLoading}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="global">
                                    <div className="flex items-center gap-2">
                                        <Eye className="h-3.5 w-3.5" />
                                        <span>Global — platform-wide counts</span>
                                    </div>
                                </SelectItem>
                                <SelectItem value="scoped">
                                    <div className="flex items-center gap-2">
                                        <EyeOff className="h-3.5 w-3.5" />
                                        <span>Scoped — assigned engagements only</span>
                                    </div>
                                </SelectItem>
                            </SelectContent>
                        </Select>
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

                <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400 space-y-2">
                    {mode === 'global' ? (
                        <>
                            <div className="flex items-start gap-2">
                                <Badge variant="outline" className="border-violet-500/30 text-violet-400 text-[10px]">Global</Badge>
                                <p>
                                    Non-admins see platform-wide aggregates on dashboard + stats pages.
                                    Identifying fields (engagement names, client names, usernames, finding
                                    titles, activity-log details) are <strong>stripped</strong> from those
                                    responses so the counts don't leak who or what they refer to.
                                </p>
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="flex items-start gap-2">
                                <Badge variant="outline" className="border-blue-500/30 text-blue-400 text-[10px]">Scoped</Badge>
                                <p>
                                    Non-admins see only data from engagements they're assigned to, with
                                    full identifiers (it's their own data). Cross-engagement counts are
                                    not visible.
                                </p>
                            </div>
                        </>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

'use client';

import { CleanupArtifact, useCleanupArtifact } from '@/lib/hooks/use-cleanup-artifacts';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
    Key, FileText, UserCog, ShieldOff, Terminal, Package, HelpCircle,
    CheckCircle2, Clock, AlertTriangle, MinusCircle, MapPin,
    Bug, CheckSquare, Server, Calendar, User, Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const ARTIFACT_TYPES: Record<string, { label: string; icon: any; color: string; bg: string; border: string }> = {
    SSH_KEY: { label: 'SSH Key', icon: Key, color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' },
    FILE: { label: 'File', icon: FileText, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
    ACCOUNT: { label: 'Account', icon: UserCog, color: 'text-primary', bg: 'bg-primary/10', border: 'border-primary/30' },
    PERMISSION: { label: 'Permission', icon: ShieldOff, color: 'text-rose-400', bg: 'bg-rose-500/10', border: 'border-rose-500/30' },
    BACKDOOR: { label: 'Backdoor', icon: Terminal, color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
    IMPLANT: { label: 'Implant', icon: Package, color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30' },
    OTHER: { label: 'Other', icon: HelpCircle, color: 'text-slate-400', bg: 'bg-slate-500/10', border: 'border-slate-500/30' },
};

const STATUS_CONFIG: Record<string, { label: string; icon: any; color: string; bg: string; border: string }> = {
    PENDING: { label: 'Pending', icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30' },
    CLEANED: { label: 'Cleaned', icon: CheckCircle2, color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' },
    PARTIALLY_CLEANED: { label: 'Partially Cleaned', icon: AlertTriangle, color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30' },
    NOT_APPLICABLE: { label: 'N/A', icon: MinusCircle, color: 'text-slate-400', bg: 'bg-slate-500/10', border: 'border-slate-500/30' },
};

interface CleanupDetailModalProps {
    artifact: Partial<CleanupArtifact> | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function CleanupDetailModal({ artifact: partialArtifact, open, onOpenChange }: CleanupDetailModalProps) {
    // When the modal receives a partial artifact (e.g. from a finding/testcase detail page),
    // fetch the full artifact by ID so all fields (linked items, audit info, etc.) are populated.
    const { data: fetchedArtifact, isLoading } = useCleanupArtifact(
        open && partialArtifact?.id ? partialArtifact.id : undefined
    );

    // Use the fetched full artifact if available, otherwise fall back to what was passed in
    const artifact = fetchedArtifact || partialArtifact as CleanupArtifact;

    if (!partialArtifact) return null;

    const typeConfig = ARTIFACT_TYPES[artifact?.artifact_type] || ARTIFACT_TYPES.OTHER;
    const statusConfig = STATUS_CONFIG[artifact?.status] || STATUS_CONFIG.PENDING;
    const TypeIcon = typeConfig.icon;
    const StatusIcon = statusConfig.icon;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[600px] max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-3 text-lg">
                        <div className={cn("p-2 rounded-lg border", typeConfig.bg, typeConfig.border)}>
                            <TypeIcon className={cn("h-4 w-4", typeConfig.color)} />
                        </div>
                        {artifact?.title}
                    </DialogTitle>
                </DialogHeader>

                {isLoading ? (
                    <div className="flex justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin text-lime-400" />
                    </div>
                ) : (
                    <div className="space-y-5 pt-2">
                        {/* Type & Status */}
                        <div className="flex items-center gap-3 flex-wrap">
                            <Badge variant="outline" className={cn("text-xs border", typeConfig.border, typeConfig.color, typeConfig.bg)}>
                                {typeConfig.label}
                            </Badge>
                            <Badge variant="outline" className={cn("text-xs border gap-1.5", statusConfig.border, statusConfig.color, statusConfig.bg)}>
                                <StatusIcon className="h-3 w-3" />
                                {statusConfig.label}
                            </Badge>
                        </div>

                        {/* Location */}
                        {artifact?.location && (
                            <div>
                                <h4 className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1.5">Location</h4>
                                <div className="flex items-center gap-2 text-sm text-slate-300 bg-slate-800/50 rounded-lg px-3 py-2 border border-slate-700/50">
                                    <MapPin className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                                    <code className="text-xs font-mono">{artifact.location}</code>
                                </div>
                            </div>
                        )}

                        {/* Description */}
                        {artifact?.description && (
                            <div>
                                <h4 className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1.5">Description</h4>
                                <p className="text-sm text-slate-300 whitespace-pre-wrap">{artifact.description}</p>
                            </div>
                        )}

                        {/* Cleanup Notes */}
                        {artifact?.cleanup_notes && (
                            <div>
                                <h4 className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1.5">Cleanup Notes</h4>
                                <p className="text-sm text-slate-300 whitespace-pre-wrap bg-slate-800/30 rounded-lg p-3 border border-slate-700/30">
                                    {artifact.cleanup_notes}
                                </p>
                            </div>
                        )}

                        <Separator className="bg-slate-800" />

                        {/* Linked Items */}
                        <div className="space-y-3">
                            <h4 className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Linked Items</h4>

                            {/* Findings */}
                            {artifact?.findings && artifact.findings.length > 0 && (
                                <div className="space-y-1.5">
                                    {artifact.findings.map(f => (
                                        <div key={f.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/5 border border-red-500/20">
                                            <Bug className="h-3.5 w-3.5 text-red-400 shrink-0" />
                                            <span className="text-xs text-white truncate flex-1">{f.title}</span>
                                            <Badge variant="outline" className="text-[9px] border-slate-700 text-slate-400 shrink-0">{f.severity}</Badge>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Test Cases */}
                            {artifact?.testcases && artifact.testcases.length > 0 && (
                                <div className="space-y-1.5">
                                    {artifact.testcases.map(tc => (
                                        <div key={tc.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                                            <CheckSquare className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                                            <span className="text-xs text-white truncate">{tc.title}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Assets */}
                            {artifact?.assets && artifact.assets.length > 0 && (
                                <div className="space-y-1.5">
                                    {artifact.assets.map(a => (
                                        <div key={a.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-500/5 border border-blue-500/20">
                                            <Server className="h-3.5 w-3.5 text-blue-400 shrink-0" />
                                            <span className="text-xs text-white truncate flex-1">{a.name}</span>
                                            <code className="text-[9px] text-slate-500 font-mono shrink-0">{a.identifier}</code>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {(!artifact?.findings || artifact.findings.length === 0) &&
                                (!artifact?.testcases || artifact.testcases.length === 0) &&
                                (!artifact?.assets || artifact.assets.length === 0) && (
                                    <p className="text-xs text-slate-600 italic">No linked items</p>
                                )}
                        </div>

                        <Separator className="bg-slate-800" />

                        {/* Audit Info */}
                        <div className="grid grid-cols-2 gap-4 text-xs">
                            <div className="space-y-1.5">
                                <h4 className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Created</h4>
                                <div className="flex items-center gap-1.5 text-slate-400">
                                    <User className="h-3 w-3" />
                                    <span>{artifact?.created_by_username || 'Unknown'}</span>
                                </div>
                                <div className="flex items-center gap-1.5 text-slate-500">
                                    <Calendar className="h-3 w-3" />
                                    <span>{artifact?.created_at ? new Date(artifact.created_at).toLocaleString() : '—'}</span>
                                </div>
                            </div>
                            {artifact?.cleaned_at && (
                                <div className="space-y-1.5">
                                    <h4 className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Cleaned</h4>
                                    <div className="flex items-center gap-1.5 text-emerald-400">
                                        <User className="h-3 w-3" />
                                        <span>{artifact.cleaned_by_username || 'Unknown'}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5 text-slate-500">
                                        <Calendar className="h-3 w-3" />
                                        <span>{new Date(artifact.cleaned_at).toLocaleString()}</span>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
